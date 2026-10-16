"""Forgetting, consistent backups and restore without resurrection (M05).

A forget or revocation is written first to an append-only journal beside the
database, then applied to the database. A restore copies a verified backup into
place only after replaying that whole journal into it, so a backup taken before a
forget or revocation cannot bring the forgotten value or the revoked access back.

Every forget receipt carries deletion accounting (alfred/deletion.py): each kind of
dependent found before the forget and still held after it, from the same scan the
deletion report uses. Value-free review history rows are kept unless the owner asks to
purge them; the choice is journalled, so a restore replays it. A restore reports, per
journal entry, what the backup still held and the replay removed again.

Not provided here: application-level encryption, key custody or secure erasure.
Forgetting removes values from current records and projections; SQLite free pages,
the WAL before a checkpoint, older backups and filesystem snapshots may still hold
earlier bytes until they are vacuumed, rotated or deleted. Receipts say so.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from .local import Fault

JOURNAL_SUFFIX = '.lifecycle.jsonl'
KINDS = {'claim_forgotten', 'entity_forgotten', 'credential_revoked', 'grant_revoked', 'source_forgotten'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS lifecycle_receipts(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, kind TEXT NOT NULL,
 subject TEXT NOT NULL, at INTEGER NOT NULL, receipt TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lifecycle_backups(
 id TEXT PRIMARY KEY, created INTEGER NOT NULL, file TEXT NOT NULL, sha256 TEXT NOT NULL,
 journal_entries INTEGER NOT NULL);
'''
REMAINS = ['Audit entries that name the record identifier and time, without its value.',
           'Lineage metadata: note identifier, line range and source hash, without the reviewed value.',
           'Backups taken before this time, until they are rotated; a restore replays this forget.',
           'Completed local drafts, which are not undone by forgetting.',
           'SQLite free pages and WAL contents until checkpoint and vacuum. This is not secure erasure.']


def journal_path(store) -> Path:
    return Path(store.path).with_name(Path(store.path).name + JOURNAL_SUFFIX)


def initialise(db):
    db.executescript(SCHEMA)


def append(store, entry: dict) -> None:
    """Durably record intent before the database changes. Fails closed."""
    if entry.get('kind') not in KINDS:
        raise Fault('invalid_lifecycle_entry')
    path = journal_path(store)
    line = (json.dumps(entry, sort_keys=True, separators=(',', ':')) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)


def entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    if path.is_symlink():
        raise Fault('lifecycle_journal_symlink')
    result = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            # A torn final write is the only tolerable damage; anything else stops restore.
            if number == len(path.read_text().splitlines()):
                break
            raise Fault('lifecycle_journal_corrupt') from None
        if value.get('kind') not in KINDS:
            raise Fault('lifecycle_journal_corrupt')
        result.append(value)
    return result


def _has(db, table):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def withdraw_dependants(db, scope, actor, claim_ids, now):
    """Clear saved answers and cancel undecided actions bound to forgotten claims."""
    answers, cancelled, completed = 0, [], []
    # Conversations belong to a device credential; the ledger to its person. Cover both.
    from .policy import ledger_keys
    keys = ledger_keys(db, actor) if _has(db, 'identity_devices') else [actor]
    if _has(db, 'conversation_turns'):
        for row in db.execute(f'''SELECT t.id,t.result FROM conversation_turns t JOIN conversations s ON s.id=t.session
                                 WHERE s.scope=? AND s.actor IN ({','.join('?' * len(keys))}) AND t.result IS NOT NULL''',
                              (scope, *keys)).fetchall():
            bound = {m.get('claim_id') for m in json.loads(row['result'])['packet'].get('memory', [])}
            if bound & set(claim_ids):
                db.execute("UPDATE conversation_turns SET state='memory_forgotten',result=NULL WHERE id=?", (row['id'],))
                answers += 1
    if _has(db, 'conversation_action_sources'):
        for link in db.execute('SELECT action_id,references_json FROM conversation_action_sources WHERE scope=?', (scope,)).fetchall():
            binding = json.loads(link['references_json'])
            memory = binding.get('memory', []) if isinstance(binding, dict) else []
            if not {m.get('claim_id') for m in memory} & set(claim_ids):
                continue
            action = db.execute('SELECT state FROM actions WHERE scope=? AND id=?', (scope, link['action_id'])).fetchone()
            if action and action['state'] in ('proposed', 'queued'):
                db.execute("UPDATE actions SET state='cancelled' WHERE scope=? AND id=?", (scope, link['action_id']))
                db.execute("UPDATE outbox SET state='cancelled' WHERE scope=? AND action_id=?", (scope, link['action_id']))
                cancelled.append(link['action_id'])
            elif action:
                completed.append(link['action_id'])
    # Drafts kept after their conversation ended, or re-proposed, are withdrawn too.
    from .drafts import bound_to_claims, withdraw
    bound = bound_to_claims(db, scope, claim_ids) if _has(db, 'actions') else set()
    for action_id in sorted(bound - set(cancelled) - set(completed)):
        action = db.execute('SELECT state FROM actions WHERE scope=? AND id=?', (scope, action_id)).fetchone()
        if action and action['state'] in ('proposed', 'queued'):
            cancelled.append(action_id)
        elif action and action['state'] in ('executing', 'uncertain', 'verified'):
            completed.append(action_id)
    withdrawn = withdraw(db, scope, bound | set(cancelled), 'memory_forgotten', now)
    return {'conversation_answers_withdrawn': answers, 'pending_actions_cancelled': cancelled,
            'completed_actions_not_undone': completed, 'drafts_withdrawn': withdrawn}


REMOVED = 'Removed when its source was forgotten.'
SOURCE_REMAINS = ['Your own files. ALFRED never deletes or edits the files a source read; remove them yourself if you want them gone.',
                  'Audit entries and job records that name identifiers, revisions and hashes, without content.',
                  'Reviewed statements that relied on this source, invalidated with their values removed, until you forget them.',
                  'Backups taken before this time, until they are rotated; a restore replays this removal.',
                  'Completed local drafts, which are not undone.',
                  'SQLite free pages and WAL contents until checkpoint and vacuum. This is not secure erasure.']


def _cancel(db, scope, action_ids, counts):
    for action_id in sorted(action_ids):
        action = db.execute('SELECT state FROM actions WHERE scope=? AND id=?', (scope, action_id)).fetchone()
        if action and action['state'] in ('proposed', 'queued'):
            db.execute("UPDATE actions SET state='cancelled' WHERE scope=? AND id=?", (scope, action_id))
            db.execute("UPDATE outbox SET state='cancelled' WHERE scope=? AND action_id=?", (scope, action_id))
            counts['pending_actions_cancelled'].append(action_id)
        elif action and action['state'] != 'cancelled':
            counts['completed_actions_not_undone'].append(action_id)


def forget_source_db(db, scope, source, now, *, origin='recorded', at=None, purge_history=False):
    """Remove one source's content and everything derived from it. Idempotent, so a
    restore can replay it. The person's own files are never read, edited or deleted.

    Value-free review history rows of the statements that cited the source are kept
    unless `purge_history` is set (decision 0.3)."""
    counts = {'notes_removed': 0, 'reviewed_statements_invalidated': 0, 'conversation_answers_withdrawn': 0,
              'pending_actions_cancelled': [], 'completed_actions_not_undone': [], 'job_results_deleted': [],
              'evidence_events_redacted': 0, 'connector_records_removed': 0, 'history_rows_purged': 0,
              'drafts_withdrawn': []}
    # Revoked first, so nothing can index or report under this source again.
    db.execute("UPDATE credentials SET revoked=1 WHERE id=? AND scope=? AND role='source'", (source, scope))
    notes = set()
    if _has(db, 'knowledge_notes'):
        current = db.execute('SELECT id,path FROM knowledge_notes WHERE scope=? AND source=?', (scope, source)).fetchall()
        notes = {r['id'] for r in current}
        if _has(db, 'knowledge_history'):
            notes |= {r[0] for r in db.execute('SELECT DISTINCT id FROM knowledge_history WHERE scope=? AND source=?', (scope, source))}
        if _has(db, 'memory_tombstones'):
            for row in current:
                # The tombstone keeps a hash of the path, not the name.
                db.execute('INSERT OR IGNORE INTO memory_tombstones VALUES (?,?,?,?,?,?)',
                           (scope, source, row['id'], 'sha256:' + hashlib.sha256(row['path'].encode()).hexdigest(), now, 'source_forgotten'))
        counts['notes_removed'] = len(current)
        for table in ('knowledge_notes', 'knowledge_refs', 'knowledge_identity', 'knowledge_history',
                      'knowledge_anchors', 'knowledge_vaults', 'knowledge_sources'):
            if _has(db, table):
                db.execute(f'DELETE FROM {table} WHERE scope=? AND source=?', (scope, source))
    for table in ('knowledge_conflicts', 'connector_instances', 'connector_item_revisions', 'connector_receipts'):
        # Conflict copies name paths; connector rows name labels, files and items of this source.
        if _has(db, table):
            removed = db.execute(f'DELETE FROM {table} WHERE scope=? AND source=?', (scope, source)).rowcount
            if table.startswith('connector_'):
                counts['connector_records_removed'] += removed
    if notes and _has(db, 'memory_claims'):
        claims = [(r[0], r[2]) for r in db.execute("SELECT id,note_id,actor FROM memory_claims WHERE scope=? AND state NOT IN ('invalidated','forgotten')", (scope,))
                  if r[1] in notes]
        from .memory_history import SYSTEM, record_if_present
        for identity, owner in claims:
            db.execute("UPDATE memory_claims SET state='invalidated',value=NULL,object_id=NULL,version=version+1 WHERE id=?", (identity,))
            record_if_present(db, scope, owner, identity, 'invalidated', at if at is not None else now, SYSTEM,
                              origin=origin, detail='source_removed')
        counts['reviewed_statements_invalidated'] = len(claims)
    if purge_history and notes and _has(db, 'memory_claims') and _has(db, 'memory_claim_history'):
        cited = [r[0] for r in db.execute('SELECT id,note_id FROM memory_claims WHERE scope=?', (scope,)) if r[1] in notes]
        for identity in cited:
            counts['history_rows_purged'] += db.execute('DELETE FROM memory_claim_history WHERE scope=? AND claim_id=?',
                                                        (scope, identity)).rowcount
    if notes and _has(db, 'conversation_turns'):
        for row in db.execute('''SELECT t.id,t.result FROM conversation_turns t JOIN conversations s ON s.id=t.session
                                 WHERE s.scope=? AND t.result IS NOT NULL''', (scope,)).fetchall():
            packet = json.loads(row['result']).get('packet', {})
            cited = {e.get('note_id') for e in packet.get('evidence', [])}
            cited |= {(m.get('support') or {}).get('note_id') for m in packet.get('memory', [])}
            focus = (packet.get('focus') or {}).get('record_id') or ''
            if cited & notes or focus.removeprefix('note:') in notes:
                db.execute("UPDATE conversation_turns SET state='source_forgotten',result=NULL WHERE id=?", (row['id'],))
                counts['conversation_answers_withdrawn'] += 1
    bound = set()
    if notes and _has(db, 'conversation_action_sources'):
        for link in db.execute('SELECT action_id,references_json FROM conversation_action_sources WHERE scope=?', (scope,)).fetchall():
            binding = json.loads(link['references_json'])
            refs = binding if isinstance(binding, list) else binding.get('sources', [])
            if {r.get('note_id') for r in refs if isinstance(r, dict)} & notes:
                bound.add(link['action_id'])
    if notes:
        # Includes drafts whose conversation has ended and drafts re-proposed from them.
        from .drafts import bound_to_notes
        bound |= bound_to_notes(db, scope, notes)
    if _has(db, 'events'):
        seqs = [r[0] for r in db.execute('SELECT seq FROM events WHERE scope=? AND source=?', (scope, source))]
        for seq in seqs:
            row = db.execute('SELECT body FROM events WHERE seq=?', (seq,)).fetchone()
            try:
                value = json.loads(row['body'])
            except ValueError:
                value = {}
            if not isinstance(value, dict) or value.get('summary') != REMOVED:
                value = (value if isinstance(value, dict) else {}) | {'summary': REMOVED}
                db.execute('UPDATE events SET body=? WHERE seq=?', (json.dumps(value, sort_keys=True, separators=(',', ':')), seq))
                counts['evidence_events_redacted'] += 1
        if seqs and _has(db, 'desk_action_evidence'):
            removed = set(seqs)
            bound |= {r[0] for r in db.execute('SELECT action_id,event_seq FROM desk_action_evidence WHERE scope=?', (scope,))
                      if r[1] in removed}
        if _has(db, 'desk_documents'):
            db.execute('UPDATE desk_documents SET title=? WHERE scope=? AND source=?', (REMOVED, scope, source))
        if _has(db, 'desk_links'):
            for seq in seqs:
                db.execute('UPDATE desk_links SET title=? WHERE seq=?', (REMOVED, seq))
    if _has(db, 'actions'):
        for row in db.execute("SELECT id,parameters FROM actions WHERE scope=? AND capability IN ('vault.inbox_note','vault.append_section')", (scope,)).fetchall():
            if json.loads(row['parameters']).get('source') == source:
                bound.add(row['id'])
        _cancel(db, scope, bound, counts)
        # Archived or lapsed copies are not a way around forgetting: their text goes too.
        from .drafts import withdraw
        counts['drafts_withdrawn'] = withdraw(db, scope, bound, 'source_forgotten', now)
    if _has(db, 'artefacts'):
        for row in db.execute('SELECT sha256,lineage FROM artefacts WHERE scope=?', (scope,)).fetchall():
            if source in json.loads(row['lineage']).get('sources', []):
                db.execute('DELETE FROM artefacts WHERE scope=? AND sha256=?', (scope, row['sha256']))
                counts['job_results_deleted'].append(row['sha256'])
    return counts


def forget_source(store, bearer, source, *, cache=None, purge_history=False):
    """An owner removes a whole source from ALFRED, journalled first, with a receipt."""
    from .local import ident
    ident(source)
    if type(purge_history) is not bool:
        raise Fault('invalid_fields')
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner'})
        row = db.execute("SELECT revoked FROM credentials WHERE id=? AND scope=? AND role='source'", (source, p['scope'])).fetchone()
        if not row:
            raise Fault('source_not_available', 404)
    entry = {'kind': 'source_forgotten', 'scope': p['scope'], 'subject': source, 'actor': p['id'], 'at': store.now()}
    if purge_history:
        entry['purge_history'] = True
    append(store, entry)
    cache_dir = getattr(cache, 'root', None)
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner'})
        full = forget_accounted(store, db, p, entry, {}, SOURCE_REMAINS, cache_dir=cache_dir)
    dropped = 0
    for sha256 in full['job_results_deleted']:
        # The job cache is an accelerator; its copies of removed results go too.
        try:
            dropped += bool(cache is not None and cache.discard(sha256))
        except (Fault, OSError):
            pass
    full['cached_results_removed'] = dropped
    if cache_dir is not None and full['trace']['artefacts']:
        # The copies go after the database commits, so their count is settled only now.
        left = _cached(cache_dir, full['trace']['artefacts'])
        full['accounting']['cache_copies']['after'] = {'count': left, 'holding_value': left}
        for key in ('still_held', 'still_holding_value'):
            full[key] = {k: v for k, v in full[key].items() if k != 'cache_copies'} | ({'cache_copies': left} if left else {})
    with store.transaction() as db:
        db.execute('UPDATE lifecycle_receipts SET receipt=? WHERE id=?', (json.dumps(full), full['id']))
    return full


def _cached(cache_dir, digests):
    root = Path(cache_dir) / 'objects'
    return sum((root / d[:2] / d).is_file() for d in digests if isinstance(d, str) and len(d) == 64)


ACCOUNTED = {'claim_forgotten': 'statement', 'entity_forgotten': 'entity', 'source_forgotten': 'source'}


def forget_accounted(store, db, p, entry, receipt, remains, *, cache_dir=None):
    """Apply one journalled forget in the caller's transaction and record a receipt that counts
    every dependent before and after, with the same scan the deletion report uses."""
    from .deletion import accounting, scan, traces
    kind = ACCOUNTED[entry['kind']]
    scope, subject, now = p['scope'], entry['subject'], store.now()
    earlier, _ = traces(db, scope, p['id'], kind, subject)
    places = {'cache_dir': cache_dir, 'database': store.path, 'forgotten_at': now}
    before = scan(db, scope, p['id'], kind, subject, trace=earlier, **places)
    effect = apply_entry(db, entry, now)
    full = record(store, db, p, entry['kind'], subject, {**receipt, **effect}, remains)
    # The receipt and its audit entry exist now, so the second scan counts them as the report will.
    after = scan(db, scope, p['id'], kind, subject, trace=before['trace'], **places)
    full |= accounting(before, after, purge=bool(entry.get('purge_history')))
    db.execute('UPDATE lifecycle_receipts SET receipt=? WHERE id=?', (json.dumps(full), full['id']))
    return full


def apply_entry(db, entry, now, origin='recorded'):
    """Idempotently apply one journal entry to a database (live or restored).

    History rows for a replay carry the time the journal recorded, never a value."""
    kind, scope = entry['kind'], entry['scope']
    at = entry.get('at', now) if origin == 'replayed' else now
    purge = bool(entry.get('purge_history'))
    if kind == 'source_forgotten':
        return forget_source_db(db, scope, entry['subject'], now, origin=origin, at=at, purge_history=purge)
    if kind == 'credential_revoked':
        changed = db.execute('UPDATE credentials SET revoked=1 WHERE id=? AND revoked=0', (entry['subject'],)).rowcount
        return {'credentials_revoked': changed}
    if kind == 'grant_revoked':
        removed = 0
        if _has(db, 'source_grants'):
            removed = db.execute('DELETE FROM source_grants WHERE scope=? AND person=? AND source=? AND capability=?',
                                 (scope, entry['person'], entry['subject'], entry['capability'])).rowcount
        return {'grants_removed': removed}
    if not _has(db, 'memory_claims'):
        return {}
    actor = entry['actor']
    # The ledger is per person. An entry may name the person or (written before ledgers were
    # per person, or replayed into an older backup) a device credential of that person.
    from .policy import ledger_keys
    keys = ledger_keys(db, actor) if _has(db, 'identity_devices') else [actor]
    within = f"actor IN ({','.join('?' * len(keys))})"
    entities = 0
    if kind == 'entity_forgotten':
        ids = [r[0] for r in db.execute(f'SELECT id FROM memory_claims WHERE scope=? AND {within} AND (subject_id=? OR object_id=?)',
                                         (scope, *keys, entry['subject'], entry['subject']))]
        entities = db.execute(f'DELETE FROM memory_entities WHERE id=? AND scope=? AND {within}', (entry['subject'], scope, *keys)).rowcount
    else:
        ids = [entry['subject']]
    from .memory_history import record_if_present
    forgotten = purged = 0
    for identity in ids:
        row = db.execute(f"SELECT actor FROM memory_claims WHERE id=? AND scope=? AND {within} AND state!='forgotten'",
                         (identity, scope, *keys)).fetchone()
        if row:
            db.execute("UPDATE memory_claims SET state='forgotten',value=NULL,object_id=NULL,version=version+1 WHERE id=?", (identity,))
            forgotten += 1
            record_if_present(db, scope, row['actor'], identity, 'forgotten', at, entry.get('by', actor), origin=origin, detail=kind)
    if purge and _has(db, 'memory_claim_history'):
        # Only on explicit request: by default these value-free rows are kept (decision 0.3).
        for identity in ids:
            purged += db.execute(f'DELETE FROM memory_claim_history WHERE scope=? AND {within} AND claim_id=?',
                                 (scope, *keys, identity)).rowcount
    effect = withdraw_dependants(db, scope, actor, ids, now)
    return {'statements_forgotten': forgotten, **({'entities_removed': entities} if kind == 'entity_forgotten' else {}),
            **effect, 'history_rows_purged': purged}


def record(store, db, p, kind, subject, receipt, remains=REMAINS):
    from .policy import ledger
    rid = 'receipt-' + secrets.token_hex(12)
    full = {'id': rid, 'kind': kind, 'subject': subject, 'at': store.now(), **receipt,
            'remains': remains, 'secure_erasure': False}
    db.execute('INSERT INTO lifecycle_receipts VALUES (?,?,?,?,?,?,?)',
               (rid, p['scope'], ledger(db, p), kind, subject, store.now(), json.dumps(full)))
    store.log(db, p['scope'], p['id'], 'lifecycle.' + kind, subject)
    return full


def receipts(store, bearer):
    from .policy import ledger
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner', 'reader'})
        return {'receipts': [json.loads(r['receipt']) for r in db.execute(
            'SELECT receipt FROM lifecycle_receipts WHERE scope=? AND actor=? ORDER BY at DESC,id LIMIT 100', (p['scope'], ledger(db, p)))]}


def backup(store, bearer, directory) -> dict:
    """Consistent online copy via SQLite's backup API, with a manifest and hash."""
    with store.transaction() as db:
        store.authenticate(db, bearer, {'owner'})
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise Fault('backup_directory_symlink')
    identity = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(store.now())) + '-' + secrets.token_hex(4)
    target = directory / f'alfred-{identity}.sqlite'
    source = sqlite3.connect(store.path)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    target.chmod(0o600)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    count = len(entries(journal_path(store)))
    manifest = {'id': identity, 'file': target.name, 'sha256': digest, 'created': store.now(),
                'journal_entries': count, 'encrypted': False,
                'note': 'Plain SQLite copy. Protect it as private data; application encryption is not implemented.'}
    manifest_path = target.with_suffix('.json')
    manifest_path.write_text(json.dumps(manifest, indent=1) + '\n')
    manifest_path.chmod(0o600)
    with store.transaction() as db:
        db.execute('INSERT INTO lifecycle_backups VALUES (?,?,?,?,?)', (identity, store.now(), str(target), digest, count))
    return manifest


