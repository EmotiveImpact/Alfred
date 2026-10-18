"""The full-disk encryption check at start (master plan phase 1, alfred/disk_encryption.py).

No real disk, FileVault or LUKS volume is needed: each test builds a small fake /sys and
/proc tree, or a fake command runner that answers as fdesetup and diskutil do. The real
`serve` test reads this machine's own answer first, so it holds wherever it runs. These
tests prove that:

* on macOS, FileVault on, off, still encrypting and still decrypting are told apart, a
  folder on another volume is asked about that volume, and a missing or failing command is
  "not confirmed", never "on";
* on Linux, a LUKS (dm-crypt) layer is found directly, under LVM and under software RAID,
  through a btrfs device number, and a plain partition reads as off; memory, network and
  ZFS folders are "not confirmed";
* other systems are "not confirmed";
* the start-up lines say what was found for the data folder and the vault, once when both
  share a disk, and `require` refuses to start unless every folder is on an encrypted disk.
"""
from __future__ import annotations
import os
from pathlib import Path
import plistlib
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from alfred import disk_encryption as de
from alfred.local import Fault

REPOSITORY = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class FakeStat:
    def __init__(self, devices):
        self.devices = devices

    def __call__(self, path):
        for prefix, (dev, rdev) in sorted(self.devices.items(), key=lambda kv: -len(kv[0])):
            if str(path) == prefix or str(path).startswith(prefix.rstrip('/') + '/'):
                return mock.Mock(st_dev=dev, st_rdev=rdev)
        raise FileNotFoundError(path)


def runner(answers):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        answer = answers.get(argv[0])
        if answer is None:
            raise FileNotFoundError(argv[0])
        if isinstance(answer, Exception):
            raise answer
        code, out = answer(argv) if callable(answer) else answer
        return subprocess.CompletedProcess(argv, code, out, b'' if isinstance(out, bytes) else '')
    run.calls = calls
    return run


class LinuxTree:
    """A fake /sys/dev/block and /proc/self/mountinfo."""

    def __init__(self, root):
        self.sys, self.proc = root / 'sys', root / 'proc'
        (self.sys / 'devices').mkdir(parents=True)
        (self.sys / 'dev' / 'block').mkdir(parents=True)
        (self.proc / 'self').mkdir(parents=True)
        self.mounts([])

    def device(self, name, number, *, dm_uuid=None, slaves=(), loop=False):
        folder = self.sys / 'devices' / name
        folder.mkdir()
        if dm_uuid is not None:
            (folder / 'dm').mkdir()
            (folder / 'dm' / 'uuid').write_text(dm_uuid + '\n')
        (folder / 'slaves').mkdir()
        for slave in slaves:
            (folder / 'slaves' / slave).symlink_to(self.sys / 'devices' / slave)
        if loop:
            (folder / 'loop').mkdir()
            (folder / 'loop' / 'backing_file').write_text('/srv/disk.img\n')
        (self.sys / 'dev' / 'block' / number).symlink_to(folder)

    def mounts(self, rows):
        (self.proc / 'self' / 'mountinfo').write_text(''.join(
            f'{i} 1 {number} / {point} rw,relatime shared:1 - {fstype} {source} rw\n'
            for i, (number, point, fstype, source) in enumerate(rows, 20)))

    def check(self, path, stat):
        return de.check(path, system='linux', sysfs=self.sys, proc=self.proc, stat=stat, realpath=lambda p: str(p))


def dev(major, minor):
    return os.makedev(major, minor)


