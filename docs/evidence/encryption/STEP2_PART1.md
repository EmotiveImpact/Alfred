# Encryption step 2, part 1 receipt: the sealing layer and vault notes

Built 17 October 2026 and brought onto `main` on 30 October 2026, after step 1 (PR #26, keys,
unlocking and the two-layer delete) merged. Tested revision: TESTED_REVISION
(the commit carrying this receipt changes only this file). Synthetic keys and invented notes
only. Nothing under `third_party/` was read, imported or executed, and no model ran.

Requirements: SYS-002 (private storage), memory job M05. Plan: integration plan phase 1, step 2,
part 1 of 5. Nothing here lets a workspace in use be sealed; part 5 adds the `seal` command and
unlocking at start.

## What was built

- `alfred/sealing.py`: plain and sealed sealers, keyed fingerprints, the `TABLES` register,
  `open_row` and `seal_row`, the per-database sealing record and its refusals, a connection
  type that carries its sealer, and a bounded cache of opened values that still refuses a
  destroyed area.
- `alfred/local.py` and `alfred/desk_store.py`: every store finds its database's sealer when
  it opens and checks the sealing record; `opened` and `sealed` helpers.
- `alfred/knowledge.py`: the vault index seals note paths, titles, text, tags, aliases,
  headings, link targets, the vault label, settings and scan errors and the path history, and
  keys note fingerprints and front-matter ids. Sorting by sealed columns moved to Python. A
  value whose text is unchanged keeps its stored sealed form, so rescans seal nothing new.
  `source_area`, `note_area` and `note_fingerprint` are the one place a note's area is chosen.
- `alfred/connectors.py`: an import's label and receipts are sealed and its item ids keyed.
- Readers of note rows updated to open them: `connectors`, `inbox`, `vault_append`,
  `sync_conflicts`, `lifecycle` (forgetting, which also empties the cache, and restore, which
  checks the sealing record), `reviewed_memory`, `conversation`,
  `executive`, `jobs`, `capture_policies`, `policy`, `console_api`.
- `tools/evaluate_retrieval.py`: compares the frozen corpus with the index in the index's
  stored digest form.
- CI: a `sealed-suite` job in `.github/workflows/alfred-ci.yml`.

## Tests

- `tests/test_sealing.py` (25 tests): plain pass-through; sealing and opening; values open
  only in their own table, column and row; empty and refused values; keyed fingerprints per
  area, stable across rotation, refusing malformed digests; destroying one area leaving
  another readable; a destroyed area refused even from the cache; the cache's byte bound,
  `clear_cache` and `close`; unchanged text keeping its stored value and a changed area
  sealing again; the register naming real columns, every plain key column bound into a
  value's context, and the keyed id columns; attaching by path through `..` and a symbolic
  link; a new workspace marked sealed; `workspace_locked`, `wrong_keyring`,
  `workspace_not_sealed` and `sealing_record_damaged` (a second record, and a lost record
  beside sealed values, plain or sealed); search and reading notes in a sealed workspace; an
  unchanged rescan sealing nothing and an edit sealing only that note's text and history; a
  value moved to another note refused; destroying the area erasing the index.
- The at-rest scans in `tests/test_sealing.py` read the database, write-ahead log, shared
  memory and lifecycle journal after indexing an invented vault, and again after a rename, a
  sync conflict copy, a scan error naming a path, and forgetting the source. They find none
  of its ten private words (in three cases), its paths, or the plain SHA-256 of any note, path
  or front-matter id, whole or as the 16 and 24 character prefixes the logs use. Run against a
  plain workspace the check fails and names every word, and with plain fingerprints it fails
  on the digests, so it does detect both.
- `tests/sealed_suite.py` first checks that a store made the ordinary way is sealed, and a
  full run fails if it sealed nothing.
- Tests that read storage directly or compare digests ALFRED returns now use
  `tests/stored_helpers.py`, so they hold in both modes: `test_knowledge`, `test_connectors`,
  `test_memory_m01`, `test_jobs`, `test_memory_capture_inbox`, `test_vault_append`,
  `test_scrub_wiring`.
- Whole suite, plain, with the pinned library in a fresh virtual environment (Python 3.13.16):
  PLAIN_RESULT.
- Whole suite, sealed (`python tests/sealed_suite.py`): SEALED_RESULT.
- `tools/check_claims.py --base origin/main --branch claude/project-thread-9npowk`, plan and
  requirement register checks: CHECKS_RESULT.

## Not covered yet

- A workspace cannot be switched to sealed outside tests (part 5).
- Reviewed memory, capture, conversations, executive records, drafts and actions, learning,
  goals and jobs still store plain text and plain fingerprints (parts 2 to 4). A proposed
  vault append keeps its note path, inserted text and diff plain in the action until part 3.
  Capture keeps plain line hashes until part 2, and so does the forgetting bin
  (`memory_bin`), which keeps copies of reviewed memory for 30 days.
- Folder and source rules for areas: every note is in the workspace's default area until
  part 5.
- Sync conflict rows are bound to their vault, not to one conflict, and a note's sealed text
  is not bound to its revision, so an older text of the same note could be put back by
  someone able to write the database (both stated in `docs/ENCRYPTION.md`).
- Keyed fingerprints and ids are made per area; moving a note between areas is part 5's to
  handle.
