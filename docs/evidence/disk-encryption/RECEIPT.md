# Receipt: disk encryption check at start

Tested commit: `cc95caa38` on branch `claude/project-thread-att046-disk-check`, from `main` at
`83d9641c9`.

## What was built

- `alfred/disk_encryption.py`: `check(path)` answers on, off or unknown for the disk under a
  folder, and `at_start(data_dir, vault, mode)` gives the start-up lines. In `require` mode it
  raises `Fault('disk_encryption_required', 409)`.
- `alfred/desk.py`: `serve` runs the check after `check_data_directory` and before the lock
  or database. It prints the lines with the other start-up lines. `--disk-encryption warn`
  is the default; the other choice is `require`.
- `docs/DISK_ENCRYPTION.md` and an entry in `docs/INDEX.md`.

## Checks run at the tested commit

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -p test_disk_encryption.py` | 26 tests, OK |
| `python3 -m unittest discover -s tests` | 1,631 tests, OK |
| `python3 tools/egress_audit.py` | ok, 111 files, 0 warnings |
| `python3 tools/check_claims.py --base origin/main --branch claude/project-thread-att046-disk-check` | claims ok |

The test file was written first and failed on the missing module before the module existed.

## On this machine

The development container's folders are on ext4 on `/dev/vda`, with no dm-crypt layer, so
the check reads OFF here. `require` refused in a real `serve` process, with nothing created.

## Not tested here

- A real Mac. The macOS answers are recorded from the documented `fdesetup status` and
  `diskutil info -plist` output. The real-Mac test run in master plan phase 2 confirms them.
- A real LUKS volume. The Linux answers use fake `/sys` and `/proc` trees shaped like a
  kernel's.

Paths the encryption thread claims (`coordination/claims/claude-encryption.md`) are untouched.
