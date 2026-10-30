"""The agent hub steps wired together (AGENT_HUB.md H2, H3 and H4).

Synthetic data only: a fictional vault note, the deterministic rule-based SyntheticBrain
from H1 and one small fixture brain defined here. No model, no network. Real SQLite, the
real job coordinator and worker, the real goal hub, verifier and daily learning routine,
and real HTTP where the boundary matters. These tests prove that:

* a mandate's acceptance checks are the owner's, reach every task packet first, and are
  enforced by the gate; the brain never declares them;
* routing notes count verified outcomes (checked or acknowledged), failed checks,
  unverifiable results and results with no declared checks separately, and never count a
  result without checks, or the brain's own word, as verified;
* goal outcomes from the hub journal become routing notes, and learning changes nothing;
* verification is reachable over the guarded HTTP handler for the submitting person only.
"""
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from alfred import brain as plug
from alfred.brain import Brain, BrainHub, BrainPolicy, BrainRegistry, BrainSpec, SyntheticBrain
from alfred.executive import ExecutiveRecords
from alfred.hub_goals import GoalHub
from alfred.jobs import JobCoordinator, JobWorker
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.local import Fault
from alfred.policy import IdentityPolicy
from alfred.routines import Routines
import stored_helpers as stored
from grant_helpers import grant_all, revoke_all

DAY, HOUR = 86400, 3600
T = 1_900_000_000
WORKSPACE = 'ws-hub-integrate-7720'
PLAN = '# Plan\nAlpha review is due on Friday.\nremember: Producers prefer short drafts.\n\nOutside line.\n'
TASK_BUDGET = {'wall_seconds': 10, 'tokens': 30, 'money_pence': 0, 'steps': 50}
NONE = {'tokens': None, 'money_pence': None, 'wall_seconds': None, 'tasks': None}
SECTIONS = {'kind': 'artefact_sections', 'artefact': 'notes.md', 'sections': ['Synthetic brain notes']}
MISSING = {'kind': 'artefact_sections', 'artefact': 'notes.md', 'sections': ['Risks']}
CITED = {'kind': 'claims_cited'}


def budget(daily=None, total=None, warn=80):
    return {'daily': {**NONE, **(daily or {})}, 'total': {**NONE, **(total or {})}, 'warn_percent': warn, 'utc_offset_minutes': 0}


