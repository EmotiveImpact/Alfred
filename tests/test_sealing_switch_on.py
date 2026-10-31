"""Switching a workspace on (encryption step 2, part 5): the ``seal`` command, refusing to
start without the keyring, sealed backups and exports, compaction after an absolute forget,
key rotation with re-sealing, and a final scan of every file a sealed workspace keeps.

Synthetic keys and invented text only. The at-rest tests of parts 1 to 4 run again here on a
workspace built plain, as an existing one is, and then converted with ``seal``.
"""
import base64
from contextlib import closing, redirect_stdout
import hashlib
import io
import itertools
import json
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

from alfred import connectors, desk, export, keys, lifecycle, seal_workspace, sealing
from alfred.local import Fault
from sealed_suite import SyntheticUnlock
import test_sealing
import test_sealing_memory
import test_sealing_records
import test_sealing_work


def plain_build(test, mixin):
    """Run a test's setUp with every sealer plain, as a workspace made before part 5 is."""
    with mock.patch.object(sealing, 'Sealed', lambda keyring, **kw: sealing.PLAIN):
        super(mixin, test).setUp()


def stored_bytes(*paths):
    """Every byte a sealed workspace keeps: each database with its log, shared memory and
    journal, the lifecycle journal, and every file under the folders given."""
    found = b''
    for path in map(Path, paths):
        if path.is_dir():
            found += b''.join(p.read_bytes() for p in sorted(path.rglob('*')) if p.is_file())
        for suffix in ('', '-wal', '-shm', '-journal', lifecycle.JOURNAL_SUFFIX):
            part = Path(str(path) + suffix)
            if part.is_file():
                found += part.read_bytes()
    return found


class Plain:
    """The base's workspace, built plain and left plain in any run (the sealed suite
    included); the test switches it on with ``seal``."""

    def setUp(self):
        default = mock.patch.object(sealing, 'for_path', lambda path: sealing._attached.get(sealing._key(path), sealing.PLAIN))
        default.start()
        self.addCleanup(default.stop)
        self.real = sealing.Sealed
        plain_build(self, Plain)
        self.sealer = self.real(self.keyring)

    def seal(self, **kw):
        result = seal_workspace.seal(self.path, self.sealer, **kw)
        sealing.attach(self.path, self.sealer)
        self.store._attach_sealer()
        return result



