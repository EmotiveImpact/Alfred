"""Forgetting, consistent backups and restore without resurrection (M05).

A forget or revocation is written first to an append-only journal beside the
database, then applied to the database. A restore copies a verified backup into
place only after replaying that whole journal into it, so a backup taken before a
forget or revocation cannot bring the forgotten value or the revoked access back.

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
KINDS = {'claim_forgotten', 'entity_forgotten', 'credential_revoked', 'grant_revoked'}
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
    if _has(db, 'conversation_turns'):
        for row in db.execute('''SELECT t.id,t.result FROM conversation_turns t JOIN conversations s ON s.id=t.session
                                 WHERE s.scope=? AND s.actor=? AND t.result IS NOT NULL''', (scope, actor)).fetchall():
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
    return {'conversation_answers_withdrawn': answers, 'pending_actions_cancelled': cancelled,
            'completed_actions_not_undone': completed}


def apply_entry(db, entry, now):
    """Idempotently apply one journal entry to a database (live or restored)."""
    kind, scope = entry['kind'], entry['scope']
    if kind == 'credential_revoked':
        db.execute('UPDATE credentials SET revoked=1 WHERE id=?', (entry['subject'],))
        return {}
    if kind == 'grant_revoked':
        if _has(db, 'source_grants'):
            db.execute('DELETE FROM source_grants WHERE scope=? AND person=? AND source=? AND capability=?',
                       (scope, entry['person'], entry['subject'], entry['capability']))
        return {}
    if not _has(db, 'memory_claims'):
        return {}
    actor = entry['actor']
    if kind == 'entity_forgotten':
        ids = [r[0] for r in db.execute('SELECT id FROM memory_claims WHERE scope=? AND actor=? AND (subject_id=? OR object_id=?)',
                                         (scope, actor, entry['subject'], entry['subject']))]
        db.execute('DELETE FROM memory_entities WHERE id=? AND scope=? AND actor=?', (entry['subject'], scope, actor))
    else:
        ids = [entry['subject']]
    for identity in ids:
        db.execute("UPDATE memory_claims SET state='forgotten',value=NULL,object_id=NULL,version=version+1 WHERE id=? AND scope=? AND actor=? AND state!='forgotten'",
                   (identity, scope, actor))
    return withdraw_dependants(db, scope, actor, ids, now)


def record(store, db, p, kind, subject, receipt):
    rid = 'receipt-' + secrets.token_hex(12)
    full = {'id': rid, 'kind': kind, 'subject': subject, 'at': store.now(), **receipt,
            'remains': REMAINS, 'secure_erasure': False}
    db.execute('INSERT INTO lifecycle_receipts VALUES (?,?,?,?,?,?,?)',
               (rid, p['scope'], p['id'], kind, subject, store.now(), json.dumps(full)))
    store.log(db, p['scope'], p['id'], 'lifecycle.' + kind, subject)
    return full


def receipts(store, bearer):
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner', 'reader'})
        return {'receipts': [json.loads(r['receipt']) for r in db.execute(
            'SELECT receipt FROM lifecycle_receipts WHERE scope=? AND actor=? ORDER BY at DESC,id LIMIT 100', (p['scope'], p['id']))]}


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


def restore(backup_file, database, now=None) -> dict:
    """Offline restore. The caller must have stopped ALFRED (the desk lock enforces this)."""
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
    try:
        db.execute('BEGIN IMMEDIATE')
        withdrawn = {'conversation_answers_withdrawn': 0, 'pending_actions_cancelled': []}
        for entry in journal:
            effect = apply_entry(db, entry, now or time.time())
            withdrawn['conversation_answers_withdrawn'] += effect.get('conversation_answers_withdrawn', 0)
            withdrawn['pending_actions_cancelled'] += effect.get('pending_actions_cancelled', [])
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
    return {'restored_from': manifest['id'], 'journal_entries_replayed': len(journal),
            'entries_after_backup': max(0, len(journal) - manifest.get('journal_entries', 0)),
            **withdrawn, 'integrity_check': integrity, 'encrypted': False}
