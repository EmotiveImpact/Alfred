"""Real HTTP acceptance for the stage 0 job coordinator on the local host.

The host runs one local-subprocess worker thread. A client submits a job, signs
out (the interface disconnects), and a new session later resumes from its event
cursor to read the reconciled outcome. Local subprocess only: not a sandbox.
"""
from pathlib import Path
import http.client
import json
import tempfile
import threading
import time
import unittest
from alfred.desk import init_demo, start_local_jobs
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer


class JobsHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        home = Path(self.tmp.name) / 'demo'; self.keys = init_demo(home, legacy_scope=True)
        self.store = KnowledgeStore(home / 'desk.sqlite')
        sup = KnowledgeSupervisor(self.store, self.keys['owner'], self.keys['source'], home / 'project', vault=home / 'vault'); sup.cycle()
        self.jobs, halt = start_local_jobs(self.store, self.keys['owner'], home)
        self.addCleanup(halt)
        self.server = DeskHTTPServer(self.store, sup, port=0, jobs=self.jobs)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), self.thread.join(3)))
        self.cookie = self.csrf = None

    def req(self, path, data=None, csrf=True):
        headers = {'Cookie': self.cookie} if self.cookie else {}
        if data is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': self.server.origin})
            if csrf and self.csrf: headers['X-CSRF-Token'] = self.csrf
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        c.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); body = json.loads(r.read()); cookie = r.getheader('Set-Cookie'); c.close()
        return r.status, body, cookie

    def login(self, role='owner'):
        code, data, cookie = self.req('/desk/login', {'key': self.keys[role]}); self.assertEqual(code, 200)
        self.cookie = cookie.split(';')[0]; self.csrf = data['csrf']

    def note(self, title):
        return next(n for n in self.req('/desk/knowledge')[1]['nodes'] if n['title'] == title)

    def submit(self, key, kind='word_count', parameters=None, inputs=None):
        return self.req('/desk/jobs', {'idempotency_key': key, 'kind': kind, 'parameters': parameters or {},
                                       'inputs': inputs if inputs is not None else [{'note': self.note('Sample film')['id']}],
                                       'side_effect_free': True})

    def until(self, job, states, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            view = self.req('/desk/jobs/' + job)[1]
            if view['state'] in states:
                return view
            time.sleep(0.2)
        self.fail(f'job did not reach {states}')

    def test_job_continues_after_the_interface_disconnects(self):
        self.login()
        code, job, _ = self.submit('k1')
        self.assertEqual((code, job['state']), (200, 'queued'))
        first = self.req(f"/desk/jobs/{job['id']}/events?after=0")[1]
        cursor = first['next_cursor']
        # The interface goes away: sign out, so this browser session no longer exists.
        self.assertEqual(self.req('/desk/logout', {})[0], 200)
        self.assertEqual(self.req('/desk/jobs/' + job['id'])[0], 401)
        time.sleep(1.5)
        self.login()
        done = self.until(job['id'], {'succeeded'})
        resumed = self.req(f"/desk/jobs/{job['id']}/events?after={cursor}")[1]
        self.assertTrue(resumed['finished'])
        kinds = [e['kind'] for e in resumed['events']]
        self.assertIn('succeeded', kinds); self.assertNotIn('submitted', kinds)
        self.assertEqual(self.req(f"/desk/jobs/{job['id']}/events?after={resumed['next_cursor']}")[1]['events'], [])
        artefact = self.req('/desk/jobs/artefacts/' + done['result']['sha256'])[1]
        result = json.loads(artefact['text'])
        self.assertEqual(result['basis'], 'deterministic_count_not_interpretation')
        self.assertGreater(result['total']['words'], 5)
        self.assertGreaterEqual(self.jobs.cache.usage()['entries'], 1)

    def test_running_job_can_be_cancelled(self):
        self.login()
        job = self.submit('slow', kind='wait', parameters={'seconds': 30})[1]
        self.until(job['id'], {'running'})
        self.assertEqual(self.req(f"/desk/jobs/{job['id']}/cancel", {})[1]['state'], 'cancel_requested')
        self.assertEqual(self.until(job['id'], {'cancelled'}, timeout=30)['state'], 'cancelled')

    def test_refused_inputs_and_boundaries(self):
        self.login()
        self.assertEqual(self.submit('missing', inputs=[{'note': '0' * 24}])[0], 403)
        self.assertEqual(self.submit('bad-kind', kind='shell')[0], 400)
        self.assertEqual(self.req('/desk/jobs', {'idempotency_key': 'x', 'kind': 'word_count', 'parameters': {}, 'inputs': [],
                                                 'side_effect_free': True}, csrf=False)[0], 403)
        self.assertEqual(self.req('/desk/jobs?scope=other')[0], 400)
        job = self.submit('k2')[1]
        self.assertEqual(self.req(f"/desk/jobs/{job['id']}/events?after=-1")[0], 400)
        self.login('reader')
        self.assertEqual(self.submit('reader-job')[0], 403)
        self.assertEqual(self.req('/desk/jobs/' + job['id'])[1]['id'], job['id'])

    def test_strict_grants_also_govern_job_history(self):
        self.login()
        self.req('/desk/identity/enable', {'epoch': 0})
        epoch = lambda: self.req('/desk/identity')[1]['epoch']
        grant = {'source': 'demo-source', 'capability': 'read', 'days': 30}
        self.req('/desk/identity/grants', {**grant, 'epoch': epoch(), 'revoke': False})
        job = self.until(self.submit('strict')[1]['id'], {'succeeded'})
        invitation = self.req('/desk/identity/invitations', {**grant, 'days': 1, 'epoch': epoch()})[1]
        owner = (self.cookie, self.csrf)
        self.login('reader')
        self.assertEqual(self.req('/desk/jobs')[1]['jobs'], [])
        for path in (f"/desk/jobs/{job['id']}", f"/desk/jobs/{job['id']}/events?after=0", '/desk/jobs/artefacts/' + job['result']['sha256']):
            self.assertEqual(self.req(path)[0], 404, path)
        self.assertEqual(self.req('/desk/identity/invitations/redeem', {'code': invitation['code']})[0], 200)
        self.assertEqual([j['id'] for j in self.req('/desk/jobs')[1]['jobs']], [job['id']])
        self.assertEqual(self.req(f"/desk/jobs/{job['id']}/events?after=0")[0], 200)
        # The submitter keeps their own job history after losing access; the result does not.
        self.cookie, self.csrf = owner
        self.req('/desk/identity/grants', {**grant, 'epoch': epoch(), 'revoke': True})
        self.assertEqual(self.req(f"/desk/jobs/{job['id']}")[1]['state'], 'succeeded')
        self.assertEqual(self.req('/desk/jobs/artefacts/' + job['result']['sha256'])[0], 404)

    def test_idempotent_submission_over_http(self):
        self.login()
        first = self.submit('same')[1]; again = self.submit('same')[1]
        self.assertEqual(first['id'], again['id'])
        self.assertEqual(self.submit('same', kind='summarise_lines', parameters={'max_lines': 2})[0], 409)


if __name__ == '__main__':
    unittest.main()
