"""Drafts that never silently disappear (owner decision, 16 October 2026).

A proposed local draft keeps its short approval window: after it lapses the draft
cannot be approved or dispatched. The draft itself stays in the ledger with a visible
status (``lapsed``, ``archived``, ``withdrawn``) and the owner can find it again by
text, date and status, archive or unarchive it, and re-propose it. Re-proposing makes
a NEW action with a fresh fingerprint over the current exact parameters, re-binds the
original source conditions and rechecks them in the same transaction. An old approval
never dispatches.

Archiving is not a way around deletion. When a source or a reviewed statement is
forgotten, every undecided draft that depends on it is withdrawn: its text is replaced
with a removal notice, it cannot be re-proposed and it stays listed so the owner can
see that it existed. Completed drafts are not undone, as before.

Value-free bindings only: ``draft_sources`` keeps note identifiers, revisions, hashes
and reviewed statement versions, never passages or values.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import re
from .local import Fault, canonical, exact, fingerprint, ident, text as plain_text

CAPABILITIES = ('message.draft', 'vault.inbox_note')
WINDOW = 900
REMOVED = 'Removed when its source was forgotten.'
STATUSES = ('awaiting_approval', 'lapsed', 'archived', 'withdrawn', 'queued', 'executing',
            'uncertain', 'verified', 'cancelled', 'blocked', 'failed')
IN_PROGRESS = ('queued', 'executing', 'uncertain')
TABLES = (
    '''CREATE TABLE IF NOT EXISTS draft_records(
 scope TEXT NOT NULL, action_id TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
 archived_at INTEGER, version INTEGER NOT NULL DEFAULT 1, reproposed_from TEXT,
 withdrawn TEXT, withdrawn_at INTEGER, PRIMARY KEY(scope,action_id))''',
    '''CREATE TABLE IF NOT EXISTS draft_sources(
 scope TEXT NOT NULL, action_id TEXT NOT NULL, kind TEXT NOT NULL, binding TEXT NOT NULL,
 PRIMARY KEY(scope,action_id))''',
)


def ensure(db):
    """Additive tables. Single statements, so this is safe inside an open transaction."""
    for statement in TABLES:
        db.execute(statement)


def _has(db, table):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


# Lifecycle hooks -------------------------------------------------------------

def preserve_conversation_links(db, session=None):
    """Keep a value-free copy of a conversation draft's source binding before the
    conversation row (and its link) is removed by retention or by forgetting it."""
    if not _has(db, 'conversation_action_sources'):
        return
    ensure(db)
    query, args = 'SELECT scope,action_id,references_json FROM conversation_action_sources', ()
    if session is not None:
        query, args = query + ' WHERE session=?', (session,)
    for link in db.execute(query, args).fetchall():
        db.execute('INSERT OR IGNORE INTO draft_sources VALUES (?,?,?,?)',
                   (link['scope'], link['action_id'], 'conversation', link['references_json']))


def _bindings(db, scope):
    """Every saved source binding for drafts in this scope: action id to binding."""
    found = {}
    if _has(db, 'draft_sources'):
        for row in db.execute("SELECT action_id,binding FROM draft_sources WHERE scope=?", (scope,)):
            found[row['action_id']] = json.loads(row['binding'])
    if _has(db, 'conversation_action_sources'):
        for row in db.execute('SELECT action_id,references_json FROM conversation_action_sources WHERE scope=?', (scope,)):
            found.setdefault(row['action_id'], json.loads(row['references_json']))
    return found


def bound_to_notes(db, scope, notes):
    result = set()
    for action_id, binding in _bindings(db, scope).items():
        refs = binding if isinstance(binding, list) else binding.get('sources', [])
        cited = {r.get('note_id') for r in refs if isinstance(r, dict)}
        if not isinstance(binding, list):
            cited |= {(m.get('support') or {}).get('note_id') for m in binding.get('memory', []) if isinstance(m, dict)}
        if cited & set(notes):
            result.add(action_id)
    return result


def bound_to_claims(db, scope, claim_ids):
    result = set()
    for action_id, binding in _bindings(db, scope).items():
        memory = binding.get('memory', []) if isinstance(binding, dict) else []
        if {m.get('claim_id') for m in memory if isinstance(m, dict)} & set(claim_ids):
            result.add(action_id)
    return result


def withdraw(db, scope, action_ids, reason, now):
    """Withdraw undecided drafts bound to forgotten content. Idempotent, replayable.

    The text is replaced, so an archived or lapsed copy cannot keep forgotten content.
    Drafts whose effect may already exist (executing, uncertain, verified) are left as
    they are and reported by the caller as not undone."""
    if not _has(db, 'actions'):
        return []
    ensure(db)
    withdrawn = []
    for action_id in sorted(set(action_ids)):
        row = db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (scope, action_id)).fetchone()
        if not row or row['capability'] not in CAPABILITIES or row['state'] in ('executing', 'uncertain', 'verified'):
            continue
        params = json.loads(row['parameters'])
        if isinstance(params, dict) and params.get('text') != REMOVED:
            params['text'] = REMOVED
            db.execute('UPDATE actions SET parameters=? WHERE scope=? AND id=?', (canonical(params), scope, action_id))
        if row['state'] in ('proposed', 'queued'):
            db.execute("UPDATE actions SET state='cancelled' WHERE scope=? AND id=?", (scope, action_id))
            db.execute("UPDATE outbox SET state='cancelled' WHERE scope=? AND action_id=?", (scope, action_id))
        db.execute('INSERT OR IGNORE INTO draft_records(scope,action_id) VALUES (?,?)', (scope, action_id))
        changed = db.execute('UPDATE draft_records SET withdrawn=?,withdrawn_at=?,version=version+1 WHERE scope=? AND action_id=? AND withdrawn IS NULL',
                             (reason, now, scope, action_id)).rowcount
        if changed:
            withdrawn.append(action_id)
    return withdrawn


# Approval condition for re-proposed conversation drafts ----------------------

def reproposal_current(store, db, row):
    """Source condition for a re-proposed draft whose conversation may have ended.

    The same checks a conversation draft gets, minus the conversation itself: every
    cited note revision and every reviewed statement version must still be current
    and permitted for this person. Checked at approval and again at dispatch."""
    if not _has(db, 'draft_sources'):
        return False
    link = db.execute("SELECT binding FROM draft_sources WHERE scope=? AND action_id=? AND kind='sources'",
                      (row['scope'], row['id'])).fetchone()
    if not link:
        return False
    from .conversation import refs_current_db
    from .reviewed_memory import context_current_db, ambiguities_current_db
    binding = json.loads(link['binding'])
    refs = binding if isinstance(binding, list) else binding['sources']
    p = {'scope': row['scope'], 'id': row['actor']}
    if not refs_current_db(db, row['scope'], refs, store.now(), p):
        return False
    if isinstance(binding, list):
        return True
    current = context_current_db(db, p, binding['memory'], store.now())
    return current is not None and ambiguities_current_db(db, p, current, binding['memory_ambiguities'])


# Views -----------------------------------------------------------------------

def _record(db, scope, action_id):
    row = db.execute('SELECT * FROM draft_records WHERE scope=? AND action_id=?', (scope, action_id)).fetchone()
    return dict(row) if row else {'archived': 0, 'archived_at': None, 'version': 1, 'reproposed_from': None,
                                  'withdrawn': None, 'withdrawn_at': None}


def _origin(db, row):
    """Which source condition this draft was bound to, or None."""
    scope, action_id = row['scope'], row['id']
    if row['capability'] == 'vault.inbox_note':
        return 'inbox', None
    if _has(db, 'desk_action_evidence'):
        link = db.execute('SELECT * FROM desk_action_evidence WHERE scope=? AND action_id=?', (scope, action_id)).fetchone()
        if link:
            return 'evidence', dict(link)
    binding = None
    if _has(db, 'conversation_action_sources'):
        link = db.execute('SELECT references_json FROM conversation_action_sources WHERE scope=? AND action_id=?', (scope, action_id)).fetchone()
        binding = json.loads(link[0]) if link else None
    if binding is None and _has(db, 'draft_sources'):
        link = db.execute('SELECT binding FROM draft_sources WHERE scope=? AND action_id=?', (scope, action_id)).fetchone()
        binding = json.loads(link[0]) if link else None
    if binding is not None:
        return 'sources', binding
    if _has(db, 'routine_action_sources'):
        link = db.execute('SELECT * FROM routine_action_sources WHERE scope=? AND action_id=?', (scope, action_id)).fetchone()
        if link:
            return 'routine', dict(link)
    return None, None


def status(row, record, now):
    if record['withdrawn']:
        return 'withdrawn'
    if record['archived']:
        return 'archived'
    if row['state'] == 'proposed':
        return 'awaiting_approval' if row['expires'] > now else 'lapsed'
    return row['state']


def draft_status(db, row, now):
    """Status for a read-only projection; does not create tables."""
    if not _has(db, 'draft_records'):
        record = {'withdrawn': None, 'archived': 0}
    else:
        record = _record(db, row['scope'], row['id'])
    return status(row, record, now)


def view(db, row, now, *, detail=False):
    record = _record(db, row['scope'], row['id'])
    params = json.loads(row['parameters'])
    value = params.get('text') if isinstance(params, dict) else None
    if record['withdrawn']:
        value = None
    later = [r[0] for r in db.execute('SELECT action_id FROM draft_records WHERE scope=? AND reproposed_from=? ORDER BY action_id',
                                      (row['scope'], row['id']))]
    result = {'id': row['id'], 'capability': row['capability'], 'status': status(row, record, now),
              'ledger_state': row['state'], 'archived': bool(record['archived']), 'archived_at': record['archived_at'],
              'version': record['version'], 'text': value if isinstance(value, str) else None,
              'path': params.get('path') if isinstance(params, dict) else None,
              'created_at': row['created'], 'approval_expires_at': row['expires'],
              'approval_lapsed': row['state'] == 'proposed' and row['expires'] <= now,
              'withdrawn': record['withdrawn'], 'withdrawn_at': record['withdrawn_at'],
              'reproposed_from': record['reproposed_from'], 'reproposed_as': later,
              'origin': _origin(db, row)[0], 'effect': 'local_draft_only_not_sent'}
    if detail:
        result['fingerprint'] = row['fingerprint']
    return result


def _date(value, end=False):
    if re.fullmatch(r'[0-9]{1,12}', value):
        return int(value)
    if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        try:
            day = datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            raise Fault('invalid_draft_query') from None
        return int(day.timestamp()) + (86399 if end else 0)
    raise Fault('invalid_draft_query')


def parse_query(query):
    """HTTP query (one value per key) into validated filters."""
    allowed = {'q', 'status', 'archived', 'since', 'until', 'limit'}
    if set(query) - allowed or any(len(v) != 1 for v in query.values()):
        raise Fault('invalid_draft_query')
    one = {k: v[0] for k, v in query.items()}
    filters = {'q': None, 'status': None, 'archived': 'exclude', 'since': None, 'until': None, 'limit': 50}
    if 'q' in one:
        if not 1 <= len(one['q']) <= 200 or any(ord(c) < 32 for c in one['q']):
            raise Fault('invalid_draft_query')
        filters['q'] = one['q']
    if 'status' in one:
        if one['status'] not in STATUSES:
            raise Fault('invalid_draft_query')
        filters['status'] = one['status']
    if 'archived' in one:
        if one['archived'] not in ('exclude', 'include', 'only'):
            raise Fault('invalid_draft_query')
        filters['archived'] = one['archived']
    if 'since' in one:
        filters['since'] = _date(one['since'])
    if 'until' in one:
        filters['until'] = _date(one['until'], end=True)
    if 'limit' in one:
        if not re.fullmatch(r'[0-9]{1,3}', one['limit']) or not 1 <= int(one['limit']) <= 200:
            raise Fault('invalid_draft_query')
        filters['limit'] = int(one['limit'])
    return filters


def search(store, bearer, filters=None):
    """The owner's own drafts, newest first, including lapsed ones; archived on request."""
    f = {'q': None, 'status': None, 'archived': 'exclude', 'since': None, 'until': None, 'limit': 50} | (filters or {})
    archived = 'only' if f['status'] == 'archived' else f['archived']
    needle = f['q'].casefold() if f['q'] else None
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner'})
        ensure(db)
        now, found, total = store.now(), [], 0
        marks = ','.join('?' * len(CAPABILITIES))
        for row in db.execute(f'SELECT * FROM actions WHERE scope=? AND actor=? AND capability IN ({marks}) ORDER BY created DESC,id DESC',
                              (p['scope'], p['id'], *CAPABILITIES)):
            item = view(db, row, now)
            if archived == 'exclude' and item['archived'] or archived == 'only' and not item['archived']:
                continue
            if f['status'] and f['status'] != 'archived' and item['status'] != f['status']:
                continue
            if f['since'] is not None and row['created'] < f['since'] or f['until'] is not None and row['created'] > f['until']:
                continue
            if needle and needle not in ' '.join(filter(None, (item['text'], item['path']))).casefold():
                continue
            total += 1
            if len(found) < f['limit']:
                found.append(item)
        return {'drafts': found, 'matched': total, 'limit': f['limit'], 'archived_filter': archived,
                'approval_window_seconds': WINDOW, 'kept_until_deleted_or_forgotten': True, 'now': now}


