"""Executive records: goals, priorities, commitments, decisions, milestones, follow-ups (ATT-002).

Records are written by the person, actor-private like reviewed memory, and may cite
exact lines of an authored note. A cited line that later changes is flagged, never
silently trusted, and the record is kept. Project progress counts only recorded
milestones. Recommendations come from one stated rule and stay recommendations
until the person accepts one; nothing here becomes an obligation by inference, and
nothing here grants authority to act.

A responsible label is short text the person types. It may point at a person record
only when the person explicitly picks one; it is never read from note text, never
merged with a namesake and never an ALFRED account, identity or grant. Decision
options are authored. A choice, its rationale and its time are recorded only when the
person decides, and changing options afterwards needs an explicit reopen. Nothing
scores or ranks options. Briefs, attention items and insights are computed on request
from records and sources the caller may read at that moment, are labelled as assembled
or derived, and are never stored as facts.
"""
from __future__ import annotations
from itertools import combinations
import hashlib
import json
import re
import secrets
from .local import Fault, exact, ident, text, timestamp
from .policy import permitted

KINDS = ('goal', 'priority', 'commitment', 'decision', 'milestone', 'follow_up')
STATUSES = {'goal': ('active', 'achieved', 'dropped'), 'priority': ('open', 'done', 'dropped'),
            'commitment': ('open', 'done', 'dropped'), 'decision': ('proposed', 'decided', 'superseded'),
            'milestone': ('open', 'done', 'dropped'), 'follow_up': ('open', 'done', 'dropped')}
FIRST = {'goal': 'active', 'priority': 'open', 'commitment': 'open', 'decision': 'proposed',
         'milestone': 'open', 'follow_up': 'open'}
OPEN = {'active', 'open', 'proposed'}
DAY = 86400
RECOMMENDATION_WINDOW = 7 * DAY
STALE_MILESTONE = 14 * DAY
QUIET_PROJECT = 30 * DAY
DEADLINE_CLASH = 2 * DAY
MAX_SNOOZE = 366 * DAY
MAX_RECORDS = 512
MAX_HISTORY = 128
BRIEF_KINDS = ('decision', 'milestone', 'commitment')
PEOPLE = ('person', 'organisation')
PROJECT = re.compile(r'(note):([0-9a-f]{24})|(entity):([A-Za-z0-9][A-Za-z0-9_.-]{0,79})')
BASE_FIELDS = {'request_id', 'kind', 'title', 'detail', 'project', 'due', 'rank', 'support'}
OPTIONAL_FIELDS = {'responsible', 'responsible_link', 'options'}
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
# Version 2 adds the responsible label, decision options and choice, snooze, and two
# append-only trails: milestone progress and decision events. Existing rows keep NULLs.
MIGRATE_2 = (
    'ALTER TABLE executive_records ADD COLUMN responsible TEXT',
    'ALTER TABLE executive_records ADD COLUMN responsible_ref TEXT',
    'ALTER TABLE executive_records ADD COLUMN options TEXT',
    'ALTER TABLE executive_records ADD COLUMN chosen TEXT',
    'ALTER TABLE executive_records ADD COLUMN rationale TEXT',
    'ALTER TABLE executive_records ADD COLUMN decided_at INTEGER',
    'ALTER TABLE executive_records ADD COLUMN snoozed_until INTEGER',
    '''CREATE TABLE IF NOT EXISTS executive_progress(
 record TEXT NOT NULL REFERENCES executive_records(id), seq INTEGER NOT NULL, kind TEXT NOT NULL,
 note TEXT, status TEXT, at INTEGER NOT NULL, PRIMARY KEY(record,seq))''',
    '''CREATE TABLE IF NOT EXISTS executive_decisions(
 record TEXT NOT NULL REFERENCES executive_records(id), seq INTEGER NOT NULL, event TEXT NOT NULL,
 option_id TEXT, option_label TEXT, rationale TEXT, at INTEGER NOT NULL, PRIMARY KEY(record,seq))''',
    'UPDATE executive_meta SET version=2',
)
ATTENTION_RULES = (
    {'id': 'overdue', 'rule': 'An open record whose due date has passed.'},
    {'id': 'decision_past_due', 'rule': 'A proposed decision whose due date has passed.'},
    {'id': 'due_soon', 'rule': 'An open commitment or follow-up due within the next seven days.'},
    {'id': 'stale_milestone', 'rule': 'An open milestone with no creation, progress note or status change in the last 14 days.'},
)
ATTENTION_REASONS = {'overdue': 'Past its due date', 'decision_past_due': 'Decision still open past its due date',
                     'due_soon': 'Due within seven days', 'stale_milestone': 'No recorded progress for 14 days'}