class SealCommandTests(Plain, test_sealing_memory.SealedMemoryBase):
    """Converting once, never half: a failed conversion leaves the workspace plain and marked
    unfinished, and running it again finishes it."""

    def raw(self, sql, params=()):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute(sql, params).fetchall()

    def keyed(self, view):
        """A view read before sealing as it reads after: every hash in it keyed."""
        text = re.sub(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])', lambda m: self.sealer.fingerprint('personal', m.group(0)),
                      json.dumps(view))
        return json.loads(text)

    def test_seal_converts_once_and_again_only_compacts(self):
        before = self.memory.view(self.owner)
        result = self.seal()
        self.assertFalse(result['already_sealed'])
        self.assertGreater(result['values_sealed'], 0)
        self.assertGreater(result['fingerprints_keyed'], 0)
        self.assertEqual(sealing.recorded(self.path), self.keyring.id)
        self.assertIsNone(seal_workspace.incomplete(self.path))
        self.assertFalse(Path(str(self.path) + '-wal').exists() and Path(str(self.path) + '-wal').stat().st_size)
        self.assertEqual(self.memory.view(self.owner), self.keyed(before))
        self.assertTrue(seal_workspace.seal(self.path, self.sealer)['already_sealed'])

    def test_a_failed_conversion_leaves_it_plain_and_marked_until_run_again(self):
        triggers = self.raw("SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name")
        with mock.patch.object(seal_workspace, '_check', side_effect=Fault('plain_fingerprint_left', 500)), \
                self.assertRaises(Fault) as caught:
            seal_workspace.seal(self.path, self.sealer)
        self.assertEqual(caught.exception.code, 'plain_fingerprint_left')
        self.assertIsNone(sealing.recorded(self.path))
        with closing(sqlite3.connect(self.path)) as db:
            self.assertFalse(sealing.holds_sealed_values(db))
        self.assertEqual(self.raw("SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name"), triggers)
        self.assertEqual(seal_workspace.incomplete(self.path), 'seal')
        self.assertTrue(b'Juniperhythe' in stored_bytes(self.path))
        self.assertFalse(self.seal()['already_sealed'])
        self.assertIsNone(seal_workspace.incomplete(self.path))
        self.assertFalse(b'Juniperhythe' in stored_bytes(self.path))

    def test_a_busy_database_is_not_called_finished(self):
        with mock.patch.object(seal_workspace, 'compact', return_value=False), self.assertRaises(Fault) as caught:
            seal_workspace.seal(self.path, self.sealer)
        self.assertEqual(caught.exception.code, 'workspace_busy')
        self.assertEqual(sealing.recorded(self.path), self.keyring.id)
        self.assertEqual(seal_workspace.incomplete(self.path), 'seal')
        self.assertTrue(self.seal()['already_sealed'])
        self.assertIsNone(seal_workspace.incomplete(self.path))

    def test_another_keyring_and_a_missing_area_are_refused(self):
        (self.root / 'other').mkdir()
        empty = self.real(test_sealing.keyring(self.root / 'other'))
        self.assertEqual(self.fault(lambda: seal_workspace.seal(self.path, empty)), ('unknown_area', 404))
        self.assertIsNone(seal_workspace.incomplete(self.path))
        self.seal()
        other = self.real(test_sealing.keyring(self.root / 'other-2', 'personal'))
        self.assertEqual(self.fault(lambda: seal_workspace.seal(self.path, other))[0], 'wrong_keyring')
        self.assertEqual(self.fault(lambda: seal_workspace.seal(self.path, sealing.PLAIN)), ('keyring_required', 423))

    def test_backups_made_before_sealing_are_sealed_with_it_and_restore(self):
        manifest = lifecycle.backup(self.store, self.owner, self.root / 'backups')
        before = self.memory.view(self.owner)
        copy = self.root / 'backups' / manifest['file']
        self.assertEqual((manifest['sealed'], manifest['encrypted']), (False, False))
        self.assertTrue(b'Juniperhythe' in copy.read_bytes())
        # A copy kept elsewhere is not converted, and is not put back into the sealed workspace.
        (self.root / 'elsewhere').mkdir()
        for part in (copy, copy.with_suffix('.json')):
            (self.root / 'elsewhere' / part.name).write_bytes(part.read_bytes())
        self.assertEqual(self.seal()['backups_sealed'], 1)
        sealed = json.loads(copy.with_suffix('.json').read_text())
        self.assertEqual((sealed['sealed'], sealed['encrypted'], sealed['keyring']), (True, True, self.keyring.id))
        self.assertEqual(sealed['sha256'], hashlib.sha256(copy.read_bytes()).hexdigest())
        self.assertEqual(self.raw('SELECT sha256 FROM lifecycle_backups'), [(sealed['sha256'],)])
        raw = stored_bytes(self.root / 'backups')
        self.assertFalse([w for w in test_sealing_memory.PRIVATE if w.encode() in raw])
        self.assertTrue(lifecycle.restore(copy, self.path)['encrypted'])
        self.store._attach_sealer()
        self.assertEqual(self.memory.view(self.owner), self.keyed(before))
        self.assertEqual(self.fault(lambda: lifecycle.restore(self.root / 'elsewhere' / copy.name, self.path))[0],
                         'workspace_not_sealed')
        self.assertTrue(lifecycle.backup(self.store, self.owner, self.root / 'backups')['sealed'])

    def fault(self, call):
        with self.assertRaises(Fault) as caught:
            call()
        return caught.exception.code, caught.exception.status


