"""Goals, mandates, heartbeats and budgets for the agent hub (AGENT_HUB.md step H2).

Synthetic data only. The only brains are the deterministic rule-based SyntheticBrain from
H1 and two small fixtures defined here: no model, no network, no files. Real SQLite, the
real job coordinator and worker, the real executive goal records, the real lifecycle
journal and real HTTP where the boundary matters. These tests prove that work for a goal
is admitted, scheduled, metered, warned, stopped and controlled by ALFRED, not by a brain.
"""
import copy
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from alfred import brain as plug
from alfred import lifecycle
from alfred.brain import Brain, BrainHub, BrainPolicy, BrainRegistry, BrainSpec, SyntheticBrain
from alfred.executive import ExecutiveRecords
from alfred.hub_goals import GoalHub, missed_slots
from alfred.jobs import JobCoordinator, JobWorker
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor, MarkdownVault
from alfred.local import Fault
from alfred.routines import next_slot
import stored_helpers as stored
from grant_helpers import grant_all

DAY, HOUR = 86400, 3600
T = 1_900_000_000  # 2030-03-17 17:46:40 UTC
WORKSPACE = 'ws-hub-4410'
PLAN = '# Plan\nAlpha review is due on Friday.\nremember: Producers prefer short drafts.\n\nOutside line.\n'
TASK_BUDGET = {'wall_seconds': 10, 'tokens': 30, 'money_pence': 0, 'steps': 50}
NONE = {'tokens': None, 'money_pence': None, 'wall_seconds': None, 'tasks': None}


def budget(daily=None, total=None, warn=80, offset=0):
    return {'daily': {**NONE, **(daily or {})}, 'total': {**NONE, **(total or {})}, 'warn_percent': warn,
            'utc_offset_minutes': offset}


class ScheduleBrain(Brain):
    """A brain that tries to schedule itself: a proposal and, optionally, an extra bundle field."""

    def __init__(self, extra_field=False):
        self.spec = BrainSpec(id='scheduler', label='Self-scheduling fixture', locality='local', version='1',
                              scopes=frozenset(plug.SCOPE_CLASSES), tools=frozenset(), max_autonomy=2)
        self.extra_field = extra_field

    def run(self, packet, meter):
        meter.step(tokens=3)
        bundle = {'bundle_version': 1, 'answer': {'text': 'I will run again every hour.', 'citations': []},
                  'artefacts': [], 'memory_suggestions': [],
                  'proposed_actions': [{'capability': 'hub.schedule', 'parameters': {'every_hours': 1, 'goal': packet['goal']['ref']},
                                        'reason': 'Wake me again.', 'cites': []}],
                  'work_log': [{'step': 1, 'kind': 'reason', 'tool': None, 'summary': 'Decided to schedule myself.'}]}
        if self.extra_field:
            bundle['schedule'] = {'every_hours': 1}
        return bundle


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.clock = [T]
        self.store = KnowledgeStore(self.root / 'desk.sqlite', clock=lambda: self.clock[0])
        provision = self.store.provision
        self.owner = provision(WORKSPACE, 'owner', 'owner', ttl=30 * DAY)
        self.second = provision(WORKSPACE, 'owner-2', 'owner', ttl=30 * DAY)
        self.reader = provision(WORKSPACE, 'reader', 'reader', ttl=30 * DAY)
        self.source = provision(WORKSPACE, 'source', 'source', ttl=30 * DAY)
        grant_all(self.store, self.owner)
        (self.root / 'project').mkdir()
        self.vault = self.root / 'vault'
        self.vault.mkdir()
        (self.vault / 'Plan.md').write_text(PLAN)
        MarkdownVault(self.store, self.source, self.vault).scan()
        self.note = next(n for n in self.store.knowledge(self.owner)['nodes'] if n['title'] == 'Plan')
        self.jobs = JobCoordinator(self.store)
        self.jobs.enrol_worker(self.owner, 'brain-1', 'Brain worker', ['brain_task'])
        self.registry = BrainRegistry()
        self.seen, self.seen_b = [], []
        self.registry.register(SyntheticBrain(seen=self.seen))
        self.registry.register(SyntheticBrain(BrainSpec(id='synthetic-b', label='Second synthetic brain', locality='local',
                                                        version='1', scopes=frozenset(plug.SCOPE_CLASSES),
                                                        tools=frozenset({'calculator'}), max_autonomy=2), seen=self.seen_b))
        self.policy = BrainPolicy(permitted_tools=('calculator',))
        self.brains = BrainHub(self.store, self.jobs, self.registry, self.policy)
        self.hub = GoalHub(self.store, self.brains, self.owner)
        self.records = ExecutiveRecords(self.store)
        self.goal = self.make_goal('Deliver the quarterly review')
        self.seq = 0
        self.set_overall(budget(total={'tasks': 100}))

    # Helpers ------------------------------------------------------------------

    def make_goal(self, title, kind='goal'):
        self.seq = getattr(self, 'seq', 0) + 1
        return self.records.create(self.owner, {'request_id': f'g{self.seq}-{kind}', 'kind': kind, 'title': title, 'detail': '',
                                                'project': None, 'due': None, 'rank': None, 'support': None})

    def fault(self, code, call, *args, **kwargs):
        with self.assertRaises(Fault) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def rows(self, sql, *args):
        with self.store.connection() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def selection(self):
        return [{'note': self.note['id'], 'start_line': 2, 'end_line': 3}]

    def template(self, **over):
        value = {'work': 'research', 'instruction': 'Summarise the plan.', 'context': self.selection(), 'learned': [],
                 'tools': [], 'budget': dict(TASK_BUDGET), 'autonomy': 1}
        value.update(over)
        return value

    def mandate_body(self, **over):
        self.seq += 1
        value = {'request_id': f'mandate-request-{self.seq}', 'goal': self.goal['id'], 'scope_class': 'company',
                 'deadline': T + 20 * DAY, 'success_test': 'The producer approves the review deck.',
                 'autonomy': {'research': 1, 'drafting': 2}, 'brains': ['synthetic', 'synthetic-b'],
                 'assigned_brain': 'synthetic', 'tools': ['calculator'], 'budget': budget(total={'tasks': 50}), 'schedule': None}
        value.update(over)
        return value

    def mandate(self, **over):
        return self.hub.create_mandate(self.owner, self.mandate_body(**over))

    def current(self, mandate_id):
        return next(g for g in self.hub.view(self.owner)['goals'] if g['id'] == mandate_id)

    def task(self, mandate_id, bearer=None, **over):
        self.seq += 1
        body = {'request_id': f'task-{self.seq}', 'brain': None, **self.template()}
        body.update(over)
        return self.hub.submit_task(bearer or self.owner, mandate_id, body)

    def worker(self):
        return JobWorker(self.jobs, self.hub.backend(), self.owner, 'brain-1', poll_seconds=0.01, heartbeat_seconds=0.05)

    def run_task(self, mandate_id, **over):
        submitted = self.task(mandate_id, **over)
        self.assertEqual(self.worker().run_once(), submitted['job']['id'])
        self.hub.cycle()
        return submitted['job']['id']

    def hub_task(self, job_id):
        return self.rows('SELECT * FROM hub_tasks WHERE job_id=?', job_id)[0]

    def set_overall(self, value):
        version = self.hub.view(self.owner)['overall']['version']
        return self.hub.set_budget(self.owner, 'overall', None, {'version': version, 'budget': value})

    def brain_view(self, brain_id):
        return next(b for b in self.hub.view(self.owner)['brains'] if b['id'] == brain_id)

    def control(self, level, target, operation, **extra):
        if level == 'goal':
            version = self.current(target)['version']
        elif level == 'brain':
            version = self.brain_view(target)['control_version']
        else:
            version = self.hub.view(self.owner)['overall']['version']
        return self.hub.control(self.owner, level, target, operation, {'version': version, **extra})

    def journal(self, event=None):
        rows = stored.rows(self.store, 'hub_journal', 'SELECT * FROM hub_journal ORDER BY seq')
        return [r for r in rows if event is None or r['event'] == event]


