"""Owner-authored automatic capture policies (MEM-004, M04, M10).

A capture policy is data the owner writes: which vaults and folder to read, one
deterministic line rule, and which reviewed-memory statement a matching line proposes.
No model runs. A rule matches indexed note text line by line; each match becomes an
ordinary reviewed-memory proposal bound to the exact note, revision, line and hash, so
it enters the existing review queue and nothing is ever accepted automatically.

Rules:
  line_prefix   a line (after an optional list bullet or task box) that starts with the
                given text, for example "Decision:"; the rest of the line is the value
  dated_line    an open line that holds a calendar date YYYY-MM-DD (optionally HH:MM)
                and, if given, a keyword; the value is "date[ time] rest of line", so the
                commitment review routine can read the date once the person accepts it

Frontmatter, fenced code and ticked tasks never match. A line is offered once per policy:
a rescan does not offer it again, and a dismissed (withdrawn or disputed) proposal is
not offered again while the line's text is the same. A proposal whose support was
invalidated before anyone dismissed it may be offered again against the new revision.

Each policy has a daily budget and the workspace has an overall one. Matches beyond a
budget are counted, never proposed; the next day's budget may propose them.

Workspace scope comes from the credential, so a policy never sees another workspace's
notes. The personal/company/client context is the owner's label for the policy; the
listed vaults decide which notes it reads. Policies are private to the owner who wrote
them, like the statements they propose.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import re
import threading
from .local import Fault, exact, ident, text
from .policy import ledger
from .reviewed_memory import MEMORY_TYPES, RELATIONS, ReviewedMemory

VERSION = 1
DAY = 86400
CONTEXTS = ('personal', 'company', 'client')
MATCH_KINDS = ('line_prefix', 'dated_line')
PREDICATES = tuple(k for k, v in RELATIONS.items() if not v['objects'])
FIELDS = {'version', 'name', 'enabled', 'context', 'match', 'sources', 'path_prefix', 'proposes', 'daily_budget'}
MAX_POLICIES, MAX_SOURCES, MAX_RULE_BUDGET, MAX_DAILY_BUDGET, DEFAULT_DAILY_BUDGET = 32, 8, 50, 200, 20
MAX_VALUE = 400
BULLET = re.compile(r'\s*(?:[-*+]|[0-9]{1,3}[.)])\s+')
TASK = re.compile(r'\[( |x|X)\]\s+')
ANCHOR = re.compile(r'\s+\^[A-Za-z0-9-]{1,64}$')
DATE = re.compile(r'(?<![0-9])([0-9]{4})-([0-9]{2})-([0-9]{2})(?:[T ]([01][0-9]|2[0-3]):([0-5][0-9]))?(?![0-9])')
PATH = re.compile(r'[A-Za-z0-9 _.-]{1,80}(?:/[A-Za-z0-9 _.-]{1,80}){0,7}/?')
NOT_PROPOSED = ('already_proposed', 'dismissed', 'forgotten', 'rule_budget', 'daily_budget', 'value_too_long',
                'source_changed', 'subject_unavailable', 'claim_capacity', 'refused')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS capture_policy_meta(version INTEGER NOT NULL);
INSERT INTO capture_policy_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM capture_policy_meta);
CREATE TABLE IF NOT EXISTS capture_policies(
 scope TEXT NOT NULL, actor TEXT NOT NULL, id TEXT NOT NULL, version INTEGER NOT NULL,
 enabled INTEGER NOT NULL, name TEXT NOT NULL, context TEXT NOT NULL, rule TEXT NOT NULL,
 created INTEGER NOT NULL, updated INTEGER NOT NULL, PRIMARY KEY(scope,actor,id));
CREATE TABLE IF NOT EXISTS capture_settings(
 scope TEXT NOT NULL, actor TEXT NOT NULL, daily_budget INTEGER NOT NULL, version INTEGER NOT NULL,
 updated INTEGER NOT NULL, last_run TEXT, PRIMARY KEY(scope,actor));
CREATE TABLE IF NOT EXISTS capture_proposals(
 scope TEXT NOT NULL, actor TEXT NOT NULL, claim_id TEXT NOT NULL, policy_id TEXT NOT NULL,
 policy_version INTEGER NOT NULL, note_id TEXT NOT NULL, revision INTEGER NOT NULL, line INTEGER NOT NULL,
 line_hash TEXT NOT NULL, day INTEGER NOT NULL, created INTEGER NOT NULL, PRIMARY KEY(scope,actor,claim_id));
CREATE INDEX IF NOT EXISTS capture_proposals_line ON capture_proposals(scope,actor,policy_id,note_id,line_hash);
CREATE TABLE IF NOT EXISTS capture_deferred(
 scope TEXT NOT NULL, actor TEXT NOT NULL, day INTEGER NOT NULL, policy_id TEXT NOT NULL, item TEXT NOT NULL,
 reason TEXT NOT NULL, PRIMARY KEY(scope,actor,day,policy_id,item));
'''


def _budget(value, high, code):
    if type(value) is not int or not 1 <= value <= high:
        raise Fault(code)
    return value


def _short(value, limit, code):
    if type(value) is not str:
        raise Fault(code)
    try:
        text(value, limit)
    except Fault:
        raise Fault(code) from None
    if value != value.strip() or not value:
        raise Fault(code)
    return value


def validate(body):
    """Normalise one authored policy. Every field is explicit; nothing is inferred."""
    exact(body, FIELDS)
    if type(body['version']) is not int or body['version'] < 0:
        raise Fault('invalid_version')
    if type(body['enabled']) is not bool:
        raise Fault('invalid_capture_policy')
    name = _short(body['name'], 80, 'invalid_capture_policy_name')
    if body['context'] not in CONTEXTS:
        raise Fault('invalid_capture_context')
    match = body['match']
    if type(match) is not dict or match.get('kind') not in MATCH_KINDS:
        raise Fault('invalid_capture_match')
    if match['kind'] == 'line_prefix':
        exact(match, {'kind', 'prefix'})
        match = {'kind': 'line_prefix', 'prefix': _short(match['prefix'], 40, 'invalid_capture_match')}
    else:
        exact(match, {'kind', 'keyword'})
        keyword = match['keyword']
        match = {'kind': 'dated_line', 'keyword': None if keyword is None else _short(keyword, 40, 'invalid_capture_match')}
    sources = body['sources']
    if type(sources) is not list or not 1 <= len(sources) <= MAX_SOURCES or len(set(map(str, sources))) != len(sources):
        raise Fault('invalid_capture_sources')
    for source in sources:
        ident(source)
    prefix = body['path_prefix']
    if prefix is not None and (type(prefix) is not str or not PATH.fullmatch(prefix) or '..' in prefix.split('/')
                               or any(part.strip() != part or part in ('', '.') for part in prefix.rstrip('/').split('/'))):
        raise Fault('invalid_capture_path')
    proposes = body['proposes']
    exact(proposes, {'subject_id', 'predicate', 'memory_type', 'retention_days'})
    ident(proposes['subject_id'])
    if proposes['predicate'] not in PREDICATES:
        raise Fault('invalid_capture_predicate')
    if proposes['memory_type'] not in MEMORY_TYPES:
        raise Fault('invalid_memory_type')
    days = proposes['retention_days']
    if days is not None and (type(days) is not int or not 1 <= days <= 3650):
        raise Fault('invalid_retention')
    return {'name': name, 'enabled': body['enabled'], 'context': body['context'],
            'rule': {'match': match, 'sources': sorted(sources), 'path_prefix': prefix,
                     'proposes': dict(proposes),
                     'daily_budget': _budget(body['daily_budget'], MAX_RULE_BUDGET, 'invalid_capture_budget')}}


def describe(name, rule, subject):
    """A plain sentence stating exactly what the rule does, for inspection."""
    match = rule['match']
    if match['kind'] == 'line_prefix':
        what = f'A line starting "{match["prefix"]}"'
    else:
        what = 'An open line with a date' + (f' and the word "{match["keyword"]}"' if match['keyword'] else '')
    where = ', '.join(rule['sources']) + (f' under "{rule["path_prefix"]}"' if rule['path_prefix'] else '')
    proposes = rule['proposes']
    return (f'{what} in notes from {where} proposes a {proposes["memory_type"]} statement '
            f'"{subject} {proposes["predicate"].replace("_", " ")} ..." for your review. Nothing is accepted automatically.')


def content_lines(body):
    """(line number, text) for lines a rule may read: not frontmatter, not fenced code."""
    lines = body.splitlines()
    start = 0
    if lines and lines[0].strip() == '---':
        end = next((i for i in range(1, min(len(lines), 81)) if lines[i].strip() == '---'), None)
        start = end + 1 if end is not None else len(lines)
    fenced = False
    for index in range(start, len(lines)):
        line = lines[index]
        if line.lstrip().startswith(('```', '~~~')):
            fenced = not fenced
            continue
        if not fenced:
            yield index + 1, line


def _strip(line):
    """Remove a list bullet and report a task box: (text, ticked)."""
    rest = line
    bullet = BULLET.match(rest)
    if bullet:
        rest = rest[bullet.end():]
    ticked = False
    task = TASK.match(rest) if bullet else None
    if task:
        ticked = task[1] in 'xX'
        rest = rest[task.end():]
    return ANCHOR.sub('', rest.strip()).strip(), ticked


def match_line(match, line):
    """The proposed value for one line, or None. Deterministic; case-insensitive prefix."""
    rest, ticked = _strip(line)
    if not rest:
        return None
    if match['kind'] == 'line_prefix':
        prefix = match['prefix']
        if not rest.casefold().startswith(prefix.casefold()):
            return None
        value = rest[len(prefix):].strip()
        return value or None
    if ticked:
        return None
    if match['keyword'] and not re.search(r'(?<!\w)' + re.escape(match['keyword']) + r'(?!\w)', rest, re.I):
        return None
    found = DATE.search(rest)
    if not found:
        return None
    try:
        datetime(int(found[1]), int(found[2]), int(found[3]), tzinfo=timezone.utc)
    except ValueError:
        return None
    when = f'{found[1]}-{found[2]}-{found[3]}' + (f' {found[4]}:{found[5]}' if found[4] else '')
    remainder = ' '.join((rest[:found.start()] + ' ' + rest[found.end():]).split()).strip(' :-,;')
    return f'{when} {remainder}' if remainder else None


def _line_hash(line):
    return hashlib.sha256(line.encode()).hexdigest()


class CapturePolicies:
    def __init__(self, store, supervisor=None, memory=None):
        self.store, self.supervisor = store, supervisor
        self.memory = memory or ReviewedMemory(store)
        self.lock = threading.Lock()
        self._signature = None
        with store.connection() as db:
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
            if [r[0] for r in db.execute('SELECT version FROM capture_policy_meta')] != [VERSION]:
                raise Fault('unsupported_capture_policy_version')

    # Authoring -----------------------------------------------------------------------

    def author(self, bearer, identity, body):
        """Create (version 0) or replace one policy at its current version. Owner only."""
        ident(identity)
        policy = validate(body)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            row = db.execute('SELECT version,created FROM capture_policies WHERE scope=? AND actor=? AND id=?',
                             (p['scope'], p['id'], identity)).fetchone()
            current = row['version'] if row else 0
            if body['version'] != current:
                raise Fault('capture_policy_changed', 409)
            if not row and db.execute('SELECT count(*) FROM capture_policies WHERE scope=? AND actor=?',
                                      (p['scope'], p['id'])).fetchone()[0] >= MAX_POLICIES:
                raise Fault('capture_policy_capacity', 409)
            for source in policy['rule']['sources']:
                if not db.execute('SELECT 1 FROM knowledge_sources WHERE scope=? AND source=?', (p['scope'], source)).fetchone():
                    raise Fault('capture_source_unknown')
            ReviewedMemory._entity(db, p, policy['rule']['proposes']['subject_id'])
            now = self.store.now()
            rule = json.dumps(policy['rule'], sort_keys=True)
            if row:
                db.execute('''UPDATE capture_policies SET version=version+1,enabled=?,name=?,context=?,rule=?,updated=?
                              WHERE scope=? AND actor=? AND id=?''',
                           (int(policy['enabled']), policy['name'], policy['context'], rule, now, p['scope'], p['id'], identity))
            else:
                db.execute('INSERT INTO capture_policies VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (p['scope'], p['id'], identity, 1, int(policy['enabled']), policy['name'], policy['context'], rule, now, now))
            self.store.log(db, p['scope'], p['id'], 'capture.policy_updated' if row else 'capture.policy_created', identity)
            return self._view(db, p)

    def configure(self, bearer, body):
        """The workspace-wide daily budget across every policy."""
        exact(body, {'version', 'daily_budget'})
        if type(body['version']) is not int or body['version'] < 0:
            raise Fault('invalid_version')
        budget = _budget(body['daily_budget'], MAX_DAILY_BUDGET, 'invalid_capture_budget')
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            row = self._settings(db, p)
            if body['version'] != row['version']:
                raise Fault('capture_settings_changed', 409)
            db.execute('''INSERT INTO capture_settings VALUES (?,?,?,?,?,NULL)
                          ON CONFLICT(scope,actor) DO UPDATE SET daily_budget=excluded.daily_budget,version=version+1,updated=excluded.updated''',
                       (p['scope'], p['id'], budget, 1, self.store.now()))
            self.store.log(db, p['scope'], p['id'], 'capture.settings_updated', p['id'])
            return self._view(db, p)

    @staticmethod
    def _settings(db, p):
        row = db.execute('SELECT * FROM capture_settings WHERE scope=? AND actor=?', (p['scope'], p['id'])).fetchone()
        return dict(row) if row else {'daily_budget': DEFAULT_DAILY_BUDGET, 'version': 0, 'last_run': None}

    # Reading -------------------------------------------------------------------------

    @staticmethod
    def _outcomes(db, p):
        """claim id -> open / accepted / dismissed / invalidated / forgotten."""
        states = {r['id']: r['state'] for r in db.execute(
            'SELECT c.id,c.state FROM memory_claims c JOIN capture_proposals x ON x.claim_id=c.id WHERE x.scope=? AND x.actor=?',
            (p['scope'], p['id']))}
        dismissed = {r[0] for r in db.execute(
            '''SELECT DISTINCT h.claim_id FROM memory_claim_history h JOIN capture_proposals x ON x.claim_id=h.claim_id
               WHERE x.scope=? AND x.actor=? AND h.scope=? AND h.actor=? AND h.state IN ('withdrawn','disputed')''',
            (p['scope'], p['id'], p['scope'], ledger(db, p)))}
        result = {}
        for row in db.execute('SELECT claim_id FROM capture_proposals WHERE scope=? AND actor=?', (p['scope'], p['id'])):
            state = states.get(row[0], 'forgotten')
            if state in ('accepted', 'superseded'):
                result[row[0]] = 'accepted'
            elif state == 'proposed':
                result[row[0]] = 'open'
            elif state in ('withdrawn', 'disputed') or (state == 'invalidated' and row[0] in dismissed):
                result[row[0]] = 'dismissed'
            else:
                result[row[0]] = state if state in ('invalidated', 'forgotten') else 'forgotten'
        return result

    def view(self, bearer):
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            self.memory._reconcile(db, p)
            return self._view(db, p)

    def _view(self, db, p):
        now = self.store.now()
        day = now // DAY
        outcomes = self._outcomes(db, p)
        names = {r['id']: r['name'] for r in db.execute('SELECT id,name FROM memory_entities WHERE scope=? AND actor=?', (p['scope'], ledger(db, p)))}
        policies = []
        for row in db.execute('SELECT * FROM capture_policies WHERE scope=? AND actor=? ORDER BY id', (p['scope'], p['id'])):
            rule = json.loads(row['rule'])
            counts = {'proposed': 0, 'open': 0, 'accepted': 0, 'dismissed': 0, 'invalidated': 0, 'forgotten': 0, 'proposed_today': 0}
            for x in db.execute('SELECT claim_id,day FROM capture_proposals WHERE scope=? AND actor=? AND policy_id=?',
                                (p['scope'], p['id'], row['id'])):
                counts['proposed'] += 1
                counts[outcomes[x['claim_id']]] += 1
                counts['proposed_today'] += x['day'] == day
            counts['deferred_today'] = db.execute('SELECT count(*) FROM capture_deferred WHERE scope=? AND actor=? AND day=? AND policy_id=?',
                                                  (p['scope'], p['id'], day, row['id'])).fetchone()[0]
            subject = names.get(rule['proposes']['subject_id'])
            policies.append({'id': row['id'], 'version': row['version'], 'enabled': bool(row['enabled']), 'name': row['name'],
                             'context': row['context'], **rule, 'subject_available': subject is not None,
                             'description': describe(row['name'], rule, subject or rule['proposes']['subject_id']),
                             'created': row['created'], 'updated': row['updated'], 'counts': counts})
        settings = self._settings(db, p)
        deferred = {reason: n for reason, n in db.execute(
            'SELECT reason,count(*) FROM capture_deferred WHERE scope=? AND actor=? AND day=? GROUP BY reason', (p['scope'], p['id'], day))}
        return {'scope': p['scope'], 'policies': policies,
                'settings': {'version': settings['version'], 'daily_budget': settings['daily_budget']},
                'today': {'day_start': day * DAY, 'proposed': sum(x['counts']['proposed_today'] for x in policies),
                          'deferred': {'rule_budget': deferred.get('rule_budget', 0), 'daily_budget': deferred.get('daily_budget', 0)}},
                'last_run': json.loads(settings['last_run']) if settings.get('last_run') else None,
                'limits': {'policies': MAX_POLICIES, 'sources_per_policy': MAX_SOURCES, 'rule_daily_budget': MAX_RULE_BUDGET,
                           'daily_budget': MAX_DAILY_BUDGET},
                'basis': 'owner_authored_deterministic_rules_over_indexed_notes', 'model_used': False,
                'auto_accept': False, 'authority_granted': False, 'day_boundary': 'utc'}

    # Running -------------------------------------------------------------------------

    def _candidates(self, db, p, now):
        """Matching lines for every enabled policy, in a fixed order, with their prior proposals."""
        from .policy import permitted
        outcomes = self._outcomes(db, p)
        found = []
        for row in db.execute('SELECT * FROM capture_policies WHERE scope=? AND actor=? AND enabled=1 ORDER BY id', (p['scope'], p['id'])):
            rule = json.loads(row['rule'])
            subject = db.execute('SELECT 1 FROM memory_entities WHERE scope=? AND actor=? AND id=?',
                                 (p['scope'], ledger(db, p), rule['proposes']['subject_id'])).fetchone()
            sources = [s for s in rule['sources'] if permitted(db, p, s, now)]
            if not sources:
                continue
            marks = ','.join('?' * len(sources))
            notes = sorted((self.store.opened('knowledge_notes', n) for n in db.execute(f'''SELECT scope,source,id,path,body,sha256,revision
                FROM knowledge_notes WHERE scope=? AND status='ready' AND source IN ({marks})''', (p['scope'], *sources))),
                key=lambda n: (n['path'], n['id']))
            for note in notes:
                if rule['path_prefix'] and not note['path'].startswith(rule['path_prefix']):
                    continue
                for number, line in content_lines(note['body']):
                    value = match_line(rule['match'], line)
                    if value is None:
                        continue
                    digest = _line_hash(line)
                    prior = [outcomes.get(r['claim_id'], 'forgotten') for r in db.execute(
                        'SELECT claim_id FROM capture_proposals WHERE scope=? AND actor=? AND policy_id=? AND note_id=? AND line_hash=?',
                        (p['scope'], p['id'], row['id'], note['id'], digest))]
                    found.append({'policy': row['id'], 'policy_version': row['version'], 'rule': rule, 'subject': bool(subject),
                                  'note': dict(note), 'line': number, 'line_hash': digest, 'value': value, 'prior': prior})
        return found

    def run(self, bearer, body=None):
        """Apply every enabled policy once. Proposals only; nothing is accepted."""
        if body is not None:
            exact(body, set())
        with self.lock:
            return self._run(bearer)

    def _run(self, bearer):
        now = self.store.now()
        day = now // DAY
        skipped = dict.fromkeys(NOT_PROPOSED, 0)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            self.memory._reconcile(db, p)
            settings = self._settings(db, p)
            candidates = self._candidates(db, p, now)
            used = {r['policy_id']: r['n'] for r in db.execute(
                'SELECT policy_id,count(*) AS n FROM capture_proposals WHERE scope=? AND actor=? AND day=? GROUP BY policy_id',
                (p['scope'], p['id'], day))}
            wanted, seen = [], set()
            for c in candidates:
                key = (c['policy'], c['note']['id'], c['line_hash'])
                if key in seen:
                    # The same text twice in one note is one line for this policy.
                    skipped['already_proposed'] += 1
                    continue
                seen.add(key)
                if any(o in ('open', 'accepted') for o in c['prior']):
                    skipped['already_proposed'] += 1
                    continue
                if 'dismissed' in c['prior']:
                    skipped['dismissed'] += 1
                    continue
                if 'forgotten' in c['prior']:
                    skipped['forgotten'] += 1
                    continue
                if not c['subject']:
                    skipped['subject_unavailable'] += 1
                    continue
                if len(c['value']) > MAX_VALUE:
                    skipped['value_too_long'] += 1
                    continue
                item = hashlib.sha256(f'{c["note"]["id"]}|{c["line_hash"]}'.encode()).hexdigest()[:32]
                reason = None
                if used.get(c['policy'], 0) >= c['rule']['daily_budget']:
                    reason = 'rule_budget'
                elif sum(used.values()) >= settings['daily_budget']:
                    reason = 'daily_budget'
                if reason:
                    # Counted only; nothing about the line is proposed or shown.
                    skipped[reason] += 1
                    db.execute('INSERT OR IGNORE INTO capture_deferred VALUES (?,?,?,?,?,?)',
                               (p['scope'], p['id'], day, c['policy'], item, reason))
                    continue
                used[c['policy']] = used.get(c['policy'], 0) + 1
                wanted.append(c)
        proposed = []
        for c in wanted:
            note, rule = c['note'], c['rule']
            request = hashlib.sha256(f'{c["policy"]}|{note["id"]}|{note["revision"]}|{c["line"]}|{c["line_hash"]}'.encode()).hexdigest()[:40]
            statement = {'request_id': 'capture-' + request, 'subject_id': rule['proposes']['subject_id'],
                         'predicate': rule['proposes']['predicate'], 'object_id': None, 'value': c['value'],
                         'valid_from': None, 'valid_until': None,
                         'evidence': {'note_id': note['id'], 'sha256': note['sha256'], 'revision': note['revision'],
                                      'start_line': c['line'], 'end_line': c['line']}}
            try:
                made = self.memory.propose(bearer, statement, capture={
                    'memory_type': rule['proposes']['memory_type'], 'retention_days': rule['proposes']['retention_days'],
                    'captured_from': {'note_id': note['id'], 'policy_id': c['policy']}})
            except Fault as exc:
                reason = {'memory_source_changed': 'source_changed', 'memory_entity_not_found': 'subject_unavailable',
                          'memory_claim_capacity': 'claim_capacity'}.get(exc.code, 'refused')
                skipped[reason] += 1
                if reason == 'claim_capacity':
                    break
                continue
            with self.store.transaction() as db:
                p = self.store.authenticate(db, bearer, {'owner'})
                db.execute('INSERT OR IGNORE INTO capture_proposals VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           (p['scope'], p['id'], made['id'], c['policy'], c['policy_version'], note['id'], note['revision'],
                            c['line'], c['line_hash'], day, self.store.now()))
                if not made['reused']:
                    self.store.log(db, p['scope'], p['id'], 'capture.proposed', made['id'])
            proposed.append({'claim_id': made['id'], 'policy_id': c['policy'], 'note_id': note['id'],
                             'revision': note['revision'], 'line': c['line'], 'state': made['state']})
        summary = {'at': now, 'proposed': len(proposed), 'not_proposed': skipped}
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            settings = self._settings(db, p)
            db.execute('''INSERT INTO capture_settings VALUES (?,?,?,?,?,?)
                          ON CONFLICT(scope,actor) DO UPDATE SET last_run=excluded.last_run''',
                       (p['scope'], p['id'], settings['daily_budget'], settings['version'], now, json.dumps(summary, sort_keys=True)))
        return {'proposed': proposed, 'not_proposed': skipped, 'auto_accepted': 0, 'model_used': False,
                'basis': 'proposals_await_review'}

    def cycle(self):
        """Supervisor hook: run when notes, policies, settings or the day have changed."""
        supervisor = self.supervisor
        if supervisor is None or self.store.paused(supervisor.scope):
            return None
        with self.store.transaction() as db:
            p = self.store.authenticate(db, supervisor.owner, {'owner'})
            signature = (
                tuple(db.execute("SELECT count(*),coalesce(sum(revision),0),coalesce(max(indexed),0) FROM knowledge_notes WHERE scope=?", (p['scope'],)).fetchone()),
                tuple(db.execute('SELECT count(*),coalesce(sum(version),0) FROM capture_policies WHERE scope=? AND actor=? AND enabled=1', (p['scope'], p['id'])).fetchone()),
                self._settings(db, p)['version'], self.store.now() // DAY)
            if signature[1][0] == 0:
                self._signature = signature
                return None
        if signature == self._signature:
            return None
        result = self.run(supervisor.owner)
        self._signature = signature
        return result


POLICY_OPERATION = re.compile(r'/desk/capture/policies/([A-Za-z0-9][A-Za-z0-9_.-]{0,79})')


def route(capture, path, mutation, bearer, body):
    """Reached only through the guarded desk handler (loopback Host/Origin, session, CSRF)."""
    if capture is None:
        raise Fault('capture_not_configured', 409)
    if not mutation:
        if path == '/desk/capture':
            return capture.view(bearer)
        raise Fault('not_found', 404)
    if path == '/desk/capture/run':
        return capture.run(bearer, body)
    if path == '/desk/capture/settings':
        return capture.configure(bearer, body)
    match = POLICY_OPERATION.fullmatch(path)
    if match:
        return capture.author(bearer, match[1], body)
    raise Fault('not_found', 404)
