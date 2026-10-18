"""Whether ALFRED's folders sit on a disk with full-disk encryption (master plan phase 1).

ALFRED seals its own records (docs/ENCRYPTION.md), but the whole disk is the first layer:
it covers swap, temporary files, the vault ALFRED reads and anything a helper leaves behind.
`desk serve` asks once at start and prints what it found for the data folder and the vault.
With `--disk-encryption require` it refuses to start unless every folder is on an encrypted
disk.

It only reads. macOS answers through `fdesetup status` for the start-up disk and
`diskutil info -plist` for any other volume; Linux answers from /sys and /proc, looking for a
dm-crypt (LUKS) layer under the folder's disk, through LVM and software RAID. Each command
runs without a shell, with no input and a short deadline. Anything this cannot read, or a
system it does not know, is "not confirmed", never "on". File-level encryption (fscrypt,
eCryptfs, ZFS native encryption) is not detected.
"""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
import plistlib
import subprocess
import sys

from .local import Fault

MODES = ('warn', 'require')
STATES = ('on', 'off', 'unknown')
TIMEOUT = 5
FDESETUP = '/usr/bin/fdesetup'
DISKUTIL = '/usr/sbin/diskutil'
# Volumes of the macOS start-up disk, whose FileVault state fdesetup reports.
START_UP_VOLUMES = ('/', '/System/Volumes/Data')
LUKS = 'LUKS (dm-crypt)'
NOT_SEEN = 'no LUKS (dm-crypt) layer found; fscrypt, eCryptfs and ZFS encryption are not detected'
# Linux file systems that live in memory, on the network or in a layer this cannot follow.
NOT_A_DISK = {
    'tmpfs': 'kept in memory, not on a disk', 'ramfs': 'kept in memory, not on a disk',
    'nfs': 'a network folder', 'nfs4': 'a network folder', 'cifs': 'a network folder', 'smb3': 'a network folder',
    'fuse.sshfs': 'a network folder', '9p': 'a shared folder from another system', 'virtiofs': 'a shared folder from another system',
    'overlay': 'an overlay of other folders', 'zfs': 'on ZFS, whose native encryption is not checked',
}
DEPTH = 8


@dataclass(frozen=True)
class Result:
    state: str
    method: str | None
    detail: str


def _unknown(detail, method=None):
    return Result('unknown', method, detail)


def check(path, *, system=None, run=subprocess.run, sysfs='/sys', proc='/proc', stat=os.stat,
          realpath=os.path.realpath, ismount=os.path.ismount):
    """What full-disk encryption covers the folder at `path`. Never raises for an unreadable answer."""
    system = sys.platform if system is None else system
    try:
        where = realpath(os.fspath(path))
    except (OSError, ValueError):
        return _unknown('the folder could not be found')
    if system == 'darwin':
        return _mac(where, run, ismount)
    if system.startswith('linux'):
        return _linux(where, Path(sysfs), Path(proc), stat)
    return _unknown('not checked on this system')


