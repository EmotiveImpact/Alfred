"""Checks run automatically when the hub accounts a result (coordination/BACKLOG.md item A3).

Synthetic data only: the fictional vault note and fixture brains of tests/test_hub_integrate.py,
plus one fixture brain here whose bundle the H1 contract refuses. No model, no network. Real
SQLite, the real job coordinator and worker, goal hub, verifier and daily learning routine.
These tests prove that:

* an accepted result whose packet declares checks is verified by the next supervisor cycle,
  once, with no owner action, and the run records that it was started automatically;
* a result without declared checks, a refused bundle and a stopped job are never verified
  automatically, and "no checks" never becomes "verified";
* a check that crashes is unverifiable, a verification that cannot run at all is recorded
  and leaves the cycle running, and nothing is re-run automatically;
* the owner's own re-run still needs the number of runs they saw;
* a database written before this change opens, reads its old runs as the owner's, and does
  not verify results it had already accounted;
* daily learning counts an automatic run exactly like an owner-started one, and a brain's
  own word still counts for nothing.
"""
import json
import unittest

from alfred import brain as plug
from alfred import hub_goals
from alfred.brain import BrainHub, BrainSpec, SyntheticBrain
from alfred.hub_goals import GoalHub
from alfred.jobs import JobWorker
from alfred.local import Fault
from alfred.routines import Routines
from alfred.verification import Verifier, outcome_rows
from test_hub_integrate import CITED, MISSING, SECTIONS, Base


class RefusedBrain(SyntheticBrain):
    """Returns an artefact whose hash does not match its content, which H1 refuses."""

    def __init__(self):
        super().__init__(BrainSpec(id='refused', label='Refused fixture', locality='local', version='1',
                                   scopes=frozenset(plug.SCOPE_CLASSES), tools=frozenset(), max_autonomy=2))

    def run(self, packet, meter):
        bundle = super().run(packet, meter)
        bundle['artefacts'][0]['sha256'] = '0' * 64
        return bundle


class AutoBase(Base):
    def setUp(self):
        super().setUp()
        self.registry.register(RefusedBrain())

    def mandate(self, goal=None, **over):
        over.setdefault('brains', ['synthetic', 'synthetic-b', 'confident', 'refused'])
        return super().mandate(goal, **over)

    def finish(self, mandate_id, count=1, **over):
        """Submit tasks, let the worker finish them, then run one supervisor cycle."""
        jobs = [self.task(mandate_id, **over)['job']['id'] for _ in range(count)]
        worker = JobWorker(self.jobs, self.hub.backend(), self.owner, 'brain-1', poll_seconds=0.01, heartbeat_seconds=0.05)
        self.assertEqual(sorted(worker.run_once() for _ in jobs), sorted(jobs))
        self.clock[0] += 5
        self.hub.cycle()
        return jobs

    def runs(self, job_id):
        return self.rows('SELECT position,outcome,initiated FROM verification_runs WHERE job_id=? ORDER BY position', job_id)

    def auto(self, job_id):
        return self.rows('SELECT result,auto_verify FROM hub_tasks WHERE job_id=?', job_id)[0]


