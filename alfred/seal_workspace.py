"""Switching a workspace to sealed, re-sealing an area after its key is rotated, and
compacting the database (encryption step 2, part 5).

``seal`` converts a plain workspace once. In one transaction it seals every value the
register in ``alfred.sealing`` names, replaces every plain fingerprint with its keyed form
(and every copy of it ALFRED made: in job inputs and lineage, job events, answers, packets
and the audit log's short references), keys the ids a source chose, makes again the ids
ALFRED derives from them, and rewrites the append-only tables once under the same rule.
Before it commits it opens every sealed value again and checks that no plain fingerprint is
left anywhere in the database; anything wrong rolls the whole conversion back, so the
workspace is either still plain or wholly sealed. The job cache, an accelerator, is emptied
in the same step, since its files are named by plain hashes. Then the database is compacted
and its write-ahead log truncated, so no plain copy is left in the file or its log, and the
backups ALFRED keeps beside it are converted the same way.

A marker file beside the database says a conversion or re-sealing has started and not
finished. While it is there ALFRED refuses to start (``sealing_incomplete``); running the
same command again finishes the work, since each step checks what is already done.

Every record is in the workspace's default area. Folder and source rules for areas come
after the owner's choice about answers drawing on several areas.
"""
from __future__ import annotations
import base64
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time

from . import sealing
from .local import Fault

MARKER = '.sealing'
RESEALING = '.resealing'
FULL = re.compile(r'[0-9a-f]{64}')
TOKEN = re.compile(r'(?<![0-9a-f])[0-9a-f]{16,64}(?![0-9a-f])')
# Short forms of a fingerprint kept in logs and references.
SHORT = (16, 24)
# Copies of the owner's own files, kept exactly as read; what a worker was sent, which its
# result names by hash; and result bytes, kept exactly as a worker returned them and named
# by their own hash. They are sealed as they are.
VERBATIM = {('knowledge_notes', c) for c in ('path', 'title', 'tags', 'aliases', 'body')} | {
    ('knowledge_history', 'path'), ('knowledge_refs', 'target'), ('knowledge_anchors', 'anchors'),
    ('knowledge_conflicts', 'path'), ('knowledge_conflicts', 'original_path'), ('jobs', 'parameters'),
    ('artefacts', 'body')}
# Work that is still running binds hashes a worker will check; it must settle first.
HARVESTED = ('learning_proposals', 'learning_records')
IN_FLIGHT = "SELECT count(*) FROM jobs WHERE state IN ('queued','leased','running','cancel_requested')"


def marker(database, suffix=MARKER) -> Path:
    database = Path(database)
    return database.with_name(database.name + suffix)


def incomplete(database) -> str | None:
    """Which unfinished step a marker beside the database names, if any."""
    for suffix, step in ((MARKER, 'seal'), (RESEALING, 'reseal')):
        if marker(database, suffix).exists() or marker(database, suffix).is_symlink():
            return step
    return None


def _mark(database, suffix, text):
    fd = os.open(marker(database, suffix), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def _connect(database, sealer):
    db = sqlite3.connect(database, timeout=5, isolation_level=None, factory=sealing.Connection)
    db.sealer = sealer
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA busy_timeout=5000')
    # Changing a key column means rewriting rows the foreign keys point at; the conversion
    # checks every foreign key itself before it commits.
    db.execute('PRAGMA foreign_keys=OFF')
    # Pages freed while converting are overwritten, not left holding the plain text.
    db.execute('PRAGMA secure_delete=ON')
    return db


def compact(database) -> bool:
    """Rebuild the database without free pages and truncate its write-ahead log, so text that
    was removed or replaced is no longer in either file. True when both were done; False when
    another connection kept the database busy past the timeout, in which case the next
    compaction (another absolute forget, a restore that applies one, or ``seal``) catches up."""
    try:
        with closing(sqlite3.connect(database, timeout=5, isolation_level=None)) as db:
            db.execute('PRAGMA busy_timeout=5000')
            db.execute('PRAGMA secure_delete=ON')
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            db.execute('VACUUM')
            busy = db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
    except sqlite3.OperationalError:
        return False
    return not busy or not busy[0]


def _compacted(database):
    """Compact after sealing or re-sealing, or stop with the marker still in place: until the
    old copies are out of the file and its log the work is not finished."""
    if not compact(database):
        raise Fault('workspace_busy', 409)


def _tables(db):
    return [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                                     "AND name!='sealing' ORDER BY name")]


