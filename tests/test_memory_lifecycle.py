"""M05 lifecycle: unavailable versus deleted, forgetting and restore without resurrection.

Synthetic notes, real SQLite, real HTTP where the boundary matters. No model.
"""
from pathlib import Path
import http.client
import json
import tempfile
import threading
import unittest
from alfred.local import Fault
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.reviewed_memory import ReviewedMemory
from alfred.conversation import ConversationService
from alfred.policy import IdentityPolicy
from alfred.grounded import retrieve
from alfred import lifecycle


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.clock = [1000]
        self.db = self.root / 'desk.sqlite'
        self.store = KnowledgeStore(self.db, clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=100000)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=100000)
        self.source = self.store.provision('work', 'source', 'source', ttl=100000)
        self.other = self.store.provision('work', 'other', 'source', ttl=100000)
        self.vault = self.root / 'vault'; self.vault.mkdir()
        (self.vault / 'Atlas.md').write_text('# Atlas\nAtlas is awaiting review.\nMina leads Atlas.\n')
        self.scanner = MarkdownVault(self.store, self.source, self.vault); self.scanner.scan()
        self.memory = ReviewedMemory(self.store); self.policy = IdentityPolicy(self.store)
        self.memory.create_entity(self.owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas'})
        self.memory.create_entity(self.owner, {'id': 'mina', 'kind': 'person', 'name': 'Mina'})
        self.status = self.accept('s1', 'status', 2, value='awaiting review')
        self.lead = self.accept('s2', 'responsible_person', 3, obj='mina')

    def note(self):
        return self.store.knowledge(self.owner)['nodes'][0]

    def accept(self, request, predicate, line, value=None, obj=None):
        n = self.note()
        made = self.memory.propose(self.owner, {'request_id': request, 'subject_id': 'atlas', 'predicate': predicate, 'object_id': obj, 'value': value,
                                                'valid_from': None, 'valid_until': None,
                                                'evidence': {'note_id': n['id'], 'sha256': n['sha256'], 'revision': n['revision'], 'start_line': line, 'end_line': line}})
        self.memory.review(self.owner, made['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        return made['id']

    def claim(self, identity, bearer=None):
        return next(c for c in self.memory.view(bearer or self.owner)['claims'] if c['id'] == identity)

    def grant(self, source, revoke=False):
        return self.policy.grant(self.owner, source, 'read', 5000, self.policy.view(self.owner)['epoch'], revoke=revoke)

    # Unavailable is not deleted.
    def test_grant_loss_withholds_and_regrant_restores(self):
        self.grant('other')
        withheld = self.claim(self.status)
        self.assertEqual((withheld['state'], withheld['usable'], withheld['withheld'], withheld['value']), ('accepted', False, True, None))
        self.assertEqual(retrieve(self.store, self.owner, 'What is the Atlas status?')['memory'], [])
        self.grant('source')
        restored = self.claim(self.status)
        self.assertEqual((restored['usable'], restored['value']), (True, 'awaiting review'))

    def test_unavailable_source_withholds_then_needs_fresh_review(self):
        self.store.knowledge_unavailable(self.source, 'vault_offline')
        during = self.claim(self.status)
        self.assertEqual((during['state'], during['withheld'], during['value']), ('accepted', True, None))
        # M01 gives returning notes a new revision after an outage, so the review is not revived.
        self.scanner.scan()
        self.assertEqual(self.claim(self.status)['state'], 'invalidated')

    def test_content_change_still_invalidates(self):
        (self.vault / 'Atlas.md').write_text('# Atlas\nAtlas is cancelled.\nMina leads Atlas.\n'); self.scanner.scan()
        self.assertEqual(self.claim(self.status)['state'], 'invalidated')

    def test_deleted_source_invalidates(self):
        (self.vault / 'Atlas.md').unlink(); self.scanner.scan()
        self.assertEqual(self.claim(self.status)['state'], 'invalidated')

    # Forgetting.
    def test_forget_removes_value_from_every_current_view(self):
        receipt = self.memory.forget(self.owner, self.status, {'version': self.claim(self.status)['version']})
        forgotten = self.claim(self.status)
        self.assertEqual((forgotten['state'], forgotten['value'], forgotten['usable']), ('forgotten', None, False))
        self.assertNotIn('awaiting review', json.dumps(self.memory.view(self.owner)))
        packet = retrieve(self.store, self.owner, 'What is the Atlas status awaiting review?')
        self.assertNotIn(self.status, [m['claim_id'] for m in packet['memory']])
        self.assertEqual(receipt['kind'], 'claim_forgotten'); self.assertFalse(receipt['secure_erasure'])
        self.assertTrue(any('not secure erasure' in r for r in receipt['remains']))
        with self.store.connection() as db:
            self.assertIsNone(db.execute('SELECT value FROM memory_claims WHERE id=?', (self.status,)).fetchone()[0])

    def test_forget_is_idempotent_and_version_bound(self):
        with self.assertRaises(Fault) as caught:
            self.memory.forget(self.owner, self.status, {'version': 1})
        self.assertEqual(caught.exception.code, 'memory_review_changed')
        first = self.memory.forget(self.owner, self.status, {'version': self.claim(self.status)['version']})
        again = self.memory.forget(self.owner, self.status, {'version': 1})
        self.assertEqual(first['id'], again['id'])

    def test_reader_cannot_forget_owner_statement(self):
        with self.assertRaises(Fault):
            self.memory.forget(self.reader, self.status, {'version': 2})

    def test_forget_withdraws_saved_answer_and_cancels_pending_draft(self):
        service = ConversationService(self.store, None, 'work'); self.addCleanup(service.stop)
        sid = service.create(self.owner, {'title': 'Atlas'})['id']
        service.submit(self.owner, sid, {'question': 'What is the Atlas status?', 'mode': 'sources', 'follow_up': False, 'request_id': 'q1', 'after': 0})
        service.process_one()
        turn = service.view(self.owner, sid)['turns'][0]
        self.assertIn(self.status, [m['claim_id'] for m in turn['result']['packet']['memory']])
        draft = service.propose_draft(self.owner, sid, {'turn_id': turn['id'], 'text': 'Atlas update.', 'request_id': 'draft-1'})
        receipt = self.memory.forget(self.owner, self.status, {'version': self.claim(self.status)['version']})
        self.assertEqual(receipt['conversation_answers_withdrawn'], 1)
        self.assertEqual(receipt['pending_actions_cancelled'], [draft['id']])
        self.assertEqual(service.view(self.owner, sid)['turns'][0]['state'], 'memory_forgotten')
        self.assertEqual(self.store.desk_state(self.owner)['actions'][0]['state'], 'cancelled')

    def test_forget_entity_removes_name_and_statements(self):
        receipt = self.memory.forget_entity(self.owner, 'mina', {})
        view = self.memory.view(self.owner)
        self.assertNotIn('mina', [e['id'] for e in view['entities']])
        self.assertEqual(self.claim(self.lead)['state'], 'forgotten')
        self.assertNotIn('Mina', json.dumps(view['entities']))
        self.assertEqual(self.memory.forget_entity(self.owner, 'mina', {})['id'], receipt['id'])

    # Backup and restore.
    def test_restore_does_not_resurrect_forgotten_or_revoked(self):
        manifest = lifecycle.backup(self.store, self.owner, self.root / 'backups')
        self.memory.forget(self.owner, self.status, {'version': self.claim(self.status)['version']})
        self.memory.forget_entity(self.owner, 'mina', {})
        self.grant('source'); self.grant('source', revoke=True)
        self.store.revoke('reader')
        result = lifecycle.restore(self.root / 'backups' / manifest['file'], self.db)
        self.assertEqual(result['journal_entries_replayed'], 4); self.assertEqual(result['integrity_check'], 'ok')
        restored = KnowledgeStore(self.db, clock=lambda: self.clock[0]); memory = ReviewedMemory(restored)
        claims = {c['id']: c for c in memory.view(self.owner)['claims']}
        self.assertEqual(claims[self.status]['state'], 'forgotten'); self.assertIsNone(claims[self.status]['value'])
        self.assertNotIn('mina', [e['id'] for e in memory.view(self.owner)['entities']])
        with self.assertRaises(Fault):
            restored.principal(self.reader)
        with restored.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM source_grants').fetchone()[0], 0)

    def test_restore_rejects_tampered_backup(self):
        manifest = lifecycle.backup(self.store, self.owner, self.root / 'backups')
        target = self.root / 'backups' / manifest['file']
        target.write_bytes(target.read_bytes() + b'x')
        with self.assertRaises(Fault) as caught:
            lifecycle.restore(target, self.db)
        self.assertEqual(caught.exception.code, 'backup_hash_mismatch')

    def test_corrupt_journal_stops_restore_but_torn_tail_is_tolerated(self):
        manifest = lifecycle.backup(self.store, self.owner, self.root / 'backups')
        journal = lifecycle.journal_path(self.store)
        self.store.revoke('reader')
        with journal.open('a') as f: f.write('{"kind":"credential_rev')
        self.assertEqual(len(lifecycle.entries(journal)), 1)
        journal.write_text('not json\n' + journal.read_text())
        with self.assertRaises(Fault):
            lifecycle.restore(self.root / 'backups' / manifest['file'], self.db)

    def test_backup_requires_owner(self):
        with self.assertRaises(Fault):
            lifecycle.backup(self.store, self.reader, self.root / 'backups')


class LifecycleHTTPTests(unittest.TestCase):
    def setUp(self):
        from alfred.desk import init_demo
        from alfred.knowledge import KnowledgeSupervisor
        from alfred.desk_http import DeskHTTPServer
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        home = Path(self.tmp.name) / 'demo'; self.keys = init_demo(home)
        self.store = KnowledgeStore(home / 'desk.sqlite')
        sup = KnowledgeSupervisor(self.store, self.keys['owner'], self.keys['source'], home / 'project', vault=home / 'vault'); sup.cycle()
        self.server = DeskHTTPServer(self.store, sup, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), self.thread.join(3)))
        self.cookie = self.csrf = None

    def req(self, path, data=None, csrf=True):
        headers = {'Cookie': self.cookie} if self.cookie else {}
        if data is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': self.server.origin})
            if csrf and self.csrf: headers['X-CSRF-Token'] = self.csrf
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); body = json.loads(r.read()); cookie = r.getheader('Set-Cookie'); c.close()
        return r.status, body, cookie

    def login(self, role):
        code, data, cookie = self.req('/desk/login', {'key': self.keys[role]}); self.cookie = cookie.split(';')[0]; self.csrf = data['csrf']

    def test_forget_over_http_needs_csrf_and_owner(self):
        self.login('owner')
        self.req('/desk/memory/entities', {'id': 'film', 'kind': 'project', 'name': 'Sample film'})
        self.assertEqual(self.req('/desk/memory/entities/film/forget', {}, csrf=False)[0], 403)
        code, receipt, _ = self.req('/desk/memory/entities/film/forget', {})
        self.assertEqual((code, receipt['kind']), (200, 'entity_forgotten'))
        self.assertEqual(self.req('/desk/memory/receipts')[1]['receipts'][0]['id'], receipt['id'])
        self.login('reader')
        self.assertEqual(self.req('/desk/memory/entities/film/forget', {})[0], 403)


if __name__ == '__main__':
    unittest.main()
