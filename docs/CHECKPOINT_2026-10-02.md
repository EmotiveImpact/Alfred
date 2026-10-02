# Build checkpoint, 2 October 2026

Resume here. This records the state of the whole-product build at the stated commit; it is
not a release note and nothing here is merged to main or deployed.

## Where the work is

- **Branch:** `claude/alfred-development-qpgxhg`, draft PR
  [EmotiveImpact/Alfred#18](https://github.com/EmotiveImpact/Alfred/pull/18) to `main`.
- **Base:** main `8398c7437`. PR #16 (M01/M03), PR #15 (console) and PR #17 (partial
  M02/M06) are merged into this branch with ordinary merge commits
  ([receipt](evidence/integration-2026-10-02/RECEIPT.md)). PRs #15 to #17 stay open; once
  #18 is reviewed and merged they can be closed as superseded.
- **Mandate and context:** the owner-supplied documents are kept byte-exact in
  [sources/2026-10-02](sources/2026-10-02/README.md). How they were absorbed:
  [reconciliation record](RECONCILIATION_2026-10-02.md).
- **State of every requirement:** [requirement register](../plans/requirement-register.json),
  checked by `tools/check_requirement_register.py`. Sources reviewed or missing:
  [source-coverage register](../plans/source-coverage.json).

## Done on the branch (implemented and tested, not merged, not deployed)

| Area | Requirement IDs | Evidence |
|---|---|---|
| Connected console: real authorised projection, inspection, truthful states, server approvals | UX-001, UX-002, MEM-016 | [receipt](evidence/console-connected/RECEIPT.md), [adapter](../console/docs/CONNECTED_CONSOLE.md) |
| Selection-aware questions on the existing conversation queue | INT-001 (partial), MEM-006 | `tests/test_console_focus.py` |
| M04 remember-this capture and approved create-only inbox notes | MEM-005, MEM-011 | [receipt](evidence/memory-m04/RECEIPT.md) |
| M06 lexical baseline measured (keywords stay default) | MEM-008 (baseline) | [receipt](evidence/memory-m06/RECEIPT.md) |

## Partial on the branch

| Area | IDs | What is missing |
|---|---|---|
| M05 forgetting, backup, restore without resurrection, withheld-not-destroyed reviews | MEM-010, SYS-002 | Application encryption and key custody (owner decision), whole-source deletion receipts. [Receipt](evidence/memory-m05/RECEIPT.md). |
| M02 identity and grants (from PR #17) | SYS-001, MEM-009 | Grant and pairing workflows for other people; under strict grants another person sees nothing (shown in the browser test). |
| Executive records | ATT-002, ATT-001 | Responsible person, preparation briefs, decision options, cross-project insight, reminders. [Receipt](evidence/executive/RECEIPT.md). |
| Stage 0 job coordinator (local subprocess worker, bounded cache, HTTP routes) | RUN-002, RUN-003, SYS-003 | Any second node, mesh, remote worker or isolation backend; console view. [Design](JOBS.md). |

## Verification at this checkpoint

- `python3 -m unittest discover -s tests`: 812 pass locally.
- Console: build, 79 unit tests, 29 offline demo browser scenarios, and
  `tools/check_console_connected_browser.py` with 60 real-browser checks against the real
  server.
- Unified CI on PR #18 passed on every completed run from the integration onwards,
  including the new `console-connected` job (for example run 37038732066 on `9ec0f7904`).
- No model inference, private data, account, device, deployment or upstream execution.

## Decisions that need the owner

Listed with defaults in the [reconciliation record](RECONCILIATION_2026-10-02.md): where the
authoritative database and coordinator live; mesh control plane and key expiry; object
storage vendor, region and ceiling; which scopes may leave the primary machine; paid compute
or self-host only; trialling Space/SpaceFS; VPS provider; confirming NVIDIA OpenShell; key
custody for encryption; and the first real account for a read-only connector. Merging PR #18
also needs the owner's review.

## Next executable steps

1. M02: an owner workflow (HTTP and console Security panel) to view identity, enable strict
   grants and grant or revoke `read`, `model` and `inbox.write` per source, with grant
   changes already clearing the console view.
2. Console view of jobs: submit a bounded job on the selected note, follow its events, leave
   and return to read the reconciled result.
3. OPS-002: draft the capability contract as a schema with a synthetic read-only adapter and
   contract tests, without claiming any real product adapter.
4. ATT-002 gaps: responsible person and decision preparation briefs.
