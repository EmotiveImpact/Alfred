# Paused memory-programme checkpoint

1 October 2026. Branch `feat/memory-programme-2026-10-01`, parent
`18dcfb39a3244fe21caf1d7ed2887443cf490914` (the tested M01/M03 draft head).
Main was rechecked at `8398c7437cb0ef1386d8dc4ff1f9e92fb2557ca2`.
PR #15's console refinement and PR #16 are unchanged.

The owner requested publishing everything to the master conversation after
pausing development to reconcile whole-product scope. See
[the master handoff](../../MASTER_HANDOFF_2026-10-01.md).

## Delivered versus unfinished

This preserves partial M02 person/device/source-policy code and partial M06
authorised-subset FTS5 ranking, plus the tested M01/M03 parent. Neither M02 nor
M06 is marked implemented. M04/M05/M07-M12 remain planned. No console/UI redesign,
HTTP enrolment/grants workflow, encryption, deletion/restore, account, microphone,
host deployment, new runtime or retrieval-quality comparison is delivered.

## Local validation

- `python3 -m unittest discover -s tests`: **671 tests pass**, comprising the
  existing 663 plus eight checkpoint regressions. [Complete result summary](core-summary.txt).
- The verbose rerun is retained as [local-tests.txt](local-tests.txt). Use the
  complete summary above for the total; the verbose output may end before its
  footer in the execution environment.
- Eight new tests use invented temporary Markdown, real SQLite and a fixed clock.
  They cover distinct identities, owner/source rotation, filtered keyword/FTS
  retrieval, separate model grants, stale policy epochs, grant expiry and
  mid-generation revocation. The provider is a declared Python fixture, not a
  model. No provider/network inference occurs.
- `python3 tools/check_memory_plan.py --self-test`: **12 tests pass**.
  [Named plan cases](plan-tests.txt). The consistency check also passes.
- Python syntax compilation and `git diff --check` pass.
- Exact tested first-party code hashes are retained in [source-sha256.json](source-sha256.json).
- Earlier failed preflight checks and corrections are recorded in
  [initial-check.txt](initial-check.txt). No failure is presented as passing.

The two existing M03 race wrappers now forward retrieval keyword arguments;
their original review-change/withholding assertions are unchanged. A missing
DeskStore policy-initialisation step found before publishing was corrected.

## Combined CI and limitations

New combined CI is to be inspected on this checkpoint's draft PR; it is not
claimed as passing by this pre-publication receipt. PR #16's successful run
36796267517 belongs to its exact parent head and is separately documented in the
[M03 receipt](../memory-m03/RECEIPT.md).

Passing these tests does not complete M02/M06 acceptance. Full identity/admin
and recovery workflows, grant-loss/review invalidation semantics, all final
persistence/display cases and frozen labelled retrieval measurements remain.
The tombstone table is a schema placeholder, not implemented deletion/restore.
Default legacy workspaces still use the coarse policy until explicitly changed.
Private-data release gates M02/M05 remain unmet.

No main merge, private-vault access, deployment, background service, live account,
audio/device effect, source archive mutation, upstream execution or model
experiment. Issue #11 remains open. This is a transferable WIP snapshot for
planning and review, not production readiness or a completed grand plan.