class RunsWhenAResultArrives(AutoBase):
    def test_passing_checks_are_verified_by_the_next_cycle_without_the_owner(self):
        view = self.mandate(acceptance=[SECTIONS])
        job_id, = self.finish(view['id'], acceptance=[CITED])
        self.assertEqual(self.runs(job_id), [{'position': 1, 'outcome': 'checked', 'initiated': 'automatic'}])
        self.assertEqual(self.auto(job_id), {'result': 'accepted', 'auto_verify': 'ran'})
        shown = self.hub.result(self.owner, job_id)
        self.assertEqual((shown['result']['state'], shown['result']['verified'], shown['result']['evidence']),
                         ('checked', True, 'verified'))
        self.assertEqual(shown['result']['last_run']['initiated'], 'automatic')
        self.assertEqual([(r['position'], r['initiated']) for r in shown['runs']], [(1, 'automatic')])
        listed = next(r for r in self.hub.results(self.owner)['results'] if r['job'] == job_id)
        self.assertEqual((listed['state'], listed['last_run']['initiated']), ('checked', 'automatic'))
        self.assertTrue(self.rows("SELECT 1 FROM audit WHERE kind='verification.run_checked' AND subject=?", job_id))

    def test_a_failing_check_is_failed_checks(self):
        view = self.mandate(acceptance=[MISSING])
        job_id, = self.finish(view['id'])
        self.assertEqual(self.runs(job_id), [{'position': 1, 'outcome': 'failed_checks', 'initiated': 'automatic'}])
        state = self.hub.result(self.owner, job_id)['result']
        self.assertEqual((state['state'], state['verified'], state['failed']), ('failed_checks', False, ['C1']))

    def test_a_brain_saying_it_is_done_still_fails_the_owner_checks(self):
        view = self.mandate(acceptance=[SECTIONS], assigned_brain='confident')
        job_id, = self.finish(view['id'])
        state = self.hub.result(self.owner, job_id)['result']
        self.assertEqual((state['state'], state['evidence'], state['failed']), ('failed_checks', 'failed_checks', ['C1']))

    def test_a_result_without_checks_is_left_alone(self):
        view = self.mandate()
        job_id, = self.finish(view['id'])
        self.assertEqual(self.runs(job_id), [])
        self.assertEqual(self.auto(job_id), {'result': 'accepted', 'auto_verify': 'not_needed'})
        state = self.hub.result(self.owner, job_id)['result']
        self.assertEqual((state['state'], state['verified'], state['evidence'], state['runs']),
                         ('returned', False, 'no_checks', 0))

    def test_a_refused_bundle_is_not_verified(self):
        view = self.mandate(acceptance=[SECTIONS], assigned_brain='refused')
        job_id, = self.finish(view['id'])
        self.assertEqual(self.auto(job_id), {'result': 'refused', 'auto_verify': 'not_needed'})
        self.assertEqual(self.runs(job_id), [])
        state = self.hub.result(self.owner, job_id)['result']
        self.assertEqual((state['state'], state['verified'], state['runs']), ('failed_checks', False, 0))

    def test_a_job_that_never_ran_is_not_verified(self):
        view = self.mandate(acceptance=[SECTIONS])
        submitted = self.task(view['id'])['job']['id']
        self.jobs.cancel(self.owner, submitted)
        self.clock[0] += 5
        self.hub.cycle()
        self.assertEqual(self.runs(submitted), [])
        task = self.auto(submitted)
        self.assertNotEqual(task['result'], 'accepted')
        self.assertEqual(task['auto_verify'], 'not_needed')

    def test_automatic_runs_follow_the_accounting_batch(self):
        view = self.mandate(acceptance=[SECTIONS])
        original = hub_goals.ACCOUNT_PER_CYCLE
        hub_goals.ACCOUNT_PER_CYCLE = 2
        self.addCleanup(setattr, hub_goals, 'ACCOUNT_PER_CYCLE', original)
        jobs = self.finish(view['id'], count=3)
        self.assertEqual(sorted(len(self.runs(j)) for j in jobs), [0, 1, 1])
        self.hub.cycle()
        self.assertEqual([len(self.runs(j)) for j in jobs], [1, 1, 1])


class NeverStopsTheCycle(AutoBase):
    def test_a_crashing_check_is_unverifiable(self):
        view = self.mandate(acceptance=[SECTIONS, CITED])

        def crash(check, ctx):
            raise RuntimeError('synthetic crash inside a check')
        self.hub.verifier._artefact_sections = crash
        job_id, = self.finish(view['id'])
        report = self.hub.result(self.owner, job_id)['result']['last_run']['report']
        self.assertEqual([(c['id'], c['status']) for c in report['checks']], [('C1', 'unverifiable'), ('C2', 'passed')])
        self.assertEqual((report['outcome'], self.runs(job_id)[0]['initiated']), ('returned', 'automatic'))
        self.assertFalse(self.hub.result(self.owner, job_id)['result']['verified'])

    def test_a_verification_that_cannot_run_is_recorded_and_the_cycle_carries_on(self):
        view = self.mandate(acceptance=[SECTIONS])
        real, calls = self.hub.verifier.verify, []

        def flaky(bearer, job_id, **kwargs):
            calls.append(job_id)
            if len(calls) == 1:
                raise RuntimeError('synthetic failure outside any check')
            if len(calls) == 2:
                raise Fault('result_not_available', 409)
            return real(bearer, job_id, **kwargs)
        self.hub.verifier.verify = flaky
        schedule = {'when': {'every_hours': 1}, 'utc_offset_minutes': 0, 'task': self.template()}
        beat = self.mandate(goal=self.make_goal('Brief the crew'), schedule=schedule)
        self.clock[0] = max(self.clock[0], beat['next_due'] - 5)
        self.assertEqual(sorted(self.finish(view['id'], count=3)), sorted(calls))
        first, second, third = calls  # In the order the hub ran them.
        self.assertEqual([self.auto(j)['auto_verify'] for j in (first, second, third)],
                         ['not_run', 'not_run:result_not_available', 'ran'])
        self.assertEqual((self.runs(first), self.runs(second), len(self.runs(third))), ([], [], 1))
        self.assertTrue(self.rows("SELECT 1 FROM audit WHERE kind='hub.auto_verify_not_run' AND subject=?", first))
        # The heartbeats after it still ran in the same cycle.
        self.assertEqual([b['status'] for b in self.rows('SELECT status FROM hub_heartbeats')], ['submitted'])
        # Nothing is retried automatically; the owner can still run the checks.
        self.hub.cycle()
        self.assertEqual(len(calls), 3)
        self.hub.verifier.verify = real
        self.assertEqual(self.hub.verify_result(self.owner, first, {'runs': 0})['result']['state'], 'checked')
        self.assertEqual(self.runs(first), [{'position': 1, 'outcome': 'checked', 'initiated': 'owner'}])


