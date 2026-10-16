"""Host restart and recovery (RUN-001, M09), synthetic data only.

Covers the clean-stop marker, reconciliation of interrupted questions, jobs and
routine slots at start, the read-only doctor, service-file text that is never
installed, and a real host process killed mid-job and restarted.
"""
from __future__ import annotations
import http.client
import json
import os
from pathlib import Path
import plistlib
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from alfred import recovery
from alfred.conversation import ConversationService
from alfred.desk import init_demo, recovery_line
from alfred.desk_http import DeskHTTPServer
from alfred.jobs import JobCoordinator
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.local import Fault
from alfred import routines

REPOSITORY = Path(__file__).resolve().parents[1]
QUESTION = {'question': 'collection', 'mode': 'sources', 'follow_up': False, 'request_id': 'r1', 'after': 0}


def wait_job(seconds=60, key='synthetic-wait'):
    return {'idempotency_key': key, 'kind': 'wait', 'parameters': {'seconds': seconds}, 'inputs': [],
            'side_effect_free': True}


class MarkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def test_first_unclean_and_clean_stops_are_told_apart(self):
        first = recovery.begin(self.home, clock=lambda: 100)
        self.assertEqual((first['previous_stop'], first['last_clean_stop']), ('first_start', None))
        self.assertEqual(stat.S_IMODE(os.stat(self.home / recovery.STATE_FILE).st_mode), 0o600)
        # No clean stop recorded: the next start reports an unclean stop.
        second = recovery.begin(self.home, clock=lambda: 200)
        self.assertEqual((second['previous_stop'], second['previous_started_at']), ('unclean', 100))
        self.assertFalse(recovery.mark_clean_stop(self.home, first['run'], clock=lambda: 250), 'an old run never marks a newer one')
        self.assertTrue(recovery.mark_clean_stop(self.home, second['run'], clock=lambda: 300))
        third = recovery.begin(self.home, clock=lambda: 400)
        self.assertEqual((third['previous_stop'], third['previous_stopped_at'], third['last_clean_stop']), ('clean', 300, 300))
        fourth = recovery.begin(self.home, clock=lambda: 500)
        self.assertEqual((fourth['previous_stop'], fourth['last_clean_stop']), ('unclean', 300), 'the last clean stop is kept')

    def test_unreadable_marker_is_reported_not_trusted(self):
        (self.home / recovery.STATE_FILE).write_text('{"version": 1, "clean_stop": tru')
        self.assertEqual(recovery.begin(self.home)['previous_stop'], 'unknown')
        (self.home / recovery.STATE_FILE).unlink()
        (self.home / recovery.STATE_FILE).symlink_to(self.home / 'elsewhere.json')
        (self.home / 'elsewhere.json').write_text(json.dumps({'version': 1, 'clean_stop': True}))
        self.assertEqual(recovery.read_state(self.home), {'unreadable': True})


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'demo'; self.keys = init_demo(self.home)
        self.owner = self.keys['owner']
        self.store = KnowledgeStore(self.home / 'desk.sqlite')
        self.jobs = JobCoordinator(self.store)
        self.jobs.enrol_worker(self.owner, 'local-host', 'This computer', ['wait'])
        self.jobs.enrol_worker(self.owner, 'other-host', 'Another enrolled worker', ['wait'])

    def leave_interrupted_work(self):
        """What a killed host leaves behind: a started job, an unstarted lease, a queued job and question."""
        running = self.jobs.submit(self.owner, wait_job(key='running'))['id']
        grant = self.jobs.lease(self.owner, 'local-host', ttl=600)
        self.jobs.start(self.owner, 'local-host', grant['job'], grant['lease'], backend='local_subprocess')
        leased = self.jobs.submit(self.owner, wait_job(key='leased'))['id']
        self.assertEqual(self.jobs.lease(self.owner, 'local-host', ttl=600)['job'], leased)
        elsewhere = self.jobs.submit(self.owner, wait_job(key='elsewhere'))['id']
        other = self.jobs.lease(self.owner, 'other-host', ttl=600)
        self.jobs.start(self.owner, 'other-host', other['job'], other['lease'], backend='local_subprocess')
        queued = self.jobs.submit(self.owner, wait_job(key='queued'))['id']
        conversations = ConversationService(self.store)
        sid = conversations.create(self.owner, {'title': 'Synthetic question'})['id']
        conversations.submit(self.owner, sid, QUESTION)
        return {'running': running, 'leased': leased, 'elsewhere': elsewhere, 'queued': queued, 'session': sid,
                'conversations': conversations}

    def state(self, job):
        view = self.jobs.view(self.owner, job)
        return view['state'], view['reason']

    def test_restart_marks_honest_states_and_never_reruns(self):
        work = self.leave_interrupted_work()
        start = recovery.begin(self.home)
        self.assertEqual(start['previous_stop'], 'first_start')
        report = recovery.reconcile(self.store, self.owner, start)
        self.assertEqual(self.state(work['running']), ('effect_unknown', 'host_stopped_while_running'))
        self.assertTrue(self.jobs.view(self.owner, work['running'])['needs_reconciliation'])
        self.assertEqual(self.state(work['leased']), ('queued', 'host_restarted_before_start'))
        self.assertEqual(self.state(work['elsewhere'])[0], 'running', "another worker's lease is left to its own expiry")
        self.assertEqual(self.state(work['queued']), ('queued', None))
        events = self.jobs.events(self.owner, work['running'])['events']
        self.assertEqual(events[-1]['kind'], 'host_restart_reconciled')
        self.assertEqual((report['jobs_effect_unknown'], report['jobs_requeued'], report['questions_interrupted']),
                         ([work['running']], [work['leased']], 1))
        turn = work['conversations'].view(self.owner, work['session'])['turns'][0]
        self.assertEqual((turn['state'], turn['reason'], turn['result']), ('interrupted', 'host_stopped_before_answer', None))
        # Reconciling twice changes nothing more; only the owner's finding settles the job.
        again = recovery.reconcile(self.store, self.owner, start)
        self.assertEqual((again['jobs_effect_unknown'], again['questions_interrupted']), ([], 0))
        self.assertEqual(self.jobs.reconcile(self.owner, work['running'], 'effect_did_not_happen')['state'], 'reconciled')
        self.assertIn('Interrupted questions: 1.', recovery_line(report))
        self.assertIn('effect unknown): 1.', recovery_line(report))

    def test_reader_cannot_reconcile(self):
        with self.assertRaises(Fault):
            recovery.reconcile(self.store, self.keys['reader'], recovery.begin(self.home))

    def test_missed_routine_slots_are_counted_not_run(self):
        with self.store.connection() as db:
            db.executescript('BEGIN IMMEDIATE;\n' + routines.SCHEMA + '\nCOMMIT;')
        scope = self.store.principal(self.owner, {'owner'})['scope']
        body = {'version': 0, 'enabled': True, 'schedule': {'every_hours': 4}, 'utc_offset_minutes': 0, 'runs_per_day': 6,
                'nominations_per_run': 3, 'quiet_hours': None, 'interrupt': 'show_now', 'propose_drafts': False}
        settings = routines.validate('commitment-review', body)
        now = self.store.now()
        first = routines.next_slot(settings, now - 13 * 3600)  # three or four slots fell while stopped
        expected, moment = 0, first
        while moment <= now:
            expected, moment = expected + 1, routines.next_slot(settings, moment)
        with self.store.transaction() as db:
            db.execute('INSERT INTO routine_settings VALUES (?,?,?,?,?,?,?,?,?)',
                       (scope, 'commitment-review', self.store.principal(self.owner, {'owner'})['id'], 1, 0,
                        json.dumps(settings), 1, first, now))
        report = recovery.reconcile(self.store, self.owner, recovery.begin(self.home))
        self.assertGreaterEqual(expected, 3)
        self.assertEqual(report['routine_slots_due_while_stopped'], {'commitment-review': expected})
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM routine_runs').fetchone()[0], 0, 'counting runs nothing')
            self.assertEqual(db.execute('SELECT next_due FROM routine_settings').fetchone()[0], first, 'the routine records its own missed slots')

    def test_health_reports_recovery_counts(self):
        self.leave_interrupted_work()
        report = recovery.reconcile(self.store, self.owner, recovery.begin(self.home))
        sup = KnowledgeSupervisor(self.store, self.owner, self.keys['source'], self.home / 'project', vault=self.home / 'vault')
        server = DeskHTTPServer(self.store, sup, port=0, jobs=self.jobs)
        self.addCleanup(server.server_close)
        from alfred import console_api
        self.assertIsNone(console_api.health(server, self.owner)['recovery'])
        server.recovery = report
        for key in (self.owner, self.keys['reader']):
            value = console_api.health(server, key)['recovery']
            self.assertEqual((value['previousStop'], value['questionsInterrupted'], value['jobsEffectUnknown'],
                              value['jobsRequeued'], value['routineSlotsMissed'], value['lastCleanStop']),
                             ('first_start', 1, 1, 1, 0, None))


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.home = self.root / 'demo'; init_demo(self.home)

    def checks(self, **kwargs):
        before = sorted(p.name for p in self.home.iterdir())
        results = recovery.doctor(self.home, **kwargs)
        self.assertEqual(sorted(p.name for p in self.home.iterdir()), before, 'doctor creates nothing')
        return {r['check']: r for r in results}

    def test_fresh_workspace_has_no_failures(self):
        dist = self.root / 'dist'; dist.mkdir(); (dist / 'index.html').write_text('<!doctype html>')
        results = self.checks(console_dist=dist)
        self.assertEqual({k: v['status'] for k, v in results.items()},
                         {'placement': 'ok', 'permissions': 'ok', 'database': 'ok', 'wal': 'ok', 'backup': 'warn',
                          'last_stop': 'ok', 'console_build': 'ok'})
        self.assertEqual(self.checks(console_dist=self.root / 'missing')['console_build']['status'], 'warn')

    def test_old_backup_is_warned(self):
        store = KnowledgeStore(self.home / 'desk.sqlite')
        with store.transaction() as db:
            db.execute('INSERT INTO lifecycle_backups VALUES (?,?,?,?,?)',
                       ('b1', int(time.time()) - 30 * 86400, str(self.root / 'gone.sqlite'), '0' * 64, 0))
        del store
        results = self.checks()
        self.assertEqual(results['backup']['status'], 'warn')
        self.assertIn('30 days old and its file is no longer where it was written', results['backup']['detail'])

    def test_unclean_stop_and_leftover_wal_are_warned_without_opening(self):
        recovery.begin(self.home)  # a start with no clean stop
        (self.home / 'desk.sqlite-wal').write_bytes(b'\0' * 32)
        os.chmod(self.home / 'desk.sqlite-wal', 0o600)
        results = self.checks()
        self.assertEqual(results['last_stop']['status'], 'warn')
        self.assertIn('did not stop cleanly', results['last_stop']['detail'])
        self.assertEqual((results['wal']['status'], results['database']['status']), ('warn', 'warn'))
        self.assertIn('32-byte write-ahead log remains', results['wal']['detail'])
        self.assertFalse((self.home / 'desk.sqlite-shm').exists(), 'doctor did not open the database')

    def test_permissions_and_placement_failures(self):
        os.chmod(self.home / 'desk-access.json', 0o644)
        self.assertEqual(self.checks()['permissions']['status'], 'fail')
        os.chmod(self.home / 'desk-access.json', 0o600)
        (self.root / '.git').mkdir()
        results = self.checks()
        self.assertEqual(results['placement']['status'], 'fail')
        self.assertIn('Git working tree', results['placement']['detail'])

    def test_missing_directory_is_not_created(self):
        missing = self.root / 'not-yet'
        results = {r['check']: r['status'] for r in recovery.doctor(missing)}
        self.assertEqual(results['data_directory'], 'fail')
        self.assertFalse(missing.exists())

    def test_cli_doctor_json_and_exit_code(self):
        run = subprocess.run([sys.executable, '-m', 'alfred.desk', 'doctor', '--json', '--data-dir', str(self.home)],
                             cwd=REPOSITORY, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        value = json.loads(run.stdout)
        self.assertFalse(value['changes_made'])
        self.assertIn('wal', {c['check'] for c in value['checks']})
        missing = subprocess.run([sys.executable, '-m', 'alfred.desk', 'doctor', '--data-dir', str(self.root / 'none')],
                                 cwd=REPOSITORY, capture_output=True, text=True, timeout=60)
        self.assertEqual(missing.returncode, 1)
        self.assertIn('Doctor only reads', missing.stdout)
        self.assertFalse((self.root / 'none').exists())


class ServiceFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / 'data dir with 100% "quotes"'

    def test_systemd_unit_quotes_arguments(self):
        arguments = recovery.serve_arguments(self.data, 8899, vault=self.root / 'vault', python='/usr/bin/python3')
        text = recovery.service_text('systemd', arguments, self.data)
        line = next(l for l in text.splitlines() if l.startswith('ExecStart='))
        self.assertIn('"' + str(self.data).replace('%', '%%').replace('"', '\\"') + '"', line)
        self.assertIn('--port 8899', line)
        self.assertIn('has not installed this file', text)
        self.assertNotIn('0.0.0.0', text)
        for word in ('[Unit]', '[Service]', '[Install]', 'Restart=on-failure', 'UMask=0077'):
            self.assertIn(word, text)

    def test_launchd_plist_parses_and_does_not_start_at_login(self):
        arguments = recovery.serve_arguments(self.data, 8765, python='/usr/bin/python3')
        text = recovery.service_text('launchd', arguments, self.data)
        value = plistlib.loads(text.encode())
        self.assertEqual(value['ProgramArguments'], arguments)
        self.assertEqual((value['Label'], value['RunAtLoad']), ('local.alfred.desk', False))
        self.assertIn('has not installed this file', text)

    def test_control_characters_and_bad_ports_are_refused(self):
        with self.assertRaises(Fault):
            recovery.serve_arguments(self.root / 'bad\nname', 8765)
        with self.assertRaises(Fault):
            recovery.serve_arguments(self.data, 80)

    def test_writing_never_installs(self):
        text = 'synthetic'
        for target in (self.root / 'Library' / 'LaunchAgents' / 'local.alfred.desk.plist',
                       self.root / '.config' / 'systemd' / 'user' / 'alfred-desk.service'):
            target.parent.mkdir(parents=True)
            with self.assertRaises(Fault) as refused:
                recovery.write_service_file(text, target)
            self.assertEqual(refused.exception.code, 'service_file_output_would_install')
            self.assertFalse(target.exists())
        written = recovery.write_service_file(text, self.root / 'alfred-desk.service')
        self.assertEqual((written.read_text(), stat.S_IMODE(written.stat().st_mode)), (text, 0o600))
        with self.assertRaises(FileExistsError):
            recovery.write_service_file('other', written)

    def test_cli_prints_without_creating_the_data_directory(self):
        run = subprocess.run([sys.executable, '-m', 'alfred.desk', 'service-file', '--service', 'systemd',
                              '--data-dir', str(self.root / 'later')], cwd=REPOSITORY, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('ExecStart=', run.stdout)
        self.assertFalse((self.root / 'later').exists())
        out = self.root / 'unit.service'
        run = subprocess.run([sys.executable, '-m', 'alfred.desk', 'service-file', '--service', 'launchd', '--output', str(out),
                              '--data-dir', str(self.root / 'later')], cwd=REPOSITORY, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('has not installed, loaded, enabled or started it', run.stdout)
        self.assertEqual(plistlib.loads(out.read_bytes())['Label'], 'local.alfred.desk')


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class RealHostKillTests(unittest.TestCase):
    """A real `serve` process killed with SIGKILL mid-job, then restarted; then stopped with SIGTERM."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'demo'; self.keys = init_demo(self.home)
        self.port = free_port()
        self.process = None
        self.addCleanup(self.stop_quietly)

    def start(self):
        env = dict(os.environ, PYTHONUNBUFFERED='1')
        self.process = subprocess.Popen([sys.executable, '-m', 'alfred.desk', 'serve', '--data-dir', str(self.home),
                                         '--port', str(self.port)], cwd=REPOSITORY, env=env, stdout=subprocess.PIPE,
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

    def stop_quietly(self):
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(10)
        if self.process:
            self.process.stdout.close()

    def wait_for(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.1)
        self.fail('condition not reached')

    def health(self):
        origin = f'http://127.0.0.1:{self.port}'
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        c.request('POST', '/desk/login', json.dumps({'key': self.keys['owner']}), {'Content-Type': 'application/json', 'Origin': origin})
        r = c.getresponse(); r.read(); cookie = r.getheader('Set-Cookie').split(';')[0]; c.close()
        self.assertEqual(r.status, 200)
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        c.request('GET', '/desk/console/health', headers={'Cookie': cookie})
        r = c.getresponse(); body = json.loads(r.read()); c.close()
        self.assertEqual(r.status, 200, body)
        return body

    def test_kill_mid_job_and_mid_question_then_restart(self):
        output = self.start()
        self.assertIn('First start of this data directory.', output)
        store = KnowledgeStore(self.home / 'desk.sqlite')
        jobs = JobCoordinator(store)
        job = jobs.submit(self.keys['owner'], wait_job(seconds=120))['id']
        self.wait_for(lambda: jobs.view(self.keys["owner"], job)['state'] == 'running')
        # A question still waiting when the host dies (left as the queued row a live queue holds).
        conversations = ConversationService(store)
        sid = conversations.create(self.keys['owner'], {'title': 'Synthetic question'})['id']
        conversations.submit(self.keys['owner'], sid, QUESTION)
        os.killpg(self.process.pid, signal.SIGKILL)  # The host and its job subprocess die without cleanup.
        self.process.wait(10); self.process.stdout.close()
        self.assertFalse(recovery.read_state(self.home)['clean_stop'])

        output = self.start()
        self.assertIn('The previous run did not stop cleanly.', output)
        self.assertIn('Interrupted questions: 1.', output)
        self.assertIn('Jobs needing reconciliation (effect unknown): 1.', output)
        view = jobs.view(self.keys["owner"], job)
        self.assertEqual((view['state'], view['reason']), ('effect_unknown', 'host_stopped_while_running'))
        time.sleep(1.5)  # Several worker cycles: the job is not re-run.
        self.assertEqual(jobs.view(self.keys["owner"], job)['state'], 'effect_unknown')
        turn = conversations.view(self.keys['owner'], sid)['turns'][0]
        self.assertEqual((turn['state'], turn['reason']), ('interrupted', 'host_stopped_before_answer'))
        value = self.health()['recovery']
        self.assertEqual((value['previousStop'], value['questionsInterrupted'], value['jobsEffectUnknown']), ('unclean', 1, 1))
        self.assertEqual(self.health()['jobs']['byState'].get('effect_unknown'), 1)

        # A service manager's SIGTERM is a clean stop, and the next start says so.
        self.process.send_signal(signal.SIGTERM)
        self.assertEqual(self.process.wait(30), 0)
        self.process.stdout.close()
        state = recovery.read_state(self.home)
        self.assertTrue(state['clean_stop'])
        self.assertEqual(state['last_recovery']['jobs_effect_unknown'], [job])
        output = self.start()
        self.assertIn('The previous run stopped cleanly.', output)
        self.assertIn('Interrupted questions: 0.', output)
        self.assertIsNotNone(self.health()['recovery']['lastCleanStop'])
        doctor = {r['check']: r['status'] for r in recovery.doctor(self.home)}
        self.assertEqual((doctor['last_stop'], doctor['wal']), ('ok', 'ok'))


if __name__ == '__main__':
    unittest.main()
