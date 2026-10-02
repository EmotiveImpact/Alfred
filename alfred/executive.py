"""Executive records: goals, priorities, commitments, decisions, milestones, follow-ups (ATT-002).

Records are written by the person, actor-private like reviewed memory, and may cite
exact lines of an authored note. A cited line that later changes is flagged, never
silently trusted, and the record is kept. Project progress counts only recorded
milestones. Recommendations come from one stated rule and stay recommendations
until the person accepts one; nothing here becomes an obligation by inference, and
nothing here grants authority to act.
"""
from __future__ import annotations
import hashlib
import json
import re
import secrets
from .local import Fault, exact, ident, text, timestamp

KINDS = ('goal', 'priority', 'commitment', 'decision', 'milestone', 'follow_up')
STATUSES = {'goal': ('active', 'achieved', 'dropped'), 'priority': ('open', 'done', 'dropped'),
            'commitment': ('open', 'done', 'dropped'), 'decision': ('proposed', 'decided', 'superseded'),
            'milestone': ('open', 'done', 'dropped'), 'follow_up': ('open', 'done', 'dropped')}
FIRST = {'goal': 'active', 'priority': 'open', 'commitment': 'open', 'decision': 'proposed',
         'milestone': 'open', 'follow_up': 'open'}
OPEN = {'active', 'open', 'proposed'}
RECOMMENDATION_WINDOW = 7 * 86400
MAX_RECORDS = 512
PROJECT = re.compile(r'(note):([0-9a-f]{24})|(entity):([A-Za-z0-9][A-Za-z0-9_.-]{0,79})')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS executive_meta(version INTEGER NOT NULL);
INSERT INTO executive_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM executive_meta);
CREATE TABLE IF NOT EXISTS executive_records(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, request_id TEXT NOT NULL,
 request_hash TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, detail TEXT NOT NULL,
 status TEXT NOT NULL, project TEXT, due INTEGER, rank INTEGER, support TEXT,
 origin TEXT NOT NULL, derived_from TEXT, version INTEGER NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL,
 UNIQUE(scope,actor,request_id));
