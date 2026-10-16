"""Plan item 1.5: approved `vault.append_section` writes (M04, MEM-002).

Synthetic vaults in temporary folders, real SQLite, the real approval route and
outbox. The only effect is an insertion under a named heading of an existing note,
after approval of an exact diff. Concurrent edits make the write refuse, never
clobber. Nothing is sent.
"""
from pathlib import Path
import hashlib
import http.client
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from alfred import lifecycle, vault_append
from alfred.desk import init_demo
from alfred.desk_http import DeskHTTPServer
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor, MarkdownVault
from alfred.local import Fault
from alfred.policy import IdentityPolicy

FIXTURE = Path(__file__).parent / 'fixtures' / 'obsidian_vault'
NOTE = '# Atlas\n\nIntro line.\n\n## Actions\n\n- Existing human item\n\n## Later\n\nHuman closing text.\n'


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.clock = [1000]
        self.store = KnowledgeStore(self.root / 'desk.sqlite', clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=2592000)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=2592000)
        self.source = self.store.provision('work', 'source', 'source', ttl=2592000)
        self.vault = self.root / 'vault'; self.vault.mkdir()
        self.note = self.vault / 'Atlas.md'
        self.note.write_bytes(NOTE.encode())
        self.scanner = MarkdownVault(self.store, self.source, self.vault); self.scanner.scan()
        self.policy = IdentityPolicy(self.store)

    def grant(self, capability, revoke=False):
        return self.policy.grant(self.owner, 'source', capability, 5000, self.policy.view(self.owner)['epoch'], revoke=revoke)

    def granted(self):
        self.grant('read'); self.grant('vault.append')

    def indexed(self, path='Atlas.md'):
        return next(n for n in self.store.knowledge(self.owner)['nodes'] if n['path'] == path)

    def propose(self, request='append-1', heading='Actions', text='- Confirm the venue', path='Atlas.md', base=None, bearer=None):
        n = self.indexed(path)
        return vault_append.propose(self.store, bearer or self.owner, {
            'request_id': request, 'source': 'source', 'note_id': n['id'], 'base_sha256': base or n['sha256'],
            'heading': heading, 'text': text})

    def approve(self, action):
        return self.store.approve(self.owner, action['id'], action['fingerprint'])

    def assert_insertion_only(self, before, after, action):
        offset, inserted = action['parameters']['offset'], action['parameters']['inserted'].encode()
        self.assertEqual(after, before[:offset] + inserted + before[offset:])


class GrantTests(Base):
    def test_legacy_policy_never_allows_appends(self):
        with self.assertRaises(Fault) as caught:
            self.propose()
        self.assertEqual(caught.exception.code, 'vault_append_not_granted')

    def test_inbox_or_read_grant_does_not_allow_appends(self):
        self.grant('read'); self.grant('inbox.write')
        with self.assertRaises(Fault) as caught:
            self.propose()
        self.assertEqual(caught.exception.code, 'vault_append_not_granted')

    def test_reader_cannot_propose(self):
        self.granted()
        with self.assertRaises(Fault):
            self.propose(bearer=self.reader)

    def test_append_grant_cannot_be_invited(self):
        with self.assertRaises(Fault) as caught:
            self.policy.invite(self.owner, 'source', 'vault.append', 2000, self.policy.view(self.owner)['epoch'])
        self.assertEqual(caught.exception.code, 'invalid_capability')


