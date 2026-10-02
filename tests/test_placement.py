"""MEM-014 placement guard: live files never sit in a synced folder, Git tree or vault.

Temporary directories holding the documented marker files stand in for the sync
tools. Nothing is synced and no sync client runs.
"""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from alfred import desk
from alfred.desk import init_demo, serve
from alfred.placement import (IN_GIT_WORKING_TREE, IN_SYNC_FOLDER, INSIDE_VAULT, PlacementFault,
                              check_data_directory, contains, locate)

GIT = '.' + 'git'


class PlacementTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def refused(self, data_dir, code, vaults=()):
        with self.assertRaises(PlacementFault) as raised:
            check_data_directory(data_dir, vaults)
        self.assertEqual((raised.exception.code, raised.exception.status), (code, 409))
        detail = raised.exception.detail
        for words in ('database', 'write-ahead log', 'lifecycle journal', 'access keys', 'job cache',
                      'There is no override', 'alfred.desk backup', 'safe to sync'):
            self.assertIn(words, detail)
        return detail

    def test_each_documented_sync_marker_is_found_in_an_ancestor(self):
        markers = [('.stfolder', True), ('.stignore', False), ('.stversions', True), ('.dropbox', False),
                   ('.dropbox.cache', True), ('.owncloudsync.log', False), ('.csync_journal.db', False),
                   ('.sync_0a1b2c3d4e5f.db', False), ('._sync_0a1b2c3d4e5f.db', False)]
        for name, directory in markers:
            with self.subTest(marker=name):
                base = self.root / ('synced' + name)
                base.mkdir()
                (base / name).mkdir() if directory else (base / name).write_text('')
                detail = self.refused(base / 'deep' / 'alfred', IN_SYNC_FOLDER)
                self.assertIn(name, detail)
                self.assertIn(str(base), detail)

    def test_git_working_tree_and_obsidian_vault_are_refused(self):
        (self.root / 'repo' / GIT).mkdir(parents=True)
        self.assertIn('Git working tree', self.refused(self.root / 'repo' / 'data', IN_GIT_WORKING_TREE))
        (self.root / 'notes' / '.obsidian').mkdir(parents=True)
        self.assertIn('Obsidian vault', self.refused(self.root / 'notes' / 'alfred', INSIDE_VAULT))

    def test_configured_vault_may_not_hold_the_data_directory(self):
        vault = self.root / 'vault'; vault.mkdir()
        self.refused(vault / 'alfred', INSIDE_VAULT, (vault,))
        self.refused(vault, INSIDE_VAULT, (vault,))
        # The demo layout keeps its synthetic vault inside the data directory, which is allowed.
        self.assertFalse(check_data_directory(self.root / 'home', (self.root / 'home' / 'vault',))['refused'])

    def test_macos_cloud_paths_are_refused_by_path(self):
        for path in (self.root / 'Library' / 'Mobile Documents' / 'com~apple~CloudDocs' / 'alfred',
                     self.root / 'Library' / 'CloudStorage' / 'OneDrive-Example' / 'alfred'):
            with self.subTest(path=path):
                self.refused(path, IN_SYNC_FOLDER)
        self.assertIsNone(locate(self.root / 'Library' / 'CloudStorageNotes' / 'alfred'))
        self.assertIsNone(locate(self.root / 'Documents' / 'Mobile Documents' / 'alfred'))

    def test_symlinks_are_checked_both_as_given_and_where_they_lead(self):
        synced = self.root / 'synced'; synced.mkdir(); (synced / '.stfolder').mkdir()
        local = self.root / 'local'; local.mkdir()
        (self.root / 'into-sync').symlink_to(synced)
        self.refused(self.root / 'into-sync' / 'alfred', IN_SYNC_FOLDER)
        (synced / 'out').symlink_to(local)
        self.refused(synced / 'out', IN_SYNC_FOLDER)
        self.assertTrue(contains(synced, self.root / 'into-sync' / 'alfred'))

    def test_a_symlink_loop_does_not_break_the_check(self):
        (self.root / 'a').symlink_to(self.root / 'b')
        (self.root / 'b').symlink_to(self.root / 'a')
        self.assertFalse(check_data_directory(self.root / 'a' / 'alfred')['refused'])
        (self.root / '.stfolder').mkdir()
        self.refused(self.root / 'a' / 'alfred', IN_SYNC_FOLDER)

    def test_a_sync_root_inside_the_data_directory_is_found(self):
        home = self.root / 'home'
        (home / 'job-cache' / '.stfolder').mkdir(parents=True)
        self.refused(home, IN_SYNC_FOLDER)

    def test_ordinary_local_folder_is_accepted(self):
        result = check_data_directory(self.root / 'local' / 'alfred')
        self.assertFalse(result['refused'])
        self.assertIn('job cache', result['artefacts'])
        self.assertIsNone(locate(self.root))

    def test_init_refuses_before_creating_anything(self):
        synced = self.root / 'Dropbox'; synced.mkdir(); (synced / '.dropbox').write_text('{}')
        with self.assertRaises(PlacementFault):
            init_demo(synced / 'alfred')
        self.assertEqual(list(synced.iterdir()), [synced / '.dropbox'])

    def test_serve_refuses_before_taking_the_lock(self):
        home = self.root / 'home'
        init_demo(home)
        (self.root / '.stfolder').mkdir()
        with self.assertRaises(PlacementFault) as raised:
            serve(home, 0)
        self.assertEqual(raised.exception.code, IN_SYNC_FOLDER)
        self.assertFalse((home / 'desk.lock').exists())

    def test_serve_refuses_a_vault_that_holds_the_data_directory(self):
        vault = self.root / 'vault'; home = vault / 'alfred'
        init_demo(home)
        with self.assertRaises(PlacementFault) as raised:
            serve(home, 0, vault=vault)
        self.assertEqual(raised.exception.code, INSIDE_VAULT)
        self.assertFalse((home / 'desk.lock').exists())


class PlacementCommandLineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        mask = os.umask(0o077); os.umask(mask)
        self.addCleanup(os.umask, mask)

    def run_desk(self, *arguments):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['alfred.desk', *arguments]), contextlib.redirect_stdout(output):
            try:
                desk.main()
                code = 0
            except SystemExit as exc:
                code = exc.code
        return code, output.getvalue()

    def test_init_prints_why_and_the_consistent_alternative(self):
        synced = self.root / 'Sync'; synced.mkdir(); (synced / '.stfolder').mkdir()
        code, output = self.run_desk('init', '--data-dir', str(synced / 'alfred'))
        self.assertEqual(code, 1)
        self.assertIn('Cannot start: data_directory_in_sync_folder', output)
        self.assertIn('a Syncthing folder', output)
        self.assertIn('python3 -m alfred.desk backup', output)
        self.assertFalse((synced / 'alfred').exists())

    def test_backup_still_works_so_a_synced_home_can_be_moved_out(self):
        home = self.root / 'home'
        init_demo(home)
        (self.root / '.dropbox.cache').mkdir()
        code, output = self.run_desk('serve', '--data-dir', str(home), '--port', '18765')
        self.assertEqual(code, 1)
        self.assertIn('a Dropbox folder', output)
        code, output = self.run_desk('restore', '--data-dir', str(home), '--backup-file', str(home / 'none.sqlite'))
        self.assertEqual(code, 1)
        self.assertIn('Cannot start: data_directory_in_sync_folder', output)
        code, output = self.run_desk('backup', '--data-dir', str(home))
        self.assertEqual(code, 0, output)
        self.assertIn('Backup written:', output)
        self.assertEqual(len(list((home / 'backups').glob('alfred-*.sqlite'))), 1)


if __name__ == '__main__':
    unittest.main()
