# Goals, mandates, budgets and heartbeats receipt (AGENT_HUB.md step H2)

16 October 2026. Branch `feat/hub-goals-2026-10-16`, started from `def198223` (H1 brain plug and
strict grants already present). **Tested commit: `7b65ca25e6170fc486e46cd017d25f8a0fcac92e` (the
commit that adds this receipt and the browser evidence changes no code).** Status: implemented on
a local branch against synthetic data only. Not pushed, not merged, not deployed, not reviewed by
the owner. The shared registers (CHANGELOG.md, BUGS_AND_FIXES.md, SESSION_HANDOFF.md, README.md,
the requirement register, the remaining build plan and docs/AGENT_HUB.md) were not edited; a
proposed changelog entry and register notes are in [CHANGELOG_ENTRY.md](CHANGELOG_ENTRY.md).

No model runs anywhere in this work. The only brains are the deterministic H1 `SyntheticBrain`
and two small fixtures in the tests. Nothing under `third_party/` was read as code, imported,
installed or executed.

## What exists

`alfred/hub_goals.py` holds the whole step. Changes elsewhere are small and additive.

| Part | What it does |
|---|---|
| Mandate | Links one of the owner's existing executive goal records (`executive_records`, kind `goal`, status `active`) to: a scope class, a deadline, a success test (owner text; nothing evaluates it, and the view says so), an autonomy level per kind of work (0 to 2; 3 and 4 refused with the H1 `autonomy_requires_pilot_gates`), the allowed brains, the assigned brain, a tool allowlist (a subset of the owner's `BrainPolicy.permitted_tools`), a budget and an optional heartbeat schedule. One live mandate per goal; no parallel goal store. Creation is idempotent by request ID; every update names the version the owner saw (`mandate_changed`). The goal and scope class cannot be changed. A brain is accepted only if it is plugged in, declares the scope class, passes the owner's cloud rule and is not stopped. |
| Authority | Only the owner credential the host runs under may author mandates, budgets, controls and tasks (`hub_owner_not_hosted`), the same rule as routines, because heartbeats, ingestion and cancellation run under it. A reader is told `owner_only`; another owner `not_hosted`. |
| Gate on `BrainHub` | `GoalHub` attaches itself as `BrainHub.gate`. Every brain task must then carry a binding to a current mandate whose ID is the packet's `goal.ref`, and stay inside it: scope class, kind of work, autonomy at or below the mandate's level, an allowed brain, tools on the allowlist, goal active, deadline not passed, mandate, brain and hub not paused or stopped, workspace not paused. Anything else is refused before a job exists (`mandate_required`, `mandate_mismatch`, `scope_class_outside_mandate`, `work_kind_not_in_mandate`, `autonomy_above_mandate`, `brain_not_in_mandate`, `tool_not_in_mandate`, `goal_paused`, `goal_stopped`, `goal_not_active`, `mandate_expired`, `brain_paused`, `brain_stopped`, `hub_paused`, `workspace_paused`). H1 policy runs first. The task links back to its mandate and goal (`hub_tasks`) in the same transaction as the H1 `brain_tasks` row. |
| Dispatch recheck | `GoalHub.backend()` returns a `BrainBackend` that asks the hub again just before a brain starts. A `brain_task` job submitted to the coordinator by any other route, or whose mandate changed while it was queued, fails with no brain run. The start is recorded first (`hub_meter`, state `running`). |
| Budgets | Per goal (in the mandate), per brain and overall (`hub_controls`), each with daily and total limits on tokens, money (pence), wall time and task count, a warning percentage and the fixed UTC offset that decides where a day starts. An overall budget must exist before any task is admitted (`overall_budget_required`). |
| Admission | A task is admitted only if measured usage of finished tasks, plus the ceilings of tasks still in flight, plus this task's ceiling stays within every limit at every level (`over_budget_<level>_<period>_<dimension>`). A task's ceiling is its own packet budget, which the H1 meter enforces; money is the lower of its money budget and its tokens at the brain's declared price. |
| Metering | Usage is what ALFRED measured: tokens and money from the H1 meter snapshot, wall time from the backend, reported before the job settles (`hub_meter`). A brain that started but never reported is charged its ceiling (`unknown_charged_at_ceiling`); a task whose brain never started is charged nothing but its place in the task count (`brain_not_started`). The supervisor cycle ingests each finished task through `BrainHub.ingest` and records usage on `hub_tasks`. |
| Warning and hard stop | Measured usage at or above the warning percentage records an attention item once per limit and period. Measured usage at a limit, or committed usage above it after the owner lowers a limit, records a `hard_stop` attention item, pauses the goal, the brain or the whole hub with reason `budget_<period>_<dimension>`, and cancels its queued and running tasks through the job coordinator (queued ones become `cancelled_before_lease`, running ones `cancel_requested` and then cancelled by the worker heartbeat). Nothing resumes on its own; resuming is refused while that budget is still spent (`budget_still_spent`). |
| Heartbeats | A mandate may carry a schedule in the routines style (`every_hours` or `daily_at`, fixed UTC offset; `routines.next_slot`) and an owner-authored task. The existing supervisor cycle calls `GoalHub.cycle`, which submits that task for the latest due slot under the mandate. Slots missed while the host was stopped are counted on the heartbeat and the mandate, never replayed; recovery's missed-slot count includes them. A paused goal or workspace records the beat as `skipped`; a beat that does not fit the budget or mandate is `refused`. The last 400 beats are kept. |
| Brains cannot schedule themselves | No bundle field reaches a schedule (an extra `schedule` field refuses the whole result, as in H1), and a proposed `hub.schedule` capability is recorded as refused (`capability_not_allowed_for_brains`). Only the owner's mandate holds a schedule, and only the supervisor cycle submits. |
| Operator controls | Goal: pause, resume, stop, reassign (to another allowed brain; tasks in flight on the old brain are cancelled). Brain: pause, resume, stop. Overall: pause, resume. Owner only, version-checked (`mandate_changed`, `control_changed`), journalled and audited. Pause and stop cancel queued and running work through the coordinator. Stop is final; it is written to the lifecycle journal first (`hub_stopped`), so restoring an older backup stops the goal or brain again. A new mandate may be made for a goal whose mandate was stopped. |
| Journal | `hub_journal` is append-only (SQLite triggers refuse update and delete). Every event is also in the audit log as `hub.<event>`. |
| HTTP | Through the existing guarded desk handler (loopback Host and Origin, session cookie, CSRF on every POST): `GET /desk/hub`; `POST /desk/hub/mandates`, `/desk/hub/mandates/<id>` (update), `.../tasks`, `.../pause`, `.../resume`, `.../stop`, `.../reassign`; `/desk/hub/brains/<id>/pause`, `/resume`, `/stop`, `/budget`; `/desk/hub/overall/pause`, `/resume`, `/budget`; `/desk/hub/attention/<id>/acknowledge`. A host given no hub answers `hub_not_configured` (409). |
| Console | A small "Goals and brains" dialog (command `goals`, or "Open goals" in console controls): each goal with its mandate, autonomy per kind of work, measured budget use, pause state, heartbeat line and recent tasks; open attention items with acknowledge; brains and the overall budget. Pause and resume for goals, brains and the hub; stop for goals and brains after a confirmation. Every control sends the version shown. It does not create or edit mandates or budgets. |