class AppendTests(Base):
    def setUp(self):
        super().setUp(); self.granted()

    def test_proposal_shows_the_exact_diff_and_writes_nothing(self):
        action = self.propose()
        self.assertEqual((action['state'], action['capability'], action['effect']),
                         ('proposed', 'vault.append_section', 'vault_note_append_insert_only_not_sent'))
        self.assertEqual(action['diff'], action['parameters']['diff'])
        self.assertIn('+- Confirm the venue', action['diff'].splitlines())
        self.assertTrue(action['diff'].startswith('--- a/Atlas.md\n+++ b/Atlas.md\n'))
        self.assertFalse([l for l in action['diff'].splitlines()[2:] if l.startswith('-')])
        self.assertEqual(self.note.read_bytes(), NOTE.encode())

    def test_approved_append_is_inserted_under_the_heading_verified_and_reindexed(self):
        before = self.note.read_bytes(); identity = self.indexed()['id']
        action = self.propose(); self.approve(action)
        result = self.store.tick(self.owner)
        self.assertEqual(result['state'], 'verified')
        after = self.note.read_bytes()
        self.assert_insertion_only(before, after, action)
        self.assertEqual(after.decode(), NOTE.replace('- Existing human item\n', '- Existing human item\n\n- Confirm the venue\n'))
        self.assertEqual(result['proof'], {'type': 'vault_append_readback', 'path': 'Atlas.md', 'heading': 'Actions',
                                           'sha256': hashlib.sha256(after).hexdigest(), 'base_sha256': hashlib.sha256(before).hexdigest(),
                                           'offset': action['parameters']['offset'], 'inserted_sha256': action['parameters']['inserted_sha256'],
                                           'sent': False})
        self.scanner.scan()
        node = self.indexed()
        self.assertEqual((node['id'], node['revision'], node['sha256']), (identity, 2, hashlib.sha256(after).hexdigest()))
        self.assertEqual(sorted(os.listdir(self.vault)), ['Atlas.md'])

    def test_wrong_fingerprint_cannot_approve(self):
        action = self.propose()
        with self.assertRaises(Fault):
            self.store.approve(self.owner, action['id'], '0' * 64)

    def test_heading_only_section_end_of_file_and_crlf(self):
        cases = [
            ('# A\n## Empty\n## Next\nx\n', 'Empty', '# A\n## Empty\nNew\n\n## Next\nx\n'),
            ('# A\n## Last\nText', 'Last', '# A\n## Last\nText\n\nNew\n'),
            ('# A\r\n## Win\r\nOld\r\n', 'win', '# A\r\n## Win\r\nOld\r\n\r\nNew\r\n'),
            ('﻿# A\nBody\n', 'A', '﻿# A\nBody\n\nNew\n'),
        ]
        for i, (body, heading, expected) in enumerate(cases):
            with self.subTest(body=body):
                path = 'case%d.md' % i
                (self.vault / path).write_bytes(body.encode())
                self.scanner.scan()
                action = self.propose(request='case-%d' % i, heading=heading, text='New', path=path); self.approve(action)
                self.assertEqual(self.store.tick(self.owner)['state'], 'verified')
                self.assertEqual((self.vault / path).read_bytes(), expected.encode())

    def test_nested_section_appends_before_the_next_sibling_heading(self):
        self.note.write_text('# A\n## Plan\nP\n### Detail\nD\n## Review\nR\n'); self.scanner.scan()
        action = self.propose(heading='Plan', text='Added'); self.approve(action); self.store.tick(self.owner)
        self.assertEqual(self.note.read_text(), '# A\n## Plan\nP\n### Detail\nD\n\nAdded\n\n## Review\nR\n')

    def test_fixture_note_with_callouts_and_blocks_keeps_every_anchor(self):
        shutil.copy(FIXTURE / 'Projects' / 'Atlas.md', self.vault / 'Fixture.md'); self.scanner.scan()
        before = (self.vault / 'Fixture.md').read_bytes()
        action = self.propose(path='Fixture.md', heading='Milestones', text='- Book the room ^book-room')
        self.approve(action); self.assertEqual(self.store.tick(self.owner)['state'], 'verified')
        self.assert_insertion_only(before, (self.vault / 'Fixture.md').read_bytes(), action)
        self.scanner.scan()
        structure = self.store.knowledge_note(self.owner, self.indexed('Fixture.md')['id'])['structure']
        self.assertEqual([b['name'] for b in structure['blocks']], ['summary', 'first-step', 'book-room', 'budget-table', 'quote-1'])

    def test_invalid_requests_are_refused_at_proposal(self):
        self.note.write_text('# A\n## Dup\n## Dup\nText ^known\n'); self.scanner.scan()
        cases = {('Missing', 'x'): 'append_heading_missing', ('Dup', 'x'): 'append_heading_ambiguous',
                 ('A', '## New heading'): 'append_text_changes_structure', ('A', 'Title\n==='): 'append_text_changes_structure',
                 ('A', '---'): 'append_text_changes_structure', ('A', 'Repeat ^known'): 'append_block_id_exists',
                 ('A', '```\nopen fence'): 'unclosed_code_fence', ('A', 'bad\x07bell'): 'control_character',
                 ('A', ' \n '): 'invalid_append_text', ('A#B', 'x'): 'invalid_append_heading'}
        for i, ((heading, text), code) in enumerate(cases.items()):
            with self.subTest(heading=heading, text=text):
                with self.assertRaises(Fault) as caught:
                    self.propose(request='bad-%d' % i, heading=heading, text=text)
                self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.store.desk_state(self.owner)['actions'], [])

    def test_stale_base_is_refused_at_proposal(self):
        with self.assertRaises(Fault) as caught:
            self.propose(base='0' * 64)
        self.assertEqual(caught.exception.code, 'note_changed_since_read')
        # The file changed on disk but the index has not caught up yet.
        self.note.write_text(NOTE + 'Human addition.\n')
        with self.assertRaises(Fault) as caught:
            self.propose()
        self.assertEqual(caught.exception.code, 'note_changed_since_read')


