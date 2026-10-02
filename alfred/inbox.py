"""Approved, create-only inbox notes in a selected vault (M04, MEM-011).

Writing is a separate capability from reading. It needs an explicit `inbox.write`
source grant (legacy scope policy never allows it), an exact proposed path and
content bound by the action fingerprint, the existing approval route and a
supervisor cycle that holds the vault. The destination is always under
`ALFRED/Inbox/`. A file is only ever created: an existing file with different
bytes fails the action and is left untouched. Nothing is sent anywhere.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from .local import Fault, canonical, exact, fingerprint, ident

CAPABILITY = 'vault.inbox_note'
FOLDER = ('ALFRED', 'Inbox')
NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}\.md')
MAX_CONTENT = 16000


def note_text(value):
    """Markdown body: printable text, newlines and tabs only, bounded, valid UTF-8."""
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_CONTENT or not value.strip():
        raise Fault('invalid_inbox_content')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise Fault('invalid_unicode') from None
    if any((ord(c) < 32 and c not in '\n\t') or 127 <= ord(c) < 160 for c in value):
        raise Fault('control_character')
    return value.replace('\r\n', '\n')


def destination(filename):
    if not isinstance(filename, str) or not NAME.fullmatch(filename) or '..' in filename:
        raise Fault('invalid_inbox_filename')
    from .sync_conflicts import conflict_copy
    if conflict_copy(filename):
        # The scanner would set such a file aside as a sync conflict copy, not index it.
        raise Fault('inbox_filename_looks_like_sync_conflict')
    return '/'.join(FOLDER + (filename,))


def _vault(db, scope, source):
    return db.execute('SELECT vault_id FROM knowledge_vaults WHERE scope=? AND source=?', (scope, source)).fetchone()


def current(store, db, row):
    """Every condition approval and dispatch depend on, rechecked in the caller's transaction."""
    from .policy import permitted
    params = json.loads(row['parameters'])
    actor = db.execute('SELECT * FROM credentials WHERE id=?', (row['actor'],)).fetchone()
    if not actor or actor['revoked'] or actor['expires'] <= store.now() or actor['role'] != 'owner' or actor['scope'] != row['scope']:
        return False
    device = db.execute('SELECT person FROM identity_devices WHERE credential=?', (row['actor'],)).fetchone()
    principal = {'id': row['actor'], 'scope': row['scope'], 'person_id': device['person'] if device else None}
    if not permitted(db, principal, params['source'], store.now(), 'inbox.write'):
        return False
    selected = _vault(db, row['scope'], params['source'])
    if not selected or selected['vault_id'] != params['vault_id']:
        return False
    # A note already indexed at the destination means someone else got there first.
    taken = db.execute("SELECT 1 FROM knowledge_notes WHERE scope=? AND source=? AND path=? AND status='ready'",
                       (row['scope'], params['source'], params['path'])).fetchone()
    return not taken or row['state'] in ('executing', 'uncertain', 'verified')


def propose(store, bearer, body):
    exact(body, {'request_id', 'source', 'filename', 'content'})
    ident(body['request_id']); ident(body['source'])
    path = destination(body['filename'])
    content = note_text(body['content'])
    content = content if content.endswith('\n') else content + '\n'
    digest = hashlib.sha256(content.encode()).hexdigest()
    from .policy import permitted
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner'})
        if not permitted(db, p, body['source'], store.now(), 'inbox.write'):
            raise Fault('inbox_write_not_granted', 403)
        selected = _vault(db, p['scope'], body['source'])
        if not selected:
            raise Fault('vault_not_selected', 409)
        params = {'source': body['source'], 'vault_id': selected['vault_id'], 'path': path, 'text': content, 'sha256': digest,
                  'precondition': 'create_only_destination_absent'}
        existing = db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (p['scope'], body['request_id'])).fetchone()
        if existing:
            if existing['actor'] != p['id'] or existing['capability'] != CAPABILITY or json.loads(existing['parameters']) != params:
                raise Fault('action_id_collision', 409)
            return store.action_view(existing)
        if db.execute("SELECT 1 FROM knowledge_notes WHERE scope=? AND source=? AND path=? AND status='ready'", (p['scope'], body['source'], path)).fetchone():
            raise Fault('inbox_destination_exists', 409)
        if db.execute('SELECT count(*) FROM actions WHERE scope=?', (p['scope'],)).fetchone()[0] >= 5000:
            raise Fault('action_capacity', 409)
        expiry = store.now() + 900
        bound = {'id': body['request_id'], 'scope': p['scope'], 'actor': p['id'], 'capability': CAPABILITY,
                 'parameters': params, 'expires_at': expiry}
        db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?)', (p['scope'], body['request_id'], p['id'], CAPABILITY,
                   canonical(params), fingerprint(bound), expiry, 'proposed', store.now(), None))
        store.log(db, p['scope'], p['id'], 'action.proposed_inbox_note', body['request_id'])
        return store.action_view(db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (p['scope'], body['request_id'])).fetchone())


def execute(store, row):
    """Create the file under the verified vault root. Returns the observed outcome."""
    params = json.loads(row['parameters'])
    writer = store.vault_writers.get(params['source'])
    if writer is None or writer.vault_id != params['vault_id']:
        return 'writer_unavailable'
    return writer.create_inbox_note(params['path'].split('/')[-1], params['text'].encode(), params['sha256'])


def verify(store, row):
    params = json.loads(row['parameters'])
    writer = store.vault_writers.get(params['source'])
    if writer is None:
        return None
    data = writer.read_inbox_note(params['path'].split('/')[-1])
    if data is None or hashlib.sha256(data).hexdigest() != params['sha256']:
        return None
    return {'type': 'vault_inbox_readback', 'path': params['path'], 'sha256': params['sha256'], 'sent': False}