class ConfidentBrain(Brain):
    """Says it is done, verified and confident, with passing self-test output. Its notes lack
    the section the owner asked for."""

    def __init__(self):
        self.spec = BrainSpec(id='confident', label='Confident fixture', locality='local', version='1',
                              scopes=frozenset(plug.SCOPE_CLASSES), tools=frozenset(), max_autonomy=2)

    def run(self, packet, meter):
        meter.step(tokens=5)
        content = '# Status\n\nverified_done: true\nAll acceptance checks passed. Self-test: 12 of 12 passing.\n'
        import hashlib
        return {'bundle_version': 1, 'answer': {'text': 'Done.', 'citations': []},
                'artefacts': [{'name': 'notes.md', 'media_type': 'text/markdown',
                               'sha256': hashlib.sha256(content.encode()).hexdigest(), 'content': content}],
                'memory_suggestions': [], 'proposed_actions': [],
                'work_log': [{'step': 1, 'kind': 'reason', 'tool': None, 'summary': 'Confidence 100 percent; verified done.'}]}


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
        self.sup = KnowledgeSupervisor(self.store, self.owner, self.source, self.root / 'project', vault=self.vault)
        self.sup.vault.scan()
        self.note = next(n for n in self.store.knowledge(self.owner)['nodes'] if n['title'] == 'Plan')
        self.jobs = JobCoordinator(self.store)
        self.jobs.enrol_worker(self.owner, 'brain-1', 'Brain worker', ['brain_task'])
        self.registry = BrainRegistry()
        self.seen = []
        self.registry.register(SyntheticBrain(seen=self.seen))
        self.registry.register(SyntheticBrain(BrainSpec(id='synthetic-b', label='Second synthetic brain', locality='local',
                                                        version='1', scopes=frozenset(plug.SCOPE_CLASSES),
                                                        tools=frozenset({'calculator'}), max_autonomy=2)))
        self.registry.register(ConfidentBrain())
        self.policy = BrainPolicy(permitted_tools=('calculator',))
        self.brains = BrainHub(self.store, self.jobs, self.registry, self.policy)
        self.hub = GoalHub(self.store, self.brains, self.owner)
        self.records = ExecutiveRecords(self.store)
        self.seq = 0
        self.goal = self.make_goal('Deliver the quarterly review')
        self.hub.set_budget(self.owner, 'overall', None, {'version': 0, 'budget': budget(total={'tasks': 100})})

    # Helpers ------------------------------------------------------------------

    def next(self, prefix):
        self.seq += 1
        return f'{prefix}-{self.seq}'

    def make_goal(self, title):
        return self.records.create(self.owner, {'request_id': self.next('goal'), 'kind': 'goal', 'title': title, 'detail': '',
                                                'project': None, 'due': None, 'rank': None, 'support': None})

    def fault(self, code, call, *args, **kwargs):
        with self.assertRaises(Fault) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def rows(self, sql, *args):
        with self.store.connection() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def journal(self, event=None):
        return [r for r in stored.rows(self.store, 'hub_journal', 'SELECT * FROM hub_journal ORDER BY seq')
                if event is None or r['event'] == event]

    def selection(self):
        return [{'note': self.note['id'], 'start_line': 2, 'end_line': 3}]

    def template(self, **over):
        value = {'work': 'research', 'instruction': 'Summarise the plan.', 'context': self.selection(), 'learned': [],
                 'tools': [], 'budget': dict(TASK_BUDGET), 'autonomy': 1}
        value.update(over)
        return value

    def mandate(self, goal=None, **over):
        body = {'request_id': self.next('mandate'), 'goal': (goal or self.goal)['id'], 'scope_class': 'company',
                'deadline': self.clock[0] + 20 * DAY, 'success_test': 'The producer approves the review deck.',
                'autonomy': {'research': 1, 'drafting': 2}, 'brains': ['synthetic', 'synthetic-b', 'confident'],
                'assigned_brain': 'synthetic', 'tools': ['calculator'], 'budget': budget(total={'tasks': 50}), 'schedule': None}
        body.update(over)
        return self.hub.create_mandate(self.owner, body)

    def current(self, mandate_id):
        return next(g for g in self.hub.view(self.owner)['goals'] if g['id'] == mandate_id)

    def task(self, mandate_id, **over):
        body = {'request_id': self.next('task'), 'brain': None, **self.template()}
        body.update(over)
        return self.hub.submit_task(self.owner, mandate_id, body)

    def run_task(self, mandate_id, **over):
        submitted = self.task(mandate_id, **over)
        worker = JobWorker(self.jobs, self.hub.backend(), self.owner, 'brain-1', poll_seconds=0.01, heartbeat_seconds=0.05)
        self.assertEqual(worker.run_once(), submitted['job']['id'])
        self.clock[0] += 5
        self.hub.cycle()
        return submitted['job']['id']

    def packet(self, job_id):
        return self.jobs.view(self.owner, job_id)['parameters']['packet']


# Task 3: mandates declare acceptance checks ------------------------------------------------

