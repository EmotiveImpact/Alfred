"""Sealing what ALFRED stores with the keyring's area keys (encryption step 2).

A workspace is either plain or sealed. Plain is the demo and the automated tests, with
synthetic data only, and behaves exactly as ALFRED did before encryption. A sealed
workspace keeps each private text value as ``alfred-seal:...`` (see ``alfred.keys``), bound
to its area and to the table, column and row it belongs to, and keeps keyed fingerprints in
place of plain SHA-256 hashes of private text, so a copied database cannot be used to check
a guess at what it holds.

Every store reaches its sealer as ``store.sealer``. ``TABLES`` lists, for each table that
holds private text, the columns naming a row, the sealed columns and the fingerprint
columns. Code that reads such a table passes each row through ``open_row``; code that
writes one seals with ``seal_row`` (or ``seal``) under the row's area; code that keeps a
hash of private text passes the plain SHA-256 through ``fingerprint``. With the plain
sealer all of them return what they were given, so a plain workspace is unchanged.
"""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import hmac
import re
import sqlite3
import threading
import time
from pathlib import Path

from . import keys
from .local import Fault

DEFAULT_AREA = 'personal'
CACHE_BYTES = 64 << 20


def context(table: str, column: str, *row) -> str:
    """The context a sealed value is bound to: moving it to another row or column fails to open."""
    return '/'.join((table, column, *(str(part) for part in row)))


class Plain:
    """No sealing: values and hashes pass through unchanged."""
    sealed = False
    keyring_id = None

    def seal(self, area, value, context):
        return value

    def open(self, value, context):
        return value

    def fingerprint(self, area, digest):
        return digest

    def clear_cache(self):
        pass

    def close(self):
        pass


PLAIN = Plain()


class Sealed:
    """Seals with an open keyring. Opened values are kept in a bounded memory cache.

    The cache holds text ALFRED has already opened while it runs, which is in its memory
    anyway; it saves opening the same note for every question. ``close`` empties it and
    closes the keyring.
    """
    sealed = True

    def __init__(self, keyring: keys.OpenKeyring, cache_bytes: int = CACHE_BYTES):
        self.keyring, self.cache_bytes = keyring, cache_bytes
        self._cache: OrderedDict[tuple[str, str], tuple[str, int]] = OrderedDict()
        self._cached = 0
        self._lock = threading.Lock()

    @property
    def keyring_id(self) -> str:
        return self.keyring.id

    def seal(self, area, value, context):
        if value is None:
            return None
        if not isinstance(value, str):
            raise Fault('invalid_sealed_value')
        return self.keyring.seal(area, value, context)

    def open(self, value, context):
        """Open a sealed value. Its area is written in it; the context must match where it was sealed."""
        if value is None:
            return None
        parts = value.split(':') if isinstance(value, str) else []
        if len(parts) != 5 or parts[0] != keys.SEAL_PREFIX or not re.fullmatch(r'[1-9][0-9]?', parts[3]):
            raise Fault('not_sealed', 409)
        # Even a cached value needs its area key to still exist, so an area destroyed while
        # ALFRED runs stops opening at once.
        self.keyring.area_key(parts[2], int(parts[3]))
        with self._lock:
            found = self._cache.get((value, context))
            if found is not None:
                self._cache.move_to_end((value, context))
                return found[0]
        opened = self.keyring.open(parts[2], value, context).decode('utf-8')
        size = len(value) + len(opened.encode('utf-8')) + len(context.encode('utf-8'))
        with self._lock:
            if (value, context) not in self._cache and size <= self.cache_bytes:
                self._cache[(value, context)] = (opened, size)
                self._cached += size
                while self._cached > self.cache_bytes:
                    _, (_, dropped) = self._cache.popitem(last=False)
                    self._cached -= dropped
        return opened

    def fingerprint(self, area, digest):
        """A keyed fingerprint for a plain SHA-256 hex digest of private text.

        Keyed with the area's first key, so it stays the same when the area's key is
        rotated, and becomes meaningless when the area is destroyed.
        """
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise Fault('invalid_digest')
        key = self.keyring.fingerprint_key(area)  # refuses a destroyed area, cached or not
        return hmac.new(key, bytes.fromhex(digest), hashlib.sha256).hexdigest()

    def clear_cache(self):
        """Forget every opened value, for example after ALFRED is told to forget a note."""
        with self._lock:
            self._cache.clear()
            self._cached = 0

    def close(self):
        self.clear_cache()
        self.keyring.close()