class IdempotencyTests(Base):
    def setUp(self):
        super().setUp(); self.granted()

    def test_same_request_returns_the_same_action_and_changed_request_collides(self):
        first = self.propose()
        self.assertEqual(self.propose()['fingerprint'], first['fingerprint'])
        with self.assertRaises(Fault) as caught:
            self.propose(text='- Something else')
        self.assertEqual(caught.exception.code, 'action_id_collision')

    def test_repeating_a_completed_request_never_appends_twice(self):
        action = self.propose(); self.approve(action); self.store.tick(self.owner)
        once = self.note.read_bytes()
        again = self.propose()  # same request after completion, before or after a rescan
        self.assertEqual((again['id'], again['state']), (action['id'], 'verified'))
        self.scanner.scan()
        self.assertEqual(self.propose(base=action['parameters']['base_sha256'])['state'], 'verified')
        # The same id with the new base is a different request, not a repeat.
        with self.assertRaises(Fault) as caught:
            self.propose()
        self.assertEqual(caught.exception.code, 'action_id_collision')
        self.assertEqual(self.store.tick(self.owner), {'state': 'idle'})
        self.assertEqual(self.note.read_bytes(), once)
        self.assertEqual(once.decode().count('Confirm the venue'), 1)

    def test_crash_after_write_reconciles_by_reading_back_without_rewriting(self):
        action = self.propose(); self.approve(action)
        with self.assertRaises(RuntimeError):
            self.store.tick(self.owner, crash_at='after_effect')
        written = self.note.read_bytes(); self.clock[0] += 31; self.store.tick(self.owner)
        self.assertEqual(self.store.desk_state(self.owner)['actions'][0]['state'], 'uncertain')
        self.assertEqual(self.store.reconcile(self.owner, action['id'])['state'], 'verified')
        self.assertEqual(self.note.read_bytes(), written)
        self.assertEqual(written.decode().count('Confirm the venue'), 1)

    def test_the_writer_recognises_its_own_completed_append(self):
        action = self.propose(); p = action['parameters']
        writer = self.store.vault_writers['source']
        args = (p['path'], p['base_sha256'], p['offset'], p['inserted'].encode(), p['result_sha256'])
        self.assertEqual(writer.append_to_note(*args), 'appended')
        self.assertEqual(writer.append_to_note(*args), 'exists_same')
        self.assertEqual(self.note.read_text().count('Confirm the venue'), 1)

    def test_second_request_from_the_same_base_is_refused_after_the_first_lands(self):
        first = self.propose(request='a-1'); second = self.propose(request='a-2', text='- Another item')
        self.approve(first); self.approve(second)
        self.assertEqual(self.store.tick(self.owner)['state'], 'verified')
        refused = self.store.tick(self.owner)
        self.assertEqual((refused['state'], refused['proof']['reason']), ('failed', 'note_changed_since_proposal'))
        self.assertNotIn('Another item', self.note.read_text())


