# Encryption step 2, part 5 receipt: switching sealing on

Built 31 October 2026 on part 4 (d93760129). Parts 1 to 4 merged on 31 October (PRs #50, #51,
#53 and #54). Tested revision: 1a5e79e05 (the commit carrying this receipt changes only this
file). Retested at 3d699f1f4, after main's PRs #49 and #52 and part 4's review fix (B-033) were
merged in: 2,048 tests pass plain and 2,048 pass sealed (60,594 values sealed). With #52's `desk serve --hub hermes`
in, `serve` now checks its port and its Hermes settings before it unlocks the keyring, so a
start that could never happen unlocks nothing (`test_serve_checks_its_settings_before_it_unlocks`,
failing without the change). Retested at eced2053b with the first review fixes below: 2,054
tests pass plain and 2,054 pass sealed (60,594 values sealed), and the six checks exit 0.
Retested at ac6843141 with the second review's fix and the test clock fix: 2,055 tests pass
plain and 2,055 pass sealed (60,594 values sealed), and the six checks exit 0. Retested at
24ac52881 with the third review's fix: 2,056 tests pass plain and 2,056 pass sealed (60,594
values sealed), and the six checks exit 0. Synthetic
keys, invented vaults and invented work only, with the rule-based SyntheticBrain. Nothing under `third_party/` was read, imported or executed, and no
model ran.

Requirements: SYS-002 (private storage), memory job M05. Plan: integration plan phase 1, step 2,
part 5 of 5. Out of scope, waiting for the owner's open choice about answers drawing on several
areas: folder rules, anything that puts a record in more than one area, and sealing an answer
under several areas' keys. Every record stays in the default area.

## What was built

