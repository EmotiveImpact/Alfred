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
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=100000, legacy_scope=True)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=100000, legacy_scope=True)
        self.source = self.store.provision('work', 'source', 'source', ttl=100000, legacy_scope=True)
        self.other = self.store.provision('work', 'other', 'source', ttl=100000, legacy_scope=True)
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
        self.assertEqual(result['journal_entries_replayed'], 5); self.assertEqual(result['integrity_check'], 'ok')
        self.assertIn('policy_strict',{e['kind'] for e in lifecycle.entries(lifecycle.journal_path(self.store))})
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

    def test_corrupt_or_torn_journal_stops_restore_without_dropping_intent(self):
        manifest = lifecycle.backup(self.store, self.owner, self.root / 'backups')
        journal = lifecycle.journal_path(self.store)
        self.store.revoke('reader')
        with journal.open('a') as f: f.write('{"kind":"credential_rev')
        with self.assertRaises(Fault):
            lifecycle.entries(journal)
        journal.write_text('not json\n' + journal.read_text())
        with self.assertRaises(Fault):
            lifecycle.restore(self.root / 'backups' / manifest['file'], self.db)

    def test_backup_requires_owner(self):
        with self.assertRaises(Fault):
            lifecycle.backup(self.store, self.reader, self.root / 'backups')

    def test_restart_replays_a_durable_forget_before_reads(self):
        lifecycle.append(self.store,{'kind':'claim_forgotten','scope':'work','actor':'owner',
                                     'subject':self.status,'at':self.store.now()})
        # Simulate termination after the intent fsync and before its DB commit.
        restarted=KnowledgeStore(self.db,clock=lambda:1000)
        view=ReviewedMemory(restarted).view(self.owner)
        claim=next(c for c in view['claims'] if c['id']==self.status)
        self.assertEqual((claim['state'],claim['value']),('forgotten',None))

    def test_restore_before_strict_transition_cannot_revive_legacy_read(self):
        manifest=lifecycle.backup(self.store,self.owner,self.root/'backups')
        self.grant('source')
        self.grant('source',revoke=True)
        lifecycle.restore(self.root/'backups'/manifest['file'],self.db)
        restarted=KnowledgeStore(self.db,clock=lambda:1000)
        self.assertEqual(IdentityPolicy(restarted).view(self.owner)['mode'],'explicit_grants')
        self.assertEqual(restarted.knowledge(self.owner)['nodes'],[])


