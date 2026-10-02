"""Authorised routines over commitments and attention (M10: ATT-001, MEM-004, MEM-015).

A routine is a setting the person authors: one allowlisted kind, a schedule, a run budget
per day, a nomination budget per run, optional quiet hours, an interrupt choice and a
pause. It runs only inside the existing foreground supervisor, under the credential this
host was started with, and that credential, the workspace pause and current source grants
are checked again inside the same transaction as every run. Revocation stops it.

A routine reads; it never acts. It may nominate an in-app reminder, or offer a local
draft, each with a stated rule and a citation of the exact commitment version it came
from. The person accepts or dismisses every nomination and both are recorded. Accepting a
reminder may create an executive follow-up through the existing executive API. Accepting a
draft offer only proposes the draft in the existing approval ledger, where its exact text
still needs its own approval. Nothing is delivered outside the app.

The kinds, rules and budgets are fixed in code and in the person's settings. No text in a
note, reviewed statement or procedure is interpreted here: procedures (memory type
'procedural') are listed read-only as reviewed descriptions, never as instructions.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import secrets
from .local import Fault, canonical, exact, fingerprint, ident

DAY, HOUR = 86400, 3600
KINDS = {
    'commitment-review': {
        'name': 'Commitment review',
        'description': 'Reads your open commitments and follow-ups and your accepted, current reviewed commitment statements, '
                       'and nominates a reminder for each one due within a day or overdue.',
        'rules': (
            {'id': 'overdue', 'rule': 'An open executive commitment or follow-up whose due time has passed, or an accepted, '
                                      'current statement captured as a commitment whose scheduled date has passed.'},
            {'id': 'due_within_a_day', 'rule': 'The same, due within the next 24 hours.'},
            {'id': 'scheduled_date', 'rule': 'A commitment statement is dated only by a "scheduled for" value that starts with '
                                             'YYYY-MM-DD, optionally followed by HH:MM, in the routine\'s local time. A date alone '
                                             'means 17:00, as for executive due dates. Other statements are read and counted as undated.'},
            {'id': 'draft_offer', 'rule': 'When local drafts are switched on, an overdue executive commitment or follow-up with a '
                                          'responsible label is also offered as a local draft asking for an update.'},
            {'id': 'once_per_version', 'rule': 'A commitment version is nominated at most once; editing it makes a new version.'},
            {'id': 'snoozed', 'rule': 'A record you have snoozed is not nominated until its snooze ends.'},
        ),
        'default': {'schedule': {'every_hours': 4}, 'interrupt': 'show_now'},
    },
    'morning-brief': {
        'name': 'Morning brief',
        'description': 'At a chosen local time, assembles an in-app brief from your attention items, derived insights and '
                       'proposals awaiting your approval, and surfaces nominations held for it.',
        'rules': (
            {'id': 'attention', 'rule': 'Items from the executive attention rules (overdue, decision past due, due soon, '
                                        'stale milestone). Snoozed items are left out.'},
            {'id': 'insights', 'rule': 'Insights derived from your records by the stated insight rules.'},
            {'id': 'approvals', 'rule': 'Your proposals waiting in the approval ledger whose evidence is still current.'},
            {'id': 'held', 'rule': 'Nominations held for the next brief are surfaced, oldest first, up to the nominations '
                                   'per run budget. The rest stay held.'},
        ),
        'default': {'schedule': {'daily_at': '07:30'}, 'interrupt': 'show_now'},
    },
}
EVERY_HOURS = (1, 2, 4, 8, 12, 24)
FIELDS = {'version', 'enabled', 'schedule', 'utc_offset_minutes', 'runs_per_day', 'nominations_per_run',
          'quiet_hours', 'interrupt', 'propose_drafts'}
SKIP_REASONS = ('authority_lost', 'workspace_paused', 'paused', 'budget_exhausted')
CLOCK = re.compile(r'([01][0-9]|2[0-3]):([0-5][0-9])')
SCHEDULED = re.compile(r'\s*([0-9]{4})-([0-9]{2})-([0-9]{2})(?:[T ]([0-9]{2}):([0-9]{2}))?(?![0-9:])')
MAX_RUNS_PER_DAY, MAX_NOMINATIONS_PER_RUN = 24, 10
MAX_OPEN, KEEP_RUNS, KEEP_DECIDED = 64, 400, 400
RUNS_PER_MINUTE, MANUAL_RECORDS_PER_DAY = 6, 200
SECTION_LIMIT, VIEW_RUNS = 20, 40
OPEN_STATES = ('active', 'open', 'proposed')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS routine_meta(version INTEGER NOT NULL);
INSERT INTO routine_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM routine_meta);
CREATE TABLE IF NOT EXISTS routine_settings(
 scope TEXT NOT NULL, kind TEXT NOT NULL, actor TEXT NOT NULL, enabled INTEGER NOT NULL,
 paused INTEGER NOT NULL, settings TEXT NOT NULL, version INTEGER NOT NULL,
 next_due INTEGER NOT NULL, updated INTEGER NOT NULL, PRIMARY KEY(scope,kind));
CREATE TABLE IF NOT EXISTS routine_runs(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, kind TEXT NOT NULL, actor TEXT NOT NULL, slot TEXT NOT NULL,
 started INTEGER NOT NULL, finished INTEGER NOT NULL, status TEXT NOT NULL, skipped_reason TEXT,
 outcome TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS routine_runs_time ON routine_runs(scope,started);
CREATE TABLE IF NOT EXISTS routine_nominations(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, routine TEXT NOT NULL, run_id TEXT NOT NULL,
 kind TEXT NOT NULL, cite_kind TEXT NOT NULL, cite_id TEXT NOT NULL, cite_version INTEGER NOT NULL,
 rule TEXT NOT NULL, reason TEXT NOT NULL, due INTEGER, delivery TEXT NOT NULL, surface_at INTEGER,
 released_by TEXT, state TEXT NOT NULL, version INTEGER NOT NULL, created INTEGER NOT NULL,
 decided INTEGER, outcome TEXT, UNIQUE(scope,actor,kind,cite_kind,cite_id,cite_version));
CREATE INDEX IF NOT EXISTS routine_nominations_owner ON routine_nominations(scope,actor,state);
CREATE TABLE IF NOT EXISTS routine_action_sources(
 scope TEXT NOT NULL, action_id TEXT NOT NULL, nomination TEXT NOT NULL, actor TEXT NOT NULL,
 cite_kind TEXT NOT NULL, cite_id TEXT NOT NULL, cite_version INTEGER NOT NULL,
 PRIMARY KEY(scope,action_id));
'''


# Settings and local time. The offset is a fixed number of minutes the person picks; daylight
# saving changes are not followed automatically.

def _minutes(value, code='invalid_routine_time'):
    match = CLOCK.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise Fault(code)
    return int(match[1]) * 60 + int(match[2])


def _number(value, low, high, code):
    if type(value) is not int or not low <= value <= high:
        raise Fault(code)
    return value


def validate(kind, body):
    """Normalise one routine's authored settings. Everything is explicit; nothing is inferred."""
    exact(body, FIELDS)
    if type(body['version']) is not int or body['version'] < 0:
        raise Fault('invalid_version')
    if type(body['enabled']) is not bool or type(body['propose_drafts']) is not bool:
        raise Fault('invalid_routine_configuration')
    schedule = body['schedule']
    if type(schedule) is not dict or len(schedule) != 1:
        raise Fault('invalid_routine_schedule')
    if 'every_hours' in schedule:
        if type(schedule['every_hours']) is not int or schedule['every_hours'] not in EVERY_HOURS:
            raise Fault('invalid_routine_schedule')
    elif 'daily_at' in schedule:
        _minutes(schedule['daily_at'], 'invalid_routine_schedule')
    else:
        raise Fault('invalid_routine_schedule')
    offset = _number(body['utc_offset_minutes'], -720, 840, 'invalid_utc_offset')
    if offset % 15:
        raise Fault('invalid_utc_offset')
    quiet = body['quiet_hours']
    if quiet is not None:
        if type(quiet) is not dict or set(quiet) != {'start', 'end'}:
            raise Fault('invalid_quiet_hours')
        if _minutes(quiet['start'], 'invalid_quiet_hours') == _minutes(quiet['end'], 'invalid_quiet_hours'):
            raise Fault('invalid_quiet_hours')
    if body['interrupt'] not in ('show_now', 'hold_for_brief'):
        raise Fault('invalid_interrupt')
    if kind == 'morning-brief' and body['interrupt'] != 'show_now':
        # The brief is the moment held nominations appear; it cannot hold for itself.
        raise Fault('interrupt_not_applicable')
    if kind == 'morning-brief' and body['propose_drafts']:
        raise Fault('drafts_not_applicable')
    return {'schedule': dict(schedule), 'utc_offset_minutes': offset,
            'runs_per_day': _number(body['runs_per_day'], 1, MAX_RUNS_PER_DAY, 'invalid_run_budget'),
            'nominations_per_run': _number(body['nominations_per_run'], 1, MAX_NOMINATIONS_PER_RUN, 'invalid_nomination_budget'),
            'quiet_hours': dict(quiet) if quiet else None, 'interrupt': body['interrupt'], 'propose_drafts': body['propose_drafts']}