def _columns(db, table):
    return [r[1] for r in db.execute(f'PRAGMA table_info({table})')]


def _keyed(sealer, area, digest):
    """An id ALFRED derived from a plain hash and cannot make again: keyed in place, so it stays
    unique and says nothing without the key."""
    return sealer.fingerprint(area, hashlib.sha256(('converted\0' + digest).encode()).hexdigest())[:len(digest)]


def _plan(db, sealer, area):
    """Every plain fingerprint and derived id in the database with what it becomes."""
    tokens = {}
    for table, (_, _, prints) in sealing.TABLES.items():
        if not sealing._has(db, table):
            continue
        for column in prints:
            for (value,) in db.execute(f'SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL'):
                if isinstance(value, str) and FULL.fullmatch(value):
                    tokens[value] = sealer.fingerprint(area, value)
    # A file digest an action binds or proves (an inbox note, an insertion, the note after it)
    # is keyed in a sealed workspace, as the index keeps it (alfred/knowledge.py file_digest).
    if sealing._has(db, 'actions'):
        for row in db.execute('SELECT parameters,proof FROM actions'):
            for value in (v for text in row if text for v in _digests(json.loads(text))):
                tokens.setdefault(value, sealer.fingerprint(area, value))
    # A source's snapshot is the keyed hash of its notes' paths and keyed hashes; it is made
    # again from the notes it names, or keyed in place if they no longer match it.
    if sealing._has(db, 'knowledge_sources'):
        for row in db.execute('SELECT scope,source,snapshot FROM knowledge_sources'):
            notes = sorted(db.execute('SELECT path,sha256 FROM knowledge_notes WHERE scope=? AND source=?',
                                      (row['scope'], row['source'])).fetchall(), key=lambda n: n['path'])
            made = lambda pairs: hashlib.sha256(json.dumps(pairs, sort_keys=True).encode()).hexdigest()
            if notes and made([(n['path'], n['sha256']) for n in notes]) == row['snapshot'] and all(n['sha256'] in tokens for n in notes):
                tokens[row['snapshot']] = sealer.fingerprint(area, made([(n['path'], tokens[n['sha256']]) for n in notes]))
    ids = {}
    for table, columns in sealing.KEYED_IDS.items():
        if sealing._has(db, table):
            for column in columns:
                for (value,) in db.execute(f'SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL'):
                    ids[value] = sealer.fingerprint(area, sealing.text_digest(value))
    # A desk document's event id is made from its keyed id and revision (alfred/desk_store.py).
    if sealing._has(db, 'desk_links') and sealing._has(db, 'events'):
        for row in db.execute("SELECT e.event_id,e.subject,l.revision FROM events e JOIN desk_links l ON l.seq=e.seq "
                              "WHERE e.event_id LIKE 'doc-%'"):
            old = row['event_id'][4:]
            if row['subject'] in ids and old == hashlib.sha256(f"{row['subject']}:{row['revision']}".encode()).hexdigest():
                tokens[old] = hashlib.sha256(f"{ids[row['subject']]}:{row['revision']}".encode()).hexdigest()
    # A captured statement's request id is made from its line's keyed hash (alfred/capture_policies.py).
    if sealing._has(db, 'capture_proposals') and sealing._has(db, 'memory_claims'):
        for row in db.execute('SELECT x.policy_id,x.note_id,x.revision,x.line,x.line_hash,c.request_id FROM capture_proposals x '
                              'JOIN memory_claims c ON c.id=x.claim_id'):
            made = lambda line_hash: hashlib.sha256(
                f"{row['policy_id']}|{row['note_id']}|{row['revision']}|{row['line']}|{line_hash}".encode()).hexdigest()[:40]
            old = row['request_id'][len('capture-'):]
            if row['request_id'].startswith('capture-') and old == made(row['line_hash']) and row['line_hash'] in tokens:
                tokens[old] = made(tokens[row['line_hash']])
    # Ids derived from a plain hash whose inputs are not kept: a deferred capture and a
    # confirmed brain draft's action.
    if sealing._has(db, 'capture_deferred'):
        for (item,) in db.execute('SELECT DISTINCT item FROM capture_deferred'):
            tokens.setdefault(item, _keyed(sealer, area, item))
    if sealing._has(db, 'actions'):
        for (identity,) in db.execute("SELECT id FROM actions WHERE id LIKE 'act-bc-%'"):
            tokens.setdefault(identity[7:], _keyed(sealer, area, identity[7:]))
    # A harvested learning's key and signature are the keyed hash of a worker's text
    # (alfred/learning.py). The same hash stays plain inside the sealed detail and evidence,
    # as in a workspace sealed from the start, so it is replaced in these columns only.
    learned = {}
    for table in HARVESTED:
        if sealing._has(db, table):
            for (signature,) in db.execute(f"SELECT signature FROM {table} WHERE key='harvest:'||signature"):
                if FULL.fullmatch(signature):
                    learned[signature] = sealer.fingerprint(area, signature)
    short = {(n, plain[:n]): keyed[:n] for plain, keyed in tokens.items() if len(plain) == 64 for n in SHORT}
    return tokens, short, ids, learned


