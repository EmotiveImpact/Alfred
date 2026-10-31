"""Two layers of deleting (M05, the owner's rule of 22 October 2026).

An ordinary delete goes to a bin for 30 days, where it can be undone, and a restore from an
older backup brings it back and says so. An absolute delete is a separate action with a typed
confirmation; it skips the bin and no restore brings it back. Revocations always hold.

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
from alfred.grounded import retrieve
from alfred import deletion, lifecycle
from grant_helpers import grant_all
import stored_helpers as stored

DAY = 86400


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.clock = [1000]
        self.db = self.root / 'desk.sqlite'
        self.store = KnowledgeStore(self.db, clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=2592000)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=2592000)
        self.source = self.store.provision('work', 'source', 'source', ttl=2592000)
        with self.store.connection() as db:
            # The bin outlives the longest credential a test can provision; keep these valid past it.
            db.execute('UPDATE credentials SET expires=?', (10 ** 9,))
        grant_all(self.store, self.owner)
        self.vault = self.root / 'vault'; self.vault.mkdir()
        (self.vault / 'Atlas.md').write_text('# Atlas\nAtlas is awaiting review.\nMina leads Atlas.\n')
        MarkdownVault(self.store, self.source, self.vault).scan()
        self.memory = ReviewedMemory(self.store)
        self.memory.create_entity(self.owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas'})
        self.memory.create_entity(self.owner, {'id': 'mina', 'kind': 'person', 'name': 'Mina'})
        self.status = self.accept('s1', 'status', 2, value='awaiting review')
        self.lead = self.accept('s2', 'responsible_person', 3, obj='mina')

    def accept(self, request, predicate, line, value=None, obj=None):
        n = self.store.knowledge(self.owner)['nodes'][0]
        made = self.memory.propose(self.owner, {'request_id': request, 'subject_id': 'atlas', 'predicate': predicate, 'object_id': obj,
                                                'value': value, 'valid_from': None, 'valid_until': None,
                                                'evidence': {'note_id': n['id'], 'sha256': n['sha256'], 'revision': n['revision'],
                                                             'start_line': line, 'end_line': line}})
        self.memory.review(self.owner, made['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        return made['id']

    def claim(self, identity, memory=None):
        return next(c for c in (memory or self.memory).view(self.owner)['claims'] if c['id'] == identity)

    def forget(self, identity, **extra):
        return self.memory.forget(self.owner, identity, {'version': self.claim(identity)['version'], **extra})

    def journal(self):
        return lifecycle.entries(lifecycle.journal_path(self.store))

    def backup(self):
        return self.root / 'backups' / lifecycle.backup(self.store, self.owner, self.root / 'backups')['file']

    def restored(self):
        store = KnowledgeStore(self.db, clock=lambda: self.clock[0])
        return store, ReviewedMemory(store)

    def report(self, kind, subject):
        return deletion.report(self.store, self.owner, kind, subject)['held']


class OrdinaryDeleteTests(Base):
    def test_an_ordinary_delete_leaves_every_current_view_and_waits_in_the_bin(self):
        receipt = self.forget(self.status)
        self.assertEqual((receipt['kind'], receipt['layer'], receipt['undo_until']), ('claim_forgotten', 'ordinary', 1000 + 30 * DAY))
        self.assertEqual((self.claim(self.status)['state'], self.claim(self.status)['value']), ('forgotten', None))
        self.assertNotIn('awaiting review', json.dumps(self.memory.view(self.owner)))
        packet = retrieve(self.store, self.owner, 'What is the Atlas status awaiting review?')
        self.assertNotIn(self.status, [m['claim_id'] for m in packet['memory']])
        self.assertEqual(self.journal()[-1]['layer'], 'ordinary')
        [item] = self.memory.bin(self.owner)['items']
        self.assertEqual({k: item[k] for k in ('kind', 'subject', 'deleted', 'expires')},
                         {'kind': 'statement', 'subject': self.status, 'deleted': 1000, 'expires': 1000 + 30 * DAY})
        self.assertEqual(item['label'], {'subject': 'Atlas', 'predicate': 'status', 'value': 'awaiting review', 'object': None})
        self.assertTrue(any('bin' in line for line in receipt['remains']))
        self.assertTrue(any('restore' in line and 'back' in line for line in receipt['remains']))
        # The bin copy is counted where it is held, so the deletion report stays honest.
        self.assertEqual(self.report('statement', self.status)['bin_copies'] | {}, {**self.report('statement', self.status)['bin_copies'],
                                                                                    'count': 1, 'holding_value': 1})

    def test_undo_puts_the_statement_back_as_it_was(self):
        self.forget(self.status)
        [item] = self.memory.bin(self.owner)['items']
        self.clock[0] += 5 * DAY
        result = self.memory.undo(self.owner, item['id'], {})
        self.assertEqual((result['kind'], result['subject'], result['statements_restored']), ('statement', self.status, 1))
        back = self.claim(self.status)
        self.assertEqual((back['state'], back['value'], back['usable']), ('accepted', 'awaiting review', True))
        self.assertEqual(self.memory.bin(self.owner)['items'], [])
        self.assertEqual(self.report('statement', self.status)['bin_copies']['count'], 0)
        packet = retrieve(self.store, self.owner, 'What is the Atlas status awaiting review?')
        self.assertIn(self.status, [m['claim_id'] for m in packet['memory']])
        self.assertEqual(self.journal()[-1]['kind'], 'forget_undone')
        with self.store.connection() as db:
            last = db.execute('SELECT state,detail FROM memory_claim_history WHERE claim_id=? ORDER BY seq DESC LIMIT 1',
                              (self.status,)).fetchone()
        self.assertEqual(tuple(last), ('accepted', 'undone_from_bin'))
        with self.assertRaises(Fault) as caught:
            self.memory.undo(self.owner, item['id'], {})
        self.assertEqual(caught.exception.code, 'not_in_bin')

    def test_answers_and_drafts_a_delete_withdrew_stay_withdrawn_after_undo(self):
        from alfred.conversation import ConversationService
        service = ConversationService(self.store, None, 'work'); self.addCleanup(service.stop)
        sid = service.create(self.owner, {'title': 'Atlas'})['id']
        service.submit(self.owner, sid, {'question': 'What is the Atlas status?', 'mode': 'sources', 'follow_up': False,
                                         'request_id': 'q1', 'after': 0})
        service.process_one()
        receipt = self.forget(self.status)
        self.assertEqual(receipt['conversation_answers_withdrawn'], 1)
        result = self.memory.undo(self.owner, self.memory.bin(self.owner)['items'][0]['id'], {})
        self.assertEqual(service.view(self.owner, sid)['turns'][0]['state'], 'memory_forgotten')
        self.assertTrue(any('answers' in line for line in result['not_restored']))

    def test_the_bin_empties_after_thirty_days(self):
        self.forget(self.status)
        [item] = self.memory.bin(self.owner)['items']
        self.clock[0] += 30 * DAY
        with self.assertRaises(Fault) as caught:
            self.memory.undo(self.owner, item['id'], {})
        self.assertEqual(caught.exception.code, 'not_in_bin')
        self.assertEqual(self.memory.empty_bin(self.owner), 1)
        self.assertEqual(self.memory.bin(self.owner)['items'], [])
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM memory_bin').fetchone()[0], 0)
        self.assertEqual(self.report('statement', self.status)['bin_copies']['count'], 0)

    def test_an_entity_comes_back_with_its_name_and_statements(self):
        receipt = self.memory.forget_entity(self.owner, 'mina', {})
        self.assertEqual(receipt['layer'], 'ordinary')
        self.assertNotIn('mina', [e['id'] for e in self.memory.view(self.owner)['entities']])
        [item] = self.memory.bin(self.owner)['items']
        self.assertEqual((item['kind'], item['subject'], item['label']), ('entity', 'mina', {'name': 'Mina', 'kind': 'person', 'statements': 1}))
        result = self.memory.undo(self.owner, item['id'], {})
        self.assertEqual(result['statements_restored'], 1)
        view = self.memory.view(self.owner)
        self.assertIn({'id': 'mina', 'name': 'Mina'}, [{'id': e['id'], 'name': e['name']} for e in view['entities']])
        self.assertEqual((self.claim(self.lead)['state'], self.claim(self.lead)['object_id']), ('accepted', 'mina'))

    def test_a_statement_naming_a_record_still_forgotten_stays_in_the_bin(self):
        self.memory.forget_entity(self.owner, 'atlas', {})
        self.memory.forget_entity(self.owner, 'mina', {})
        atlas = next(i for i in self.memory.bin(self.owner)['items'] if i['subject'] == 'atlas')
        result = self.memory.undo(self.owner, atlas['id'], {})
        self.assertEqual((result['statements_restored'], result['statements_not_restored']), (1, 1))
        self.assertIn('stay in the bin', result['not_restored'][-1])
        self.assertEqual(self.claim(self.status)['state'], 'accepted')
        left = {i['kind']: i for i in self.memory.bin(self.owner)['items']}
        self.assertEqual(sorted(left), ['entity', 'statement'])
        statement = left['statement']
        self.assertEqual((statement['subject'], statement['expires']), (self.lead, atlas['expires']))
        self.assertEqual(statement['label'], {'subject': 'Atlas', 'predicate': 'responsible_person', 'value': None, 'object': 'Mina'})
        with self.assertRaises(Fault) as caught:
            self.memory.undo(self.owner, statement['id'], {})
        self.assertEqual(caught.exception.code, 'undo_record_first')
        self.memory.undo(self.owner, left['entity']['id'], {})
        self.memory.undo(self.owner, statement['id'], {})
        self.assertEqual((self.claim(self.lead)['state'], self.claim(self.lead)['object_id']), ('accepted', 'mina'))
        self.assertEqual(self.memory.bin(self.owner)['items'], [])

    def test_undo_refuses_when_its_record_is_gone_or_taken(self):
        self.forget(self.lead)
        statement = self.memory.bin(self.owner)['items'][0]['id']
        self.memory.forget_entity(self.owner, 'mina', {'absolute': True, 'confirm': 'mina'})
        # Absolutely deleting Mina also empties the bin of statements that name her.
        self.assertEqual(self.memory.bin(self.owner)['items'], [])
        with self.assertRaises(Fault) as caught:
            self.memory.undo(self.owner, statement, {})
        self.assertEqual(caught.exception.code, 'not_in_bin')
        self.memory.forget_entity(self.owner, 'atlas', {})
        atlas = self.memory.bin(self.owner)['items'][0]['id']
        self.memory.create_entity(self.owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas again'})
        with self.assertRaises(Fault) as caught:
            self.memory.undo(self.owner, atlas, {})
        self.assertEqual(caught.exception.code, 'memory_entity_id_unavailable')

    def test_only_the_owner_sees_and_empties_their_bin(self):
        self.forget(self.status)
        for call in (lambda: self.memory.bin(self.reader), lambda: self.memory.undo(self.reader, 'bin-0', {})):
            with self.assertRaises(Fault):
                call()
        other = self.store.provision('elsewhere', 'elsewhere-owner', 'owner', ttl=2592000)
        self.assertEqual(self.memory.bin(other)['items'], [])
        with self.assertRaises(Fault) as caught:
            self.memory.undo(other, self.memory.bin(self.owner)['items'][0]['id'], {})
        self.assertEqual(caught.exception.code, 'not_in_bin')

    def test_a_retention_end_skips_the_bin_and_holds_through_a_restore(self):
        with self.store.connection() as db:
            db.execute('INSERT INTO memory_capture VALUES (?,?,?,?,?)', (self.status, 'commitment', 2000, 'note', 1000))
        backup = self.backup()
        self.clock[0] = 2000
        [receipt] = self.memory.apply_retention(self.owner)
        self.assertEqual((receipt['layer'], receipt['reason']), ('absolute', 'retention_ended'))
        self.assertEqual(self.memory.bin(self.owner)['items'], [])
        lifecycle.restore(backup, self.db)
        self.assertEqual(self.claim(self.status, self.restored()[1])['state'], 'forgotten')

    def test_a_retention_end_after_the_bin_emptied_still_holds_through_a_restore(self):
        with self.store.connection() as db:
            db.execute('INSERT INTO memory_capture VALUES (?,?,?,?,?)', (self.status, 'commitment', 1000 + 90 * DAY, 'note', 1000))
        backup = self.backup()
        self.forget(self.status)
        self.clock[0] = 1000 + 31 * DAY
        self.memory.empty_bin(self.owner)
        self.assertEqual(self.memory.bin(self.owner)['items'], [])
        self.clock[0] = 1000 + 90 * DAY
        [receipt] = self.memory.apply_retention(self.owner)
        self.assertEqual((receipt['layer'], receipt['reason'], receipt['removed']), ('absolute', 'retention_ended', []))
        # Once the end is journalled as absolute, later cycles leave it alone.
        self.assertEqual(self.memory.apply_retention(self.owner), [])
        lifecycle.restore(backup, self.db)
        self.assertEqual(self.claim(self.status, self.restored()[1])['state'], 'forgotten')


class AbsoluteDeleteTests(Base):
    def test_an_absolute_delete_needs_the_id_typed_and_skips_the_bin(self):
        for body in ({'absolute': True}, {'absolute': True, 'confirm': 'something else'}):
            with self.assertRaises(Fault) as caught:
                self.forget(self.status, **body)
            self.assertEqual(caught.exception.code, 'confirmation_mismatch')
        with self.assertRaises(Fault):
            self.forget(self.status, absolute='yes', confirm=self.status)
        self.assertEqual(self.claim(self.status)['state'], 'accepted')
        receipt = self.forget(self.status, absolute=True, confirm=self.status)
        self.assertEqual((receipt['layer'], 'undo_until' in receipt), ('absolute', False))
        self.assertEqual(self.memory.bin(self.owner)['items'], [])
        self.assertEqual(self.journal()[-1]['layer'], 'absolute')
        self.assertTrue(any('restore removes it again' in line for line in receipt['remains']))

    def test_an_absolute_delete_after_an_ordinary_one_empties_the_bin(self):
        first = self.forget(self.status)
        second = self.forget(self.status, absolute=True, confirm=self.status)
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(second['layer'], 'absolute')
        self.assertEqual(self.memory.bin(self.owner)['items'], [])
        self.assertEqual([e['layer'] for e in self.journal() if e['kind'] == 'claim_forgotten'], ['ordinary', 'absolute'])
        self.assertEqual(self.forget(self.status, absolute=True, confirm=self.status)['id'], second['id'])
        self.assertEqual(self.forget(self.status)['id'], second['id'])


class RestoreTests(Base):
    def test_a_restore_brings_ordinary_deletes_back_and_lists_them(self):
        backup = self.backup()
        self.clock[0] += DAY
        self.forget(self.status)
        self.memory.forget_entity(self.owner, 'mina', {})
        result = lifecycle.restore(backup, self.db)
        came = {(c['kind'], c['subject']): c for c in result['came_back']}
        self.assertEqual(set(came), {('claim_forgotten', self.status), ('entity_forgotten', 'mina')})
        self.assertEqual(came[('claim_forgotten', self.status)]['deleted_at'], 1000 + DAY)
        self.assertEqual(came[('entity_forgotten', 'mina')]['label'], 'Mina')
        self.assertEqual(came[('claim_forgotten', self.status)]['label'], 'Atlas status')
        self.assertEqual(result['ordinary_entries_not_replayed'], 2)
        store, memory = self.restored()
        self.assertEqual((self.claim(self.status, memory)['state'], self.claim(self.status, memory)['value']), ('accepted', 'awaiting review'))
        self.assertEqual(self.claim(self.lead, memory)['state'], 'accepted')
        self.assertIn('mina', [e['id'] for e in memory.view(self.owner)['entities']])

    def test_a_restore_removes_absolute_deletes_and_revocations_again(self):
        backup = self.backup()
        self.forget(self.status, absolute=True, confirm=self.status)
        self.memory.forget_entity(self.owner, 'mina', {'absolute': True, 'confirm': 'mina'})
        self.store.revoke('reader')
        result = lifecycle.restore(backup, self.db)
        self.assertEqual(result['came_back'], [])
        store, memory = self.restored()
        self.assertEqual((self.claim(self.status, memory)['state'], self.claim(self.status, memory)['value']), ('forgotten', None))
        self.assertNotIn('mina', [e['id'] for e in memory.view(self.owner)['entities']])
        with self.assertRaises(Fault):
            store.principal(self.reader)

    def test_an_undone_delete_is_not_listed_as_coming_back(self):
        backup = self.backup()
        self.forget(self.status)
        self.memory.undo(self.owner, self.memory.bin(self.owner)['items'][0]['id'], {})
        self.assertEqual(lifecycle.restore(backup, self.db)['came_back'], [])

    def test_a_backup_taken_while_in_the_bin_loses_that_copy_when_the_delete_becomes_absolute(self):
        self.forget(self.status)
        backup = self.backup()
        self.forget(self.status, absolute=True, confirm=self.status)
        lifecycle.restore(backup, self.db)
        store, memory = self.restored()
        self.assertEqual(memory.bin(self.owner)['items'], [])
        with store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM memory_bin').fetchone()[0], 0)
        self.assertEqual(self.claim(self.status, memory)['state'], 'forgotten')

    def test_journal_entries_written_before_the_two_layers_still_hold(self):
        backup = self.backup()
        self.forget(self.status)
        journal = lifecycle.journal_path(self.store)
        lines = [json.loads(line) for line in journal.read_text().splitlines()]
        for entry in lines:
            entry.pop('layer', None)
        journal.write_text(''.join(json.dumps(e, sort_keys=True, separators=(',', ':')) + '\n' for e in lines))
        result = lifecycle.restore(backup, self.db)
        self.assertEqual(result['came_back'], [])
        self.assertEqual(self.claim(self.status, self.restored()[1])['state'], 'forgotten')

    def test_an_unknown_layer_stops_a_restore(self):
        backup = self.backup()
        self.forget(self.status)
        journal = lifecycle.journal_path(self.store)
        journal.write_text(journal.read_text().replace('"layer":"ordinary"', '"layer":"later"') + '\n')
        with self.assertRaises(Fault) as caught:
            lifecycle.restore(backup, self.db)
        self.assertEqual(caught.exception.code, 'lifecycle_journal_corrupt')


class SourceTests(Base):
    def test_removing_a_source_ordinarily_comes_back_with_a_restore(self):
        backup = self.backup()
        label = stored.rows(self.store, 'knowledge_sources', 'SELECT scope,source,label FROM knowledge_sources WHERE source=?', ('source',))[0]['label']
        receipt = lifecycle.forget_source(self.store, self.owner, 'source')
        self.assertEqual(receipt['layer'], 'ordinary')
        result = lifecycle.restore(backup, self.db)
        self.assertEqual([(c['kind'], c['subject']) for c in result['came_back']], [('source_forgotten', 'source')])
        # The list names the source as the owner knows it, opened in a sealed workspace.
        self.assertEqual(result['came_back'][0]['label'], label)
        store, _ = self.restored()
        self.assertEqual(len(store.knowledge(self.owner)['nodes']), 1)

    def test_removing_a_source_absolutely_after_ordinarily_empties_the_bin_of_its_statements(self):
        self.forget(self.status)
        lifecycle.forget_source(self.store, self.owner, 'source')
        [item] = self.memory.bin(self.owner)['items']
        receipt = lifecycle.forget_source(self.store, self.owner, 'source', absolute=True)
        self.assertEqual(receipt['bin_copies_removed'], 1)
        self.assertEqual(self.memory.bin(self.owner)['items'], [])
        with self.assertRaises(Fault) as caught:
            self.memory.undo(self.owner, item['id'], {})
        self.assertEqual(caught.exception.code, 'not_in_bin')

    def test_removing_a_source_absolutely_holds_through_a_restore(self):
        backup = self.backup()
        receipt = lifecycle.forget_source(self.store, self.owner, 'source', absolute=True)
        self.assertEqual(receipt['layer'], 'absolute')
        self.assertEqual(lifecycle.restore(backup, self.db)['came_back'], [])
        store, _ = self.restored()
        self.assertEqual(store.knowledge(self.owner)['nodes'], [])


class HTTPTests(unittest.TestCase):
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
        _, data, cookie = self.req('/desk/login', {'key': self.keys[role]}); self.cookie = cookie.split(';')[0]; self.csrf = data['csrf']

    def test_the_bin_and_undo_over_http_need_the_owner_and_csrf(self):
        self.login('owner')
        self.req('/desk/memory/entities', {'id': 'film', 'kind': 'project', 'name': 'Sample film'})
        code, receipt, _ = self.req('/desk/memory/entities/film/forget', {})
        self.assertEqual((code, receipt['layer']), (200, 'ordinary'))
        code, view, _ = self.req('/desk/memory/bin')
        [item] = view['items']
        self.assertEqual((code, item['subject']), (200, 'film'))
        self.assertEqual(self.req(f"/desk/memory/bin/{item['id']}/undo", {}, csrf=False)[0], 403)
        self.login('reader')
        self.assertEqual(self.req('/desk/memory/bin')[0], 403)
        self.assertEqual(self.req(f"/desk/memory/bin/{item['id']}/undo", {})[0], 403)
        self.login('owner')
        code, result, _ = self.req(f"/desk/memory/bin/{item['id']}/undo", {})
        self.assertEqual((code, result['subject']), (200, 'film'))
        self.assertEqual(self.req('/desk/memory/bin')[1]['items'], [])

    def test_an_absolute_delete_over_http_needs_the_id_typed(self):
        self.login('owner')
        self.req('/desk/memory/entities', {'id': 'film', 'kind': 'project', 'name': 'Sample film'})
        self.assertEqual(self.req('/desk/memory/entities/film/forget', {'absolute': True})[1], {'error': 'confirmation_mismatch'})
        code, receipt, _ = self.req('/desk/memory/entities/film/forget', {'absolute': True, 'confirm': 'film'})
        self.assertEqual((code, receipt['layer']), (200, 'absolute'))
        self.assertEqual(self.req('/desk/memory/bin')[1]['items'], [])
        code, receipt, _ = self.req('/desk/sources/demo-source/forget', {'confirm': 'demo-source', 'absolute': True})
        self.assertEqual((code, receipt['layer']), (200, 'absolute'))


if __name__ == '__main__':
    unittest.main()
