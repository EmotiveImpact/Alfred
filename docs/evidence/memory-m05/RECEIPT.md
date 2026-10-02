# M05 receipt: unavailable versus deleted, forgetting, backup and restore

2 October 2026, branch `claude/alfred-development-qpgxhg`. Status: **in progress**. Three
of M05's acceptance points have synthetic evidence; application encryption and key custody
(SYS-002) do not, because they need an owner decision.

## Defect found and fixed

Losing a source grant permanently invalidated reviewed statements and cleared their values,
and regranting could not restore them (reproduced before the change). Reconciliation now
separates two cases:

- **Changed**: the supporting note was edited, renamed, deleted or returned under a new
  revision. The review is invalidated, as before. The earlier M01/M03 rule that a revision
  change is never silently revived is kept.
- **Withheld**: the file is temporarily unreadable, the source is unavailable, its
  credential is revoked or expired, or the reader no longer holds a grant. The review stays
  recorded but is unusable, and its value is hidden from every view. Restoring access
  restores it while the supporting revision is unchanged.

Two older tests asserted that any temporary loss invalidates. They now assert the stronger
M05 behaviour: withheld, unusable and value hidden during the loss, and invalidated (not
revived) when the source returns under a new revision.

## Implemented

- `ReviewedMemory.forget` and `forget_entity`, with HTTP routes and owner-only console
  controls. Each returns a receipt naming what was removed, saved answers withdrawn, undecided
  drafts cancelled, completed drafts not undone, and what remains (audit identifiers, lineage
  without values, older backups, SQLite free pages and WAL). Secure erasure is not claimed.
- `alfred/lifecycle.py`: an append-only, fsynced journal written before the database changes
  for forgets and for credential and grant revocations; consistent backups through SQLite's
  backup API with a hashed manifest; an offline restore that verifies the hash, replays the
  whole journal into a staging copy, runs an integrity check and only then replaces the
  database. `python3 -m alfred.desk backup` and `restore --backup-file` refuse to restore
  while ALFRED holds its lock.

## Evidence

- `tests/test_memory_lifecycle.py`: 14 tests, including grant loss and regrant, outage then
  fresh review, forgetting across retrieval, conversation answers and pending drafts, entity
  forgetting, restore without resurrection of forgotten statements, revoked credentials or
  revoked grants, tampered backups and a corrupt journal.
- `tools/check_console_connected_browser.py`: forgetting from the inspector in a real browser.
- Full suite: 713 tests pass.

## Not done

Application-level encryption of the database and backups, key custody and recovery keys
(SYS-002, owner decision). Receipts for whole-source deletion. Scheduled backup rotation.
Restore of a backup taken on another machine. Private data remains gated by M02 and M05.