class MandateChecksTests(Base):
    def test_the_owner_attaches_checks_and_every_packet_carries_them_first(self):
        view = self.mandate(acceptance=[SECTIONS])
        self.assertEqual(view['acceptance'], [{'id': 'C1', **SECTIONS, 'non_empty': True}])
        self.assertEqual((view['acceptance_declared_by'], view['success_test_evaluated']), ('mandate', False))
        created = json.loads(self.journal('mandate.created')[0]['detail'])
        self.assertEqual(created['acceptance'], [{**SECTIONS, 'non_empty': True}])
        # The task adds its own check; the mandate's identical one is not repeated.
        job_id = self.run_task(view['id'], acceptance=[SECTIONS, CITED])
        acceptance = self.packet(job_id)['acceptance']
        self.assertEqual((acceptance['declared_by'], acceptance['ref']), ('mandate', view['id']))
        self.assertEqual([(c['id'], c['kind']) for c in acceptance['checks']], [('C1', 'artefact_sections'), ('C2', 'claims_cited')])
        checked = self.hub.verifier.verify(self.owner, job_id)
        self.assertEqual((checked['state'], checked['evidence'], checked['declared']), ('checked', 'verified', 2))
        # The success test is the owner's text: no check reads it and nothing reports it as met.
        self.assertNotIn('producer approves', json.dumps(checked['last_run']['report']))
        # A task with no checks of its own still carries the mandate's.
        plain = self.run_task(view['id'])
        self.assertEqual([c['kind'] for c in self.packet(plain)['acceptance']['checks']], ['artefact_sections'])

    def test_a_heartbeat_task_carries_the_mandate_checks(self):
        schedule = {'when': {'every_hours': 1}, 'utc_offset_minutes': 0, 'task': self.template(acceptance=[CITED])}
        view = self.mandate(acceptance=[SECTIONS], schedule=schedule)
        self.clock[0] = view['next_due']
        self.hub.cycle()
        beat = self.rows('SELECT * FROM hub_heartbeats')[0]
        self.assertEqual(beat['status'], 'submitted')
        acceptance = self.packet(beat['job_id'])['acceptance']
        self.assertEqual(([c['kind'] for c in acceptance['checks']], acceptance['declared_by']),
                         (['artefact_sections', 'claims_cited'], 'mandate'))

    def test_checks_are_owner_only_version_checked_and_journalled(self):
        view = self.mandate()
        self.assertEqual((view['acceptance'], view['acceptance_declared_by']), ([], None))
        self.fault('mandate_changed', self.hub.update_mandate, self.owner, view['id'], {'version': 9, 'acceptance': [SECTIONS]})
        self.fault('hub_owner_not_hosted', self.hub.update_mandate, self.second, view['id'], {'version': 1, 'acceptance': [SECTIONS]})
        self.fault('forbidden', self.hub.update_mandate, self.reader, view['id'], {'version': 1, 'acceptance': [SECTIONS]})
        updated = self.hub.update_mandate(self.owner, view['id'], {'version': 1, 'acceptance': [SECTIONS]})
        self.assertEqual((updated['version'], [c['kind'] for c in updated['acceptance']]), (2, ['artefact_sections']))
        events = self.journal('mandate.updated')
        self.assertEqual((events[-1]['version'], json.loads(events[-1]['detail'])),
                         (2, {'acceptance': [{**SECTIONS, 'non_empty': True}]}))
        self.assertTrue(self.rows("SELECT 1 FROM audit WHERE kind='hub.mandate.updated'"))
        cleared = self.hub.update_mandate(self.owner, view['id'], {'version': 2, 'acceptance': None})
        self.assertEqual((cleared['acceptance'], json.loads(self.journal('mandate.updated')[-1]['detail'])), ([], {'acceptance': None}))
        # Changing anything else keeps the checks.
        self.hub.update_mandate(self.owner, view['id'], {'version': 3, 'acceptance': [CITED]})
        kept = self.hub.update_mandate(self.owner, view['id'], {'version': 4, 'success_test': 'The deck is approved.'})
        self.assertEqual([c['kind'] for c in kept['acceptance']], ['claims_cited'])

    def test_checks_are_validated_by_the_verifier_rules(self):
        self.fault('unknown_check_kind', self.mandate, acceptance=[{'kind': 'brain_says_done'}])
        self.fault('schema_keyword_not_supported', self.mandate,
                   acceptance=[{'kind': 'artefact_schema', 'artefact': 'out.json', 'schema': {'type': 'object', '$ref': '#'}}])
        self.fault('invalid_acceptance', self.mandate, acceptance=[])
        self.fault('invalid_acceptance', self.mandate, acceptance=[CITED] * 9)
        self.fault('invalid_check', self.mandate, acceptance=[{'kind': 'artefact_sections', 'artefact': 'notes.md'}])
        # A mandate also covers lower autonomy levels, so it cannot declare a read-back of effects.
        self.fault('readback_needs_autonomy_two', self.mandate, acceptance=[{'kind': 'effect_readback'}])
        # The merged checks of a scheduled task must fit too.
        many = [{'kind': 'artefact_sections', 'artefact': 'notes.md', 'sections': [f'Part {n}']} for n in range(5)]
        schedule = {'when': {'every_hours': 1}, 'utc_offset_minutes': 0,
                    'task': self.template(acceptance=[{'kind': 'artefact_fields', 'artefact': 'o.json', 'fields': [f'f{n}']} for n in range(4)])}
        self.fault('invalid_acceptance', self.mandate, acceptance=many, schedule=schedule)
        self.assertEqual(self.rows('SELECT * FROM hub_mandates'), [])
        view = self.mandate(acceptance=[SECTIONS])
        # A task may declare read-back only when it may act (autonomy 2).
        self.fault('readback_needs_autonomy_two', self.task, view['id'], acceptance=[{'kind': 'effect_readback'}])
        submitted = self.task(view['id'], work='drafting', autonomy=2, instruction='draft: Short note.',
                              acceptance=[{'kind': 'effect_readback'}])
        self.assertEqual([c['kind'] for c in self.packet(submitted['job']['id'])['acceptance']['checks']],
                         ['artefact_sections', 'effect_readback'])

    def test_the_gate_refuses_a_packet_without_the_mandate_checks(self):
        view = self.mandate(acceptance=[SECTIONS])
        request = {'task_id': self.next('direct'), 'brain': 'synthetic', 'goal': {'ref': view['id'], 'statement': 'x'},
                   'scope': 'company', 'instruction': 'Summarise.', 'context': self.selection(), 'learned': [], 'tools': [],
                   'budget': dict(TASK_BUDGET), 'autonomy': 1}
        binding = {'mandate': view['id'], 'work': 'research', 'trigger': 'operator', 'slot': 'request:direct'}
        self.fault('mandate_checks_missing', self.brains.submit, self.owner, request, binding=binding)
        self.fault('mandate_checks_missing', self.brains.submit, self.owner, {**request, 'acceptance': {'checks': [CITED]}},
                   binding=binding)
        self.fault('mandate_checks_changed', self.brains.submit, self.owner,
                   {**request, 'acceptance': {'declared_by': 'mandate', 'ref': view['id'], 'checks': [CITED]}}, binding=binding)
        self.fault('mandate_mismatch', self.brains.submit, self.owner,
                   {**request, 'acceptance': {'declared_by': 'mandate', 'ref': 'mandate-' + 'f' * 24, 'checks': [SECTIONS]}},
                   binding=binding)
        self.assertEqual(self.rows('SELECT * FROM jobs'), [])
        refused = [json.loads(r['detail']) for r in self.journal('task.refused')]
        self.assertEqual([r['reason'] for r in refused],
                         ['mandate_checks_missing', 'mandate_checks_missing', 'mandate_checks_changed', 'mandate_mismatch'])
        self.assertEqual(refused[0], {'reason': 'mandate_checks_missing', 'stage': 'admission', 'brain': 'synthetic',
                                      'work': 'research', 'trigger': 'operator', 'mandate': view['id'], 'job': None})
        self.assertEqual({r['target'] for r in self.journal('task.refused')}, {'tasks'})
        # The mandate's checks first, then anything else, is admitted.
        admitted = self.brains.submit(self.owner, {**request, 'acceptance': {'declared_by': 'mandate', 'ref': view['id'],
                                                                             'checks': [SECTIONS, CITED]}}, binding=binding)
        self.assertEqual(admitted['brain'], 'synthetic')

    def test_a_brain_cannot_satisfy_checks_by_saying_it_is_done(self):
        view = self.mandate(acceptance=[SECTIONS])
        job_id = self.run_task(view['id'], brain='confident')
        report = self.hub.verifier.verify(self.owner, job_id)
        self.assertEqual((report['state'], report['evidence'], report['failed']), ('failed_checks', 'failed_checks', ['C1']))
        self.assertFalse(report['verified'])

    def test_mandates_written_before_checks_gain_the_column(self):
        view = self.mandate()
        with self.store.connection() as db:
            db.execute('ALTER TABLE hub_mandates DROP COLUMN acceptance')
        brains = BrainHub(self.store, self.jobs, self.registry, self.policy)
        hub = GoalHub(self.store, brains, self.owner)
        self.assertIn('acceptance', {r['name'] for r in self.rows('PRAGMA table_info(hub_mandates)')})
        self.assertEqual(next(g for g in hub.view(self.owner)['goals'] if g['id'] == view['id'])['acceptance'], [])


