"""The host builds the goal hub only when asked (coordination/BACKLOG.md item C2).

Synthetic data only: an invented vault note, the deterministic SyntheticBrain, no model and
no network. Real SQLite, the real job coordinator, goal hub and HTTP handler, and a real
`serve` process for the switch itself. These tests prove that:

* without the switch nothing is built: no hub tables, no brain worker, and `/desk/hub`
  answers `hub_not_configured` as before;
* with `--hub synthetic` the host registers only the synthetic test brain, allows no cloud
  scope and no tool, enrols one brain worker that takes only brain tasks, and runs a task
  from submission to an accounted result without anyone driving it;
* starting twice over the same data directory works, and stopping ends the worker;
* with `hermes` the host checks the box image against this checkout's pins before building
  anything, registers Hermes beside the synthetic brain with the cloud allowed for the
  owner's areas only, and a personal task goes through the relay to a stand-in Claude
  connection (no Docker, no network) and back to an accepted result, while a company
  mandate naming Hermes is refused.
"""
from __future__ import annotations
from contextlib import closing
import hashlib
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
from alfred.anthropic_provider import KeySource
from alfred import hermes_box as hb
from alfred.hub_host import CHOICES, HermesSetup, hermes_brain, start_goal_hub
from alfred.jobs import JobCoordinator
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.local import Fault
from grant_helpers import grant_all
from test_hermes_box import StandInBox, sse

REPOSITORY = Path(__file__).resolve().parents[1]
DAY = 86400
WORKSPACE = 'ws-hub-host-4410'
PLAN = '# Plan\nThe harbour survey is due on Thursday.\n'
NONE = {'tokens': None, 'money_pence': None, 'wall_seconds': None, 'tasks': None}


def budget(total):
    return {'daily': dict(NONE), 'total': {**NONE, **total}, 'warn_percent': 80, 'utc_offset_minutes': 0}


def tables(path):
    with closing(sqlite3.connect(path)) as db:  # sqlite3's own context manager does not close
        return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


class Fixture(unittest.TestCase):
    """A synthetic desk store with one vault note, and the job coordinator."""

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


class InProcessTests(Fixture):
    def start(self, choice='synthetic'):
        hub, halt = start_goal_hub(self.store, self.jobs, self.owner, choice, poll_seconds=0.02)
        self.addCleanup(halt)
        return hub, halt

    def test_off_builds_nothing(self):
        self.assertEqual(CHOICES, ('off', 'synthetic', 'hermes'))
        before = tables(self.root / 'desk.sqlite')
        hub, halt = self.start('off')
        self.assertIsNone(hub)
        self.assertTrue(halt())
        self.assertEqual(tables(self.root / 'desk.sqlite'), before)
        self.assertNotIn('local-brain', [w['id'] for w in self.jobs.workers(self.owner)])

    def test_unknown_choice_is_refused_before_anything_is_built(self):
        before = tables(self.root / 'desk.sqlite')
        for choice in ('claude', 'HERMES', '', None, 'SYNTHETIC'):
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
        self.run_synthetic_task()

    def test_a_worker_cannot_lease_a_task_before_it_is_bound_to_its_mandate(self):
        # Regression: the job used to commit before its brain task and mandate link, so the
        # worker could lease it in between, find no mandate, and the task ended stopped.
        seen, submit = [], self.jobs.submit

        def slow_submit(bearer, request, **options):
            job = submit(bearer, request, **options)
            with closing(sqlite3.connect(self.root / 'desk.sqlite')) as db:
                seen.append([db.execute(f'SELECT count(*) FROM {table} WHERE job_id=?', (job['id'],)).fetchone()[0]
                             for table in ('brain_tasks', 'hub_tasks')])
            time.sleep(0.3)  # The worker polls every 20 ms, so it leases here if it can.
            return job
        self.jobs.submit = slow_submit
        self.run_synthetic_task()
        self.assertEqual(seen, [[1, 1]])

    def run_synthetic_task(self):
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


# Assembled at run time, so the public hygiene check never sees a credential-shaped literal.
KEY = 'sk' + '-ant-' + 'stand' + 'in' + '9876543210abcdefghij'
HERMES_MODEL = 'claude-opus-5-5'
QUOTE = 'The harbour survey is due on Thursday.'


class Key(KeySource):
    def read(self):
        return KEY


class Connection:
    """Stands in for the TLS connection to the provider: records what was sent, answers once."""

    def __init__(self, body):
        self.body, self.sent = body, []

    def __call__(self, timeout):
        return self

    def request(self, method, path, body, headers):
        self.sent.append((method, path, json.loads(body), dict(headers)))

    def getresponse(self):
        return self

    status = 200

    def read(self, limit):
        return self.body[:limit]

    def getheader(self, name, default=None):
        return 'text/event-stream' if name == 'content-type' else default

    def close(self):
        pass


def reply(**changes):
    body = {'answer': f'{QUOTE} [E1]', 'citations': [{'ref': 'E1', 'quote': QUOTE}], 'drafts': [], 'remember': []}
    body.update(changes)
    return json.dumps(body)