### Changes outside `alfred/hub_goals.py`

| File | Change |
|---|---|
| `alfred/brain.py` | `BrainHub(gate=None)` and `submit(..., binding=None)`: with a gate, `gate.authorise` before the job and `gate.bind` inside the H1 transaction; a binding without a gate is refused. `BrainBackend(gate=None)`: `gate.dispatch` before the brain starts and `gate.metered` with the meter snapshot and wall time when the run ends. With no gate, H1 behaviour is unchanged. |
| `alfred/knowledge.py` | `KnowledgeSupervisor.cycle` calls `goals.cycle()` when a hub is attached, also while paused, so due heartbeats are recorded as skipped. |
| `alfred/desk_http.py` | `DeskHTTPServer(goals=None)` hands the hub to the supervisor and routes `/desk/hub`. |
| `alfred/lifecycle.py` | New journal kind `hub_stopped`, replayed by `hub_goals.apply_stop`, counted as `hub_targets_stopped`. |
| `alfred/recovery.py` | Missed heartbeat slots are counted with routine slots as `hub:<mandate>`. |
| `console/` | `src/integration/goals.ts`, `src/components/GoalsPanel.tsx`, `src/goals.css`, `tests/goals.test.ts`; one-line additions to the modal type, dialog titles, console controls and the command parser. |
| `tools/check_hub_goals_browser.py` | Browser check against the real loopback server with the synthetic brain behind a `GoalHub`. |

## Tests

`tests/test_hub_goals.py`, 36 tests, real SQLite, the real job coordinator and worker, real
executive goal records, the real lifecycle journal and real HTTP:

