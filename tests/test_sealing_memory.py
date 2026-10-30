"""Sealing reviewed memory, its bin and capture (encryption step 2, part 2).

Synthetic keys and an invented vault only. A sealed workspace keeps record names, statement
values, the bin's copies and the owner's capture rules sealed, and keeps keyed fingerprints in
place of plain SHA-256 hashes of statement text and captured lines. Each statement is in the
area of the note that supports it; a record and a capture rule are in the default area.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from alfred import export, lifecycle, sealing
from alfred.capture_policies import CapturePolicies
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.local import Fault, fingerprint
from alfred.reviewed_memory import ReviewedMemory
from grant_helpers import grant_all
from test_sealing import keyring

# Words that appear only in this invented vault and memory, so finding one in a file means it leaked.
PRIVATE = ('Fellmoor', 'Garnetvale', 'Hollowbeck', 'Ismerelda', 'Juniperhythe', 'Kestrelmoor',
           'Lindqvale', 'Mossgarden', 'Nettlecombe', 'Orrisford')
NOTE = 'Orrisford/Fellmoor brief.md'
BODY = ('# Fellmoor brief\n'
        'Garnetvale leads Fellmoor.\n'
        'Status: Fellmoor waits on Hollowbeck approval.\n'
        'Decision: Fellmoor launches with Ismerelda pricing\n'
        '- [ ] 2026-11-20 send Juniperhythe the Kestrelmoor budget\n')
DECISION = 'Decision: Fellmoor launches with Ismerelda pricing'


class ClientStore(KnowledgeStore):
    """Every source in one client area, as a folder rule (part 5) would place it."""
    def source_area(self, db, scope, source):
        return 'client-a'


class SealedMemoryBase(unittest.TestCase):
    store_class = KnowledgeStore

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'db.sqlite'
        self.keyring = keyring(self.root, 'personal', 'client-a')
        sealing.attach(self.path, sealing.Sealed(self.keyring))
        self.addCleanup(sealing.detach, self.path)
        self.clock = [1_000_000]
        self.store = self.store_class(self.path, clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=2592000)
        self.source = self.store.provision('work', 'source', 'source', ttl=2592000)
        grant_all(self.store, self.owner)
        vault = self.root / 'vault'
        (vault / 'Orrisford').mkdir(parents=True)
        (vault / NOTE).write_text(BODY, encoding='utf-8')
        MarkdownVault(self.store, self.source, vault).scan()
        self.note = self.store.knowledge(self.owner)['nodes'][0]
        self.memory = ReviewedMemory(self.store)
        for identity, kind, name in (('e1', 'project', 'Fellmoor'), ('e2', 'person', 'Garnetvale'),
                                     ('e3', 'person', 'Lindqvale')):
            self.memory.create_entity(self.owner, {'id': identity, 'kind': kind, 'name': name})
        self.bodies = []
        self.status = self.accept('r1', 'status', 3, value='waits on Hollowbeck approval')
        self.lead = self.accept('r2', 'responsible_person', 2, obj='e2')
        self.other = self.accept('r3', 'responsible_person', 2, obj='e3', subject='e2')
        statement = self.statement('r4', 'scheduled_for', 5, value='send Juniperhythe the Kestrelmoor budget')
        self.captured = self.memory.capture(self.owner, {**statement, 'memory_type': 'commitment', 'retention_days': 30,
                                                         'captured_from': {'turn_id': 'turn-1'}})['id']
        self.capture = CapturePolicies(self.store, memory=self.memory)
        self.policy = {'version': 0, 'name': 'Nettlecombe decisions', 'enabled': True, 'context': 'client',
                       'match': {'kind': 'line_prefix', 'prefix': 'Decision:'}, 'sources': ['source'],
                       'path_prefix': 'Orrisford/', 'daily_budget': 10,
                       'proposes': {'subject_id': 'e1', 'predicate': 'decision', 'memory_type': 'semantic', 'retention_days': None}}
        self.capture.author(self.owner, 'rule-1', self.policy)
        self.proposed = self.capture.run(self.owner)['proposed']
        # Into the bin: one statement, and one record with the statement that names it.
        self.memory.forget(self.owner, self.status, {'version': self.claim(self.status)['version']})
        self.memory.forget_entity(self.owner, 'e3', {})

    def statement(self, request, predicate, line, value=None, obj=None, subject='e1'):
        body = {'request_id': request, 'subject_id': subject, 'predicate': predicate, 'object_id': obj,
                'value': value, 'valid_from': None, 'valid_until': None,
                'evidence': {'note_id': self.note['id'], 'sha256': self.note['sha256'], 'revision': self.note['revision'],
                             'start_line': line, 'end_line': line}}
        self.bodies.append(body)
        return body

    def accept(self, request, predicate, line, **kw):
        made = self.memory.propose(self.owner, self.statement(request, predicate, line, **kw))
        self.memory.review(self.owner, made['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        return made['id']

    def claim(self, identity):
        return next(c for c in self.memory.view(self.owner)['claims'] if c['id'] == identity)

    def stored_bytes(self):
        found = b''
        for suffix in ('', '-wal', '-shm', '-journal', lifecycle.JOURNAL_SUFFIX):
            part = Path(str(self.path) + suffix)
            if part.exists():
                found += part.read_bytes()
        return found

    def raw(self, sql, params=()):
        with self.store.connection() as db:
            return [dict(r) for r in db.execute(sql, params)]

    def counting_seals(self):
        sealed, real = [], self.keyring.seal

        def seal(area, plaintext, where):
            sealed.append(where)
            return real(area, plaintext, where)
        self.keyring.seal = seal
        self.addCleanup(lambda: vars(self.keyring).pop('seal', None))
        return sealed


class SealedMemoryAtRestTests(SealedMemoryBase):
    def test_answers_still_open_sealed(self):
        # What follows is read from sealed values, not from text kept plain beside them.
        stored = self.raw('SELECT name FROM memory_entities') + self.raw('SELECT value AS name FROM memory_claims WHERE value IS NOT NULL')
        self.assertTrue(stored and all(r['name'].startswith('alfred-seal:1:') for r in stored))
        view = self.memory.view(self.owner)
        self.assertEqual(sorted(e['name'] for e in view['entities']), ['Fellmoor', 'Garnetvale'])
        self.assertEqual(self.claim(self.captured)['value'], 'send Juniperhythe the Kestrelmoor budget')
        self.assertEqual(self.claim(self.captured)['memory_type'], 'commitment')
        decision = self.claim(self.proposed[0]['claim_id'])
        self.assertEqual((decision['value'], decision['state']), ('Fellmoor launches with Ismerelda pricing', 'proposed'))
        items = {i['kind']: i for i in self.memory.bin(self.owner)['items']}
        self.assertEqual(items['statement']['label'], {'subject': 'Fellmoor', 'predicate': 'status',
                                                       'value': 'waits on Hollowbeck approval', 'object': None})
        self.assertEqual(items['entity']['label'], {'name': 'Lindqvale', 'kind': 'person', 'statements': 1})
        policy = self.capture.view(self.owner)['policies'][0]
        self.assertEqual((policy['name'], policy['path_prefix'], policy['match']['prefix']),
                         ('Nettlecombe decisions', 'Orrisford/', 'Decision:'))
        self.assertIn('"Fellmoor decision ..."', policy['description'])
        captures = export.collect(self.store, self.owner)['captures']
        self.assertEqual([c['captured_from'] for c in captures if c['statement_id'] == self.captured], [{'turn_id': 'turn-1'}])
        # A rescan offers the decision line once, which needs its keyed hash to match.
        self.assertEqual(self.capture.run(self.owner)['not_proposed']['already_proposed'], 1)
        # Undo puts back what each forget cleared, with its text.
        for item in sorted(items.values(), key=lambda i: i['kind'] != 'entity'):
            self.memory.undo(self.owner, item['id'], {})
        self.assertEqual(self.claim(self.status)['value'], 'waits on Hollowbeck approval')
        self.assertIn('Lindqvale', [e['name'] for e in self.memory.view(self.owner)['entities']])
        self.assertEqual(self.claim(self.other)['state'], 'accepted')

    def test_no_private_text_or_plain_fingerprint_at_rest(self):
        self.memory.view(self.owner)
        raw = self.stored_bytes()
        leaked = [form for word in PRIVATE + (DECISION, NOTE) for form in {word, word.lower(), word.upper()}
                  if form.encode('utf-8') in raw]
        self.assertFalse(leaked, f'private text in the stored files: {leaked}')
        plain = [fingerprint(body) for body in self.bodies]
        line = hashlib.sha256(DECISION.encode()).hexdigest()
        plain += [line, hashlib.sha256(f'{self.note["id"]}|{line}'.encode()).hexdigest()[:32],
                  hashlib.sha256(f'rule-1|{self.note["id"]}|{self.note["revision"]}|4|{line}'.encode()).hexdigest()[:40]]
        plain += [hashlib.sha256(text.encode()).hexdigest() for text in (*PRIVATE, *BODY.splitlines(), 'Nettlecombe decisions')]
        found = [d[:n] for d in plain for n in (16, 24, 32, 40, 64) if d[:n].encode() in raw]
        self.assertFalse(found, 'plain fingerprints in the stored files')
        for table in ('memory_entities', 'memory_claims', 'memory_capture', 'memory_bin', 'capture_policies'):
            column = sealing.TABLES[table][1][0]
            self.assertTrue(any(str(r[column]).startswith('alfred-seal:1:') for r in self.raw(f'SELECT {column} FROM {table}')), table)

    def test_reading_seals_nothing_and_an_unchanged_rule_keeps_its_sealed_text(self):
        before = self.raw('SELECT name, rule FROM capture_policies')
        sealed = self.counting_seals()
        self.memory.view(self.owner)
        self.memory.bin(self.owner)
        self.capture.view(self.owner)
        export.collect(self.store, self.owner)
        self.assertEqual(sealed, [])
        self.capture.author(self.owner, 'rule-1', dict(self.policy, version=1, enabled=False))
        self.assertEqual(sealed, [])
        self.assertEqual(self.raw('SELECT name, rule FROM capture_policies'), before)
        self.capture.author(self.owner, 'rule-1', dict(self.policy, version=2, name='Nettlecombe calls'))
        self.assertEqual([where.split('/')[:2] for where in sealed], [['capture_policies', 'name']])

    def test_a_value_moved_to_another_row_does_not_open(self):
        with self.store.connection() as db:
            value = db.execute('SELECT value FROM memory_claims WHERE id=?', (self.captured,)).fetchone()[0]
            db.execute('UPDATE memory_claims SET value=? WHERE id=?', (value, self.proposed[0]['claim_id']))
        with self.assertRaises(Fault) as caught:
            self.memory.view(self.owner)
        self.assertEqual(caught.exception.code, 'seal_does_not_match')

    def test_a_bin_copy_moved_to_another_row_does_not_open(self):
        with self.store.connection() as db:
            rows = db.execute('SELECT id, snapshot FROM memory_bin ORDER BY id').fetchall()
            db.execute('UPDATE memory_bin SET snapshot=? WHERE id=?', (rows[0]['snapshot'], rows[1]['id']))
        with self.assertRaises(Fault) as caught:
            self.memory.bin(self.owner)
        self.assertEqual(caught.exception.code, 'seal_does_not_match')

    def test_destroying_the_area_erases_reviewed_memory_and_the_bin(self):
        self.keyring.destroy_area('personal')
        for call in (lambda: self.memory.view(self.owner), lambda: self.memory.bin(self.owner),
                     lambda: self.capture.view(self.owner)):
            with self.assertRaises(Fault) as caught:
                call()
            self.assertEqual((caught.exception.code, caught.exception.status), ('area_destroyed', 410))


class StatementAreaTests(SealedMemoryBase):
    """A statement, its capture and its bin copy follow the area of the note that supports it."""
    store_class = ClientStore

    def area(self, value):
        return sealing.area_of(value)

    def test_statements_follow_their_note_and_records_stay_in_the_default_area(self):
        self.assertEqual({self.area(r['path']) for r in self.raw('SELECT path FROM knowledge_notes')}, {'client-a'})
        claims = self.raw('SELECT id, value, request_hash, request_id FROM memory_claims')
        self.assertEqual({self.area(c['value']) for c in claims if c['value'] is not None}, {'client-a'})
        sealer = self.store.sealer
        by_request = {c['request_id']: c['request_hash'] for c in claims}
        for body in self.bodies:
            self.assertEqual(by_request[body['request_id']], sealer.fingerprint('client-a', fingerprint(body)))
        self.assertEqual({self.area(r['captured_from']) for r in self.raw('SELECT captured_from FROM memory_capture')}, {'client-a'})
        line = hashlib.sha256(DECISION.encode()).hexdigest()
        self.assertEqual([r['line_hash'] for r in self.raw('SELECT line_hash FROM capture_proposals')],
                         [sealer.fingerprint('client-a', line)])
        self.assertEqual({self.area(r['name']) for r in self.raw('SELECT name FROM memory_entities')}, {'personal'})
        self.assertEqual({self.area(r['name']) for r in self.raw('SELECT name FROM capture_policies')}, {'personal'})
        self.assertEqual({r['kind']: self.area(r['snapshot']) for r in self.raw('SELECT kind, snapshot FROM memory_bin')},
                         {'statement': 'client-a', 'entity': 'personal'})


class RegisterTests(unittest.TestCase):
    def test_part_two_tables_are_registered(self):
        for table in ('memory_entities', 'memory_claims', 'memory_capture', 'memory_bin', 'capture_policies', 'capture_proposals'):
            self.assertIn(table, sealing.TABLES)
        self.assertEqual(sealing.TABLES['capture_proposals'][2], ('line_hash',))
        self.assertIn('request_hash', sealing.TABLES['memory_claims'][2])

    def test_a_lost_sealing_record_is_refused_when_only_memory_is_sealed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'db.sqlite'
            sealing.attach(path, sealing.Sealed(keyring(directory, 'personal')))
            try:
                store = KnowledgeStore(path)
                owner = store.provision('work', 'owner', 'owner')
                ReviewedMemory(store).create_entity(owner, {'id': 'e1', 'kind': 'person', 'name': 'Garnetvale'})
            finally:
                sealing.detach(path)
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('DELETE FROM sealing')
            with self.assertRaises(Fault) as caught:
                KnowledgeStore(path)
            self.assertEqual(caught.exception.code, 'sealing_record_damaged')


if __name__ == '__main__':
    unittest.main()