# Journal attribution for learning ------------------------------------------------------------

class JournalTests(Base):
    def test_budget_events_and_refusals_name_the_brain(self):
        view = self.mandate(budget=budget(total={'tasks': 2}, warn=50))
        for _ in range(2):
            self.run_task(view['id'])
        warning, hard = self.journal('budget.warning')[0], self.journal('budget.hard_stop')[0]
        self.assertEqual((warning['target'], json.loads(warning['detail'])['brain']), ('goal:' + view['id'], 'synthetic'))
        self.assertEqual((hard['target'], json.loads(hard['detail'])['brain']), ('goal:' + view['id'], 'synthetic'))
        self.assertEqual(json.loads(self.journal('goal.paused')[0]['detail']), {'reason': 'budget_total_tasks', 'brain': 'synthetic'})
        self.fault('goal_paused', self.task, view['id'])
        refusal = self.journal('task.refused')[0]
        self.assertEqual((refusal['target'], json.loads(refusal['detail'])),
                         ('tasks', {'reason': 'goal_paused', 'stage': 'admission', 'brain': 'synthetic', 'work': 'research',
                                    'trigger': 'operator', 'mandate': view['id'], 'job': None}))
        self.assertTrue(self.rows("SELECT 1 FROM audit WHERE kind='hub.task.refused'"))
        # The goal's own journal is unchanged by refusals.
        self.assertEqual([j['event'] for j in self.journal() if j['target'] == 'goal:' + view['id']],
                         ['mandate.created', 'budget.warning', 'budget.hard_stop', 'goal.paused'])

    def test_dispatch_refusals_carry_the_job(self):
        view = self.mandate()
        submitted = self.task(view['id'])
        self.records.update(self.owner, self.goal['id'], {'version': 1, 'status': 'achieved'})
        JobWorker(self.jobs, self.hub.backend(), self.owner, 'brain-1', poll_seconds=0.01).run_once()
        detail = json.loads(self.journal('task.refused')[0]['detail'])
        self.assertEqual((detail['reason'], detail['stage'], detail['job']), ('goal_not_active', 'dispatch', submitted['job']['id']))
        self.assertEqual(self.seen, [])

    def test_missed_heartbeat_slots_are_journalled(self):
        schedule = {'when': {'every_hours': 1}, 'utc_offset_minutes': 0, 'task': self.template()}
        view = self.mandate(schedule=schedule)
        self.clock[0] = view['next_due'] + 3 * HOUR + 60
        self.hub.cycle()
        missed = self.journal('heartbeat.missed')
        self.assertEqual((missed[0]['target'], json.loads(missed[0]['detail'])),
                         ('heartbeats', {'mandate': view['id'], 'brain': 'synthetic', 'missed': 3, 'due': view['next_due']}))