CREATE INDEX IF NOT EXISTS executive_owner ON executive_records(scope,actor);
'''


def _multiline(value, limit):
    """Printable text with newlines and tabs; empty allowed."""
    if not isinstance(value, str) or len(value) > limit:
        raise Fault('invalid_text')
    if any((ord(c) < 32 and c not in '\n\t') or 127 <= ord(c) < 160 for c in value):
        raise Fault('control_character')
    return value.strip()


def _project(value):
    if value is None:
        return None
    match = PROJECT.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise Fault('invalid_project_reference')
    return value


class ExecutiveRecords:
    def __init__(self, store):
        self.store = store
        with store.connection() as db:
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
            if [r[0] for r in db.execute('SELECT version FROM executive_meta')] != [1]:
                raise Fault('unsupported_executive_version')

    # Support -------------------------------------------------------------

    def _bind_support(self, db, p, ref):
        """Bind exact lines of a currently permitted note, like reviewed statements do."""
        from .reviewed_memory import ReviewedMemory
        source = ReviewedMemory._source(db, p['scope'], ref, self.store.now(), p)
        return {k: source[k] for k in ('note_id', 'sha256', 'revision', 'start_line', 'end_line', 'quote_hash')}

    def _support_view(self, db, p, support):
        if not support:
            return None
        from .reviewed_memory import ReviewedMemory
        ref = {k: support[k] for k in ('note_id', 'sha256', 'revision', 'start_line', 'end_line')}
        try:
            current = ReviewedMemory._source(db, p['scope'], ref, self.store.now(), p)
        except Fault as exc:
            # Changed, removed, unavailable or not permitted: say which without leaking text.
            return {'note_id': support['note_id'], 'start_line': support['start_line'], 'end_line': support['end_line'],
                    'state': 'changed' if exc.code == 'memory_source_changed' else 'unavailable', 'quote': None}
        if current['quote_hash'] != support['quote_hash']:
            return {'note_id': support['note_id'], 'start_line': support['start_line'], 'end_line': support['end_line'],
                    'state': 'changed', 'quote': None}
        return {'note_id': current['note_id'], 'path': current['path'], 'title': current['title'],
                'start_line': current['start_line'], 'end_line': current['end_line'], 'quote': current['quote'], 'state': 'current'}

    # Writes --------------------------------------------------------------

    def create(self, bearer, body, *, derived_from=None):
        exact(body, {'request_id', 'kind', 'title', 'detail', 'project', 'due', 'rank', 'support'})
        ident(body['request_id']); text(body['title'], 160); _multiline(body['detail'], 1200)
        if body['kind'] not in KINDS:
            raise Fault('invalid_executive_kind')
        project = _project(body['project'])
        if body['due'] is not None:
            timestamp(body['due'])
        if body['rank'] is not None and (type(body['rank']) is not int or not 1 <= body['rank'] <= 1000):
            raise Fault('invalid_rank')
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            old = db.execute('SELECT id,request_hash FROM executive_records WHERE scope=? AND actor=? AND request_id=?',
                             (p['scope'], p['id'], body['request_id'])).fetchone()
            if old:
                if old['request_hash'] != digest:
                    raise Fault('executive_request_collision', 409)
                return self._one(db, p, old['id'])
            if db.execute('SELECT count(*) FROM executive_records WHERE scope=? AND actor=?', (p['scope'], p['id'])).fetchone()[0] >= MAX_RECORDS:
                raise Fault('executive_capacity', 409)
            self._check_project(db, p, project)
            support = self._bind_support(db, p, body['support']) if body['support'] is not None else None
            rid = 'exec-' + secrets.token_hex(12); now = self.store.now()
            db.execute('INSERT INTO executive_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (rid, p['scope'], p['id'], body['request_id'], digest, body['kind'], body['title'].strip(), body['detail'].strip(),
                        FIRST[body['kind']], project, body['due'], body['rank'], json.dumps(support) if support else None,
                        'accepted_recommendation' if derived_from else 'user_authored', derived_from, 1, now, now))
            self.store.log(db, p['scope'], p['id'], 'executive.created', rid)
            return self._one(db, p, rid)

    def _check_project(self, db, p, project):
        """A project link must point at a record this person can currently see."""
        if project is None:
            return
        kind, _, key = project.partition(':')
        if kind == 'entity':
            ok = db.execute("SELECT 1 FROM memory_entities WHERE id=? AND scope=? AND actor=?", (key, p['scope'], p['id'])).fetchone() \
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_entities'").fetchone() else None
        else:
            from .policy import permitted
            row = db.execute("SELECT source FROM knowledge_notes WHERE scope=? AND id=? AND status='ready'", (p['scope'], key)).fetchone()
            ok = row and permitted(db, p, row['source'], self.store.now())
        if not ok:
            raise Fault('project_not_available', 404)

    def update(self, bearer, identity, body):
        allowed = {'version', 'status', 'title', 'detail', 'due', 'rank'}
        if type(body) is not dict or 'version' not in body or not set(body) <= allowed:
            raise Fault('invalid_fields')
        ident(identity)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            row = db.execute('SELECT * FROM executive_records WHERE id=? AND scope=? AND actor=?', (identity, p['scope'], p['id'])).fetchone()
            if not row:
                raise Fault('executive_record_not_found', 404)
            if row['version'] != body['version']:
                raise Fault('executive_record_changed', 409)
            changes = {}
            if 'status' in body:
                if body['status'] not in STATUSES[row['kind']]:
                    raise Fault('invalid_status')
                changes['status'] = body['status']
            if 'title' in body:
                text(body['title'], 160); changes['title'] = body['title'].strip()
            if 'detail' in body:
                changes['detail'] = _multiline(body['detail'], 1200)
            if 'due' in body:
                if body['due'] is not None:
                    timestamp(body['due'])
                changes['due'] = body['due']
            if 'rank' in body:
                if body['rank'] is not None and (type(body['rank']) is not int or not 1 <= body['rank'] <= 1000):
                    raise Fault('invalid_rank')
                changes['rank'] = body['rank']
            if not changes:
                raise Fault('nothing_to_change')
            assignments = ','.join(f'{k}=?' for k in changes)
            db.execute(f'UPDATE executive_records SET {assignments},version=version+1,updated=? WHERE id=?',
                       (*changes.values(), self.store.now(), identity))
            self.store.log(db, p['scope'], p['id'], 'executive.updated', identity)
            return self._one(db, p, identity)

    def accept_recommendation(self, bearer, body):
        """Turn one current recommendation into a priority the person owns."""
        exact(body, {'request_id', 'from_record', 'from_version'})
        ident(body['request_id']); ident(body['from_record'])
        view = self.view(bearer)
        match = next((r for r in view['recommendations'] if r['from_record'] == body['from_record']), None)
        if not match or match['from_version'] != body['from_version']:
            raise Fault('recommendation_not_current', 409)
        record = next(r for r in view['records'] if r['id'] == body['from_record'])
        return self.create(bearer, {'request_id': body['request_id'], 'kind': 'priority', 'title': record['title'],
                                    'detail': f"Accepted from the recommendation: {match['reason']}",
                                    'project': record['project'], 'due': record['due'], 'rank': None, 'support': None},
                           derived_from=record['id'])

    # Reads ---------------------------------------------------------------

    def _record(self, db, p, row, now):
        support = self._support_view(db, p, json.loads(row['support'])) if row['support'] else None
        return {'id': row['id'], 'kind': row['kind'], 'title': row['title'], 'detail': row['detail'], 'status': row['status'],
                'open': row['status'] in OPEN, 'project': row['project'], 'due': row['due'],
                'overdue': bool(row['due'] is not None and row['due'] < now and row['status'] in OPEN),
                'rank': row['rank'], 'origin': row['origin'], 'derived_from': row['derived_from'], 'version': row['version'],
                'created': row['created'], 'updated': row['updated'], 'support': support,
                'basis': 'user_authored_record_not_verified_fact', 'authority_granted': False}

    def _one(self, db, p, identity):
        row = db.execute('SELECT * FROM executive_records WHERE id=?', (identity,)).fetchone()
        return self._record(db, p, row, self.store.now())

    def view(self, bearer):
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            now = self.store.now()
            records = [self._record(db, p, r, now) for r in db.execute(
                'SELECT * FROM executive_records WHERE scope=? AND actor=? ORDER BY created,id', (p['scope'], p['id']))]
        priorities = sorted((r for r in records if r['kind'] == 'priority' and r['status'] != 'dropped'),
                            key=lambda r: (not r['open'], r['rank'] is None, r['rank'] or 0, r['created'], r['id']))
        progress = {}
        for r in records:
            if r['kind'] == 'milestone' and r['project'] and r['status'] != 'dropped':
                entry = progress.setdefault(r['project'], {'done': 0, 'total': 0})
                entry['total'] += 1
                entry['done'] += r['status'] == 'done'
        accepted = {r['derived_from'] for r in records if r['kind'] == 'priority' and r['status'] != 'dropped' and r['derived_from']}
        recommendations = []
        for r in records:
            if r['kind'] in ('commitment', 'follow_up') and r['open'] and r['due'] is not None and r['due'] <= now + RECOMMENDATION_WINDOW:
                reason = ('overdue ' if r['overdue'] else 'due within seven days ') + r['kind'].replace('_', '-')
                if r['id'] in accepted:
                    continue
                recommendations.append({'from_record': r['id'], 'from_version': r['version'], 'title': r['title'],
                                        'due': r['due'], 'reason': reason, 'rule': 'open commitment or follow-up due within 7 days',
                                        'basis': 'recommendation_not_obligation'})
        return {'records': records, 'priorities': priorities, 'recommendations': recommendations,
                'milestone_progress': [{'project': k, **v, 'basis': 'recorded_milestones_only'} for k, v in sorted(progress.items())],
                'actor_private': True, 'authority_granted': False}