def _own(store, db, bearer, action_id):
    ident(action_id)
    p = store.authenticate(db, bearer, {'owner'})
    ensure(db)
    row = db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (p['scope'], action_id)).fetchone()
    if not row or row['actor'] != p['id'] or row['capability'] not in CAPABILITIES:
        raise Fault('draft_not_found', 404)
    return p, row


def reopen(store, bearer, action_id):
    """Full draft, with whether re-proposing would pass its source checks right now."""
    with store.transaction() as db:
        p, row = _own(store, db, bearer, action_id)
        result = view(db, row, store.now(), detail=True)
        reason = None
        db.execute('SAVEPOINT draft_preview')
        try:
            _repropose(store, db, p, row, 'preview-' + row['fingerprint'][:24], None)
        except Fault as exc:
            reason = exc.code
        finally:
            db.execute('ROLLBACK TO draft_preview')
            db.execute('RELEASE draft_preview')
        return result | {'reproposable': reason is None, 'repropose_blocked_by': reason}


def _bump(store, db, p, row, version, archived):
    record = _record(db, p['scope'], row['id'])
    if type(version) is not int or version != record['version']:
        raise Fault('draft_changed', 409)
    if bool(record['archived']) == archived:
        return False
    db.execute('INSERT OR IGNORE INTO draft_records(scope,action_id) VALUES (?,?)', (p['scope'], row['id']))
    db.execute('UPDATE draft_records SET archived=?,archived_at=?,version=version+1 WHERE scope=? AND action_id=?',
               (int(archived), store.now() if archived else None, p['scope'], row['id']))
    return True


