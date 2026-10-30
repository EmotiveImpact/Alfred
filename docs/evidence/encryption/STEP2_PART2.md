# Encryption step 2, part 2 receipt: reviewed memory, its bin and capture

Built 30 October 2026 on part 1 (PR #50, including its fix 717d813c6), which has not merged yet;
part 2 goes up only after it does. Tested revision: TESTED_REVISION (the commit carrying this
receipt changes only this file). Synthetic keys and invented memory only. Nothing under
`third_party/` was read, imported or executed, and no model ran.

Requirements: SYS-002 (private storage), memory job M05. Plan: integration plan phase 1, step 2,
part 2 of 5. Nothing here lets a workspace in use be sealed; part 5 adds the `seal` command and
unlocking at start.

## What was built

- `alfred/sealing.py`: six tables join the `TABLES` register. Sealed: `memory_entities.name`,
  `memory_claims.value`, `memory_capture.captured_from`, `memory_bin.snapshot`,
  `capture_policies.name` and `rule`. Keyed fingerprints: `memory_claims.request_hash`,
  `note_hash` and `quote_hash`, and `capture_proposals.line_hash`. A table that keeps only
  fingerprints has no sealed column, and the check for a lost sealing record skips it.
- `alfred/reviewed_memory.py`: records and statements are sealed when written and opened when
  read; the request hash is keyed in the statement's area; conflict checks compare opened text.
  `statement_area` (the area the supporting note's text was sealed under, else the default
  area) and `entity_area` (the default area) are the one place each is chosen; `entities_of`
  is the one reader of a person's records with their names opened. Undo seals what it puts
  back in each value's own area.
- `alfred/memory_bin.py`: each copy is sealed whole, a statement's copy in its statement's area
  and a record's copy in the record's area; every reader opens it, and trimming a record's copy
  after an absolute forget seals it again.
- `alfred/capture_policies.py`: a policy's name and rule are sealed in the default area
  (`policy_area`), keeping the stored value when the text is unchanged; a matched line is kept
  as its SHA-256 keyed in its note's area, so the request and deferral ids made from it are
  derived from the keyed form.
- Readers updated: `lifecycle` (restore names restored records and statements opened, beside
  part 1's fix for sources), `export` (where a capture came from), `routines` and `executive`
  (record names). Two readers that never use where a capture came from now select only the
  columns they use.

## Tests

- `tests/test_sealing_memory.py` (9 tests), each run first against part 1 and failing there:
  - views, the bin's labels, capture's policy view and export still read correctly from sealed
    values, a rescan still recognises an offered line, and undo puts back the names and text
    a forget cleared;
  - the database, write-ahead log, shared memory and lifecycle journal, after records,
    statements, a capture, a capture policy run and ordinary forgets of a statement and a
    record, hold none of ten invented words (in three cases), the decision line or the note
    path, nor the plain SHA-256 of any statement request, the captured line, the deferral and
    request ids derived from it, or any line, word or policy name, whole or as 16, 24, 32 and
    40 character prefixes;
  - reading memory, the bin, capture and export seals nothing, and saving an unchanged policy
    seals nothing while a renamed one seals only its name;
  - a statement's text or a bin copy moved to another row does not open;
  - destroying the area refuses memory, the bin and capture (`area_destroyed`, 410);
  - with every source placed in a client area, statements, their request hashes, captures,
    captured lines and statement bin copies are in the client area, and records, policies and
    a record's bin copy in the default area;
  - the register lists the six tables, and a lost sealing record is refused when only a
    record's name is sealed.
- `tests/test_sealing.py`: the register check now creates the memory and capture tables, so
  it confirms every registered column exists and every key column is bound into a value's
  context.
- `tests/test_two_layer_delete.py`: a restore's list of what came back names the restored
  record and statement as the opened stored names; it failed sealed before `_held` opened them.
- `tests/test_deletion_accounting.py`: counting bin copies reads them opened, so it holds in
  both modes.
- A scripted plain scenario (records, statements, a capture, a policy saved twice and run,
  ordinary and absolute forgets, an undo, then every view and an export), run with fixed random
  ids on part 1 (717d813c6) and on part 2, gave the same views, export and rows in all 54
  tables, apart from the inode numbers of the scenario's own temporary vault folder.
- Whole suite, plain (`python -m unittest discover -s tests`): 1,951 tests, all passing.
- Whole suite, sealed (`python tests/sealed_suite.py`): 1,951 tests, all passing, with
  53,324 values sealed in the process.
- `tools/check_public_hygiene.py`, `tools/check_claims.py --base origin/main --branch
  claude/project-thread-9npowk`, `tools/check_requirement_register.py`,
  `tools/check_memory_plan.py`, `tools/check_adoptions.py` and `tools/egress_audit.py`: all
  pass.

## Not covered yet

- A workspace cannot be switched to sealed outside tests (part 5), which also keys the
  fingerprints a plain workspace already holds.
- Answers and drafts that cite statements keep a copy of their text in conversation records,
  and executive records and learning keep their own text, until parts 3 and 4.
- Areas: a record's name is in the default area whatever its statements' areas, and a
  record's bin copy holds the statements forgotten with it in the record's area. Nothing
  crosses areas until part 5's folder rules put notes outside the default area; both are part
  of the owner's open choice about answers drawing on several areas (`docs/ENCRYPTION.md`).
- Record and capture policy ids are not sealed; the console makes random record ids.
- A sealed value is bound to its row but not to its version, so an older value of the same
  row could be put back by someone able to write the database (stated in `docs/ENCRYPTION.md`).