class MandateTests(Base):
    def test_a_mandate_links_an_executive_goal_with_its_limits(self):
        view = self.mandate()
        self.assertEqual(view['goal'], {'id': self.goal['id'], 'title': 'Deliver the quarterly review', 'status': 'active',
                                        'available': True})
        self.assertEqual((view['state'], view['version'], view['scope_class'], view['assigned_brain']),
                         ('active', 1, 'company', 'synthetic'))
        self.assertEqual(view['autonomy'], {'drafting': {'level': 2, 'name': 'act_with_approval'},
                                            'research': {'level': 1, 'name': 'suggest'}})
        self.assertEqual((view['brains'], view['tools']), (['synthetic', 'synthetic-b'], ['calculator']))
        self.assertEqual(view['success_test'], 'The producer approves the review deck.')
        self.assertFalse(view['success_test_evaluated'])
        self.assertEqual(view['basis'], 'owner_authored_limits_not_a_grant')
        # Journalled and audited.
        self.assertEqual([j['event'] for j in self.journal() if j['target'].startswith('goal:')], ['mandate.created'])
        self.assertTrue(self.rows("SELECT 1 FROM audit WHERE kind='hub.mandate.created' AND subject=?", 'goal:' + view['id']))
        # The goal record itself is unchanged: the mandate does not rewrite the owner's goal.
        self.assertEqual(self.records.view(self.owner)['records'][0]['version'], 1)

    def test_creation_is_idempotent_and_one_mandate_per_goal(self):
        body = self.mandate_body()
        first = self.hub.create_mandate(self.owner, body)
        self.assertEqual(self.hub.create_mandate(self.owner, copy.deepcopy(body))['id'], first['id'])
        self.fault('mandate_request_collision', self.hub.create_mandate, self.owner, {**body, 'success_test': 'Other.'})
        self.fault('goal_has_mandate', self.mandate)

    def test_owner_only_and_hosted_credential_only(self):
        self.fault('forbidden', self.hub.create_mandate, self.reader, self.mandate_body())
        self.fault('hub_owner_not_hosted', self.hub.create_mandate, self.second, self.mandate_body())
        self.assertEqual(self.hub.view(self.reader)['reason'], 'owner_only')
        self.assertEqual(self.hub.view(self.second)['reason'], 'not_hosted')
        self.assertEqual(self.hub.view(self.second)['goals'], [])

    def test_mandates_refuse_what_the_hub_cannot_allow(self):
        self.fault(plug.PILOT_GATE_REASON, self.mandate, autonomy={'research': 3})
        self.fault(plug.PILOT_GATE_REASON, self.mandate, autonomy={'research': 4})
        self.fault('invalid_autonomy', self.mandate, autonomy={'research': 5})
        self.fault('invalid_work_kind', self.mandate, autonomy={'Bad Kind': 1})
        self.fault('brain_not_registered', self.mandate, brains=['synthetic', 'hermes'])
        self.fault('assigned_brain_not_allowed', self.mandate, assigned_brain='synthetic-c')
        self.fault('tool_not_permitted', self.mandate, tools=['web.fetch'])
        self.fault('invalid_deadline', self.mandate, deadline=T - 1)
        self.fault('invalid_success_test', self.mandate, success_test='   ')
        self.fault('invalid_budget', self.mandate, budget=budget(daily={'tokens': 0}))
        self.fault('invalid_scope_class', self.mandate, scope_class='everyone')
        cloud = BrainSpec(id='cloud-x', label='Cloud fixture', locality='cloud', version='1',
                          scopes=frozenset(plug.SCOPE_CLASSES), max_autonomy=2)
        self.registry.register(SyntheticBrain(cloud))
        self.fault('cloud_brain_refused_for_scope', self.mandate, brains=['cloud-x'], assigned_brain='cloud-x')
        commitment = self.make_goal('Book the grade', kind='commitment')
        self.fault('not_a_goal', self.mandate, goal=commitment['id'])
        self.fault('goal_not_available', self.mandate, goal='exec-unknown')
        dropped = self.make_goal('Old goal')
        self.records.update(self.owner, dropped['id'], {'version': 1, 'status': 'dropped'})
        self.fault('goal_not_active', self.mandate, goal=dropped['id'])
        # A schedule may not exceed the mandate it serves.
        when = {'every_hours': 1}
        self.fault('schedule_outside_mandate', self.mandate,
                   schedule={'when': when, 'utc_offset_minutes': 0, 'task': self.template(autonomy=2)})
        self.fault('schedule_outside_mandate', self.mandate,
                   schedule={'when': when, 'utc_offset_minutes': 0, 'task': self.template(work='publishing')})
        self.assertEqual(self.rows('SELECT * FROM hub_mandates'), [])

    def test_updates_are_version_checked_and_journalled(self):
        view = self.mandate()
        updated = self.hub.update_mandate(self.owner, view['id'], {'version': 1, 'autonomy': {'research': 0}})
        self.assertEqual((updated['version'], updated['autonomy']), (2, {'research': {'level': 0, 'name': 'observe'}}))
        self.fault('mandate_changed', self.hub.update_mandate, self.owner, view['id'], {'version': 1, 'tools': []})
        self.fault('invalid_fields', self.hub.update_mandate, self.owner, view['id'], {'version': 2, 'goal': 'x'})
        self.fault('invalid_fields', self.hub.update_mandate, self.owner, view['id'], {'version': 2, 'scope_class': 'client'})
        self.fault('assigned_brain_not_allowed', self.hub.update_mandate, self.owner, view['id'],
                   {'version': 2, 'brains': ['synthetic-b']})
        self.fault('hub_owner_not_hosted', self.hub.update_mandate, self.second, view['id'], {'version': 2, 'tools': []})
        events = self.journal('mandate.updated')
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0]['version'], json.loads(events[0]['detail'])), (2, {'autonomy': {'research': 0}}))

    def test_the_hub_journal_is_append_only(self):
        self.mandate()
        with self.store.connection() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE hub_journal SET event='rewritten'")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM hub_journal')


