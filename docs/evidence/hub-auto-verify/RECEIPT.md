# Automatic verification receipt (backlog A3)

17 October 2026. Branch `claude/project-thread-att046-hub-auto-verify`, started from `main` at
`d81a5d509`. **Tested commits: `c3ce35297`** (the change and its unit tests) **and `417600bc4`, `7945e5c4e`** (the
goals panel browser check updated to match; no other code). The commits that add this receipt change
no code.
Synthetic data only. Not merged, not deployed. The shared registers (CHANGELOG.md,
SESSION_HANDOFF.md, docs/INDEX.md) are updated after the merge.

No model runs and nothing touches the network. Every brain in the tests is the H1
`SyntheticBrain` or a scripted variant of it.

## What changed

Before, a goal task's result stayed `unverifiable` until the owner pressed verify, even when its
mandate declared acceptance checks. Now:

- `GoalHub.cycle()` runs `_account()`, then the new `_auto_verify()`, then the heartbeats.
- `_account()` marks a task `auto_verify='pending'` when its result was `accepted` and its packet
  declared acceptance checks; otherwise `not_needed`.
- `_auto_verify()` runs each pending task's declared checks once, as the host, with
  `Verifier.verify(..., expected_runs=0, initiated='automatic')`. The zero-runs condition is
  checked inside the transaction that records the run, so a restart, a second cycle or the owner
  verifying at the same moment never gives a second run. It then marks the task `ran` or
  `not_run[:reason]`, and logs `hub.auto_verify_not_run` for the latter. A failure on one task
  never stops the others or the heartbeats. At most `ACCOUNT_PER_CYCLE` (32) tasks per cycle.
- `verification_runs` gains `initiated` (`automatic` or `owner`); runs recorded before this read
  as `owner`. The value is shown on `last_run` and in `runs()`. It changes nothing about how a
  run is judged or counted. The HTTP route cannot set it: `verify_result` still accepts only
  `runs`.
- `hub_tasks` gains `auto_verify`. Both columns are added in place on older databases
  (`PRAGMA table_info` then `ALTER TABLE ADD COLUMN`). Tasks accounted before the change keep
  `NULL` and are never run late.
- The two positional `INSERT`s now name their columns.

## Tests

`tests/test_hub_auto_verify.py`, 17 tests, written before the code:

- passing checks become `verified` on the next cycle with no owner action, with one `automatic`
  run;
- failing checks become `failed_checks`; a brain claiming every task is done still fails;
- results without checks, refused bundles and jobs that never ran are left alone;
- the automatic runs follow the accounting batch;
- a crashing check is `unverifiable`; a run that cannot start is recorded with its reason and
  the cycle carries on to the next task;
- never twice: repeated cycles, a run recorded before a crash, a pending task left by a crash,
  and an owner run made first;
- an unknown initiator is refused (`invalid_initiated`);
- an older database reads its runs as the owner's, gains the columns once, and runs nothing new;
- daily learning counts an automatic run exactly like an owner run.

Four existing tests assumed no run until the owner acted. Each keeps its purpose:

| Test | Was | Now |
| --- | --- | --- |
| `test_hub_integrate` `test_routes_keep_the_session_csrf_origin_and_version_checks` | listing shows 0 runs, `unverifiable`; owner verifies at `runs: 0` | listing shows 1 `automatic` run, `failed_checks`; CSRF, origin, stale-version and extra-field refusals unchanged; owner re-runs at `runs: 1` and that run reads `owner`; `runs_total` 2 |
| `test_hub_integrate` `test_only_the_submitting_person_reads_or_acts` | no rows in `verification_runs` after others try | only the one `automatic` row: other people still add nothing |
| `test_hub_integrate` `test_failed_unverifiable_and_unchecked_results_are_kept_apart_and_never_verified` | the confident brain's results are `unverifiable` | they are `failed_checks`, still `verified` 0 (declared but never run is covered by the new not-run tests) |
| `test_learning` `test_a_learning_run_changes_no_policy_grant_scope_autonomy_or_budget` | `results_verified` 1 | 2: both goal results were checked on arrival; the run still changes no policy, grant, scope, autonomy or budget |

## Commands and results at `c3ce35297`

```
python3 -m unittest discover -s tests -p "test_hub_auto_verify.py"   # 17 tests OK, three runs
python3 -m unittest discover -s tests -p "test_hub*.py"              # 69 tests OK
python3 -m unittest discover -s tests -p "test_verification*.py"     # 36 tests OK
python3 -m unittest discover -s tests -p "test_learning*.py"         # 39 tests OK
python3 -m unittest discover -s tests                                # Ran 1444 tests in 234.8s, OK
python3 tools/check_claims.py --base origin/main --branch claude/project-thread-att046-hub-auto-verify   # claims ok
```

## Browser checks at `417600bc4` and `7945e5c4e`

`tools/check_hub_integrate_browser.py` asserted that results stayed unverifiable until the owner
ran the checks, so it now waits for the automatic run. It checks that each declared result has one
run recorded as `automatic` (`failed_checks` for the failing goal, `verified` for the passing one),
and that the panel shows those classes on arrival with `Run 1`. The owner's re-runs count from
`Run 2` and are recorded as `owner`. The stale-count refusal, the acknowledgement confirmation and
the per-brain line are checked as before. The screenshot taken before the owner acts is now named
`results-on-arrival.png`.

Run locally with Playwright 1.57.0 and the preinstalled Chromium, after `npm ci && npm run build` in
`console/`:

```
tools/check_hub_integrate_browser.py   # {"passed": 23, "page_errors": []}
tools/check_hub_goals_browser.py       # {"passed": 19, "page_errors": []}
tools/check_learning_browser.py        # {"passed": 28, "page_errors": []}
```

Before the update, the first check failed at "before any run, declared checks are not verified".

`7945e5c4e` closes a race found when rerunning: the passing result's chip already read verified, so
the check could ask the server before the owner's second run was recorded. It now waits for
`Run 2` on the card. The goals panel check then passed three times in a row.

## Left for later

- The web desk does not yet show who started a run (backlog C3).
- `docs/AGENT_HUB.md` has a note under the build table; its "Still to do" cell is tidied after
  this and the hub host pull request both merge, to avoid a conflict between them.
