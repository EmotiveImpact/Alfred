"""MEM-012: rebuilding the knowledge index never loses source or review history.

Synthetic vault, real SQLite. The Markdown files are canonical; the note, link and anchor
tables are projections rebuilt from them and the durable catalogue.
"""
from pathlib import Path
import fcntl
import os
import shutil
import sqlite3
import tempfile
import unittest
from alfred.desk import init_demo, load_keys
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.local import Fault
from alfred.rebuild import rebuild_index
from alfred.reviewed_memory import ReviewedMemory


class RebuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'demo'; self.keys = init_demo(self.home)
        self.vault = self.home / 'vault'
        self.store = KnowledgeStore(self.home / 'desk.sqlite')
        MarkdownVault(self.store, self.keys['source'], self.vault).scan()
        self.memory = ReviewedMemory(self.store)
        self.memory.create_entity(self.owner, {'id': 'film', 'kind': 'project', 'name': 'Sample film'})
        self.memory.create_entity(self.owner, {'id': 'producer', 'kind': 'person', 'name': 'Sample producer'})
        producer = self.note('Sample producer')
        made = self.memory.propose(self.owner, {'request_id': 'r1', 'subject_id': 'film', 'predicate': 'responsible_person', 'object_id': 'producer',
                                                'value': None, 'valid_from': None, 'valid_until': None,
                                                'evidence': {'note_id': producer['id'], 'sha256': producer['sha256'], 'revision': producer['revision'],
                                                             'start_line': 8, 'end_line': 8}})
        self.memory.review(self.owner, made['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        self.claim = made['id']

    @property
    def owner(self):
        return self.keys['owner']

    def note(self, title):
        return next(n for n in self.store.knowledge(self.owner)['nodes'] if n['title'] == title)

    def state(self):
        return next(c for c in self.memory.view(self.owner)['claims'] if c['id'] == self.claim)['state']

    def rebuild(self):
        return rebuild_index(self.store, self.owner, self.keys['source'], self.vault)

    def test_a_rebuild_keeps_every_identity_revision_link_and_review(self):
        before = {n['id']: (n['path'], n['revision']) for n in self.store.knowledge(self.owner)['nodes']}
        report = self.rebuild()
        after = {n['id']: (n['path'], n['revision']) for n in self.store.knowledge(self.owner)['nodes']}
        self.assertEqual(before, after)
        self.assertEqual(report['notes']['same_identity_and_revision'], 20)
        self.assertEqual((report['notes']['new_revision'], report['notes']['no_longer_present'], report['notes']['new']), ([], [], []))
        self.assertTrue(report['links']['unchanged'])
        self.assertEqual(report['reviewed_statements']['state_changed'], [])
        self.assertEqual(self.state(), 'accepted')

    def test_an_offline_edit_is_reported_and_invalidates_exactly_what_it_should(self):
        producer = self.note('Sample producer')
        path = self.vault / producer['path']
        path.write_text(path.read_text().replace('Fictional responsibility', 'Changed responsibility'))
        report = self.rebuild()
        self.assertEqual([r['id'] for r in report['notes']['new_revision']], [producer['id']])
        self.assertEqual(report['notes']['new_revision'][0]['revision_after'], producer['revision'] + 1)
        self.assertEqual(report['reviewed_statements']['state_changed'], [{'id': self.claim, 'before': 'accepted', 'after': 'invalidated'}])

    def test_reverting_the_text_never_revives_an_invalidated_review(self):
        producer = self.note('Sample producer')
        path = self.vault / producer['path']
        original = path.read_text()
        path.write_text(original.replace('Fictional responsibility', 'Changed responsibility')); self.rebuild()
        path.write_text(original)
        report = self.rebuild()
        self.assertEqual(self.state(), 'invalidated')
        self.assertGreater(report['notes']['new_revision'][0]['revision_after'], producer['revision'] + 1)

    def test_a_deleted_file_is_reported_as_no_longer_present(self):
        producer = self.note('Sample producer')
        (self.vault / producer['path']).unlink()
        report = self.rebuild()
        self.assertEqual(report['notes']['no_longer_present'], [producer['id']])
        self.assertEqual(self.state(), 'invalidated')

    def test_an_unreadable_vault_changes_nothing(self):
        before = {n['id'] for n in self.store.knowledge(self.owner)['nodes']}
        moved = self.home / 'vault-away'
        shutil.move(self.vault, moved)
        with self.assertRaises(Fault) as caught:
            self.rebuild()
        self.assertEqual(caught.exception.code, 'rebuild_source_unavailable')
        with self.store.connection() as db:
            self.assertEqual({r[0] for r in db.execute("SELECT id FROM knowledge_notes WHERE status='ready'")}, before)

    def test_an_older_schema_migrates_and_then_rebuilds_without_loss(self):
        before = {n['id']: n['revision'] for n in self.store.knowledge(self.owner)['nodes']}
        db = sqlite3.connect(self.home / 'desk.sqlite')
        # The version 1 table also made each path unique; the migration removes that constraint.
        columns = [r[1] for r in db.execute('PRAGMA table_info(knowledge_notes)')]
        db.executescript('BEGIN;'
                         'ALTER TABLE knowledge_notes RENAME TO knowledge_notes_current;'
                         'CREATE TABLE knowledge_notes(' + ','.join(columns) + ',UNIQUE(scope,source,path));'
                         'INSERT INTO knowledge_notes SELECT * FROM knowledge_notes_current;'
                         'DROP TABLE knowledge_notes_current;'
                         'UPDATE knowledge_meta SET version=1;COMMIT;')
        db.close()
        store = KnowledgeStore(self.home / 'desk.sqlite')
        with store.connection() as conn:
            self.assertEqual([r[0] for r in conn.execute('SELECT version FROM knowledge_meta')], [2])
        report = rebuild_index(store, self.owner, self.keys['source'], self.vault)
        self.assertEqual({n['id']: n['revision'] for n in store.knowledge(self.owner)['nodes']}, before)
        self.assertEqual(report['reviewed_statements']['state_changed'], [])

    def test_the_command_refuses_while_the_host_runs(self):
        import subprocess, sys
        fd = os.open(self.home / 'desk.lock', os.O_RDWR | os.O_CREAT, 0o600); self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run([sys.executable, '-m', 'alfred.desk', 'rebuild-index', '--data-dir', str(self.home)],
                                capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('stop_alfred_before_rebuild', result.stdout + result.stderr)
        self.assertEqual(load_keys(self.home)['owner'], self.keys['owner'])


if __name__ == '__main__':
    unittest.main()