def _run(run, argv):
    try:
        done = run(argv, capture_output=True, timeout=TIMEOUT, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return done.stdout if done.returncode == 0 else None


def _mount_point(where, ismount):
    point = Path(where)
    while not ismount(str(point)) and point != point.parent:
        point = point.parent
    return str(point)


def _mac(where, run, ismount):
    point = _mount_point(where, ismount)
    if point in START_UP_VOLUMES:
        out = _run(run, [FDESETUP, 'status'])
        if isinstance(out, bytes):
            out = out.decode('utf-8', 'replace')
        lines = [line.strip() for line in (out or '').splitlines()]
        if any(line.startswith('Decryption in progress') for line in lines):
            return Result('off', 'FileVault', 'FileVault is being turned off')
        if 'FileVault is On.' in lines:
            still = any(line.startswith('Encryption in progress') for line in lines)
            return Result('on', 'FileVault', 'FileVault is still encrypting the disk' if still else '')
        if 'FileVault is Off.' in lines:
            return Result('off', 'FileVault', 'FileVault is off')
        return _unknown('fdesetup did not answer')
    out = _run(run, [DISKUTIL, 'info', '-plist', point])
    try:
        info = plistlib.loads(out.encode() if isinstance(out, str) else out) if out else None
    except Exception:
        info = None
    vault = info.get('FileVault') if isinstance(info, dict) else None
    if vault is True:
        return Result('on', 'FileVault', '')
    if vault is False:
        return Result('off', 'FileVault', 'FileVault is off for this volume')
    return _unknown('diskutil did not say whether this volume is encrypted')


def _unescape(field):
    # mountinfo writes space, tab, newline and backslash as three-digit octal escapes.
    out, i = [], 0
    while i < len(field):
        if field[i] == '\\' and i + 3 < len(field) and all(c in '01234567' for c in field[i + 1:i + 4]):
            out.append(chr(int(field[i + 1:i + 4], 8)))
            i += 4
        else:
            out.append(field[i])
            i += 1
    return ''.join(out)


def _mount(where, proc):
    """The mountinfo row whose mount point holds `where`: (mount point, file system, source)."""
    best = None
    with open(proc / 'self' / 'mountinfo', encoding='utf-8', errors='replace') as rows:
        for row in rows:
            fields = row.split()
            if '-' not in fields:
                continue
            dash = fields.index('-')
            if len(fields) < dash + 3 or len(fields) < 5:
                continue
            point = _unescape(fields[4])
            inside = where == point or where.startswith(point.rstrip('/') + '/')
            if inside and (best is None or len(point) >= len(best[0])):
                best = (point, fields[dash + 1], _unescape(fields[dash + 2]))
    return best


def _layers(folder, seen, depth):
    """'on' when every path down from this block device passes through dm-crypt, else 'off'.
    None when the tree cannot be followed."""
    if depth > DEPTH:
        return None
    try:
        real = folder.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if real in seen:
        return None
    seen = seen | {real}
    if (real / 'loop').is_dir():
        return None
    try:
        uuid = (real / 'dm' / 'uuid').read_text().strip()
    except FileNotFoundError:
        uuid = ''
    except OSError:
        return None
    if uuid.startswith('CRYPT-'):
        return 'on'
    try:
        slaves = sorted((real / 'slaves').iterdir()) if (real / 'slaves').is_dir() else []
    except OSError:
        return None
    if not slaves:
        return 'off'
    answers = [_layers(slave, seen, depth + 1) for slave in slaves]
    if None in answers:
        return None
    return 'on' if all(answer == 'on' for answer in answers) else 'off'


def _linux(where, sysfs, proc, stat):
    try:
        number = stat(where).st_dev
    except OSError:
        return _unknown('the folder could not be found')
    if os.major(number) == 0:
        # btrfs, network, memory and overlay folders report an anonymous device number.
        try:
            mount = _mount(where, proc)
        except OSError:
            mount = None
        if mount is None:
            return _unknown('the mount table could not be read')
        _point, fstype, source = mount
        if fstype in NOT_A_DISK:
            return _unknown(f'the folder is {NOT_A_DISK[fstype]}')
        if not source.startswith('/dev/'):
            return _unknown(f'the folder is on {fstype}, which this check cannot follow')
        try:
            number = stat(source).st_rdev
        except OSError:
            return _unknown('the disk under the folder could not be found')
    state = _layers(sysfs / 'dev' / 'block' / f'{os.major(number)}:{os.minor(number)}', frozenset(), 0)
    if state is None:
        return _unknown('the disk layers under the folder could not be read', LUKS)
    return Result(state, LUKS, '' if state == 'on' else NOT_SEEN)


def _line(result, label):
    method = f' ({result.method})' if result.method else ''
    if result.state == 'on':
        note = f' {result.detail[0].upper()}{result.detail[1:]}.' if result.detail else ''
        return f'Disk encryption: on{method} for {label}.{note}'
    if result.state == 'off':
        return (f'Disk encryption: OFF for {label} ({result.detail}). Anyone holding this disk can read these files. '
                'Turn on full-disk encryption, or start with --disk-encryption require to refuse to run without it.')
    return f'Disk encryption: not confirmed for {label} ({result.detail}).'


def _device(path):
    return os.stat(path).st_dev


def at_start(data_dir, vault, mode, *, check=check, device=_device):
    """The start-up lines for the data folder and the vault. `require` raises
    Fault('disk_encryption_required') unless every folder is on an encrypted disk."""
    if mode not in MODES:
        raise ValueError(mode)
    folders = [('the data folder', data_dir)] + ([('the vault', vault)] if vault else [])
    groups = []
    for label, folder in folders:
        try:
            number = device(folder)
        except OSError:
            number = None
        for group in groups:
            if number is not None and group[0] == number:
                group[1].append(label)
                break
        else:
            groups.append((number, [label], folder))
    lines, refused = [], False
    for _number, labels, folder in groups:
        result = check(folder)
        lines.append(_line(result, ' and '.join(labels)))
        refused = refused or result.state != 'on'
    if mode == 'require' and refused:
        fault = Fault('disk_encryption_required', 409)
        fault.detail = '\n'.join(lines)
        raise fault
    return lines