class ConcurrentEditTests(Base):
    def setUp(self):
        super().setUp(); self.granted()

    def test_human_edit_after_approval_is_never_overwritten(self):
        action = self.propose(); self.approve(action)
        human = NOTE + 'Typed by a person after approval.\n'
        self.note.write_text(human)
        result = self.store.tick(self.owner)
        self.assertEqual((result['state'], result['proof']), ('failed', {'type': 'vault_append_refused', 'reason': 'note_changed_since_proposal', 'sent': False}))
        self.assertEqual(self.note.read_text(), human)

    def test_indexed_edit_before_approval_expires_the_proposal(self):
        action = self.propose()
        self.note.write_text(NOTE + 'Edited.\n'); self.scanner.scan()
        with self.assertRaises(Fault) as caught:
            self.approve(action)
        self.assertEqual(caught.exception.code, 'evidence_or_approval_expired')

    def test_indexed_edit_after_approval_blocks_dispatch(self):
        action = self.propose(); self.approve(action)
        self.note.write_text(NOTE + 'Edited.\n'); self.scanner.scan()
        self.assertEqual(self.store.tick(self.owner)['state'], 'blocked')
        self.assertEqual(self.note.read_text(), NOTE + 'Edited.\n')

    def test_edit_landing_between_read_and_rename_is_kept(self):
        action = self.propose(); self.approve(action)
        original = MarkdownVault._read_note_at
        human = NOTE + 'Saved by the editor mid-write.\n'

        def racing(vault, fd, name):
            data, info = original(vault, fd, name)
            time.sleep(0.01); self.note.write_text(human)  # the editor saves in place
            return data, info

        with patch.object(MarkdownVault, '_read_note_at', racing):
            result = self.store.tick(self.owner)
        self.assertEqual((result['state'], result['proof']['reason']), ('failed', 'note_changed_since_proposal'))
        self.assertEqual(self.note.read_text(), human)
        self.assertEqual(sorted(os.listdir(self.vault)), ['Atlas.md'])

    def test_replaced_note_and_links_are_refused(self):
        action = self.propose(); self.approve(action)
        outside = self.root / 'outside.md'; outside.write_bytes(NOTE.encode())
        self.note.unlink(); self.note.symlink_to(outside)
        result = self.store.tick(self.owner)
        self.assertEqual((result['state'], result['proof']['reason']), ('failed', 'note_unavailable'))
        self.assertEqual(outside.read_bytes(), NOTE.encode())

    def test_hardlinked_note_is_refused(self):
        action = self.propose(); self.approve(action)
        os.link(self.note, self.root / 'second-name.md')
        result = self.store.tick(self.owner)
        self.assertEqual((result['state'], result['proof']['reason']), ('failed', 'note_unavailable'))
        self.assertEqual(self.note.read_bytes(), NOTE.encode())

    def test_replaced_vault_root_is_refused(self):
        action = self.propose(); self.approve(action)
        self.vault.rename(self.root / 'original'); self.vault.mkdir(); (self.vault / 'Atlas.md').write_bytes(NOTE.encode())
        result = self.store.tick(self.owner)
        self.assertEqual((result['state'], result['proof']['reason']), ('failed', 'vault_unavailable'))
        self.assertEqual((self.vault / 'Atlas.md').read_bytes(), NOTE.encode())

    def test_revoked_grant_blocks_dispatch(self):
        action = self.propose(); self.approve(action)
        self.grant('vault.append', revoke=True)
        self.assertEqual(self.store.tick(self.owner)['state'], 'blocked')
        self.assertEqual(self.note.read_bytes(), NOTE.encode())

    def test_paused_workspace_does_not_write(self):
        action = self.propose(); self.approve(action)
        self.store.set_paused(self.owner, True)
        self.assertEqual(self.store.tick(self.owner), {'state': 'paused'})
        self.assertEqual(self.note.read_bytes(), NOTE.encode())

    def test_forgetting_the_source_cancels_a_pending_append(self):
        action = self.propose(); self.approve(action)
        receipt = lifecycle.forget_source(self.store, self.owner, 'source')
        self.assertIn(action['id'], json.dumps(receipt))
        self.assertEqual(self.store.tick(self.owner), {'state': 'idle'})
        self.assertEqual(self.note.read_bytes(), NOTE.encode())


