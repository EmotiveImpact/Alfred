"""Read-only console projection over the existing authorised services.

The premium console receives only what the knowledge index and reviewed-memory
ledger already return to this bearer. Counts, labels and links are computed
after that filtering, never before. Authored note references, reviewed claims
and the support a reviewed claim cites are separate edge layers. Nothing here
writes, executes, merges identities or grants authority.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import re
from .local import Fault
from .policy import permitted

SCHEMA_VERSION = 1
NOTE_CATEGORY = {'project': 'projects', 'person': 'people', 'decision': 'operations',
                 'procedure': 'resources', 'map': 'knowledge', 'note': 'knowledge'}
NOTE_TYPE = {'project': 'project', 'person': 'person'}
ENTITY_CATEGORY = {'person': 'people', 'organisation': 'people', 'project': 'projects',
                   'asset': 'resources', 'decision': 'operations', 'commitment': 'operations',
                   'event': 'knowledge'}
ENTITY_TYPE = {'person': 'person', 'organisation': 'person', 'project': 'project',
               'asset': 'resource', 'decision': 'action', 'commitment': 'action', 'event': 'note'}
SOURCE_AVAILABILITY = {'ready': 'current', 'attention': 'attention', 'unavailable': 'unavailable'}
MAX_APPROVALS = 40
RECORD_ID = re.compile(r'(note|entity|source):([A-Za-z0-9][A-Za-z0-9_.-]{0,79})')


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat().replace('+00:00', 'Z')


def grant_revision(db, p, now):
    """Changes whenever this bearer's effective read authority could change."""
    policy = db.execute('SELECT strict,epoch FROM source_policy WHERE scope=?', (p['scope'],)).fetchone()
    sources = [r['id'] for r in db.execute(
        "SELECT id FROM credentials WHERE scope=? AND role='source' AND revoked=0 AND expires>?", (p['scope'], now))]
    allowed = sorted(s for s in sources if permitted(db, p, s, now, 'read'))
    return _digest({'credential': p['id'], 'generation': p['generation'], 'role': p['role'],
                    'scope': p['scope'], 'person': p['person_id'],
                    'policy': [policy['strict'], policy['epoch']] if policy else None,
                    'sources': allowed})[:32]


def _label(scope):
    words = re.split(r'[-_.]+', scope)
    return ' '.join(words).strip().capitalize() or scope


def _summary(body, limit=220):
    """First prose line of an authored note, as text. Never interpreted."""
    lines = body.splitlines()
    if lines and lines[0].strip() == '---':
        closing = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == '---'), None)
        lines = lines[closing + 1:] if closing is not None else []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        line = re.sub(r'!?\[\[([^\]|#]*)(?:[#|][^\]]*)?\]\]', r'\1', line)
        return line[:limit]
    return ''


def _authority(store, bearer):
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner', 'reader'})
        now = store.now()
        return p, now, grant_revision(db, p, now)


def workspaces(store, bearer):
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner', 'reader'})
        now = store.now()
        row = db.execute('SELECT simulation FROM workspaces WHERE id=?', (p['scope'],)).fetchone()
        return {'workspaces': [{'id': p['scope'], 'label': _label(p['scope']), 'role': p['role'],
                                'synthetic': bool(row and row['simulation'])}],
                'grantRevision': grant_revision(db, p, now),
                'basis': 'one workspace per credential; the server decides, the console never widens it'}


def _model(server, p):
    model = getattr(server, 'local_model', None)
    scope = getattr(getattr(server, 'supervisor', None), 'scope', None)
    return {'configured': model is not None, 'name': model.model if model is not None else None,
            'allowed': model is not None and p['role'] == 'owner' and p['scope'] == scope,
            'tools_enabled': False}