class GateTests(Base):
    def setUp(self):
        super().setUp()
        self.view = self.mandate()

    def test_brain_hub_refuses_a_task_without_a_mandate(self):
        request = {'task_id': 'loose-1', 'brain': 'synthetic', 'goal': {'ref': self.view['id'], 'statement': 'Anything.'},
                   'scope': 'company', 'instruction': 'Summarise.', 'context': self.selection(), 'learned': [], 'tools': [],
                   'budget': dict(TASK_BUDGET), 'autonomy': 1}
        self.fault('mandate_required', self.brains.submit, self.owner, request)
        binding = {'mandate': 'mandate-' + 'f' * 24, 'work': 'research', 'trigger': 'operator', 'slot': None}
        self.fault('mandate_mismatch', self.brains.submit, self.owner, request, binding=binding)
        request['goal']['ref'] = binding['mandate']
        self.fault('mandate_required', self.brains.submit, self.owner, request, binding=binding)
        self.assertEqual(self.rows('SELECT * FROM jobs'), [])

    def test_tasks_outside_the_mandate_are_refused_before_a_job_exists(self):
        mid = self.view['id']
        self.fault('autonomy_above_mandate', self.task, mid, autonomy=2)
        self.fault('work_kind_not_in_mandate', self.task, mid, work='publishing')
        self.hub.update_mandate(self.owner, mid, {'version': 1, 'tools': []})
        self.fault('tool_not_in_mandate', self.task, mid, tools=['calculator'])
        self.registry.register(SyntheticBrain(BrainSpec(id='synthetic-c', label='Third', locality='local', version='1',
                                                        scopes=frozenset(plug.SCOPE_CLASSES), max_autonomy=2)))
        self.fault('brain_not_in_mandate', self.task, mid, brain='synthetic-c')
        # H1 policy still applies first: autonomy 3 and 4 never reach the mandate check.
        self.fault(plug.PILOT_GATE_REASON, self.task, mid, autonomy=3)
        self.fault('hub_owner_not_hosted', self.task, mid, bearer=self.second)
        self.assertEqual(self.rows('SELECT * FROM jobs'), [])

    def test_scope_class_and_deadline_and_goal_state_bind_every_task(self):
        mid = self.view['id']
        request = {'task_id': 'scope-1', 'brain': 'synthetic', 'goal': {'ref': mid, 'statement': 'x'}, 'scope': 'client',
                   'instruction': 'Summarise.', 'context': [], 'learned': [], 'tools': [], 'budget': dict(TASK_BUDGET), 'autonomy': 1}
        binding = {'mandate': mid, 'work': 'research', 'trigger': 'operator', 'slot': None}
        self.fault('scope_class_outside_mandate', self.brains.submit, self.owner, request, binding=binding)
        self.clock[0] = T + 20 * DAY
        self.fault('mandate_expired', self.task, mid)
        self.clock[0] = T
        self.records.update(self.owner, self.goal['id'], {'version': 1, 'status': 'achieved'})
        self.fault('goal_not_active', self.task, mid)

    def test_an_admitted_task_links_back_to_its_goal_and_mandate(self):
        job_id = self.run_task(self.view['id'])
        task = self.hub_task(job_id)
        self.assertEqual((task['mandate'], task['goal'], task['work'], task['brain'], task['trigger']),
                         (self.view['id'], self.goal['id'], 'research', 'synthetic', 'operator'))
        packet = self.jobs.view(self.owner, job_id)['parameters']['packet']
        self.assertEqual(packet['goal'], {'ref': self.view['id'], 'statement': 'Deliver the quarterly review'})
        self.assertEqual(packet['scope'], 'company')
        self.assertEqual(self.brains.result(self.owner, job_id)['status'], 'accepted')
        shown = self.current(self.view['id'])['tasks'][0]
        self.assertEqual((shown['job'], shown['job_state'], shown['result']), (job_id, 'succeeded', 'accepted'))

    def test_a_brain_task_that_bypassed_the_hub_never_reaches_a_brain(self):
        request = {'task_id': 'bypass-1', 'brain': 'synthetic', 'goal': {'ref': self.view['id'], 'statement': 'x'},
                   'scope': 'company', 'instruction': 'Summarise.', 'context': self.selection(), 'learned': [], 'tools': [],
                   'budget': dict(TASK_BUDGET), 'autonomy': 1}
        packet = self.brains.build_packet(self.owner, request)
        job = self.jobs.submit(self.owner, {'idempotency_key': 'bypass-1', 'kind': 'brain_task',
                                            'parameters': {'brain': 'synthetic', 'packet': packet},
                                            'inputs': [{'note': self.note['id'], 'revision': self.note['revision']}],
                                            'side_effect_free': True, 'max_attempts': 1})
        self.worker().run_once()
        view = self.jobs.view(self.owner, job['id'])
        self.assertEqual((view['state'], view['reason']), ('failed', 'mandate_required'))
        self.assertEqual(self.seen, [])

    def test_dispatch_rechecks_the_mandate_before_the_brain_starts(self):
        submitted = self.task(self.view['id'])
        self.records.update(self.owner, self.goal['id'], {'version': 1, 'status': 'achieved'})
        self.worker().run_once()
        job = self.jobs.view(self.owner, submitted['job']['id'])
        self.assertEqual((job['state'], job['reason']), ('failed', 'goal_not_active'))
        self.assertEqual(self.seen, [])
        self.hub.cycle()
        task = self.hub_task(job['id'])
        self.assertEqual((task['usage_basis'], task['used_tokens'], task['used_wall']), ('brain_not_started', 0, 0))


