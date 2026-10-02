# Build checkpoint, 2 October 2026 (evening)

Resume here. This records the state of the whole-product build on the integration branch;
it is not a release note, and nothing here is merged to main or deployed.

## Where the work is

- **Branch:** `claude/alfred-development-qpgxhg`, draft PR
  [EmotiveImpact/Alfred#18](https://github.com/EmotiveImpact/Alfred/pull/18) to `main`.
- **Base:** main `8398c7437`, with PRs #15, #16 and #17 merged in
  ([receipt](evidence/integration-2026-10-02/RECEIPT.md)). They stay open until #18 is
  reviewed and merged, then can be closed as superseded.
- **Mandate and context:** [sources/2026-10-02](sources/2026-10-02/README.md) and the
  [reconciliation record](RECONCILIATION_2026-10-02.md).
- **State of every requirement:** [requirement register](../plans/requirement-register.json),
  checked by `tools/check_requirement_register.py`; sources in
  [source coverage](../plans/source-coverage.json). Of 33 requirements, 8 are implemented on
  the branch, 24 partial and 1 not started. The register gives no completion percentage on
  purpose.
- **Parallel work:** background agents build in lead-created worktrees under
  `.claude/worktrees/` (never committed) and the lead reviews and merges each branch with an
  ordinary merge commit. Both wave 2 branches are merged: `wave2/temporal-review` (MEM-007,
  merge `afbf72b8d`) and `wave2/routines` (M10, merge `e5917441e`). No agent branch is open.

## Implemented on the branch (tested, not merged, not deployed)

| Area | IDs | Evidence |
|---|---|---|
| Connected console over the real backend | UX-001, UX-002, MEM-016 | [receipt](evidence/console-connected/RECEIPT.md) |
| Selection-aware questions on the conversation queue | MEM-006, INT-001 (partial) | `tests/test_console_focus.py` |
| Remember-this capture and approved create-only inbox notes | MEM-005, MEM-011 | [receipt](evidence/memory-m04/RECEIPT.md) |
| Executive records and workflows: responsible labels, decision options, assembled briefs, attention, derived insights | ATT-002 | [receipt](evidence/executive-2/RECEIPT.md) |
| Temporal review: recorded history of every review transition, valid periods, disputes, supersession with lineage, as-of report, console review queue | MEM-007 | [receipt](evidence/temporal-review/RECEIPT.md) |

## Partial on the branch, with what changed today

| Area | IDs | Done | Still missing |
|---|---|---|---|
| Identity and grants | SYS-001, MEM-009 | grant workflows, invitations, offline rotation, device pairing by single-use code, own-device revocation, recovery documented | multi-owner administration, team roles, strict grants by default |
| Forgetting, backup, restore | MEM-010, SYS-002 | forget statements and entities, whole-source removal with receipts, journal-replaying restore | encryption and key custody (owner decision) |
| Sync safety and export | MEM-014, MEM-013 | conflict copies recognised and shown, live-file placement guard, portable export | other tools' conflicts, real sync clients, export encryption |
| Connectors | CON-001 | read-only .ics and .vcf export importers, connector status and Import switch in the console | a real account (owner decision) |
| Answer support | INT-002 | per-answer support report in the console; 13-case evaluation with denominators | semantic evaluation; the live-model comparison stays blocked |
| Routines and procedures | ATT-001, MEM-004, MEM-015 | commitment review and morning brief with schedules, budgets, quiet hours, pause and inspectable runs; reminders and draft offers that still need exact approval; read-only procedure registry | real time zones and who else may author routines (owner decisions); no delivery outside the app |
| Voice output | VOI-001 | read-aloud with on-device voices only; generated, played (device report), stopped and acknowledged kept apart; hash and length only on the server | any microphone or listening (owner decision) |
| Host health | RUN-001 | console health panel from the foreground host; owner pause and resume with confirmation | installed service, offline recovery |
| Index rebuild | MEM-012 | atomic `rebuild-index` keeping identities, revisions and reviews | connector re-import only; no schedule |
| Jobs | RUN-002, RUN-003, SYS-003 | local job coordinator, console jobs view, job history under strict grants | second node, isolation backend (owner decisions) |
| Specialist contract | OPS-002 | contract version 1 with a synthetic simulation adapter | real product interfaces (owner) |

## Verification at this checkpoint

Run locally on merge `e5917441e`:

- `python3 -m unittest discover -s tests`: 1112 pass.
- Console: build, 140 unit tests, 29 offline demo scenarios; connected browser checks
  (98), executive (45), temporal review (50), routines (52), read-aloud (12) and
  sync-conflict (5) browser checks.
- Unified CI on PR #18 runs every one of these browser checks and has passed on every
  completed run, most recently on the temporal merge `afbf72b8d`.
- No model inference, private data, account, device, deployment or upstream execution.

## Decisions that need the owner

Where the authoritative database and coordinator live; mesh and key expiry; object storage
vendor, region and ceiling; which scopes may leave the primary machine; paid compute or
self-host; trialling Space/SpaceFS; VPS provider; confirming NVIDIA OpenShell; key custody
for encryption; the first real account for a connector; accepting the specialist contract;
whether voice may ever use a microphone; and review and merge of PR #18.

Raised by the wave 2 work:

- Routines use fixed UTC offsets with no daylight saving. Should they use real time zones?
- Only the owner key the host runs under can author routines. Should the same person's
  paired devices be allowed? That needs per-person routine credentials.
- An accepted draft offer becomes a ledger proposal that expires after 15 minutes, which
  uses up the offer for that commitment version. Keep, or re-offer?
- Supersession retracts the replaced statement; it does not record that the old one stayed
  true for an earlier period. Should accepting a replacement close the old valid period?
- Should statement review history be included in portable exports, and should forgetting
  also purge value-free history rows?

## Next executable steps

1. Confirm unified CI on the routines merge.
2. Export statement history and routine settings in the portable export (MEM-013), once
   the owner answers the export question above.
3. Keep this checkpoint, the register and the PR #18 description current.
