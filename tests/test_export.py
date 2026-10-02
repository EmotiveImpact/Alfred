"""MEM-013 portable export: readable, hashed, filtered to what the caller may read.

Synthetic notes, entities, statements, captures and executive records in real
SQLite. Checks what is included, what is never included, where an export may be
written, and that it is a different thing from a backup.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from alfred import desk, export as export_module
from alfred.desk import init_demo
from alfred.executive import ExecutiveRecords
from alfred.export import REPOSITORY, export
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.local import Fault
from alfred.policy import IdentityPolicy
from alfred.reviewed_memory import ReviewedMemory

DAY = 86400
FILES = {'README.md', 'manifest.json', 'statements.json', 'captures.json', 'executive-records.json',
         'statements.md', 'executive-records.md', 'SHA256SUMS'}


class ExportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.clock = [1_000_000]
        self.store = KnowledgeStore(self.root / 'desk.sqlite', clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=2592000)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=2592000)
        self.source = self.store.provision('work', 'source', 'source', ttl=2592000)
        self.other = self.store.provision('work', 'other', 'source', ttl=2592000)
        self.vault = self.root / 'vault'; self.vault.mkdir()
        (self.vault / 'Atlas.md').write_text('# Atlas\nAtlas is awaiting review.\nMina leads Atlas.\n'
                                             'The opening is monochrome.\nThe opening is now in colour.\n'
                                             'Secretforgottenvalue appears here.\nReview Atlas weekly.\n'
                                             'Launch in spring.\nUse <img src=x onerror=alert(1)> carefully.\n')
        MarkdownVault(self.store, self.source, self.vault).scan()
        self.offline = self.root / 'offline'; self.offline.mkdir()
        (self.offline / 'Budget.md').write_text('# Budget\nWithheldmarker budget is approved.\n')
        MarkdownVault(self.store, self.other, self.offline).scan()
        self.memory = ReviewedMemory(self.store); self.records = ExecutiveRecords(self.store)
        for identity, kind, name in (('atlas', 'project', 'Atlas'), ('mina', 'person', 'Mina'), ('mina-2', 'person', 'Mina')):
            self.memory.create_entity(self.owner, {'id': identity, 'kind': kind, 'name': name})
        self.status = self.accept('s-status', 'status', 2, value='awaiting review')
        self.lead = self.accept('s-lead', 'responsible_person', 3, obj='mina')
        self.old = self.accept('s-old', 'decision', 4, value='monochrome opening')
        self.new = self.propose('s-new', 'decision', 5, value='colour opening')['id']
        self.memory.review(self.owner, self.new, {'version': 1, 'decision': 'supersede', 'replaces_id': self.old, 'replaces_version': 2})
        self.forgotten = self.accept('s-forget', 'scheduled_for', 6, value='Secretforgottenvalue')
        self.memory.forget(self.owner, self.forgotten, {'version': 2})
        self.proposed = self.propose('s-proposed', 'scheduled_for', 8, value='spring launch')['id']
        self.hostile = self.accept('s-hostile', 'status', 9, value='<img src=x onerror=alert(1)> `tick`')
        self.kept = self.capture('c-kept', 7, 'weekly review', 30)['id']
        self.forever = self.capture('c-forever', 8, 'launch season', None)['id']
        self.expired = self.capture('c-expired', 2, 'Expiredmarker', 1)['id']
        budget = self.store.knowledge(self.owner)['nodes']
        budget = next(n for n in budget if n['path'] == 'Budget.md')
        self.withheld = self.accept('s-withheld', 'status', 2, value='Withheldmarker approved', note=budget)
        self.store.knowledge_unavailable(self.other, 'vault_offline')
        note = self.note()
        self.commitment = self.records.create(self.owner, {
            'request_id': 'e1', 'kind': 'commitment', 'title': 'Send the Atlas brief', 'detail': 'Line one.\n```\nfenced\n```',
            'project': 'entity:atlas', 'due': self.clock[0] + 2 * DAY, 'rank': None,
            'support': {'note_id': note['id'], 'sha256': note['sha256'], 'revision': note['revision'], 'start_line': 7, 'end_line': 7}})
        self.goal = self.records.create(self.owner, {'request_id': 'e2', 'kind': 'goal', 'title': 'Atlas ships in spring', 'detail': '',
                                                      'project': None, 'due': None, 'rank': None, 'support': None})
        self.invitation = IdentityPolicy(self.store).invite(self.owner, 'source', 'read', self.clock[0] + DAY, 0)['code']
        self.clock[0] += 2 * DAY

    def note(self, path='Atlas.md'):
        return next(n for n in self.store.knowledge(self.owner)['nodes'] if n['path'] == path)

    def evidence(self, line, note=None):
        n = note or self.note()
        return {'note_id': n['id'], 'sha256': n['sha256'], 'revision': n['revision'], 'start_line': line, 'end_line': line}

    def propose(self, request, predicate, line, value=None, obj=None, note=None):
        return self.memory.propose(self.owner, {'request_id': request, 'subject_id': 'atlas', 'predicate': predicate, 'object_id': obj,
                                                'value': value, 'valid_from': None, 'valid_until': None, 'evidence': self.evidence(line, note)})

    def accept(self, request, predicate, line, value=None, obj=None, note=None):
        made = self.propose(request, predicate, line, value, obj, note)
        self.memory.review(self.owner, made['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        return made['id']

    def capture(self, request, line, value, days):
        return self.memory.capture(self.owner, {'request_id': request, 'subject_id': 'atlas', 'predicate': 'scheduled_for', 'object_id': None,
                                                'value': value, 'valid_from': None, 'valid_until': None, 'evidence': self.evidence(line),
                                                'memory_type': 'commitment', 'retention_days': days, 'captured_from': {'note_id': 'n1'}})

    def bundle(self, directory):
        return {p.name: p.read_bytes() for p in Path(directory).iterdir()}

    def test_bundle_is_self_describing_hashed_and_private(self):
        result = export(self.store, self.owner, self.root / 'out')
        out = self.root / 'out'
        self.assertEqual(set(p.name for p in out.iterdir()), FILES)
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o700)
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in out.iterdir()))
        files = self.bundle(out)
        manifest = json.loads(files['manifest.json'])
        self.assertEqual(manifest, {k: v for k, v in result.items() if k != 'directory'})
        self.assertEqual((manifest['format'], manifest['format_version'], manifest['exported_at']),
                         ('alfred-portable-export', 1, self.clock[0]))
        self.assertEqual((manifest['workspace'], manifest['credential'], manifest['role']), ('work', 'owner', 'owner'))
        self.assertEqual({f['path'] for f in manifest['files']}, FILES - {'manifest.json', 'SHA256SUMS'})
        for entry in manifest['files']:
            self.assertEqual(hashlib.sha256(files[entry['path']]).hexdigest(), entry['sha256'])
            self.assertEqual(len(files[entry['path']]), entry['bytes'])
        sums = dict(reversed(line.split('  ')) for line in files['SHA256SUMS'].decode().splitlines())
        self.assertEqual(set(sums), FILES - {'SHA256SUMS'})
        self.assertTrue(all(hashlib.sha256(files[name]).hexdigest() == digest for name, digest in sums.items()))
        self.assertEqual(manifest['counts'], {'entities': 3, 'statements': 8, 'captures': 2, 'executive_records': 2})
        self.assertEqual({k: manifest['excluded'][k] for k in ('forgotten_statements', 'withheld_statements', 'retention_ended_statements')},
                         {'forgotten_statements': 1, 'withheld_statements': 1, 'retention_ended_statements': 1})
        self.assertFalse(manifest['encrypted'] or manifest['restorable'] or manifest['authority_granted'])
        self.assertIn('backup', manifest['differs_from_backup'])
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT subject FROM audit WHERE kind='export.written'").fetchone()[0], manifest['export_id'])

    def test_review_state_source_revisions_lineage_and_retention_are_kept(self):
        export(self.store, self.owner, self.root / 'out')
        files = self.bundle(self.root / 'out')
        statements = {s['id']: s for s in json.loads(files['statements.json'])['statements']}
        self.assertEqual(set(statements), {self.status, self.lead, self.old, self.new, self.proposed, self.hostile, self.kept, self.forever})
        self.assertEqual(statements[self.proposed]['review_state'], 'proposed')
        self.assertFalse(statements[self.proposed]['usable_now'])
        self.assertEqual(statements[self.old]['review_state'], 'superseded')
        self.assertEqual(statements[self.old]['lineage'], {'replaces': None, 'replaced_by': self.new})
        self.assertEqual(statements[self.new]['lineage'], {'replaces': self.old, 'replaced_by': None})
        self.assertEqual(statements[self.lead]['object'], {'id': 'mina', 'kind': 'person', 'name': 'Mina'})
        note = self.note()
        self.assertEqual({k: statements[self.status]['source'][k] for k in ('note_id', 'sha256', 'revision', 'start_line', 'end_line', 'state', 'quote')},
                         {'note_id': note['id'], 'sha256': note['sha256'], 'revision': note['revision'], 'start_line': 2, 'end_line': 2,
                          'state': 'current', 'quote': 'Atlas is awaiting review.'})
        captures = {c['statement_id']: c for c in json.loads(files['captures.json'])['captures']}
        self.assertEqual(set(captures), {self.kept, self.forever})
        self.assertEqual(captures[self.kept]['retention_until'], 1_000_000 + 30 * DAY)
        self.assertIsNone(captures[self.forever]['retention_until'])
        self.assertEqual(captures[self.forever]['captured_from'], {'note_id': 'n1'})
        entities = {e['id']: e for e in json.loads(files['statements.json'])['entities']}
        self.assertEqual((entities['mina']['same_name_as'], entities['mina-2']['same_name_as']), (['mina-2'], ['mina']))
        records = {r['id']: r for r in json.loads(files['executive-records.json'])['records']}
        self.assertEqual(set(records), {self.commitment['id'], self.goal['id']})
        self.assertEqual(records[self.commitment['id']]['support']['state'], 'current')
        self.assertEqual(records[self.commitment['id']]['support']['quote'], 'Review Atlas weekly.')

    def test_lineage_never_names_a_statement_that_was_left_out(self):
        first = self.accept('s-dep-1', 'depends_on', 3, obj='mina')
        second = self.propose('s-dep-2', 'depends_on', 3, obj='mina-2')['id']
        self.memory.review(self.owner, second, {'version': 1, 'decision': 'supersede', 'replaces_id': first, 'replaces_version': 2})
        self.memory.forget(self.owner, second, {'version': 2})
        export(self.store, self.owner, self.root / 'out')
        files = self.bundle(self.root / 'out')
        statements = {s['id']: s for s in json.loads(files['statements.json'])['statements']}
        self.assertEqual(statements[first]['lineage'], {'replaces': None, 'replaced_by': 'not_exported'})
        self.assertNotIn(second.encode(), b''.join(files.values()))
        self.assertIn('Replaces (none); replaced by `not_exported`', files['statements.md'].decode())

    def test_forgotten_withheld_expired_and_secret_values_never_appear(self):
        export(self.store, self.owner, self.root / 'out')
        everything = b''.join(self.bundle(self.root / 'out').values())
        with self.store.connection() as db:
            digests = [r[0] for r in db.execute('SELECT digest FROM credentials')]
        for secret in [self.owner, self.reader, self.source, self.other, self.invitation, *digests,
                       'Secretforgottenvalue', self.forgotten, 'Withheldmarker', self.withheld, 'Expiredmarker', self.expired]:
            with self.subTest(secret=secret[:12]):
                self.assertNotIn(secret.encode(), everything)

    def test_markdown_shows_note_text_literally(self):
        export(self.store, self.owner, self.root / 'out')
        files = self.bundle(self.root / 'out')
        statements = files['statements.md'].decode()
        self.assertIn('`` <img src=x onerror=alert(1)> `tick` ``', statements)
        self.assertIn('`Use <img src=x onerror=alert(1)> carefully.`', statements)
        # Outside code spans no note text can act as HTML or Markdown.
        self.assertNotIn('<img', re.sub(r'(`+)(?!`).+?(?<!`)\1(?!`)', '', statements))
        self.assertIn('## Proposed (3)', statements)
        self.assertIn('They are separate records and were never merged.', statements)
        executive = files['executive-records.md'].decode()
        self.assertIn('````text\nLine one.\n```\nfenced\n```\n````', executive)
        self.assertNotIn('\u2014', statements + executive + files['README.md'].decode())

    def test_same_clock_gives_the_same_records(self):
        export(self.store, self.owner, self.root / 'one')
        export(self.store, self.owner, self.root / 'two')
        one, two = self.bundle(self.root / 'one'), self.bundle(self.root / 'two')
        for name in ('statements.json', 'captures.json', 'executive-records.json', 'statements.md', 'executive-records.md', 'README.md'):
            self.assertEqual(one[name], two[name], name)
        self.assertNotEqual(json.loads(one['manifest.json'])['export_id'], json.loads(two['manifest.json'])['export_id'])

    def test_reader_exports_only_its_own_actor_private_records(self):
        export(self.store, self.reader, self.root / 'reader')
        files = self.bundle(self.root / 'reader')
        manifest = json.loads(files['manifest.json'])
        self.assertEqual(manifest['counts'], {'entities': 0, 'statements': 0, 'captures': 0, 'executive_records': 0})
        everything = b''.join(files.values())
        for owner_text in (b'awaiting review', b'Send the Atlas brief', b'Mina'):
            self.assertNotIn(owner_text, everything)

    def test_source_credential_cannot_export(self):
        with self.assertRaises(Fault) as raised:
            export(self.store, self.source, self.root / 'out')
        self.assertEqual(raised.exception.code, 'forbidden')
        self.assertFalse((self.root / 'out').exists())

    def test_authority_change_while_assembling_stops_the_export(self):
        original = ExecutiveRecords.view
        def changing(records, bearer):
            policy = IdentityPolicy(self.store)
            policy.enable(self.owner, policy.view(self.owner)['epoch'])
            return original(records, bearer)
        with patch.object(ExecutiveRecords, 'view', changing), self.assertRaises(Fault) as raised:
            export(self.store, self.owner, self.root / 'out')
        self.assertEqual(raised.exception.code, 'export_authority_changed')
        self.assertFalse((self.root / 'out').exists())

    def test_destination_rules(self):
        busy = self.root / 'busy'; busy.mkdir(); (busy / 'keep.txt').write_text('mine')
        file = self.root / 'file.txt'; file.write_text('mine')
        (self.root / 'notes' / '.obsidian').mkdir(parents=True)
        (self.root / 'link').symlink_to(self.root / 'elsewhere')
        cases = [(busy, (), 'export_destination_not_empty'), (file, (), 'export_destination_not_empty'),
                 (self.vault / 'export', (self.vault,), 'export_destination_inside_vault'),
                 (self.root / 'notes' / 'export', (), 'export_destination_inside_vault'),
                 (REPOSITORY / 'export-test-never-created', (), 'export_destination_inside_repository'),
                 (self.root / 'link', (), 'export_destination_symlink'),
                 (self.root / 'absent' / 'export', (), 'export_parent_missing')]
        for target, vaults, code in cases:
            with self.subTest(target=target.name), self.assertRaises(Fault) as raised:
                export(self.store, self.owner, target, vaults=vaults)
            self.assertEqual(raised.exception.code, code)
        self.assertEqual((busy / 'keep.txt').read_text(), 'mine')
        self.assertEqual(file.read_text(), 'mine')
        self.assertFalse((self.vault / 'export').exists() or (REPOSITORY / 'export-test-never-created').exists())
        self.assertFalse(any('.partial-' in p.name for p in self.root.iterdir()))
        with self.store.connection() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM audit WHERE kind='export.written'").fetchone())

    def test_empty_folder_and_synced_folder_are_valid_destinations(self):
        empty = self.root / 'empty'; empty.mkdir(mode=0o755)
        export(self.store, self.owner, empty)
        self.assertEqual(stat.S_IMODE(empty.stat().st_mode), 0o700)
        synced = self.root / 'Sync'; synced.mkdir(); (synced / '.stfolder').mkdir()
        export(self.store, self.owner, synced / 'alfred-export')
        self.assertEqual(set(p.name for p in (synced / 'alfred-export').iterdir()), FILES)

    def test_a_file_that_appears_before_the_rename_stops_the_export(self):
        empty = self.root / 'empty'; empty.mkdir()
        real = os.rename
        def racing(source, target):
            (Path(target) / 'late.txt').write_text('someone else')
            return real(source, target)
        with patch.object(export_module.os, 'rename', racing), self.assertRaises(Fault) as raised:
            export(self.store, self.owner, empty)
        self.assertEqual(raised.exception.code, 'export_destination_not_empty')
        self.assertEqual([p.name for p in empty.iterdir()], ['late.txt'])
        self.assertFalse(any('.partial-' in p.name for p in self.root.iterdir()))

    def test_failed_write_leaves_nothing_behind(self):
        real = os.write
        calls = []
        def failing(fd, data):
            calls.append(fd)
            if len(calls) == 3:
                raise OSError('disk full')
            return real(fd, data)
        with patch.object(export_module.os, 'write', failing), self.assertRaises(OSError):
            export(self.store, self.owner, self.root / 'out')
        self.assertFalse((self.root / 'out').exists())
        self.assertFalse(any('.partial-' in p.name for p in self.root.iterdir()))


class ExportCommandLineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        mask = os.umask(0o077); os.umask(mask)
        self.addCleanup(os.umask, mask)
        self.home = self.root / 'home'; init_demo(self.home)

    def run_desk(self, *arguments):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['alfred.desk', *arguments]), contextlib.redirect_stdout(output):
            try:
                desk.main()
                code = 0
            except SystemExit as exc:
                code = exc.code
        return code, output.getvalue()

    def test_export_command_writes_a_bundle_and_refuses_to_overwrite(self):
        code, output = self.run_desk('export', '--data-dir', str(self.home), '--export-dir', str(self.root / 'export'))
        self.assertEqual(code, 0, output)
        self.assertIn('Export written:', output)
        self.assertIn('Not a backup and not encrypted', output)
        self.assertEqual(set(p.name for p in (self.root / 'export').iterdir()), FILES)
        code, output = self.run_desk('export', '--data-dir', str(self.home), '--export-dir', str(self.root / 'export'))
        self.assertEqual(code, 1)
        self.assertIn('Cannot start: export_destination_not_empty', output)
        code, output = self.run_desk('export', '--data-dir', str(self.home), '--export-dir', str(self.home / 'vault' / 'export'))
        self.assertEqual(code, 1)
        self.assertIn('Cannot start: export_destination_inside_vault', output)
        code, output = self.run_desk('export', '--data-dir', str(self.home))
        self.assertEqual((code, 'Cannot start: export_dir_required' in output), (1, True))


if __name__ == '__main__':
    unittest.main()
