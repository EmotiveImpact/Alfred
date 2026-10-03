"""MEM-014 sync conflict copies: recognised by exact names, recorded, never indexed.

Synthetic vault files, real SQLite and the real scanner, retrieval and console
projection. No sync client runs here: the copies are created by name, the way the
named tools document them.
"""
from pathlib import Path
import http.client
import json
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from alfred import inbox
from alfred.console_api import projection
from alfred.desk import init_demo
from alfred.desk_http import DeskHTTPServer
from alfred.grounded import retrieve
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor, MarkdownVault
from alfred.knowledge_context import build_packet
from alfred.local import Fault
from alfred.policy import IdentityPolicy
from alfred.reviewed_memory import ReviewedMemory
from alfred.sync_conflicts import MAX_CONFLICTS, conflict_copy

SYNCTHING = 'Atlas.sync-conflict-20261002-101500-ABCDEFG.md'
DROPBOX = "Atlas (Jo Example's conflicted copy 2026-10-02).md"


class ConflictNameTests(unittest.TestCase):
    RECOGNISED = {
        SYNCTHING: ('syncthing', 'Atlas.md'),
        'Atlas.sync-conflict-20261002-101500-.md': ('syncthing', 'Atlas.md'),
        'v1.2 notes.sync-conflict-20261002-101500-Q2RST7Z.MD': ('syncthing', 'v1.2 notes.MD'),
        DROPBOX: ('dropbox', 'Atlas.md'),
        "Atlas (Jo's MacBook Air's conflicted copy 2026-10-02 (2)).md": ('dropbox', 'Atlas.md'),
        'Atlas (Jo’s conflicted copy 2026-10-02).md': ('dropbox', 'Atlas.md'),
        'Atlas (conflicted copy 2026-10-02 101500).md': ('nextcloud_owncloud', 'Atlas.md'),
        'Atlas (conflicted copy sam example 2026-10-02 101500).md': ('nextcloud_owncloud', 'Atlas.md'),
        'Atlas_conflict-20261002-101500.md': ('owncloud_legacy', 'Atlas.md'),
    }
    ORDINARY = [
        'Meeting 2.md', 'Report (1).md', 'Atlas.md', 'notes.sync-conflict.md', 'notes.sync-conflict-2026-10-02.md',
        'x (conflicted copy).md', "Alice's conflicted copy.md", 'Conflicted copy policy.md',
        'Notes about sync-conflict handling.md', 'Plan_conflict-notes.md', 'Budget-LAPTOP-7F3K2Q.md',
        "Atlas (Jo's conflicted copy 2026-13-40).md", 'Atlas (conflicted copy 2026-02-30 101500).md',
        'Atlas.sync-conflict-20261002-256199-ABCDEFG.md', 'Atlas.sync-conflict-20261002-101500-abcdefg.md',
        'Atlas.sync-conflict-20261002-101500-ABCDEFG.txt', ' (conflicted copy 2026-10-02 101500).md',
        "Atlas (PC (Office)'s conflicted copy 2026-10-02).md",
    ]

    def test_documented_names_are_recognised(self):
        for name, (tool, original) in self.RECOGNISED.items():
            with self.subTest(name=name):
                found = conflict_copy(name)
                self.assertEqual((found['tool'], found['original_path'], found['markers']), (tool, original, 1))

    def test_ordinary_names_are_not_conflicts(self):
        for name in self.ORDINARY:
            with self.subTest(name=name):
                self.assertIsNone(conflict_copy(name))

    def test_copy_of_a_copy_leads_to_the_first_original_in_the_same_folder(self):
        nested = 'Projects/a.sync-conflict-20260101-000000-AAAAAAA.sync-conflict-20260102-000000-BBBBBBB.md'
        self.assertEqual(conflict_copy(nested), {'tool': 'syncthing', 'original_path': 'Projects/a.md', 'markers': 2})
        mixed = "a (X's conflicted copy 2026-01-01) (conflicted copy 2026-01-02 000000).md"
        self.assertEqual(conflict_copy(mixed), {'tool': 'nextcloud_owncloud', 'original_path': 'a.md', 'markers': 2})
        self.assertIsNone(conflict_copy(None))


class ScannerConflictTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.vault = self.root / 'vault'
        self.vault.mkdir()
        self.clock = [1000]
        self.store = KnowledgeStore(self.root / 'db', clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=100000, legacy_scope=True)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=100000, legacy_scope=True)
        self.source = self.store.provision('work', 'source', 'source', ttl=100000, legacy_scope=True)
        self.scanner = MarkdownVault(self.store, self.source, self.vault)

    def write(self, path, body):
        file = self.vault / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(body, encoding='utf-8')
        return file

    def data(self, bearer=None, query=''):
        return self.store.knowledge(bearer or self.owner, query)

    def paths(self):
        return sorted(n['path'] for n in self.data()['nodes'])

    def audit(self):
        with self.store.connection() as db:
            return [r['kind'] for r in db.execute("SELECT kind FROM audit WHERE kind LIKE 'knowledge.sync_conflict%' ORDER BY seq")]

    def test_copy_is_recorded_linked_and_kept_out_of_the_index(self):
        self.write('Atlas.md', '# Atlas\nAtlas is awaiting review.\n')
        self.write(SYNCTHING, '# Atlas\nAtlas is cancelled.\n')
        health = self.scanner.scan()
        self.assertEqual(health['status'], 'attention')
        self.assertIn({'path': SYNCTHING, 'code': 'sync_conflict_copy', 'original_path': 'Atlas.md'}, health['errors'])
        data = self.data()
        self.assertEqual(self.paths(), ['Atlas.md'])
        original = data['nodes'][0]['id']
        [conflict] = data['sync_conflicts']
        self.assertEqual({k: conflict[k] for k in ('path', 'original_path', 'original', 'state', 'tool', 'basis')},
                         {'path': SYNCTHING, 'original_path': 'Atlas.md', 'original': original, 'state': 'linked',
                          'tool': 'syncthing', 'basis': 'sync_conflict_copy_not_indexed'})
        self.assertEqual(data['counts']['sync_conflicts'], 1)
        self.assertEqual(data['sources'][0]['status'], 'attention')
        self.assertEqual(self.audit(), ['knowledge.sync_conflict_detected'])
        # A later scan keeps the first detection time and does not repeat the audit entry.
        self.clock[0] = 2000; self.scanner.scan()
        self.assertEqual(self.data()['sync_conflicts'][0]['detected'], 1000)
        self.assertEqual(self.audit(), ['knowledge.sync_conflict_detected'])

    def test_copy_text_never_reaches_search_retrieval_or_grounding(self):
        self.write('Atlas.md', '# Atlas\nAtlas is awaiting review.\n')
        self.write(DROPBOX, '# Atlas\nZephyrmarker says Atlas is cancelled.\n')
        self.scanner.scan()
        self.assertEqual(self.data(query='Zephyrmarker')['results'], [])
        self.assertNotIn('Zephyrmarker', json.dumps(self.data()))
        self.assertEqual(retrieve(self.store, self.owner, 'Zephyrmarker cancelled')['evidence'], [])
        self.assertEqual(build_packet(self.store, self.owner, 'Zephyrmarker')['evidence'], [])
        with self.store.connection() as db:
            self.assertFalse(db.execute("SELECT 1 FROM knowledge_notes WHERE body LIKE '%Zephyrmarker%'").fetchone())

    def test_removing_the_copy_resolves_the_conflict(self):
        self.write('Atlas.md', '# Atlas\nAtlas is awaiting review.\n')
        copy = self.write(SYNCTHING, '# Atlas\nAtlas is cancelled.\n')
        self.scanner.scan(); before = self.data()['nodes'][0]
        copy.unlink()
        self.assertEqual(self.scanner.scan()['status'], 'ready')
        data = self.data()
        self.assertEqual((data['sync_conflicts'], data['counts']['sync_conflicts']), ([], 0))
        self.assertEqual(data['sources'][0]['status'], 'ready')
        self.assertEqual((data['nodes'][0]['id'], data['nodes'][0]['revision']), (before['id'], before['revision']))
        self.assertEqual(self.audit(), ['knowledge.sync_conflict_detected', 'knowledge.sync_conflict_cleared'])

    def test_orphaned_copy_without_an_original(self):
        self.write('Other.md', '# Other\n')
        self.write('Projects/Plan (conflicted copy 2026-10-02 101500).md', '# Plan\nDraft.\n')
        self.scanner.scan()
        data = self.data()
        self.assertEqual(self.paths(), ['Other.md'])
        [conflict] = data['sync_conflicts']
        self.assertEqual((conflict['state'], conflict['original'], conflict['original_path'], conflict['tool']),
                         ('orphaned', None, 'Projects/Plan.md', 'nextcloud_owncloud'))

    def test_original_that_cannot_be_indexed_is_not_called_missing(self):
        self.write('Atlas.md', '# Atlas\n```\nunclosed fence\n')
        self.write(SYNCTHING, '# Atlas\n')
        self.scanner.scan()
        [conflict] = self.data()['sync_conflicts']
        self.assertEqual((conflict['state'], conflict['original']), ('original_unavailable', None))

    def test_identity_stays_with_the_original_path_when_the_old_file_becomes_the_copy(self):
        # Syncthing renames the losing local file to the conflict name and writes the
        # winning version under the original name, so the old inode moves to the copy.
        original = self.write('Atlas.md', '# Atlas\nAtlas is awaiting review.\n')
        self.scanner.scan(); before = self.data()['nodes'][0]
        original.rename(self.vault / SYNCTHING)
        self.write('Atlas.md', '# Atlas\nAtlas is approved.\n')
        self.scanner.scan()
        after = self.data()['nodes']
        self.assertEqual([(n['path'], n['id']) for n in after], [('Atlas.md', before['id'])])
        self.assertEqual(after[0]['revision'], before['revision'] + 1)
        self.assertEqual(self.data()['sync_conflicts'][0]['original'], before['id'])

    def test_copy_carrying_the_same_adopted_id_does_not_take_the_vault_offline(self):
        # Explicit adoption before the first selected-vault scan, as in the M01 tests.
        with self.store.transaction() as db:
            db.execute('DELETE FROM knowledge_vaults')
        scanner = MarkdownVault(self.store, self.source, self.vault, id_key='alfred_id')
        self.write('Atlas.md', '---\nalfred_id: atlas-001\n---\n# Atlas\nAwaiting review.\n')
        self.write(DROPBOX, '---\nalfred_id: atlas-001\n---\n# Atlas\nCancelled.\n')
        self.assertEqual(scanner.scan()['status'], 'attention')
        self.assertEqual(self.paths(), ['Atlas.md'])
        self.assertEqual(self.data()['sync_conflicts'][0]['state'], 'linked')

    def test_review_of_an_unchanged_original_stays_usable_while_a_copy_waits(self):
        self.write('Atlas.md', '# Atlas\nAtlas is awaiting review.\n')
        self.scanner.scan(); note = self.data()['nodes'][0]
        memory = ReviewedMemory(self.store)
        memory.create_entity(self.owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas'})
        made = memory.propose(self.owner, {'request_id': 'r1', 'subject_id': 'atlas', 'predicate': 'status', 'object_id': None,
                                           'value': 'awaiting review', 'valid_from': None, 'valid_until': None,
                                           'evidence': {'note_id': note['id'], 'sha256': note['sha256'], 'revision': note['revision'],
                                                        'start_line': 2, 'end_line': 2}})
        memory.review(self.owner, made['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        # The copy arrives on this device as a new file; the original is untouched.
        self.write(DROPBOX, '# Atlas\nAtlas is cancelled.\n')
        self.scanner.scan()
        claim = next(c for c in memory.view(self.owner)['claims'] if c['id'] == made['id'])
        self.assertEqual((claim['state'], claim['usable'], claim['value']), ('accepted', True, 'awaiting review'))
        self.assertEqual(self.data()['nodes'][0]['revision'], note['revision'])

    def test_copy_indexed_by_an_older_scanner_is_withheld_not_deleted(self):
        self.write('Atlas.md', '# Atlas\n')
        self.write(SYNCTHING, '# Atlas copy\n')
        with patch('alfred.sync_conflicts.conflict_copy', return_value=None):
            self.scanner.scan()
        legacy = next(n for n in self.data()['nodes'] if n['path'] == SYNCTHING)
        self.scanner.scan()
        self.assertEqual(self.paths(), ['Atlas.md'])
        with self.store.connection() as db:
            status = lambda: db.execute('SELECT status FROM knowledge_notes WHERE id=?', (legacy['id'],)).fetchone()[0]
            self.assertEqual(status(), 'unavailable')
            (self.vault / SYNCTHING).unlink(); self.scanner.scan()
            self.assertEqual(status(), 'missing')

    def test_recorded_copies_are_bounded(self):
        self.write('a.md', '# A\n')
        for second in range(MAX_CONFLICTS + 1):
            self.write(f'a.sync-conflict-20261002-1015{second % 60:02d}-{"ABCDEFG" if second < 60 else "QRSTUVW"}.md', '# A copy\n')
        self.write('b.md', '# B\n```\nunclosed fence\n')
        health = self.scanner.scan()
        self.assertEqual(health['errors'][:2], [{'code': 'sync_conflict_capacity'}, {'path': 'b.md', 'code': 'unclosed_code_fence'}])
        self.assertEqual(self.data()['sources'][0]['errors'][:2], health['errors'][:2])
        self.assertEqual(self.paths(), ['a.md'])
        self.assertEqual(len(self.data()['sync_conflicts']), MAX_CONFLICTS)

    def test_conflicts_follow_source_permission(self):
        self.write('Atlas.md', '# Atlas\n')
        self.write(SYNCTHING, '# Atlas\n')
        self.scanner.scan()
        self.assertEqual(len(self.data(self.reader)['sync_conflicts']), 1)
        policy = IdentityPolicy(self.store)
        policy.grant(self.owner, 'source', 'read', 50000, policy.view(self.owner)['epoch'])
        self.assertEqual(len(self.data()['sync_conflicts']), 1)
        hidden = self.data(self.reader)
        self.assertEqual((hidden['sync_conflicts'], hidden['sources']), ([], []))
        self.assertNotIn('sync-conflict', json.dumps(hidden))

    def test_unavailable_source_hides_its_last_known_conflicts(self):
        self.write('Atlas.md', '# Atlas\n')
        self.write(SYNCTHING, '# Atlas\n')
        self.scanner.scan()
        self.vault.rename(self.root / 'away')
        self.assertEqual(self.scanner.scan()['status'], 'unavailable')
        self.assertEqual(self.data()['sync_conflicts'], [])

    def test_console_projection_marks_the_original_and_lists_every_copy(self):
        self.write('Atlas.md', '# Atlas\nAwaiting review.\n')
        self.write(SYNCTHING, '# Atlas\n')
        self.write('Plan (conflicted copy 2026-10-02 101500).md', '# Plan\n')
        self.scanner.scan()
        server = types.SimpleNamespace(store=self.store, memory=ReviewedMemory(self.store), executive=None)
        view = projection(server, self.owner)
        notes = {n['path']: n for n in view['nodes'] if n['origin'] == 'authored_note'}
        self.assertEqual(sorted(notes), ['Atlas.md'])
        atlas = notes['Atlas.md']
        self.assertEqual(atlas['availability'], 'attention')
        self.assertEqual(atlas['syncConflict']['state'], 'unresolved')
        self.assertEqual([c['path'] for c in atlas['syncConflict']['copies']], [SYNCTHING])
        self.assertEqual(atlas['evidence'][0]['availability'], 'current')
        self.assertEqual(sorted((c['path'], c['state'], c['originalId']) for c in view['syncConflicts']),
                         [(SYNCTHING, 'linked', atlas['id']),
                          ('Plan (conflicted copy 2026-10-02 101500).md', 'orphaned', None)])
        self.assertEqual(view['counts']['syncConflicts'], 2)
        source = next(n for n in view['nodes'] if n['origin'] == 'source')
        self.assertEqual((source['availability'], source['issues']), ('attention', 2))

    def test_store_rejects_an_inconsistent_conflict_report(self):
        def note(path):
            return {'path': path, 'title': 'Atlas', 'kind': 'note', 'tags': [], 'aliases': [], 'body': '# Atlas\n',
                    'sha256': '0' * 64, 'refs': [], 'anchors': [], 'external_id': None, 'warnings': [], 'modified': 1}
        def report(**changes):
            return [{'path': SYNCTHING, 'original_path': 'Atlas.md', 'tool': 'syncthing', 'markers': 1, 'original_present': True} | changes]
        cases = [(note('Atlas.md'), report(path='Atlas.md', original_path='Atlas.md'), 'invalid_sync_conflict'),
                 (note('Atlas.md'), report(original_path='Other.md'), 'invalid_sync_conflict'),
                 (note('Atlas.md'), report(tool='dropbox'), 'invalid_sync_conflict'),
                 (note('Atlas.md'), report(original_present='yes'), 'invalid_sync_conflict'),
                 (note('Atlas.md'), report(extra=True), 'invalid_sync_conflict'),
                 (note('Atlas.md'), report(markers=2), 'invalid_sync_conflict'),
                 (note('Atlas.md'), [{k: v for k, v in report()[0].items() if k != 'markers'}], 'invalid_sync_conflict'),
                 (note(SYNCTHING), report(), 'duplicate_note_path'),
                 (note('Atlas.md'), report() * 2, 'duplicate_note_path')]
        for indexed, conflicts, code in cases:
            with self.subTest(conflicts=conflicts), self.assertRaises(Fault) as raised:
                self.store.replace_notes(self.source, 'Vault', [indexed], [], self.scanner.vault_id, conflicts=conflicts)
            self.assertEqual(raised.exception.code, code)
        self.assertEqual(self.data()['nodes'], [])

    def test_inbox_never_creates_a_note_named_like_a_conflict_copy(self):
        for name in (SYNCTHING, 'Atlas_conflict-20261002-101500.md'):
            with self.subTest(name=name), self.assertRaises(Fault) as raised:
                inbox.destination(name)
            self.assertEqual(raised.exception.code, 'inbox_filename_looks_like_sync_conflict')
        self.assertEqual(inbox.destination('Atlas update.md'), 'ALFRED/Inbox/Atlas update.md')


class ConflictHTTPTests(unittest.TestCase):
    """The existing authenticated routes surface the conflict; no route was added."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name); self.home = root / 'demo'; self.keys = init_demo(self.home)
        self.store = KnowledgeStore(self.home / 'desk.sqlite')
        (self.home / 'vault' / 'notes' / 'Brief (Sample Coordinator\'s conflicted copy 2026-10-02).md').write_text(
            '# Creative brief\nA colour opening instead.\n')
        self.sup = KnowledgeSupervisor(self.store, self.keys['owner'], self.keys['source'], self.home / 'project', vault=self.home / 'vault')
        self.sup.cycle()
        self.server = DeskHTTPServer(self.store, self.sup, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)

    def request(self, path, data=None, headers=None):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = dict(headers or {})
        if data is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': self.server.origin})
        c.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); body = r.read(); c.close()
        return r, body

    def test_knowledge_and_console_routes_show_the_conflict_only_after_sign_in(self):
        r, body = self.request('/desk/knowledge')
        self.assertEqual(r.status, 401)
        self.assertNotIn(b'conflicted copy', body)
        r, body = self.request('/desk/login', {'key': self.keys['reader']}); self.assertEqual(r.status, 200)
        cookie = {'Cookie': r.getheader('Set-Cookie').split(';')[0]}
        r, body = self.request('/desk/knowledge', headers=cookie); self.assertEqual(r.status, 200)
        data = json.loads(body)
        [conflict] = data['sync_conflicts']
        brief = next(n for n in data['nodes'] if n['path'] == 'notes/Brief.md')
        self.assertEqual((conflict['original'], conflict['state'], conflict['tool']), (brief['id'], 'linked', 'dropbox'))
        self.assertFalse(any('conflicted copy' in n['path'] for n in data['nodes']))
        errors = data['sources'][0]['errors']
        self.assertIn('sync_conflict_copy', [e['code'] for e in errors])
        r, body = self.request('/desk/console/projection', headers=cookie); self.assertEqual(r.status, 200)
        view = json.loads(body)
        self.assertEqual(view['counts']['syncConflicts'], 1)
        node = next(n for n in view['nodes'] if n['id'] == 'note:' + brief['id'])
        self.assertEqual(node['availability'], 'attention')


if __name__ == '__main__':
    unittest.main()