class Connection(sqlite3.Connection):
    """A database connection that carries its workspace's sealer, so code holding only the
    connection can still open and seal (``of(db)``)."""
    sealer = PLAIN


def of(db):
    """The sealer of a connection; plain for one not made by a store."""
    return getattr(db, 'sealer', PLAIN)


# Which sealer serves which database ----------------------------------------
#
# One ALFRED process serves one workspace database, but builds many store objects over
# it. The host attaches its sealer to the database path once, at start, and every store
# made for that path finds it.

_attached: dict[Path, Plain | Sealed] = {}


def _key(path) -> Path:
    return Path(path).expanduser().resolve()


def attach(path, sealer) -> None:
    _attached[_key(path)] = sealer


def detach(path) -> None:
    sealer = _attached.pop(_key(path), None)
    if sealer is not None:
        sealer.close()


def for_path(path):
    return _attached.get(_key(path), PLAIN)


def check(db, sealer, clock=time.time) -> None:
    """Match the database to the sealer, in the caller's transaction.

    A sealed database refuses to open without its keyring. A sealer on a database that is
    not sealed is refused, unless the database holds no workspace yet, in which case it is
    marked sealed from the start. Converting a plain workspace is the ``seal`` command's job.
    A database holding sealed values without its record is refused either way, so losing
    the record can never let plain text be written beside sealed text.
    """
    db.execute('CREATE TABLE IF NOT EXISTS sealing(keyring TEXT NOT NULL, default_area TEXT NOT NULL, '
               'sealed_at INTEGER NOT NULL)')
    rows = db.execute('SELECT keyring FROM sealing').fetchall()
    if len(rows) > 1 or (not rows and holds_sealed_values(db)):
        raise Fault('sealing_record_damaged', 409)
    if rows and not sealer.sealed:
        raise Fault('workspace_locked', 423)
    if rows and rows[0][0] != sealer.keyring_id:
        raise Fault('wrong_keyring', 409)
    if sealer.sealed and not rows:
        if db.execute('SELECT 1 FROM credentials LIMIT 1').fetchone():
            raise Fault('workspace_not_sealed', 409)
        db.execute('INSERT INTO sealing VALUES (?,?,?)', (sealer.keyring_id, DEFAULT_AREA, int(clock())))


def recorded(path) -> str | None:
    """The keyring a workspace database records it was sealed with, read without opening a
    store; None for a plain workspace or no database yet. ALFRED reads this at start, to know
    whether it must unlock the keyring before anything else touches the database."""
    path = Path(path).expanduser()
    if not path.is_file():
        return None
    from contextlib import closing
    with closing(sqlite3.connect(path, timeout=5)) as db:
        if not _has(db, 'sealing'):
            return None
        rows = db.execute('SELECT keyring FROM sealing').fetchall()
    if len(rows) > 1:
        raise Fault('sealing_record_damaged', 409)
    return rows[0][0] if rows else None


def default_area(db) -> str:
    row = db.execute('SELECT default_area FROM sealing').fetchone() if _has(db, 'sealing') else None
    return row[0] if row else DEFAULT_AREA


