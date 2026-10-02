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
  [source coverage](../plans/source-coverage.json). Of 33 requirements, 7 are implemented on
  the branch, 24 partial and 2 not started. The register gives no completion percentage on
  purpose.
- **Parallel work:** background agents build in lead-created worktrees under
  `.claude/worktrees/` (never committed) and the lead reviews and merges each branch with an
  ordinary merge commit. Open at this checkpoint: `wave2/routines` (M10 routines and
  procedures) and `wave2/temporal-review` (MEM-007 review workflow).

## Implemented on the branch (tested, not merged, not deployed)

| Area | IDs | Evidence |
|---|---|---|
| Connected console over the real backend | UX-001, UX-002, MEM-016 | [receipt](evidence/console-connected/RECEIPT.md) |
| Selection-aware questions on the conversation queue | MEM-006, INT-001 (partial) | `tests/test_console_focus.py` |
| Remember-this capture and approved create-only inbox notes | MEM-005, MEM-011 | [receipt](evidence/memory-m04/RECEIPT.md) |
| Executive records and workflows: responsible labels, decision options, assembled briefs, attention, derived insights | ATT-002 | [receipt](evidence/executive-2/RECEIPT.md) |

## Partial on the branch, with what changed today

| Area | IDs | Done | Still missing |
|---|---|---|---|
| Identity and grants | SYS-001, MEM-009 | grant workflows, invitations, offline rotation, device pairing by single-use code, own-device revocation, recovery documented | multi-owner administration, team roles, strict grants by default |
| Forgetting, backup, restore | MEM-010, SYS-002 | forget statements and entities, whole-source removal with receipts, journal-replaying restore | encryption and key custody (owner decision) |
| Sync safety and export | MEM-014, MEM-013 | conflict copies recognised and shown, live-file placement guard, portable export | other tools' conflicts, real sync clients, export encryption |
| Connectors | CON-001 | read-only .ics and .vcf export importers, connector status and Import switch in the console | a real account (owner decision) |
| Answer support | INT-002 | per-answer support report in the console; 12-case evaluation with denominators | semantic evaluation; the live-model comparison stays blocked |
| Index rebuild | MEM-012 | atomic `rebuild-index` keeping identities, revisions and reviews | connector re-import only; no schedule |
| Jobs | RUN-002, RUN-003, SYS-003 | local job coordinator, console jobs view, job history under strict grants | second node, isolation backend (owner decisions) |
| Specialist contract | OPS-002 | contract version 1 with a synthetic simulation adapter | real product interfaces (owner) |

## Verification at this checkpoint

- `python3 -m unittest discover -s tests`: 1048 pass.
- Console: build, 110 unit tests, 29 offline demo scenarios; connected browser checks
  (94), executive browser checks (45), sync-conflict browser check (5), and the seven
  backend browser suites.
- Unified CI on PR #18 has passed on every completed run, including the new executive and
  sync-conflict browser jobs.
- No model inference, private data, account, device, deployment or upstream execution.

## Decisions that need the owner

Where the authoritative database and coordinator live; mesh and key expiry; object storage
vendor, region and ceiling; which scopes may leave the primary machine; paid compute or
self-host; trialling Space/SpaceFS; VPS provider; confirming NVIDIA OpenShell; key custody
for encryption; the first real account for a connector; accepting the specialist contract;
whether voice may ever use a microphone; and review and merge of PR #18.

## Next executable steps

1. Review and merge `wave2/routines` and `wave2/temporal-review` when they report.
2. VOI-001 output only: spoken playback of an answer with honest generated, playing and
   acknowledged states, local voices only, no microphone.
3. Keep this checkpoint, the register and the PR #18 description current.