def restore(backup_file, database, now=None, *, cache=None) -> dict:
    """Offline restore. The caller must have stopped ALFRED (the desk lock enforces this).

    The result says what the journal removed again: per replayed entry, what the backup
    still held and the replay removed, with totals. `cache` is the job cache, whose copies
    of results deleted again are discarded."""
    backup_file, database = Path(backup_file), Path(database)
    manifest_path = backup_file.with_suffix('.json')
    if backup_file.is_symlink() or not backup_file.is_file() or not manifest_path.is_file():
        raise Fault('backup_not_found', 404)
    manifest = json.loads(manifest_path.read_text())
    if hashlib.sha256(backup_file.read_bytes()).hexdigest() != manifest.get('sha256'):
        raise Fault('backup_hash_mismatch', 409)
    journal = entries(database.with_name(database.name + JOURNAL_SUFFIX))
    staging = database.with_name(database.name + '.restoring')
    staging.unlink(missing_ok=True)
    staging.write_bytes(backup_file.read_bytes())
    staging.chmod(0o600)
    db = sqlite3.connect(staging, isolation_level=None)
    db.row_factory = sqlite3.Row
    moment = int(now if now is not None else time.time())
    cache_dir = getattr(cache, 'root', None)
    removed_again, totals, deleted = [], {}, []
    try:
        db.execute('BEGIN IMMEDIATE')
        withdrawn = {'conversation_answers_withdrawn': 0, 'pending_actions_cancelled': []}
        for entry in journal:
            effect, accounted = _replay(db, entry, moment, cache_dir, database)
            withdrawn['conversation_answers_withdrawn'] += effect.get('conversation_answers_withdrawn', 0)
            withdrawn['pending_actions_cancelled'] += effect.get('pending_actions_cancelled', [])
            deleted += effect.get('job_results_deleted', [])
            changed = {k: len(v) if isinstance(v, list) else v for k, v in effect.items()
                       if k in REMOVAL_COUNTS and (len(v) if isinstance(v, list) else v)}
            for k, v in changed.items():
                totals[k] = totals.get(k, 0) + v
            if changed:
                # What this backup still held that the journal had removed, and removed again now.
                removed_again.append({'kind': entry['kind'], 'subject': entry.get('subject'), 'at': entry.get('at'),
                                      'removed': changed} | ({'still_held': accounted['still_held']} if accounted else {}))
        _register_backups(db, backup_file.parent)
        db.execute('COMMIT')
        integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
    except Exception:
        db.close(); staging.unlink(missing_ok=True)
        raise
    db.close()
    if integrity != 'ok':
        staging.unlink(missing_ok=True)
        raise Fault('restored_database_failed_integrity_check', 409)
    for suffix in ('-wal', '-shm'):
        database.with_name(database.name + suffix).unlink(missing_ok=True)
    os.replace(staging, database)
    dropped = 0
    for sha256 in sorted(set(deleted)):
        # A result the backup brought back and the replay deleted again leaves the cache too.
        try:
            dropped += bool(cache is not None and cache.discard(sha256))
        except (Fault, OSError):
            pass
    return {'restored_from': manifest['id'], 'journal_entries_replayed': len(journal),
            'entries_after_backup': max(0, len(journal) - manifest.get('journal_entries', 0)),
            **withdrawn, 'removed_again': {'entries': removed_again, 'totals': totals,
                                           'cached_results_removed': dropped},
            'integrity_check': integrity, 'encrypted': False}