class BudgetTests(Base):
    def test_an_overall_budget_is_required(self):
        view = self.mandate()
        self.set_overall(None)
        self.fault('overall_budget_required', self.task, view['id'])

    def test_metered_usage_comes_from_the_h1_meter(self):
        view = self.mandate()
        job_id = self.run_task(view['id'])
        task = self.hub_task(job_id)
        metered = self.brains.result(self.owner, job_id)['metered']
        self.assertEqual(task['usage_basis'], 'metered')
        self.assertEqual((task['used_tokens'], task['used_money']), (metered['tokens'], metered['money_pence']))
        self.assertGreater(task['used_tokens'], 0)
        self.assertEqual(task['used_wall'], 1)
        meter = self.rows('SELECT * FROM hub_meter WHERE job_id=?', job_id)[0]
        self.assertEqual((meter['state'], meter['steps'], meter['reason']), ('finished', metered['steps'], None))
        usage = self.current(view['id'])['usage']['total']['dimensions']
        self.assertEqual((usage['tasks']['used'], usage['tokens']['used']), (1, metered['tokens']))

    def test_admission_counts_tasks_in_flight_at_their_ceiling(self):
        view = self.mandate(budget=budget(daily={'tokens': 50}))
        self.task(view['id'])  # Ceiling 30, still queued.
        self.fault('over_budget_goal_daily_tokens', self.task, view['id'])
        self.worker().run_once(); self.hub.cycle()
        used = self.current(view['id'])['usage']['daily']['dimensions']['tokens']['used']
        self.assertLess(used + 30, 51)
        self.task(view['id'])  # Measured usage replaced the reservation, so it fits now.

    def test_a_warning_is_recorded_once_as_an_attention_item(self):
        view = self.mandate(budget=budget(daily={'tokens': 60}, warn=20))
        self.run_task(view['id'])
        self.run_task(view['id'])
        items = [a for a in self.hub.view(self.owner)['attention'] if a['target'] == 'goal:' + view['id']]
        self.assertEqual([(a['level'], a['dimension'], a['period'], a['state']) for a in items],
                         [('warning', 'tokens', 'daily', 'open')])
        self.assertEqual(self.current(view['id'])['state'], 'active')
        acknowledged = self.hub.acknowledge(self.owner, items[0]['id'], {})
        self.assertEqual(acknowledged['state'], 'acknowledged')
        self.fault('hub_owner_not_hosted', self.hub.acknowledge, self.second, items[0]['id'], {})

    def test_a_hard_stop_pauses_the_goal_until_the_owner_resumes(self):
        view = self.mandate(budget=budget(daily={'tasks': 2}))
        self.run_task(view['id'])
        self.assertEqual(self.current(view['id'])['state'], 'active')
        self.run_task(view['id'])
        current = self.current(view['id'])
        self.assertEqual((current['state'], current['state_reason']), ('paused', 'budget_daily_tasks'))
        levels = {(a['target'], a['level']) for a in self.hub.view(self.owner)['attention']}
        self.assertIn(('goal:' + view['id'], 'hard_stop'), levels)
        self.fault('goal_paused', self.task, view['id'])
        self.fault('budget_still_spent', self.control, 'goal', view['id'], 'resume')
        # A new day gives the budget room again; still nothing resumes on its own.
        self.clock[0] = T + DAY
        self.assertEqual(self.current(view['id'])['state'], 'paused')
        self.control('goal', view['id'], 'resume')
        self.assertEqual(self.current(view['id'])['state'], 'active')
        self.task(view['id'])

    def test_per_brain_and_overall_budgets_pause_their_own_target(self):
        view = self.mandate()
        self.hub.set_budget(self.owner, 'brain', 'synthetic', {'version': 0, 'budget': budget(total={'tasks': 1})})
        self.run_task(view['id'])
        self.assertEqual(self.brain_view('synthetic')['state'], 'paused')
        self.assertEqual(self.current(view['id'])['state'], 'active')
        self.fault('brain_paused', self.task, view['id'])
        self.run_task(view['id'], brain='synthetic-b')
        self.set_overall(budget(total={'tasks': 3}))
        self.run_task(view['id'], brain='synthetic-b')
        overall = self.hub.view(self.owner)['overall']
        self.assertEqual((overall['state'], overall['reason']), ('paused', 'budget_total_tasks'))
        self.fault('hub_paused', self.task, view['id'], brain='synthetic-b')
        self.fault('budget_still_spent', self.control, 'overall', None, 'resume')
        self.set_overall(budget(total={'tasks': 10}))
        self.control('overall', None, 'resume')
        self.task(view['id'], brain='synthetic-b')

    def test_lowering_a_limit_cancels_running_work_through_the_coordinator(self):
        self.registry.register(SyntheticBrain(BrainSpec(id='slow', label='Slow fixture', locality='local', version='1',
                                                        scopes=frozenset(plug.SCOPE_CLASSES), max_autonomy=2),
                                              faults=('runaway', 'slow_steps')))
        view = self.mandate(brains=['slow'], assigned_brain='slow', budget=budget(total={'tokens': 5000}))
        submitted = self.task(view['id'], budget={'wall_seconds': 30, 'tokens': 2000, 'money_pence': 0, 'steps': 1000})
        job_id = submitted['job']['id']
        backend = self.hub.backend()
        thread = threading.Thread(target=JobWorker(self.jobs, backend, self.owner, 'brain-1', poll_seconds=0.01,
                                                   heartbeat_seconds=0.05).run_once)
        thread.start()
        # Lower the limit only once the brain has metered work: a job marked running may not
        # have taken its first step yet, and then nothing would have been used to charge.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with backend._lock:
                runs = list(backend._runs.values())
            if runs and runs[0].meter.snapshot()['tokens'] > 0:
                break
            time.sleep(0.01)
        self.hub.update_mandate(self.owner, view['id'], {'version': 1, 'budget': budget(total={'tokens': 100})})
        thread.join(10)
        self.assertFalse(thread.is_alive())
        job = self.jobs.view(self.owner, job_id)
        self.assertEqual(job['state'], 'cancelled')
        events = [e['kind'] for e in self.jobs.events(self.owner, job_id)['events']]
        self.assertIn('cancel_requested', events)
        current = self.current(view['id'])
        self.assertEqual((current['state'], current['state_reason']), ('paused', 'budget_total_tokens'))
        self.assertEqual(self.journal('tasks.cancelled')[0]['detail'], json.dumps({'jobs': [job_id]}, separators=(',', ':')))
        self.hub.cycle()
        task = self.hub_task(job_id)
        self.assertEqual(task['usage_basis'], 'metered')
        self.assertGreater(task['used_tokens'], 0)
        self.assertLessEqual(task['used_tokens'], 2000)

    def test_a_run_that_never_reported_is_charged_its_ceiling(self):
        view = self.mandate()

        def lost(*_args):
            raise RuntimeError('report lost')
        self.hub.metered = lost
        job_id = self.run_task(view['id'])
        task = self.hub_task(job_id)
        self.assertEqual((task['usage_basis'], task['used_tokens'], task['used_wall']),
                         ('unknown_charged_at_ceiling', TASK_BUDGET['tokens'], TASK_BUDGET['wall_seconds']))