INSIGHT_RULES = (
    {'id': 'responsible_overdue_across_projects',
     'rule': 'One responsible label, with the same explicit link or none, holds overdue open records in two or more currently available projects.'},
    {'id': 'top_priorities_deadline_clash', 'rule': 'Two of the top three open priorities are due within two days of each other.'},
    {'id': 'commitments_without_milestone',
     'rule': 'A currently available project has had open commitments for at least 30 days and no milestone created or progressed in the last 30 days.'},
)


def _multiline(value, limit):
    """Printable text with newlines and tabs; empty allowed."""
    if not isinstance(value, str) or len(value) > limit:
        raise Fault('invalid_text')
    if any((ord(c) < 32 and c not in '\n\t') or 127 <= ord(c) < 160 for c in value):
        raise Fault('control_character')
    return value.strip()


def _line(value, limit, code):
    """One line of authored text with runs of spaces collapsed. Never empty."""
    if not isinstance(value, str):
        raise Fault(code)
    text(value, limit)
    value = ' '.join(value.split())
    if not value:
        raise Fault(code)
    return value


def _project(value):
    if value is None:
        return None
    match = PROJECT.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise Fault('invalid_project_reference')
    return value


def _responsible(value):
    return None if value is None else _line(value, 80, 'invalid_responsible')


def _link(value):
    if value is None:
        return None
    if not isinstance(value, str) or not PROJECT.fullmatch(value):
        raise Fault('invalid_responsible_link')
    return value


def _points(value):
    if value is None:
        return []
    if type(value) is not list or len(value) > 4:
        raise Fault('invalid_option_points')
    return [_line(item, 120, 'invalid_option_points') for item in value]


def _options(value):
    """Two to six authored options, kept in the order given. No scores, no ranking."""
    if value is None:
        return None
    if type(value) is not list or not 2 <= len(value) <= 6:
        raise Fault('invalid_decision_options')
    result, seen = [], set()
    for position, option in enumerate(value, 1):
        if type(option) is not dict or not {'label'} <= set(option) <= {'label', 'notes', 'pros', 'cons'}:
            raise Fault('invalid_decision_option')
        label = _line(option['label'], 120, 'invalid_decision_option')
        if label.casefold() in seen:
            raise Fault('duplicate_option_label')
        seen.add(label.casefold())
        notes = option.get('notes')
        result.append({'id': f'o{position}', 'label': label, 'notes': '' if notes is None else _multiline(notes, 500),
                       'pros': _points(option.get('pros')), 'cons': _points(option.get('cons'))})
    return result


def _excerpt(body, limit=280):
    """The first prose line of a note, exactly as written, with its line number."""
    lines = body.splitlines()
    start = 0
    if lines and lines[0].strip() == '---':
        closing = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == '---'), None)
        start = closing + 1 if closing is not None else len(lines)
    for number, line in enumerate(lines[start:], start + 1):
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            return number, line[:limit], len(line) > limit
    return None, '', False