class MacTests(unittest.TestCase):
    def check(self, answers, path='/Users/owner/alfred', mount='/'):
        run = runner(answers)
        result = de.check(path, system='darwin', run=run, realpath=lambda p: str(p),
                          ismount=lambda p: str(p) in (mount, '/'))
        return result, run.calls

    def test_filevault_on(self):
        result, calls = self.check({'/usr/bin/fdesetup': (0, 'FileVault is On.\n')})
        self.assertEqual((result.state, result.method), ('on', 'FileVault'))
        self.assertEqual(calls, [['/usr/bin/fdesetup', 'status']])

    def test_filevault_off(self):
        result, _ = self.check({'/usr/bin/fdesetup': (0, 'FileVault is Off.\n')})
        self.assertEqual((result.state, result.method), ('off', 'FileVault'))

    def test_still_encrypting_counts_as_on_and_says_so(self):
        result, _ = self.check({'/usr/bin/fdesetup': (0, 'FileVault is On.\nEncryption in progress: Percent completed = 41.2\n')})
        self.assertEqual(result.state, 'on')
        self.assertIn('still encrypting', result.detail)

    def test_decrypting_counts_as_off(self):
        result, _ = self.check({'/usr/bin/fdesetup': (0, 'FileVault is On.\nDecryption in progress: Percent completed = 10.0\n')})
        self.assertEqual(result.state, 'off')
        self.assertIn('being turned off', result.detail)

    def test_the_data_volume_of_the_boot_disk_asks_fdesetup(self):
        result, calls = self.check({'/usr/bin/fdesetup': (0, 'FileVault is On.\n')},
                                   path='/System/Volumes/Data/owner', mount='/System/Volumes/Data')
        self.assertEqual(result.state, 'on')
        self.assertEqual(calls, [['/usr/bin/fdesetup', 'status']])

    def test_another_volume_asks_diskutil_about_that_volume(self):
        on = plistlib.dumps({'FileVault': True, 'MountPoint': '/Volumes/Work'})
        result, calls = self.check({'/usr/sbin/diskutil': (0, on)}, path='/Volumes/Work/alfred', mount='/Volumes/Work')
        self.assertEqual((result.state, result.method), ('on', 'FileVault'))
        self.assertEqual(calls, [['/usr/sbin/diskutil', 'info', '-plist', '/Volumes/Work']])
        off = plistlib.dumps({'FileVault': False})
        result, _ = self.check({'/usr/sbin/diskutil': (0, off)}, path='/Volumes/Work/alfred', mount='/Volumes/Work')
        self.assertEqual(result.state, 'off')

    def test_a_volume_that_does_not_say_is_not_confirmed(self):
        result, _ = self.check({'/usr/sbin/diskutil': (0, plistlib.dumps({'VolumeName': 'Work'}))},
                               path='/Volumes/Work/alfred', mount='/Volumes/Work')
        self.assertEqual(result.state, 'unknown')

    def test_missing_failing_slow_or_strange_commands_are_never_on(self):
        for answer in (None, (1, ''), subprocess.TimeoutExpired(['fdesetup'], 5), PermissionError('denied'),
                       (0, 'Something else entirely\n'), (0, '')):
            with self.subTest(answer=answer):
                answers = {} if answer is None else {'/usr/bin/fdesetup': answer}
                result, _ = self.check(answers)
                self.assertEqual(result.state, 'unknown')
        result, _ = self.check({'/usr/sbin/diskutil': (0, b'not a plist')}, path='/Volumes/Work/a', mount='/Volumes/Work')
        self.assertEqual(result.state, 'unknown')

    def test_commands_are_bounded_and_take_no_shell(self):
        seen = {}

        def run(argv, **kwargs):
            seen.update(kwargs, argv=argv)
            return subprocess.CompletedProcess(argv, 0, 'FileVault is On.\n', '')
        de.check('/Users/owner', system='darwin', run=run, realpath=lambda p: str(p), ismount=lambda p: str(p) == '/')
        self.assertEqual(seen['timeout'], de.TIMEOUT)
        self.assertFalse(seen.get('shell', False))
        self.assertIs(seen['check'], False)
        self.assertEqual(seen['stdin'], subprocess.DEVNULL)


class LinuxTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tree = LinuxTree(Path(tmp.name))

    def test_a_luks_volume_is_on(self):
        self.tree.device('nvme0n1p2', '259:2')
        self.tree.device('dm-0', '253:0', dm_uuid='CRYPT-LUKS2-0a1b2c3d-root', slaves=('nvme0n1p2',))
        result = self.tree.check('/home/owner/alfred', FakeStat({'/': (dev(253, 0), 0)}))
        self.assertEqual((result.state, result.method), ('on', 'LUKS (dm-crypt)'))

    def test_lvm_on_luks_is_on_and_luks_on_one_of_two_raid_members_is_not(self):
        self.tree.device('sda2', '8:2')
        self.tree.device('dm-0', '253:0', dm_uuid='CRYPT-LUKS2-0a1b-luks', slaves=('sda2',))
        self.tree.device('dm-1', '253:1', dm_uuid='LVM-aaaa', slaves=('dm-0',))
        result = self.tree.check('/srv/alfred', FakeStat({'/': (dev(253, 1), 0)}))
        self.assertEqual(result.state, 'on')
        self.tree.device('sdb1', '8:17')
        self.tree.device('sdc1', '8:33')
        self.tree.device('dm-2', '253:2', dm_uuid='CRYPT-LUKS2-0a1c-half', slaves=('sdb1',))
        self.tree.device('md0', '9:0', slaves=('dm-2', 'sdc1'))
        result = self.tree.check('/data/alfred', FakeStat({'/': (dev(9, 0), 0)}))
        self.assertEqual(result.state, 'off')
        self.tree.device('sdd1', '8:49')
        self.tree.device('dm-3', '253:3', dm_uuid='CRYPT-LUKS2-0a1d-other', slaves=('sdd1',))
        self.tree.device('md1', '9:1', slaves=('dm-2', 'dm-3'))
        result = self.tree.check('/data/alfred', FakeStat({'/': (dev(9, 1), 0)}))
        self.assertEqual(result.state, 'on')

    def test_a_plain_partition_is_off_and_says_what_it_cannot_see(self):
        self.tree.device('sda1', '8:1')
        result = self.tree.check('/home/owner/alfred', FakeStat({'/': (dev(8, 1), 0)}))
        self.assertEqual((result.state, result.method), ('off', 'LUKS (dm-crypt)'))
        self.assertIn('fscrypt', result.detail)

    def test_a_non_crypt_device_mapper_layer_alone_is_off(self):
        self.tree.device('sda3', '8:3')
        self.tree.device('dm-4', '253:4', dm_uuid='LVM-bbbb', slaves=('sda3',))
        result = self.tree.check('/home/owner', FakeStat({'/': (dev(253, 4), 0)}))
        self.assertEqual(result.state, 'off')

    def test_btrfs_is_followed_through_its_mount_source(self):
        self.tree.device('nvme0n1p3', '259:3')
        self.tree.device('dm-0', '253:0', dm_uuid='CRYPT-LUKS2-77-root', slaves=('nvme0n1p3',))
        self.tree.mounts([('0:27', '/', 'btrfs', '/dev/mapper/root'), ('0:30', '/home', 'btrfs', '/dev/mapper/root')])
        stat = FakeStat({'/home': (dev(0, 31), 0), '/dev/mapper/root': (0, dev(253, 0))})
        result = self.tree.check('/home/owner/alfred', stat)
        self.assertEqual(result.state, 'on')

    def test_mount_points_with_spaces_are_read(self):
        self.tree.device('sdb1', '8:17')
        self.tree.device('dm-5', '253:5', dm_uuid='CRYPT-LUKS1-ab-usb', slaves=('sdb1',))
        self.tree.mounts([('0:27', '/', 'ext4', '/dev/sda1'), ('0:40', '/media/My\\040Disk', 'btrfs', '/dev/dm-5')])
        stat = FakeStat({'/media/My Disk': (dev(0, 41), 0), '/dev/dm-5': (0, dev(253, 5))})
        result = self.tree.check('/media/My Disk/alfred', stat)
        self.assertEqual(result.state, 'on')

    def test_memory_network_zfs_and_overlay_folders_are_not_confirmed(self):
        for fstype, source, word in (('tmpfs', 'tmpfs', 'memory'), ('nfs4', 'server:/export', 'network'),
                                     ('zfs', 'tank/home', 'ZFS'), ('overlay', 'overlay', 'overlay')):
            with self.subTest(fstype=fstype):
                self.tree.mounts([('0:27', '/', 'ext4', '/dev/sda1'), ('0:50', '/work', fstype, source)])
                result = self.tree.check('/work/alfred', FakeStat({'/work': (dev(0, 51), 0)}))
                self.assertEqual(result.state, 'unknown')
                self.assertIn(word, result.detail)

    def test_a_loop_device_or_an_unreadable_tree_is_not_confirmed(self):
        self.tree.device('loop0', '7:0', loop=True)
        self.assertEqual(self.tree.check('/mnt/img', FakeStat({'/': (dev(7, 0), 0)})).state, 'unknown')
        self.assertEqual(self.tree.check('/mnt/x', FakeStat({'/': (dev(8, 99), 0)})).state, 'unknown')
        self.assertEqual(self.tree.check('/missing', FakeStat({})).state, 'unknown')

    def test_a_device_loop_in_sysfs_does_not_hang(self):
        self.tree.device('dm-8', '253:8', dm_uuid='LVM-cccc')
        (self.tree.sys / 'devices' / 'dm-8' / 'slaves' / 'dm-8').symlink_to(self.tree.sys / 'devices' / 'dm-8')
        self.assertEqual(self.tree.check('/x', FakeStat({'/': (dev(253, 8), 0)})).state, 'unknown')


