"""M02 workflows: owner grants, invitations for another person, offline rotation.

Real HTTP for the browser-facing parts. Synthetic workspace only.
"""
from pathlib import Path
import fcntl
import http.client
import json
import os
import stat
import tempfile
import threading
import unittest
from alfred.local import Fault
from alfred.desk import init_demo, load_keys, rotate_key
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer
from alfred.policy import IdentityPolicy


class IdentityHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'demo'; self.keys = init_demo(self.home)
        self.store = KnowledgeStore(self.home / 'desk.sqlite')
        self.sup = KnowledgeSupervisor(self.store, self.keys['owner'], self.keys['source'], self.home / 'project', vault=self.home / 'vault'); self.sup.cycle()
        self.server = DeskHTTPServer(self.store, self.sup, port=0)
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
        r = c.getresponse(); body = json.loads(r.read()); set_cookie = r.getheader('Set-Cookie'); c.close()
        return r.status, body, set_cookie

    def login(self, role):
        code, data, cookie = self.req(role, '/desk/login', {'key': self.keys[role]})
        self.assertEqual(code, 200); self.sessions[role] = (cookie.split(';')[0], data['csrf'])

    def notes(self, role):
        return self.req(role, '/desk/console/projection')[1]['counts']['notes']

    def epoch(self):
        return self.req('owner', '/desk/identity')[1]['epoch']

    def test_legacy_view_lists_sources_and_write_is_never_implied(self):
        self.login('owner')
        view = self.req('owner', '/desk/identity')[1]
        self.assertEqual(view['mode'], 'legacy_scope')
        self.assertEqual(view['sources'][0]['permitted'], {'connector.read': False, 'inbox.write': False, 'model': True, 'read': True, 'sync': False})

    def test_owner_grants_and_revokes_with_epoch_and_csrf(self):
        self.login('owner')
        self.assertEqual(self.req('owner', '/desk/identity/enable', {'epoch': 0}, csrf=False)[0], 403)
        self.assertEqual(self.req('owner', '/desk/identity/enable', {'epoch': 0})[1]['mode'], 'explicit_grants')
        self.assertEqual(self.notes('owner'), 0)
        body = {'source': 'demo-source', 'capability': 'read', 'days': 30, 'epoch': self.epoch(), 'revoke': False}
        code, view, _ = self.req('owner', '/desk/identity/grants', body)
        self.assertEqual(code, 200)
        grant = view['grants'][0]
        self.assertLessEqual(grant['expires'], next(s['credential_expires'] for s in view['sources']))
        self.assertEqual(self.notes('owner'), 20)
        self.assertEqual(self.req('owner', '/desk/identity/grants', body)[1:2][0]['error'], 'policy_changed')
        self.req('owner', '/desk/identity/grants', {**body, 'epoch': self.epoch(), 'revoke': True})
        self.assertEqual(self.notes('owner'), 0)

    def test_invitation_grants_only_the_redeeming_person(self):
        self.login('owner'); self.login('reader')
        self.req('owner', '/desk/identity/enable', {'epoch': 0})
        self.assertEqual(self.notes('reader'), 0)
        self.assertEqual(self.req('reader', '/desk/identity')[1]['sources'], [])
        code, invitation, _ = self.req('owner', '/desk/identity/invitations', {'source': 'demo-source', 'capability': 'read', 'days': 1, 'epoch': self.epoch()})
        self.assertEqual(code, 200); self.assertTrue(invitation['single_use'])
        self.assertEqual(self.req('owner', '/desk/identity/invitations/redeem', {'code': invitation['code']})[0], 404)
        code, view, _ = self.req('reader', '/desk/identity/invitations/redeem', {'code': invitation['code']})
        self.assertEqual((code, view['sources'][0]['permitted']['read']), (200, True))
        self.assertEqual(self.notes('reader'), 20)
        self.assertEqual(self.notes('owner'), 0)
        self.assertEqual(self.req('reader', '/desk/identity/invitations/redeem', {'code': invitation['code']})[0], 404)

    def test_invitations_are_bounded(self):
        self.login('owner'); self.login('reader')
        self.assertEqual(self.req('owner', '/desk/identity/invitations', {'source': 'demo-source', 'capability': 'inbox.write', 'days': 1, 'epoch': 0})[0], 400)
        self.assertEqual(self.req('reader', '/desk/identity/invitations', {'source': 'demo-source', 'capability': 'read', 'days': 1, 'epoch': 0})[0], 403)
        self.assertEqual(self.req('reader', '/desk/identity/invitations/redeem', {'code': 'x' * 24})[0], 404)
        self.assertEqual(self.req('owner', '/desk/identity/invitations', {'source': 'nope', 'capability': 'read', 'days': 1, 'epoch': 0})[0], 404)

    def test_other_workspace_cannot_redeem(self):
        self.login('owner')
        invitation = self.req('owner', '/desk/identity/invitations', {'source': 'demo-source', 'capability': 'read', 'days': 1, 'epoch': 0})[1]
        stranger = self.store.provision('elsewhere', 'stranger', 'owner')
        with self.assertRaises(Fault) as caught:
            IdentityPolicy(self.store).redeem(stranger, invitation['code'])
        self.assertEqual(caught.exception.code, 'invitation_not_valid')


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'demo'; init_demo(self.home)

    def test_rotation_replaces_the_key_atomically(self):
        before = load_keys(self.home)
        replacement = rotate_key(self.home, 'owner')
        after = load_keys(self.home)
        self.assertEqual(after['owner'], replacement); self.assertNotEqual(replacement, before['owner'])
        self.assertEqual((after['reader'], after['source']), (before['reader'], before['source']))
        self.assertEqual(stat.S_IMODE((self.home / 'desk-access.json').stat().st_mode), 0o600)
        store = KnowledgeStore(self.home / 'desk.sqlite')
        with self.assertRaises(Fault):
            store.principal(before['owner'])
        self.assertEqual(store.principal(replacement)['id'], 'demo-owner')
        self.assertFalse((self.home / 'desk-access.json.rotating').exists())

    def test_rotation_refuses_while_the_host_runs(self):
        fd = os.open(self.home / 'desk.lock', os.O_RDWR | os.O_CREAT, 0o600); self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = load_keys(self.home)
        with self.assertRaises(Fault) as caught:
            rotate_key(self.home, 'owner')
        self.assertEqual(caught.exception.code, 'stop_alfred_before_rotation')
        self.assertEqual(load_keys(self.home), before)


if __name__ == '__main__':
    unittest.main()