def archive(store, bearer, action_id, body):
    exact(body, {'version'})
    with store.transaction() as db:
        p, row = _own(store, db, bearer, action_id)
        if row['state'] in IN_PROGRESS:
            raise Fault('draft_in_progress', 409)
        if _bump(store, db, p, row, body['version'], True):
            if row['state'] == 'proposed' and row['expires'] > store.now():
                # Setting a draft aside closes its approval window; the fingerprint is unchanged,
                # so the old approval can never be used. Re-propose to approve it later.
                db.execute('UPDATE actions SET expires=? WHERE scope=? AND id=?', (store.now(), p['scope'], action_id))
            store.log(db, p['scope'], p['id'], 'draft.archived', action_id)
        row = db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (p['scope'], action_id)).fetchone()
        return view(db, row, store.now(), detail=True)


def unarchive(store, bearer, action_id, body):
    exact(body, {'version'})
    with store.transaction() as db:
        p, row = _own(store, db, bearer, action_id)
        if _bump(store, db, p, row, body['version'], False):
            store.log(db, p['scope'], p['id'], 'draft.unarchived', action_id)
        return view(db, row, store.now(), detail=True)


def _repropose(store, db, p, row, request_id, new_text):
    """Insert a fresh proposal bound to current parameters and rebinding the original
    source condition, then recheck that condition. Raises (and the caller rolls back)
    when anything is no longer current."""
    record, now = _record(db, p['scope'], row['id']), store.now()
    if record['withdrawn']:
        raise Fault('draft_withdrawn', 409)
    if row['state'] == 'proposed' and row['expires'] > now:
        raise Fault('draft_still_awaiting_approval', 409)
    if row['state'] in IN_PROGRESS:
        raise Fault('draft_in_progress', 409)
    params = json.loads(row['parameters'])
    if new_text is not None:
        if row['capability'] != 'message.draft':
            raise Fault('draft_text_not_editable', 409)
        params = {'text': new_text}
    kind, link = _origin(db, row)
    if kind is None:
        raise Fault('draft_has_no_source_binding', 409)
    bound = {'id': request_id, 'scope': p['scope'], 'actor': p['id'], 'capability': row['capability'],
             'parameters': params, 'reproposed_from': row['id']}
    existing = db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (p['scope'], request_id)).fetchone()
    if existing:
        prior = _record(db, p['scope'], request_id)
        if existing['actor'] != p['id'] or prior['reproposed_from'] != row['id'] or json.loads(existing['parameters']) != params:
            raise Fault('action_id_collision', 409)
        return existing, False
    if db.execute('SELECT count(*) FROM actions WHERE scope=?', (p['scope'],)).fetchone()[0] >= 5000:
        raise Fault('action_capacity', 409)
    expiry = now + WINDOW
    if kind == 'evidence':
        event = db.execute('SELECT expires FROM events WHERE scope=? AND seq=?', (p['scope'], link['event_seq'])).fetchone()
        if not event:
            raise Fault('evidence_not_current', 409)
        expiry = min(expiry, event['expires'])
        bound['evidence'] = {'seq': link['event_seq'], 'fingerprint': link['event_fingerprint']}
    elif kind == 'sources':
        bound['sources'] = link if isinstance(link, list) else link['sources']
        if isinstance(link, dict):
            bound['memory'], bound['memory_ambiguities'] = link['memory'], link['memory_ambiguities']
    elif kind == 'routine':
        bound['routine'] = {'nomination': link['nomination'], 'cite': {'kind': link['cite_kind'], 'id': link['cite_id'], 'version': link['cite_version']}}
    if expiry <= now:
        raise Fault('evidence_not_current', 409)
    bound['expires_at'] = expiry
    db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?)', (p['scope'], request_id, p['id'], row['capability'],
               canonical(params), fingerprint(bound), expiry, 'proposed', now, None))
    if kind == 'evidence':
        db.execute('INSERT INTO desk_action_evidence VALUES (?,?,?,?)', (p['scope'], request_id, link['event_seq'], link['event_fingerprint']))
    elif kind == 'sources':
        db.execute('INSERT INTO draft_sources VALUES (?,?,?,?)', (p['scope'], request_id, 'sources', json.dumps(link)))
    elif kind == 'routine':
        db.execute('INSERT INTO routine_action_sources VALUES (?,?,?,?,?,?,?)', (p['scope'], request_id, link['nomination'],
                   p['id'], link['cite_kind'], link['cite_id'], link['cite_version']))
    db.execute('INSERT INTO draft_records(scope,action_id,reproposed_from) VALUES (?,?,?)', (p['scope'], request_id, row['id']))
    fresh = db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (p['scope'], request_id)).fetchone()
    # The authoritative recheck: the very condition approval and dispatch will apply.
    if not store.evidence_valid(db, fresh):
        raise Fault('evidence_not_current', 409)
    return fresh, True


