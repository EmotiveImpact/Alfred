"""Goals, mandates, heartbeats and budgets for the agent hub (docs/AGENT_HUB.md, step H2).

ALFRED holds the goals; brains only work on them. A **mandate** links one of the owner's
executive goal records (``alfred.executive``, kind ``goal``) to the limits within which
brains may work for it: the owner, a scope class, a deadline, a success test (text the
owner writes; nothing here evaluates it), an autonomy level per kind of work (0 to 2; 3 and
4 are refused as in H1), the brains allowed, the brain currently assigned, a tool
allowlist, a budget and an optional heartbeat schedule. Mandates, budgets and controls are
owner-only and version-checked. Every change is written to an append-only hub journal and
the audit log; a stop is also written first to the lifecycle journal, so restoring an older
backup cannot undo it.

``GoalHub`` attaches itself to a ``BrainHub`` as its gate. From then on:

* every brain task must name a current mandate (the packet's ``goal.ref``) and stay inside
  it: the brain allowed, tools on the mandate's allowlist, autonomy at or below the level
  for its kind of work, the mandate's scope class, the goal active, the mandate not paused,
  stopped or past its deadline, the brain and the hub not paused. Anything else is refused
  before a job exists;
* the brain backend from ``GoalHub.backend`` asks again at dispatch, so a job that reached
  the coordinator by another route, or whose mandate changed while it was queued, never
  reaches a brain;
* each task is bound to its mandate and goal (``hub_tasks``) in the same transaction as the
  H1 brain task record.

Budgets apply per goal (in the mandate), per brain and overall (in ``hub_controls``), each
with daily and total limits on tokens, money, wall time and task count, and a warning
percentage. An overall budget must exist before any task is admitted. Usage is what ALFRED
measured: tokens and money from the H1 meter that stopped the brain at its own budget, wall
time from the backend, reported before the job settles. A brain that started but never
reported is charged its task's ceiling; a task whose brain never started is charged nothing
except its place in the task count.

* Admission: a task is admitted only if the measured usage of finished tasks, plus the
  ceilings of tasks still in flight, plus this task's ceiling, stays within every limit of
  every level. Work ALFRED admitted therefore cannot pass a limit.
* Warning: measured usage at or above the warning percentage records an attention item,
  once per limit and period.
* Hard stop: measured usage at a limit, or committed usage above it (after the owner lowers
  a limit), records an attention item, pauses the goal, the brain or the whole hub, and
  cancels its queued and running tasks through the job coordinator. Nothing resumes on its
  own: the owner resumes once the budget has room again.

Heartbeats: a mandate may carry a schedule (the routines scheduling style) and an
owner-authored task. The supervisor cycle submits that task for the latest due slot; slots
missed while the host was stopped are counted, never replayed. A brain cannot schedule
itself: no field of a result bundle and no proposal capability reaches a schedule.

Acceptance checks (H4) on a mandate: the owner may attach a list of ``alfred.verification``
checks to a mandate, owner only, version-checked and journalled like every other mandate
setting. ``GoalHub`` puts them first in the ``acceptance`` of every task packet it
authorises under that mandate (declared by the mandate, with the mandate as reference),
followed by any checks the task request itself declares; exact duplicates are dropped. The
gate refuses a packet under that mandate that does not carry them. A brain never declares
checks: the result bundle has no field for them. ``effect_readback`` can only be declared by
a task at autonomy 2, never by a mandate, because a mandate also covers lower levels. The
mandate's success test stays text the owner wrote; nothing evaluates it.

What happened to goal work is journalled for the learning loop (H3), value-free: budget
warnings and hard stops (with the brain whose accounted task triggered them), goals and
brains paused, stopped or reassigned, tasks the mandate gate refused (``task.refused``:
reason code, stage, brain, kind of work, mandate) and heartbeat slots missed
(``heartbeat.missed``). Learning reads these for routing notes only and changes nothing here.

Verification over HTTP: ``results`` lists the caller's own brain results with ALFRED's
routing evidence class (verified, failed checks, unverifiable, no checks, not returned);
``result`` reads one with its runs; ``verify`` runs its declared checks and ``acknowledge``
records the owner accepting the exact run they saw (explicitly over failed checks). Each is
private to the person who submitted the task (``policy.ledger``), and a check's reasons are
withheld when the result's sources can no longer be read under the person's grants.

Like routines, the hub runs under the owner credential this host was started with, because
heartbeats, ingestion and cancellation use it. Any other credential is told the hub is not
available to it. No model, network or file access happens here.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
import secrets
import threading

from . import brain as plug
from . import sealing
from . import verification
from .local import Fault, canonical, exact, ident, timestamp
from .routines import CLOCK, EVERY_HOURS, day_start, next_slot

DAY = 86400
WORK = re.compile(r'[a-z][a-z0-9_-]{0,31}')
BRAIN_ID = re.compile(r'[a-z0-9][a-z0-9_.-]{0,63}')
NOTE_ID = re.compile(r'[0-9a-f]{24}')
DIMENSIONS = ('tokens', 'money_pence', 'wall_seconds', 'tasks')
PERIODS = ('daily', 'total')
LIMITS = {'tokens': (1, 100_000_000), 'money_pence': (0, 10_000_000), 'wall_seconds': (1, 31_622_400), 'tasks': (1, 100_000)}
BUDGET_KEYS = {'daily', 'total', 'warn_percent', 'utc_offset_minutes'}
STATES = ('active', 'paused', 'stopped')
MAX_WORK, MAX_BRAINS, MAX_MANDATES = 8, 8, 64
MAX_DEADLINE = 5 * 366 * DAY
ACCOUNT_PER_CYCLE, BEATS_PER_CYCLE = 32, 8
KEEP_HEARTBEATS, VIEW_TASKS, VIEW_BEATS, VIEW_ATTENTION, VIEW_JOURNAL = 400, 8, 8, 40, 20
VIEW_RESULTS, RESULTS_WINDOW, RESULTS_SCAN, VIEW_RUNS = 24, 30 * DAY, 2000, 20
CREATE_FIELDS = {'request_id', 'goal', 'scope_class', 'deadline', 'success_test', 'autonomy', 'brains',
                 'assigned_brain', 'tools', 'budget', 'schedule'}
# Optional on create, update, a scheduled task and an operator task: acceptance checks (H4).
OPTIONAL = 'acceptance'
SETTINGS = ('deadline', 'success_test', 'autonomy', 'brains', 'tools', 'budget', 'schedule', 'acceptance')
TEMPLATE_FIELDS = {'work', 'instruction', 'context', 'learned', 'tools', 'budget', 'autonomy'}
TASK_FIELDS = TEMPLATE_FIELDS | {'request_id', 'brain'}
# Refusals that are the gate's replay guards, not decisions about the work.
NOT_JOURNALLED = ('already_dispatched',)
OPERATIONS = {'goal': ('pause', 'resume', 'stop', 'reassign'), 'brain': ('pause', 'resume', 'stop'),
              'overall': ('pause', 'resume')}

SCHEMA = '''
CREATE TABLE IF NOT EXISTS hub_meta(version INTEGER NOT NULL);
INSERT INTO hub_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM hub_meta);
CREATE TABLE IF NOT EXISTS hub_mandates(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 goal TEXT NOT NULL, scope_class TEXT NOT NULL, deadline INTEGER NOT NULL, success_test TEXT NOT NULL,
 autonomy TEXT NOT NULL, brains TEXT NOT NULL, assigned_brain TEXT NOT NULL, tools TEXT NOT NULL, budget TEXT NOT NULL,
 schedule TEXT, next_due INTEGER NOT NULL, missed_total INTEGER NOT NULL, state TEXT NOT NULL, state_reason TEXT,
 version INTEGER NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL, acceptance TEXT,
 UNIQUE(scope,actor,request_id), CHECK(state IN ('active','paused','stopped')));
CREATE UNIQUE INDEX IF NOT EXISTS hub_mandate_goal ON hub_mandates(scope,goal) WHERE state!='stopped';
CREATE TABLE IF NOT EXISTS hub_controls(
 scope TEXT NOT NULL, actor TEXT NOT NULL, target TEXT NOT NULL, state TEXT NOT NULL, reason TEXT, budget TEXT,
 version INTEGER NOT NULL, updated INTEGER NOT NULL, PRIMARY KEY(scope,actor,target),
 CHECK(state IN ('active','paused','stopped')));
CREATE TABLE IF NOT EXISTS hub_tasks(
 job_id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, mandate TEXT NOT NULL, goal TEXT NOT NULL,
 work TEXT NOT NULL, brain TEXT NOT NULL, autonomy INTEGER NOT NULL, trigger TEXT NOT NULL, slot TEXT,
 ceil_tokens INTEGER NOT NULL, ceil_money INTEGER NOT NULL, ceil_wall INTEGER NOT NULL, created INTEGER NOT NULL,
 accounted INTEGER, used_tokens INTEGER, used_money INTEGER, used_wall INTEGER, usage_basis TEXT, result TEXT,
 auto_verify TEXT, CHECK(trigger IN ('operator','heartbeat')));
CREATE INDEX IF NOT EXISTS hub_tasks_owner ON hub_tasks(scope,actor,created);
CREATE TABLE IF NOT EXISTS hub_meter(
 job_id TEXT PRIMARY KEY, state TEXT NOT NULL, steps INTEGER, tokens INTEGER, money_pence INTEGER,
 wall_seconds INTEGER, reason TEXT, started INTEGER NOT NULL, finished INTEGER,
 CHECK(state IN ('running','finished')));
CREATE TABLE IF NOT EXISTS hub_heartbeats(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, mandate TEXT NOT NULL, slot TEXT NOT NULL,
 at INTEGER NOT NULL, status TEXT NOT NULL, reason TEXT, missed INTEGER NOT NULL, job_id TEXT,
 CHECK(status IN ('submitted','skipped','refused')));
CREATE INDEX IF NOT EXISTS hub_heartbeats_owner ON hub_heartbeats(scope,actor,mandate,at);
CREATE TABLE IF NOT EXISTS hub_attention(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, target TEXT NOT NULL, period TEXT NOT NULL,
 period_start INTEGER NOT NULL, dimension TEXT NOT NULL, level TEXT NOT NULL, used INTEGER NOT NULL,
 limit_value INTEGER NOT NULL, at INTEGER NOT NULL, state TEXT NOT NULL,
 UNIQUE(scope,actor,target,period,period_start,dimension,level),
 CHECK(level IN ('warning','hard_stop')), CHECK(state IN ('open','acknowledged')));
CREATE TABLE IF NOT EXISTS hub_journal(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, actor TEXT NOT NULL, target TEXT NOT NULL,
 event TEXT NOT NULL, version INTEGER, detail TEXT NOT NULL, at INTEGER NOT NULL);
CREATE TRIGGER IF NOT EXISTS hub_journal_no_update BEFORE UPDATE ON hub_journal
 BEGIN SELECT RAISE(ABORT,'hub_journal_append_only'); END;
CREATE TRIGGER IF NOT EXISTS hub_journal_no_delete BEFORE DELETE ON hub_journal
 BEGIN SELECT RAISE(ABORT,'hub_journal_append_only'); END;
'''


# Validation ------------------------------------------------------------------

def _prose(value, limit, code):
    """Owner-authored text with newlines and tabs; never empty."""
    if not isinstance(value, str) or len(value) > limit or not value.strip():
        raise Fault(code)
    if any((ord(c) < 32 and c not in '\n\t') or 127 <= ord(c) < 160 for c in value):
        raise Fault('control_character')
    return value.strip()


def _offset(value):
    if type(value) is not int or not -720 <= value <= 840 or value % 15:
        raise Fault('invalid_utc_offset')
    return value


def _names(value, pattern, limit, code, *, minimum=0):
    if type(value) is not list or not minimum <= len(value) <= limit or len(set(map(str, value))) != len(value):
        raise Fault(code)
    if any(not isinstance(item, str) or not pattern.fullmatch(item) for item in value):
        raise Fault(code)
    return list(value)


def _level(value, code='invalid_autonomy'):
    if type(value) is not int or not 0 <= value <= 4:
        raise Fault(code)
    if value not in plug.ENFORCED_AUTONOMY:
        raise Fault(plug.PILOT_GATE_REASON, 403)
    return value


def _limits(value):
    if type(value) is not dict or set(value) != set(DIMENSIONS):
        raise Fault('invalid_budget')
    for name, (low, high) in LIMITS.items():
        item = value[name]
        if item is not None and (type(item) is not int or not low <= item <= high):
            raise Fault('invalid_budget')
    return {name: value[name] for name in DIMENSIONS}


def validate_budget(value):
    """Daily and total limits per dimension (``None`` means no limit at this level),
    a warning percentage and the fixed UTC offset that decides where a day starts."""
    if type(value) is not dict or set(value) != BUDGET_KEYS:
        raise Fault('invalid_budget')
    warn = value['warn_percent']
    if type(warn) is not int or not 1 <= warn <= 99:
        raise Fault('invalid_budget')
    return {'daily': _limits(value['daily']), 'total': _limits(value['total']), 'warn_percent': warn,
            'utc_offset_minutes': _offset(value['utc_offset_minutes'])}


def _selections(value):
    """Context selections as BrainHub.build_packet takes them. Shape only; the notes,
    grants and line ranges are checked again every time a packet is built."""
    if type(value) is not list or len(value) > plug.MAX_EXCERPTS:
        raise Fault('invalid_context')
    for item in value:
        exact(item, {'note', 'start_line', 'end_line'})
        if not isinstance(item['note'], str) or not NOTE_ID.fullmatch(item['note']):
            raise Fault('invalid_context')
        first = plug._int(item['start_line'], 1, 2**31, 'invalid_context')
        plug._int(item['end_line'], first, first + plug.MAX_EXCERPT_LINES - 1, 'invalid_context')
    return [dict(item) for item in value]


def validate_checks(value):
    """Acceptance check requests as ``verification.declare`` takes them, normalised: defaults
    filled, no identifiers (they are numbered when a packet is built). ``None`` means none."""
    if value is None:
        return None
    if type(value) is not list or not value:
        raise Fault('invalid_acceptance')
    declared = verification.declare({'checks': value})
    verification.validate_acceptance(declared, {'autonomy': 2})  # Shape; read-back is checked where it is used.
    return _bare(declared['checks'])


def _bare(checks):
    return [{k: v for k, v in check.items() if k != 'id'} for check in checks]


def merge_checks(mandate_id, mandate_checks, task_checks, autonomy):
    """The packet's acceptance request: the mandate's checks first, then the task's own,
    exact duplicates dropped, validated against the task's autonomy. ``None`` when neither
    declares any."""
    checks = list(mandate_checks or [])
    for check in task_checks or []:
        if check not in checks:
            checks.append(check)
    if not checks:
        return None
    request = ({'declared_by': 'mandate', 'ref': mandate_id, 'checks': checks} if mandate_checks
               else {'declared_by': 'owner', 'checks': checks})
    verification.validate_acceptance(verification.declare(request), {'autonomy': autonomy})
    return request


def validate_template(value):
    """The task a heartbeat submits, or an operator task, before it becomes a packet."""
    if type(value) is not dict or not TEMPLATE_FIELDS <= set(value) <= TEMPLATE_FIELDS | {OPTIONAL}:
        raise Fault('invalid_task')
    if not isinstance(value['work'], str) or not WORK.fullmatch(value['work']):
        raise Fault('invalid_work_kind')
    plug._body(value['instruction'], 1000, 'invalid_instruction')
    learned = value['learned']
    if type(learned) is not list or len(learned) > plug.MAX_LEARNED or len(set(map(str, learned))) != len(learned):
        raise Fault('invalid_learned')
    for item in learned:
        ident(item)
    task = {'work': value['work'], 'instruction': value['instruction'], 'context': _selections(value['context']),
            'learned': list(learned), 'tools': _names(value['tools'], plug.TOOL, plug.MAX_TOOLS, 'invalid_tools'),
            'budget': dict(plug.validate_budget(value['budget'])), 'autonomy': _level(value['autonomy'])}
    checks = validate_checks(value.get(OPTIONAL))
    if checks is not None:
        task[OPTIONAL] = checks
    return task


def validate_schedule(value):
    if value is None:
        return None
    if type(value) is not dict or set(value) != {'when', 'utc_offset_minutes', 'task'}:
        raise Fault('invalid_schedule')
    when = value['when']
    if type(when) is not dict or len(when) != 1:
        raise Fault('invalid_schedule')
    if 'every_hours' in when:
        if type(when['every_hours']) is not int or when['every_hours'] not in EVERY_HOURS:
            raise Fault('invalid_schedule')
    elif 'daily_at' in when:
        if not isinstance(when['daily_at'], str) or not CLOCK.fullmatch(when['daily_at']):
            raise Fault('invalid_schedule')
    else:
        raise Fault('invalid_schedule')
    return {'when': dict(when), 'utc_offset_minutes': _offset(value['utc_offset_minutes']),
            'task': validate_template(value['task'])}


def _clock(schedule):
    return {'schedule': schedule['when'], 'utc_offset_minutes': schedule['utc_offset_minutes']}


def missed_slots(schedule, due, now):
    """How many scheduled slots fell at or before ``now`` since ``due`` (inclusive)."""
    settings, count, moment = _clock(schedule), 0, due
    while moment <= now and count < 1000:
        count += 1
        moment = next_slot(settings, moment)
    return count


def _ceilings(spec, budget):
    """What one task may use at most: its own packet budget, which the H1 meter enforces."""
    money = math.ceil(budget['tokens'] * spec.pence_per_1k_tokens / 1000)
    return {'tokens': budget['tokens'], 'money_pence': min(budget['money_pence'], money),
            'wall_seconds': budget['wall_seconds']}


# The hub ---------------------------------------------------------------------

class GoalHub:
    """Mandates, budgets, heartbeats and operator controls over one ``BrainHub``.

    ``host_bearer`` is the owner credential this host runs under (the supervisor's). Only
    that credential may author mandates, budgets and controls, and every scheduled task,
    ingestion and cancellation runs under it.
    """

    def __init__(self, store, brains: plug.BrainHub, host_bearer):
        from .executive import ExecutiveRecords
        if getattr(brains, 'gate', None) is not None:
            raise Fault('brain_hub_gate_already_attached', 409)
        self.store, self.brains, self.jobs = store, brains, brains.jobs
        self.registry, self.policy, self.host = brains.registry, brains.policy, host_bearer
        principal = store.principal(host_bearer, {'owner'})
        self.scope, self.host_id = principal['scope'], principal['id']
        ExecutiveRecords(store)  # The goal records a mandate links to.
        self.lock = threading.RLock()
        with store.connection() as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hub_meta'").fetchone()
            versions = [r[0] for r in db.execute('SELECT version FROM hub_meta')] if exists else [1]
            if versions != [1]:
                raise Fault('unsupported_hub_version')
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
            if 'acceptance' not in {r[1] for r in db.execute('PRAGMA table_info(hub_mandates)')}:
                # Additive: mandates written before H4 acceptance checks have none.
                db.executescript('BEGIN IMMEDIATE;\nALTER TABLE hub_mandates ADD COLUMN acceptance TEXT;\nCOMMIT;')
            if 'auto_verify' not in {r[1] for r in db.execute('PRAGMA table_info(hub_tasks)')}:
                # Additive: tasks accounted before automatic verification are never run late.
                db.executescript('BEGIN IMMEDIATE;\nALTER TABLE hub_tasks ADD COLUMN auto_verify TEXT;\nCOMMIT;')
        self.verifier = verification.Verifier(brains)
        brains.gate = self

    def backend(self) -> plug.BrainBackend:
        """The brain backend for this hub: it asks the hub again before any brain starts and
        reports what the brain used."""
        return plug.BrainBackend(self.registry, self.policy, gate=self)

    # Authority and records ---------------------------------------------------

    def _hosted(self, db, bearer):
        p = self.store.authenticate(db, bearer, {'owner'})
        if p['scope'] != self.scope or p['id'] != self.host_id:
            raise Fault('hub_owner_not_hosted', 403)
        return p

    def _journal(self, db, p, target, event, version, detail):
        db.execute('INSERT INTO hub_journal(scope,actor,target,event,version,detail,at) VALUES (?,?,?,?,?,?,?)',
                   (p['scope'], p['id'], target, event, version, canonical(detail), self.store.now()))
        self.store.log(db, p['scope'], p['id'], 'hub.' + event, target)

    def _mandate(self, db, p, mandate_id, version=None):
        ident(mandate_id)
        row = db.execute('SELECT * FROM hub_mandates WHERE id=? AND scope=? AND actor=?',
                         (mandate_id, p['scope'], p['id'])).fetchone()
        if not row:
            raise Fault('mandate_not_found', 404)
        if version is not None:
            if type(version) is not int or version < 1:
                raise Fault('invalid_version')
            if row['version'] != version:
                raise Fault('mandate_changed', 409)
        return row

    def _goal(self, db, p, goal_id):
        return self.store.opened('executive_records', db.execute(
            'SELECT id,kind,title,status,version FROM executive_records WHERE id=? AND scope=? AND actor=?',
            (goal_id, p['scope'], p['id'])).fetchone())

    def _control(self, db, p, target):
        return db.execute('SELECT * FROM hub_controls WHERE scope=? AND actor=? AND target=?',
                          (p['scope'], p['id'], target)).fetchone()

    def _workspace_paused(self, db, scope):
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='desk_settings'").fetchone():
            return False
        row = db.execute('SELECT paused FROM desk_settings WHERE scope=?', (scope,)).fetchone()
        return bool(row and row[0])

    def _spec(self, brain_id):
        return self.registry.get(brain_id).spec

    def _brain_fits(self, db, p, brain_id, scope_class):
        """A brain may be named in a mandate only if it is plugged in, declares the scope
        class, would be allowed by the owner's cloud rule and has not been stopped."""
        spec = self._spec(brain_id)
        if scope_class not in spec.scopes:
            raise Fault('brain_scope_not_declared', 403)
        if spec.locality == 'cloud' and scope_class not in self.policy.cloud_scopes:
            raise Fault('cloud_brain_refused_for_scope', 403)
        control = self._control(db, p, 'brain:' + brain_id)
        if control and control['state'] == 'stopped':
            raise Fault('brain_stopped', 409)
        return spec

    def _settings(self, db, p, body, scope_class, now, mandate_id):
        """Normalise a whole mandate. Everything is explicit; nothing is inferred."""
        deadline = timestamp(body['deadline'])
        if not now < deadline <= now + MAX_DEADLINE:
            raise Fault('invalid_deadline')
        autonomy = body['autonomy']
        if type(autonomy) is not dict or not 1 <= len(autonomy) <= MAX_WORK:
            raise Fault('invalid_autonomy')
        for work, level in autonomy.items():
            if not isinstance(work, str) or not WORK.fullmatch(work):
                raise Fault('invalid_work_kind')
            _level(level)
        brains = _names(body['brains'], BRAIN_ID, MAX_BRAINS, 'invalid_brains', minimum=1)
        for brain_id in brains:
            self._brain_fits(db, p, brain_id, scope_class)
        tools = _names(body['tools'], plug.TOOL, plug.MAX_TOOLS, 'invalid_tools')
        if not set(tools) <= self.policy.permitted_tools:
            raise Fault('tool_not_permitted', 403)
        checks = validate_checks(body.get(OPTIONAL))
        if checks is not None:
            # A mandate covers every level up to its own, so it cannot declare a read-back of effects.
            verification.validate_acceptance(verification.declare(
                {'declared_by': 'mandate', 'ref': mandate_id, 'checks': checks}), {'autonomy': 0})
        schedule = validate_schedule(body['schedule'])
        if schedule is not None:
            task = schedule['task']
            if (task['work'] not in autonomy or task['autonomy'] > autonomy[task['work']]
                    or not set(task['tools']) <= set(tools)):
                raise Fault('schedule_outside_mandate', 403)
            merge_checks(mandate_id, checks, task.get(OPTIONAL), task['autonomy'])
        return {'deadline': deadline, 'success_test': _prose(body['success_test'], 600, 'invalid_success_test'),
                'autonomy': {k: autonomy[k] for k in sorted(autonomy)}, 'brains': brains, 'tools': tools,
                'budget': validate_budget(body['budget']), 'schedule': schedule, OPTIONAL: checks}

    @staticmethod
    def _stored(row):
        return {'deadline': row['deadline'], 'success_test': row['success_test'], 'autonomy': json.loads(row['autonomy']),
                'brains': json.loads(row['brains']), 'tools': json.loads(row['tools']), 'budget': json.loads(row['budget']),
                'schedule': json.loads(row['schedule']) if row['schedule'] else None,
                OPTIONAL: json.loads(row['acceptance']) if row['acceptance'] else None}

    # Mandates ---------------------------------------------------------------

    def create_mandate(self, bearer, body):
        if type(body) is not dict or not CREATE_FIELDS <= set(body) <= CREATE_FIELDS | {OPTIONAL}:
            raise Fault('invalid_fields')
        ident(body['request_id']); ident(body['goal'])
        if body['scope_class'] not in plug.SCOPE_CLASSES:
            raise Fault('invalid_scope_class')
        digest = hashlib.sha256(canonical(body).encode()).hexdigest()
        with self.lock, self.store.transaction() as db:
            p = self._hosted(db, bearer)
            old = db.execute('SELECT id,request_hash FROM hub_mandates WHERE scope=? AND actor=? AND request_id=?',
                             (p['scope'], p['id'], body['request_id'])).fetchone()
            if old:
                if old['request_hash'] != digest:
                    raise Fault('mandate_request_collision', 409)
                return self._mandate_view(db, p, self._mandate(db, p, old['id']), self.store.now())
            if db.execute("SELECT count(*) FROM hub_mandates WHERE scope=? AND actor=? AND state!='stopped'",
                          (p['scope'], p['id'])).fetchone()[0] >= MAX_MANDATES:
                raise Fault('mandate_capacity', 409)
            goal = self._goal(db, p, body['goal'])
            if not goal:
                raise Fault('goal_not_available', 404)  # Unknown and someone else's look alike.
            if goal['kind'] != 'goal':
                raise Fault('not_a_goal')
            if goal['status'] != 'active':
                raise Fault('goal_not_active', 409)
            if db.execute("SELECT 1 FROM hub_mandates WHERE scope=? AND goal=? AND state!='stopped'",
                          (p['scope'], goal['id'])).fetchone():
                raise Fault('goal_has_mandate', 409)
            now = self.store.now()
            mandate_id = 'mandate-' + secrets.token_hex(12)
            settings = self._settings(db, p, body, body['scope_class'], now, mandate_id)
            if body['assigned_brain'] not in settings['brains']:
                raise Fault('assigned_brain_not_allowed', 403)
            schedule, checks = settings['schedule'], settings[OPTIONAL]
            db.execute('''INSERT INTO hub_mandates(id,scope,actor,request_id,request_hash,goal,scope_class,deadline,success_test,
                autonomy,brains,assigned_brain,tools,budget,schedule,next_due,missed_total,state,state_reason,version,created,updated,
                acceptance) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (mandate_id, p['scope'], p['id'], body['request_id'], digest, goal['id'], body['scope_class'],
                        settings['deadline'], settings['success_test'], canonical(settings['autonomy']),
                        canonical(settings['brains']), body['assigned_brain'], canonical(settings['tools']),
                        canonical(settings['budget']), canonical(schedule) if schedule else None,
                        next_slot(_clock(schedule), now) if schedule else 0, 0, 'active', None, 1, now, now,
                        canonical(checks) if checks else None))
            self._journal(db, p, 'goal:' + mandate_id, 'mandate.created', 1,
                          {'goal': goal['id'], 'scope_class': body['scope_class'], 'assigned_brain': body['assigned_brain'],
                           **settings})
            return self._mandate_view(db, p, self._mandate(db, p, mandate_id), now)

    def update_mandate(self, bearer, mandate_id, body):
        """Change any setting except the goal and scope class, at the version the owner saw."""
        if (type(body) is not dict or 'version' not in body or len(body) < 2
                or not set(body) <= set(SETTINGS) | {'version'}):
            raise Fault('invalid_fields')
        with self.lock:
            with self.store.transaction() as db:
                p = self._hosted(db, bearer)
                row = self._mandate(db, p, mandate_id, body['version'])
                if row['state'] == 'stopped':
                    raise Fault('goal_stopped', 409)
                now = self.store.now()
                merged = {**self._stored(row), **{k: body[k] for k in SETTINGS if k in body}}
                settings = self._settings(db, p, merged, row['scope_class'], now, row['id'])
                if row['assigned_brain'] not in settings['brains']:
                    raise Fault('assigned_brain_not_allowed', 409)  # Reassign first.
                changed = {k: settings[k] for k in SETTINGS if k in body}
                schedule = settings['schedule']
                next_due = row['next_due']
                if 'schedule' in body:
                    next_due = next_slot(_clock(schedule), now) if schedule else 0
                checks = settings[OPTIONAL]
                db.execute('''UPDATE hub_mandates SET deadline=?,success_test=?,autonomy=?,brains=?,tools=?,budget=?,schedule=?,
                    acceptance=?,next_due=?,version=version+1,updated=? WHERE id=?''',
                           (settings['deadline'], settings['success_test'], canonical(settings['autonomy']),
                            canonical(settings['brains']), canonical(settings['tools']), canonical(settings['budget']),
                            canonical(schedule) if schedule else None, canonical(checks) if checks else None,
                            next_due, now, row['id']))
                self._journal(db, p, 'goal:' + row['id'], 'mandate.updated', row['version'] + 1, changed)
            # A lowered limit can stop the goal at once.
            self._enforce(mandate=row['id'])
            with self.store.transaction() as db:
                return self._mandate_view(db, p, self._mandate(db, p, row['id']), self.store.now())

    # Tasks ------------------------------------------------------------------

    def submit_task(self, bearer, mandate_id, body):
        """An operator task now, under the mandate. The brain defaults to the assigned one."""
        if type(body) is not dict or not TASK_FIELDS <= set(body) <= TASK_FIELDS | {OPTIONAL}:
            raise Fault('invalid_fields')
        ident(body['request_id'])
        if body['brain'] is not None and (not isinstance(body['brain'], str) or not BRAIN_ID.fullmatch(body['brain'])):
            raise Fault('invalid_brain')
        task = validate_template({k: body[k] for k in set(body) & (TEMPLATE_FIELDS | {OPTIONAL})})
        with self.lock:
            with self.store.transaction() as db:
                p = self._hosted(db, bearer)
                row = self._mandate(db, p, mandate_id)
            brain = row['assigned_brain'] if body['brain'] is None else body['brain']
            return self._submit(bearer, row, task, brain, 'operator', 'request:' + body['request_id'])

    def _submit(self, bearer, row, task, brain, trigger, slot):
        with self.store.transaction() as db:
            goal = self._goal(db, {'scope': row['scope'], 'id': row['actor']}, row['goal'])
        title = goal['title'] if goal else 'Goal no longer available'
        key = hashlib.sha256(f"{row['id']}|{trigger}|{slot}".encode()).hexdigest()[:32]
        request = {'task_id': 'goal-' + key, 'brain': brain, 'goal': {'ref': row['id'], 'statement': title[:400]},
                   'scope': row['scope_class'], 'instruction': task['instruction'], 'context': task['context'],
                   'learned': task['learned'], 'tools': task['tools'], 'budget': task['budget'],
                   'autonomy': task['autonomy']}
        # The owner's checks: the mandate's first, then the task's own. Never the brain's.
        acceptance = merge_checks(row['id'], json.loads(row['acceptance']) if row['acceptance'] else None,
                                  task.get(OPTIONAL), task['autonomy'])
        if acceptance is not None:
            request['acceptance'] = acceptance
        binding = {'mandate': row['id'], 'work': task['work'], 'trigger': trigger, 'slot': slot}
        submitted = self.brains.submit(bearer, request, binding=binding)
        return {**submitted, 'mandate': row['id'], 'goal': row['goal'], 'work': task['work'], 'trigger': trigger}

    # The gate BrainHub and BrainBackend call --------------------------------

    def _admissible(self, db, row, brain_id, now):
        """Whether any new work may start under this mandate on this brain right now."""
        if self._workspace_paused(db, row['scope']):
            raise Fault('workspace_paused', 409)
        if row['state'] == 'stopped':
            raise Fault('goal_stopped', 409)
        if row['state'] == 'paused':
            raise Fault('goal_paused', 409)
        goal = self._goal(db, {'scope': row['scope'], 'id': row['actor']}, row['goal'])
        if not goal or goal['kind'] != 'goal' or goal['status'] != 'active':
            raise Fault('goal_not_active', 409)
        if now >= row['deadline']:
            raise Fault('mandate_expired', 409)
        owner = {'scope': row['scope'], 'id': row['actor']}
        brain = self._control(db, owner, 'brain:' + brain_id)
        if brain and brain['state'] != 'active':
            raise Fault('brain_' + brain['state'], 409)
        overall = self._control(db, owner, 'overall')
        if overall and overall['state'] != 'active':
            raise Fault('hub_paused', 409)

    def authorise(self, bearer, spec, packet, binding):
        """Called by ``BrainHub.submit`` before a job exists. Raises unless the task serves
        a current mandate, stays inside it and fits every budget."""
        if binding is None:
            raise Fault('mandate_required', 403)
        if type(binding) is not dict or set(binding) != {'mandate', 'work', 'trigger', 'slot'}:
            raise Fault('invalid_mandate_binding')
        if binding['trigger'] not in ('operator', 'heartbeat'):
            raise Fault('invalid_mandate_binding')
        if binding['mandate'] != packet['goal']['ref']:
            raise Fault('mandate_mismatch', 403)
        refusal = None
        with self.store.transaction() as db:
            p = self._hosted(db, bearer)
            row = db.execute('SELECT * FROM hub_mandates WHERE id=? AND scope=? AND actor=?',
                             (binding['mandate'], p['scope'], p['id'])).fetchone()
            if not row:
                raise Fault('mandate_required', 403)
            try:
                self._inside(db, p, row, spec, packet, binding)
            except Fault as exc:
                refusal = exc  # Nothing was written; the refusal is journalled below.
        if refusal is not None:
            self._refused(p, 'admission', refusal, spec.id, binding['work'], binding['trigger'], row['id'])
            raise refusal

    @staticmethod
    def _checks_carried(row, packet):
        """The mandate's acceptance checks must lead the packet's, declared by this mandate."""
        mandate_checks = json.loads(row['acceptance']) if row['acceptance'] else None
        acceptance = packet.get('acceptance')
        if acceptance and acceptance['declared_by'] == 'mandate' and acceptance['ref'] != row['id']:
            raise Fault('mandate_mismatch', 403)
        if mandate_checks:
            if not acceptance or acceptance['declared_by'] != 'mandate':
                raise Fault('mandate_checks_missing', 403)
            if _bare(acceptance['checks'][:len(mandate_checks)]) != mandate_checks:
                raise Fault('mandate_checks_changed', 409)
        elif acceptance and acceptance['declared_by'] == 'mandate':
            raise Fault('mandate_checks_changed', 409)

    def _inside(self, db, p, row, spec, packet, binding):
        now = self.store.now()
        self._admissible(db, row, spec.id, now)
        if packet['scope'] != row['scope_class']:
            raise Fault('scope_class_outside_mandate', 403)
        autonomy = json.loads(row['autonomy'])
        if binding['work'] not in autonomy:
            raise Fault('work_kind_not_in_mandate', 403)
        if packet['autonomy'] > autonomy[binding['work']]:
            raise Fault('autonomy_above_mandate', 403)
        if spec.id not in json.loads(row['brains']):
            raise Fault('brain_not_in_mandate', 403)
        if not set(packet['tools']) <= set(json.loads(row['tools'])):
            raise Fault('tool_not_in_mandate', 403)
        self._checks_carried(row, packet)
        prior = db.execute('''SELECT 1 FROM brain_tasks b JOIN hub_tasks h ON h.job_id=b.job_id
            WHERE b.scope=? AND b.actor=? AND b.task_id=?''', (p['scope'], p['id'], packet['task_id'])).fetchone()
        if not prior:  # A repeated request for an admitted task is already counted.
            self._admit(db, p, row, spec, _ceilings(spec, packet['budget']), now)

    def _refused(self, p, stage, refusal, brain, work, trigger, mandate, job=None):
        """A task the mandate gate refused, for the owner's record and the learning loop.
        Codes, identifiers and the stage only."""
        if refusal.code in NOT_JOURNALLED or not plug.REASON.fullmatch(refusal.code):
            return
        with self.store.transaction() as db:
            self._journal(db, p, 'tasks', 'task.refused', None,
                          {'reason': refusal.code, 'stage': stage, 'brain': brain, 'work': work, 'trigger': trigger,
                           'mandate': mandate, 'job': job})

    def bind(self, db, p, job, spec, packet, binding):
        """Called by ``BrainHub.submit`` inside its own transaction: the task links back to
        the mandate and goal it serves, with the ceilings its budget allows."""
        row = db.execute('SELECT goal FROM hub_mandates WHERE id=?', (binding['mandate'],)).fetchone()
        ceiling = _ceilings(spec, packet['budget'])
        inserted = db.execute('''INSERT OR IGNORE INTO hub_tasks(job_id,scope,actor,mandate,goal,work,brain,autonomy,trigger,
            slot,ceil_tokens,ceil_money,ceil_wall,created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                              (job['id'], p['scope'], p['id'], binding['mandate'], row['goal'], binding['work'], spec.id,
                               packet['autonomy'], binding['trigger'], binding['slot'], ceiling['tokens'],
                               ceiling['money_pence'], ceiling['wall_seconds'], self.store.now())).rowcount
        if inserted:
            self.store.log(db, p['scope'], p['id'], 'hub.task_admitted', job['id'])

    def dispatch(self, job_id, spec, packet):
        """Called by the brain backend just before a brain starts: the final recheck. The
        start is recorded first, so a brain that never reports is charged its ceiling."""
        refusal = None
        with self.store.transaction() as db:
            task = db.execute('SELECT * FROM hub_tasks WHERE job_id=?', (job_id,)).fetchone()
            if not task:
                raise Fault('mandate_required', 403)
            try:
                if task['brain'] != spec.id or packet['goal']['ref'] != task['mandate']:
                    raise Fault('mandate_mismatch', 403)
                row = db.execute('SELECT * FROM hub_mandates WHERE id=?', (task['mandate'],)).fetchone()
                self._admissible(db, row, spec.id, self.store.now())
                if db.execute('SELECT 1 FROM hub_meter WHERE job_id=?', (job_id,)).fetchone():
                    raise Fault('already_dispatched', 409)
            except Fault as exc:
                refusal = exc
            else:
                db.execute("INSERT INTO hub_meter(job_id,state,started) VALUES (?,'running',?)", (job_id, self.store.now()))
        if refusal is not None:
            self._refused({'scope': task['scope'], 'id': task['actor']}, 'dispatch', refusal, task['brain'], task['work'],
                          task['trigger'], task['mandate'], job_id)
            raise refusal

    def metered(self, job_id, used, wall_seconds, reason):
        """Called by the brain backend when a run ends, with the meter's own count."""
        values = [used.get(k) for k in ('steps', 'tokens', 'money_pence')] + [wall_seconds]
        if any(type(v) is not int or v < 0 for v in values):
            raise Fault('invalid_meter_report')
        with self.store.transaction() as db:
            db.execute('''UPDATE hub_meter SET state='finished',steps=?,tokens=?,money_pence=?,wall_seconds=?,reason=?,finished=?
                WHERE job_id=? AND state='running' ''', (*values, reason, self.store.now(), job_id))

    # Budgets ----------------------------------------------------------------

    @staticmethod
    def _filter(level, target, prefix=''):
        if level == 'goal':
            return prefix + 'mandate=?', (target,)
        if level == 'brain':
            return prefix + 'brain=?', (target,)
        return '1=1', ()

    def _measure(self, db, p, level, target, since):
        where, args = self._filter(level, target)
        row = db.execute(f'''SELECT count(*) AS admitted, coalesce(sum(accounted IS NOT NULL),0) AS done,
            coalesce(sum(used_tokens),0) AS tokens, coalesce(sum(used_money),0) AS money_pence,
            coalesce(sum(used_wall),0) AS wall_seconds,
            coalesce(sum(CASE WHEN accounted IS NULL THEN ceil_tokens ELSE 0 END),0) AS r_tokens,
            coalesce(sum(CASE WHEN accounted IS NULL THEN ceil_money ELSE 0 END),0) AS r_money,
            coalesce(sum(CASE WHEN accounted IS NULL THEN ceil_wall ELSE 0 END),0) AS r_wall
            FROM hub_tasks WHERE scope=? AND actor=? AND {where} AND created>=?''', (p['scope'], p['id'], *args, since)).fetchone()
        used = {'tokens': row['tokens'], 'money_pence': row['money_pence'], 'wall_seconds': row['wall_seconds'], 'tasks': row['done']}
        reserved = {'tokens': row['r_tokens'], 'money_pence': row['r_money'], 'wall_seconds': row['r_wall'],
                    'tasks': row['admitted'] - row['done']}
        return used, reserved

    def _levels(self, db, p, mandate=None, brain=None):
        """(level, target id, journal target, budget) for each budget a task could count against."""
        levels = []
        if mandate is not None:
            row = db.execute('SELECT budget FROM hub_mandates WHERE id=?', (mandate,)).fetchone()
            if row:
                levels.append(('goal', mandate, 'goal:' + mandate, json.loads(row['budget'])))
        if brain is not None:
            row = self._control(db, p, 'brain:' + brain)
            levels.append(('brain', brain, 'brain:' + brain, json.loads(row['budget']) if row and row['budget'] else None))
        row = self._control(db, p, 'overall')
        levels.append(('overall', None, 'overall', json.loads(row['budget']) if row and row['budget'] else None))
        return levels

    def _periods(self, budget, now):
        return (('daily', day_start({'utc_offset_minutes': budget['utc_offset_minutes']}, now)), ('total', 0))

    def _admit(self, db, p, row, spec, ceiling, now):
        for level, target, _, budget in self._levels(db, p, row['id'], spec.id):
            if budget is None:
                if level == 'overall':
                    raise Fault('overall_budget_required', 409)
                continue
            for period, since in self._periods(budget, now):
                used, reserved = self._measure(db, p, level, target, since)
                for dimension in DIMENSIONS:
                    limit = budget[period][dimension]
                    need = 1 if dimension == 'tasks' else ceiling[dimension]
                    if limit is not None and used[dimension] + reserved[dimension] + need > limit:
                        raise Fault(f'over_budget_{level}_{period}_{dimension}', 409)

    @staticmethod
    def _spent(used, reserved, limit):
        return used > limit or (limit > 0 and used >= limit) or used + reserved > limit

    def _evaluate(self, db, p, level, target, budget, now):
        """Yields (period, since, dimension, used, limit, level of concern) for one budget."""
        for period, since in self._periods(budget, now):
            used, reserved = self._measure(db, p, level, target, since)
            for dimension in DIMENSIONS:
                limit = budget[period][dimension]
                if limit is None:
                    continue
                if self._spent(used[dimension], reserved[dimension], limit):
                    yield period, since, dimension, used[dimension], limit, 'hard_stop'
                elif limit > 0 and used[dimension] * 100 >= limit * budget['warn_percent']:
                    yield period, since, dimension, used[dimension], limit, 'warning'

    def _attention(self, db, p, target, period, since, dimension, level, used, limit, cause=None):
        identity = 'hub-att-' + hashlib.sha256(
            f"{p['scope']}|{p['id']}|{target}|{period}|{since}|{dimension}|{level}".encode()).hexdigest()[:24]
        inserted = db.execute('INSERT OR IGNORE INTO hub_attention VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                              (identity, p['scope'], p['id'], target, period, since, dimension, level, used, limit,
                               self.store.now(), 'open')).rowcount
        if inserted:
            detail = {'period': period, 'since': since, 'dimension': dimension, 'used': used, 'limit': limit}
            if cause is not None:
                detail['brain'] = cause  # The brain whose accounted task brought this budget here.
            self._journal(db, p, target, 'budget.' + level, None, detail)

    def _in_flight(self, db, p, level, target):
        where, args = self._filter(level, target, 'h.')
        return [r[0] for r in db.execute(f'''SELECT h.job_id FROM hub_tasks h JOIN jobs j ON j.id=h.job_id
            WHERE h.scope=? AND h.actor=? AND h.accounted IS NULL AND {where}
            AND j.state IN ('queued','leased','running') ORDER BY h.created,h.job_id''', (p['scope'], p['id'], *args))]

    def _hold(self, db, p, level, target, state, reason):
        """Pause or stop a goal, a brain or the hub. Returns the in-flight jobs to cancel."""
        now = self.store.now()
        if level == 'goal':
            row = db.execute('SELECT * FROM hub_mandates WHERE id=?', (target,)).fetchone()
            if row['state'] == 'active' or (state == 'stopped' and row['state'] != 'stopped'):
                db.execute('UPDATE hub_mandates SET state=?,state_reason=?,next_due=?,version=version+1,updated=? WHERE id=?',
                           (state, reason, 0 if state == 'stopped' else row['next_due'], now, target))
                self._journal(db, p, 'goal:' + target, 'goal.' + state, row['version'] + 1,
                              {'reason': reason, 'brain': row['assigned_brain']})
        else:
            key = 'overall' if level == 'overall' else 'brain:' + target
            row = self._control(db, p, key)
            if row is None:
                db.execute('INSERT INTO hub_controls VALUES (?,?,?,?,?,?,?,?)', (p['scope'], p['id'], key, state, reason, None, 1, now))
                self._journal(db, p, key, level + '.' + state, 1, {'reason': reason})
            elif row['state'] == 'active' or (state == 'stopped' and row['state'] != 'stopped'):
                db.execute('UPDATE hub_controls SET state=?,reason=?,version=version+1,updated=? WHERE scope=? AND actor=? AND target=?',
                           (state, reason, now, p['scope'], p['id'], key))
                self._journal(db, p, key, level + '.' + state, row['version'] + 1, {'reason': reason})
        return self._in_flight(db, p, level, target)

    def _cancel(self, jobs):
        """Cancellation goes through the job coordinator, which records it on each job."""
        cancelled = []
        for job_id in jobs:
            try:
                self.jobs.cancel(self.host, job_id)
                cancelled.append(job_id)
            except Fault:
                pass  # Finished meanwhile: cancellation is not undo.
        if cancelled:
            with self.store.transaction() as db:
                self._journal(db, {'scope': self.scope, 'id': self.host_id}, 'tasks', 'tasks.cancelled', None,
                              {'jobs': cancelled})
        return cancelled

    def _enforce(self, *, mandate=None, brain=None, cause=None):
        """Record warnings and apply hard stops for the budgets a goal and brain count against.
        ``cause`` is the brain whose accounted task is being enforced, when there is one."""
        cancel = []
        with self.store.transaction() as db:
            p = {'scope': self.scope, 'id': self.host_id}
            now = self.store.now()
            for level, target, key, budget in self._levels(db, p, mandate, brain):
                if budget is None:
                    continue
                stop = None
                for period, since, dimension, used, limit, concern in self._evaluate(db, p, level, target, budget, now):
                    self._attention(db, p, key, period, since, dimension, concern, used, limit, cause)
                    if concern == 'hard_stop' and stop is None:
                        stop = f'budget_{period}_{dimension}'
                if stop:
                    cancel += self._hold(db, p, level, target, 'paused', stop)
        return self._cancel(sorted(set(cancel)))

    def _still_spent(self, db, p, level, target):
        """Resuming is refused while the budget that stopped this target is still spent."""
        levels = self._levels(db, p, target if level == 'goal' else None, target if level == 'brain' else None)
        for found, _, _, budget in levels:
            if found != level or budget is None:
                continue
            if any(item[-1] == 'hard_stop' for item in self._evaluate(db, p, level, target, budget, self.store.now())):
                raise Fault('budget_still_spent', 409)

    def set_budget(self, bearer, level, target, body):
        """The overall budget, or one brain's. ``budget`` None removes it (the overall budget
        is then missing, so no task is admitted)."""
        exact(body, {'version', 'budget'})
        if type(body['version']) is not int or body['version'] < 0:
            raise Fault('invalid_version')
        budget = None if body['budget'] is None else validate_budget(body['budget'])
        if level == 'brain':
            if not isinstance(target, str) or not BRAIN_ID.fullmatch(target):
                raise Fault('invalid_brain')
            key = 'brain:' + target
        elif level == 'overall':
            key = 'overall'
        else:
            raise Fault('not_found', 404)
        with self.lock:
            with self.store.transaction() as db:
                p = self._hosted(db, bearer)
                row = self._control(db, p, key)
                if (row['version'] if row else 0) != body['version']:
                    raise Fault('budget_changed', 409)
                if level == 'brain' and row is None:
                    self._spec(target)  # A budget for a brain that is not plugged in is refused.
                now = self.store.now()
                if row is None:
                    db.execute('INSERT INTO hub_controls VALUES (?,?,?,?,?,?,?,?)',
                               (p['scope'], p['id'], key, 'active', None, canonical(budget) if budget else None, 1, now))
                else:
                    db.execute('UPDATE hub_controls SET budget=?,version=version+1,updated=? WHERE scope=? AND actor=? AND target=?',
                               (canonical(budget) if budget else None, now, p['scope'], p['id'], key))
                self._journal(db, p, key, 'budget.set', body['version'] + 1, {'budget': budget})
            self._enforce(brain=target if level == 'brain' else None)
            return self.view(bearer)

    # Operator controls -------------------------------------------------------

    def control(self, bearer, level, target, operation, body):
        """Pause, resume, stop or reassign a goal; pause, resume or stop a brain; pause or
        resume the whole hub. Owner only, version-checked, journalled and audited."""
        if level not in OPERATIONS or operation not in OPERATIONS[level]:
            raise Fault('not_found', 404)
        exact(body, {'version', 'brain'} if operation == 'reassign' else {'version'})
        if type(body['version']) is not int or body['version'] < 0:
            raise Fault('invalid_version')
        if level == 'brain' and (not isinstance(target, str) or not BRAIN_ID.fullmatch(target)):
            raise Fault('invalid_brain')
        with self.lock:
            with self.store.transaction() as db:
                p = self._hosted(db, bearer)
                if level == 'goal':
                    cancel = self._goal_control(db, p, target, operation, body)
                else:
                    cancel = self._target_control(db, p, level, target, operation, body)
            self._cancel(cancel)
            return self.view(bearer)

    def _lifecycle_stop(self, p, subject):
        """Written before the database changes, so a restore replays the stop."""
        from . import lifecycle
        lifecycle.append(self.store, {'kind': 'hub_stopped', 'scope': p['scope'], 'actor': p['id'], 'subject': subject,
                                      'at': self.store.now(), 'by': p['id']})

    def _goal_control(self, db, p, mandate_id, operation, body):
        row = self._mandate(db, p, mandate_id, body['version'])
        if row['state'] == 'stopped':
            raise Fault('goal_stopped', 409)
        if operation == 'pause':
            if row['state'] != 'active':
                raise Fault('goal_not_running', 409)
            return self._hold(db, p, 'goal', row['id'], 'paused', 'operator')
        if operation == 'stop':
            self._lifecycle_stop(p, 'goal:' + row['id'])
            return self._hold(db, p, 'goal', row['id'], 'stopped', 'operator')
        if operation == 'resume':
            if row['state'] != 'paused':
                raise Fault('goal_not_paused', 409)
            self._still_spent(db, p, 'goal', row['id'])
            now = self.store.now()
            db.execute("UPDATE hub_mandates SET state='active',state_reason=NULL,version=version+1,updated=? WHERE id=?",
                       (now, row['id']))
            self._journal(db, p, 'goal:' + row['id'], 'goal.resumed', row['version'] + 1, {'previous_reason': row['state_reason']})
            return []
        brain = body['brain']
        if not isinstance(brain, str) or not BRAIN_ID.fullmatch(brain):
            raise Fault('invalid_brain')
        if brain not in json.loads(row['brains']):
            raise Fault('brain_not_in_mandate', 403)
        if brain == row['assigned_brain']:
            raise Fault('brain_already_assigned', 409)
        self._brain_fits(db, p, brain, row['scope_class'])
        control = self._control(db, p, 'brain:' + brain)
        if control and control['state'] != 'active':
            raise Fault('brain_' + control['state'], 409)
        db.execute('UPDATE hub_mandates SET assigned_brain=?,version=version+1,updated=? WHERE id=?',
                   (brain, self.store.now(), row['id']))
        self._journal(db, p, 'goal:' + row['id'], 'goal.reassigned', row['version'] + 1,
                      {'from': row['assigned_brain'], 'to': brain})
        # Work in flight for this goal on the previous brain is moved, not left running.
        return [j for j in self._in_flight(db, p, 'goal', row['id'])
                if db.execute('SELECT brain FROM hub_tasks WHERE job_id=?', (j,)).fetchone()['brain'] == row['assigned_brain']]

    def _target_control(self, db, p, level, target, operation, body):
        key = 'overall' if level == 'overall' else 'brain:' + target
        row = self._control(db, p, key)
        if (row['version'] if row else 0) != body['version']:
            raise Fault('control_changed', 409)
        if level == 'brain' and row is None:
            named = any(target in json.loads(r[0]) for r in db.execute(
                'SELECT brains FROM hub_mandates WHERE scope=? AND actor=?', (p['scope'], p['id'])))
            if not named:
                self._spec(target)  # Unknown brains cannot be controlled.
        state = row['state'] if row else 'active'
        if state == 'stopped':
            raise Fault('brain_stopped', 409)
        if operation == 'pause':
            if state != 'active':
                raise Fault('already_paused', 409)
            return self._hold(db, p, level, target, 'paused', 'operator')
        if operation == 'stop':
            self._lifecycle_stop(p, key)
            return self._hold(db, p, level, target, 'stopped', 'operator')
        if state != 'paused':
            raise Fault('not_paused', 409)
        self._still_spent(db, p, level, target)
        db.execute("UPDATE hub_controls SET state='active',reason=NULL,version=version+1,updated=? WHERE scope=? AND actor=? AND target=?",
                   (self.store.now(), p['scope'], p['id'], key))
        self._journal(db, p, key, level + '.resumed', row['version'] + 1, {'previous_reason': row['reason']})
        return []

    def acknowledge(self, bearer, attention_id, body):
        exact(body, set())
        ident(attention_id)
        with self.lock, self.store.transaction() as db:
            p = self._hosted(db, bearer)
            row = db.execute('SELECT * FROM hub_attention WHERE id=? AND scope=? AND actor=?',
                             (attention_id, p['scope'], p['id'])).fetchone()
            if not row:
                raise Fault('attention_not_found', 404)
            if row['state'] == 'open':
                db.execute("UPDATE hub_attention SET state='acknowledged' WHERE id=?", (attention_id,))
                self._journal(db, p, row['target'], 'attention.acknowledged', None, {'attention': attention_id})
            return self._attention_view(db.execute('SELECT * FROM hub_attention WHERE id=?', (attention_id,)).fetchone())

    # The supervisor cycle ----------------------------------------------------

    def cycle(self):
        """Called by the existing supervisor; no thread of its own. Accounts finished tasks
        (ingesting each result through the brain hub), runs the declared checks once on each
        newly accepted result, and then runs due heartbeats."""
        with self.lock:
            try:
                with self.store.transaction() as db:
                    self._hosted(db, self.host)
            except Fault:
                return  # Authority lost: nothing is submitted, ingested or cancelled.
            self._account()
            self._auto_verify()
            self._heartbeats()

    def _account(self):
        with self.store.connection() as db:
            pending = [r[0] for r in db.execute('''SELECT job_id FROM hub_tasks WHERE scope=? AND actor=? AND accounted IS NULL
                ORDER BY created,job_id LIMIT ?''', (self.scope, self.host_id, ACCOUNT_PER_CYCLE))]
        touched = []
        for job_id in pending:
            try:
                job = self.jobs.view(self.host, job_id)
            except Fault:
                continue
            if not job['finished']:
                continue
            declared = bool(((job.get('parameters') or {}).get('packet') or {}).get('acceptance'))
            try:
                result = self.brains.ingest(self.host, job_id)['status']
            except Fault as exc:
                result = 'not_ingested_' + exc.code if plug.REASON.fullmatch(exc.code) else 'not_ingested'
            with self.store.transaction() as db:
                task = db.execute('SELECT * FROM hub_tasks WHERE job_id=?', (job_id,)).fetchone()
                if task['accounted'] is not None:
                    continue
                meter = db.execute('SELECT * FROM hub_meter WHERE job_id=?', (job_id,)).fetchone()
                if meter and meter['state'] == 'finished':
                    used, basis = (meter['tokens'], meter['money_pence'], meter['wall_seconds']), 'metered'
                elif meter:
                    used, basis = (task['ceil_tokens'], task['ceil_money'], task['ceil_wall']), 'unknown_charged_at_ceiling'
                else:
                    used, basis = (0, 0, 0), 'brain_not_started'
                auto = 'pending' if result == 'accepted' and declared else 'not_needed'
                db.execute('''UPDATE hub_tasks SET accounted=?,used_tokens=?,used_money=?,used_wall=?,usage_basis=?,result=?,
                    auto_verify=? WHERE job_id=?''', (self.store.now(), *used, basis, result[:80], auto, job_id))
                self.store.log(db, task['scope'], task['actor'], 'hub.task_accounted', job_id)
                touched.append((task['mandate'], task['brain']))
        for mandate, brain in dict.fromkeys(touched):
            self._enforce(mandate=mandate, brain=brain, cause=brain)

    def _auto_verify(self):
        """Run the declared checks once on each newly accepted result, as the host, recorded
        as ``automatic``. Never again automatically: later runs are the owner's, through
        ``verify_result``. A run that cannot start is recorded and the cycle carries on; a check
        that crashes inside a run is already ``unverifiable`` (``Verifier._check``). A task left
        ``pending`` by a stopped process is finished on the next cycle, unless a run was already
        recorded: the run is made only at zero runs, checked in the same transaction that records
        it, so neither a restart nor the owner verifying at the same moment gives a second run."""
        with self.store.connection() as db:
            pending = [r[0] for r in db.execute('''SELECT job_id FROM hub_tasks WHERE scope=? AND actor=?
                AND auto_verify='pending' ORDER BY accounted,job_id LIMIT ?''', (self.scope, self.host_id, ACCOUNT_PER_CYCLE))]
        for job_id in pending:
            outcome = 'ran'
            try:
                self.verifier.verify(self.host, job_id, expected_runs=0, initiated='automatic')
            except Fault as exc:
                if exc.code != 'verification_changed':  # Otherwise a run already exists: nothing to add.
                    outcome = 'not_run:' + exc.code if plug.REASON.fullmatch(exc.code) else 'not_run'
            except Exception:  # Whatever went wrong, the other tasks and the heartbeats still run.
                outcome = 'not_run'
            with self.store.transaction() as db:
                db.execute("UPDATE hub_tasks SET auto_verify=? WHERE job_id=? AND auto_verify='pending'", (outcome[:80], job_id))
                if outcome != 'ran':
                    self.store.log(db, self.scope, self.host_id, 'hub.auto_verify_not_run', job_id)

    def _heartbeats(self):
        with self.store.connection() as db:
            due = [tuple(r) for r in db.execute('''SELECT id,next_due FROM hub_mandates WHERE scope=? AND actor=? AND next_due>0
                AND next_due<=? ORDER BY next_due,id LIMIT ?''', (self.scope, self.host_id, self.store.now(), BEATS_PER_CYCLE))]
        for mandate_id, due_at in due:
            self._beat(mandate_id, due_at)

    def _beat(self, mandate_id, due):
        """One heartbeat for the latest due slot. Slots missed meanwhile are counted, never run."""
        slot = f'due:{due}'
        with self.store.transaction() as db:
            row = db.execute('SELECT * FROM hub_mandates WHERE id=?', (mandate_id,)).fetchone()
            if row['next_due'] != due or not row['schedule']:
                return
            now = self.store.now()
            schedule = json.loads(row['schedule'])
            missed = missed_slots(schedule, due, now) - 1
            db.execute('UPDATE hub_mandates SET next_due=?,missed_total=missed_total+? WHERE id=?',
                       (next_slot(_clock(schedule), now), missed, mandate_id))
            if missed:
                # Slots that fell while the host was not running: counted, never replayed.
                self._journal(db, {'scope': self.scope, 'id': self.host_id}, 'heartbeats', 'heartbeat.missed', None,
                              {'mandate': mandate_id, 'brain': row['assigned_brain'], 'missed': missed, 'due': due})
            reason = None
            try:
                self._admissible(db, row, row['assigned_brain'], now)
            except Fault as exc:
                reason = exc.code
        status, job_id = 'skipped', None
        if reason is None:
            try:
                submitted = self._submit(self.host, row, schedule['task'], row['assigned_brain'], 'heartbeat', slot)
                status, job_id = 'submitted', submitted['job']['id']
            except Fault as exc:
                status, reason = 'refused', exc.code
        identity = 'hub-beat-' + hashlib.sha256(f'{self.scope}|{mandate_id}|{slot}'.encode()).hexdigest()[:24]
        with self.store.transaction() as db:
            db.execute('INSERT OR IGNORE INTO hub_heartbeats VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (identity, self.scope, self.host_id, mandate_id, slot, self.store.now(), status, reason, missed, job_id))
            self.store.log(db, self.scope, self.host_id, 'hub.heartbeat_' + status, mandate_id)
            db.execute('''DELETE FROM hub_heartbeats WHERE scope=? AND id IN (SELECT id FROM hub_heartbeats WHERE scope=?
                ORDER BY at DESC,rowid DESC LIMIT -1 OFFSET ?)''', (self.scope, self.scope, KEEP_HEARTBEATS))

    # Reads -------------------------------------------------------------------

    def _usage_view(self, db, p, level, target, budget, now):
        if budget is None:
            return None
        periods = {}
        for period, since in self._periods(budget, now):
            used, reserved = self._measure(db, p, level, target, since)
            dims = {}
            for dimension in DIMENSIONS:
                limit = budget[period][dimension]
                dims[dimension] = {'used': used[dimension], 'in_flight': reserved[dimension], 'limit': limit,
                                   'spent': limit is not None and self._spent(used[dimension], reserved[dimension], limit),
                                   'warning': limit is not None and limit > 0
                                   and used[dimension] * 100 >= limit * budget['warn_percent']}
            periods[period] = {'since': since, 'dimensions': dims}
        return periods

    @staticmethod
    def _attention_view(row):
        return {'id': row['id'], 'target': row['target'], 'period': row['period'], 'since': row['period_start'],
                'dimension': row['dimension'], 'level': row['level'], 'used': row['used'], 'limit': row['limit_value'],
                'at': row['at'], 'state': row['state'], 'basis': 'measured_usage_against_owner_budget'}

    def _brain_view(self, db, p, brain_id, now):
        try:
            spec = self._spec(brain_id)
        except Fault:
            spec = None
        control = self._control(db, p, 'brain:' + brain_id)
        budget = json.loads(control['budget']) if control and control['budget'] else None
        return {'id': brain_id, 'registered': spec is not None, 'label': spec.label if spec else None,
                'locality': spec.locality if spec else None, 'version': spec.version if spec else None,
                'scopes': sorted(spec.scopes) if spec else [], 'tools': sorted(spec.tools) if spec else [],
                'max_autonomy': spec.max_autonomy if spec else None,
                'state': control['state'] if control else 'active', 'reason': control['reason'] if control else None,
                'control_version': control['version'] if control else 0, 'budget': budget,
                'usage': self._usage_view(db, p, 'brain', brain_id, budget, now)}

    def _mandate_view(self, db, p, row, now):
        goal = self._goal(db, p, row['goal'])
        settings = self._stored(row)
        tasks = []
        for t in db.execute('SELECT * FROM hub_tasks WHERE mandate=? ORDER BY created DESC,rowid DESC LIMIT ?', (row['id'], VIEW_TASKS)):
            job = db.execute('SELECT state,reason FROM jobs WHERE id=?', (t['job_id'],)).fetchone()
            tasks.append({'job': t['job_id'], 'work': t['work'], 'brain': t['brain'], 'autonomy': t['autonomy'],
                          'trigger': t['trigger'], 'created': t['created'], 'job_state': job['state'] if job else None,
                          'job_reason': job['reason'] if job else None, 'result': t['result'], 'accounted': t['accounted'],
                          'usage': None if t['accounted'] is None else {
                              'tokens': t['used_tokens'], 'money_pence': t['used_money'], 'wall_seconds': t['used_wall'],
                              'basis': t['usage_basis']},
                          'ceiling': {'tokens': t['ceil_tokens'], 'money_pence': t['ceil_money'], 'wall_seconds': t['ceil_wall']}})
        beats = [{'slot': b['slot'], 'at': b['at'], 'status': b['status'], 'reason': b['reason'], 'missed': b['missed'],
                  'job': b['job_id']}
                 for b in db.execute('SELECT * FROM hub_heartbeats WHERE mandate=? ORDER BY at DESC,rowid DESC LIMIT ?',
                                     (row['id'], VIEW_BEATS))]
        return {'id': row['id'], 'version': row['version'], 'state': row['state'], 'state_reason': row['state_reason'],
                'goal': {'id': row['goal'], 'title': goal['title'] if goal else None,
                         'status': goal['status'] if goal else None, 'available': bool(goal)},
                'scope_class': row['scope_class'], 'deadline': row['deadline'], 'expired': now >= row['deadline'],
                'success_test': row['success_test'],
                'autonomy': {k: {'level': v, 'name': plug.AUTONOMY[v]} for k, v in settings['autonomy'].items()},
                'brains': settings['brains'], 'assigned_brain': row['assigned_brain'], 'tools': settings['tools'],
                'budget': settings['budget'], 'usage': self._usage_view(db, p, 'goal', row['id'], settings['budget'], now),
                'schedule': settings['schedule'], 'next_due': row['next_due'] or None, 'missed_total': row['missed_total'],
                'tasks': tasks, 'heartbeats': beats, 'created': row['created'], 'updated': row['updated'],
                'acceptance': [{'id': f'C{n}', **check} for n, check in enumerate(settings[OPTIONAL] or [], 1)],
                'acceptance_declared_by': 'mandate' if settings[OPTIONAL] else None,
                'basis': 'owner_authored_limits_not_a_grant', 'success_test_evaluated': False}

    def view(self, bearer):
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            now = self.store.now()
            base = {'scope': p['scope'], 'now': now, 'model_used': False, 'authority_granted': False,
                    'autonomy_levels': [{'level': k, 'name': v, 'enforced': k in plug.ENFORCED_AUTONOMY}
                                        for k, v in plug.AUTONOMY.items()],
                    'dimensions': list(DIMENSIONS), 'periods': list(PERIODS)}
            if p['role'] != 'owner' or p['scope'] != self.scope or p['id'] != self.host_id:
                return {**base, 'available': False, 'reason': 'owner_only' if p['role'] != 'owner' else 'not_hosted',
                        'goals': [], 'unlinked_goals': [], 'brains': [], 'overall': None, 'attention': [], 'journal': []}
            rows = db.execute('''SELECT * FROM hub_mandates WHERE scope=? AND actor=?
                ORDER BY state='stopped',created DESC,id''', (p['scope'], p['id'])).fetchall()
            goals = [self._mandate_view(db, p, r, now) for r in rows]
            linked = {r['goal'] for r in rows if r['state'] != 'stopped'}
            unlinked = [self.store.opened('executive_records', r) for r in db.execute(
                "SELECT id,title,version FROM executive_records WHERE scope=? AND actor=? AND kind='goal' AND status='active' ORDER BY created,id",
                (p['scope'], p['id'])) if r['id'] not in linked]
            named = {b for r in rows for b in json.loads(r['brains'])} | {s.id for s in self.registry.specs()}
            named |= {r[0][len('brain:'):] for r in db.execute(
                "SELECT target FROM hub_controls WHERE scope=? AND actor=? AND target LIKE 'brain:%'", (p['scope'], p['id']))}
            overall = self._control(db, p, 'overall')
            overall_budget = json.loads(overall['budget']) if overall and overall['budget'] else None
            attention = [self._attention_view(r) for r in db.execute(
                "SELECT * FROM hub_attention WHERE scope=? AND actor=? ORDER BY state='acknowledged',at DESC,id LIMIT ?",
                (p['scope'], p['id'], VIEW_ATTENTION))]
            journal = [{'seq': r['seq'], 'target': r['target'], 'event': r['event'], 'version': r['version'], 'at': r['at']}
                       for r in db.execute('SELECT * FROM hub_journal WHERE scope=? AND actor=? ORDER BY seq DESC LIMIT ?',
                                           (p['scope'], p['id'], VIEW_JOURNAL))]
            return {**base, 'available': True, 'reason': None, 'workspace_paused': self._workspace_paused(db, p['scope']),
                    'goals': goals, 'unlinked_goals': unlinked,
                    'brains': [self._brain_view(db, p, b, now) for b in sorted(named)],
                    'overall': {'state': overall['state'] if overall else 'active', 'reason': overall['reason'] if overall else None,
                                'version': overall['version'] if overall else 0, 'budget': overall_budget,
                                'usage': self._usage_view(db, p, 'overall', None, overall_budget, now)},
                    'attention': attention, 'journal': journal,
                    'policy': {'permitted_tools': sorted(self.policy.permitted_tools),
                               'cloud_scopes': sorted(self.policy.cloud_scopes)}}

    # Verification of results (H4) ----------------------------------------------

    @staticmethod
    def _work_of(db, row):
        """The goal work a result served, if the hub admitted it: identifiers and the title only."""
        task = db.execute('SELECT mandate,goal,work,trigger,actor,scope FROM hub_tasks WHERE job_id=?', (row['job'],)).fetchone()
        if not task:
            return None
        goal = sealing.open_row(sealing.of(db), 'executive_records', db.execute(
            'SELECT id,title FROM executive_records WHERE id=? AND scope=? AND actor=?', (task['goal'], task['scope'], task['actor'])).fetchone())
        return {'mandate': task['mandate'], 'goal': task['goal'], 'goal_title': goal['title'] if goal else None,
                'work': task['work'], 'trigger': task['trigger']}

    @staticmethod
    def _last_run(db, job_id):
        """The latest run's position, hash, outcome and per-check statuses. No reasons."""
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='verification_results'").fetchone():
            return None
        row = db.execute('''SELECT r.position,r.outcome,r.report,r.report_sha256,r.initiated FROM verification_results v
            JOIN verification_runs r ON r.id=v.last_run WHERE v.job_id=?''', (job_id,)).fetchone()
        if not row:
            return None
        report = json.loads(row['report'])
        return {'position': row['position'], 'outcome': row['outcome'], 'sha256': row['report_sha256'],
                'initiated': row['initiated'] or 'owner', 'counts': report['counts'],
                'checks': [{'id': c['id'], 'kind': c['kind'], 'status': c['status']} for c in report['checks']]}

    def results(self, bearer):
        """The caller's own brain results of the last 30 days, newest first, each with ALFRED's
        routing evidence class, and the counts per brain. Person-private (policy.ledger)."""
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            now = self.store.now()
            base = {'classes': list(verification.EVIDENCE), 'window_days': RESULTS_WINDOW // DAY,
                    'basis': verification.BASIS, 'limits': verification.LIMITS, 'brain_claims_counted': False,
                    'no_checks_counted_as_verified': False, 'model_used': False, 'authority_granted': False}
            if p['role'] != 'owner':
                return {**base, 'available': False, 'reason': 'owner_only', 'results': [], 'by_brain': {}}
            rows = verification.outcome_rows(db, p['scope'], verification.submitters(db, p), since=now - RESULTS_WINDOW,
                                             limit=RESULTS_SCAN)
            by_brain = {}
            for row in rows:
                counts = by_brain.setdefault(row['brain'], {'results': 0, **dict.fromkeys(verification.EVIDENCE, 0)})
                counts['results'] += 1
                counts[row['evidence']] += 1
            listed = []
            for row in reversed(rows[-VIEW_RESULTS:]):
                listed.append({'job': row['job'], 'brain': row['brain'], 'task_id': row['task_id'],
                               'scope_class': row['scope_class'], 'contract': row['contract'],
                               'contract_reason': row['reason'], 'declared': row['declared'], 'checks': row['checks'],
                               'state': row['state'], 'evidence': row['evidence'], 'runs': row['runs'],
                               'acknowledged_over': row['acknowledged_over'], 'ingested_at': row['ingested_at'],
                               'updated_at': row['updated_at'], 'work': self._work_of(db, row),
                               'last_run': self._last_run(db, row['job'])})
            return {**base, 'available': True, 'reason': None, 'results': listed, 'by_brain': by_brain,
                    'scanned': len(rows)}

    def result(self, bearer, job_id):
        """One of the caller's results: its verification state, declared checks and runs. A
        check's reasons can quote what the brain returned, so they are withheld when the
        result's sources can no longer be read under the person's grants."""
        state = self.verifier.state(bearer, job_id)  # Submitter only; anyone else is told it does not exist.
        runs = self.verifier.runs(bearer, job_id)
        with self.store.transaction() as db:
            self.store.authenticate(db, bearer, {'owner'})
            envelope = db.execute('SELECT envelope_sha256 FROM brain_results WHERE job_id=?', (job_id,)).fetchone()[0]
            work = self._work_of(db, {'job': job_id})
        readable = False
        if envelope:
            try:
                self.jobs.artefact(bearer, envelope)
                readable = True
            except Fault:
                readable = False
        packet = self.jobs.view(bearer, job_id)['parameters']['packet']
        acceptance = packet.get('acceptance')

        def shown(report):
            if readable:
                return report
            return {**report, 'checks': [{**c, 'reasons': [], 'detail': {}, 'truncated': False} for c in report['checks']],
                    'reasons_withheld': True}

        if state.get('last_run'):
            state = {**state, 'last_run': {**state['last_run'], 'report': shown(state['last_run']['report'])}}
        return {'result': state, 'work': work, 'sources_readable': readable,
                'declared': {'by': acceptance['declared_by'], 'ref': acceptance['ref'], 'checks': acceptance['checks']}
                if acceptance else None,
                'runs': [{**run, 'report': shown(run['report'])} for run in runs[-VIEW_RUNS:]], 'runs_total': len(runs),
                'basis': verification.BASIS, 'limits': verification.LIMITS, 'brain_claims_counted': False,
                'authority_granted': False}

    def verify_result(self, bearer, job_id, body):
        """Run the declared checks again, at the number of runs the owner saw."""
        exact(body, {'runs'})
        self.verifier.verify(bearer, job_id, expected_runs=body['runs'])
        return self.result(bearer, job_id)

    def acknowledge_result(self, bearer, job_id, body):
        """The owner accepts the exact run they saw; explicitly over failed checks."""
        exact(body, {'run_sha256', 'accept_failures'})
        self.verifier.acknowledge(bearer, job_id, body['run_sha256'], accept_failures=body['accept_failures'])
        return self.result(bearer, job_id)


def apply_stop(db, entry):
    """Replay a journalled stop into a database (live or restored). Idempotent."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hub_mandates'").fetchone():
        return 0
    subject, scope, actor = entry['subject'], entry['scope'], entry.get('actor')
    if subject.startswith('goal:'):
        return db.execute("""UPDATE hub_mandates SET state='stopped',state_reason='operator',next_due=0,version=version+1
            WHERE id=? AND scope=? AND state!='stopped'""", (subject[len('goal:'):], scope)).rowcount
    row = db.execute('SELECT state FROM hub_controls WHERE scope=? AND actor=? AND target=?', (scope, actor, subject)).fetchone()
    if row is None:
        db.execute("INSERT INTO hub_controls VALUES (?,?,?,'stopped','operator',NULL,1,?)", (scope, actor, subject, entry.get('at', 0)))
        return 1
    return db.execute("""UPDATE hub_controls SET state='stopped',reason='operator',version=version+1
        WHERE scope=? AND actor=? AND target=? AND state!='stopped'""", (scope, actor, subject)).rowcount


# HTTP ------------------------------------------------------------------------

MANDATE = r'(mandate-[0-9a-f]{24})'
JOB = r'(job-[0-9a-f]{24})'
DRAFT = r'(bp-[0-9a-f]{24})'
ROUTES = (
    (re.compile(r'/desk/hub/mandates'), 'create'),
    (re.compile(rf'/desk/hub/mandates/{MANDATE}'), 'update'),
    (re.compile(rf'/desk/hub/mandates/{MANDATE}/tasks'), 'task'),
    (re.compile(rf'/desk/hub/mandates/{MANDATE}/(pause|resume|stop|reassign)'), 'goal'),
    (re.compile(r'/desk/hub/brains/([a-z0-9][a-z0-9_.-]{0,63})/(pause|resume|stop)'), 'brain'),
    (re.compile(r'/desk/hub/brains/([a-z0-9][a-z0-9_.-]{0,63})/budget'), 'brain_budget'),
    (re.compile(r'/desk/hub/overall/(pause|resume)'), 'overall'),
    (re.compile(r'/desk/hub/overall/budget'), 'overall_budget'),
    (re.compile(r'/desk/hub/attention/([A-Za-z0-9][A-Za-z0-9_.-]{0,79})/acknowledge'), 'acknowledge'),
    (re.compile(rf'/desk/hub/results/{JOB}/verify'), 'verify_result'),
    (re.compile(rf'/desk/hub/results/{JOB}/acknowledge'), 'acknowledge_result'),
    (re.compile(rf'/desk/hub/drafts/{DRAFT}/confirm'), 'confirm_draft'),
    (re.compile(rf'/desk/hub/drafts/{DRAFT}/dismiss'), 'dismiss_draft'),
)


def route(server, path, mutation, bearer, body):
    """Hub routes, reached only through the guarded desk handler: loopback Host and Origin,
    the session cookie and, for every POST, the CSRF token have already been checked."""
    hub = getattr(server, 'goals', None)
    if hub is None:
        raise Fault('hub_not_configured', 409)
    if not mutation:
        if path == '/desk/hub':
            return hub.view(bearer)
        if path == '/desk/hub/results':
            return hub.results(bearer)
        if path == '/desk/hub/drafts':
            # The agent drafts list (docs/AGENT_DRAFTS.md), kept by the brain hub itself.
            return hub.brains.drafts(bearer)
        match = re.fullmatch(rf'/desk/hub/results/{JOB}', path)
        if match:
            return hub.result(bearer, match[1])
        raise Fault('not_found', 404)
    for pattern, name in ROUTES:
        match = pattern.fullmatch(path)
        if not match:
            continue
        if name == 'create':
            return hub.create_mandate(bearer, body)
        if name == 'update':
            return hub.update_mandate(bearer, match[1], body)
        if name == 'task':
            return hub.submit_task(bearer, match[1], body)
        if name == 'goal':
            return hub.control(bearer, 'goal', match[1], match[2], body)
        if name == 'brain':
            return hub.control(bearer, 'brain', match[1], match[2], body)
        if name == 'brain_budget':
            return hub.set_budget(bearer, 'brain', match[1], body)
        if name == 'overall':
            return hub.control(bearer, 'overall', None, match[1], body)
        if name == 'overall_budget':
            return hub.set_budget(bearer, 'overall', None, body)
        if name == 'verify_result':
            return hub.verify_result(bearer, match[1], body)
        if name == 'acknowledge_result':
            return hub.acknowledge_result(bearer, match[1], body)
        if name == 'confirm_draft':
            return hub.brains.confirm_places(bearer, match[1], body)
        if name == 'dismiss_draft':
            return hub.brains.dismiss_draft(bearer, match[1], body)
        return hub.acknowledge(bearer, match[1], body)
    raise Fault('not_found', 404)