def _has(db, table) -> bool:
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def holds_sealed_values(db) -> bool:
    """Whether any registered table holds a sealed value. Each table's first sealed column is
    read until one sealed value is found, so the check reads little even when note text is
    large. A table that keeps only fingerprints has nothing to find."""
    prefix = keys.SEAL_PREFIX + ':'
    return any(sealed and _has(db, table) and db.execute(
        f'SELECT 1 FROM {table} WHERE substr({sealed[0]},1,?)=? LIMIT 1', (len(prefix), prefix)).fetchone()
        for table, (_, sealed, _) in TABLES.items())


# The tables that hold private text --------------------------------------------
#
# table: (columns naming a row, sealed columns, fingerprint columns). Fingerprint columns
# hold the keyed form of a plain SHA-256 hex digest, so converting a plain workspace keys
# the digests it already has.

TABLES: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    'knowledge_sources': (('scope', 'source'), ('label', 'errors'), ('snapshot',)),
    'knowledge_notes': (('scope', 'source', 'id'), ('path', 'title', 'tags', 'aliases', 'body'), ('sha256',)),
    'knowledge_refs': (('scope', 'source', 'origin', 'line', 'syntax', 'relation'), ('target',), ()),
    'knowledge_vaults': (('scope', 'source'), ('configuration',), ()),
    'knowledge_history': (('scope', 'source', 'id', 'revision'), ('path',), ('sha256',)),
    'knowledge_anchors': (('scope', 'source', 'id'), ('anchors',), ()),
    'knowledge_conflicts': (('scope', 'source'), ('path', 'original_path'), ()),
    'connector_instances': (('scope', 'source'), ('label',), ()),
    'connector_receipts': (('scope', 'source', 'id'), ('receipt',), ()),
    # Reviewed memory, its bin and capture (part 2). A statement keeps keyed fingerprints of its
    # request, its note and its quote; a captured line is kept only as a keyed fingerprint.
    'memory_entities': (('id',), ('name',), ()),
    'memory_claims': (('id',), ('value',), ('request_hash', 'note_hash', 'quote_hash')),
    'memory_capture': (('claim_id',), ('captured_from',), ()),
    'memory_bin': (('id',), ('snapshot',), ()),
    'capture_policies': (('scope', 'actor', 'id'), ('name', 'rule'), ()),
    'capture_proposals': (('scope', 'actor', 'claim_id'), (), ('line_hash',)),
    # Conversations, executive records, drafts and actions (part 3). A request's hash, an
    # action's fingerprint, a local draft's digest and a read-aloud hash cover the text, so
    # they are keyed; an action's parameters and proof, and a draft's source binding, are
    # sealed whole.
    'conversations': (('id',), ('title',), ()),
    'conversation_turns': (('id',), ('question', 'result'), ('request_hash',)),
    'conversation_action_sources': (('scope', 'action_id'), ('references_json',), ()),
    'executive_records': (('id',), ('title', 'detail', 'responsible', 'options', 'rationale'), ('request_hash',)),
    'executive_progress': (('record', 'seq'), ('note',), ()),
    'executive_decisions': (('record', 'seq'), ('option_label', 'rationale'), ()),
    'actions': (('scope', 'id'), ('parameters', 'proof'), ('fingerprint',)),
    'drafts': (('scope', 'action_id'), ('body',), ('digest',)),
    'draft_sources': (('scope', 'action_id'), ('binding',), ()),
    'voice_playbacks': (('id',), (), ('text_sha256',)),
    # What the desk observes (part 4). An event's body holds what a source reported and is
    # sealed whole; the file names and titles of the documents and links the desk lists are
    # sealed; the fingerprints of events and of document files are keyed.
    'events': (('seq',), ('body',), ('fingerprint',)),
    'desk_documents': (('scope', 'source', 'document_id'), ('filename', 'title'), ('sha256',)),
    'desk_links': (('seq',), ('filename', 'title'), ('sha256',)),
    'desk_action_evidence': (('scope', 'action_id'), (), ('event_fingerprint',)),
    # Jobs, their results and workers (part 4, ``jobs.job_area``). A result is addressed by the
    # keyed SHA-256 of its bytes, which also names it in jobs, lineage, job events and the
    # cache; its bytes are sealed as Base64 text.
    'jobs': (('id',), ('parameters',), ('fingerprint',)),
    'workers': (('scope', 'id'), ('label',), ()),
    'artefacts': (('scope', 'sha256'), ('body',), ('sha256',)),
    # Brain tasks (part 4, ``brain.brain_area``): a result's outcome holds the brain's answer;
    # proposals and memory suggestions hold what it proposed and why.
    'brain_tasks': (('job_id',), (), ('packet_sha256',)),
    'brain_results': (('job_id',), ('outcome',), ('envelope_sha256',)),
    'brain_proposals': (('id',), ('parameters', 'reason', 'cites', 'provenance', 'confirmation'), ('fingerprint',)),
    'brain_suggestions': (('id',), ('statement', 'cites'), ()),
    # Verification of brain results (part 4, in the brain task's area): a run's report quotes
    # what the checks found, so it is sealed and its hash keyed.
    'verification_runs': (('id',), ('report',), ('report_sha256',)),
    'verification_results': (('job_id',), (), ('last_run_sha256',)),
    # Learnings (part 4, ``learning.learning_area``). A harvested learning's key and signature
    # are keyed fingerprints of a worker's text; other keys and signatures are ALFRED's codes.
    'learning_proposals': (('id',), ('statement', 'detail', 'evidence'), ()),
    'learning_records': (('id',), ('statement', 'detail', 'evidence'), ()),
    # Goals the hub works on (part 4, ``hub_goals.goal_area``): a mandate's success test,
    # schedule (which holds the task's instruction) and acceptance checks, and what the
    # append-only hub journal records about each change.
    'hub_mandates': (('id',), ('success_test', 'schedule', 'acceptance'), ('request_hash',)),
    'hub_journal': (('seq',), ('detail',), ()),
}