class ExecutiveRecords:
    def __init__(self, store):
        self.store = store
        with store.connection() as db:
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
        with store.transaction() as db:
            versions = [r[0] for r in db.execute('SELECT version FROM executive_meta')]
            if versions == [1]:
                for statement in MIGRATE_2:
                    db.execute(statement)
                versions = [2]
            if versions != [2]:
                raise Fault('unsupported_executive_version')

    # Lookups -------------------------------------------------------------

    def _resolver(self, db, p, now):
        """Whether a linked note or entity is visible to this caller now, and its name if so."""
        cache = {}
        entities = bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_entities'").fetchone())
        def resolve(ref):
            if ref not in cache:
                kind, _, key = ref.partition(':')
                found = None
                if kind == 'entity' and entities:
                    row = db.execute('SELECT id,kind,name FROM memory_entities WHERE id=? AND scope=? AND actor=?',
                                     (key, p['scope'], p['id'])).fetchone()
                    if row:
                        found = {'ref': ref, 'name': row['name'], 'kind': row['kind'], 'origin': 'reviewed_entity'}
                elif kind == 'note':
                    row = db.execute('''SELECT n.* FROM knowledge_notes n JOIN knowledge_sources s ON s.scope=n.scope AND s.source=n.source
                        WHERE n.scope=? AND n.id=? AND n.status='ready' AND s.status IN ('ready','attention')''', (p['scope'], key)).fetchone()
                    if row and permitted(db, p, row['source'], now):
                        found = {'ref': ref, 'name': row['title'], 'kind': row['kind'], 'origin': 'authored_note', 'note': dict(row)}
                cache[ref] = found
            return cache[ref]
        return resolve

    def _context(self, db, p, now, record=None):
        """Shared lookups for every record view assembled in one transaction."""
        where, args = ('r.scope=? AND r.actor=?', (p['scope'], p['id'])) if record is None else ('r.id=?', (record,))
        progress, decisions = {}, {}
        for row in db.execute(f'SELECT g.* FROM executive_progress g JOIN executive_records r ON r.id=g.record WHERE {where} ORDER BY g.record,g.seq', args).fetchall():
            progress.setdefault(row['record'], []).append(dict(row))
        for row in db.execute(f'SELECT d.* FROM executive_decisions d JOIN executive_records r ON r.id=d.record WHERE {where} ORDER BY d.record,d.seq', args).fetchall():
            decisions.setdefault(row['record'], []).append(dict(row))
        return {'now': now, 'resolve': self._resolver(db, p, now), 'progress': progress, 'decisions': decisions}

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
        flagged = {'note_id': support['note_id'], 'start_line': support['start_line'], 'end_line': support['end_line'], 'quote': None}
        now = self.store.now()
        note = db.execute('''SELECT n.status,n.source,s.status AS source_status FROM knowledge_notes n
            JOIN knowledge_sources s ON s.scope=n.scope AND s.source=n.source WHERE n.scope=? AND n.id=?''', (p['scope'], support['note_id'])).fetchone()
        # Not readable by this caller now: say only that, never whether the text changed.
        if not note or not permitted(db, p, note['source'], now) or (note['status'] != 'missing' and (
                note['status'] != 'ready' or note['source_status'] not in ('ready', 'attention'))):
            return {**flagged, 'state': 'unavailable'}
        try:
            current = ReviewedMemory._source(db, p['scope'], ref, now, p)
        except Fault:
            # Edited, renamed or removed: a durable change that needs checking against the source.
            return {**flagged, 'state': 'changed'}
        if current['quote_hash'] != support['quote_hash']:
            return {**flagged, 'state': 'changed'}
        return {'note_id': current['note_id'], 'path': current['path'], 'title': current['title'], 'revision': current['revision'],
                'start_line': current['start_line'], 'end_line': current['end_line'], 'quote': current['quote'], 'state': 'current'}

    # Writes --------------------------------------------------------------

    def create(self, bearer, body, *, derived_from=None):
        if type(body) is not dict or not BASE_FIELDS <= set(body) <= BASE_FIELDS | OPTIONAL_FIELDS:
            raise Fault('invalid_fields')
        ident(body['request_id']); text(body['title'], 160); _multiline(body['detail'], 1200)
        if body['kind'] not in KINDS:
            raise Fault('invalid_executive_kind')
        project = _project(body['project'])
        if body['due'] is not None:
            timestamp(body['due'])
        if body['rank'] is not None and (type(body['rank']) is not int or not 1 <= body['rank'] <= 1000):
            raise Fault('invalid_rank')
        responsible, link = _responsible(body.get('responsible')), _link(body.get('responsible_link'))
        if link is not None and responsible is None:
            raise Fault('responsible_label_required')
        options = _options(body.get('options'))
        if options is not None and body['kind'] != 'decision':
            raise Fault('options_only_for_decisions')
        # Optional fields join the request hash only when set, so earlier requests replay unchanged.
        digest = hashlib.sha256(json.dumps({k: v for k, v in body.items() if k in BASE_FIELDS or v is not None},
                                           sort_keys=True).encode()).hexdigest()
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
            if link is not None:
                self._check_responsible(db, p, link)
            support = self._bind_support(db, p, body['support']) if body['support'] is not None else None
            rid = 'exec-' + secrets.token_hex(12); now = self.store.now()
            db.execute('''INSERT INTO executive_records(id,scope,actor,request_id,request_hash,kind,title,detail,status,project,due,rank,
                support,origin,derived_from,version,created,updated,responsible,responsible_ref,options) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (rid, p['scope'], p['id'], body['request_id'], digest, body['kind'], body['title'].strip(), body['detail'].strip(),
                        FIRST[body['kind']], project, body['due'], body['rank'], json.dumps(support) if support else None,
                        'accepted_recommendation' if derived_from else 'user_authored', derived_from, 1, now, now,
                        responsible, link, json.dumps(options) if options else None))
            self.store.log(db, p['scope'], p['id'], 'executive.created', rid)
            return self._one(db, p, rid)

    def _check_project(self, db, p, project):
        """A project link must point at a record this person can currently see."""
        if project is not None and not self._resolver(db, p, self.store.now())(project):
            raise Fault('project_not_available', 404)

    def _check_responsible(self, db, p, link):
        """An explicitly picked person record this caller can see now. Unknown and hidden look alike."""
        target = self._resolver(db, p, self.store.now())(link)
        if not target:
            raise Fault('responsible_not_available', 404)
        if target['kind'] not in PEOPLE:
            raise Fault('responsible_not_a_person')

    def _owned(self, db, bearer, identity, version):
        ident(identity)
        if type(version) is not int or version < 1:
            raise Fault('invalid_version')
        p = self.store.authenticate(db, bearer, {'owner'})
        row = db.execute('SELECT * FROM executive_records WHERE id=? AND scope=? AND actor=?', (identity, p['scope'], p['id'])).fetchone()
        if not row:
            raise Fault('executive_record_not_found', 404)
        if row['version'] != version:
            raise Fault('executive_record_changed', 409)
        return p, row

    def _trail(self, db, table, identity, values):
        """Append one entry to a record's progress or decision trail."""
        seq = db.execute(f'SELECT coalesce(max(seq),0) FROM {table} WHERE record=?', (identity,)).fetchone()[0]
        if seq >= MAX_HISTORY:
            raise Fault('executive_history_capacity', 409)
        marks = ','.join('?' * (len(values) + 2))
        db.execute(f'INSERT INTO {table} VALUES ({marks})', (identity, seq + 1, *values))

    def _commit(self, db, p, identity, changes, event):
        assignments = ''.join(f'{k}=?,' for k in changes)
        db.execute(f'UPDATE executive_records SET {assignments}version=version+1,updated=? WHERE id=?',
                   (*changes.values(), self.store.now(), identity))
        self.store.log(db, p['scope'], p['id'], event, identity)
        return self._one(db, p, identity)

    def update(self, bearer, identity, body):
        allowed = {'version', 'status', 'title', 'detail', 'due', 'rank', 'responsible', 'responsible_link', 'snoozed_until'}
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
            changes, now = {}, self.store.now()
            if 'status' in body:
                if body['status'] not in STATUSES[row['kind']]:
                    raise Fault('invalid_status')
                if body['status'] != row['status']:
                    self._status_trail(db, row, body['status'], changes, now)
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
            if 'responsible' in body:
                changes['responsible'] = _responsible(body['responsible'])
                if changes['responsible'] is None and 'responsible_link' not in body:
                    changes['responsible_ref'] = None
            if 'responsible_link' in body:
                link = _link(body['responsible_link'])
                if link is not None:
                    if changes.get('responsible', row['responsible']) is None:
                        raise Fault('responsible_label_required')
                    self._check_responsible(db, p, link)
                changes['responsible_ref'] = link
            if 'snoozed_until' in body:
                until = body['snoozed_until']
                if until is not None and not now < timestamp(until) <= now + MAX_SNOOZE:
                    raise Fault('invalid_snooze')
                changes['snoozed_until'] = until
            if not changes:
                raise Fault('nothing_to_change')
            return self._commit(db, p, identity, changes, 'executive.updated')

    def _status_trail(self, db, row, status, changes, now):
        """Status changes that carry meaning beyond the status itself leave a trail."""
        if row['kind'] == 'milestone':
            self._trail(db, 'executive_progress', row['id'], ('status', None, status, now))
        if row['kind'] != 'decision':
            return
        if row['options'] is not None and status == 'decided':
            raise Fault('decision_choice_required', 409)
        if row['status'] != 'proposed' and status == 'proposed' and (row['options'] is not None or row['chosen'] is not None):
            raise Fault('decision_reopen_required', 409)
        if status == 'decided':
            changes.update(decided_at=now)
            self._trail(db, 'executive_decisions', row['id'], ('decided', None, None, None, now))
        elif status == 'proposed':
            changes.update(decided_at=None, rationale=None, chosen=None)
            self._trail(db, 'executive_decisions', row['id'], ('reopened', None, None, None, now))

    def set_options(self, bearer, identity, body):
        """Replace a proposed decision's options. A decided one must be reopened first."""
        exact(body, {'version', 'options'})
        options = _options(body['options'])
        with self.store.transaction() as db:
            p, row = self._owned(db, bearer, identity, body['version'])
            if row['kind'] != 'decision':
                raise Fault('options_only_for_decisions')
            if row['status'] != 'proposed':
                raise Fault('decision_reopen_required', 409)
            return self._commit(db, p, identity, {'options': json.dumps(options) if options else None}, 'executive.options_set')

    def decide(self, bearer, identity, body):
        """Record the person's choice, rationale and time. Only on an explicit request."""
        exact(body, {'version', 'option', 'rationale'})
        rationale = _multiline(body['rationale'], 1200)
        if not rationale:
            raise Fault('rationale_required')
        with self.store.transaction() as db:
            p, row = self._owned(db, bearer, identity, body['version'])
            if row['kind'] != 'decision':
                raise Fault('not_a_decision')
            if row['status'] != 'proposed':
                raise Fault('decision_not_open', 409)
            options = json.loads(row['options']) if row['options'] else []
            chosen = next((o for o in options if o['id'] == body['option']), None)
            if (options and chosen is None) or (not options and body['option'] is not None):
                raise Fault('unknown_decision_option')
            now = self.store.now()
            self._trail(db, 'executive_decisions', identity, ('decided', body['option'], chosen['label'] if chosen else None, rationale, now))
            return self._commit(db, p, identity, {'status': 'decided', 'chosen': body['option'], 'rationale': rationale, 'decided_at': now},
                                'executive.decided')

    def reopen(self, bearer, identity, body):
        """Return a decided or superseded decision to proposed; the earlier choice stays in its trail."""
        exact(body, {'version'})
        with self.store.transaction() as db:
            p, row = self._owned(db, bearer, identity, body['version'])
            if row['kind'] != 'decision':
                raise Fault('not_a_decision')
            if row['status'] == 'proposed':
                raise Fault('decision_not_closed', 409)
            options = {o['id']: o['label'] for o in json.loads(row['options'])} if row['options'] else {}
            self._trail(db, 'executive_decisions', identity, ('reopened', row['chosen'], options.get(row['chosen']), None, self.store.now()))
            return self._commit(db, p, identity, {'status': 'proposed', 'chosen': None, 'rationale': None, 'decided_at': None},
                                'executive.reopened')

    def add_progress(self, bearer, identity, body):
        """An authored progress note on an open milestone; the defined input for staleness."""
        exact(body, {'version', 'note'})
        note = _line(body['note'], 400, 'invalid_progress_note')
        with self.store.transaction() as db:
            p, row = self._owned(db, bearer, identity, body['version'])
            if row['kind'] != 'milestone':
                raise Fault('progress_only_for_milestones')
            if row['status'] != 'open':
                raise Fault('milestone_not_open', 409)
            self._trail(db, 'executive_progress', identity, ('note', note, None, self.store.now()))
            return self._commit(db, p, identity, {}, 'executive.progress')

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

    def _record(self, db, p, row, ctx):
        now, resolve = ctx['now'], ctx['resolve']
        support = self._support_view(db, p, json.loads(row['support'])) if row['support'] else None
        project = resolve(row['project']) if row['project'] else None
        person = resolve(row['responsible_ref']) if row['responsible_ref'] else None
        view = {'id': row['id'], 'kind': row['kind'], 'title': row['title'], 'detail': row['detail'], 'status': row['status'],
                'open': row['status'] in OPEN, 'project': row['project'], 'due': row['due'],
                'overdue': bool(row['due'] is not None and row['due'] < now and row['status'] in OPEN),
                'rank': row['rank'], 'origin': row['origin'], 'derived_from': row['derived_from'], 'version': row['version'],
                'created': row['created'], 'updated': row['updated'], 'support': support,
                'project_state': None if row['project'] is None else 'current' if project else 'unavailable',
                'project_name': project['name'] if project else None,
                'responsible': row['responsible'], 'responsible_link': row['responsible_ref'],
                'responsible_state': None if row['responsible_ref'] is None else 'current' if person else 'unavailable',
                'responsible_name': person['name'] if person else None,
                'snoozed_until': row['snoozed_until'],
                'snoozed': bool(row['snoozed_until'] is not None and row['snoozed_until'] > now),
                'basis': 'user_authored_record_not_verified_fact', 'authority_granted': False}
        if row['kind'] == 'decision':
            options = json.loads(row['options']) if row['options'] else []
            chosen = next((o for o in options if o['id'] == row['chosen']), None)
            view['options'] = options
            view['choice'] = None if row['status'] != 'decided' and row['decided_at'] is None else {
                'option': row['chosen'], 'label': chosen['label'] if chosen else None,
                'rationale': row['rationale'], 'decided_at': row['decided_at']}
            view['decision_history'] = [{'event': d['event'], 'option': d['option_id'], 'label': d['option_label'],
                                         'rationale': d['rationale'], 'at': d['at']} for d in ctx['decisions'].get(row['id'], [])[-10:]]
        if row['kind'] == 'milestone':
            entries = ctx['progress'].get(row['id'], [])
            view['progress'] = [{'kind': e['kind'], 'note': e['note'], 'status': e['status'], 'at': e['at']} for e in reversed(entries[-6:])]
            view['last_progress_at'] = max([row['created']] + [e['at'] for e in entries])
        return view

    def _one(self, db, p, identity):
        row = db.execute('SELECT * FROM executive_records WHERE id=?', (identity,)).fetchone()
        return self._record(db, p, row, self._context(db, p, self.store.now(), identity))

    def _records(self, db, p, now):
        ctx = self._context(db, p, now)
        rows = db.execute('SELECT * FROM executive_records WHERE scope=? AND actor=? ORDER BY created,id', (p['scope'], p['id'])).fetchall()
        return [self._record(db, p, r, ctx) for r in rows], ctx

    def view(self, bearer):
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            now = self.store.now()
            records, ctx = self._records(db, p, now)
            return self._summarise(records, now, ctx['resolve'])

    @staticmethod
    def _summarise(records, now, resolve):
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
                # Accepted, or snoozed by the person: not recommended again until the snooze ends.
                if r['id'] in accepted or r['snoozed']:
                    continue
                recommendations.append({'from_record': r['id'], 'from_version': r['version'], 'title': r['title'],
                                        'due': r['due'], 'reason': reason, 'rule': 'open commitment or follow-up due within 7 days',
                                        'basis': 'recommendation_not_obligation'})
        return {'records': records, 'priorities': priorities, 'recommendations': recommendations,
                'milestone_progress': [{'project': k, **v, 'basis': 'recorded_milestones_only'} for k, v in sorted(progress.items())],
                'attention': attention(records, now), 'insights': insights(records, priorities, now, resolve),
                'responsible_groups': responsible_groups(records),
                'actor_private': True, 'authority_granted': False}

    def brief(self, bearer, identity):
        """Assemble a preparation brief from what this caller may read now. Computed, never stored."""
        ident(identity)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            row = db.execute('SELECT kind FROM executive_records WHERE id=? AND scope=? AND actor=?', (identity, p['scope'], p['id'])).fetchone()
            if not row:
                raise Fault('executive_record_not_found', 404)
            if row['kind'] not in BRIEF_KINDS:
                raise Fault('brief_kind_not_supported')
            now = self.store.now()
            records, ctx = self._records(db, p, now)
            record = next(r for r in records if r['id'] == identity)
            return assemble_brief(db, p, now, record, records, ctx)


# Derived views. Pure functions over record views already filtered for this caller. ---

def _cite(record):
    return {'record': record['id'], 'version': record['version']}


def attention(records, now):
    """Due, overdue and stale items by the stated rules. In-app only: nothing is delivered anywhere."""
    items, snoozed = [], []
    for r in records:
        if not r['open']:
            continue
        rules = []
        if r['due'] is not None and r['due'] < now:
            rules.append('decision_past_due' if r['kind'] == 'decision' else 'overdue')
        elif r['kind'] in ('commitment', 'follow_up') and r['due'] is not None and r['due'] <= now + RECOMMENDATION_WINDOW:
            rules.append('due_soon')
        if r['kind'] == 'milestone' and now - r['last_progress_at'] >= STALE_MILESTONE:
            rules.append('stale_milestone')
        if not rules:
            continue
        item = {'record': r['id'], 'version': r['version'], 'kind': r['kind'], 'title': r['title'], 'rules': rules,
                'reason': ATTENTION_REASONS[rules[0]], 'due': r['due'],
                'project': r['project'] if r['project_state'] == 'current' else None, 'project_name': r['project_name'],
                'responsible': r['responsible'], 'last_progress_at': r.get('last_progress_at'),
                'snoozed_until': r['snoozed_until'], 'cite': _cite(r)}
        (snoozed if r['snoozed'] else items).append(item)
    order = {rule['id']: i for i, rule in enumerate(ATTENTION_RULES)}
    items.sort(key=lambda i: (order[i['rules'][0]], i['due'] if i['due'] is not None else 2**53, i['record']))
    snoozed.sort(key=lambda i: (i['snoozed_until'], i['record']))
    return {'items': items, 'snoozed': snoozed, 'rules': list(ATTENTION_RULES),
            'basis': 'computed_on_request_from_your_records', 'delivery': 'in_app_only'}


def _group_key(r):
    return (r['responsible'], r['responsible_link'])


def responsible_groups(records):
    """Group by the exact label and explicit link together; namesakes are never combined."""
    groups, unassigned = {}, []
    for r in records:
        if r['responsible'] is None:
            if r['open']:
                unassigned.append(r['id'])
            continue
        entry = groups.setdefault(_group_key(r), {'label': r['responsible'], 'link': r['responsible_link'],
                                                  'link_state': r['responsible_state'], 'link_name': r['responsible_name'],
                                                  'records': [], 'open': 0, 'overdue': 0})
        entry['records'].append(r['id'])
        entry['open'] += r['open']
        entry['overdue'] += r['overdue']
    ordered = sorted(groups.values(), key=lambda g: (g['label'].casefold(), g['label'], g['link'] or ''))
    return {'groups': ordered, 'unassigned_open': unassigned, 'basis': 'your_labels_not_identities'}


def insights(records, priorities, now, resolve):
    """Deterministic, labelled derivations linking to the records they come from. Never stored or accepted."""
    found = []
    def add(rule, statement, used, projects=()):
        found.append({'rule': rule, 'statement': statement,
                      'records': [{'id': r['id'], 'version': r['version'], 'title': r['title'], 'kind': r['kind']} for r in used],
                      'projects': [{'ref': ref, 'name': resolve(ref)['name']} for ref in projects],
                      'basis': 'derived_from_your_records_not_accepted_fact', 'stored': False})
    overdue = {}
    for r in records:
        # Only projects the caller can currently see may contribute.
        if r['open'] and r['overdue'] and r['responsible'] and r['project_state'] == 'current':
            overdue.setdefault(_group_key(r), []).append(r)
    for (label, _), used in sorted(overdue.items(), key=lambda item: (item[0][0].casefold(), item[0][0], item[0][1] or '')):
        projects = sorted({r['project'] for r in used})
        if len(projects) >= 2:
            add('responsible_overdue_across_projects', f'"{label}" holds overdue records in {len(projects)} projects.', used, projects)
    top = [r for r in priorities if r['open']][:3]
    for a, b in combinations([r for r in top if r['due'] is not None], 2):
        if abs(a['due'] - b['due']) <= DEADLINE_CLASH:
            add('top_priorities_deadline_clash', f'Top priorities "{a["title"]}" and "{b["title"]}" are due within two days of each other.', [a, b])
    projects = {}
    for r in records:
        if r['project_state'] != 'current':
            continue
        entry = projects.setdefault(r['project'], {'commitments': [], 'activity': None})
        if r['kind'] == 'commitment' and r['status'] == 'open':
            entry['commitments'].append(r)
        if r['kind'] == 'milestone' and r['status'] != 'dropped':
            entry['activity'] = max(entry['activity'] or 0, r['last_progress_at'])
    for ref, entry in sorted(projects.items()):
        if (entry['commitments'] and now - min(c['created'] for c in entry['commitments']) >= QUIET_PROJECT
                and (entry['activity'] is None or now - entry['activity'] >= QUIET_PROJECT)):
            add('commitments_without_milestone',
                f'"{resolve(ref)["name"]}" has open commitments but no milestone created or progressed in 30 days.', entry['commitments'], [ref])
    return {'items': found, 'rules': list(INSIGHT_RULES), 'basis': 'derived_from_your_records_not_accepted_fact', 'stored': False}


def assemble_brief(db, p, now, record, records, ctx):
    """Every item cites its record, note revision or reviewed statement. Not advice, not model output."""
    resolve, questions = ctx['resolve'], []
    def ask(code, message):
        questions.append({'code': code, 'text': message, 'cite': _cite(record)})
    notes = []
    project = resolve(record['project']) if record['project'] else None
    if project and project['origin'] == 'authored_note':
        note = project['note']
        line, excerpt, truncated = _excerpt(note['body'])
        notes.append({'role': 'project', 'state': 'current', 'note_id': note['id'], 'title': note['title'], 'path': note['path'],
                      'revision': note['revision'], 'sha256': note['sha256'], 'start_line': line, 'end_line': line,
                      'excerpt': excerpt, 'truncated': truncated,
                      'cite': {'note': note['id'], 'revision': note['revision'], 'lines': [line, line] if line else []}})
    support = record['support']
    if support and support['state'] == 'current':
        notes.append({'role': 'cited_support', 'state': 'current', 'note_id': support['note_id'], 'title': support['title'],
                      'path': support['path'], 'revision': support['revision'], 'start_line': support['start_line'],
                      'end_line': support['end_line'], 'excerpt': support['quote'], 'truncated': False,
                      'cite': {'note': support['note_id'], 'revision': support['revision'], 'lines': [support['start_line'], support['end_line']]}})
    elif support:
        notes.append({'role': 'cited_support', 'state': support['state'], 'note_id': support['note_id'], 'excerpt': None,
                      'start_line': support['start_line'], 'end_line': support['end_line']})
        ask('support_' + support['state'], 'The cited lines have changed since this record was written.' if support['state'] == 'changed'
            else 'The cited lines are not currently available to you.')
    statements, hidden = _brief_statements(db, p, now, record, notes, resolve, ask)
    related, progress = [], None
    if project:
        for r in sorted(records, key=lambda r: (r['due'] is None, r['due'] or 0, r['created'], r['id'])):
            if r['id'] != record['id'] and r['project'] == record['project'] and r['kind'] in ('commitment', 'follow_up') and r['open']:
                related.append({'id': r['id'], 'version': r['version'], 'kind': r['kind'], 'title': r['title'], 'due': r['due'],
                                'overdue': r['overdue'], 'responsible': r['responsible'], 'cite': _cite(r)})
        milestones = [r for r in records if r['kind'] == 'milestone' and r['project'] == record['project'] and r['status'] != 'dropped']
    else:
        milestones = [record] if record['kind'] == 'milestone' else []
    if milestones:
        recent = sorted(((m, e) for m in milestones for e in ctx['progress'].get(m['id'], [])), key=lambda pair: (-pair[1]['at'], -pair[1]['seq'], pair[0]['id']))
        progress = {'project': record['project'] if project else None, 'done': sum(m['status'] == 'done' for m in milestones),
                    'total': len(milestones), 'basis': 'recorded_milestones_only',
                    'recent': [{'record': m['id'], 'title': m['title'], 'kind': e['kind'], 'note': e['note'], 'status': e['status'],
                                'at': e['at'], 'cite': _cite(m)} for m, e in recent[:6]]}
    if record['responsible'] is None:
        ask('no_responsible', 'No responsible label is recorded.')
    elif record['responsible_state'] == 'unavailable':
        ask('responsible_link_unavailable', 'The linked responsible record is not currently available to you.')
    if record['due'] is None:
        ask('no_due_date', 'No due date is recorded.')
    elif record['overdue']:
        ask('overdue', 'The due date has passed and the record is still open.')
    if record['project'] is None:
        ask('no_project', 'No project is linked, so related commitments and milestones cannot be gathered.')
    elif not project:
        ask('project_unavailable', 'The linked project is not currently available to you.')
    if record['kind'] == 'decision':
        if not record['options'] and record['status'] == 'proposed':
            ask('no_options', 'No options are recorded for this decision.')
        bare = [o['label'] for o in record['options'] if not o['notes']]
        if bare:
            ask('options_without_notes', 'Options without notes: ' + ', '.join(f'"{b}"' for b in bare) + '.')
        if record['status'] == 'decided' and not (record['choice'] or {}).get('rationale'):
            ask('no_rationale', 'This decision is marked decided without a recorded rationale.')
    if any(hidden.values()):
        ask('statements_not_shown', 'Reviewed statements about linked records not shown here: ' +
            ', '.join(f'{v} {k.replace("_", " ")}' for k, v in hidden.items() if v) + '.')
    return {'kind': 'assembled_brief', 'record': record, 'linked_notes': notes, 'statements': statements,
            'statements_not_shown': hidden, 'related': related[:12], 'progress': progress, 'questions': questions,
            'assembled_at': now, 'label': 'Assembled brief from your current records and permitted sources. Not advice and not model output.',
            'basis': 'assembled_from_current_permitted_records_not_advice', 'model_used': False, 'stored': False,
            'authority_granted': False}


def _brief_statements(db, p, now, record, notes, resolve, ask):
    """Accepted, current reviewed statements about linked records, by the reviewed-memory rule."""
    hidden = {'withheld': 0, 'conflicting': 0, 'outside_valid_period': 0, 'needing_fresh_review': 0, 'awaiting_review': 0, 'disputed': 0}
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_claims'").fetchone():
        return [], hidden
    from .reviewed_memory import ReviewedMemory
    linked = {ref.partition(':')[2] for ref in (record['project'], record['responsible_link'])
              if ref and ref.startswith('entity:') and resolve(ref)}
    cited = {n['note_id'] for n in notes if n['state'] == 'current'}
    entities = {r['id']: dict(r) for r in db.execute('SELECT id,kind,name FROM memory_entities WHERE scope=? AND actor=?', (p['scope'], p['id']))}
    for key in sorted(linked):
        e = entities[key]
        if any(x['id'] != key and (x['kind'], x['name'].casefold()) == (e['kind'], e['name'].casefold()) for x in entities.values()):
            ask('same_name_records', f'Another reviewed record is also named "{e["name"]}". They are kept separate.')
    statements = []
    # The one currentness rule shared by the reviewed-memory view, retrieval and final checks.
    for c in ReviewedMemory._claims(db, p, now):
        about = c['subject_id'] in linked or c['object_id'] in linked
        if not about and c['note_id'] not in cited:
            continue
        if not c['usable']:
            if about:
                # Counted, never shown: no value of an unusable statement leaves this function.
                reason = {'invalidated': 'needing_fresh_review', 'proposed': 'awaiting_review', 'disputed': 'disputed'}.get(c['state'])
                if c['state'] == 'accepted':
                    reason = ('conflicting' if c['conflicts'] else 'outside_valid_period' if c['source'] and not c['valid_now']
                              else 'needing_fresh_review' if ReviewedMemory._support_state(db, p['scope'], c) == 'changed' else 'withheld')
                if reason:
                    hidden[reason] += 1
            continue
        def entity(key):
            return {k: entities[key][k] for k in ('id', 'kind', 'name')} if key in entities else None
        source = c['source']
        statements.append({'claim_id': c['id'], 'version': c['version'], 'subject': entity(c['subject_id']), 'predicate': c['predicate'],
                           'object': entity(c['object_id']) if c['object_id'] else None, 'value': c['value'],
                           'why': 'about_linked_record' if about else 'supported_by_linked_note', 'reviewed': c['reviewed'],
                           'valid_from': c['valid_from'], 'valid_until': c['valid_until'],
                           'support': {k: source[k] for k in ('note_id', 'title', 'path', 'revision', 'start_line', 'end_line', 'quote')},
                           'basis': 'user_reviewed_statement_not_verified_fact',
                           'cite': {'claim': c['id'], 'version': c['version'], 'note': source['note_id'], 'revision': source['revision'],
                                    'lines': [source['start_line'], source['end_line']]}})
    statements.sort(key=lambda s: (-(s['reviewed'] or 0), s['claim_id']))
    return statements[:8], hidden