class HeartbeatTests(Base):
    def scheduled(self, **over):
        schedule = {'when': {'every_hours': 1}, 'utc_offset_minutes': 0, 'task': self.template()}
        return self.mandate(schedule=schedule, **over)

    def test_a_heartbeat_submits_the_owner_authored_task(self):
        view = self.scheduled()
        due = next_slot({'schedule': {'every_hours': 1}, 'utc_offset_minutes': 0}, T)
        self.assertEqual(view['next_due'], due)
        self.clock[0] = due - 1
        self.hub.cycle()
        self.assertEqual(self.rows('SELECT * FROM hub_heartbeats'), [])
        self.clock[0] = due
        self.hub.cycle()
        beat = self.rows('SELECT * FROM hub_heartbeats')[0]
        self.assertEqual((beat['status'], beat['missed'], beat['slot']), ('submitted', 0, f'due:{due}'))
        task = self.hub_task(beat['job_id'])
        self.assertEqual((task['trigger'], task['brain'], task['work']), ('heartbeat', 'synthetic', 'research'))
        self.worker().run_once(); self.hub.cycle()
        self.assertEqual(self.hub_task(beat['job_id'])['usage_basis'], 'metered')
        self.assertEqual(self.current(view['id'])['next_due'], due + HOUR)

    def test_slots_missed_while_stopped_are_counted_not_replayed(self):
        view = self.scheduled()
        due = view['next_due']
        self.clock[0] = due + 4 * HOUR + 600
        self.assertEqual(missed_slots(view['schedule'], due, self.clock[0]), 5)
        from alfred.recovery import _routine_slots
        with self.store.connection() as db:
            self.assertEqual(_routine_slots(db, WORKSPACE, self.clock[0])['hub:' + view['id']], 5)
        self.hub.cycle()
        beats = self.rows('SELECT * FROM hub_heartbeats')
        self.assertEqual([(b['status'], b['missed']) for b in beats], [('submitted', 4)])
        self.assertEqual(len(self.rows('SELECT * FROM hub_tasks')), 1)
        current = self.current(view['id'])
        self.assertEqual((current['missed_total'], current['next_due']), (4, due + 5 * HOUR))
        self.hub.cycle()
        self.assertEqual(len(self.rows('SELECT * FROM hub_heartbeats')), 1)

    def test_a_paused_goal_skips_its_heartbeat(self):
        view = self.scheduled()
        self.control('goal', view['id'], 'pause')
        self.clock[0] = view['next_due']
        self.hub.cycle()
        beat = self.rows('SELECT * FROM hub_heartbeats')[0]
        self.assertEqual((beat['status'], beat['reason'], beat['job_id']), ('skipped', 'goal_paused', None))
        self.assertEqual(self.rows('SELECT * FROM hub_tasks'), [])

    def test_a_heartbeat_that_does_not_fit_the_budget_is_refused(self):
        view = self.scheduled(budget=budget(daily={'tokens': 10}))
        self.clock[0] = view['next_due']
        self.hub.cycle()
        beat = self.rows('SELECT * FROM hub_heartbeats')[0]
        self.assertEqual((beat['status'], beat['reason']), ('refused', 'over_budget_goal_daily_tokens'))

    def test_a_brain_cannot_schedule_itself(self):
        self.registry.register(ScheduleBrain())
        view = self.mandate(brains=['scheduler'], assigned_brain='scheduler')
        before = self.rows('SELECT next_due,schedule,version FROM hub_mandates')
        job_id = self.run_task(view['id'], work='drafting', autonomy=2, context=[])
        proposals = self.brains.proposals(self.owner)
        self.assertEqual([(p['capability'], p['disposition'], p['refusal']) for p in proposals],
                         [('hub.schedule', 'refused', 'capability_not_allowed_for_brains')])
        self.assertEqual(self.rows('SELECT next_due,schedule,version FROM hub_mandates'), before)
        self.clock[0] = T + 3 * HOUR
        self.hub.cycle()
        self.assertEqual(self.rows('SELECT * FROM hub_heartbeats'), [])
        self.assertEqual([t['job_id'] for t in self.rows('SELECT job_id FROM hub_tasks')], [job_id])

    def test_a_bundle_claiming_a_schedule_is_refused_whole(self):
        registry_brain = ScheduleBrain(extra_field=True)
        self.registry.register(registry_brain)
        view = self.mandate(brains=['scheduler'], assigned_brain='scheduler')
        job_id = self.run_task(view['id'], work='drafting', autonomy=2, context=[])
        result = self.brains.result(self.owner, job_id)
        self.assertEqual((result['status'], result['reason']), ('refused', 'invalid_bundle_fields'))
        self.assertIsNone(self.current(view['id'])['schedule'])
        self.assertEqual(self.hub_task(job_id)['result'], 'refused')

    def test_supervisor_cycle_runs_heartbeats_even_while_paused(self):
        supervisor = KnowledgeSupervisor(self.store, self.owner, self.source, self.root / 'project', vault=self.vault)
        supervisor.goals = self.hub
        view = self.scheduled()
        self.store.set_paused(self.owner, True)
        self.clock[0] = view['next_due']
        supervisor.cycle()
        beat = self.rows('SELECT * FROM hub_heartbeats')[0]
        self.assertEqual((beat['status'], beat['reason']), ('skipped', 'workspace_paused'))