class AppendHTTPTests(unittest.TestCase):
    """The new route inherits sign-in, Origin and CSRF checks from the existing server."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'demo'; self.keys = init_demo(self.home)
        self.store = KnowledgeStore(self.home / 'desk.sqlite')
        self.sup = KnowledgeSupervisor(self.store, self.keys['owner'], self.keys['source'], self.home / 'project', vault=self.home / 'vault')
        self.sup.cycle()
        policy = IdentityPolicy(self.store)
        for capability in ('read', 'vault.append'):
            policy.grant(self.keys['owner'], 'demo-source', capability, int(time.time()) + 3600, policy.view(self.keys['owner'])['epoch'])
        self.server = DeskHTTPServer(self.store, self.sup, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)

    def request(self, path, data=None, headers=None, origin=True):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = dict(headers or {})
        if data is not None:
            headers['Content-Type'] = 'application/json'
            if origin: headers['Origin'] = self.server.origin
        c.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); body = r.read(); c.close()
        return r, json.loads(body or b'{}')

    def test_owner_session_proposes_and_approves_through_the_desk(self):
        r, body = self.request('/desk/login', {'key': self.keys['owner']}); self.assertEqual(r.status, 200)
        session = {'Cookie': r.getheader('Set-Cookie').split(';')[0], 'X-CSRF-Token': body['csrf']}
        r, data = self.request('/desk/knowledge', headers=session); self.assertEqual(r.status, 200)
        note = next(n for n in data['nodes'] if n['path'] == 'notes/Brief.md')
        before = (self.home / 'vault' / 'notes' / 'Brief.md').read_bytes()
        heading = next(l[2:].strip() for l in before.decode().splitlines() if l.startswith('# '))
        payload = {'request_id': 'http-append', 'source': 'demo-source', 'note_id': note['id'],
                   'base_sha256': note['sha256'], 'heading': heading, 'text': 'Added through the desk.'}
        r, _ = self.request('/desk/vault/append-proposals', payload, headers={'Cookie': session['Cookie']})
        self.assertEqual(r.status, 403)  # no CSRF token
        r, _ = self.request('/desk/vault/append-proposals', payload, headers=session, origin=False)
        self.assertEqual(r.status, 403)  # no Origin
        r, action = self.request('/desk/vault/append-proposals', payload, headers=session)
        self.assertEqual(r.status, 200, action)
        self.assertIn('+Added through the desk.', action['diff'])
        r, _ = self.request('/desk/actions/http-append/approve', {'fingerprint': action['fingerprint']}, headers=session)
        self.assertEqual(r.status, 200)
        self.sup.cycle()
        after = (self.home / 'vault' / 'notes' / 'Brief.md').read_bytes()
        offset = action['parameters']['offset']
        self.assertEqual(after, before[:offset] + action['parameters']['inserted'].encode() + before[offset:])


if __name__ == '__main__':
    unittest.main()
