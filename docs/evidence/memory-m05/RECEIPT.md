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

## Whole-source removal (added later on 2 October)

An owner can remove a whole source from ALFRED: `POST /desk/sources/{id}/forget` with the
source ID typed back as confirmation, or "Remove this source from ALFRED" in the console
inspector for a source, which asks for explicit consent. `alfred/lifecycle.py`
(`forget_source`) journals `source_forgotten` first, then in one transaction:

- revokes the source credential, so nothing can index or report under it again;
- deletes its indexed notes, links, identities, revision history, anchors, vault binding
  and source record, leaving tombstones that keep a hash of each path, not the name;
- invalidates every reviewed statement supported by any of its notes, current or past,
  removing their values (there is no revival if the folder is added again later);
- withdraws saved answers that cited its notes, as evidence, reviewed support or focus;
- cancels undecided drafts bound to its notes or evidence and pending inbox notes for it,
  and lists completed drafts as not undone;
- redacts the summaries of evidence events it reported and the titles of its documents;
- deletes job results derived from it, from the database and from the local job cache.
  The job record stays visible to its submitter, marked as having had its result removed.

The receipt counts each of these and says what remains: the person's own files (ALFRED never
reads, edits or deletes them for this), identifiers and hashes in audit and job records,
invalidated statements without values until forgotten, older backups (a restore replays the
removal), completed drafts, and SQLite free pages. Secure erasure is not claimed.

Evidence: `tests/test_memory_lifecycle.py` (`SourceForgetTests`, which also reruns the earlier
lifecycle tests, plus an HTTP test with typed confirmation, CSRF and owner checks) and the
source-removal scenario at the end of `tools/check_console_connected_browser.py`
([screenshot](../console-connected/connected-source-removed.png)).

## Not done

Application-level encryption of the database and backups, key custody and recovery keys
(SYS-002, owner decision). Scheduled backup rotation.
Restore of a backup taken on another machine. Private data remains gated by M02 and M05.
