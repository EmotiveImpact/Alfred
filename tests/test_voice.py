"""VOI-001 playback records over real HTTP: generated, played and acknowledged stay distinct.

No audio, microphone or spoken text reaches the server; only a hash and a length.
"""
from pathlib import Path
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer
from alfred.conversation import ConversationService


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        home = Path(self.tmp.name) / 'demo'; self.keys = init_demo(home)
        self.store = KnowledgeStore(home / 'desk.sqlite')
        sup = KnowledgeSupervisor(self.store, self.keys['owner'], self.keys['source'], home / 'project', vault=home / 'vault'); sup.cycle()
        # The answer exists before the server starts, so the server's own worker cannot race for it.
        service = ConversationService(self.store, None, 'demo-production')
        session = service.create(self.keys['owner'], {'title': 'Voice'})['id']
        service.submit(self.keys['owner'], session, {'question': 'What still needs confirming?', 'mode': 'sources', 'follow_up': False,
                                                     'request_id': 'q1', 'after': 0})
        service.process_one()
        self.turn = service.view(self.keys['owner'], session)['turns'][0]['id']
        service.stop()
        self.server = DeskHTTPServer(self.store, sup, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), self.thread.join(3)))
        self.sessions = {}

    def req(self, role, path, data=None, csrf=True):
        cookie, token = self.sessions.get(role, (None, None))
        headers = {'Cookie': cookie} if cookie else {}
        if data is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': self.server.origin})
            if csrf and token: headers['X-CSRF-Token'] = token
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); body = json.loads(r.read()); cookie = r.getheader('Set-Cookie'); c.close()
        return r.status, body, cookie

    def login(self, role):
        code, data, cookie = self.req(role, '/desk/login', {'key': self.keys[role]})
        self.assertEqual(code, 200); self.sessions[role] = (cookie.split(';')[0], data['csrf'])

    def generated(self, role='owner', **over):
        body = {'turn_id': self.turn, 'text_sha256': hashlib.sha256(b'spoken').hexdigest(), 'characters': 6, 'voice_local': True} | over
        return self.req(role, '/desk/voice/playbacks', body)

    def test_generated_played_and_acknowledged_are_separate_states(self):
        self.login('owner')
        code, made, _ = self.generated()
        self.assertEqual((code, made['state']), (200, 'generated'))
        playback = made['id']
        # Hearing cannot be acknowledged before the browser reports that playback ended.
        self.assertEqual(self.req('owner', f'/desk/voice/playbacks/{playback}/acknowledge', {})[1], {'error': 'playback_not_finished'})
        self.assertEqual(self.req('owner', f'/desk/voice/playbacks/{playback}/report', {'outcome': 'ended'})[1]['state'], 'played')
        self.assertEqual(self.req('owner', f'/desk/voice/playbacks/{playback}/report', {'outcome': 'ended'})[0], 409)
        done = self.req('owner', f'/desk/voice/playbacks/{playback}/acknowledge', {})[1]
        self.assertEqual(done['state'], 'acknowledged')
        self.assertEqual(done['basis'], {'played': 'browser_report_not_proof_of_hearing', 'acknowledged': 'explicit_human_action'})
        history = self.req('owner', f'/desk/voice/playbacks/turn/{self.turn}')[1]
        self.assertEqual(([p['state'] for p in history['playbacks']], history['microphone']), (['acknowledged'], 'never_requested'))

    def test_a_stopped_playback_is_never_called_played(self):
        self.login('owner')
        playback = self.generated()[1]['id']
        self.assertEqual(self.req('owner', f'/desk/voice/playbacks/{playback}/report', {'outcome': 'stopped'})[1]['state'], 'stopped')
        self.assertEqual(self.req('owner', f'/desk/voice/playbacks/{playback}/acknowledge', {})[0], 409)

    def test_network_voices_other_people_and_bad_input_are_refused(self):
        self.login('owner'); self.login('reader')
        self.assertEqual(self.generated(voice_local=False)[1], {'error': 'network_voice_refused'})
        self.assertEqual(self.generated(text_sha256='x')[0], 400)
        self.assertEqual(self.generated(characters=0)[0], 400)
        self.assertEqual(self.generated(turn_id='turn-unknown')[0], 404)
        self.assertEqual(self.generated(role='reader')[0], 404)  # Another person's answer looks unknown.
        playback = self.generated()[1]['id']
        self.assertEqual(self.req('reader', f'/desk/voice/playbacks/{playback}/report', {'outcome': 'ended'})[0], 404)
        self.assertEqual(self.req('owner', f'/desk/voice/playbacks/{playback}/report', {'outcome': 'ended'}, csrf=False)[0], 403)
        self.assertEqual(self.req('owner', f'/desk/voice/playbacks/{playback}/report', {'outcome': 'heard'})[0], 400)
        with self.store.connection() as db:
            self.assertNotIn('spoken', str([tuple(r) for r in db.execute('SELECT * FROM voice_playbacks')]))


if __name__ == '__main__':
    unittest.main()