- mandates (6): linking an executive goal with its limits, journal and audit, the goal record
  unchanged; idempotent creation and one mandate per goal; owner and hosted credential only;
  refusal of autonomy 3, 4 and 5, bad work kinds, unknown or unassigned brains, tools the owner
  has not permitted, past deadlines, empty success tests, bad budgets and scope classes, a cloud
  brain for a scope the owner has not allowed, commitments, unknown and dropped goals, schedules
  beyond the mandate; version-checked updates; the append-only journal;
- gate (6): `BrainHub` refuses a task with no mandate, a mismatched one and an unknown one; tasks
  outside the mandate (autonomy, work kind, tool, brain, H1 levels 3 and 4, another owner) are
  refused before any job exists; scope class, deadline and goal status bind every task; an
  admitted task links back to its goal and mandate; a `brain_task` that bypassed the hub never
  reaches a brain; dispatch rechecks a goal achieved while the task was queued;
- budgets (8): overall budget required; usage comes from the H1 meter; admission counts tasks in
  flight at their ceiling; a warning recorded once as an attention item and acknowledged; a hard
  stop pauses the goal until the owner resumes after a new day (refused while still spent);
  per-brain and overall budgets pause their own target; lowering a limit cancels a running
  `runaway` brain through the coordinator and pauses the goal; a run that never reported is
  charged its ceiling;
- heartbeats (7): the owner-authored task is submitted when due and not before; missed slots are
  counted (5 due, 4 missed, 1 submitted) and not replayed, and recovery counts them; a paused goal
  skips; a beat that does not fit the budget is refused; a brain proposing `hub.schedule` is
  refused and changes nothing; a bundle claiming a schedule is refused whole; the supervisor cycle
  records skipped beats while the workspace is paused;
- controls (6): pause cancels queued work and resume reopens, with journal and audit; owner only;
  reassign moves the goal and cancels work on the old brain; stop is final and survives a restore
  from an older backup; brain pause, resume and stop; overall pause holds every goal;
- HTTP (3): session, CSRF, Origin and version checks on the routes; a reader sees nothing and
  changes nothing; a host without a hub says so.

Results on the tested commit (Linux, python3):

- `python3 -m unittest discover -s tests`: **1335 tests, OK**, 248 seconds (includes the 36 new
  tests and the 46 H1 tests unchanged).
- `cd console && npm ci && npm run build && npm test`: build OK (the existing chunk-size warning
  only); **17 files, 161 tests passed**, including `tests/goals.test.ts`.
- `tools/check_console_connected_browser.py` with Chromium at `/opt/pw-browsers/chromium` and
  `ALFRED_CONSOLE_OUTPUT` pointed at a scratch folder (committed evidence untouched): **108 checks
  passed, no page errors**.
- `tools/check_hub_goals_browser.py`: **19 checks passed, no page errors**. Report and
  screenshots in [browser/](browser/). The two console errors recorded are the expected 401 before
  sign-in and the 409 `budget_still_spent` refusal the check provokes.

## Limits

- **No real brain.** Token and money figures are the synthetic brain's deterministic counts.
  Nothing here says anything about reasoning quality, and the blocked live-model comparison was
  not retried.
- **Not wired into `alfred desk run`.** No real brain exists before H5, so the shipped host
  constructs no `GoalHub` and the hub routes answer `hub_not_configured`. The tests and the
  browser check construct one with the synthetic brain.
- **One hosted owner credential.** Mandates belong to the credential the host runs under, as
  routines do. A paired device of the same person sees "not hosted"; a per-person hub over
  `policy.ledger` is not built.
- **Console is a read view with pause, resume and stop.** Creating or editing mandates, budgets,
  schedules and reassigning are HTTP only for now.
- **Success tests are text.** Nothing evaluates them; independent verification is H4.
- **Budgets are conservative and local.** In-flight tasks count at their ceiling, so a task that
  would have fitted can be refused. Days use a fixed UTC offset per budget (no daylight saving
  rules). Hard stops are found when tasks are accounted in the supervisor cycle and when a limit
  changes; admitted work cannot pass a limit, but a lowered limit can already be exceeded.
- **Cancellation is cooperative.** A cancelled brain in the H1 thread backend stops at its next
  meter step; a thread cannot be killed (H5 needs a killable process or container).
- **Heartbeats.** One task per due slot; there is no overlap guard beyond budgets, so a slow task
  and the next beat can run together if the budget allows. Heartbeats run only while the host is
  running, in the existing supervisor; there is no installed service.
- **Retention.** `hub_journal`, `hub_tasks` and `hub_attention` grow without trimming; heartbeats
  are trimmed to 400. The journal's triggers stop accidental rewriting, not someone with write
  access to the database file.
- **Starting autonomy per kind of work** is an owner decision (AGENT_HUB.md); the code presets
  none and every mandate states its own.