# Tasks 1 and 2: routing notes from verified outcomes and goal outcomes ------------------------

class LearningTests(Base):
    def setUp(self):
        super().setUp()
        self.routines = Routines(self.store, self.sup)
        self.sup.routines = self.routines
        self.learning = self.routines.learning
        self.learning.catalogue = self.root / 'no-library' / 'CATALOGUE.json'
        self.learning.upstream_file = self.root / 'upstream-latest.json'
        version = next(r for r in self.routines.view(self.owner)['routines'] if r['kind'] == 'daily-learning')['version']
        self.routines.configure(self.owner, 'daily-learning', {
            'version': version, 'enabled': True, 'schedule': {'daily_at': '21:00'}, 'utc_offset_minutes': 0, 'runs_per_day': 24,
            'nominations_per_run': 10, 'quiet_hours': None, 'interrupt': 'show_now', 'propose_drafts': False})

    def learn(self):
        self.clock[0] += 15
        return self.routines.manual(self.owner, 'daily-learning', {'request_id': self.next('learn')})['outcome']

    def notes(self):
        return {p['key']: p for p in self.learning.view(self.owner)['proposals'] if p['kind'] == 'routing'}

    def hub_tables(self):
        with self.store.connection() as db:
            names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND "
                                              "(name LIKE 'hub_%' OR name LIKE 'verification_%') ORDER BY name")]
            return {n: [tuple(r) for r in db.execute(f'SELECT * FROM "{n}" ORDER BY 1')] for n in names}

    def test_verified_outcomes_are_counted_per_brain_and_kind_of_work(self):
        view = self.mandate(acceptance=[SECTIONS])
        for _ in range(3):
            self.hub.verifier.verify(self.owner, self.run_task(view['id']))
        run = self.learn()
        self.assertEqual(run['window']['evidence']['results_verified'], 3)
        note = self.notes()['routing:synthetic:research:company']
        self.assertEqual(note['detail']['verification'], {'verified': 3, 'failed_checks': 0, 'unverifiable': 0, 'no_checks': 0,
                                                          'not_returned': 0})
        self.assertEqual((note['detail']['verified'], note['detail']['basis']),
                         (3, 'alfred_checks_and_owner_acknowledgement_not_brain_confidence'))
        self.assertIn('mostly verified', note['statement'])
        self.assertLessEqual(len(note['statement']), 600)

    def test_failed_unverifiable_and_unchecked_results_are_kept_apart_and_never_verified(self):
        failing = self.mandate(acceptance=[MISSING])
        for _ in range(3):
            self.hub.verifier.verify(self.owner, self.run_task(failing['id']))
        other = self.mandate(goal=self.make_goal('Plan the offsite'), assigned_brain='synthetic-b')
        unchecked = [self.run_task(other['id']) for _ in range(3)]
        # Acknowledging a result that declared no checks does not make it verified.
        run = self.hub.verifier.verify(self.owner, unchecked[0])
        acknowledged = self.hub.verifier.acknowledge(self.owner, unchecked[0], run['last_run']['sha256'])
        self.assertEqual((acknowledged['state'], acknowledged['evidence']), ('acknowledged', 'no_checks'))
        # A brain that claims every task is done: its checks now run on their own and fail, so its
        # own word never counts as verified. (Declared but never run stays unverifiable; see
        # test_hub_auto_verify.)
        pending = self.mandate(goal=self.make_goal('Brief the crew'), assigned_brain='confident', acceptance=[SECTIONS])
        for _ in range(3):
            self.run_task(pending['id'])
        self.learn()
        notes = self.notes()
        failed = notes['routing:synthetic:research:company']
        self.assertEqual((failed['detail']['verification']['failed_checks'], failed['detail']['verified']), (3, 0))
        self.assertIn('often failed', failed['statement'])
        plain = notes['routing:synthetic-b:research:company']
        self.assertEqual((plain['detail']['verification']['no_checks'], plain['detail']['verified'], plain['detail']['acknowledged']),
                         (3, 0, 0))
        self.assertIn('mostly not verified', plain['statement'])
        confident = notes['routing:confident:research:company']
        self.assertEqual((confident['detail']['verification']['failed_checks'], confident['detail']['verified']), (3, 0))
        self.assertNotIn('100 percent', json.dumps(confident))
        self.assertNotIn('12 of 12', json.dumps(confident))
        summary = self.hub.verifier.outcomes(self.owner)
        self.assertEqual(summary['evidence_by_brain']['synthetic-b']['no_checks'], 3)
        self.assertEqual(summary['by_brain']['synthetic-b']['verified'], 1)  # H4's own state count is unchanged.

    def test_goal_outcomes_become_routing_notes_and_learning_changes_nothing(self):
        view = self.mandate(budget=budget(total={'tasks': 1}, warn=50))
        self.run_task(view['id'])
        for _ in range(3):
            self.fault('goal_paused', self.task, view['id'])
        before = self.hub_tables()
        run = self.learn()
        self.assertEqual(before, self.hub_tables())
        evidence = run['window']['evidence']
        self.assertEqual((evidence['hub_hard_stops'], evidence['mandate_refusals'], evidence['hub_budget_warnings']), (1, 3, 0))  # At the limit: a hard stop, not a warning.
        note = self.notes()['routing-goals:synthetic']
        self.assertEqual((note['rule'], note['detail']['hard_stops'], note['detail']['mandate_refusals'],
                          note['detail']['refusal_reasons']), ('goal_outcomes', 1, 3, {'goal_paused': 3}))
        self.assertIn('refused by the mandate', note['statement'])
        self.assertTrue(all(e.startswith('hub_journal:') for e in note['evidence']))
        # Accepting the note changes no budget, mandate or assignment either.
        self.learning.accept(self.owner, note['id'], {'version': note['version']})
        self.assertEqual(before, self.hub_tables())
        self.assertEqual(self.current(view['id'])['state'], 'paused')

    def test_owner_controls_count_and_budget_holds_are_not_counted_twice(self):
        view = self.mandate()
        self.hub.control(self.owner, 'goal', view['id'], 'pause', {'version': 1})
        self.hub.control(self.owner, 'goal', view['id'], 'resume', {'version': 2})
        self.hub.control(self.owner, 'goal', view['id'], 'reassign', {'version': 3, 'brain': 'synthetic-b'})
        self.hub.control(self.owner, 'goal', view['id'], 'reassign', {'version': 4, 'brain': 'synthetic'})
        self.hub.control(self.owner, 'goal', view['id'], 'reassign', {'version': 5, 'brain': 'synthetic-b'})
        run = self.learn()
        self.assertEqual((run['window']['evidence']['paused_or_stopped_by_you'], run['window']['evidence']['work_reassigned']), (1, 3))
        note = self.notes()['routing-goals:synthetic']
        self.assertEqual((note['detail']['paused_or_stopped_by_you'], note['detail']['moved_to_another_brain']), (1, 2))
        self.assertIn('paused, stopped or moved', note['statement'])
        self.assertNotIn('routing-goals:synthetic-b', self.notes())  # One move away is below the threshold.


