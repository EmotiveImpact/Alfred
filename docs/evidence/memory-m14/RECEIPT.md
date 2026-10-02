# M14 receipt: file sync kept apart, conflict copies, placement guard and portable export

2 October 2026. Requirements MEM-014 (memory job M09) and the portable-export part of MEM-013.
Status: **implemented and tested; integrated on `claude/alfred-development-qpgxhg` by the lead as a
reviewed patch.** The agent's worktree had started from `main`, and moving it onto the integration
branch was refused by the permission system, so the agent built and tested the change in a plain
copy of `870751368` and handed over a patch (SHA-256 `a18cdf9d...ddee49`). The lead applied it to
the head after `a6d8fd10e` (two hunks re-applied by hand beside the connector changes), reran the
checks below, and committed it; the commit that adds this text is the integrated revision.
Synthetic files and temporary folders only; no sync client, device, account, vault, model or
network was used. Design and limits: [SYNC.md](../../SYNC.md).

## Tested tree

The base commit plus these files, with their SHA-256 at test time (this receipt excluded):

| File | Change | SHA-256 |
|---|---|---|
| `alfred/sync_conflicts.py` | new | `83ec73fc6a5d55e2bfe5eb6167eab5e8af11c07bf672660b76e66d7ea66dc754` |
| `alfred/placement.py` | new | `b995cd29c987104f9de7e53941355bc4f5887b3cd0daff0db648c8ae97ab079a` |
| `alfred/export.py` | new | `b8170193e3b2371dc23e8c68f9c73664cd34c5b80ee2c0d04dde0a4e90ac713f` |
| `alfred/knowledge.py` | additive | `d3910d2bab9c6c9b962e4d80050b3fab8956272249fe07e0a335df90eafa115a` |
| `alfred/console_api.py` | additive | `376a436c9f1c482c3df3f2c10ba250792811248eb9f5b0eb98af0dc9cb94da0e` |
| `alfred/desk.py` | additive | `663397bddcf93ff72c76f421db2a02676c2faac7ffb788037a378f366780b101` |
| `alfred/inbox.py` | additive | `e5720dbaccd12eedf280d0690bd0640b8cc1ee368cd3a1a2b196b9fde5b57bbc` |
| `tests/test_sync_conflicts.py` | new | `1980243941a798b6bc24d3e1c932d1966a7f1f1aad5ade62b29fced7b5879b64` |
| `tests/test_placement.py` | new | `3cd66b88d57b52c7b5872e1d2e4b94b7383fde4e645e7c75cf74aeec5ab30883` |
| `tests/test_export.py` | new | `cd79d7aebcf410417fbd4d6f83bed5f68c59ede6293183cb66ac725ea6a9b87a` |
| `tools/check_sync_conflict_browser.py` | new | `f77f7ab9ee2c0fc9ba644995d0dd6bb7cc98edaef3374b60d0322a81055e50b3` |
| `docs/SYNC.md` | new | `e0cb20792f61919f87a0026c6c7bb810d1e84b825afc3d038aff327be8aaa45f` |
| `docs/OBSIDIAN_INTEGRATION.md` | one paragraph | `279bf363038728879b079fa6c00dea0abff6d71e8d99bd6e0c0531716e9a0e66` |
| `README.md` | one paragraph | `e743d48911813d555d3eaccde51f56e5979f4487eaaec527fc32f4d639962c55` |
| `docs/evidence/memory-m14/browser-report.json` | new | `62ae337e244915afa4de3b25d0cb4cfe8a071fa5fcea66a028eee89e22c0c2a3` |

## Implemented