def _digests(value):
    """The SHA-256 values under keys ending in ``sha256`` anywhere in a decoded record."""
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key.endswith('sha256') and isinstance(item, str) and FULL.fullmatch(item):
                yield item
            else:
                yield from _digests(item)
    elif isinstance(value, list):
        for item in value:
            yield from _digests(item)


def _swapper(tokens, short):
    def swap(match):
        token = match.group(0)
        if token in tokens:
            return tokens[token]
        return short.get((len(token), token), token)
    return lambda text: TOKEN.sub(swap, text)


def _convert(db, sealer, area, now) -> tuple:
    """Seal one plain database in the caller's transaction. Returns what it changed, and the
    plain fingerprints with their keyed forms."""
    if db.execute('SELECT count(*) FROM sealing').fetchone()[0] or sealing.holds_sealed_values(db):
        raise Fault('sealing_record_damaged', 409)
    if sealing._has(db, 'jobs') and db.execute(IN_FLIGHT).fetchone()[0]:
        raise Fault('work_in_flight', 409)
    tokens, short, ids, learned = _plan(db, sealer, area)
    swap = _swapper(tokens, short)
    triggers = db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'").fetchall()
    for name, _ in triggers:
        # The append-only tables refuse every change; they are rewritten once, here.
        db.execute(f'DROP TRIGGER {name}')
    counts = {'values_sealed': 0, 'fingerprints_keyed': len(tokens) + len(learned), 'ids_keyed': len(ids), 'rows_rewritten': 0}
    for table in _tables(db):
        names, sealed, _ = sealing.TABLES.get(table, ((), (), ()))
        keyed_ids = sealing.KEYED_IDS.get(table, ())
        columns = _columns(db, table)
        for row in db.execute(f'SELECT rowid AS _row,* FROM {table}').fetchall():
            new = {c: row[c] for c in columns}
            for column in columns:
                value = new[column]
                if value is None:
                    continue
                if column in keyed_ids:
                    new[column] = ids[value]
                elif table in HARVESTED and column in ('key', 'signature') and row['signature'] in learned:
                    new[column] = (column == 'key') * 'harvest:' + learned[row['signature']]
                elif isinstance(value, str) and (table, column) not in VERBATIM:
                    new[column] = swap(value)
            for column in sealed:
                value = new[column]
                if value is None:
                    continue
                if isinstance(value, bytes):
                    value = base64.b64encode(value).decode('ascii')
                new[column] = sealer.seal(area, value, sealing.row_context(table, column, new))
                counts['values_sealed'] += 1
            changed = [c for c in columns if new[c] != row[c]]
            if changed:
                db.execute(f"UPDATE {table} SET {','.join(f'{c}=?' for c in changed)} WHERE rowid=?",
                           (*(new[c] for c in changed), row['_row']))
                counts['rows_rewritten'] += 1
    for _, sql in triggers:
        db.execute(sql)
    db.execute('INSERT INTO sealing VALUES (?,?,?)', (sealer.keyring_id, sealing.DEFAULT_AREA, int(now)))
    _check(db, sealer, {**tokens, **learned}, short)
    return counts, tokens