def projection(server, bearer):
    store, memory = server.store, getattr(server, 'memory', None)
    if not hasattr(store, 'knowledge'):
        raise Fault('knowledge_not_configured', 409)
    p, now, before = _authority(store, bearer)
    scope = p['scope']
    knowledge = store.knowledge(bearer)
    reviewed = memory.view(bearer) if memory is not None else {'entities': [], 'claims': []}
    expected = {n['id']: (n['revision'], n['sha256']) for n in knowledge['nodes']}
    with store.transaction() as db:
        q = store.authenticate(db, bearer, {'owner', 'reader'})
        if q['id'] != p['id'] or grant_revision(db, q, store.now()) != before:
            # Authority moved while the views were assembled: return nothing stale.
            raise Fault('projection_authority_changed', 409)
        bodies = {}
        if expected:
            marks = ','.join('?' * len(expected))
            for row in db.execute(f"SELECT id,body,revision,sha256 FROM knowledge_notes WHERE scope=? AND status='ready' AND id IN ({marks})",
                                  (scope, *expected)):
                if (row['revision'], row['sha256']) == expected[row['id']]:
                    bodies[row['id']] = row['body']
        if len(bodies) != len(expected):
            raise Fault('projection_data_changed', 409)
        approvals = []
        for row in db.execute('SELECT * FROM actions WHERE scope=? ORDER BY created DESC,id DESC LIMIT ?', (scope, MAX_APPROVALS)):
            view = store.action_view(row)
            text = view['parameters'].get('text') if isinstance(view['parameters'], dict) else None
            approvals.append({'id': view['id'], 'capability': view['capability'], 'state': view['state'],
                              'text': text if isinstance(text, str) else None,
                              'fingerprint': view['fingerprint'], 'createdAt': _iso(row['created']),
                              'expiresAt': _iso(view['expires_at']), 'evidenceCurrent': bool(store.evidence_valid(db, row)),
                              'mine': row['actor'] == p['id'], 'effect': view['effect']})
    nodes, edges = [], []
    sources = {s['source']: s for s in knowledge['sources']}
    for s in knowledge['sources']:
        nodes.append({'id': 'source:' + s['source'], 'label': s['label'], 'type': 'source', 'kind': 'vault',
                      'category': 'sources', 'origin': 'source', 'workspaceId': scope,
                      'availability': SOURCE_AVAILABILITY.get(s['status'], 'unavailable'),
                      'summary': {'ready': 'Selected source, last scan complete.',
                                  'attention': 'Selected source, scanned with reported issues.',
                                  'unavailable': 'Selected source is currently unavailable.'}.get(s['status'], 'Source state unknown.'),
                      'revision': (s['last_confirmed_snapshot'] or '')[:16], 'updatedAt': _iso(s['checked']),
                      'evidence': [], 'issues': len(s['errors'])})
    for n in knowledge['nodes']:
        nodes.append({'id': 'note:' + n['id'], 'label': n['title'], 'type': NOTE_TYPE.get(n['kind'], 'note'),
                      'kind': n['kind'], 'category': NOTE_CATEGORY[n['kind']], 'origin': 'authored_note',
                      'workspaceId': scope, 'availability': 'current', 'summary': _summary(bodies[n['id']]),
                      'path': n['path'], 'revision': str(n['revision']), 'sha256': n['sha256'],
                      'sourceId': 'source:' + n['source'], 'updatedAt': _iso(n['indexed']),
                      'evidence': [{'sourceId': 'note:' + n['id'], 'revision': str(n['revision']), 'sha256': n['sha256'],
                                    'location': {'kind': 'lines', 'start': 1, 'end': max(1, len(bodies[n['id']].splitlines()))},
                                    'basis': 'authored', 'availability': 'current'}]})
    for link in knowledge['links']:
        edges.append({'id': 'ref:' + _digest([link['source'], link['target'], link['line'], link['relation']])[:20],
                      'from': 'note:' + link['source'], 'to': 'note:' + link['target'], 'layer': 'note_reference',
                      'relation': link['relation'],
                      'evidence': [{'sourceId': 'note:' + link['source'], 'revision': str(link['source_revision']),
                                    'sha256': link['source_sha256'], 'location': {'kind': 'lines', 'start': link['line'], 'end': link['line']},
                                    'basis': 'authored', 'availability': 'current'}]})
    entities = {e['id']: e for e in reviewed['entities']}
    projected = {n['id'] for n in nodes}
    per_entity = {}
    support = {}
    for c in reviewed['claims']:
        tally = per_entity.setdefault(c['subject_id'], {'usable': 0, 'proposed': 0, 'disputed': 0, 'conflicted': 0, 'unavailable': 0})
        if c['usable']:
            tally['usable'] += 1
        elif c['state'] == 'proposed':
            tally['proposed'] += 1
        elif c['state'] == 'disputed':
            tally['disputed'] += 1
        if c['conflicts']:
            tally['conflicted'] += 1
        if c['state'] in ('accepted', 'disputed', 'proposed') and not c['source']:
            tally['unavailable'] += 1
        if not c['usable'] or 'note:' + c['source']['note_id'] not in projected:
            continue
        evidence = {'sourceId': 'note:' + c['source']['note_id'], 'revision': str(c['source']['revision']),
                    'sha256': c['source']['sha256'],
                    'location': {'kind': 'lines', 'start': c['source']['start_line'], 'end': c['source']['end_line']},
                    'basis': 'human_review', 'availability': 'current', 'claimId': c['id'], 'claimVersion': c['version']}
        if c['object_id'] and c['object_id'] in entities:
            edges.append({'id': 'claim:' + c['id'], 'from': 'entity:' + c['subject_id'], 'to': 'entity:' + c['object_id'],
                          'layer': 'reviewed_claim', 'relation': c['predicate'], 'evidence': [evidence]})
        key = (c['subject_id'], c['source']['note_id'])
        support.setdefault(key, []).append(evidence)
    for (subject, note), evidence in sorted(support.items()):
        edges.append({'id': 'support:' + _digest([subject, note])[:20], 'from': 'entity:' + subject, 'to': 'note:' + note,
                      'layer': 'review_support', 'relation': 'supported_by', 'evidence': evidence})
    for e in reviewed['entities']:
        tally = per_entity.get(e['id'], {'usable': 0, 'proposed': 0, 'disputed': 0, 'conflicted': 0, 'unavailable': 0})
        parts = [f"{tally['usable']} current reviewed statement{'s' if tally['usable'] != 1 else ''}"]
        parts += [f"{v} {k}" for k, v in tally.items() if k != 'usable' and v]
        nodes.append({'id': 'entity:' + e['id'], 'label': e['name'], 'type': ENTITY_TYPE[e['kind']], 'kind': e['kind'],
                      'category': ENTITY_CATEGORY[e['kind']], 'origin': 'reviewed_entity', 'workspaceId': scope,
                      'availability': 'current', 'summary': '; '.join(parts) + '.', 'statements': tally,
                      'revision': str(e['created']), 'updatedAt': _iso(e['created']), 'evidence': []})
    latest = [c for c in reviewed['claims'] if c['usable']]
    latest.sort(key=lambda c: (c['reviewed'] or 0, c['id']), reverse=True)
    insights = [{'entityId': 'entity:' + c['subject_id'], 'claimId': c['id'], 'predicate': c['predicate'],
                 'value': c['value'], 'objectId': 'entity:' + c['object_id'] if c['object_id'] else None,
                 'reviewedAt': _iso(c['reviewed']), 'supportId': 'note:' + c['source']['note_id'],
                 'basis': 'user_reviewed_statement_not_verified_fact'} for c in latest[:3]
                if c['subject_id'] in entities]
    content = {'nodes': nodes, 'edges': edges, 'approvals': approvals}
    return {'kind': 'authorised_projection', 'schemaVersion': SCHEMA_VERSION, 'workspaceId': scope,
            'dataRevision': _digest(content)[:32], 'grantRevision': before, 'observedAt': _iso(now),
            **content,
            'executive': {'priorities': [], 'prioritiesStatus': 'not_recorded', 'insights': insights,
                          'milestonesStatus': 'not_recorded'},
            'sources': [{'id': 'source:' + s['source'], 'label': s['label'], 'status': s['status'],
                         'checkedAt': _iso(s['checked']), 'issues': len(s['errors'])} for s in sources.values()],
            'counts': {'notes': len(knowledge['nodes']), 'entities': len(reviewed['entities']),
                       'noteLinks': len(knowledge['links']), 'reviewedClaims': sum(e['layer'] == 'reviewed_claim' for e in edges),
                       'unresolvedLinks': len(knowledge['issues']), 'pendingApprovals': sum(a['state'] == 'proposed' for a in approvals)},
            'model': _model(server, p), 'paused': knowledge['paused'], 'readOnly': True,
            'basis': {'notes': 'authored_note_not_verified_fact', 'claims': 'user_reviewed_statements_not_verified_facts',
                      'decorativeGeometry': 'not_included'},
            'authorityGranted': False}