class CompactionTests(Plain, test_sealing_memory.SealedMemoryBase):
    """An absolute forget compacts the database and empties its log, in a plain workspace and
    a sealed one, and so does a restore that applies it again. Every connection here starts
    with SQLite's secure delete off, as some builds ship it (this one overwrites deleted bytes
    by default), so what is left in free pages shows."""

    NOTE_ONLY = (b'Hollowbeck', b'Ismerelda', b'Juniperhythe', b'Kestrelmoor')

    def setUp(self):
        real = sqlite3.connect

        def connect(*args, **kwargs):
            db = real(*args, **kwargs)
            db.execute('PRAGMA secure_delete=OFF')
            return db
        patched = mock.patch.object(sqlite3, 'connect', connect)
        patched.start()
        self.addCleanup(patched.stop)
        super().setUp()
        # A statement whose value is in no note, so the forget is its only copy's end.
        self.secret = self.accept('r9', 'status', 3, value='ask Quernhallow for the figures')

    def forget_absolutely(self, identity):
        self.memory.forget(self.owner, identity, {'version': self.claim(identity)['version'], 'absolute': True,
                                                  'confirm': identity})

    def left(self):
        raw = stored_bytes(self.path)
        return [word for word in self.NOTE_ONLY if word in raw]

    def test_an_absolute_forget_of_a_source_leaves_no_copy_in_the_file_or_its_log(self):
        self.assertEqual(self.left(), list(self.NOTE_ONLY))
        lifecycle.forget_source(self.store, self.owner, 'source', absolute=True)
        self.assertEqual(self.left(), [])

    def test_an_absolute_forget_of_a_statement_leaves_no_copy(self):
        self.assertTrue(b'Quernhallow' in stored_bytes(self.path))
        self.forget_absolutely(self.secret)
        self.assertFalse(b'Quernhallow' in stored_bytes(self.path))

    def test_sealed_a_forgotten_note_leaves_no_sealed_copy_either(self):
        self.seal()
        with closing(sqlite3.connect(self.path)) as db:
            bodies = [v.encode() for (v,) in db.execute('SELECT body FROM knowledge_notes')]
            value = db.execute('SELECT value FROM memory_claims WHERE id=?', (self.secret,)).fetchone()[0].encode()
        self.assertTrue(bodies and all(b in stored_bytes(self.path) for b in bodies + [value]))
        self.forget_absolutely(self.secret)
        lifecycle.forget_source(self.store, self.owner, 'source', absolute=True)
        raw = stored_bytes(self.path)
        self.assertFalse([b for b in bodies + [value] if b in raw])

    def test_a_restore_applies_it_again_and_compacts(self):
        backup = self.root / 'backups' / lifecycle.backup(self.store, self.owner, self.root / 'backups')['file']
        lifecycle.forget_source(self.store, self.owner, 'source', absolute=True)
        self.forget_absolutely(self.secret)
        forgotten = self.claim(self.secret)
        result = lifecycle.restore(backup, self.path)
        self.assertEqual(result['journal_entries_replayed'], 2)
        self.assertEqual(self.left(), [])
        self.assertFalse(b'Quernhallow' in stored_bytes(self.path))
        self.assertEqual(self.claim(self.secret), forgotten)


class ExportTests(Plain, test_sealing_memory.SealedMemoryBase):
    """A sealed workspace's export is sealed unless asked for plain, and ALFRED opens it again
    with the keyring."""

    def setUp(self):
        super().setUp()
        self.seal()

    def test_an_export_is_sealed_and_opens_with_the_keyring(self):
        result = export.export(self.store, self.owner, self.root / 'sealed')
        self.assertEqual((result['sealed'], result['keyring']), (True, self.keyring.id))
        names = {p.name for p in Path(result['directory']).iterdir()}
        self.assertEqual({n for n in names if not n.endswith(export.SEALED_SUFFIX)}, {export.SEALED_FILE, 'SHA256SUMS'})
        raw = stored_bytes(Path(result['directory']))
        self.assertFalse([w for w in test_sealing_memory.PRIVATE if w.encode() in raw])
        opened = export.open_export(result['directory'], self.sealer, self.root / 'opened')
        plain = export.export(self.store, self.owner, self.root / 'plain', plain=True)
        self.assertNotIn('sealed', plain)
        for name in ('statements.json', 'statements.md'):
            self.assertEqual((Path(opened['directory']) / name).read_bytes(), (Path(plain['directory']) / name).read_bytes())
        self.assertIn(b'Juniperhythe', (Path(plain['directory']) / 'statements.json').read_bytes())

    def test_a_sealed_export_is_refused_without_its_keyring_or_when_changed(self):
        directory = Path(export.export(self.store, self.owner, self.root / 'sealed')['directory'])
        other = self.real(test_sealing.keyring(self.root / 'other', 'personal'))
        for sealer, code in ((other, 'wrong_keyring'), (sealing.PLAIN, 'workspace_locked')):
            with self.assertRaises(Fault) as caught:
                export.opened_files(directory, sealer)
            self.assertEqual(caught.exception.code, code)
        changed = next(p for p in directory.iterdir() if p.name.endswith(export.SEALED_SUFFIX))
        changed.write_text(changed.read_text()[:-4] + 'AAAA')
        with self.assertRaises(Fault) as caught:
            export.opened_files(directory, self.sealer)
        self.assertEqual(caught.exception.code, 'export_checksum_mismatch')


