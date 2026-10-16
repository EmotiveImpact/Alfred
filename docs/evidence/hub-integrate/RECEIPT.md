# Hub steps wired together receipt (AGENT_HUB.md steps H2, H3 and H4)

16 October 2026. Branch `feat/hub-integrate-2026-10-16`, started from `f51ba2c0b` (main with H1
to H4 merged as separate steps). **Tested commit: `b0c3a7f574aacb3fb433daef28481795501b7035` (the commit that adds this
receipt and the browser evidence changes no code).** Status: implemented on a local branch
against synthetic data only. Not pushed, not merged, not deployed, not reviewed by the owner.
The shared registers (CHANGELOG.md, BUGS_AND_FIXES.md, SESSION_HANDOFF.md, README.md, the
requirement register, the remaining build plan and docs/AGENT_HUB.md) were not edited; a
proposed changelog entry and register notes are in [CHANGELOG_ENTRY.md](CHANGELOG_ENTRY.md).

No model runs anywhere in this work and nothing touches the network. The only brains are the
deterministic H1 `SyntheticBrain` and a small test fixture that claims to be done and confident.
Nothing under `third_party/` was read as code, imported, installed or executed (the learning tests
point the upstream catalogue at a path that does not exist).

## What changed

### 1. Routing notes from verified outcomes (H3 reads H4)

`verification.outcome_rows` joins each ingested brain result with its verification record and
the packet's declared checks, and gives every result one evidence class:

| Class | When |
|---|---|
| `verified` | Declared checks all passed in a run (`checked`), or the owner acknowledged the exact run (`acknowledged`), and at least one check was declared. |
| `failed_checks` | A declared check failed, or H1 refused the bundle. |
| `unverifiable` | Checks declared but not run yet, or a check could not run. |
| `no_checks` | Nothing was declared. Kept apart, never counted as verified, even if the owner acknowledged it. |
| `not_returned` | The job stopped (failed, cancelled, over budget) and returned nothing. |

The daily learning run (`learning.gather`) now reads results through `outcome_rows`, counting per
brain, kind of work (the goal's `work` when the task came through the hub, otherwise
`brain_task`) and scope class. A result's time is the later of ingestion and its last check or
acknowledgement, so verifying it later brings it back into the window. Routing categories, in
order: `often_stops_at_budget`, `often_fails_checks` (at least 3 and a third of results),
`mostly_verified` (at least 3 and four fifths), `mostly_refused_or_stopped`, `mostly_not_verified`
(no checks or unverifiable, at least 3 and half), otherwise `mixed`. The threshold of 3 results
per group is unchanged. The note's detail carries every class count, `verified` as a number (it
was `null` before H4 was wired in), how many verified results were the owner's acknowledgement,
`no_checks_counted_as_verified: false` and the basis
`alfred_checks_and_owner_acknowledgement_not_brain_confidence`. Nothing the brain says (its
answer, confidence or "done") is read. Daily and window counts gain `results_<class>`.

`verification.outcomes` keeps its `by_brain` counts and adds `evidence_by_brain` and each
result's `declared` count and class. Verification is now per person (`policy.ledger`): the
owner's paired device can see, run and acknowledge the owner's results; the rows keep the task's
actor, so the H4 effect gate reads them exactly as before. `Verifier.verify` takes an optional
`expected_runs` and refuses a stale view with `verification_changed` (409).

### 2. Goal outcomes as learning evidence (H3 reads H2)

`GoalHub` journals, value-free, in `hub_journal` (and the audit log):

| Event | Target | Detail |
|---|---|---|
| `budget.warning`, `budget.hard_stop` | the goal, brain or overall budget | as before, plus `brain`: the brain whose accounted task triggered it |
| `goal.paused`, `goal.stopped` | the goal | `reason` (`operator` or the budget) and the assigned `brain` |
| `task.refused` | `tasks` | `reason` code, `stage` (`admission` or `dispatch`), `brain`, `work`, `trigger`, `mandate`, and the `job` at dispatch. `already_dispatched` (a duplicate start) is not a refusal and is not journalled. |
| `heartbeat.missed` | `heartbeats` | `mandate`, `brain`, number of slots `missed`, `due` |

The learning run reads budget warnings and hard stops, owner pauses and stops (a hold a budget
caused is counted once, as its hard stop), reassignments (attributed to the brain the goal was
moved from), mandate refusals and missed heartbeat slots as identifiers, codes, times and counts.
Only brain identifiers and reason codes matching strict patterns are kept. A new rule
`goal_outcomes` proposes one routing note per brain (`routing-goals:<brain>`) with at least 3
setbacks (hard stops, refusals, owner pauses, stops and moves); budget warnings and missed slots
are shown alongside. Daily and window counts gain `hub_budget_warnings`, `hub_hard_stops`,
`paused_or_stopped_by_you`, `work_reassigned`, `mandate_refusals` and `heartbeat_slots_missed`.

