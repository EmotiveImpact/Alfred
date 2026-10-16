"""Approved appends under a named heading of an existing note (M04, MEM-002).

The second vault write capability, after create-only inbox notes. It needs an
explicit `vault.append` source grant (legacy scope policy never allows it, and it
cannot be invited), the exact note, base content hash, heading and text bound by
the action fingerprint, the existing approval route and a supervisor cycle that
holds the vault.

The change is always a pure insertion: the written file equals the base bytes
with one block inserted at one byte offset, so existing human text is never
rewritten, moved or removed. The proposal carries a unified diff for the person
to approve. At dispatch the file must still hash to the approved base; anything
else is refused and left untouched. A file that already hashes to the approved
result is recognised as the same append, so a retry never appends twice. The
result is read back and its hash compared before the action is verified.
Nothing is sent anywhere.
"""
from __future__ import annotations
import difflib
import hashlib
import json
import re
from .local import Fault, canonical, exact, fingerprint, ident

CAPABILITY = 'vault.append_section'
GRANT = 'vault.append'
EFFECT = 'vault_note_append_insert_only_not_sent'
SUCCESS = ('appended', 'exists_same')
RECEIPT = 'connector.append_receipt'
REFUSED = ('vault_append_refused', 'action.append_refused')
VERIFIED = 'action.verified_vault_append'
MAX_TEXT = 4000
HEADING = re.compile(r'[^\n`*\[\]<>#]{1,160}')


def append_text(value):
    """The appended block: printable text, newlines and tabs, bounded, no new structure."""
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_TEXT or not value.strip():
        raise Fault('invalid_append_text')
    if any((ord(c) < 32 and c not in '\n\t') or 127 <= ord(c) < 160 or c in '  ' for c in value):
        raise Fault('control_character')
    lines = value.replace('\r\n', '\n').strip('\n').split('\n')
    for line in lines:
        # A heading or setext underline would change the note's sections.
        if re.match(r'\s{0,3}#{1,6}(\s|$)', line) or re.fullmatch(r'\s{0,3}(=+|-+)\s*', line):
            raise Fault('append_text_changes_structure')
    return lines


def _lines(text):
    if ' ' in text or ' ' in text or re.search(r'\r(?!\n)', text):
        raise Fault('unsupported_line_endings', 409)
    return text.splitlines(keepends=True)


def plan(path, raw, heading, text):
    """Compute the insertion. Pure: no filesystem access.

    Returns (offset, inserted bytes, result bytes, diff). Refuses when the note
    cannot be changed by insertion alone without altering its structure.
    """
    from .knowledge import parse_note, MAX_BYTES
    try:
        decoded = raw.decode('utf-8')
    except UnicodeError:
        raise Fault('note_not_utf8', 409) from None
    before = parse_note(path, raw)
    lines = _lines(decoded)
    matches = [a for a in before['anchors'] if a['kind'] == 'heading' and a['name'].casefold() == heading.casefold()]
    if len(matches) != 1:
        raise Fault('append_heading_ambiguous' if matches else 'append_heading_missing', 409)
    target = matches[0]
    block = append_text(text)
    # The block must stand alone: balanced fences and comments, no existing block IDs.
    probe = parse_note('append.md', ('\n'.join(block) + '\n').encode('utf-8'))
    existing = {a['name'] for a in before['anchors'] if a['kind'] == 'block'}
    if any(a['kind'] == 'heading' for a in probe['anchors']):
        raise Fault('append_text_changes_structure')
    if any(a['kind'] == 'block' and a['name'] in existing for a in probe['anchors']):
        raise Fault('append_block_id_exists', 409)
    eol = '\r\n' if '\r\n' in decoded else '\n'
    last = max(n for n in range(target['start_line'], target['end_line'] + 1) if lines[n - 1].strip())
    inserted = ''
    if not lines[last - 1].endswith('\n'):
        inserted += eol  # the note ends without a newline; this adds one, it changes no text
    if last > target['start_line']:
        inserted += eol  # a blank line keeps the new paragraph separate from the one above
    inserted += eol.join(block) + eol
    if last < len(lines) and lines[last].strip():
        inserted += eol
    offset = len(''.join(lines[:last]).encode('utf-8'))
    data = inserted.encode('utf-8')
    result = raw[:offset] + data + raw[offset:]
    if len(result) > MAX_BYTES:
        raise Fault('note_too_large', 409)
    after = parse_note(path, result)
    shape = lambda p: [(a['kind'], a['name'], a.get('level')) for a in p['anchors'] if a['kind'] == 'heading']
    if shape(after) != shape(before) or not existing <= {a['name'] for a in after['anchors'] if a['kind'] == 'block'}:
        raise Fault('append_text_changes_structure')
    diff = '\n'.join(difflib.unified_diff(decoded.splitlines(), result.decode('utf-8').splitlines(),
                                          'a/' + path, 'b/' + path, n=3, lineterm=''))
    return offset, data, result, diff


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
    if not permitted(db, principal, params['source'], store.now(), GRANT):
        return False
    selected = _vault(db, row['scope'], params['source'])
    if not selected or selected['vault_id'] != params['vault_id']:
        return False
    note = db.execute("SELECT path,sha256 FROM knowledge_notes WHERE scope=? AND source=? AND id=? AND status='ready'",
                      (row['scope'], params['source'], params['note_id'])).fetchone()
    if not note or note['path'] != params['path']:
        return False
    # Before dispatch the indexed note must still be the approved base. Once the
    # effect may have happened, the index may show either the base or the result.
    allowed = {params['base_sha256']}
    if row['state'] in ('executing', 'uncertain', 'verified'):
        allowed.add(params['result_sha256'])
    return note['sha256'] in allowed