# Task 4: verification over HTTP ----------------------------------------------------------------

class HTTPTests(Base):
    def setUp(self):
        super().setUp()
        from alfred.desk_http import DeskHTTPServer
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

    def failed_result(self):
        view = self.mandate(acceptance=[SECTIONS, MISSING])
        return self.run_task(view['id'])

    def test_routes_keep_the_session_csrf_origin_and_version_checks(self):
        job_id = self.failed_result()
        path = f'/desk/hub/results/{job_id}'
        self.assertEqual(self.raw('/desk/hub/results')[0], 401)
        self.login(self.owner)
        status, listing = self.raw('/desk/hub/results')
        self.assertEqual((status, listing['available'], listing['no_checks_counted_as_verified']), (200, True, False))
        item = listing['results'][0]
        # The checks already ran once on their own when the result arrived.
        self.assertEqual((item['job'], item['evidence'], item['declared'], item['runs'], item['last_run']['initiated']),
                         (job_id, 'failed_checks', 2, 1, 'automatic'))
        self.assertEqual((item['work']['goal_title'], item['work']['work']), ('Deliver the quarterly review', 'research'))
        self.assertEqual(listing['by_brain']['synthetic']['failed_checks'], 1)
        self.assertEqual(self.raw(path + '/verify', {'runs': 1}, {'X-CSRF-Token': 'wrong'}), (403, {'error': 'csrf_rejected'}))
        self.assertEqual(self.raw(path + '/verify', {'runs': 1}, {'Origin': 'http://evil.example'}), (403, {'error': 'invalid_origin'}))
        self.assertEqual(self.raw(path + '/verify', {'runs': 0}), (409, {'error': 'verification_changed'}))
        self.assertEqual(self.raw(path + '/verify', {'runs': 3}), (409, {'error': 'verification_changed'}))
        self.assertEqual(self.raw(path + '/verify', {'runs': 1, 'extra': 1})[0], 400)
        status, verified = self.raw(path + '/verify', {'runs': 1})
        self.assertEqual((status, verified['result']['state'], verified['result']['failed']), (200, 'failed_checks', ['C2']))
        self.assertEqual((verified['declared']['by'], verified['result']['last_run']['initiated']), ('mandate', 'owner'))
        self.assertTrue(verified['sources_readable'])
        reasons = verified['result']['last_run']['report']['checks'][1]['reasons']
        self.assertEqual(reasons, [{'code': 'section_missing', 'section': 'Risks'}])
        self.assertEqual(self.raw(path + '/verify', {'runs': 1}), (409, {'error': 'verification_changed'}))
        sha = verified['result']['last_run']['sha256']
        self.assertEqual(self.raw(path + '/acknowledge', {'run_sha256': 'b' * 64, 'accept_failures': True}),
                         (409, {'error': 'acknowledgement_mismatch'}))
        self.assertEqual(self.raw(path + '/acknowledge', {'run_sha256': sha, 'accept_failures': False}),
                         (409, {'error': 'failed_checks_need_explicit_acceptance'}))
        status, acknowledged = self.raw(path + '/acknowledge', {'run_sha256': sha, 'accept_failures': True})
        self.assertEqual((status, acknowledged['result']['state'], acknowledged['result']['acknowledged']['over']),
                         (200, 'acknowledged', 'failed_checks'))
        status, detail = self.raw(path)
        self.assertEqual((status, detail['runs_total'], detail['authority_granted']), (200, 2, False))
        item = self.raw('/desk/hub/results')[1]['results'][0]
        self.assertEqual((item['evidence'], item['state'], item['last_run']['counts']),
                         ('verified', 'acknowledged', {'passed': 1, 'failed': 1, 'unverifiable': 0}))
        self.assertEqual(self.raw('/desk/hub/results/job-unknown')[0], 404)
        self.assertEqual(self.raw(f'/desk/hub/results/{job_id}/approve', {})[0], 404)

    def test_only_the_submitting_person_reads_or_acts(self):
        job_id = self.failed_result()
        path = f'/desk/hub/results/{job_id}'
        self.login(self.reader)
        status, listing = self.raw('/desk/hub/results')
        self.assertEqual((status, listing['available'], listing['results']), (200, False, []))
        self.assertEqual(self.raw(path), (403, {'error': 'forbidden'}))
        self.assertEqual(self.raw(path + '/verify', {'runs': 1}), (403, {'error': 'forbidden'}))
        self.login(self.second)  # Another person, also an owner.
        self.assertEqual(self.raw('/desk/hub/results')[1]['results'], [])
        self.assertEqual(self.raw(path), (404, {'error': 'not_found'}))
        self.assertEqual(self.raw(path + '/verify', {'runs': 1}), (404, {'error': 'not_found'}))
        # Only the run made on its own when the result arrived; nobody else's attempt added one.
        self.assertEqual([r['initiated'] for r in self.rows('SELECT initiated FROM verification_runs')], ['automatic'])
        # Another device of the same person is the submitter too (policy.ledger), with no more authority.
        policy = IdentityPolicy(self.store)
        tablet = policy.redeem_pairing(policy.offer_pairing(self.owner, 'owner')['code'], 'Fictional tablet')['key']
        self.login(tablet)
        self.assertEqual(self.raw('/desk/hub')[1]['reason'], 'not_hosted')
        status, verified = self.raw(path + '/verify', {'runs': 1})
        self.assertEqual((status, verified['result']['state']), (200, 'failed_checks'))
        self.assertEqual(self.raw('/desk/hub/results')[1]['results'][0]['job'], job_id)
        self.assertEqual(self.rows('SELECT actor FROM verification_results'), [{'actor': self.rows('SELECT actor FROM brain_tasks')[0]['actor']}])

    def test_reasons_are_withheld_once_the_sources_cannot_be_read(self):
        job_id = self.failed_result()
        self.hub.verifier.verify(self.owner, job_id)
        revoke_all(self.store, self.owner)
        self.login(self.owner)
        status, detail = self.raw(f'/desk/hub/results/{job_id}')
        self.assertEqual((status, detail['sources_readable']), (200, False))
        report = detail['result']['last_run']['report']
        self.assertTrue(report['reasons_withheld'])
        self.assertTrue(all(c['reasons'] == [] for c in report['checks']))
        self.assertTrue(all(run['report']['reasons_withheld'] for run in detail['runs']))
        self.assertEqual(detail['result']['state'], 'failed_checks')  # The outcome itself stays.


if __name__ == '__main__':
    unittest.main()