def _register_backups(db, directory):
    """A backup never lists itself, so the restored copy is told about the verified backups
    beside the one restored; the deletion report can then name them as still holding data."""
    if not _has(db, 'lifecycle_backups'):
        return
    for manifest_path in sorted(Path(directory).glob('alfred-*.json')):
        try:
            manifest = json.loads(manifest_path.read_text())
            target = manifest_path.with_suffix('.sqlite')
            if manifest_path.is_symlink() or target.is_symlink() or not target.is_file() or target.name != manifest.get('file'):
                continue
            db.execute('INSERT OR IGNORE INTO lifecycle_backups VALUES (?,?,?,?,?)',
                       (str(manifest['id']), int(manifest['created']), str(target), str(manifest['sha256']),
                        int(manifest.get('journal_entries', 0))))
        except (OSError, ValueError, KeyError, TypeError):
            continue


REMOVAL_COUNTS = ('statements_forgotten', 'entities_removed', 'notes_removed', 'reviewed_statements_invalidated',
                  'conversation_answers_withdrawn', 'pending_actions_cancelled', 'job_results_deleted',
                  'evidence_events_redacted', 'connector_records_removed', 'history_rows_purged',
                  'credentials_revoked', 'grants_removed')


def _replay(db, entry, now, cache_dir, database):
    """Apply one journal entry to a restored copy. A forget is accounted as on the live
    database, and gets a replayed receipt if the backup predates the original one."""
    if entry['kind'] not in ACCOUNTED or not entry.get('actor'):
        return apply_entry(db, entry, now, origin='replayed'), None
    from .deletion import accounting, scan, traces
    kind, scope, actor, subject = ACCOUNTED[entry['kind']], entry['scope'], entry['actor'], entry['subject']
    earlier, _ = traces(db, scope, actor, kind, subject)
    places = {'cache_dir': cache_dir, 'database': database, 'forgotten_at': entry.get('at', now)}
    before = scan(db, scope, actor, kind, subject, trace=earlier, **places)
    effect = apply_entry(db, entry, now, origin='replayed')
    after = scan(db, scope, actor, kind, subject, trace=before['trace'], **places)
    accounted = accounting(before, after, purge=bool(entry.get('purge_history')))
    if _has(db, 'lifecycle_receipts') and not db.execute(
            'SELECT 1 FROM lifecycle_receipts WHERE scope=? AND actor=? AND kind=? AND subject=?',
            (scope, actor, entry['kind'], subject)).fetchone():
        rid = 'receipt-' + secrets.token_hex(12)
        at = int(entry.get('at', now))
        full = {'id': rid, 'kind': entry['kind'], 'subject': subject, 'at': at, 'origin': 'replayed_on_restore',
                **effect, **accounted, 'remains': SOURCE_REMAINS if kind == 'source' else REMAINS, 'secure_erasure': False}
        db.execute('INSERT INTO lifecycle_receipts VALUES (?,?,?,?,?,?,?)',
                   (rid, scope, actor, entry['kind'], subject, at, json.dumps(full)))
    return effect, accounted