class SourceForgetTests(LifecycleTests):
    """Removing a whole source: its content and everything derived from it, with a receipt."""

    def answer_and_job(self):
        from alfred.jobs import BoundedCache, JobCoordinator, JobWorker, LocalSubprocessBackend
        service = ConversationService(self.store, None, 'work'); self.addCleanup(service.stop)
        sid = service.create(self.owner, {'title': 'Atlas'})['id']
        service.submit(self.owner, sid, {'question': 'What is the Atlas status?', 'mode': 'sources', 'follow_up': False, 'request_id': 'q1', 'after': 0})
        service.process_one()
        turn = service.view(self.owner, sid)['turns'][0]
        draft = service.propose_draft(self.owner, sid, {'turn_id': turn['id'], 'text': 'Atlas update.', 'request_id': 'draft-1'})
        cache = BoundedCache(self.root / 'job-cache', 1 << 20)
        jobs = JobCoordinator(self.store, cache=cache)
        jobs.enrol_worker(self.owner, 'local-1', 'Local worker', ['summarise_lines'])
        job = jobs.submit(self.owner, {'idempotency_key': 'j1', 'kind': 'summarise_lines', 'parameters': {'max_lines': 2},
                                       'inputs': [{'note': self.note()['id']}], 'side_effect_free': True})
        JobWorker(jobs, LocalSubprocessBackend(wall_clock=10), self.owner, 'local-1').run_once()
        result = jobs.view(self.owner, job['id'])['result']['sha256']
        jobs.artefact(self.owner, result)  # Mirrors the result into the cache.
        return service, sid, draft, jobs, cache, job, result

    def test_forgetting_a_source_removes_its_content_and_dependants(self):
        service, sid, draft, jobs, cache, job, result = self.answer_and_job()
        self.assertTrue(cache.contains(result))
        receipt = lifecycle.forget_source(self.store, self.owner, 'source', cache=cache)
        self.assertEqual((receipt['kind'], receipt['notes_removed'], receipt['reviewed_statements_invalidated']), ('source_forgotten', 1, 2))
        self.assertEqual((receipt['conversation_answers_withdrawn'], receipt['pending_actions_cancelled']), (1, [draft['id']]))
        self.assertEqual((receipt['job_results_deleted'], receipt['cached_results_removed']), ([result], 1))
        self.assertFalse(receipt['secure_erasure'])
        self.assertTrue(receipt['remains'][0].startswith('Your own files'))
        # The person's file is untouched; ALFRED holds none of its content.
        self.assertEqual((self.vault / 'Atlas.md').read_text(), '# Atlas\nAtlas is awaiting review.\nMina leads Atlas.\n')
        self.assertEqual(self.store.knowledge(self.owner)['nodes'], [])
        with self.store.connection() as db:
            for table in ('knowledge_notes', 'knowledge_history', 'knowledge_refs', 'knowledge_sources'):
                self.assertEqual(db.execute(f"SELECT count(*) FROM {table} WHERE source='source'").fetchone()[0], 0, table)
            self.assertNotIn('awaiting review', str([tuple(r) for r in db.execute('SELECT * FROM memory_claims')]))
        self.assertEqual({(c['state'], c['value']) for c in self.memory.view(self.owner)['claims']}, {('invalidated', None)})
        self.assertEqual(service.view(self.owner, sid)['turns'][0]['state'], 'source_forgotten')
        # Retain the cancelled record internally, without disclosing a removed
        # source's action ID, path or proposed content through the read API.
        self.assertEqual(self.store.desk_state(self.owner)['actions'], [])
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT state FROM actions WHERE id=?', (draft['id'],)).fetchone()[0], 'cancelled')
        self.assertFalse(cache.contains(result))
        with self.assertRaises(Fault):
            jobs.artefact(self.owner, result)
        self.assertIsNone(jobs.view(self.owner, job['id'])['result'])  # The submitter keeps the job record only.
        # The source cannot index again, and repeating the removal changes nothing.
        try:
            self.scanner.scan()
        except Fault:
            pass
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM knowledge_notes WHERE source='source'").fetchone()[0], 0)
        again = lifecycle.forget_source(self.store, self.owner, 'source', cache=cache)
        self.assertEqual((again['notes_removed'], again['reviewed_statements_invalidated']), (0, 0))

    def test_adding_the_folder_again_never_revives_old_reviews(self):
        lifecycle.forget_source(self.store, self.owner, 'source')
        fresh = self.store.provision('work', 'source-2', 'source', ttl=100000, legacy_scope=True)
        MarkdownVault(self.store, fresh, self.vault).scan()
        self.assertEqual(len(self.store.knowledge(self.owner)['nodes']), 1)
        self.assertEqual({c['state'] for c in self.memory.view(self.owner)['claims']}, {'invalidated'})

    def test_restore_replays_source_removal(self):
        manifest = lifecycle.backup(self.store, self.owner, self.root / 'backups')
        lifecycle.forget_source(self.store, self.owner, 'source')
        lifecycle.restore(self.root / 'backups' / manifest['file'], self.db)
        restored = KnowledgeStore(self.db, clock=lambda: self.clock[0])
        self.assertEqual(restored.knowledge(self.owner)['nodes'], [])
        self.assertEqual({c['state'] for c in ReviewedMemory(restored).view(self.owner)['claims']}, {'invalidated'})
        with restored.connection() as db:
            self.assertEqual(db.execute("SELECT revoked FROM credentials WHERE id='source'").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM knowledge_notes WHERE source='source'").fetchone()[0], 0)

    def test_only_an_owner_removes_a_known_source_in_their_workspace(self):
        for bearer, source, code in ((self.reader, 'source', 'forbidden'), (self.owner, 'nope', 'source_not_available'),
                                     (self.owner, 'owner', 'source_not_available')):
            with self.assertRaises(Fault) as caught:
                lifecycle.forget_source(self.store, bearer, source)
            self.assertEqual(caught.exception.code, code)
        elsewhere = self.store.provision('elsewhere', 'elsewhere-source', 'source', legacy_scope=True)
        with self.assertRaises(Fault) as caught:
            lifecycle.forget_source(self.store, self.owner, 'elsewhere-source')
        self.assertEqual(caught.exception.code, 'source_not_available')
        self.assertEqual(lifecycle.entries(lifecycle.journal_path(self.store)), [])


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

    def test_source_removal_over_http_needs_owner_csrf_and_typed_confirmation(self):
        self.login('reader')
        self.assertEqual(self.req('/desk/sources/demo-source/forget', {'confirm': 'demo-source'})[0], 403)
        self.login('owner')
        self.assertEqual(self.req('/desk/sources/demo-source/forget', {})[0], 400)
        self.assertEqual(self.req('/desk/sources/demo-source/forget', {'confirm': 'other'})[1], {'error': 'confirmation_mismatch'})
        self.assertEqual(self.req('/desk/sources/demo-source/forget', {'confirm': 'demo-source'}, csrf=False)[0], 403)
        events_before = self.store.desk_state(self.keys['owner'])['events']
        code, receipt, _ = self.req('/desk/sources/demo-source/forget', {'confirm': 'demo-source'})
        self.assertEqual((code, receipt['kind'], receipt['notes_removed']), (200, 'source_forgotten', 20))
        self.assertEqual(receipt['evidence_events_redacted'], len(events_before))
        self.assertTrue(all(e['summary'] == lifecycle.REMOVED for e in self.store.desk_state(self.keys['owner'])['events']))
        self.assertEqual(self.req('/desk/console/projection')[1]['counts']['notes'], 0)
        self.assertEqual(self.req('/desk/memory/receipts')[1]['receipts'][0]['id'], receipt['id'])


if __name__ == '__main__':
    unittest.main()