- `alfred/seal_workspace.py` (new): `seal(path, sealer, cache_dir=)` converts a plain workspace
  in one transaction with foreign keys off and its triggers dropped and recreated inside it.
  It seals every column `sealing.TABLES` names; maps every plain fingerprint, and its 16 and 24
  character short forms, to the keyed form and swaps it wherever ALFRED copied it (every text
  column except the ones a worker or the owner wrote as they are: note text and paths, job
  parameters, artefact bodies); keys `KEYED_IDS`; derives again the ids made from them (desk
  event ids, capture request ids, a scan's snapshot hash) and keys in place those whose inputs
  are gone (held capture items, confirmed brain actions); keys the SHA-256 values inside action
  parameters and proofs and a harvested learning's key and signature. Before commit `_check`
  opens every sealed value, looks for every plain token and short form in every text column and
  runs `PRAGMA foreign_key_check`. It refuses `work_in_flight` (409) while any job is queued,
  leased, running or asked to cancel. After commit it empties the job cache (keeping pins under
  their keyed names), compacts (`wal_checkpoint(TRUNCATE)`, `VACUUM`, `wal_checkpoint(TRUNCATE)`)
  and converts and compacts each registered backup, rewriting its manifest. `reseal(path, sealer,
  area)` seals one area's values again under its newest key version, in the workspace and its
  backups and, for the default area, in the sealed exports the export register names. Each writes a marker (`.sealing`, `.resealing`) first and removes it last; a busy
  database stops with `workspace_busy` (409) and the marker kept.
- `alfred/keys.py`: `OpenKeyring.retire_old_keys(area)` deletes every key version but the
  newest and keeps only the number of the last one deleted (`retired_through`), after storing
  the area's fingerprint key wrapped on its own; `fingerprint_key(area)` derives it from the
  first version until then. `area_key` refuses a retired version (`key_version_retired`, 410).
  `MAX_VERSIONS` (16) caps the keys an area holds at once; version numbers count on to
  `MAX_KEY_VERSION` (9,999), and a sealed value's version may have four digits.
- `alfred/sealing.py`: fingerprints use `fingerprint_key`; `recorded(path)` reads which keyring
  a workspace records.
- `alfred/desk.py`: `open_workspace(root)` refuses while a marker exists (`sealing_incomplete`,
  409) and, for a sealed workspace, unlocks the keyring through `keys.unlock` before anything
  opens the database, or stops (`workspace_locked`). Every command but `init` goes through it.
  New commands `seal`, `rotate-area --area` and `open-export --sealed-export --export-dir`;
  `export` gains `--plain`, and warns when used on a sealed workspace.
- `alfred/export.py`: `export(..., plain=False)` seals each file of an export from a sealed
  workspace and lists them in a plain `SEALED.json` and `SHA256SUMS`; `open_export` checks and
  opens one. `reseal_export(directory, sealer)` seals one again under the newest key, writing
  beside it and swapping it in, and finishes an interrupted swap first.
- `alfred/lifecycle.py`: a backup manifest records `sealed`, `encrypted` and the keyring's id
  (`manifest_sealing`); an absolute forget marks the transaction for compaction
  (`forget_accounted`), and restore compacts the staged file after replaying the journal.
- `alfred/local.py`: sealed connections set `secure_delete=ON`; a transaction marked for
  compaction compacts after it commits.
- `alfred/deletion.py`: an export on disk is recognised by `manifest.json` or `SEALED.json`.
- `alfred/knowledge_check.py`: opens the workspace through `open_workspace` first.

## Tests

- `tests/test_sealing_switch_on.py` (49 tests at 1a5e79e05, 51 at 3d699f1f4, 58 after the
  review fixes below). Run against part 4 (d93760129) the file fails at
  import, since part 4 has no `alfred.seal_workspace`.
  - The `seal` command converts once and a second run only compacts; a conversion that fails
    its own check rolls back, keeps its triggers and leaves the workspace plain with its marker,
    and running it again finishes it; a database another connection holds is not called
    finished; another keyring and a missing area are refused; backups made before sealing are
    sealed with it, say so and restore.
  - Compaction, with SQLite's own secure delete turned off as macOS builds may have it: an
    absolute forget of a source or a statement leaves none of its words in the database, its
    write-ahead log or shared memory; sealed, no sealed copy of a forgotten note is left
    either; a restore applies the forget again (`journal_entries_replayed == 2`) and compacts.
    For comparison, the same source forget on part 4 with secure delete off left all four of
    the note's invented words in the file; part 5 left none.
  - An export is sealed and opens with the keyring to the same files a plain export (`plain`)
    writes; it is refused without the keyring, with another keyring, or when a file is changed.
  - Rotation seals the area again, retires the old versions so a copy made before can no longer
    be opened, and keeps every view and fingerprint, in the workspace and its backup; an
    interrupted rotation leaves its marker and finishes when run again.
  - The desk starts a plain workspace without unlocking, unlocks a sealed one first or refuses
    (`workspace_locked`), warns on `export --plain`, and refuses a workspace with an unfinished
    seal (`sealing_incomplete`).
  - The at-rest tests of parts 1 to 4 (`SealedAtRestTests`, `SealedMemoryAtRestTests`,
    `SealedRecordsAtRestTests`, `SealedWorkAtRestTests`) run again on workspaces built plain and
    converted by `seal`.
  - The same invented workspace sealed from the start and converted by `seal`, with one keyring,
    one clock and fixed random ids, gives the same tables, row counts and opened rows, apart from
    two named classes: hashes made over a whole request or record before sealing, which are keyed
    as made (`memory_claims.request_hash`, `actions.fingerprint`, `events.fingerprint`,
    `jobs.fingerprint`, `brain_tasks.packet_sha256`), and what a worker was sent and returned with
    the result's address wherever it is copied (`jobs.parameters`, `jobs.result_artefact`,
    `artefacts.body`, `artefacts.sha256`, `brain_results.envelope_sha256`, `job_events.detail`,
    `verification_runs.report`, `verification_runs.report_sha256`,
    `verification_results.last_run_sha256`). Notes show no difference at all.
  - The final scan, below.
- `tests/test_export.py` and `tests/test_deletion_accounting.py` open a sealed export through
  `tests/stored_helpers.py` (`export_files`), so they hold in both modes.

## The final scan and what it allows