def record(server, bearer, identity):
    """Inspect one permitted record. Unknown and denied records are indistinguishable."""
    match = RECORD_ID.fullmatch(identity) if isinstance(identity, str) else None
    if not match:
        raise Fault('record_not_available', 404)
    kind, key = match[1], match[2]
    store, memory = server.store, getattr(server, 'memory', None)
    p, now, revision = _authority(store, bearer)
    if kind == 'note':
        if not re.fullmatch(r'[0-9a-f]{24}', key):
            raise Fault('record_not_available', 404)
        try:
            note = store.knowledge_note(bearer, key)
        except Fault as exc:
            if exc.status in (401, 403):
                raise
            raise Fault('record_not_available', 404) from None
        lines = note['body'].splitlines()
        return {'id': identity, 'type': 'note', 'origin': 'authored_note', 'workspaceId': p['scope'],
                'label': note['title'], 'kind': note['kind'], 'path': note['path'], 'revision': str(note['revision']),
                'sha256': note['sha256'], 'indexedAt': _iso(note['indexed']), 'lines': lines[:400],
                'truncated': len(lines) > 400, 'basis': note['basis'], 'grantRevision': revision,
                'authorityGranted': False}
    if kind == 'source':
        knowledge = store.knowledge(bearer)
        found = [s for s in knowledge['sources'] if s['source'] == key]
        if not found:
            raise Fault('record_not_available', 404)
        s = found[0]
        return {'id': identity, 'type': 'source', 'origin': 'source', 'workspaceId': p['scope'], 'label': s['label'],
                'status': s['status'], 'checkedAt': _iso(s['checked']),
                'lastCompleteScan': _iso(s['last_complete_scan']) if s['last_complete_scan'] else None,
                'snapshot': (s['last_confirmed_snapshot'] or '')[:16], 'issues': s['errors'][:32],
                'notes': sum(n['source'] == key for n in knowledge['nodes']), 'grantRevision': revision,
                'authorityGranted': False}
    if memory is None:
        raise Fault('record_not_available', 404)
    reviewed = memory.view(bearer)
    entities = {e['id']: e for e in reviewed['entities']}
    if key not in entities:
        raise Fault('record_not_available', 404)
    statements = []
    for c in reviewed['claims']:
        if c['subject_id'] != key and c['object_id'] != key:
            continue
        support = None
        if c['source']:
            support = {'noteId': 'note:' + c['source']['note_id'], 'path': c['source']['path'], 'title': c['source']['title'],
                       'revision': str(c['source']['revision']), 'sha256': c['source']['sha256'],
                       'startLine': c['source']['start_line'], 'endLine': c['source']['end_line'], 'quote': c['source']['quote']}
        statements.append({'id': c['id'], 'version': c['version'], 'state': c['state'], 'usable': c['usable'],
                           'subject': {k: entities[c['subject_id']][k] for k in ('id', 'kind', 'name')} if c['subject_id'] in entities else None,
                           'predicate': c['predicate'], 'value': c['value'],
                           'object': {k: entities[c['object_id']][k] for k in ('id', 'kind', 'name')} if c['object_id'] in entities else None,
                           'validFrom': _iso(c['valid_from']) if c['valid_from'] is not None else None,
                           'validUntil': _iso(c['valid_until']) if c['valid_until'] is not None else None,
                           'validNow': c['valid_now'], 'conflicts': c['conflicts'], 'replacesId': c['replaces_id'],
                           'reviewedAt': _iso(c['reviewed']) if c['reviewed'] else None,
                           'support': support, 'supportAvailable': support is not None})
    e = entities[key]
    same_name = sorted(x['id'] for x in entities.values() if x['id'] != key and (x['kind'], x['name'].casefold()) == (e['kind'], e['name'].casefold()))
    return {'id': identity, 'type': 'entity', 'origin': 'reviewed_entity', 'workspaceId': p['scope'], 'label': e['name'],
            'kind': e['kind'], 'createdAt': _iso(e['created']), 'statements': statements,
            'sameNameEntities': ['entity:' + x for x in same_name], 'basis': 'user_reviewed_statements_not_verified_facts',
            'grantRevision': revision, 'authorityGranted': False}
