"""Sealing stored records with the keyring's area keys (encryption step 2, part 1).

Synthetic keys and invented notes only. The whole suite also runs with every database sealed
(``python tests/sealed_suite.py``); these tests pin the sealing layer itself and check that a
sealed workspace's files hold none of the private text it was given.
"""
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from alfred import connectors, drafts, keys, lifecycle, sealing
from alfred.capture_policies import CapturePolicies
from alfred.conversation import ConversationService
from alfred.executive import ExecutiveRecords
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.local import Fault
from alfred.voice import VoiceLog
from grant_helpers import grant_all
from sealed_suite import SyntheticUnlock


def keyring(directory, *areas):
    opened, _ = keys.Keyring.create(Path(directory) / keys.KEYRING_FILE, SyntheticUnlock())
    for area in areas:
        opened.add_area(area, 'client' if area.startswith('client') else area)
    return opened


class SealerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.keyring = keyring(self.tmp.name, 'personal', 'client-1')
        self.sealer = sealing.Sealed(self.keyring)

    def tearDown(self):
        self.sealer.close()
        self.tmp.cleanup()

    def code(self, call, *args):
        with self.assertRaises(Fault) as caught:
            call(*args)
        return caught.exception.code

    def test_plain_passes_everything_through(self):
        digest = hashlib.sha256(b'x').hexdigest()
        self.assertEqual((sealing.PLAIN.seal('personal', 'Private words', 'c'), sealing.PLAIN.open('Private words', 'c'),
                          sealing.PLAIN.fingerprint('personal', digest), sealing.PLAIN.sealed),
                         ('Private words', 'Private words', digest, False))
        row = {'scope': 's', 'source': 'v', 'id': 'n1', 'body': 'Private words'}
        self.assertEqual(sealing.seal_row(sealing.PLAIN, 'knowledge_notes', 'personal', row), row)
        self.assertEqual(sealing.open_row(sealing.PLAIN, 'knowledge_notes', row), row)

    def test_seal_and_open(self):
        value = self.sealer.seal('personal', 'Private words', 'knowledge_notes/body/s/v/n1')
        self.assertTrue(value.startswith('alfred-seal:1:personal:1:'))
        self.assertNotIn('Private', value)
        self.assertEqual(sealing.area_of(value), 'personal')
        self.assertEqual(self.sealer.open(value, 'knowledge_notes/body/s/v/n1'), 'Private words')
        self.assertNotEqual(value, self.sealer.seal('personal', 'Private words', 'knowledge_notes/body/s/v/n1'))

    def test_value_opens_only_where_it_was_sealed(self):
        value = self.sealer.seal('personal', 'Private words', sealing.context('knowledge_notes', 'body', 's', 'v', 'n1'))
        for elsewhere in (sealing.context('knowledge_notes', 'body', 's', 'v', 'n2'),
                          sealing.context('knowledge_notes', 'title', 's', 'v', 'n1'),
                          sealing.context('knowledge_notes', 'body', 'other', 'v', 'n1')):
            self.assertEqual(self.code(self.sealer.open, value, elsewhere), 'seal_does_not_match')

    def test_empty_and_refused_values(self):
        self.assertIsNone(self.sealer.seal('personal', None, 'c'))
        self.assertIsNone(self.sealer.open(None, 'c'))
        self.assertEqual(self.sealer.open(self.sealer.seal('personal', '', 'c'), 'c'), '')
        self.assertEqual(self.code(self.sealer.seal, 'personal', b'bytes', 'c'), 'invalid_sealed_value')
        self.assertEqual(self.code(self.sealer.seal, 'unknown', 'text', 'c'), 'unknown_area')
        for plain in ('Private words', 'a:b:c:d:e', 'alfred-seal:1:personal:x:abc'):
            self.assertEqual(self.code(self.sealer.open, plain, 'c'), 'not_sealed')
        self.assertIsNone(sealing.area_of('Private words'))

    def test_fingerprints_are_keyed_per_area_and_survive_rotation(self):
        digest = hashlib.sha256('Private words'.encode()).hexdigest()
        personal = self.sealer.fingerprint('personal', digest)
        self.assertRegex(personal, r'^[0-9a-f]{64}$')
        self.assertNotEqual(personal, digest)
        self.assertEqual(personal, self.sealer.fingerprint('personal', digest))
        self.assertNotEqual(personal, self.sealer.fingerprint('client-1', digest))
        self.keyring.rotate_area('personal')
        self.assertEqual(sealing.Sealed(self.keyring).fingerprint('personal', digest), personal)
        for bad in ('abc', digest.upper(), None, 'g' * 64):
            self.assertEqual(self.code(self.sealer.fingerprint, 'personal', bad), 'invalid_digest')

    def test_destroying_one_area_leaves_the_others(self):
        personal = self.sealer.seal('personal', 'Personal words', 'c')
        client = self.sealer.seal('client-1', 'Client words', 'c')
        self.keyring.destroy_area('client-1')
        self.assertEqual(self.sealer.open(personal, 'c'), 'Personal words')
        self.assertEqual(self.code(self.sealer.open, client, 'c'), 'area_destroyed')
        self.assertEqual(sealing.area_of(self.sealer.seal('personal', 'More', 'c')), 'personal')

    def test_destroyed_area_stops_opening_even_from_the_cache(self):
        value = self.sealer.seal('client-1', 'Client words', 'c')
        digest = hashlib.sha256(b'Client words').hexdigest()
        self.assertEqual(self.sealer.open(value, 'c'), 'Client words')
        self.sealer.fingerprint('client-1', digest)
        self.keyring.destroy_area('client-1')
        self.assertEqual(self.code(self.sealer.open, value, 'c'), 'area_destroyed')
        self.assertEqual(self.code(self.sealer.fingerprint, 'client-1', digest), 'area_destroyed')
        self.assertEqual(self.code(self.sealer.seal, 'client-1', 'More', 'c'), 'area_destroyed')

    def test_cache_is_bounded_and_close_forgets(self):
        small = sealing.Sealed(self.keyring, cache_bytes=4000)
        values = [small.seal('personal', f'note {n} ' + 'x' * 300, f'c{n}') for n in range(30)]
        for n, value in enumerate(values):
            self.assertEqual(small.open(value, f'c{n}'), f'note {n} ' + 'x' * 300)
        self.assertLessEqual(small._cached, 4000)
        self.assertLess(len(small._cache), 30)
        # Each entry counts the bytes of its sealed value, its text and its context.
        self.assertEqual(small._cached, sum(size for _, size in small._cache.values()))
        for (value, where), (text, size) in small._cache.items():
            self.assertEqual(size, len(value) + len(text.encode()) + len(where.encode()))
        small.clear_cache()
        self.assertEqual((len(small._cache), small._cached), (0, 0))
        self.assertEqual(small.open(values[-1], 'c29'), 'note 29 ' + 'x' * 300)
        small.close()
        self.assertEqual((len(small._cache), small._cached), (0, 0))
        self.assertEqual(self.code(small.open, values[0], 'c0'), 'keyring_closed')

    def test_rows_seal_and_open_by_register(self):
        row = {'scope': 's', 'source': 'v', 'id': 'n1', 'path': 'Folder/Note.md', 'title': 'Note',
               'tags': '[]', 'aliases': '[]', 'body': 'Private words', 'sha256': 'not sealed here', 'revision': 1}
        sealed = sealing.seal_row(self.sealer, 'knowledge_notes', 'personal', row)
        for column in ('path', 'title', 'tags', 'aliases', 'body'):
            self.assertEqual(sealing.area_of(sealed[column]), 'personal')
        self.assertEqual({k: sealed[k] for k in ('scope', 'source', 'id', 'sha256', 'revision')},
                         {k: row[k] for k in ('scope', 'source', 'id', 'sha256', 'revision')})
        self.assertEqual(sealing.open_row(self.sealer, 'knowledge_notes', sealed), row)
        moved = dict(sealed, id='n2')
        with self.assertRaises(Fault):
            sealing.open_row(self.sealer, 'knowledge_notes', moved)
        self.assertIsNone(sealing.open_row(self.sealer, 'knowledge_notes', None))

    def test_unchanged_text_keeps_its_stored_value(self):
        row = {'scope': 's', 'source': 'v', 'id': 'n1', 'path': 'Note.md', 'title': 'Note',
               'tags': '[]', 'aliases': '[]', 'body': 'Private words'}
        stored = sealing.seal_row(self.sealer, 'knowledge_notes', 'personal', row)
        again = sealing.seal_row(self.sealer, 'knowledge_notes', 'personal', row, stored)
        self.assertEqual(again, stored)
        edited = sealing.seal_row(self.sealer, 'knowledge_notes', 'personal', dict(row, body='Other words'), stored)
        self.assertEqual({k for k in row if edited[k] != stored[k]}, {'body'})
        # A value kept under another area is sealed again under the row's area.
        moved = sealing.seal_row(self.sealer, 'knowledge_notes', 'client-1', row, stored)
        self.assertEqual({sealing.area_of(moved[k]) for k in ('path', 'title', 'tags', 'aliases', 'body')}, {'client-1'})
        # A stored value that does not belong to the row is refused rather than kept.
        with self.assertRaises(Fault):
            sealing.seal_row(self.sealer, 'knowledge_notes', 'personal', dict(row, id='n2'), stored)

    def test_register_names_real_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            store = KnowledgeStore(Path(directory) / 'db.sqlite')
            connectors.initialise(store)
            CapturePolicies(store)
            ConversationService(store), ExecutiveRecords(store), VoiceLog(store)
            with store.transaction() as db:
                drafts.ensure(db)
            with closing(sqlite3.connect(Path(directory) / 'db.sqlite')) as db:
                for table, (names, sealed, fingerprints) in sealing.TABLES.items():
                    info = list(db.execute(f'PRAGMA table_info({table})'))
                    columns = {row[1] for row in info}
                    self.assertTrue(columns, table)
                    self.assertLessEqual(set(names + sealed + fingerprints), columns, table)
                    self.assertFalse(set(names) & set(sealed), table)
                    # A row's context names every plain part of its key, so a sealed value cannot
                    # be moved to another row with the same context.
                    key = {row[1] for row in info if row[5]}
                    self.assertLessEqual(key - set(sealed), set(names), table)
                for table, keyed in sealing.KEYED_IDS.items():
                    columns = {row[1] for row in db.execute(f'PRAGMA table_info({table})')}
                    self.assertLessEqual(set(keyed), columns, table)


class AttachAndCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / 'db.sqlite'
        (self.root / 'one').mkdir()
        self.keyring = keyring(self.root / 'one', 'personal')

    def tearDown(self):
        sealing.detach(self.path)
        self.tmp.cleanup()

    def store(self, sealer):
        sealing.attach(self.path, sealer)
        return KnowledgeStore(self.path)

    def code(self, sealer):
        with self.assertRaises(Fault) as caught:
            self.store(sealer)
        return caught.exception.code, caught.exception.status

    def test_attach_finds_by_path(self):
        sealer = sealing.Sealed(self.keyring)
        sealing.attach(self.root / 'one' / '..' / '.' / 'db.sqlite', sealer)
        (self.root / 'link').symlink_to(self.root, target_is_directory=True)
        for spelling in (self.path, self.root / 'link' / 'db.sqlite', str(self.path)):
            self.assertIs(sealing.for_path(spelling), sealer)
        sealing.detach(self.root / 'link' / 'db.sqlite')
        self.assertIsNot(sealing.for_path(self.path), sealer)
        self.assertEqual(self.keyring._master, None)

    def test_new_workspace_is_marked_sealed(self):
        store = self.store(sealing.Sealed(self.keyring))
        self.assertTrue(store.sealer.sealed)
        with store.connection() as db:
            self.assertIs(sealing.of(db), store.sealer)
            self.assertEqual([tuple(r)[:2] for r in db.execute('SELECT keyring, default_area FROM sealing')],
                             [(self.keyring.id, 'personal')])
            self.assertEqual(sealing.default_area(db), 'personal')

    def test_sealed_workspace_refuses_without_its_keyring(self):
        self.store(sealing.Sealed(self.keyring))
        self.assertEqual(self.code(sealing.PLAIN), ('workspace_locked', 423))
        (self.root / 'two').mkdir()
        other = sealing.Sealed(keyring(self.root / 'two', 'personal'))
        self.assertEqual(self.code(other), ('wrong_keyring', 409))

    def test_plain_workspace_in_use_is_not_sealed_by_attaching(self):
        store = self.store(sealing.PLAIN)
        store.provision('work', 'owner', 'owner')
        self.assertEqual(self.code(sealing.Sealed(self.keyring)), ('workspace_not_sealed', 409))

    def test_damaged_sealing_record_refused(self):
        self.store(sealing.Sealed(self.keyring))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("INSERT INTO sealing VALUES ('another', 'personal', 1)")
        self.assertEqual(self.code(sealing.Sealed(self.keyring)), ('sealing_record_damaged', 409))

    def test_lost_sealing_record_refused_when_sealed_values_remain(self):
        store = self.store(sealing.Sealed(self.keyring))
        source = store.provision('work', 'source', 'source')
        store.knowledge_unavailable(source, 'vault_missing')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DELETE FROM sealing')
        # Neither a plain store nor a sealed one may carry on beside sealed values.
        self.assertEqual(self.code(sealing.PLAIN), ('sealing_record_damaged', 409))
        self.assertEqual(self.code(sealing.Sealed(self.keyring)), ('sealing_record_damaged', 409))

    def test_plain_connection_has_plain_sealer(self):
        with closing(sqlite3.connect(':memory:')) as db:
            self.assertIs(sealing.of(db), sealing.PLAIN)