def _check(db, sealer, tokens, short):
    """Before committing: every sealed value opens where it is, no plain fingerprint or short
    form of one is left anywhere, and every foreign key still holds."""
    for table, (_, sealed, _) in sealing.TABLES.items():
        if sealed and sealing._has(db, table):
            for row in db.execute(f'SELECT * FROM {table}'):
                sealing.open_row(sealer, table, row)
    for table in _tables(db):
        for row in db.execute(f'SELECT * FROM {table}'):
            for value in tuple(row):
                if isinstance(value, str) and any(m.group(0) in tokens or (len(m.group(0)), m.group(0)) in short
                                                  for m in TOKEN.finditer(value)):
                    raise Fault('plain_fingerprint_left', 500)
    if db.execute('PRAGMA foreign_key_check').fetchone():
        raise Fault('foreign_key_broken', 500)


def _empty_cache(cache_dir, tokens):
    """The job cache names its files by plain hashes and holds plain copies; it is an
    accelerator, so its entries go and it fills again, sealed, as results are read. A pin, a
    wish to keep a result offline, follows the result to its keyed address; a pin on anything
    else is dropped, since its name is a plain hash. The cache keeps its folders and index."""
    root = Path(cache_dir) if cache_dir is not None else None
    if root is None or not root.exists():
        return False
    if root.is_symlink() or not root.is_dir():
        raise Fault('cache_directory_unsafe', 409)
    for name in ('objects', 'incoming'):
        folder = root / name
        for item in (folder.rglob('*') if folder.is_dir() and not folder.is_symlink() else ()):
            if item.is_file() or item.is_symlink():
                item.unlink()
    index = root / 'index.sqlite3'
    if index.is_file() and not index.is_symlink():
        with closing(sqlite3.connect(index, timeout=5, isolation_level=None)) as db:
            db.execute('PRAGMA busy_timeout=5000')
            db.execute('PRAGMA secure_delete=ON')
            if sealing._has(db, 'entries'):
                db.execute('DELETE FROM entries')
            if sealing._has(db, 'pins'):
                pins = [r[0] for r in db.execute('SELECT sha256 FROM pins')]
                db.execute('DELETE FROM pins')
                db.executemany('INSERT OR IGNORE INTO pins VALUES (?)', [(tokens[p],) for p in pins if p in tokens])
            db.execute('VACUUM')
    return True