def next_slot(settings, after):
    """The first scheduled moment strictly after `after`, in UTC seconds."""
    offset = settings['utc_offset_minutes'] * 60
    local = after + offset
    day = local - local % DAY
    schedule = settings['schedule']
    if 'daily_at' in schedule:
        at = day + _minutes(schedule['daily_at']) * 60
        return (at if at > local else at + DAY) - offset
    step = schedule['every_hours'] * HOUR
    return day + ((local - day) // step + 1) * step - offset


def quiet_until(settings, moment):
    """None outside quiet hours; otherwise the moment the quiet hours end."""
    quiet = settings['quiet_hours']
    if not quiet:
        return None
    offset = settings['utc_offset_minutes'] * 60
    local = moment + offset
    minute, start, end = (local % DAY) // 60, _minutes(quiet['start']), _minutes(quiet['end'])
    inside = start <= minute < end if start < end else (minute >= start or minute < end)
    if not inside:
        return None
    finish = local - local % DAY + end * 60
    return (finish if finish > local else finish + DAY) - offset


def day_start(settings, moment):
    local = moment + settings['utc_offset_minutes'] * 60
    return local - local % DAY - settings['utc_offset_minutes'] * 60


def scheduled_time(value, offset_minutes):
    """A commitment statement's date, only from a leading YYYY-MM-DD[ HH:MM]. Anything else is undated."""
    match = SCHEDULED.match(value) if isinstance(value, str) else None
    if not match:
        return None
    try:
        moment = datetime(int(match[1]), int(match[2]), int(match[3]), int(match[4] or 17), int(match[5] or 0),
                          tzinfo=timezone(timedelta(minutes=offset_minutes)))
    except ValueError:
        return None
    return int(moment.timestamp())


def _local_text(moment, offset_minutes):
    zone = timezone(timedelta(minutes=offset_minutes))
    return datetime.fromtimestamp(moment, zone).strftime('%Y-%m-%d %H:%M')


def draft_text(record, offset_minutes):
    """The fixed wording of an offered draft. Only the person's own title, label and due date fill it."""
    due = _local_text(record['due'], offset_minutes) if record['due'] is not None else 'an earlier date'
    return (f'{record["responsible"]}: checking in on "{record["title"]}", which was due {due}. '
            'Could you let me know where it stands?')


def action_current(store, db, row):
    """Approval and dispatch condition for a draft accepted from a routine nomination.

    The exact commitment version it cites must still exist, belong to the same person and
    be open. Checked in the caller's transaction, at approval and again at dispatch.
    """
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='routine_action_sources'").fetchone():
        return False
    link = db.execute('SELECT * FROM routine_action_sources WHERE scope=? AND action_id=?', (row['scope'], row['id'])).fetchone()
    if not link or link['actor'] != row['actor'] or link['cite_kind'] != 'record':
        return False
    record = db.execute('SELECT version,status FROM executive_records WHERE id=? AND scope=? AND actor=?',
                        (link['cite_id'], row['scope'], row['actor'])).fetchone()
    return bool(record and record['version'] == link['cite_version'] and record['status'] in OPEN_STATES)


class Routines:
    """Two allowlisted routine kinds with durable slots, budgets, holds and recorded outcomes."""

    def __init__(self, store, supervisor):
        from .executive import ExecutiveRecords
        from .reviewed_memory import ReviewedMemory
        self.store, self.supervisor, self.scope = store, supervisor, supervisor.scope
        self.executive, self.memory = ExecutiveRecords(store), ReviewedMemory(store)
        with store.connection() as db:
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
            if [r[0] for r in db.execute('SELECT version FROM routine_meta')] != [1]:
                raise Fault('unsupported_routine_version')

    # Authority ----------------------------------------------------------------

    @staticmethod
    def _kind(kind):
        if kind not in KINDS:
            raise Fault('unknown_routine', 404)
        return kind

    def _hosted(self, db, bearer):
        """Routines run under the credential this host holds; nobody else can author them."""
        p = self.store.authenticate(db, bearer, {'owner'})
        if p['scope'] != self.scope or p['id'] != self.supervisor.principal['id']:
            raise Fault('routine_owner_not_hosted', 403)
        return p

    @staticmethod
    def _paused(db, scope):
        row = db.execute('SELECT paused FROM desk_settings WHERE scope=?', (scope,)).fetchone()
        return bool(row and row[0])

    # Settings -----------------------------------------------------------------

    def configure(self, bearer, kind, body):
        self._kind(kind)
        settings = validate(kind, body)
        with self.supervisor.lock, self.store.transaction() as db:
            p = self._hosted(db, bearer)
            row = db.execute('SELECT version FROM routine_settings WHERE scope=? AND kind=?', (self.scope, kind)).fetchone()
            if (row['version'] if row else 0) != body['version']:
                raise Fault('routine_changed', 409)
            now = self.store.now()
            next_due = next_slot(settings, now) if body['enabled'] else 0
            if row:
                db.execute('UPDATE routine_settings SET actor=?,enabled=?,settings=?,version=version+1,next_due=?,updated=? WHERE scope=? AND kind=?',
                           (p['id'], int(body['enabled']), canonical(settings), next_due, now, self.scope, kind))
            else:
                db.execute('INSERT INTO routine_settings VALUES (?,?,?,?,?,?,?,?,?)',
                           (self.scope, kind, p['id'], int(body['enabled']), 0, canonical(settings), 1, next_due, now))
            self.store.log(db, self.scope, p['id'], 'routine.configured', kind)
        return self.view(bearer)

    def pause(self, bearer, kind, body):
        """A per-routine pause. Due slots while paused are recorded as skipped, never run later."""
        self._kind(kind)
        exact(body, {'version', 'paused'})
        if type(body['paused']) is not bool or type(body['version']) is not int:
            raise Fault('invalid_routine_pause')
        with self.supervisor.lock, self.store.transaction() as db:
            p = self._hosted(db, bearer)
            row = db.execute('SELECT version FROM routine_settings WHERE scope=? AND kind=?', (self.scope, kind)).fetchone()
            if not row:
                raise Fault('routine_not_configured', 409)
            if row['version'] != body['version']:
                raise Fault('routine_changed', 409)
            db.execute('UPDATE routine_settings SET paused=?,version=version+1,updated=? WHERE scope=? AND kind=?',
                       (int(body['paused']), self.store.now(), self.scope, kind))
            self.store.log(db, self.scope, p['id'], 'routine.paused' if body['paused'] else 'routine.resumed', kind)
        return self.view(bearer)

    # Runs ---------------------------------------------------------------------

    def manual(self, bearer, kind, body):
        """Run now at the person's request. Budgets, pauses and authority apply exactly as on schedule."""
        self._kind(kind)
        exact(body, {'request_id'})
        ident(body['request_id'])
        return self._slot(kind, 'manual:' + body['request_id'], bearer=bearer)

    def cycle(self):
        """Called by the existing supervisor; no thread of its own. Each due slot is recorded once."""
        with self.supervisor.lock:
            with self.store.connection() as db:
                due = [dict(r) for r in db.execute('''SELECT kind,next_due FROM routine_settings WHERE scope=? AND enabled=1
                    AND next_due>0 AND next_due<=? ORDER BY next_due,kind LIMIT 4''', (self.scope, self.store.now()))]
            for row in due:
                self._slot(row['kind'], 'due:' + str(row['next_due']), due=row['next_due'])

    def _slot(self, kind, slot, *, due=None, bearer=None):
        manual = bearer is not None
        attempt = {}
        with self.supervisor.lock:
            try:
                with self.store.transaction() as db:
                    return self._attempt(db, kind, slot, due, bearer or self.supervisor.owner, manual, attempt)
            except Exception as exc:
                code = exc.code if isinstance(exc, Fault) else 'routine_failed'
                if 'run_id' not in attempt:
                    # Refused before a run began (not hosted, not configured, rate limited).
                    if manual:
                        raise
                    return None
            # The run began and failed: nothing it did is kept, the failure is recorded and the slot moves on.
            with self.store.transaction() as db:
                db.execute('INSERT OR IGNORE INTO routine_runs VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (attempt['run_id'], self.scope, kind, attempt['actor'], slot, attempt['now'], self.store.now(),
                            'failed', None, canonical({'error': code, 'external_effects': False})))
                if due is not None:
                    db.execute('UPDATE routine_settings SET next_due=? WHERE scope=? AND kind=? AND next_due=?',
                               (next_slot(attempt['settings'], self.store.now()), self.scope, kind, due))
                self.store.log(db, self.scope, attempt['actor'], 'routine.failed', kind)
                return self._run_view(db.execute('SELECT * FROM routine_runs WHERE id=?', (attempt['run_id'],)).fetchone())

    def _attempt(self, db, kind, slot, due, bearer, manual, attempt):
        now = self.store.now()
        try:
            p = self.store.authenticate(db, bearer, {'owner'})
        except Fault:
            if manual:
                raise
            p = None
        if manual and (p['scope'] != self.scope or p['id'] != self.supervisor.principal['id']):
            raise Fault('routine_owner_not_hosted', 403)
        row = db.execute('SELECT * FROM routine_settings WHERE scope=? AND kind=?', (self.scope, kind)).fetchone()
        if not row:
            raise Fault('routine_not_configured', 409)
        if due is not None and (not row['enabled'] or row['next_due'] != due):
            return None
        settings = json.loads(row['settings'])
        run_id = hashlib.sha256(f'{self.scope}\0{kind}\0{row["actor"]}\0{slot}'.encode()).hexdigest()[:32]
        existing = db.execute('SELECT * FROM routine_runs WHERE id=?', (run_id,)).fetchone()
        if existing:
            return {**self._run_view(existing), 'duplicate': True}
        if manual:
            recent = db.execute('SELECT count(*),sum(started>?) FROM routine_runs WHERE scope=? AND started>?',
                                (now - 60, self.scope, now - DAY)).fetchone()
            if (recent[1] or 0) >= RUNS_PER_MINUTE or recent[0] >= MANUAL_RECORDS_PER_DAY:
                raise Fault('routine_rate_limited', 429)
        attempt.update(run_id=run_id, actor=row['actor'], now=now, settings=settings)
        missed = 0
        if due is not None:
            # Advance before running: a failure can never spin on one slot, and downtime never
            # turns into a burst of catch-up runs. Missed slots are counted, not run.
            following = next_slot(settings, due)
            while following <= now and missed < 100:
                missed += 1
                following = next_slot(settings, following)
            db.execute('UPDATE routine_settings SET next_due=? WHERE scope=? AND kind=?', (next_slot(settings, now), self.scope, kind))
        used = db.execute("SELECT count(*) FROM routine_runs WHERE scope=? AND kind=? AND status='completed' AND started>=?",
                          (self.scope, kind, day_start(settings, now))).fetchone()[0]
        budget = {'runs_today': used, 'runs_per_day': settings['runs_per_day'], 'nominations_per_run': settings['nominations_per_run']}
        reason = None
        if p is None or p['id'] != row['actor'] or p['scope'] != self.scope:
            reason = 'authority_lost'
        elif self._paused(db, self.scope):
            reason = 'workspace_paused'
        elif row['paused']:
            reason = 'paused'
        elif used >= settings['runs_per_day']:
            reason = 'budget_exhausted'
        common = {'trigger': 'manual' if manual else 'scheduled', 'missed_slots': missed, 'budget': budget,
                  'model_used': False, 'external_effects': False, 'delivery': 'in_app_only'}
        if reason:
            outcome = {**common, 'skipped': reason}
            self._insert_run(db, run_id, kind, row['actor'], slot, now, 'skipped', reason, outcome)
            self.store.log(db, self.scope, row['actor'], 'routine.skipped', kind)
        else:
            budget['runs_today'] = used + 1
            work = self._commitment_review if kind == 'commitment-review' else self._morning_brief
            outcome = {**common, **work(db, p, settings, run_id, now)}
            self._insert_run(db, run_id, kind, row['actor'], slot, now, 'completed', None, outcome)
            self.store.log(db, self.scope, row['actor'], 'routine.completed', kind)
        return self._run_view(db.execute('SELECT * FROM routine_runs WHERE id=?', (run_id,)).fetchone())

    def _insert_run(self, db, run_id, kind, actor, slot, started, status, reason, outcome):
        db.execute('INSERT INTO routine_runs VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (run_id, self.scope, kind, actor, slot, started, self.store.now(), status, reason, canonical(outcome)))
        # Bounded history. Recent runs stay, so budgets and rate limits cannot be reset by pruning.
        db.execute('''DELETE FROM routine_runs WHERE scope=? AND started<? AND id IN (SELECT id FROM routine_runs WHERE scope=?
            ORDER BY started DESC,rowid DESC LIMIT -1 OFFSET ?)''', (self.scope, self.store.now() - 2 * DAY, self.scope, KEEP_RUNS))

    # What each kind does --------------------------------------------------------

    def _deliver(self, settings, now):
        """Where a new nomination goes: shown now, held until quiet hours end, or held for the next brief."""
        if settings['interrupt'] == 'hold_for_brief':
            return 'next_brief', None
        until = quiet_until(settings, now)
        return ('quiet_hours', until) if until else ('now', None)

    def _commitment_review(self, db, p, settings, run_id, now):
        from .reviewed_memory import ReviewedMemory
        records, _ = self.executive._records(db, p, now)
        candidates, read_records, cited = [], 0, []
        not_nominated = {'already_nominated': 0, 'nomination_budget': 0, 'nomination_capacity': 0, 'snoozed': 0}
        for r in records:
            if r['kind'] not in ('commitment', 'follow_up') or not r['open']:
                continue
            read_records += 1
            cited.append({'kind': 'record', 'id': r['id'], 'version': r['version']})
            if r['due'] is None or r['due'] > now + DAY:
                continue
            if r['snoozed']:
                not_nominated['snoozed'] += 1
                continue
            candidates.append({'cite_kind': 'record', 'cite_id': r['id'], 'cite_version': r['version'], 'due': r['due'],
                               'rule': 'overdue' if r['due'] < now else 'due_within_a_day', 'record': r})
        # Accepted, current statements the person captured as commitments. The shared currentness
        # rule rechecks review state, validity, conflicts, the source revision and the read grant.
        captured = {row['claim_id'] for row in db.execute('''SELECT m.claim_id FROM memory_capture m JOIN memory_claims c ON c.id=m.claim_id
            WHERE c.scope=? AND c.actor=? AND m.memory_type='commitment' ''', (p['scope'], p['id']))}
        statements = {'read': 0, 'undated': 0, 'not_usable': 0}
        for c in ReviewedMemory._claims(db, p, now):
            if c['id'] not in captured:
                continue
            if not c['usable']:
                # Counted only; nothing about it is shown or nominated.
                statements['not_usable'] += 1
                continue
            statements['read'] += 1
            source = c['source']
            cited.append({'kind': 'statement', 'id': c['id'], 'version': c['version'], 'note': source['note_id'],
                          'revision': source['revision'], 'lines': [source['start_line'], source['end_line']]})
            when = scheduled_time(c['value'], settings['utc_offset_minutes']) if c['predicate'] == 'scheduled_for' else None
            if when is None:
                statements['undated'] += 1
                continue
            if when <= now + DAY:
                candidates.append({'cite_kind': 'statement', 'cite_id': c['id'], 'cite_version': c['version'], 'due': when,
                                   'rule': 'overdue' if when < now else 'due_within_a_day', 'record': None})
        candidates.sort(key=lambda c: (c['rule'] != 'overdue', c['due'], c['cite_id']))
        delivery, surface_at = self._deliver(settings, now)
        nominated, held = [], {'quiet_hours': 0, 'next_brief': 0}
        wanted = []
        for c in candidates:
            wanted.append(('reminder', c))
            r = c['record']
            if settings['propose_drafts'] and r is not None and c['rule'] == 'overdue' and r['responsible']:
                wanted.append(('draft', c))
        open_count = db.execute("SELECT count(*) FROM routine_nominations WHERE scope=? AND actor=? AND state='open'",
                                (p['scope'], p['id'])).fetchone()[0]
        for kind, c in wanted:
            if db.execute('''SELECT 1 FROM routine_nominations WHERE scope=? AND actor=? AND kind=? AND cite_kind=? AND cite_id=?
                AND cite_version=?''', (p['scope'], p['id'], kind, c['cite_kind'], c['cite_id'], c['cite_version'])).fetchone():
                not_nominated['already_nominated'] += 1
                continue
            if len(nominated) >= settings['nominations_per_run']:
                not_nominated['nomination_budget'] += 1
                continue
            if open_count >= MAX_OPEN:
                not_nominated['nomination_capacity'] += 1
                continue
            reason = self._reason(kind, c)
            identity = 'nom-' + secrets.token_hex(12)
            db.execute('INSERT INTO routine_nominations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (identity, p['scope'], p['id'], 'commitment-review', run_id, kind, c['cite_kind'], c['cite_id'],
                        c['cite_version'], c['rule'] if kind == 'reminder' else 'draft_offer', reason, c['due'], delivery,
                        surface_at, None, 'open', 1, now, None, None))
            self.store.log(db, p['scope'], p['id'], 'routine.nominated', identity)
            open_count += 1
            if delivery != 'now':
                held[delivery] += 1
            nominated.append({'nomination': identity, 'kind': kind, 'rule': c['rule'] if kind == 'reminder' else 'draft_offer',
                              'delivery': delivery, 'cite': {'kind': c['cite_kind'], 'id': c['cite_id'], 'version': c['cite_version']}})
        return {'read': {'executive_records': read_records, 'commitment_statements': statements['read'],
                         'undated_statements': statements['undated'], 'statements_not_usable': statements['not_usable']},
                'cited': cited[:SECTION_LIMIT * 2], 'cited_total': len(cited), 'due': len(candidates),
                'nominated': nominated, 'not_nominated': not_nominated, 'held': held,
                'nothing_due': not candidates, 'surface_at': surface_at,
                'basis': 'stated_rules_over_your_records_and_reviewed_statements'}

    @staticmethod
    def _reason(kind, c):
        subject = ('Your open ' + c['record']['kind'].replace('_', '-')) if c['record'] else 'Your accepted commitment statement'
        if kind == 'draft':
            return subject + ' is overdue and has a responsible label, so a local draft asking for an update is offered.'
        return subject + (' is past its due time.' if c['rule'] == 'overdue' else ' is due within a day.')

    def _morning_brief(self, db, p, settings, run_id, now):
        records, ctx = self.executive._records(db, p, now)
        summary = self.executive._summarise(records, now, ctx['resolve'])
        attention = summary['attention']['items']
        insights = summary['insights']['items']
        approvals = []
        for row in db.execute("SELECT * FROM actions WHERE scope=? AND actor=? AND state='proposed' AND expires>? ORDER BY created,id",
                              (p['scope'], p['id'], now)):
            if self.store.evidence_valid(db, row):
                approvals.append({'kind': 'action', 'id': row['id'], 'version': 1, 'fingerprint': row['fingerprint'][:16]})
        held = [dict(r) for r in db.execute('''SELECT id FROM routine_nominations WHERE scope=? AND actor=? AND state='open'
            AND delivery='next_brief' AND released_by IS NULL ORDER BY created,id''', (p['scope'], p['id']))]
        release = held[:settings['nominations_per_run']]
        # Released inside the brief's own quiet hours: they appear when those hours end.
        surface_at = quiet_until(settings, now)
        for item in release:
            db.execute('UPDATE routine_nominations SET released_by=?,surface_at=?,version=version+1 WHERE id=?',
                       (run_id, surface_at, item['id']))
        sections = {'attention': [{'kind': 'record', 'id': a['record'], 'version': a['version'], 'rule': a['rules'][0]}
                                  for a in attention[:SECTION_LIMIT]],
                    'insights': [{'rule': i['rule'], 'records': [{'kind': 'record', 'id': r['id'], 'version': r['version']} for r in i['records'][:6]]}
                                 for i in insights[:SECTION_LIMIT]],
                    'approvals': approvals[:SECTION_LIMIT]}
        cited = sections['attention'] + [r for i in sections['insights'] for r in i['records']] + sections['approvals']
        return {'read': {'attention_items': len(attention), 'snoozed_items': len(summary['attention']['snoozed']),
                         'insights': len(insights), 'pending_approvals': len(approvals), 'held_nominations': len(held)},
                'sections': sections, 'cited': cited[:SECTION_LIMIT * 3], 'cited_total': len(cited),
                'released': [item['id'] for item in release], 'still_held': len(held) - len(release),
                'surface_at': surface_at if release else None,
                'nothing_due': not (attention or insights or approvals or release),
                'basis': 'assembled_from_current_permitted_records_not_advice', 'stored': 'citations_and_counts_only'}

    # Nominations --------------------------------------------------------------

    def _nomination(self, db, p, identity):
        ident(identity)
        row = db.execute('SELECT * FROM routine_nominations WHERE id=? AND scope=? AND actor=?', (identity, p['scope'], p['id'])).fetchone()
        if not row:
            # Unknown and someone else's look alike.
            raise Fault('nomination_not_found', 404)
        return row

    def accept(self, bearer, identity, body):
        exact(body, {'version', 'create_follow_up'})
        if type(body['version']) is not int or type(body['create_follow_up']) is not bool:
            raise Fault('invalid_nomination_decision')
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            row = self._nomination(db, p, identity)
            if row['state'] == 'accepted' and row['version'] == body['version'] + 1:
                # The same decision sent again returns its recorded result; a different one is refused.
                recorded = json.loads(row['outcome'] or '{}')
                if row['kind'] == 'draft' or bool(recorded.get('follow_up')) == body['create_follow_up']:
                    return self._accepted(db, p, row)
                raise Fault('nomination_closed', 409)
            if row['version'] != body['version']:
                raise Fault('nomination_changed', 409)
            if row['state'] != 'open':
                raise Fault('nomination_closed', 409)
            if row['kind'] == 'draft' and body['create_follow_up']:
                raise Fault('follow_up_only_for_reminders')
            cite = self._resolver(db, p, self.store.now())(row['cite_kind'], row['cite_id'], row['cite_version'])
            if cite['state'] != 'current' or (row['cite_kind'] == 'record' and cite['status'] not in OPEN_STATES):
                raise Fault('nomination_source_changed', 409)
            if row['kind'] == 'draft':
                return self._accept_draft(db, p, row)
            if not body['create_follow_up']:
                self._decide(db, p, row, 'accepted', {'follow_up': None})
                return self._accepted(db, p, self._nomination(db, p, identity))
            follow_up = self._follow_up_body(db, p, row, cite)
        # The follow-up goes through the existing executive API, with a request ID fixed to this
        # nomination, so a retry can never create a second one.
        created = self.executive.create(bearer, follow_up, derived_from=row['cite_id'] if row['cite_kind'] == 'record' else None)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            row = self._nomination(db, p, identity)
            if row['state'] == 'open' and row['version'] == body['version']:
                self._decide(db, p, row, 'accepted', {'follow_up': created['id']})
            elif json.loads(row['outcome'] or '{}').get('follow_up') != created['id']:
                raise Fault('nomination_closed', 409)
            return self._accepted(db, p, self._nomination(db, p, identity))

    def _follow_up_body(self, db, p, row, cite):
        if row['cite_kind'] == 'record':
            record = db.execute('SELECT * FROM executive_records WHERE id=?', (row['cite_id'],)).fetchone()
            title, project = record['title'], record['project']
            if project and not self.executive._resolver(db, p, self.store.now())(project):
                project = None
        else:
            title = f"{cite['subject']['name']}, scheduled for {cite['value']}"
            project = 'entity:' + cite['subject']['id'] if cite['subject']['kind'] == 'project' else None
        return {'request_id': 'routine-' + row['id'], 'kind': 'follow_up', 'title': ('Follow up: ' + ' '.join(title.split()))[:160],
                'detail': 'Accepted from a commitment review reminder. ' + row['reason'], 'project': project,
                'due': None, 'rank': None, 'support': None}

    def _accept_draft(self, db, p, row):
        """Propose the draft in the existing ledger. It still needs its own exact approval."""
        record = db.execute('SELECT * FROM executive_records WHERE id=?', (row['cite_id'],)).fetchone()
        if not record['responsible']:
            raise Fault('nomination_source_changed', 409)
        settings = db.execute("SELECT settings FROM routine_settings WHERE scope=? AND kind='commitment-review'", (p['scope'],)).fetchone()
        offset = json.loads(settings['settings'])['utc_offset_minutes'] if settings else 0
        if db.execute('SELECT count(*) FROM actions WHERE scope=?', (p['scope'],)).fetchone()[0] >= 5000:
            raise Fault('action_capacity', 409)
        action_id, now = 'routine-' + row['id'], self.store.now()
        params = {'text': draft_text(dict(record), offset)}
        expiry = now + 900
        bound = {'id': action_id, 'scope': p['scope'], 'actor': p['id'], 'capability': 'message.draft', 'parameters': params,
                 'expires_at': expiry, 'routine': {'nomination': row['id'], 'cite': {'kind': 'record', 'id': row['cite_id'],
                                                                                     'version': row['cite_version']}}}
        db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?)', (p['scope'], action_id, p['id'], 'message.draft', canonical(params),
                   fingerprint(bound), expiry, 'proposed', now, None))
        db.execute('INSERT INTO routine_action_sources VALUES (?,?,?,?,?,?,?)',
                   (p['scope'], action_id, row['id'], p['id'], 'record', row['cite_id'], row['cite_version']))
        self.store.log(db, p['scope'], p['id'], 'action.proposed_from_routine', action_id)
        self._decide(db, p, row, 'accepted', {'action': action_id})
        return self._accepted(db, p, self._nomination(db, p, row['id']))

    def _accepted(self, db, p, row):
        outcome = json.loads(row['outcome'] or '{}')
        result = {'nomination': self._nomination_view(row, self._resolver(db, p, self.store.now()), self.store.now())}
        if outcome.get('action'):
            action = db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (p['scope'], outcome['action'])).fetchone()
            result['action'] = self.store.action_view(action) if action else None
        if outcome.get('follow_up'):
            result['follow_up'] = outcome['follow_up']
        return result

    def dismiss(self, bearer, identity, body):
        exact(body, {'version'})
        if type(body['version']) is not int:
            raise Fault('invalid_nomination_decision')
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            row = self._nomination(db, p, identity)
            if row['state'] == 'dismissed' and row['version'] == body['version'] + 1:
                return {'nomination': self._nomination_view(row, self._resolver(db, p, self.store.now()), self.store.now())}
            if row['version'] != body['version']:
                raise Fault('nomination_changed', 409)
            if row['state'] != 'open':
                raise Fault('nomination_closed', 409)
            self._decide(db, p, row, 'dismissed', None)
            row = self._nomination(db, p, identity)
            return {'nomination': self._nomination_view(row, self._resolver(db, p, self.store.now()), self.store.now())}

    def _decide(self, db, p, row, state, outcome):
        db.execute('UPDATE routine_nominations SET state=?,decided=?,outcome=?,version=version+1 WHERE id=?',
                   (state, self.store.now(), canonical(outcome) if outcome is not None else None, row['id']))
        self.store.log(db, p['scope'], p['id'], 'routine.nomination_' + state, row['id'])
        db.execute('''DELETE FROM routine_nominations WHERE scope=? AND actor=? AND state!='open' AND id IN (SELECT id FROM routine_nominations
            WHERE scope=? AND actor=? AND state!='open' ORDER BY decided DESC,id LIMIT -1 OFFSET ?)''',
                   (p['scope'], p['id'], p['scope'], p['id'], KEEP_DECIDED))

    # Reads --------------------------------------------------------------------

    def _resolver(self, db, p, now):
        """What a citation points at, as this caller may read it now. Nothing else is revealed."""
        from .reviewed_memory import ReviewedMemory
        records = {r['id']: dict(r) for r in db.execute('SELECT id,kind,title,status,version,due,responsible FROM executive_records WHERE scope=? AND actor=?',
                                                        (p['scope'], p['id']))}
        cache = {}

        def claims():
            if 'claims' not in cache:
                cache['claims'] = {c['id']: c for c in ReviewedMemory._claims(db, p, now)}
                cache['entities'] = {r['id']: dict(r) for r in db.execute('SELECT id,kind,name FROM memory_entities WHERE scope=? AND actor=?',
                                                                         (p['scope'], p['id']))}
            return cache['claims'], cache['entities']

        def resolve(kind, identity, version):
            if kind == 'record':
                r = records.get(identity)
                if not r:
                    return {'state': 'unavailable'}
                return {'state': 'current' if r['version'] == version else 'changed', 'title': r['title'], 'record_kind': r['kind'],
                        'status': r['status'], 'current_version': r['version'], 'due': r['due'], 'responsible': r['responsible']}
            if kind == 'statement':
                found, entities = claims()
                c = found.get(identity)
                if not c or not c['usable'] or c['subject_id'] not in entities:
                    # Withdrawn, unreadable now or no longer accepted: its value is never shown.
                    return {'state': 'unavailable'}
                subject = {k: entities[c['subject_id']][k] for k in ('id', 'kind', 'name')}
                source = c['source']
                return {'state': 'current' if c['version'] == version else 'changed', 'subject': subject, 'predicate': c['predicate'],
                        'value': c['value'], 'current_version': c['version'],
                        'source': {k: source[k] for k in ('note_id', 'path', 'title', 'revision', 'start_line', 'end_line')}}
            if kind == 'action':
                row = db.execute('SELECT state,actor FROM actions WHERE scope=? AND id=?', (p['scope'], identity)).fetchone()
                return {'state': 'unavailable'} if not row or row['actor'] != p['id'] else {'state': 'current', 'action_state': row['state']}
            return {'state': 'unavailable'}
        return resolve

    @staticmethod
    def _surfaced(row, now):
        if row['state'] != 'open':
            return False
        if row['delivery'] == 'next_brief' and row['released_by'] is None:
            return False
        return row['surface_at'] is None or row['surface_at'] <= now

    def _nomination_view(self, row, resolve, now):
        surfaced = self._surfaced(row, now)
        held = None
        if row['state'] == 'open' and not surfaced:
            held = 'next_brief' if row['delivery'] == 'next_brief' and row['released_by'] is None else 'quiet_hours'
        return {'id': row['id'], 'version': row['version'], 'routine': row['routine'], 'kind': row['kind'], 'rule': row['rule'],
                'reason': row['reason'], 'due': row['due'], 'delivery': row['delivery'], 'surface_at': row['surface_at'],
                'released_by_brief': row['released_by'], 'surfaced': surfaced, 'held': held, 'state': row['state'],
                'created': row['created'], 'decided': row['decided'], 'outcome': json.loads(row['outcome']) if row['outcome'] else None,
                'cite': {'kind': row['cite_kind'], 'id': row['cite_id'], 'version': row['cite_version'],
                         **resolve(row['cite_kind'], row['cite_id'], row['cite_version'])},
                'basis': 'nomination_not_obligation', 'external_delivery': False}

    def _run_view(self, row, resolve=None):
        outcome = json.loads(row['outcome'])
        view = {'id': row['id'], 'kind': row['kind'], 'trigger': 'manual' if row['slot'].startswith('manual:') else 'scheduled',
                'started': row['started'], 'finished': row['finished'], 'status': row['status'],
                'skipped_reason': row['skipped_reason'], 'outcome': outcome, 'historical': True}
        if resolve is not None:
            # Each citation is shown as this caller may read it now; the stored outcome holds no titles or values.
            sections = outcome.get('sections') or {}
            cites = outcome.get('cited', []) + sections.get('attention', []) + sections.get('approvals', [])
            cites += [r for i in sections.get('insights', []) for r in i['records']] + [n['cite'] for n in outcome.get('nominated', [])]
            for item in cites:
                item['resolved'] = resolve(item['kind'], item['id'], item['version'])
        return view

    def _settings_view(self, db, row, now):
        kind = row['kind']
        settings = json.loads(row['settings'])
        credential = db.execute('SELECT revoked,expires FROM credentials WHERE id=? AND scope=?', (row['actor'], self.scope)).fetchone()
        used = db.execute("SELECT count(*) FROM routine_runs WHERE scope=? AND kind=? AND status='completed' AND started>=?",
                          (self.scope, kind, day_start(settings, now))).fetchone()[0]
        return {'configured': True, 'enabled': bool(row['enabled']), 'paused': bool(row['paused']), 'version': row['version'],
                'settings': settings, 'next_due': row['next_due'] or None, 'runs_today': used, 'updated': row['updated'],
                'quiet_now': quiet_until(settings, now) is not None,
                'authority_available': bool(credential and not credential['revoked'] and credential['expires'] > now
                                            and row['actor'] == self.supervisor.principal['id'])}

    def view(self, bearer):
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            now = self.store.now()
            kinds = [{'kind': k, 'name': v['name'], 'description': v['description'], 'rules': list(v['rules']), 'default': v['default']}
                     for k, v in KINDS.items()]
            base = {'scope': p['scope'], 'now': now, 'kinds': kinds, 'delivery': 'in_app_only', 'external_effects': False,
                    'model_used': False, 'authority_granted': False,
                    'limits': {'runs_per_day': MAX_RUNS_PER_DAY, 'nominations_per_run': MAX_NOMINATIONS_PER_RUN,
                               'open_nominations': MAX_OPEN, 'every_hours': list(EVERY_HOURS), 'retained_runs': KEEP_RUNS}}
            if p['scope'] != self.scope or p['id'] != self.supervisor.principal['id']:
                return {**base, 'available': False, 'reason': 'owner_only' if p['role'] != 'owner' else 'not_hosted',
                        'routines': [], 'runs': [], 'nominations': []}
            resolve = self._resolver(db, p, now)
            rows = {r['kind']: r for r in db.execute('SELECT * FROM routine_settings WHERE scope=?', (self.scope,))}
            routines = []
            for kind in kinds:
                row = rows.get(kind['kind'])
                routines.append({**kind, **(self._settings_view(db, row, now) if row else
                                            {'configured': False, 'enabled': False, 'paused': False, 'version': 0,
                                             'settings': None, 'next_due': None, 'runs_today': 0, 'quiet_now': False,
                                             'authority_available': True})})
            runs = [self._run_view(r, resolve) for r in db.execute(
                'SELECT * FROM routine_runs WHERE scope=? AND actor=? ORDER BY started DESC,rowid DESC LIMIT ?', (self.scope, p['id'], VIEW_RUNS))]
            nominations = [self._nomination_view(r, resolve, now) for r in db.execute(
                '''SELECT * FROM routine_nominations WHERE scope=? AND actor=? AND (state='open' OR id IN (SELECT id FROM routine_nominations
                   WHERE scope=? AND actor=? AND state!='open' ORDER BY decided DESC,id LIMIT 20)) ORDER BY state!='open',created DESC,id''',
                (self.scope, p['id'], self.scope, p['id']))]
            return {**base, 'available': True, 'reason': None, 'workspace_paused': self._paused(db, self.scope),
                    'routines': routines, 'runs': runs, 'nominations': nominations}

    def summary(self, bearer):
        """What the executive panel shows: surfaced open nominations and the latest brief, nothing held."""
        view = self.view(bearer)
        if not view['available']:
            return {'available': False, 'reason': view['reason'], 'nominations': [], 'held': 0, 'latest_brief': None}
        open_items = [n for n in view['nominations'] if n['state'] == 'open']
        brief = next((r for r in view['runs'] if r['kind'] == 'morning-brief' and r['status'] == 'completed'), None)
        return {'available': True, 'reason': None, 'nominations': [n for n in open_items if n['surfaced']],
                'held': sum(not n['surfaced'] for n in open_items),
                'latest_brief': {'id': brief['id'], 'finished': brief['finished'], 'read': brief['outcome']['read'],
                                 'released': len(brief['outcome']['released'])} if brief else None,
                'delivery': 'in_app_only', 'external_effects': False}

    def procedures(self, bearer):
        """Read-only registry of procedural memory. Listed to be read; nothing here is ever run."""
        from .reviewed_memory import ReviewedMemory
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            now = self.store.now()
            # The same reconciliation the reviewed-memory view runs: edited support invalidates.
            self.memory._reconcile(db, p)
            procedural = {r['claim_id']: dict(r) for r in db.execute('''SELECT m.* FROM memory_capture m JOIN memory_claims c ON c.id=m.claim_id
                WHERE c.scope=? AND c.actor=? AND m.memory_type='procedural' ''', (p['scope'], p['id']))}
            entities = {r['id']: dict(r) for r in db.execute('SELECT id,kind,name FROM memory_entities WHERE scope=? AND actor=?', (p['scope'], p['id']))}
            items = []
            for c in ReviewedMemory._claims(db, p, now):
                if c['id'] not in procedural or c['state'] == 'forgotten':
                    continue
                source = c['source']
                # Support that changed needs a fresh review; support this caller cannot read now is withheld.
                support = 'current' if source else 'changed' if c['state'] == 'invalidated' else 'unavailable'
                subject = entities.get(c['subject_id'])
                obj = entities.get(c['object_id']) if c['object_id'] else None
                items.append({'id': c['id'], 'version': c['version'], 'review_state': c['state'], 'usable': c['usable'],
                              'subject': {k: subject[k] for k in ('id', 'kind', 'name')} if subject else None,
                              'predicate': c['predicate'], 'value': c['value'] if source else None,
                              'object': {k: obj[k] for k in ('id', 'kind', 'name')} if obj and source else None,
                              'support_state': support, 'conflicts': len(c['conflicts']), 'reviewed': c['reviewed'],
                              'valid_from': c['valid_from'], 'valid_until': c['valid_until'],
                              'captured': procedural[c['id']]['created'], 'retention_until': procedural[c['id']]['retention_until'],
                              'source': {k: source[k] for k in ('note_id', 'path', 'title', 'revision', 'start_line', 'end_line', 'quote')} if source else None,
                              'executable': False, 'grants_authority': False, 'basis': 'reviewed_description_not_instruction'})
        notes = []
        if hasattr(self.store, 'knowledge'):
            for n in self.store.knowledge(bearer, kind='procedure')['results']:
                notes.append({'id': n['id'], 'title': n['title'], 'path': n['path'], 'revision': n['revision'],
                              'basis': 'authored_note_not_reviewed', 'executable': False})
        return {'procedures': items, 'authored_procedure_notes': notes[:64],
                'counts': {'reviewed': len(items), 'usable': sum(i['usable'] for i in items), 'authored_notes': len(notes)},
                'read_only': True, 'executable': False, 'authority_granted': False,
                'basis': 'reviewed_descriptions_not_instructions',
                'statement': 'Procedures are kept to be read. Nothing here runs, approves, schedules or grants anything.'}
