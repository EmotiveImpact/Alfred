"""M04: explicit capture and approved, create-only inbox notes.

Synthetic vaults in temporary folders, real SQLite and the real outbox. Nothing
is sent; the only effect is a new file under ALFRED/Inbox when approved.
"""
from pathlib import Path
import hashlib
import json
import os
import tempfile
import unittest
from alfred.local import Fault
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.reviewed_memory import ReviewedMemory
from alfred.policy import IdentityPolicy
from alfred import inbox, lifecycle


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.clock = [1000]
        self.store = KnowledgeStore(self.root / 'desk.sqlite', clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=2592000)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=2592000)
        self.source = self.store.provision('work', 'source', 'source', ttl=2592000)
        self.vault = self.root / 'vault'; self.vault.mkdir()
        (self.vault / 'Atlas.md').write_text('# Atlas\nAtlas launches in spring.\n')
        self.scanner = MarkdownVault(self.store, self.source, self.vault); self.scanner.scan()
        self.memory = ReviewedMemory(self.store); self.policy = IdentityPolicy(self.store)

    def grant(self, capability, revoke=False):
        return self.policy.grant(self.owner, 'source', capability, 5000, self.policy.view(self.owner)['epoch'], revoke=revoke)


class CaptureTests(Base):
    def body(self, **over):
        n = self.store.knowledge(self.owner)['nodes'][0]
        value = {'request_id': 'remember-1', 'subject_id': 'atlas', 'predicate': 'scheduled_for', 'object_id': None, 'value': 'spring',
                 'valid_from': None, 'valid_until': None,
                 'evidence': {'note_id': n['id'], 'sha256': n['sha256'], 'revision': n['revision'], 'start_line': 2, 'end_line': 2},
                 'memory_type': 'commitment', 'retention_days': 30, 'captured_from': {'note_id': n['id']}}
        value.update(over); return value

    def setUp(self):
        super().setUp(); self.memory.create_entity(self.owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas'})

    def test_capture_previews_scope_type_source_and_retention_without_accepting(self):
        made = self.memory.capture(self.owner, self.body())
        preview = made['preview']
        self.assertEqual((made['state'], preview['scope'], preview['memory_type']), ('proposed', 'work', 'commitment'))
        self.assertEqual(preview['retention_until'], 1000 + 30 * 86400)
        self.assertEqual(preview['source']['quote'], 'Atlas launches in spring.')
        self.assertTrue(preview['needs_review']); self.assertFalse(preview['authority_granted'])
        claim = self.memory.view(self.owner)['claims'][0]
        self.assertFalse(claim['usable'])

    def test_invalid_capture_values_are_rejected(self):
        for over in ({'memory_type': 'fact'}, {'retention_days': 0}, {'retention_days': 'forever'}, {'captured_from': {'path': '/etc'}}):
            with self.assertRaises(Fault, msg=over):
                self.memory.capture(self.owner, self.body(**over))
        self.assertEqual(self.memory.view(self.owner)['claims'], [])

    def test_retention_expiry_forgets_with_a_receipt(self):
        made = self.memory.capture(self.owner, self.body(retention_days=1))
        self.memory.review(self.owner, made['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        self.assertEqual(self.memory.apply_retention(self.owner), [])
        self.clock[0] += 86401
        receipts = self.memory.apply_retention(self.owner)
        self.assertEqual([r['subject'] for r in receipts], [made['id']])
        self.assertEqual(self.memory.view(self.owner)['claims'][0]['state'], 'forgotten')
        self.assertEqual(lifecycle.entries(lifecycle.journal_path(self.store))[-1]['subject'], made['id'])

    def test_keep_means_no_expiry(self):
        made = self.memory.capture(self.owner, self.body(retention_days=None))
        self.clock[0] += 10**6
        self.assertEqual(self.memory.apply_retention(self.owner), [])
        self.assertIsNone(made['preview']['retention_until'])


class InboxTests(Base):
    def propose(self, request='inbox-1', filename='Atlas follow-up.md', content='# Atlas follow-up\nConfirm the launch window.\n'):
        return inbox.propose(self.store, self.owner, {'request_id': request, 'source': 'source', 'filename': filename, 'content': content})

    def approve(self, action):
        return self.store.approve(self.owner, action['id'], action['fingerprint'])

    def target(self, name='Atlas follow-up.md'):
        return self.vault / 'ALFRED' / 'Inbox' / name

    def granted(self):
        self.grant('read'); self.grant('inbox.write')

    def test_legacy_policy_never_allows_writes(self):
        with self.assertRaises(Fault) as caught:
            self.propose()
        self.assertEqual(caught.exception.code, 'inbox_write_not_granted')

    def test_read_grant_alone_does_not_allow_writes(self):
        self.grant('read')
        with self.assertRaises(Fault):
            self.propose()

    def test_approved_note_is_created_exactly_verified_and_indexed(self):
        self.granted(); action = self.propose()
        self.assertEqual(action['state'], 'proposed'); self.assertFalse(self.target().exists())
        self.assertEqual(self.approve(action)['state'], 'queued')
        result = self.store.tick(self.owner)
        self.assertEqual(result['state'], 'verified')
        self.assertEqual(self.target().read_text(), '# Atlas follow-up\nConfirm the launch window.\n')
        self.assertEqual(result['proof']['sha256'], hashlib.sha256(self.target().read_bytes()).hexdigest())
        self.scanner.scan()
        self.assertIn('ALFRED/Inbox/Atlas follow-up.md', [n['path'] for n in self.store.knowledge(self.owner)['nodes']])
        self.assertEqual(sorted(os.listdir(self.target().parent)), ['Atlas follow-up.md'])

    def test_wrong_fingerprint_cannot_approve(self):
        self.granted(); action = self.propose()
        with self.assertRaises(Fault):
            self.store.approve(self.owner, action['id'], '0' * 64)

    def test_human_file_created_after_approval_is_never_overwritten(self):
        self.granted(); action = self.propose(); self.approve(action)
        self.target().parent.mkdir(parents=True); self.target().write_text('Human note.\n')
        result = self.store.tick(self.owner)
        self.assertEqual((result['state'], result['proof']['reason']), ('failed', 'destination_exists'))
        self.assertEqual(self.target().read_text(), 'Human note.\n')

    def test_indexed_destination_refused_at_proposal(self):
        self.granted(); self.target().parent.mkdir(parents=True); self.target().write_text('Existing.\n'); self.scanner.scan()
        with self.assertRaises(Fault) as caught:
            self.propose()
        self.assertEqual(caught.exception.code, 'inbox_destination_exists')

    def test_duplicate_request_is_idempotent_and_changed_request_collides(self):
        self.granted(); first = self.propose()
        self.assertEqual(self.propose()['fingerprint'], first['fingerprint'])
        with self.assertRaises(Fault) as caught:
            self.propose(content='Different.\n')
        self.assertEqual(caught.exception.code, 'action_id_collision')

    def test_crash_after_write_reconciles_by_reading_back(self):
        self.granted(); action = self.propose(); self.approve(action)
        with self.assertRaises(RuntimeError):
            self.store.tick(self.owner, crash_at='after_effect')
        self.clock[0] += 31; self.store.tick(self.owner)
        self.assertEqual(self.store.desk_state(self.owner)['actions'][0]['state'], 'uncertain')
        self.assertEqual(self.store.reconcile(self.owner, action['id'])['state'], 'verified')
        self.assertTrue(self.target().exists())

    def test_revoked_write_grant_blocks_dispatch(self):
        self.granted(); action = self.propose(); self.approve(action)
        self.grant('inbox.write', revoke=True)
        self.assertEqual(self.store.tick(self.owner)['state'], 'blocked')
        self.assertFalse(self.target().exists())

    def test_symlinked_inbox_folder_is_not_followed(self):
        self.granted(); outside = self.root / 'outside'; outside.mkdir()
        (self.vault / 'ALFRED').symlink_to(outside, target_is_directory=True)
        action = self.propose(); self.approve(action)
        result = self.store.tick(self.owner)
        self.assertEqual((result['state'], result['proof']['reason']), ('failed', 'vault_unavailable'))
        self.assertEqual(list(outside.iterdir()), [])

    def test_unsafe_names_are_rejected(self):
        self.granted()
        for name in ('../escape.md', 'a/b.md', 'note.txt', '.hidden.md', ''):
            with self.assertRaises(Fault, msg=name):
                self.propose(request='r-' + str(abs(hash(name)) % 1000), filename=name)

    def test_reader_cannot_propose(self):
        self.granted()
        with self.assertRaises(Fault):
            inbox.propose(self.store, self.reader, {'request_id': 'x', 'source': 'source', 'filename': 'x.md', 'content': 'x'})

    def test_paused_workspace_does_not_write(self):
        self.granted(); action = self.propose(); self.approve(action)
        self.store.set_paused(self.owner, True)
        self.assertEqual(self.store.tick(self.owner), {'state': 'paused'})
        self.assertFalse(self.target().exists())

    def test_replaced_vault_root_is_refused(self):
        self.granted(); action = self.propose(); self.approve(action)
        self.vault.rename(self.root / 'original'); self.vault.mkdir()
        result = self.store.tick(self.owner)
        self.assertEqual((result['state'], result['proof']['reason']), ('failed', 'vault_unavailable'))
        self.assertFalse(self.target().exists())


if __name__ == '__main__':
    unittest.main()