class RotationTests(Plain, test_sealing_memory.SealedMemoryBase):
    """Rotating an area's key seals its values again under the new key, in the workspace and
    its backups, then deletes the old key: a copy made before can no longer be opened."""

    def setUp(self):
        super().setUp()
        self.seal()
        self.backup = self.root / 'backups' / lifecycle.backup(self.store, self.owner, self.root / 'backups')['file']
        self.before = self.root / 'before.sqlite'
        self.before.write_bytes(self.path.read_bytes())

    def versions(self, path):
        with closing(sqlite3.connect(path)) as db:
            return {v.split(':')[3] for t, (_, sealed, _) in sealing.TABLES.items() if sealing._has(db, t)
                    for c in sealed for (v,) in db.execute(f'SELECT {c} FROM {t} WHERE {c} IS NOT NULL')
                    if sealing.area_of(v) == 'personal'}

    def prints(self, path):
        with closing(sqlite3.connect(path)) as db:
            return sorted(db.execute('SELECT request_hash, note_hash, quote_hash FROM memory_claims ORDER BY id').fetchall())

    def test_rotation_reseals_then_retires_the_old_key(self):
        prints, before = self.prints(self.path), self.memory.view(self.owner)
        self.keyring.rotate_area('personal')
        result = seal_workspace.reseal(self.path, self.sealer, 'personal')
        self.assertEqual((result['key_versions_retired'], result['key_version'], result['backups_resealed']), (1, 2, 1))
        self.assertGreater(result['values_resealed'], 0)
        self.assertEqual(self.versions(self.path), {'2'})
        self.assertEqual(self.versions(self.backup), {'2'})
        self.assertEqual(self.prints(self.path), prints)
        stored = json.loads(keys.keyring_path(self.root).read_text())
        personal = next(a for a in stored['areas'] if a['id'] == 'personal')
        self.assertEqual(([k['version'] for k in personal['keys']], personal['retired_through']), ([2], 1))
        # Everything still opens, and a fingerprint still matches.
        self.assertEqual(self.memory.view(self.owner), before)
        self.assertEqual(self.capture.run(self.owner)['not_proposed']['already_proposed'], 1)
        self.assertEqual(json.loads(self.backup.with_suffix('.json').read_text())['sha256'],
                         hashlib.sha256(self.backup.read_bytes()).hexdigest())
        # The copy made before rotating holds only values sealed with the deleted key.
        with closing(sqlite3.connect(self.before)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT * FROM memory_claims WHERE value IS NOT NULL').fetchone()
            with self.assertRaises(Fault) as caught:
                sealing.open_row(sealing.Sealed(self.keyring), 'memory_claims', row)
        self.assertEqual((caught.exception.code, caught.exception.status), ('key_version_retired', 410))

    def test_an_interrupted_rotation_is_finished_by_running_it_again(self):
        self.keyring.rotate_area('personal')
        with mock.patch.object(self.keyring, 'retire_old_keys', side_effect=OSError('stopped')), \
                self.assertRaises(OSError):
            seal_workspace.reseal(self.path, self.sealer, 'personal')
        self.assertEqual(seal_workspace.incomplete(self.path), 'reseal')
        self.assertEqual(seal_workspace.reseal(self.path, self.sealer, 'personal')['key_versions_retired'], 1)
        self.assertIsNone(seal_workspace.incomplete(self.path))

    def export_versions(self, directory):
        return {p.read_text().split(':')[3] for p in Path(directory).iterdir() if p.name.endswith(export.SEALED_SUFFIX)}

    def test_rotation_seals_the_sealed_exports_it_wrote_again(self):
        written = Path(export.export(self.store, self.owner, self.root / 'sealed')['directory'])
        moved = Path(export.export(self.store, self.owner, self.root / 'moved')['directory'])
        moved = moved.rename(self.root / 'elsewhere')
        changed = Path(export.export(self.store, self.owner, self.root / 'changed')['directory'])
        edited = next(p for p in changed.iterdir() if p.name.endswith(export.SEALED_SUFFIX))
        edited.write_text(edited.read_text()[:-4] + 'AAAA')
        held = {p.name: p.read_bytes() for p in changed.iterdir()}
        damaged = Path(export.export(self.store, self.owner, self.root / 'damaged')['directory'])
        next(p for p in damaged.iterdir() if p.name.endswith(export.SEALED_SUFFIX)).unlink()
        plain = Path(export.export(self.store, self.owner, self.root / 'plain', plain=True)['directory'])
        readable = (plain / 'statements.json').read_bytes()
        self.keyring.rotate_area('personal')
        result = seal_workspace.reseal(self.path, self.sealer, 'personal')
        self.assertEqual((result['exports_resealed'], result['exports_not_resealed']), (1, 2))
        self.assertEqual({p.name: p.read_bytes() for p in changed.iterdir()}, held)
        self.assertEqual(self.export_versions(written), {'2'})
        opened = export.open_export(written, self.sealer, self.root / 'opened')
        self.assertEqual((Path(opened['directory']) / 'statements.json').read_bytes(), readable)
        # The plain export is left as it is, and one moved away holds only the deleted key.
        self.assertEqual((plain / 'statements.json').read_bytes(), readable)
        with self.assertRaises(Fault) as caught:
            export.opened_files(moved, self.sealer)
        self.assertEqual(caught.exception.code, 'key_version_retired')
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith('.')], [])

    def test_an_interrupted_export_swap_is_finished_by_running_it_again(self):
        written = Path(export.export(self.store, self.owner, self.root / 'sealed')['directory'])
        self.keyring.rotate_area('personal')
        rename = export.os.rename

        def stop_after_moving_it_aside(source, target):
            rename(source, target)
            if Path(source) == written:
                raise OSError('stopped')
        with mock.patch.object(export.os, 'rename', stop_after_moving_it_aside), self.assertRaises(OSError):
            seal_workspace.reseal(self.path, self.sealer, 'personal')
        self.assertFalse(written.exists())
        self.assertEqual(seal_workspace.incomplete(self.path), 'reseal')
        self.assertEqual(seal_workspace.reseal(self.path, self.sealer, 'personal')['exports_resealed'], 1)
        self.assertEqual(self.export_versions(written), {'2'})
        self.assertIn('statements.json', export.opened_files(written, self.sealer))
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith('.')], [])

    def test_an_area_rotates_again_and_again(self):
        before = self.memory.view(self.owner)
        rotations = 17  # one more than the keys an area may hold at once
        for _ in range(rotations):
            self.keyring.rotate_area('personal')
            seal_workspace.reseal(self.path, self.sealer, 'personal')
        newest = rotations + 1
        self.assertEqual(self.versions(self.path), {str(newest)})
        self.assertEqual(self.memory.view(self.owner), before)
        with keys.Keyring.read(keys.keyring_path(self.root)).unlock(SyntheticUnlock()) as again:
            self.assertEqual(again.area_key('personal')[0], newest)
            for version, code in ((1, 'key_version_retired'), (newest - 1, 'key_version_retired'),
                                  (newest + 1, 'unknown_key_version')):
                with self.assertRaises(Fault) as caught:
                    again.area_key('personal', version)
                self.assertEqual(caught.exception.code, code, version)