- **Conflict copies (MEM-014).** The vault scanner recognises Syncthing, Dropbox,
  Nextcloud/ownCloud and older ownCloud conflict names by exact pattern with a real date and
  time, never reads them as notes, and records each in `knowledge_conflicts` as `linked` (with
  the original's catalogue ID), `original_unavailable` or `orphaned`. Each copy is a per-path
  source issue `sync_conflict_copy`, so the source shows `attention`. `GET /desk/knowledge`
  returns `sync_conflicts`; the console projection marks the original note `attention` with
  `syncConflict` and lists all copies in `syncConflicts`. Removing the copy clears the record.
  Detection and clearing are audited with a hashed reference. At most 64 copies are recorded per
  source. The inbox writer refuses conflict-like filenames.
- **Placement guard.** `init`, `serve` and `restore` refuse a data directory inside a configured
  vault or `.obsidian` folder, a recognised Syncthing, Dropbox or Nextcloud/ownCloud folder, the
  macOS `Library/Mobile Documents` or `Library/CloudStorage` paths, or a Git working tree,
  checking the given and the real path. The refusal explains the `backup` alternative. No
  override exists. `access`, `backup`, `export`, `rotate` and `revoke` still run.
- **Portable export (MEM-013).** `python3 -m alfred.desk export --export-dir PATH [--role reader]`
  writes plain JSON and readable Markdown of one credential's authorised reviewed statements
  (review state, cited revision, lineage), capture retention and executive records, with a
  manifest of SHA-256 hashes, counts, exclusions and export time, and `SHA256SUMS`. Forgotten,
  withheld and past-retention statements, keys, digests, sessions and invitation codes are left
  out. The destination must be new or empty, outside every vault and this repository; files are
  0600 in a 0700 folder, written through a staging folder and renamed into place.
- **Documentation.** [SYNC.md](../../SYNC.md) separates vault file sync, identity and grants,
  ledger and job state, and runtime or model sync, and lists what is not implemented.

## Defects found and fixed

Both were reproduced on the base behaviour by disabling recognition in the working copy, and are
now covered by tests in `tests/test_sync_conflicts.py`:

1. Syncthing renames the losing local file to the conflict name, so its inode moves to the copy.
   The scanner's inode continuity then gave the original note's catalogue identity to the copy
   (indexed as that note) and a new identity to the original path. Identity now stays with the
   original path.
2. With adopted `alfred_id` properties, a conflict copy carrying the same ID made the whole
   source unavailable as `duplicate_stable_note_id`. The copy is now set aside and the source
   stays readable with `attention`.

## Commands and results

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests` on the unmodified base | 819 tests, OK |
| `python3 -m unittest discover -s tests` on the tested tree | 865 tests, OK (46 new: 19 conflict, 13 placement, 14 export) |
| `cd console && npm run build`, `npm test` (existing `node_modules` linked, nothing installed) | built; 79 unit tests passed |
| `CHROMIUM_PATH=/opt/pw-browsers/chromium tools/check_console_connected_browser.py` (output to a scratch folder) | 64 passed, no page errors |
| `tools/check_knowledge_browser.py` (output to a scratch folder) | 25 checks, no errors |
| `tools/check_sync_conflict_browser.py` | 5 checks, no errors ([report](browser-report.json); its screenshot is regenerated by the tool and not committed) |
| `python3 tools/check_requirement_register.py` | passes; the register is unchanged |
| `python3 tools/check_memory_plan.py` | in the working copy, which omits `third_party/`, it reports only the existing links into `third_party/`, the same as on the unmodified base; the links in the changed documents resolve |

The same change, applied unchanged to the later branch head
`fcdf7e9ae2ffddba5b079c5d4665d0b6ac3b272c` (none of the modified files differ there):

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests` on the unmodified head | 839 tests, OK |
| `python3 -m unittest discover -s tests` on the head with this change | 885 tests, OK |
| `cd console && npm run build`, `npm test` | built; 89 unit tests passed |
| `tools/check_console_connected_browser.py` (output to a scratch folder) | 81 passed, no page errors |
| `tools/check_knowledge_browser.py` and `tools/check_sync_conflict_browser.py` | 25 and 5 checks, no errors |

Rerun by the lead on the integrated tree (head `a6d8fd10e` plus this change, which also carries
the connector merge, pairing and whole-source removal):

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests` | 1005 tests, OK |
| `python3 tools/check_requirement_register.py` and `tools/check_memory_plan.py` (full checkout) | both pass |
| `tools/check_sync_conflict_browser.py` | 5 checks, no errors ([report](browser-report.json), [screenshot](web-knowledge-conflict.png)); now also run by the `console-connected` CI job |
| `tools/check_console_connected_browser.py` (output to a scratch folder) | 85 passed, no page errors |
| `tools/check_knowledge_browser.py` (output to a scratch folder) | passes, no errors |

## Not done

- Unified CI runs on the integrated commit; the receipt records the local reruns only.
- No real sync client, device or vault. Name forms follow the tools' documented behaviour and
  were tested with files created by name.
- OneDrive, iCloud Drive, Obsidian Sync, Google Drive and other tools' conflicts, Git conflict
  markers, and Dropbox case or encoding conflicts are not recognised (reasons in SYNC.md).
- Network filesystems, FUSE mounts, sync of ordinary paths such as `~/Documents`, and sync
  started after `serve` are not detected by the placement guard.
- The console interface does not display the note-level conflict fields; only the projection
  carries them.
- Export: no encryption, no redaction inside the bundle, and no export of the knowledge index,
  note history, receipts or jobs. Identity, ledger, job and runtime sync between devices do not
  exist.