class ControlTests(Base):
    def setUp(self):
        super().setUp()
        self.view = self.mandate()

    def test_pause_cancels_queued_work_and_resume_reopens(self):
        submitted = self.task(self.view['id'])
        result = self.control('goal', self.view['id'], 'pause')
        current = next(g for g in result['goals'] if g['id'] == self.view['id'])
        self.assertEqual((current['state'], current['state_reason'], current['version']), ('paused', 'operator', 2))
        job = self.jobs.view(self.owner, submitted['job']['id'])
        self.assertEqual((job['state'], job['reason']), ('cancelled', 'cancelled_before_lease'))
        self.fault('goal_paused', self.task, self.view['id'])
        self.fault('mandate_changed', self.hub.control, self.owner, 'goal', self.view['id'], 'resume', {'version': 1})
        self.control('goal', self.view['id'], 'resume')
        self.task(self.view['id'])
        self.assertEqual([j['event'] for j in self.journal() if j['target'] == 'goal:' + self.view['id']],
                         ['mandate.created', 'goal.paused', 'goal.resumed'])
        audit = [r['kind'] for r in self.rows("SELECT kind FROM audit WHERE kind LIKE 'hub.%' ORDER BY seq")]
        self.assertIn('hub.goal.paused', audit)
        self.assertIn('hub.tasks.cancelled', audit)

    def test_controls_are_owner_only(self):
        self.fault('forbidden', self.hub.control, self.reader, 'goal', self.view['id'], 'pause', {'version': 1})
        self.fault('hub_owner_not_hosted', self.hub.control, self.second, 'goal', self.view['id'], 'pause', {'version': 1})
        self.fault('not_found', self.hub.control, self.owner, 'goal', self.view['id'], 'delete', {'version': 1})
        self.fault('not_found', self.hub.control, self.owner, 'overall', None, 'stop', {'version': 0})

    def test_reassign_moves_the_goal_to_another_allowed_brain(self):
        submitted = self.task(self.view['id'])
        self.fault('brain_already_assigned', self.control, 'goal', self.view['id'], 'reassign', brain='synthetic')
        self.registry.register(SyntheticBrain(BrainSpec(id='synthetic-c', label='Third', locality='local', version='1',
                                                        scopes=frozenset(plug.SCOPE_CLASSES), max_autonomy=2)))
        self.fault('brain_not_in_mandate', self.control, 'goal', self.view['id'], 'reassign', brain='synthetic-c')
        self.control('goal', self.view['id'], 'reassign', brain='synthetic-b')
        self.assertEqual(self.current(self.view['id'])['assigned_brain'], 'synthetic-b')
        self.assertEqual(self.jobs.view(self.owner, submitted['job']['id'])['state'], 'cancelled')
        job_id = self.run_task(self.view['id'])
        self.assertEqual(self.hub_task(job_id)['brain'], 'synthetic-b')
        self.assertEqual((len(self.seen), len(self.seen_b)), (0, 1))
        detail = json.loads(self.journal('goal.reassigned')[0]['detail'])
        self.assertEqual(detail, {'from': 'synthetic', 'to': 'synthetic-b'})

    def test_stop_is_final_and_survives_a_restore(self):
        backups = self.root / 'backups'
        manifest = lifecycle.backup(self.store, self.owner, backups)
        self.control('goal', self.view['id'], 'stop')
        current = self.current(self.view['id'])
        self.assertEqual((current['state'], current['next_due']), ('stopped', None))
        self.fault('goal_stopped', self.control, 'goal', self.view['id'], 'resume')
        self.fault('goal_stopped', self.task, self.view['id'])
        entries = lifecycle.entries(lifecycle.journal_path(self.store))
        self.assertEqual([(e['kind'], e['subject']) for e in entries], [('hub_stopped', 'goal:' + self.view['id'])])
        # A new mandate may be made for the same goal once the old one is stopped.
        self.mandate()
        result = lifecycle.restore(backups / manifest['file'], self.store.path, now=T)
        self.assertEqual(result['removed_again']['totals'], {'hub_targets_stopped': 1})
        restored = KnowledgeStore(self.store.path, clock=lambda: self.clock[0])
        with restored.connection() as db:
            self.assertEqual([r['state'] for r in db.execute('SELECT state FROM hub_mandates')], ['stopped'])

    def test_brain_pause_resume_and_stop(self):
        self.control('brain', 'synthetic', 'pause')
        self.assertEqual(self.brain_view('synthetic')['state'], 'paused')
        self.fault('brain_paused', self.task, self.view['id'])
        self.task(self.view['id'], brain='synthetic-b')
        self.control('brain', 'synthetic', 'resume')
        submitted = self.task(self.view['id'])
        self.control('brain', 'synthetic', 'stop')
        self.assertEqual(self.jobs.view(self.owner, submitted['job']['id'])['state'], 'cancelled')
        self.fault('brain_stopped', self.control, 'brain', 'synthetic', 'resume')
        self.fault('brain_stopped', self.task, self.view['id'])
        other = self.make_goal('Another goal')
        self.fault('brain_stopped', self.mandate, goal=other['id'])
        self.assertEqual([e['subject'] for e in lifecycle.entries(lifecycle.journal_path(self.store))], ['brain:synthetic'])
        self.fault('brain_not_registered', self.hub.control, self.owner, 'brain', 'unknown-brain', 'pause', {'version': 0})

    def test_overall_pause_holds_every_goal(self):
        self.control('overall', None, 'pause')
        self.fault('hub_paused', self.task, self.view['id'])
        self.control('overall', None, 'resume')
        self.task(self.view['id'])