class DeskStartTests(unittest.TestCase):
    """A sealed desk workspace unlocks its keyring before anything else, or refuses to start;
    a plain one starts as before."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        default = mock.patch.object(sealing, 'for_path', lambda path: sealing._attached.get(sealing._key(path), sealing.PLAIN))
        default.start()
        self.addCleanup(default.stop)
        self.root = Path(tmp.name)
        self.home = self.root / 'home'
        desk.init_demo(self.home)
        self.addCleanup(sealing.detach, self.home / 'desk.sqlite')
        keys.Keyring.create(keys.keyring_path(self.home), SyntheticUnlock())

    def unlocked(self, keyring, **kw):
        return keys.Keyring.read(keys.keyring_path(self.home)).unlock(SyntheticUnlock()), 'synthetic test key'

    def run_desk(self, *arguments, unlock=None):
        output = io.StringIO()
        with mock.patch.object(keys, 'unlock', unlock or self.unlocked), \
                mock.patch.object(sys, 'argv', ['alfred.desk', *arguments]), redirect_stdout(output):
            try:
                desk.main()
                code = 0
            except SystemExit as exc:
                code = exc.code
        sealing.detach(self.home / 'desk.sqlite')
        return code, output.getvalue()

    def locked(self, keyring, **kw):
        raise Fault('no_unlock_available', 423)

    def export(self, name, **kw):
        return self.run_desk('export', '--data-dir', str(self.home), '--export-dir', str(self.root / name), **kw)

    def test_a_plain_workspace_starts_without_unlocking(self):
        code, output = self.export('plain', unlock=self.locked)
        self.assertEqual(code, 0, output)
        self.assertIn('Not a backup and not encrypted', output)

    def test_sealed_it_unlocks_first_or_refuses(self):
        code, output = self.run_desk('seal', '--data-dir', str(self.home))
        self.assertEqual(code, 0, output)
        self.assertIn('Sealed the workspace', output)
        self.assertIn('Added the personal area', output)
        code, output = self.export('refused', unlock=self.locked)
        self.assertEqual((code, output.splitlines()[0]), (1, 'Cannot start: workspace_locked'))
        self.assertFalse((self.root / 'refused').exists())
        code, output = self.export('sealed')
        self.assertEqual(code, 0, output)
        self.assertIn('open only with this workspace', output)
        code, output = self.run_desk('export', '--plain', '--data-dir', str(self.home),
                                     '--export-dir', str(self.root / 'readable'))
        self.assertIn('Warning: you asked for a plain export', output)
        keys.keyring_path(self.home).rename(self.root / 'moved.json')
        code, output = self.export('no-keyring')
        self.assertEqual((code, output.splitlines()[0]), (1, 'Cannot start: workspace_locked'))

    def test_serve_checks_its_settings_before_it_unlocks(self):
        self.assertEqual(self.run_desk('seal', '--data-dir', str(self.home))[0], 0)
        asked = []

        def unlock(keyring, **kw):
            asked.append(True)
            return self.unlocked(keyring, **kw)
        for extra, code in ((['--port', '80'], 'invalid_port'),
                            (['--hub', 'hermes', '--cloud-area', 'personal'], 'hermes_settings_required')):
            output = self.run_desk('serve', '--data-dir', str(self.home), *extra, unlock=unlock)[1]
            self.assertEqual(output.splitlines()[0], f'Cannot start: {code}', extra)
        self.assertEqual(asked, [], 'the keyring was unlocked for settings that could never start')

    def test_a_sealed_export_is_never_opened_into_a_vault(self):
        self.assertEqual(self.run_desk('seal', '--data-dir', str(self.home))[0], 0)
        self.assertEqual(self.export('sealed')[0], 0)
        # A vault named on the command line, with nothing in it that marks it as one.
        vault = self.root / 'notes'
        vault.mkdir()
        (self.home / 'vault').mkdir(exist_ok=True)
        for chosen, inside in ((['--vault', str(vault)], vault), ([], self.home / 'vault')):
            code, output = self.run_desk('open-export', '--data-dir', str(self.home), *chosen,
                                         '--sealed-export', str(self.root / 'sealed'), '--export-dir', str(inside / 'opened'))
            self.assertEqual((code, output.splitlines()[0]), (1, 'Cannot start: export_destination_inside_vault'), chosen)
            self.assertFalse((inside / 'opened').exists())
        code, output = self.run_desk('open-export', '--data-dir', str(self.home), '--vault', str(vault),
                                     '--sealed-export', str(self.root / 'sealed'), '--export-dir', str(self.root / 'opened'))
        self.assertEqual(code, 0, output)
        self.assertTrue((self.root / 'opened' / 'statements.json').is_file())

    def test_rotating_the_area_keeps_a_sealed_export_openable(self):
        self.assertEqual(self.run_desk('seal', '--data-dir', str(self.home))[0], 0)
        self.assertEqual(self.export('sealed')[0], 0)
        code, output = self.run_desk('rotate-area', '--data-dir', str(self.home), '--area', 'personal')
        self.assertEqual(code, 0, output)
        self.assertIn('1 sealed exports sealed again', output)
        self.assertIn('copied anywhere else before now can no longer be opened', output)
        code, output = self.run_desk('open-export', '--data-dir', str(self.home), '--sealed-export', str(self.root / 'sealed'),
                                     '--export-dir', str(self.root / 'opened'))
        self.assertEqual(code, 0, output)
        self.assertTrue((self.root / 'opened' / 'statements.json').is_file())

    def test_an_unfinished_seal_is_refused_at_start(self):
        seal_workspace._mark(self.home / 'desk.sqlite', seal_workspace.MARKER, 'x')
        code, output = self.export('refused')
        self.assertEqual((code, output.splitlines()[0]), (1, 'Cannot start: sealing_incomplete'))
        code, output = self.run_desk('seal', '--data-dir', str(self.home))
        self.assertEqual(code, 0, output)
        self.assertEqual(self.export('after')[0], 0)

class Converted:
    """The workspace is built plain, then switched on with ``seal``; every check of the
    sealed workspace must then hold as if it had been sealed from the start."""

    def setUp(self):
        real = sealing.Sealed
        plain_build(self, Converted)
        self.assertFalse(self.store.sealer.sealed)
        self.sealer = real(self.keyring)
        self.converted = seal_workspace.seal(self.path, self.sealer, cache_dir=getattr(self, 'cache_root', None))
        sealing.attach(self.path, self.sealer)
        self.store._attach_sealer()


class ConvertedNotesAtRestTests(Converted, test_sealing.SealedAtRestTests):
    pass


class ConvertedMemoryAtRestTests(Converted, test_sealing_memory.SealedMemoryAtRestTests):
    pass


class ConvertedRecordsAtRestTests(Converted, test_sealing_records.SealedRecordsAtRestTests):
    def setUp(self):
        super().setUp()
        # The playback was recorded before sealing; what ALFRED returns for it now is the keyed hash.
        self.spoken = self.voice.history(self.owner, self.turns[1])['playbacks'][0]


class ConvertedWorkAtRestTests(Converted, test_sealing_work.SealedWorkAtRestTests):
    def setUp(self):
        super().setUp()
        self.assertTrue(self.converted['cache_emptied'])
        self.assertFalse([p for p in (self.cache_root / 'objects').rglob('*') if p.is_file()])
        # The cache is emptied by sealing and fills again, sealed, as results are read.
        for job in (self.job, self.second):
            self.envelope(job)


# Hashes over a whole request or record made before sealing: they are keyed as they are, so a
# request repeated after sealing with the same id is refused as a collision (docs/ENCRYPTION.md).
KEYED_AS_MADE = {('memory_claims', 'request_hash'), ('actions', 'fingerprint'), ('events', 'fingerprint'),
                 ('jobs', 'fingerprint'), ('brain_tasks', 'packet_sha256')}
# What a worker was sent and returned, kept as it was, and the result's address wherever it is
# copied: a worker sent plain hashes before sealing returned different bytes.
WORKER_RECORD = {('jobs', 'parameters'), ('artefacts', 'body'), ('artefacts', 'sha256'), ('jobs', 'result_artefact'),
                 ('brain_results', 'envelope_sha256'), ('job_events', 'detail'), ('verification_runs', 'report'),
                 ('verification_runs', 'report_sha256'), ('verification_results', 'last_run_sha256')}
# The folders' own inode numbers and file times, and how long an answer took.
ENVIRONMENT = re.compile(r'(elapsed_ms\\*": )\d+')


class SameAsSealedFromTheStartTests(unittest.TestCase):
    """The same invented workspace, sealed from the start and converted by ``seal``, with one
    keyring, one clock and fixed random ids: every row, opened, is the same, apart from hashes
    made over whole requests before sealing and the record of what a worker was sent."""

    def build(self, base, converted):
        cls = type('Build', (Converted, base) if converted else (base,), {'runTest': lambda self: None})
        module = sys.modules[base.__module__]
        count = itertools.count()
        with mock.patch.object(module, 'keyring', lambda root, *areas: self.keyring), \
                mock.patch('time.time', lambda: 1_800_000_000.0), \
                mock.patch.object(secrets, 'token_hex', lambda n=16: f'{next(count):0{2 * n}x}'), \
                mock.patch.object(secrets, 'token_urlsafe', lambda n=32: base64.urlsafe_b64encode(
                    hashlib.sha256(b'%d' % next(count)).digest()[:n]).rstrip(b'=').decode()):
            case = cls()
            case.setUp()
        self.addCleanup(case.tearDown)
        self.addCleanup(case.doCleanups)
        sealer = sealing.Sealed(self.keyring)
        rows = {}
        with closing(sqlite3.connect(case.path)) as db:
            db.row_factory = sqlite3.Row
            for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='sealing' ORDER BY name"):
                found = []
                for row in db.execute(f'SELECT * FROM {table} ORDER BY rowid'):
                    opened = sealing.open_row(sealer, table, row) if table in sealing.TABLES else dict(row)
                    opened = {c: v for c, v in opened.items() if c != 'inode' and (table, c) != ('knowledge_notes', 'modified')}
                    text = json.dumps(opened, default=lambda b: b.hex()).replace(str(case.root), '<root>')
                    found.append(json.loads(ENVIRONMENT.sub(r'\g<1>0', text)))
                rows[table] = found
        return rows

    def differences(self, base):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.keyring = test_sealing.keyring(tmp.name, 'personal', 'client-a')
        native, converted = self.build(base, False), self.build(base, True)
        self.assertEqual({t: len(r) for t, r in native.items()}, {t: len(r) for t, r in converted.items()})
        return {(table, column) for table in native for one, other in zip(native[table], converted[table])
                for column in one if one[column] != other[column]}

    def test_notes(self):
        self.assertEqual(self.differences(test_sealing.SealedAtRestTests), set())

    def test_reviewed_memory_and_capture(self):
        self.assertEqual(self.differences(test_sealing_memory.SealedMemoryBase), {('memory_claims', 'request_hash')})

    def test_conversations_records_drafts_and_actions(self):
        self.assertEqual(self.differences(test_sealing_records.SealedRecordsBase), {('actions', 'fingerprint')})

    def test_jobs_brain_goals_learning_and_desk(self):
        self.assertEqual(self.differences(test_sealing_work.SealedWorkBase), KEYED_AS_MADE - {
            ('memory_claims', 'request_hash'), ('actions', 'fingerprint')} | WORKER_RECORD)

HEX = re.compile(rb'[0-9a-f]{64}')
# The one plain SHA-256 a sealed workspace keeps: an access key's, which ALFRED checks a
# presented key against. The key is random, so its hash says nothing about the owner's text.
READABLE_HASHES = {('credentials', 'digest')}


def calendar_export(case):
    """The notes workspace also gets a sync conflict and a connector import."""
    case.write("Marrowgate plan (Halloway's conflicted copy 2026-10-17).md", 'Zanzibar by Peregrine, edited elsewhere.')
    case.reader.scan()
    connectors.initialise(case.store)
    made = connectors.create_instance(case.store, case.owner, 'ics-export', 'Wintermere calendar')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Example//Synthetic//EN', 'BEGIN:VEVENT', 'UID:vellichor-1',
             'DTSTAMP:20261001T120000Z', 'DTSTART;TZID=Europe/London:20261014T090000', 'SUMMARY:Thistledown review',
             'END:VEVENT', 'END:VCALENDAR', '']
    (case.root / 'calendar.ics').write_bytes('\r\n'.join(lines).encode())
    connectors.run_import(case.store, case.owner, made['bearer'], case.root / 'calendar.ics')


def evidence_draft(case):
    """The desk's workspace also gets a draft made from one of its observations."""
    seq = case.store.desk_state(case.owner)['events'][0]['seq']
    case.store.propose_from_evidence(case.owner, {'event_seq': seq, 'text': 'Ask Mirewhistle about the brief.',
                                                  'request_id': 'evidence-1'})