class HermesHostTests(Fixture):
    """``--hub hermes`` in process, with the box and the provider's connection stood in."""

    def setup_(self, areas=('personal',), **record):
        digest = hashlib.sha256(hb.PIN_FILE.read_bytes()).hexdigest()
        self.labels = {hb.PIN_LABEL: digest}
        return HermesSetup(record={'image': 'sha256:' + 'e' * 64, 'pin_sha256': digest, **record},
                           model=HERMES_MODEL, price=2, key_source=Key(), cloud_areas=frozenset(areas))

    def start_hermes(self, setup, box=None, connection=None):
        def make(s):
            return hermes_brain(s, inspect=lambda image, docker: self.labels, launch=box, connect=connection)
        hub, halt = start_goal_hub(self.store, self.jobs, self.owner, 'hermes', hermes=setup, make_hermes=make,
                                   poll_seconds=0.02)
        self.addCleanup(halt)
        hub.set_budget(self.owner, 'overall', None, {'version': 0, 'budget': budget({'tasks': 10})})
        return hub

    def mandate(self, hub, scope_class, brains=('hermes',)):
        goal = ExecutiveRecords(self.store).create(self.owner, {
            'request_id': f'goal-{scope_class}-{brains[0]}', 'kind': 'goal', 'title': 'Finish the harbour survey', 'detail': '',
            'project': None, 'due': None, 'rank': None, 'support': None})
        return hub.create_mandate(self.owner, {
            'request_id': f'mandate-{scope_class}-{brains[0]}', 'goal': goal['id'], 'scope_class': scope_class,
            'deadline': self.store.now() + 20 * DAY, 'success_test': 'The surveyor signs off.',
            'autonomy': {'research': 1}, 'brains': list(brains), 'assigned_brain': brains[0], 'tools': [],
            'budget': budget({'tasks': 5}), 'schedule': None})

    def test_hermes_needs_its_setup_and_nothing_else_takes_one(self):
        before = tables(self.root / 'desk.sqlite')
        for choice, setup, code in (('hermes', None, 'hermes_setup_missing'),
                                    ('synthetic', self.setup_(), 'hermes_setup_unused')):
            with self.assertRaises(Fault) as caught:
                start_goal_hub(self.store, self.jobs, self.owner, choice, hermes=setup)
            self.assertEqual(caught.exception.code, code)
        for areas in ({'personal', 'everyone'}, ['personal']):
            with self.assertRaises(Fault) as caught:
                HermesSetup(record={}, model=HERMES_MODEL, price=2, key_source=Key(), cloud_areas=areas)
            self.assertEqual(caught.exception.code, 'invalid_cloud_scopes')
        self.assertEqual(tables(self.root / 'desk.sqlite'), before)

    def test_an_image_not_built_from_these_pins_stops_the_start_before_anything_is_built(self):
        before = tables(self.root / 'desk.sqlite')
        setup = self.setup_()
        for labels in ({}, {hb.PIN_LABEL: '0' * 64}):
            with self.assertRaises(Fault) as caught:
                start_goal_hub(self.store, self.jobs, self.owner, 'hermes', hermes=setup,
                               make_hermes=lambda s: hermes_brain(s, inspect=lambda image, docker: labels))
            self.assertEqual(caught.exception.code, 'hermes_image_not_pinned')
        with self.assertRaises(Fault) as caught:
            start_goal_hub(self.store, self.jobs, self.owner, 'hermes', hermes=self.setup_(pin_sha256='1' * 64))
        self.assertEqual(caught.exception.code, 'hermes_record_not_this_pin')
        self.assertEqual(tables(self.root / 'desk.sqlite'), before)
        self.assertNotIn('local-brain', [w['id'] for w in self.jobs.workers(self.owner)])

    def test_hermes_is_registered_on_the_cloud_for_the_owners_areas_only(self):
        hub = self.start_hermes(self.setup_())
        specs = {s.id: s for s in hub.registry.specs()}
        self.assertEqual(sorted(specs), ['hermes', 'synthetic'])
        self.assertEqual((specs['hermes'].locality, specs['hermes'].tools, specs['hermes'].max_autonomy,
                          specs['hermes'].pence_per_1k_tokens), ('cloud', frozenset({'file.read'}), 1, 2))
        self.assertEqual((hub.policy.cloud_scopes, hub.policy.permitted_tools), (frozenset({'personal'}), frozenset()))
        self.assertEqual(hub.registry.get('hermes').model, HERMES_MODEL)
        workers = {w['id']: w for w in self.jobs.workers(self.owner)}
        self.assertEqual(workers['local-brain']['capabilities'], ['brain_task'])
        for scope_class in ('company', 'client'):
            with self.assertRaises(Fault) as caught:
                self.mandate(hub, scope_class)
            self.assertEqual(caught.exception.code, 'cloud_brain_refused_for_scope')
        self.mandate(hub, 'company', brains=('synthetic',))  # The local test brain still serves every area.

    def test_with_no_area_named_hermes_serves_none(self):
        hub = self.start_hermes(self.setup_(areas=()))
        with self.assertRaises(Fault) as caught:
            self.mandate(hub, 'personal')
        self.assertEqual(caught.exception.code, 'cloud_brain_refused_for_scope')

    def test_a_personal_task_goes_through_the_relay_to_claude_and_comes_back_accepted(self):
        events = sse(reply(), input_tokens=900, output_tokens=60)
        connection = Connection(events)
        frame = {'type': 'model_request', 'id': 1, 'method': 'POST', 'path': '/v1/messages',
                 'betas': 'interleaved-thinking-2025-05-14,fine-grained-tool-streaming-2025-05-14',
                 'body': json.dumps({'model': HERMES_MODEL, 'max_tokens': 128000, 'stream': True,
                                     'messages': [{'role': 'user', 'content': 'Summarise the plan.'}]})}
        box = StandInBox([('model', frame), ('final', reply())])
        hub = self.start_hermes(self.setup_(), box=box, connection=connection)
        mandate = self.mandate(hub, 'personal')
        task = hub.submit_task(self.owner, mandate['id'], {
            'request_id': 'task-1', 'brain': None, 'work': 'research', 'instruction': 'Summarise the plan.',
            'context': [{'note': self.note['id'], 'start_line': 2, 'end_line': 2}], 'learned': [], 'tools': [],
            'budget': {'wall_seconds': 30, 'tokens': 20000, 'money_pence': 100, 'steps': 20}, 'autonomy': 1})
        job = task['job']['id']
        deadline = time.monotonic() + 20
        while not self.jobs.view(self.owner, job)['finished']:
            self.assertLess(time.monotonic(), deadline, 'the host brain worker did not run the task')
            time.sleep(0.02)
        self.sup.goals = hub
        self.sup.cycle()
        with self.store.connection() as db:
            row = db.execute('SELECT result, brain FROM hub_tasks WHERE job_id=?', (job,)).fetchone()
        self.assertEqual((row['result'], row['brain']), ('accepted', 'hermes'))
        # One call, to the one path, with the key read for it and no beta header.
        [(method, path, sent, headers)] = connection.sent
        self.assertEqual((method, path, sent['model'], headers['x-api-key']), ('POST', '/v1/messages', HERMES_MODEL, KEY))
        self.assertNotIn('anthropic-beta', headers)
        self.assertLessEqual(sent['max_tokens'], hb.MAX_OUTPUT_TOKENS)
        # The key went nowhere near the box, and the box was removed.
        self.assertTrue(box.stopped)
        self.assertNotIn(KEY, json.dumps(box.received))
        self.assertNotIn(KEY, json.dumps(task))


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

    def desk(self, *arguments):
        return subprocess.run([sys.executable, '-m', 'alfred.desk', *arguments, '--data-dir', str(self.home)],
                              cwd=REPOSITORY, capture_output=True, text=True, timeout=30)

    def key_file(self, mode=0o600):
        path = self.home.parent / 'claude-key'
        path.write_text(KEY + '\n')
        path.chmod(mode)
        return path

    def test_hermes_on_the_command_line_needs_every_setting_and_a_matching_image(self):
        record = self.home.parent / 'box-record.json'
        record.write_text(json.dumps({'image': 'sha256:' + 'e' * 64, 'pin_sha256': '0' * 64}))
        key = self.key_file()
        settings = ['--hermes-record', str(record), '--hermes-model', HERMES_MODEL, '--hermes-price', '2']
        source = ['--claude-key', 'file', '--claude-key-file', str(key)]
        for extra, code in (([], 'hermes_settings_required'), (settings, 'claude_key_source_required'),
                            (settings[:4] + source, 'hermes_settings_required'),
                            (settings + ['--claude-key', 'file'], 'claude_key_source_unclear'),
                            (settings + source, 'hermes_record_not_this_pin')):
            run = self.desk('serve', '--port', str(free_port()), '--hub', 'hermes', '--cloud-area', 'personal', *extra)
            self.assertEqual((run.returncode, run.stdout.strip()), (1, f'Cannot start: {code}'), extra)
            self.assertNotIn(KEY, run.stdout + run.stderr)
        self.assertFalse((self.home / 'desk.lock').exists(), 'the host took its lock before its settings were read')

    def test_the_key_check_says_where_and_how_long_and_never_shows_the_key(self):
        key = self.key_file()
        run = self.desk('claude-key-check', '--claude-key', 'file', '--claude-key-file', str(key))
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), f'Claude key found in file {key}: {len(KEY)} characters, in the expected shape.')
        key.chmod(0o644)
        run = self.desk('claude-key-check', '--claude-key', 'file', '--claude-key-file', str(key))
        self.assertEqual(run.stdout.strip(), f'No Claude key could be read from file {key} (secret_file_too_open).')
        run = self.desk('claude-key-check')
        self.assertEqual((run.returncode, run.stdout.strip()), (1, 'Cannot start: claude_key_source_required'))
        for out in (run.stdout, run.stderr):
            self.assertNotIn(KEY, out)


if __name__ == '__main__':
    unittest.main()
