# MEM-012 receipt: rebuild the index without losing history

2 October 2026, branch `claude/alfred-development-qpgxhg`. Status: **partial**. The commit that
adds this receipt is the tested source; unified CI on that commit is the independent rerun.
Synthetic vault only.

## What exists

`python3 -m alfred.desk rebuild-index` (offline: it refuses while the host holds its lock)
rebuilds one vault source's note, link and anchor tables from the Markdown files, which are
canonical. `alfred/rebuild.py` drops those projections inside the scanner's single write
transaction (`replace_notes(..., rebuild=True)`), so the durable catalogue (revision
history, identities and the vault binding) restores every note identity and revision. If
the vault cannot be read, the transaction never runs and nothing changes. Reviewed
statements, tombstones, receipts and the lifecycle journal are never rebuilt.

A rebuild is not a reset. Text that changed on disk since the last scan gets a new
revision and invalidates the reviews that cited it, exactly as an ordinary scan does, and
nothing invalidated is revived. Each run returns a reconciliation report: notes before and
after, how many kept the same identity and revision, new revisions, notes no longer present,
new notes, whether the links are unchanged, and every reviewed statement whose state
changed. The audit log records the rebuild.

## Evidence

`tests/test_rebuild.py` (7 tests, real SQLite, synthetic demo vault):

| Test | Shows |
|---|---|
| keeps every identity, revision, link and review | all 20 notes keep identity and revision, links are unchanged, the accepted review stays accepted |
| offline edit | exactly one new revision is reported and exactly the review citing it is invalidated |
| reverting the text | the review stays invalidated; the returning text gets a further revision (no revival) |
| deleted file | reported as no longer present; its review is invalidated |
| unreadable vault | the rebuild is refused and the earlier projections are untouched |
| older schema | a version 1 database (unique paths) migrates to version 2 and then rebuilds without loss |
| offline only | the command refuses while the host lock is held |

## Not done

- Connector sources are rebuilt by importing their export again, not by this command.
- The executive, conversation and job tables are records, not projections, and are not
  rebuilt; the console projection and keyword search are computed on request.
- No rebuild over HTTP or from the console, and no scheduled verification that projections
  match the files.