class FinalScanTests(unittest.TestCase):
    """Each invented workspace of parts 1 to 4, built plain with a backup, switched on with
    ``seal`` (the desk's own command for the desk's workspace), read through every view and
    exported: no private word, and no plain SHA-256 it held, is left in any file it keeps."""

    def scan(self, base, words, extra=None):
        case = type('Build', (Plain, base), {'runTest': lambda self: None})()
        case.setUp()
        self.addCleanup(case.tearDown)
        self.addCleanup(case.doCleanups)
        if extra:
            extra(case)
        lifecycle.backup(case.store, case.owner, case.root / 'backups')
        with closing(sqlite3.connect(case.path)) as db:
            covered = {t for t in sealing.TABLES if sealing._has(db, t) and db.execute(f'SELECT 1 FROM {t}').fetchone()}
            readable = {v.encode() for t, c in READABLE_HASHES for (v,) in db.execute(f'SELECT {c} FROM {t} WHERE {c} IS NOT NULL')}
            # Every SHA-256 the plain workspace holds anywhere, and the hash of every id a source chose.
            hashes = {m for t in seal_workspace._tables(db) for row in db.execute(f'SELECT * FROM {t}')
                      for v in tuple(row) if isinstance(v, str) for m in HEX.findall(v.encode())}
            hashes |= {hashlib.sha256(v.encode()).hexdigest().encode() for t, cs in sealing.KEYED_IDS.items()
                       if sealing._has(db, t) for c in cs for (v,) in db.execute(f'SELECT {c} FROM {t} WHERE {c} IS NOT NULL')}
            ids = {v for t, cs in sealing.KEYED_IDS.items() if sealing._has(db, t) for c in cs
                   for (v,) in db.execute(f'SELECT {c} FROM {t} WHERE {c} IS NOT NULL')}
        self.assertTrue(hashes - readable)
        if base is test_sealing_work.SealedWorkBase:
            # The desk's workspace is switched on by its own command, unlocked as it would be at start.
            unlocked = lambda keyring, **kw: (keys.Keyring.read(keys.keyring_path(case.root)).unlock(SyntheticUnlock()), 'test')
            output = io.StringIO()
            with mock.patch.object(keys, 'unlock', unlocked), mock.patch.object(sys, 'argv', [
                    'alfred.desk', 'seal', '--data-dir', str(case.root)]), redirect_stdout(output):
                desk.main()
            self.assertIn('Sealed the workspace', output.getvalue())
            sealing.attach(case.path, case.sealer)
            case.store._attach_sealer()
        else:
            self.assertFalse(case.seal()['already_sealed'])
        for read in getattr(case, 'reads', lambda: [])():
            read()
        export.export(case.store, case.owner, case.root / 'export')
        raw = stored_bytes(case.path, case.root / 'backups', case.root / 'export', case.root / 'job-cache')
        self.assertIn(b'alfred-seal:1:personal:', raw)
        leaked = [form for word in (*words, *ids) for form in {word, word.lower(), word.upper()} if form.encode() in raw]
        self.assertFalse(leaked, f'private text in the stored files: {leaked}')
        left = {h for h in hashes - readable if any(h[:n] in raw for n in (16, 24, 32, 40, 64))}
        self.assertFalse(left, 'plain hashes in the stored files')
        return covered

    def test_nothing_private_is_left_in_any_file(self):
        covered = set()
        for base, words, extra in ((test_sealing.SealedAtRestTests, test_sealing.PRIVATE, calendar_export),
                                   (test_sealing_memory.SealedMemoryBase, test_sealing_memory.PRIVATE, None),
                                   (test_sealing_records.SealedRecordsBase, test_sealing_records.PRIVATE, None),
                                   (test_sealing_work.SealedWorkBase, test_sealing_work.PRIVATE, evidence_draft)):
            with self.subTest(base.__name__):
                covered |= self.scan(base, words, extra)
        # Every table the register names held something to find.
        self.assertEqual(set(sealing.TABLES) - covered, set())

if __name__ == '__main__':
    unittest.main()