Routing notes stay notes: they never travel in a packet (H3's existing rule), and the trusted-kinds
rule can never accept them. The authority test now runs goal work first (a mandate with checks,
two tasks, a hard stop at the task budget, three refusals, one verified result), then snapshots
every table, including `hub_meta`, `hub_mandates`, `hub_controls`, `hub_tasks`, `hub_meter`,
`hub_heartbeats`, `hub_attention`, `hub_journal`, `verification_meta`, `verification_runs`,
`verification_results` and `executive_records`, and finds them unchanged after a learning run
and again after accepting every proposal.

### 3. Mandates declare acceptance checks (H2 carries H4)

A mandate may carry `acceptance`: a non-empty list of H4 checks without IDs, set at creation or
by a version-checked update, owner only, journalled with the other mandate settings. It is
validated by `verification.declare` and `verification.validate_acceptance` (unknown kinds and
parameters refused, at most eight checks); `effect_readback` is refused on a mandate
(`readback_needs_autonomy_two`) because a mandate also covers autonomy 0 and 1. A heartbeat task
is validated against the merge at authoring time.

For every task it authorises, `GoalHub` builds the packet's `acceptance` with the mandate's
checks first, then the task request's own checks with exact duplicates dropped, `declared_by:
mandate` and the mandate ID as `ref` (or `owner` when the mandate has none). The gate refuses a
packet under that mandate that lacks them (`mandate_checks_missing`), names another mandate
(`mandate_mismatch`), or whose checks no longer match (`mandate_checks_changed`). A brain never
declares checks: its bundle has no field for them (H4). The success test stays the owner's text;
nothing evaluates it. Databases created before this change gain the `acceptance` column on
start.

### 4. Verification over HTTP and in the console

Routes on the existing guarded desk handler (loopback Host and Origin, session cookie, CSRF on
every POST, exact JSON bodies):

| Route | What |
|---|---|
| `GET /desk/hub/results` | The caller's results of the last 30 days, newest 24 listed (up to 2000 scanned), each with its class, contract outcome, declared count, state, run count, goal and work, and the last run's per-check status (no reasons); counts per brain. A reader gets `available: false`, `owner_only`. |
| `GET /desk/hub/results/<job>` | One result: state, declared checks, the last 20 runs with their reports. Reasons can quote returned text, so when the result's sources can no longer be read under strict grants (`JobCoordinator.artefact` refuses), reasons are withheld (`reasons_withheld: true`). |
| `POST /desk/hub/results/<job>/verify` | `{"runs": n}`: runs the declared checks if `n` is still the number of runs; otherwise `verification_changed`. |
| `POST /desk/hub/results/<job>/acknowledge` | `{"run_sha256": ..., "accept_failures": bool}`: H4's acknowledgement of the exact run, explicit over failed checks. |

Only the submitting person (owner credential or the owner's paired device) can read or act;
anyone else is told `not_found`. Acknowledgement grants no authority: every drafted action still
needs its own exact approval.

The console's Goals and brains dialog gains a "Results and checks" section: a line per brain
(verified, failed checks, not verified, no checks declared), and a card per result with its
class, the last run per check, "Run checks" (only where checks are declared and the contract
accepted the result) and "Acknowledge…", which opens a confirmation first; over failed checks the
button says "Accept with failed checks" and the note names the failed checks. A result with no
declared checks offers neither and its line says it is never counted as verified. The goal card
lists the mandate's acceptance checks. Because results follow the person, the section is also
shown to the owner signed in with another of their keys than the one the host runs under (for
example a paired device), where the goals themselves are not; a reader sees none of it.

## Commands and results on the tested commit

Python 3.13.16 on Linux, real SQLite, real job coordinator and worker threads. Browser checks with
Playwright for Python 1.64.0 and Chromium 141.0.7390.37 (SwiftShader), `CHROMIUM_PATH` and
`ALFRED_CHROMIUM_PATH` set to `/opt/pw-browsers/chromium`. Node 22.22.0, npm 10.9.4.

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests` | 1427 tests (1410 existing plus 17 new), OK, none skipped, in 248.8 seconds. |
| The same command on the starting commit `f51ba2c0b` | 1410 tests, OK, in 249.8 seconds. |
| `cd console && npm ci && npm run build && npm test` | Build succeeds, with Vite's existing chunk size warning (main chunk 1649 kB against the configured 1400 kB limit). 18 files, 174 tests pass, 4 of them new in `console/tests/goals.test.ts`. |
| `python tools/check_hub_integrate_browser.py` (new) | 21 checks pass, no page errors, no request leaves the loopback origin. [Report](browser/browser-report.json) and screenshots in [browser/](browser/). The two browser console errors are the expected 401 from the session probe before sign-in and the 409 the server returns for the deliberately stale run count. |
| `tools/check_hub_goals_browser.py`, report to a scratch folder | 19 checks pass, no page errors. The committed hub-goals evidence was not rewritten. |
| `tools/check_learning_browser.py`, to a scratch folder | 28 checks pass, no page errors. |
| `tools/check_console_connected_browser.py`, to a scratch folder | 108 checks pass, no page errors. |
| `tools/check_routines_browser.py`, to a scratch folder | 52 checks pass, no page errors. |

`tests/test_hub_integrate.py` (17 tests):

- mandate checks: the owner attaches checks and every authorised packet carries them first,
  declared by the mandate, merged with the task's own; a heartbeat task carries them; owner
  only, version-checked and journalled; validated by H4's rules, with `effect_readback` refused
  on a mandate; the gate refuses a packet without them, with another mandate's, or with changed
  checks; a brain that claims to be done and confident is not verified by saying so; a database
  from before this change gains the column;
- journal: budget events and refusals name the brain; dispatch refusals carry the job; missed
  heartbeat slots are journalled;
- learning: verified outcomes counted per brain and kind of work; failed, unverifiable and
  unchecked results kept apart and never verified (an acknowledged result with no checks stays
  `no_checks`); goal outcomes become `routing-goals` notes and the run changes nothing in the hub
  or verification records; owner controls counted once and budget holds not counted twice;
- HTTP: session, CSRF, Origin and version checks on every route; only the submitting person
  (including the owner's paired device) reads or acts, a reader and a second owner do not;
  reasons withheld once read grants are revoked (`revoke_all`).

`tests/test_learning.py`: the routing test now expects verification classes and the new basis;
the authority test covers the hub and verification tables (above).

The new browser check runs the real loopback server with a `GoalHub`, its verifier and a brain
worker thread, serving the built console. Three synthetic goals: one whose mandate declares
checks the result fails (a section check and `claims_cited` against a task sent no excerpt), one
whose check it passes and one with no checks. It checks the goal card's checks line, each
result's class before any run, that the unchecked result offers no run or acknowledgement, the
per-brain line, running checks through the UI (verified on the server), the failed check shown
as on the server, a stale run count refused, the confirmation (nothing sent before it, cancel
changes nothing), the server recording the owner accepting the exact run over failed checks
with no authority granted, the unchecked result still not verified, no horizontal scroll at
390 px, a reader seeing no results or controls, and no foreign requests or page errors.

The full backend suite was first run while the browser checks and the console build were running
on the same machine. One existing H2 test,
`test_hub_goals.BudgetTests.test_lowering_a_limit_cancels_running_work_through_the_coordinator`,
failed once (`usage_basis` was `brain_not_started` rather than `metered`): it lowers a limit as soon as
the job is `running`, and under load the brain had not started its meter yet. It passed six times
in a row on its own and in the full rerun without other load (the result in the table). This
file is unchanged on this branch; the race is in the test's timing, noted here rather than
hidden.

Not run: the console's offline Playwright scenarios (`npm run test:browser`), because they need
the fixed port 4173, which other sessions on this machine may be using; they use fictional
fixtures with no backend and do not reach the goals dialog's results section.

## Limits

- **No host wiring.** No production entry point constructs a `GoalHub`; `DeskHTTPServer` accepts
  one (`goals=`), and only the tests and the browser tools pass it. On a real host the results
  routes answer `hub_not_configured` until that is built.
- **Verification is still run by request.** Nothing runs the checks automatically after ingest;
  the owner runs them from the console or a caller runs `Verifier.verify`. Until then a result
  with declared checks counts as `unverifiable`, never verified.
- **Budget attribution is approximate.** A budget event names the brain whose accounted task
  triggered that enforcement pass. If one supervisor cycle accounts tasks from several brains,
  a goal or overall budget event is attributed to the first of them; a brain budget event always
  names its own brain.
- **Reasons withheld only in the detail view.** The list view never carries reasons (only
  per-check status), and the detail view withholds them when the sources cannot be read. The
  check kinds and statuses themselves stay visible to the submitter.
- **Routing notes are deterministic counts**, not judgements of quality. `verified` means the
  owner's declared rules passed or the owner acknowledged a run; it is not factual entailment
  (see H4's limits).
- **Goal outcomes cover the last 30 days** and up to 2000 journal events per run, like the rest
  of the learning evidence.
- **CI.** A step for the new browser check was added to `.github/workflows/alfred-ci.yml` after
  the learning step; other branches editing the same job may conflict there.
