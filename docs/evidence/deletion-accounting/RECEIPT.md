# Deletion and restore accounting receipt (plan item 1.3)

16 October 2026. Branch `feat/deletion-accounting-2026-10-16`, started from `main` at
`75947b8dd` (PR #18 merge). Tested revision: the working tree committed as the single commit
on that branch (its hash is in the delivery report; a commit cannot name itself). Synthetic
data only. Nothing under `third_party/` was read, imported or executed.

Requirements: MEM-010 (correct, delete and revoke through all dependents), MEM-013 (portable
exports), memory job M05. Decision 0.3 defaults applied: history is included in export, and
value-free history rows are kept on forget, with purge as an explicit option.

## What was built

- **One scan** (`alfred/deletion.py`). For a source, an entity (a statement subject) or one
  reviewed statement it finds every dependent through current links (statement cites note,
  answer cites statement or note, draft proposed from an answer or bound to evidence, job read
  a note, routine nomination cites a statement, executive record cites a note) and through the
  identifiers earlier receipts recorded, because forgetting deliberately breaks some links (a
  withdrawn answer keeps its question but loses the packet). Twenty categories: statements,
  entity name, captures, source index, tombstones, desk events and documents, connector
  records, answers, voice playback records, drafts (counted by whatever ledger state they are
  in, so archived or lapsed drafts count too), routine nominations, executive citations, job
  artefacts, jobs, cache copies, history rows, audit rows, lifecycle receipts, exports on disk
  and backups. Each reports `count` and `holding_value` (rows that still hold content, a name or
  text rather than identifiers, states, times and hashes). Statements and entities are scanned
  only within the asking person's own records.
- **Forget receipts** (`lifecycle.forget_accounted`, used by `ReviewedMemory.forget`,
  `forget_entity` and `lifecycle.forget_source`). The receipt now carries `accounting` (per
  category: before, after, where), `dependents_found`, `still_held`, `still_holding_value`,
  `history` (`value_free_rows_kept` or `purged`), a `trace` of identifiers and `not_counted`.
  The after-scan runs once the receipt and its audit entry exist, so it counts them exactly as
  a later report does. Source removal updates the stored receipt after discarding cache copies.
- **Purge option.** `purge_history: true` on statement forget, entity forget and source removal
  (HTTP body and Python API). It is written into the journal entry, so a restore replays it.
- **Source removal gaps closed.** Connector instances, item revisions and import receipts and
  `knowledge_conflicts` rows for the source are now removed too (counted as
  `connector_records_removed`).
- **Restore accounting.** `restore` returns `removed_again`: per journal entry, what the backup
  still held and the replay removed (statements forgotten, entities removed, notes removed,
  statements invalidated, answers withdrawn, drafts cancelled, job results deleted, events
  redacted, connector rows removed, history purged, credentials revoked, grants removed), with
  totals, and discards job cache copies of results deleted again (the `restore` command passes
  the job cache).
  When the backup predates a forget, a receipt marked `replayed_on_restore` is written into the
  restored copy, so the report can still find unlinked residue and a repeated forget returns a
  receipt instead of failing. The verified backups beside the restored one are registered in
  the restored copy, because a backup never lists itself.
- **Deletion report.** `python3 -m alfred.desk deletion-report --subject-kind
  source|entity|statement --subject ID [--json]` and `GET
  /desk/deletion-report/{kind}/{id}` (owner only, read only, same loopback, Host/Origin and
  session checks as every desk route). Values are never included.
- **Export format 2.** Adds `review-history.json` (history of exported statements only, no
  values; history of left-out statements counted in `excluded`) and `routines.json` (routine
  settings and pulse intervals this credential authored, no runs). `statements.md` shows each
  statement's review steps. Each export is recorded in `desk.sqlite.exports.jsonl` beside the
  database (0600, identifiers and folder only) so receipts and reports can name exports still
  on disk; the register lives outside the database, so restoring an older backup does not
  forget an export exists. `placement` now lists the register as a live file.

## Tests

- New `tests/test_deletion_accounting.py` (14 tests). One fixture holds every kind of
  dependent: three reviewed statements (value, relationship, captured commitment) with
  history, a routine nomination, a saved answer with a voice playback record, three drafts in
  `proposed`, `verified` and an arbitrary `archived` state, a desk event, document and link, a
  job result with its cache copy, an executive record citing the note, an export on disk and a
  backup. Forget (statement, entity, source), purge, backup, restore and export run over it.
  Every receipt's after-counts equal the report's counts category by category, and both equal
  a direct scan written in the test with plain SQL, file checks and the export's own
  `statements.json`, independently of the scanner. HTTP: owner only, CSRF-protected purge,
  unknown kind 404. CLI: text and JSON output.
- Updated `tests/test_export.py` for format 2 (two new files, two new counts).
- `python3 -m unittest tests.test_deletion_accounting tests.test_memory_lifecycle
  tests.test_export`: 60 tests, OK.
- Full backend suite `python3 -m unittest discover -s tests`: 1,127 tests, OK (285 s), on the
  committed tree.
- No console code was touched, so the console build, unit and browser checks were not rerun.

## Limits

- Not secure erasure. SQLite free pages, the WAL before checkpoint, filesystem snapshots,
  sync copies and anything copied out by hand are outside every count (stated in each receipt
  and report as `not_counted`). `VACUUM` and encryption belong to plan item 1.1.
- Exports and backups are counted and listed, never deleted. A withdrawn answer keeps the
  question the person typed, and a completed or cancelled draft keeps its text; both are
  counted as still holding text.
- Linkage that existed only inside a value that is now gone cannot be rediscovered except
  through receipts. After restoring a backup that predates a forget, the replayed receipt
  restores that trace; residue unlinked by a forget whose receipt was lost some other way is
  not found.
- A statement report does not follow an entity forget or a source removal that covered the
  statement; ask for the entity or source report.
- The export register records exports written by this version onwards; earlier exports on
  disk are unknown to it.
- Statement and entity reports cover only the asking owner's records; a source report counts
  across the workspace but shows counts and identifiers only.
- No console view of the report yet.
