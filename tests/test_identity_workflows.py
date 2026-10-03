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
        # Explicit pre-migration compatibility fixture; new installation coverage
        # lives in test_permission_defaults, without this synthetic legacy option.
        self.home = Path(self.tmp.name) / 'demo'; self.keys = init_demo(self.home, legacy_scope=True)
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
        stranger = self.store.provision('elsewhere', 'stranger', 'owner', legacy_scope=True)
        with self.assertRaises(Fault) as caught:
            IdentityPolicy(self.store).redeem(stranger, invitation['code'])
        self.assertEqual(caught.exception.code, 'invitation_not_valid')


class PairingTests(IdentityHTTPTests):
    """M02 pairing: another device for the same person, without copying a key."""

    def pair(self, name, code, label='Fictional tablet'):
        status, body, cookie = self.req(name, '/desk/identity/pairing/redeem', {'code': code, 'label': label})
        if status == 200:
            self.sessions[name] = (cookie.split(';')[0], body['csrf'])
        return status, body

    def offer(self, role='owner', by='owner'):
        return self.req(by, '/desk/identity/pairing', {'role': role})

    def test_a_paired_device_is_the_same_person_with_no_more_authority(self):
        self.login('owner')
        self.req('owner', '/desk/identity/grants', {'source': 'demo-source', 'capability': 'read', 'days': 30, 'epoch': self.epoch(), 'revoke': False})
        status, offer, _ = self.offer()
        self.assertEqual((status, offer['single_use'], len(offer['code'])), (200, True, 24))
        owner_view = self.req('owner', '/desk/identity')[1]
        status, paired = self.pair('tablet', offer['code'])
        self.assertEqual((status, paired['role']), (200, 'owner'))
        self.assertLessEqual(paired['expires_at'], offer['device_expires_no_later_than'])
        tablet_view = self.req('tablet', '/desk/identity')[1]
        self.assertEqual(tablet_view['person_id'], owner_view['person_id'])
        self.assertNotEqual(tablet_view['device_id'], owner_view['device_id'])
        self.assertEqual(self.notes('tablet'), 20)  # Grants belong to the person, so they apply here too.
        devices = {d['label']: d for d in tablet_view['devices']}
        self.assertEqual(set(devices), {'Fictional tablet', 'Provisioned access key'})
        self.assertTrue(devices['Fictional tablet']['current'])
        # The key works on its own after the pairing session.
        self.assertEqual(self.store.principal(paired['key'])['role'], 'owner')

    def test_pairing_codes_are_single_use_bounded_and_indistinguishable(self):
        self.login('owner'); self.login('reader')
        code = self.offer()[1]['code']
        self.assertEqual(self.pair('tablet', code)[0], 200)
        self.assertEqual(self.pair('second', code), (404, {'error': 'pairing_not_valid'}))
        self.assertEqual(self.pair('third', 'x' * 24)[0], 404)
        self.assertEqual(self.pair('fourth', self.offer()[1]['code'], label='  ')[0], 400)
        # A reader can pair a reader device for themselves, never an owner device.
        self.assertEqual(self.offer('owner', by='reader')[0], 400)
        status, reader_device = self.pair('reader-phone', self.offer('reader', by='reader')[1]['code'], 'Fictional phone')
        self.assertEqual((status, reader_device['role']), (200, 'reader'))
        # An owner may pair a lower-authority reader device for themselves.
        status, reading = self.pair('owner-reader', self.offer('reader')[1]['code'])
        self.assertEqual((status, reading['role']), (200, 'reader'))
        self.assertEqual(self.req('owner-reader', '/desk/identity/invitations', {'source': 'demo-source', 'capability': 'read', 'days': 1, 'epoch': 0})[0], 403)
        # An expired code and a code from a revoked device are refused the same way.
        expired = self.offer()[1]['code']
        with self.store.transaction() as db:
            db.execute('UPDATE device_pairings SET expires=0 WHERE redeemed_at IS NULL')
        self.assertEqual(self.pair('late', expired), (404, {'error': 'pairing_not_valid'}))
        orphan = self.offer('reader', by='reader')[1]['code']
        self.store.revoke('demo-reader')
        self.assertEqual(self.pair('orphan', orphan), (404, {'error': 'pairing_not_valid'}))

    def test_refused_pairings_share_the_sign_in_failure_budget(self):
        for _ in range(20):
            self.assertEqual(self.pair('guess', 'y' * 24)[0], 404)
        self.assertEqual(self.pair('guess', 'y' * 24)[0], 429)
        self.assertEqual(self.req('owner', '/desk/login', {'key': self.keys['owner']})[0], 429)

    def test_a_person_revokes_only_their_own_other_devices(self):
        self.login('owner'); self.login('reader')
        self.pair('tablet', self.offer()[1]['code'])
        owner_device = self.req('owner', '/desk/identity')[1]['device_id']
        tablet_device = self.req('tablet', '/desk/identity')[1]['device_id']
        self.assertEqual(self.req('tablet', f'/desk/identity/devices/{tablet_device}/revoke', {})[1], {'error': 'cannot_revoke_current_device'})
        self.assertEqual(self.req('reader', f'/desk/identity/devices/{owner_device}/revoke', {})[0], 404)
        status, view, _ = self.req('tablet', f'/desk/identity/devices/{owner_device}/revoke', {})
        self.assertEqual((status, [d['label'] for d in view['devices']]), (200, ['Fictional tablet']))
        self.assertEqual(self.req('owner', '/desk/identity')[0], 401)
        from alfred.lifecycle import entries, journal_path
        self.assertIn(('credential_revoked', 'demo-owner'), [(e['kind'], e.get('subject')) for e in entries(journal_path(self.store))])

    # The inherited tests also run here, so pairing never changes earlier behaviour.


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