class NeverRunsTwice(AutoBase):
    def test_a_second_cycle_does_not_run_again_and_the_owner_rerun_is_guarded(self):
        view = self.mandate(acceptance=[SECTIONS])
        job_id, = self.finish(view['id'])
        for _ in range(3):
            self.clock[0] += 60
            self.hub.cycle()
        self.assertEqual(len(self.runs(job_id)), 1)
        self.fault('verification_changed', self.hub.verify_result, self.owner, job_id, {'runs': 0})
        again = self.hub.verify_result(self.owner, job_id, {'runs': 1})
        self.assertEqual([(r['position'], r['initiated']) for r in again['runs']], [(1, 'automatic'), (2, 'owner')])
        self.assertEqual(again['result']['last_run']['initiated'], 'owner')

    def test_a_run_recorded_before_a_crash_is_not_repeated(self):
        view = self.mandate(acceptance=[SECTIONS])
        job_id, = self.finish(view['id'])
        # As if the process stopped after the run was recorded but before the task was marked.
        with self.store.connection() as db:
            db.execute("UPDATE hub_tasks SET auto_verify='pending' WHERE job_id=?", (job_id,))
        self.hub.cycle()
        self.assertEqual((len(self.runs(job_id)), self.auto(job_id)['auto_verify']), (1, 'ran'))

    def test_a_pending_run_left_by_a_crash_is_completed_once(self):
        view = self.mandate(acceptance=[SECTIONS])
        real = self.hub.verifier.verify
        self.hub.verifier.verify = lambda *a, **k: (_ for _ in ()).throw(SystemExit('stopped mid-run'))
        with self.assertRaises(SystemExit):
            self.finish(view['id'])
        job_id = self.rows('SELECT job_id FROM hub_tasks')[0]['job_id']
        self.assertEqual(self.auto(job_id), {'result': 'accepted', 'auto_verify': 'pending'})
        self.hub.verifier.verify = real
        self.hub.cycle()
        self.assertEqual(self.runs(job_id), [{'position': 1, 'outcome': 'checked', 'initiated': 'automatic'}])
        self.hub.cycle()
        self.assertEqual(len(self.runs(job_id)), 1)

    def test_an_owner_run_made_first_is_not_followed_by_an_automatic_one(self):
        view = self.mandate(acceptance=[SECTIONS])
        self.hub._auto_verify = lambda: None  # The owner verifies between accounting and the automatic run.
        job_id, = self.finish(view['id'])
        self.hub.verify_result(self.owner, job_id, {'runs': 0})
        del self.hub._auto_verify
        self.hub.cycle()
        self.assertEqual(self.runs(job_id), [{'position': 1, 'outcome': 'checked', 'initiated': 'owner'}])
        self.assertEqual(self.auto(job_id)['auto_verify'], 'ran')
        self.assertFalse(self.rows("SELECT 1 FROM audit WHERE kind='hub.auto_verify_not_run'"))

    def test_the_verifier_refuses_an_unknown_initiator(self):
        view = self.mandate(acceptance=[SECTIONS])
        job_id, = self.finish(view['id'])
        for value in ('brain', '', None, 'AUTOMATIC', 1):
            self.fault('invalid_initiated', self.hub.verifier.verify, self.owner, job_id, initiated=value)
        self.assertEqual(len(self.runs(job_id)), 1)