class HTTPTests(Base):
    def setUp(self):
        super().setUp()
        from alfred.desk_http import DeskHTTPServer
        self.sup = KnowledgeSupervisor(self.store, self.owner, self.source, self.root / 'project', vault=self.vault)
        self.server = DeskHTTPServer(self.store, self.sup, port=0, jobs=self.jobs, goals=self.hub)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.cookie = self.csrf = None

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)

    def raw(self, path, data=None, headers=None):
        headers = dict(headers or {})
        if self.cookie:
            headers.setdefault('Cookie', self.cookie)
        if data is not None:
            headers.setdefault('Content-Type', 'application/json'); headers.setdefault('Origin', self.server.origin)
            if self.csrf:
                headers.setdefault('X-CSRF-Token', self.csrf)
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); body = r.read(); c.close()
        return r.status, json.loads(body)

    def login(self, key):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST', '/desk/login', json.dumps({'key': key}), {'Content-Type': 'application/json', 'Origin': self.server.origin})
        r = c.getresponse(); body = json.loads(r.read()); c.close()
        self.cookie = r.getheader('Set-Cookie').split(';')[0]; self.csrf = body['csrf']

    def test_routes_keep_the_session_csrf_and_version_checks(self):
        self.assertEqual(self.raw('/desk/hub')[0], 401)
        self.login(self.owner)
        status, view = self.raw('/desk/hub')
        self.assertEqual((status, view['available'], view['unlinked_goals'][0]['id']), (200, True, self.goal['id']))
        body = self.mandate_body()
        self.assertEqual(self.raw('/desk/hub/mandates', body, {'X-CSRF-Token': 'wrong'}), (403, {'error': 'csrf_rejected'}))
        self.assertEqual(self.raw('/desk/hub/mandates', body, {'Origin': 'http://evil.example'}), (403, {'error': 'invalid_origin'}))
        status, created = self.raw('/desk/hub/mandates', body)
        self.assertEqual((status, created['state']), (200, 'active'))
        path = f"/desk/hub/mandates/{created['id']}"
        self.assertEqual(self.raw(path + '/pause', {'version': 7}), (409, {'error': 'mandate_changed'}))
        status, after = self.raw(path + '/pause', {'version': 1})
        self.assertEqual((status, after['goals'][0]['state']), (200, 'paused'))
        status, after = self.raw(path + '/resume', {'version': 2})
        self.assertEqual(after['goals'][0]['state'], 'active')
        task = {'request_id': 'http-task', 'brain': None, **self.template()}
        status, submitted = self.raw(path + '/tasks', task)
        self.assertEqual((status, submitted['mandate'], submitted['trigger']), (200, created['id'], 'operator'))
        self.assertEqual(self.raw(path + '/tasks', {**task, 'request_id': 'http-2', 'autonomy': 2}),
                         (403, {'error': 'autonomy_above_mandate'}))
        status, after = self.raw('/desk/hub/brains/synthetic/pause', {'version': 0})
        self.assertEqual(next(b for b in after['brains'] if b['id'] == 'synthetic')['state'], 'paused')
        status, after = self.raw('/desk/hub/overall/budget', {'version': after['overall']['version'],
                                                              'budget': budget(daily={'tasks': 5})})
        self.assertEqual((status, after['overall']['budget']['daily']['tasks']), (200, 5))
        self.assertEqual(self.raw('/desk/hub/unknown', {}), (404, {'error': 'not_found'}))

    def test_a_reader_sees_nothing_and_changes_nothing(self):
        created = self.mandate()
        self.login(self.reader)
        status, view = self.raw('/desk/hub')
        self.assertEqual((status, view['available'], view['reason'], view['goals']), (200, False, 'owner_only', []))
        self.assertEqual(self.raw(f"/desk/hub/mandates/{created['id']}/pause", {'version': 1}), (403, {'error': 'forbidden'}))

    def test_a_host_without_a_hub_says_so(self):
        self.server.goals = None
        self.login(self.owner)
        self.assertEqual(self.raw('/desk/hub'), (409, {'error': 'hub_not_configured'}))


if __name__ == '__main__':
    unittest.main()