`FinalScanTests` builds each invented workspace of parts 1 to 4 plain (the notes one with a sync
conflict and a calendar import added, the desk's one with a draft made from an observation),
backs it up, switches it on with `seal` (the desk's workspace through `python3 -m alfred.desk
seal`), reads every view and exports it. It then reads every byte of the database, its `-wal`,
`-shm` and `-journal` files and the lifecycle journal, the job cache, the backups folder and
the export, and looks for: every invented word in three cases; every id a source chose
(`KEYED_IDS`); and every SHA-256 found anywhere in the plain workspace plus the SHA-256 of each
of those ids, whole and as 16, 24, 32, 40 and 64 character prefixes. It finds none. It also
checks that every table in `sealing.TABLES` held something to find.

Allowed, matched to part 4's list of what stays readable:

| Part 4 says stays readable | How the scan treats it |
| --- | --- |
| Job inputs and lineage: note ids, sources, revisions, keyed hashes | Random ids, labels and numbers are not private words; any plain hash there would be found, and none is |
| Job event details: codes, sizes and keyed hashes | The same |
| The count of values scrubbed from each packet | Numbers, not looked for |
| Hub tasks, controls, heartbeats, meter readings, attention items | Codes and numbers, not looked for |
| Learning keys and signatures that are ALFRED's codes | Codes are not looked for; a harvested learning's key and signature are hashes and are found keyed |
| Routine run outcomes: counts and ids | Not looked for |
| Briefs about public upstream projects | Copied from the public catalogue, not invented words |
| Identifiers a caller chooses (request, task, idempotency, worker, event ids) | Not looked for; only the ids in `KEYED_IDS` are |

One allowance is added, as `READABLE_HASHES = {('credentials', 'digest')}`: each access key's
SHA-256. Part 4's list did not name it because no earlier scan looked at every hash in the
file. ALFRED checks a presented key against it; the key is random and kept in the access-key
file beside the database, so its hash says nothing about what the owner wrote.
`docs/ENCRYPTION.md` lists it under "One hash stays plain".

## Suites and checks at 1a5e79e05

- Whole suite, plain (`python -m unittest discover -s tests`): 2,020 tests, all passing.
- Whole suite, sealed (`python tests/sealed_suite.py`): 2,020 tests, all passing, with 60,479
  values sealed in the process.
- `tools/check_public_hygiene.py`, `tools/check_claims.py --base origin/main --branch
  claude/project-thread-9npowk`, `tools/check_requirement_register.py`,
  `tools/check_memory_plan.py`, `tools/check_adoptions.py` and `tools/egress_audit.py`: all
  exit 0.

## Review fixes (31 October 2026)

Three findings from the automatic review of PR #55, each with a test that fails without its
fix and passes with it:

- Rotation made sealed exports unreadable: they are sealed under the default area, and
  rotating it deleted the key they were sealed with. `reseal` now seals again every sealed
  export the export register names and still finds, before it deletes the older keys.
  `test_rotation_seals_the_sealed_exports_it_wrote_again` (one export opens after rotation; one
  moved away, one changed and one with a file removed do not, and the last two are counted and
  left as they were; a listed file that is gone is now `export_checksum_mismatch`),
  `test_an_interrupted_export_swap_is_finished_by_running_it_again` and, through the desk,
  `test_rotating_the_area_keeps_a_sealed_export_openable`.
- An area could be rotated only fifteen times: retired versions kept an entry each and the
  16-entry cap never freed. Retired versions now collapse to one number.
  `test_an_area_rotates_again_and_again` (17 rotations of a sealed workspace) and, in
  `tests/test_keys.py`, `test_retired_versions_free_room_for_more_rotations` (120 rotations, a
  value sealed and opened at version 121, and 16 unretired keys still refused).
- `open-export` passed no vault to the destination check, so it could write readable files into
  a `--vault` with nothing marking it as one. It now passes the same vaults `export` does.
  `test_a_sealed_export_is_never_opened_into_a_vault`.

A second review, of the first fix, found one more:

- An export ALFRED could read but not write beside (a read-only drive, a full disk) raised a
  file error that stopped the rotation with its marker in place, so ALFRED would not start.
  Each step of the swap that fails now puts the export back whole, and the rotation counts it
  and finishes. `test_an_export_that_cannot_be_written_beside_is_counted_and_left_whole`
  (staging refused for one export, the second rename refused for another). The interrupted-swap
  test now stops with `KeyboardInterrupt`, since a rename that raises has not happened.

A third review found one more:

- If the new copy could not go in and the original could not go back either, the export was
  left only under hidden names, and the rotation still finished and deleted the older keys.
  Now neither copy at its path stops the rotation (`export_swap_unfinished`, naming where the
  new copy is), with its marker and the older keys kept; running it again puts the new copy in
  place. `test_an_export_left_off_its_path_stops_the_rotation_with_the_old_keys_kept`.

While retesting, `SameAsSealedFromTheStartTests.test_notes` failed once in the sealed run, with
`audit.at` and two `expires` columns differing. Its builds patched `time.time`, but a store's
clock is a default argument bound to the real `time.time` at import, so the two builds could
fall in different seconds. They now freeze `LocalCore` and `DeskStore`'s clocks too. Forcing a
second between the builds reproduced the failure before the change and passes after it, for
all four comparison tests.

## Platform note

The SQLite this was tested with (3.45.1, Linux) has `SECURE_DELETE` on by default, so part 4
already lost deleted text there. Builds on macOS may not, which is why the compaction tests turn
it off and why compaction is done in plain workspaces too.

## Not covered

- Folder rules and records in more than one area wait for the owner's choice about answers
  drawing on several areas; `docs/ENCRYPTION.md` says so.
- Limits written into `docs/ENCRYPTION.md`: exports and copies made before sealing stay plain,
  and a plain backup is not restored into a sealed workspace; a request repeated across sealing
  needs a new id; a draft proposed by a brain task before sealing must be proposed again;
  rotation keeps fingerprints, and keyring copies made before it still hold the old versions;
  compaction is not secure erasure; one hash stays plain.
- The keychain and server unlocks are tested through stand-ins; nothing was run on a real Mac
  or server.