class OlderDatabases(AutoBase):
    def test_a_database_from_before_this_change_reads_old_runs_as_the_owner_and_runs_nothing_new(self):
        view = self.mandate(acceptance=[SECTIONS])
        old_run, old_unrun = self.finish(view['id'], count=2)
        with self.store.connection() as db:
            db.execute('DELETE FROM verification_results WHERE job_id=?', (old_unrun,))
            db.execute('DROP TRIGGER verification_runs_no_update')
            db.execute('DELETE FROM verification_runs WHERE job_id=?', (old_unrun,))
            db.execute('ALTER TABLE verification_runs DROP COLUMN initiated')
            db.execute('ALTER TABLE hub_tasks DROP COLUMN auto_verify')
            db.execute("CREATE TRIGGER verification_runs_no_update BEFORE UPDATE ON verification_runs "
                       "BEGIN SELECT RAISE(ABORT,'verification_runs_append_only'); END")
        brains = BrainHub(self.store, self.jobs, self.registry, self.policy)
        hub = GoalHub(self.store, brains, self.owner)
        self.assertIn('initiated', {r['name'] for r in self.rows('PRAGMA table_info(verification_runs)')})
        self.assertIn('auto_verify', {r['name'] for r in self.rows('PRAGMA table_info(hub_tasks)')})
        self.assertEqual([r['initiated'] for r in hub.result(self.owner, old_run)['runs']], ['owner'])
        self.assertEqual(hub.result(self.owner, old_run)['result']['last_run']['initiated'], 'owner')
        hub.cycle()
        # Accounted before the change: never verified behind the owner's back.
        self.assertEqual(self.runs(old_unrun), [])
        self.assertEqual(hub.result(self.owner, old_unrun)['result']['runs'], 0)
        # The update guard still holds on the rebuilt table.
        with self.store.connection() as db, self.assertRaises(Exception):
            db.execute("UPDATE verification_runs SET outcome='checked'")

    def test_a_fresh_verifier_on_an_old_table_adds_the_column_once(self):
        Verifier(self.brains)
        Verifier(self.brains)
        names = [r['name'] for r in self.rows('PRAGMA table_info(verification_runs)')]
        self.assertEqual(names.count('initiated'), 1)


class LearningCountsItTheSame(AutoBase):
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

    def test_an_automatic_run_counts_exactly_like_an_owner_run(self):
        automatic = self.mandate(acceptance=[SECTIONS])
        auto_jobs = self.finish(automatic['id'], count=3)
        with self.store.connection() as db:
            rows = {r['job']: r for r in outcome_rows(db, self.hub.scope, [self.hub.host_id])}
        self.assertEqual({rows[j]['evidence'] for j in auto_jobs}, {'verified'})
        # The same results verified again by the owner keep the same evidence class.
        for job_id in auto_jobs:
            self.hub.verify_result(self.owner, job_id, {'runs': 1})
        with self.store.connection() as db:
            again = {r['job']: r for r in outcome_rows(db, self.hub.scope, [self.hub.host_id])}
        self.assertEqual([again[j]['evidence'] for j in auto_jobs], [rows[j]['evidence'] for j in auto_jobs])
        confident = self.mandate(goal=self.make_goal('Brief the crew'), assigned_brain='confident', acceptance=[SECTIONS])
        self.finish(confident['id'], count=3)
        self.clock[0] += 15
        run = self.routines.manual(self.owner, 'daily-learning', {'request_id': self.next('learn')})['outcome']
        self.assertEqual(run['window']['evidence']['results_verified'], 3)
        notes = {p['key']: p for p in self.learning.view(self.owner)['proposals'] if p['kind'] == 'routing'}
        self.assertEqual(notes['routing:synthetic:research:company']['detail']['verified'], 3)
        said_done = notes['routing:confident:research:company']['detail']
        self.assertEqual((said_done['verified'], said_done['verification']['failed_checks']), (0, 3))
        self.assertNotIn('12 of 12', json.dumps(notes['routing:confident:research:company']))


if __name__ == '__main__':
    unittest.main()
