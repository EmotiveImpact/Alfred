# Disk encryption check at start

ALFRED seals its own records with keys (see [ENCRYPTION.md](ENCRYPTION.md)). Full-disk
encryption is the layer underneath. It also covers swap, temporary files, the vault ALFRED
reads and anything a helper leaves behind. This is the first of the four layers in master plan
phase 1: the whole disk, ALFRED's sealing, helpers that leave nothing behind, and a cloud rule
per area.

`alfred/disk_encryption.py` asks once, when `desk serve` starts, whether the data folder and
the vault are on an encrypted disk. Then the host prints one line for each disk:

```
Disk encryption: on (FileVault) for the data folder and the vault.
Disk encryption: OFF for the vault (FileVault is off for this volume). Anyone holding this disk can read these files. Turn on full-disk encryption, or start with --disk-encryption require to refuse to run without it.
Disk encryption: not confirmed for the data folder (the folder is a network folder).
```

When the two folders share a disk, there is one line for both.

## Warn or require

| Option | What happens |
| --- | --- |
| `--disk-encryption warn` (default) | ALFRED starts and prints what it found. |
| `--disk-encryption require` | ALFRED refuses to start (`Cannot start: disk_encryption_required`) unless every folder is on a disk it confirmed as encrypted. It refuses before it takes the lock or opens the database, so nothing is created. |

"Not confirmed" counts as not encrypted under `require`.

## How it finds out

The check only reads. Each command runs directly, never through a shell, with no input and a
five-second deadline.

- **macOS, the start-up disk** (a folder under `/` or `/System/Volumes/Data`): it runs
  `/usr/bin/fdesetup status`.
  - "FileVault is On." reads as on. If encryption is still in progress, the line says so.
  - "FileVault is Off." reads as off, and so does "Decryption in progress".
- **macOS, any other volume:** it runs `/usr/sbin/diskutil info -plist` on the volume's mount
  point and reads its `FileVault` value.
- **Linux:** it reads `/sys/dev/block` for the folder's disk. It looks for a dm-crypt (LUKS)
  layer, through LVM and software RAID.
  - The disk counts as on only when every path down to the hardware passes through dm-crypt.
    For example, RAID over one encrypted member and one plain member reads as off.
  - btrfs folders report an anonymous device number, so it follows the mount's source device
    from `/proc/self/mountinfo` instead.
- **Anything else is "not confirmed", never "on":**
  - a missing, failing, slow or unreadable command
  - a loop device
  - a folder kept in memory, on the network, in an overlay or on ZFS
  - Windows and other systems

## What it cannot see

- File-level encryption: fscrypt, eCryptfs and ZFS native encryption. A Linux home folder
  protected only by fscrypt reads as off.
- Encryption below the operating system, such as a self-encrypting drive or a cloud
  provider's volume encryption.
- A btrfs file system spread over several disks is judged only by the disk its mount names.
- Whether the disk is unlocked right now by someone else. An encrypted disk only protects
  data while the machine is off or locked.

The macOS answers follow the documented output of `fdesetup` and `diskutil`. The tests use
recorded answers, because CI has no Mac. The real-Mac test run in master plan phase 2
confirms them on hardware.

## Tests

`tests/test_disk_encryption.py` covers:
- each macOS answer
- LUKS directly, under LVM and under RAID
- btrfs, and mount points with spaces
- memory, network, ZFS and overlay folders
- loop devices, and device loops in `/sys`
- the start-up lines
- `require` refusing in a real `serve` process before it creates anything