# Columns holding stable ids taken from private text (a note's front-matter id, an imported
# item's id). A sealed workspace keeps them keyed (``KnowledgeStore.external_key``), so they
# still match exactly but say nothing without the key.
KEYED_IDS: dict[str, tuple[str, ...]] = {
    'knowledge_identity': ('external_id',),
    'connector_item_revisions': ('item',),
    # An event's subject and a desk document's id, which a source chose (``local.event_key``).
    'events': ('subject',),
    'desk_documents': ('document_id',),
}


def area_of(value) -> str | None:
    """The area written in a sealed value; None for a value that is not sealed."""
    parts = value.split(':') if isinstance(value, str) else []
    return parts[2] if len(parts) == 5 and parts[0] == keys.SEAL_PREFIX else None


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def row_context(table, column, row) -> str:
    names, _, _ = TABLES[table]
    return context(table, column, *(row[name] for name in names))


def open_row(sealer, table, row):
    """A row as a dict with its sealed columns opened. Columns not selected are left out."""
    if row is None:
        return None
    row = dict(row)
    if not sealer.sealed:
        return row
    _, sealed, _ = TABLES[table]
    for column in sealed:
        if row.get(column) is not None:
            row[column] = sealer.open(row[column], row_context(table, column, row))
    return row


def seal_row(sealer, table, area, row: dict, stored=None) -> dict:
    """The row with its sealed columns sealed under ``area``, ready to write.

    ``stored`` is the same row as the database holds it now, if it exists. A column whose
    text has not changed keeps its stored sealed value, so rescanning an unchanged vault
    writes nothing new and seals nothing.
    """
    row = dict(row)
    if not sealer.sealed:
        return row
    _, sealed, _ = TABLES[table]
    for column in sealed:
        if row.get(column) is None:
            continue
        where = row_context(table, column, row)
        kept = stored.get(column) if stored is not None else None
        if kept is not None and area_of(kept) == area and sealer.open(kept, where) == row[column]:
            row[column] = kept
        else:
            row[column] = sealer.seal(area, row[column], where)
    return row