class OtherSystemTests(unittest.TestCase):
    def test_other_systems_are_not_confirmed(self):
        result = de.check('C:\\alfred', system='win32')
        self.assertEqual(result.state, 'unknown')
        self.assertIn('not checked on this system', result.detail)


ON = de.Result('on', 'FileVault', '')
OFF = de.Result('off', 'FileVault', 'FileVault is off')
UNKNOWN = de.Result('unknown', None, 'the check did not answer')


class StartTests(unittest.TestCase):
    def start(self, results, vault='/vault', same_disk=False, mode='warn'):
        found = iter(results)
        devices = {'/data': 1, '/vault': 1 if same_disk else 2}
        return de.at_start('/data', vault, mode, check=lambda path: next(found),
                           device=lambda path: devices[str(path)])

    def test_lines_name_each_folder_and_what_was_found(self):
        self.assertEqual(self.start([ON, OFF]), [
            'Disk encryption: on (FileVault) for the data folder.',
            'Disk encryption: OFF for the vault (FileVault is off). Anyone holding this disk can read these files. '
            'Turn on full-disk encryption, or start with --disk-encryption require to refuse to run without it.'])
        self.assertEqual(self.start([UNKNOWN], vault=None), [
            'Disk encryption: not confirmed for the data folder (the check did not answer).'])

    def test_one_line_when_the_data_folder_and_vault_share_a_disk(self):
        self.assertEqual(self.start([ON], same_disk=True),
                         ['Disk encryption: on (FileVault) for the data folder and the vault.'])

    def test_require_refuses_unless_every_folder_is_on(self):
        self.assertEqual(self.start([ON, ON], mode='require'), [
            'Disk encryption: on (FileVault) for the data folder.', 'Disk encryption: on (FileVault) for the vault.'])
        for results in ([ON, OFF], [UNKNOWN, ON], [OFF, OFF]):
            with self.subTest(results=results), self.assertRaises(Fault) as caught:
                self.start(results, mode='require')
            self.assertEqual((caught.exception.code, caught.exception.status), ('disk_encryption_required', 409))
            self.assertTrue(caught.exception.detail.startswith('Disk encryption: '))

    def test_an_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            self.start([ON], mode='off')


class RealHostTests(unittest.TestCase):
    """A real `serve` process prints the check, and `require` follows this machine's answer."""

    def setUp(self):
        from alfred.desk import init_demo
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / 'demo'
        init_demo(self.home)
        self.state = de.check(self.home).state

    def serve(self, *extra):
        return subprocess.run([sys.executable, '-m', 'alfred.desk', 'serve', '--data-dir', str(self.home),
                               '--port', str(free_port()), *extra], cwd=REPOSITORY, capture_output=True, text=True, timeout=60)

    def test_a_normal_start_says_what_it_found_and_runs(self):
        process = subprocess.Popen([sys.executable, '-m', 'alfred.desk', 'serve', '--data-dir', str(self.home),
                                    '--port', str(free_port())], cwd=REPOSITORY, env=dict(os.environ, PYTHONUNBUFFERED='1'),
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        try:
            lines, deadline = [], time.monotonic() + 30
            while time.monotonic() < deadline:
                line = process.stdout.readline()
                if not line or line.startswith('Use the access command'):
                    break
                lines.append(line)
            found = [line for line in lines if line.startswith('Disk encryption: ')]
            self.assertEqual(len(found), 1, ''.join(lines))
            self.assertIn('for the data folder', found[0])
            os.killpg(process.pid, signal.SIGTERM)
            self.assertEqual(process.wait(30), 0)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(10)
            process.stdout.close()

    def test_require_refuses_before_anything_starts_unless_the_disk_is_encrypted(self):
        if self.state == 'on':
            self.skipTest('this machine keeps its temporary folder on an encrypted disk')
        run = self.serve('--disk-encryption', 'require')
        self.assertEqual(run.returncode, 1)
        self.assertIn('Cannot start: disk_encryption_required', run.stdout)
        self.assertIn('Disk encryption: ', run.stdout)
        self.assertFalse((self.home / 'desk.lock').exists())

    def test_an_unknown_choice_is_refused_by_the_command_line(self):
        run = self.serve('--disk-encryption', 'ignore')
        self.assertEqual(run.returncode, 2)
        self.assertIn("invalid choice: 'ignore'", run.stderr)


if __name__ == '__main__':
    unittest.main()