def _seal_file(database, sealer, area, clock, *, cache_dir=None) -> dict | None:
    """Convert one database file, unless it is already sealed. None when it was."""
    with closing(_connect(database, sealer)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS sealing(keyring TEXT NOT NULL, default_area TEXT NOT NULL, '
                   'sealed_at INTEGER NOT NULL)')
        db.execute('BEGIN IMMEDIATE')
        try:
            rows = db.execute('SELECT keyring FROM sealing').fetchall()
            if rows:
                db.execute('ROLLBACK')
                if len(rows) > 1:
                    raise Fault('sealing_record_damaged', 409)
                if rows[0][0] != sealer.keyring_id:
                    raise Fault('wrong_keyring', 409)
                return None
            counts, tokens = _convert(db, sealer, area, clock())
            counts['cache_emptied'] = _empty_cache(cache_dir, tokens)
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
    return counts


def _backups(database):
    """The backups ALFRED registered or keeps beside the workspace, with their manifests."""
    found = {}
    with closing(sqlite3.connect(database, timeout=5)) as db:
        if sealing._has(db, 'lifecycle_backups'):
            for identity, file in db.execute('SELECT id,file FROM lifecycle_backups'):
                found[Path(file)] = identity
    for path in list(found):
        if not path.is_file() or path.is_symlink() or not path.with_suffix('.json').is_file():
            del found[path]
    return found


def _backup_resealed(database, path, identity, sealed_by):
    """A converted or re-sealed backup's manifest and register entry name its new bytes."""
    manifest_path = path.with_suffix('.json')
    manifest = json.loads(manifest_path.read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    from .lifecycle import manifest_sealing
    manifest |= {'sha256': digest, **manifest_sealing(sealed_by)}
    manifest_path.write_text(json.dumps(manifest, indent=1) + '\n')
    manifest_path.chmod(0o600)
    with closing(sqlite3.connect(database, timeout=5, isolation_level=None)) as db:
        db.execute('PRAGMA busy_timeout=5000')
        db.execute('UPDATE lifecycle_backups SET sha256=? WHERE id=?', (digest, identity))


def seal(database, sealer, *, cache_dir=None, clock=time.time) -> dict:
    """Convert a plain workspace, then its backups, then compact. Safe to run again: a sealed
    workspace is only compacted, and backups already sealed are left as they are."""
    database = Path(database)
    if not sealer.sealed:
        raise Fault('keyring_required', 423)
    if not database.is_file() or database.is_symlink():
        raise Fault('workspace_not_found', 404)
    area = sealing.DEFAULT_AREA
    sealer.keyring.area_key(area)  # the default area must exist, and not be destroyed
    _mark(database, MARKER, sealer.keyring_id)
    counts = _seal_file(database, sealer, area, clock, cache_dir=cache_dir)
    _compacted(database)
    converted = 0
    for path, identity in _backups(database).items():
        if _seal_file(path, sealer, area, clock) is not None:
            converted += 1
        _compacted(path)
        for suffix in ('-wal', '-shm'):
            Path(str(path) + suffix).unlink(missing_ok=True)
        _backup_resealed(database, path, identity, sealer)
    marker(database).unlink()
    return {'already_sealed': counts is None, **(counts or {}), 'backups_sealed': converted}


# Re-sealing after a key rotation ----------------------------------------------

def _reseal_file(database, sealer, area) -> int:
    """Seal again, under the area's newest key, every value of ``area`` sealed with an older one."""
    newest, _ = sealer.keyring.area_key(area)
    resealed = 0
    with closing(_connect(database, sealer)) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            if not db.execute('SELECT 1 FROM sealing').fetchone():
                raise Fault('workspace_not_sealed', 409)
            triggers = db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'").fetchall()
            for name, _ in triggers:
                db.execute(f'DROP TRIGGER {name}')
            for table, (_, sealed, _) in sealing.TABLES.items():
                if not sealed or not sealing._has(db, table):
                    continue
                for row in db.execute(f'SELECT rowid AS _row,* FROM {table}').fetchall():
                    changed = {}
                    for column in sealed:
                        value = row[column]
                        parts = value.split(':') if isinstance(value, str) else []
                        if sealing.area_of(value) == area and int(parts[3]) != newest:
                            where = sealing.row_context(table, column, row)
                            changed[column] = sealer.seal(area, sealer.open(value, where), where)
                    if changed:
                        db.execute(f"UPDATE {table} SET {','.join(f'{c}=?' for c in changed)} WHERE rowid=?",
                                   (*changed.values(), row['_row']))
                        resealed += len(changed)
            for _, sql in triggers:
                db.execute(sql)
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
    return resealed


def reseal(database, sealer, area) -> dict:
    """After ``rotate_area``: seal the area's values again under its newest key, in the
    workspace, in its backups and, for the default area, in the sealed exports ALFRED wrote;
    compact them, and only then delete the older keys. Safe to run again until it finishes."""
    database = Path(database)
    _mark(database, RESEALING, area)
    resealed = _reseal_file(database, sealer, area)
    _compacted(database)
    backups = 0
    for path, identity in _backups(database).items():
        if _seal_file(path, sealer, sealing.DEFAULT_AREA, time.time) is not None:
            backups += 1
        backups += bool(_reseal_file(path, sealer, area))
        _compacted(path)
        for suffix in ('-wal', '-shm'):
            Path(str(path) + suffix).unlink(missing_ok=True)
        _backup_resealed(database, path, identity, sealer)
    exports = _reseal_exports(database, sealer) if area == sealing.DEFAULT_AREA else {}
    retired = sealer.keyring.retire_old_keys(area)
    sealer.clear_cache()
    marker(database, RESEALING).unlink()
    return {'area': area, 'values_resealed': resealed, 'backups_resealed': backups, **exports, **retired}


def _reseal_exports(database, sealer) -> dict:
    """Sealed exports are sealed under the default area (``alfred.export``). Seal again each
    one ALFRED wrote and still finds where it wrote it. One that has been changed, or cannot be
    written beside, is counted and left: once the older keys go it no longer opens, and nor
    does any copy kept somewhere else."""
    from .deletion import exports
    from .export import reseal_export
    counts = {'exports_resealed': 0, 'exports_not_resealed': 0}
    for directory in dict.fromkeys(e['directory'] for e in exports(database) if isinstance(e.get('directory'), str)):
        try:
            counts['exports_resealed'] += reseal_export(directory, sealer)
        except Fault:
            counts['exports_not_resealed'] += 1
    return counts