def repropose(store, bearer, action_id, body):
    keys = {'version', 'request_id'}
    exact(body, keys | {'text'} if isinstance(body, dict) and 'text' in body else keys)
    ident(body['request_id'])
    if 'text' in body:
        plain_text(body['text'])
    with store.transaction() as db:
        p, row = _own(store, db, bearer, action_id)
        if type(body['version']) is not int or body['version'] != _record(db, p['scope'], row['id'])['version']:
            raise Fault('draft_changed', 409)
        fresh, created = _repropose(store, db, p, row, body['request_id'], body.get('text'))
        if created:
            store.log(db, p['scope'], p['id'], 'action.reproposed_from_draft', body['request_id'])
        return store.action_view(fresh) | {'reproposed_from': row['id'], 'draft': view(db, fresh, store.now(), detail=True)}


def route(store, path, mutation, bearer, body, query):
    """``/desk/drafts`` routes, reached only after Host, Origin, session and CSRF checks."""
    parts = path.split('/')[3:]
    if not mutation and parts == []:
        return search(store, bearer, parse_query(query))
    if query:
        raise Fault('invalid_draft_query')
    if not mutation and len(parts) == 1:
        return reopen(store, bearer, parts[0])
    if mutation and len(parts) == 2 and parts[1] in ('archive', 'unarchive', 'repropose'):
        return {'archive': archive, 'unarchive': unarchive, 'repropose': repropose}[parts[1]](store, bearer, parts[0], body)
    raise Fault('not_found', 404)