# Words that appear only in the invented vault, so finding one in a file means it leaked.
PRIVATE = ('Zanzibar', 'Quillfeather', 'Marrowgate', 'Thistledown', 'Brackenfold', 'Corvinia',
           'Halloway', 'Peregrine', 'Wintermere', 'Vellichor')


class SealedAtRestTests(unittest.TestCase):
    """A sealed workspace's database, write-ahead log and shared memory hold none of the
    private words, paths or plain fingerprints of the notes it indexed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / 'db.sqlite'
        self.keyring = keyring(self.root, 'personal')
        sealing.attach(self.path, sealing.Sealed(self.keyring))
        self.store = KnowledgeStore(self.path)
        self.owner = self.store.provision('work', 'owner', 'owner')
        self.source = self.store.provision('work', 'source', 'source')
        grant_all(self.store, self.owner)
        self.vault = self.root / 'vault'
        self.files = {
            'MAP.md': '# Map\n[[Marrowgate plan]]\n[[Thistledown/Notes]]',
            'Marrowgate plan.md': '---\nalfred_id: brackenfold-1\ntags: [corvinia]\naliases: [Halloway]\n---\n'
                                  '# Marrowgate plan\nMeet Peregrine about Zanzibar.\n## Wintermere\n[[Missing Vellichor]]',
            'Thistledown/Notes.md': '# Thistledown\nA quiet note.',
        }
        for name, body in self.files.items():
            self.write(name, body)
        self.reader = MarkdownVault(self.store, self.source, self.vault, label='Quillfeather vault',
                                    exclude_folders=('Corvinia archive',), id_key='alfred_id')
        self.reader.scan()

    def write(self, name, body):
        (self.vault / name).parent.mkdir(parents=True, exist_ok=True)
        (self.vault / name).write_text(body, encoding='utf-8')
        self.files[name] = body

    def tearDown(self):
        sealing.detach(self.path)
        self.tmp.cleanup()

    def stored_bytes(self):
        found = b''
        for suffix in ('', '-wal', '-shm', '-journal', lifecycle.JOURNAL_SUFFIX):
            part = Path(str(self.path) + suffix)
            if part.exists():
                found += part.read_bytes()
        return found

    def test_answers_still_work_sealed(self):
        data = self.store.knowledge(self.owner, 'zanzibar')
        self.assertEqual([r['title'] for r in data['results']], ['Marrowgate plan'])
        note = next(n for n in self.store.knowledge(self.owner)['nodes'] if n['title'] == 'Marrowgate plan')
        self.assertEqual(note['path'], 'Marrowgate plan.md')
        self.assertIn('Meet Peregrine about Zanzibar.', self.store.knowledge_note(self.owner, note['id'])['body'])
        self.assertEqual([i['target'] for i in self.store.knowledge(self.owner)['issues']], ['Missing Vellichor'])

    def assert_nothing_plain(self, *paths, holding=True):
        raw = self.stored_bytes()
        # assertFalse rather than assertNotIn, so a failure names the leak without printing the file.
        leaked = [form for word in PRIVATE + tuple(self.files) + paths for form in {word, word.lower(), word.upper()}
                  if form.encode('utf-8') in raw]
        self.assertFalse(leaked, f'private text in the stored files: {leaked}')
        # Plain SHA-256 of any note's text, path or id, whole or as the short forms kept in logs.
        texts = [*self.files.values(), *self.files, *paths, 'brackenfold-1']
        texts += ['source\0' + text for text in (*self.files, *paths)]
        digests = [hashlib.sha256(text.encode('utf-8')).hexdigest() for text in texts]
        found = [d[:n] for d in digests for n in (16, 24, 64) if d[:n].encode() in raw]
        self.assertFalse(found, 'plain fingerprints in the stored files')
        if holding:
            self.assertTrue(b'alfred-seal:1:personal:' in raw)

    def sealed_values(self):
        with self.store.connection() as db:
            return {(table, column, *(row[n] for n in names), *([row['revision']] if table == 'knowledge_history' else [])):
                    row[column]
                    for table, (names, sealed, _) in sealing.TABLES.items() if sealing._has(db, table)
                    for row in db.execute(f'SELECT * FROM {table}') for column in sealed if row[column] is not None}

    def counting_seals(self):
        sealed, real = [], self.keyring.seal

        def seal(area, plaintext, where):
            sealed.append(where)
            return real(area, plaintext, where)
        self.keyring.seal = seal
        self.addCleanup(lambda: vars(self.keyring).pop('seal', None))
        return sealed

    def test_no_private_text_or_plain_fingerprint_at_rest(self):
        self.store.knowledge(self.owner, 'zanzibar')
        self.assert_nothing_plain()

    def test_unchanged_rescan_seals_nothing_and_an_edit_seals_only_its_note(self):
        before = self.sealed_values()
        sealed = self.counting_seals()
        self.reader.scan()
        self.assertEqual(sealed, [])
        self.assertEqual(self.sealed_values(), before)
        note = next(n for n in self.store.knowledge(self.owner)['nodes'] if n['path'] == 'Thistledown/Notes.md')
        self.write('Thistledown/Notes.md', '# Thistledown\nA quiet note, now longer.')
        self.reader.scan()
        # The edited body and the new revision's history path; nothing else is sealed again.
        self.assertEqual(sorted(where.split('/')[:2] for where in sealed),
                         [['knowledge_history', 'path'], ['knowledge_notes', 'body']])
        self.assertTrue(all(note['id'] in where.split('/') for where in sealed))
        after = self.sealed_values()
        changed = {key for key in before if after.get(key) != before[key]}
        self.assertEqual(changed, {('knowledge_notes', 'body', *key[2:]) for key in changed})
        self.assertEqual(len(changed), 1)

    def test_renames_conflicts_errors_and_forgetting_leave_nothing_plain(self):
        (self.vault / 'Thistledown/Notes.md').rename(self.vault / 'Thistledown/Wintermere notes.md')
        renamed = self.files.pop('Thistledown/Notes.md')
        self.write('Thistledown/Wintermere notes.md', renamed)
        self.write("Marrowgate plan (Halloway's conflicted copy 2026-10-17).md", 'Zanzibar by Peregrine, edited elsewhere.')
        (self.vault / 'Vellichor shortcut.md').symlink_to(self.vault / 'MAP.md')
        self.reader.scan()
        data = self.store.knowledge(self.owner)
        self.assertIn('Thistledown/Wintermere notes.md', [n['path'] for n in data['nodes']])
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM knowledge_conflicts').fetchone()[0], 1)
            errors = self.store.opened('knowledge_sources', db.execute('SELECT * FROM knowledge_sources').fetchone())['errors']
        self.assertIn('Vellichor shortcut.md', errors)
        self.assert_nothing_plain('Thistledown/Notes.md', 'Vellichor shortcut.md')

        receipt = lifecycle.forget_source(self.store, self.owner, 'source')
        self.assertEqual(receipt['notes_removed'], 3)
        with self.store.connection() as db:
            tombstones = [r[0] for r in db.execute('SELECT * FROM memory_tombstones')]
            self.assertEqual(db.execute('SELECT count(*) FROM knowledge_notes').fetchone()[0], 0)
        self.assertEqual(len(tombstones), 3)
        self.assertEqual(self.store.sealer._cache, {})
        self.assert_nothing_plain('Thistledown/Notes.md', 'Vellichor shortcut.md', holding=False)

    def test_a_value_moved_to_another_note_does_not_open(self):
        with self.store.connection() as db:
            rows = db.execute('SELECT id, body FROM knowledge_notes ORDER BY id').fetchall()
            db.execute('UPDATE knowledge_notes SET body=? WHERE id=?', (rows[0]['body'], rows[1]['id']))
        with self.assertRaises(Fault) as caught:
            self.store.knowledge(self.owner)
        self.assertEqual(caught.exception.code, 'seal_does_not_match')

    def test_lost_sealing_record_is_refused(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DELETE FROM sealing')
        with self.assertRaises(Fault) as caught:
            KnowledgeStore(self.path)
        self.assertEqual(caught.exception.code, 'sealing_record_damaged')

    def test_destroying_the_area_erases_the_index(self):
        self.store.knowledge(self.owner, 'zanzibar')
        self.keyring.destroy_area('personal')
        with self.assertRaises(Fault) as caught:
            self.store.knowledge(self.owner)
        self.assertEqual((caught.exception.code, caught.exception.status), ('area_destroyed', 410))


if __name__ == '__main__':
    unittest.main()
