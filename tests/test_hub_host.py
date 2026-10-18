"""The host builds the goal hub only when asked (coordination/BACKLOG.md item C2).

Synthetic data only: an invented vault note, the deterministic SyntheticBrain, no model and
no network. Real SQLite, the real job coordinator, goal hub and HTTP handler, and a real
`serve` process for the switch itself. These tests prove that:

* without the switch nothing is built: no hub tables, no brain worker, and `/desk/hub`
  answers `hub_not_configured` as before;
* with `--hub synthetic` the host registers only the synthetic test brain, allows no cloud
  scope and no tool, enrols one brain worker that takes only brain tasks, and runs a task
  from submission to an accounted result without anyone driving it;
* starting twice over the same data directory works, and stopping ends the worker.
"""
from __future__ import annotations
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

from alfred.desk import init_demo
from alfred.executive import ExecutiveRecords
from alfred.hub_host import CHOICES, start_goal_hub
from alfred.jobs import JobCoordinator
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.local import Fault
from grant_helpers import grant_all

REPOSITORY = Path(__file__).resolve().parents[1]
DAY = 86400
WORKSPACE = 'ws-hub-host-4410'
PLAN = '# Plan\nThe harbour survey is due on Thursday.\n'
NONE = {'tokens': None, 'money_pence': None, 'wall_seconds': None, 'tasks': None}


def budget(total):
    return {'daily': dict(NONE), 'total': {**NONE, **total}, 'warn_percent': 80, 'utc_offset_minutes': 0}


def tables(path):
    with sqlite3.connect(path) as db:
        return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


class InProcessTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = KnowledgeStore(self.root / 'desk.sqlite')
        self.owner = self.store.provision(WORKSPACE, 'owner', 'owner', ttl=30 * DAY)
        self.source = self.store.provision(WORKSPACE, 'source', 'source', ttl=30 * DAY)
        grant_all(self.store, self.owner)
        (self.root / 'project').mkdir()
        (self.root / 'vault').mkdir()
        (self.root / 'vault' / 'Plan.md').write_text(PLAN)
        self.sup = KnowledgeSupervisor(self.store, self.owner, self.source, self.root / 'project', vault=self.root / 'vault')
        self.sup.vault.scan()
        self.note = next(n for n in self.store.knowledge(self.owner)['nodes'] if n['title'] == 'Plan')
        self.jobs = JobCoordinator(self.store)

    def start(self, choice='synthetic'):
        hub, halt = start_goal_hub(self.store, self.jobs, self.owner, choice, poll_seconds=0.02)
        self.addCleanup(halt)
        return hub, halt

    def test_off_builds_nothing(self):
        self.assertEqual(CHOICES, ('off', 'synthetic'))
        before = tables(self.root / 'desk.sqlite')
        hub, halt = self.start('off')
        self.assertIsNone(hub)
        self.assertTrue(halt())
        self.assertEqual(tables(self.root / 'desk.sqlite'), before)
        self.assertNotIn('local-brain', [w['id'] for w in self.jobs.workers(self.owner)])

    def test_unknown_choice_is_refused_before_anything_is_built(self):
        before = tables(self.root / 'desk.sqlite')
        for choice in ('claude', 'hermes', '', None, 'SYNTHETIC'):
            with self.assertRaises(Fault) as caught:
                start_goal_hub(self.store, self.jobs, self.owner, choice)
            self.assertEqual(caught.exception.code, 'invalid_hub_brain')
        self.assertEqual(tables(self.root / 'desk.sqlite'), before)

    def test_synthetic_registers_only_the_test_brain_with_no_cloud_and_no_tools(self):
        hub, _ = self.start()
        self.assertEqual([s.id for s in hub.registry.specs()], ['synthetic'])
        self.assertEqual(hub.registry.specs()[0].locality, 'local')
        self.assertEqual((hub.policy.cloud_scopes, hub.policy.permitted_tools), (frozenset(), frozenset()))
        workers = {w['id']: w for w in self.jobs.workers(self.owner)}
        self.assertEqual(workers['local-brain']['capabilities'], ['brain_task'])
        self.assertIn('hub_mandates', tables(self.root / 'desk.sqlite'))

    def test_a_task_runs_to_an_accounted_result_without_anyone_driving_it(self):
        hub, _ = self.start()
        goal = ExecutiveRecords(self.store).create(self.owner, {
            'request_id': 'goal-1', 'kind': 'goal', 'title': 'Finish the harbour survey', 'detail': '',
            'project': None, 'due': None, 'rank': None, 'support': None})
        hub.set_budget(self.owner, 'overall', None, {'version': 0, 'budget': budget({'tasks': 10})})
        mandate = hub.create_mandate(self.owner, {
            'request_id': 'mandate-1', 'goal': goal['id'], 'scope_class': 'company',
            'deadline': self.store.now() + 20 * DAY, 'success_test': 'The surveyor signs off.',
            'autonomy': {'research': 1}, 'brains': ['synthetic'], 'assigned_brain': 'synthetic', 'tools': [],
            'budget': budget({'tasks': 5}), 'schedule': None})
        task = hub.submit_task(self.owner, mandate['id'], {
            'request_id': 'task-1', 'brain': None, 'work': 'research', 'instruction': 'Summarise the plan.',
            'context': [{'note': self.note['id'], 'start_line': 2, 'end_line': 2}], 'learned': [], 'tools': [],
            'budget': {'wall_seconds': 10, 'tokens': 30, 'money_pence': 0, 'steps': 50}, 'autonomy': 1})
        job = task['job']['id']
        deadline = time.monotonic() + 20
        while not self.jobs.view(self.owner, job)['finished']:
            self.assertLess(time.monotonic(), deadline, 'the host brain worker did not run the task')
            time.sleep(0.02)
        self.sup.goals = hub
        self.sup.cycle()  # The host's own supervisor loop accounts the result.
        with self.store.connection() as db:
            row = db.execute('SELECT result, accounted, brain FROM hub_tasks WHERE job_id=?', (job,)).fetchone()
        self.assertEqual((row['result'], row['brain']), ('accepted', 'synthetic'))
        self.assertIsNotNone(row['accounted'])
        self.assertEqual(hub.result(self.owner, job)['result']['evidence'], 'no_checks')

    def test_starting_twice_over_the_same_data_works(self):
        _, halt = self.start()
        self.assertTrue(halt())
        hub, _ = self.start()
        self.assertEqual([w['id'] for w in self.jobs.workers(self.owner)].count('local-brain'), 1)
        self.assertEqual(hub.view(self.owner)['available'], True)

    def test_halt_stops_the_worker(self):
        _, halt = self.start()
        self.assertTrue(halt())
        self.assertTrue(halt())  # Stopping again is harmless.


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class RealHostTests(unittest.TestCase):
    """A real `serve` process, with and without the switch, stopped with SIGTERM."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / 'demo'
        self.keys = init_demo(self.home)
        self.process = None
        self.addCleanup(self.kill)

    def start(self, *extra):
        self.port = free_port()
        self.process = subprocess.Popen([sys.executable, '-m', 'alfred.desk', 'serve', '--data-dir', str(self.home),
                                         '--port', str(self.port), *extra], cwd=REPOSITORY,
                                        env=dict(os.environ, PYTHONUNBUFFERED='1'), stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, start_new_session=True)
        lines, deadline = [], time.monotonic() + 30
        while time.monotonic() < deadline:
            line = self.process.stdout.readline()
            if not line:
                break
            lines.append(line)
            if line.startswith('Use the access command'):
                return ''.join(lines)
        self.fail('host did not start: ' + ''.join(lines))

    def stop(self):
        os.killpg(self.process.pid, signal.SIGTERM)
        self.assertEqual(self.process.wait(30), 0)
        self.process.stdout.close()

    def kill(self):
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(10)
        if self.process and not self.process.stdout.closed:
            self.process.stdout.close()

    def hub(self):
        origin = f'http://127.0.0.1:{self.port}'
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        c.request('POST', '/desk/login', json.dumps({'key': self.keys['owner']}), {'Content-Type': 'application/json', 'Origin': origin})
        r = c.getresponse(); r.read(); cookie = r.getheader('Set-Cookie').split(';')[0]; c.close()
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        c.request('GET', '/desk/hub', headers={'Cookie': cookie})
        r = c.getresponse(); body = json.loads(r.read()); c.close()
        return r.status, body

    def test_without_the_switch_the_hub_is_not_configured(self):
        output = self.start()
        self.assertNotIn('Goal hub', output)
        self.assertEqual(self.hub(), (409, {'error': 'hub_not_configured'}))
        self.stop()
        self.assertNotIn('hub_mandates', tables(self.home / 'desk.sqlite'))

    def test_with_the_switch_the_hub_answers_and_says_what_it_is(self):
        output = self.start('--hub', 'synthetic')
        self.assertIn('Goal hub on: synthetic test brain only. No model, no cloud, no tools.', output)
        status, view = self.hub()
        self.assertEqual((status, view['available']), (200, True))
        self.stop()
        # Off again on the next start, even though the hub's tables now exist.
        self.start()
        self.assertEqual(self.hub(), (409, {'error': 'hub_not_configured'}))
        self.stop()

    def test_an_unknown_brain_is_refused_by_the_command_line(self):
        run = subprocess.run([sys.executable, '-m', 'alfred.desk', 'serve', '--data-dir', str(self.home), '--hub', 'claude'],
                             cwd=REPOSITORY, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 2)
        self.assertIn("invalid choice: 'claude'", run.stderr)


if __name__ == '__main__':
    unittest.main()