def propose(store, bearer, body):
    exact(body, {'request_id', 'source', 'note_id', 'base_sha256', 'heading', 'text'})
    ident(body['request_id']); ident(body['source'])
    if not isinstance(body['note_id'], str) or not re.fullmatch(r'[0-9a-f]{24}', body['note_id']):
        raise Fault('invalid_note_id')
    if not isinstance(body['base_sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', body['base_sha256']):
        raise Fault('invalid_base_sha256')
    if not isinstance(body['heading'], str) or not HEADING.fullmatch(body['heading'].strip()):
        raise Fault('invalid_append_heading')
    heading = body['heading'].strip()
    append_text(body['text'])
    request = {'note_id': body['note_id'], 'base_sha256': body['base_sha256'], 'heading': heading, 'text': body['text']}
    from .policy import permitted
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner'})
        if not permitted(db, p, body['source'], store.now(), GRANT):
            raise Fault('vault_append_not_granted', 403)
        existing = db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (p['scope'], body['request_id'])).fetchone()
        if existing:
            # The same request returns the same action, whatever has happened to the note since.
            params = json.loads(existing['parameters'])
            if (existing['actor'] != p['id'] or existing['capability'] != CAPABILITY or params.get('source') != body['source']
                    or {k: params.get(k) for k in request} != request):
                raise Fault('action_id_collision', 409)
            return store.action_view(existing)
        selected = _vault(db, p['scope'], body['source'])
        if not selected:
            raise Fault('vault_not_selected', 409)
        note = db.execute("SELECT path,sha256,revision FROM knowledge_notes WHERE scope=? AND source=? AND id=? AND status='ready'",
                          (p['scope'], body['source'], body['note_id'])).fetchone()
        if not note:
            raise Fault('note_not_available', 404)
        if note['sha256'] != body['base_sha256']:
            raise Fault('note_changed_since_read', 409)
        path, revision = note['path'], note['revision']
    writer = store.vault_writers.get(body['source'])
    if writer is None or writer.vault_id != selected['vault_id']:
        raise Fault('writer_unavailable', 409)
    raw = writer.read_note(path)
    if raw is None:
        raise Fault('note_not_available', 404)
    if hashlib.sha256(raw).hexdigest() != body['base_sha256']:
        # The file on disk has moved on from what was indexed and shown.
        raise Fault('note_changed_since_read', 409)
    offset, inserted, result, diff = plan(path, raw, heading, body['text'])
    params = {'source': body['source'], 'vault_id': selected['vault_id'], 'path': path, 'base_revision': revision,
              **request, 'offset': offset, 'inserted': inserted.decode('utf-8'),
              'inserted_sha256': hashlib.sha256(inserted).hexdigest(), 'result_sha256': hashlib.sha256(result).hexdigest(),
              'diff': diff, 'precondition': 'file_bytes_equal_base_sha256'}
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner'})
        if db.execute('SELECT 1 FROM actions WHERE scope=? AND id=?', (p['scope'], body['request_id'])).fetchone():
            raise Fault('action_id_collision', 409)
        note = db.execute("SELECT sha256 FROM knowledge_notes WHERE scope=? AND source=? AND id=? AND status='ready'",
                          (p['scope'], body['source'], body['note_id'])).fetchone()
        if not note or note['sha256'] != body['base_sha256'] or not permitted(db, p, body['source'], store.now(), GRANT):
            raise Fault('note_changed_since_read', 409)
        if db.execute('SELECT count(*) FROM actions WHERE scope=?', (p['scope'],)).fetchone()[0] >= 5000:
            raise Fault('action_capacity', 409)
        expiry = store.now() + 900
        bound = {'id': body['request_id'], 'scope': p['scope'], 'actor': p['id'], 'capability': CAPABILITY,
                 'parameters': params, 'expires_at': expiry}
        db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?)', (p['scope'], body['request_id'], p['id'], CAPABILITY,
                   canonical(params), fingerprint(bound), expiry, 'proposed', store.now(), None))
        store.log(db, p['scope'], p['id'], 'action.proposed_vault_append', body['request_id'])
        return store.action_view(db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (p['scope'], body['request_id'])).fetchone())


def execute(store, row):
    """Insert the approved block if the file is still the approved base. Returns the observed outcome."""
    params = json.loads(row['parameters'])
    writer = store.vault_writers.get(params['source'])
    if writer is None or writer.vault_id != params['vault_id']:
        return 'writer_unavailable'
    return writer.append_to_note(params['path'], params['base_sha256'], params['offset'],
                                 params['inserted'].encode('utf-8'), params['result_sha256'])


def verify(store, row):
    params = json.loads(row['parameters'])
    writer = store.vault_writers.get(params['source'])
    if writer is None:
        return None
    data = writer.read_note(params['path'])
    if data is None or hashlib.sha256(data).hexdigest() != params['result_sha256']:
        return None
    return {'type': 'vault_append_readback', 'path': params['path'], 'heading': params['heading'],
            'sha256': params['result_sha256'], 'base_sha256': params['base_sha256'], 'offset': params['offset'],
            'inserted_sha256': params['inserted_sha256'], 'sent': False}
