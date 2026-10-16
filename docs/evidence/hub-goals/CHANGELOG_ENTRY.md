### Added: goals, mandates, budgets and heartbeats for the agent hub (AGENT_HUB.md step H2), 16 October 2026

Proposed entry for the lead to merge into CHANGELOG.md. Branch `feat/hub-goals-2026-10-16`.

- `alfred/hub_goals.py`: a `GoalHub` that links the owner's existing executive goal records to
  mandates (scope class, deadline, success test text, autonomy 0 to 2 per kind of work with 3 and
  4 refused as in H1, allowed and assigned brains, tool allowlist, budget, optional heartbeat
  schedule). Owner only under the host credential, version-checked, journalled in an append-only
  hub journal and the audit log.
- `BrainHub` gains an optional gate: with a `GoalHub` attached, every brain task must serve a
  current mandate and stay inside it, or it is refused before a job exists. The gated
  `BrainBackend` rechecks at dispatch and reports the H1 meter's count when a run ends.
- Budgets per goal, per brain and overall (daily and total tokens, money, wall time and task
  count). Admission reserves each task's ceiling; a warning becomes an attention item; a hard stop
  pauses the goal, brain or hub and cancels its queued and running tasks through the job
  coordinator. Nothing resumes on its own, and resuming is refused while the budget is still
  spent. An overall budget is required before any task runs.
- Heartbeats in the routines scheduling style run from the existing supervisor cycle; missed slots
  are counted, never replayed, and appear in recovery's missed-slot count. A brain cannot schedule
  itself.
- Operator controls: pause, resume, stop and reassign for a goal; pause, resume and stop for a
  brain; pause and resume for the hub. Stop is final and written to the lifecycle journal
  (`hub_stopped`) so a restore cannot undo it.
- HTTP routes under `/desk/hub` through the existing guarded handler; a host without a hub answers
  `hub_not_configured`. `alfred desk run` does not construct a hub yet (no real brain before H5).
- Console: a small "Goals and brains" dialog (command `goals`) showing mandate, budget use and
  pause state, with pause, resume and a confirmed stop.
- `tests/test_hub_goals.py` (36 tests), `console/tests/goals.test.ts`, and
  `tools/check_hub_goals_browser.py` (19 browser checks). [Receipt](docs/evidence/hub-goals/RECEIPT.md).
- Not built: mandate and budget editing in the console, a per-person hub across paired devices,
  evaluation of success tests (H4), a real brain (H5).

## Suggested register changes (for the integrating session)

- `INT-001`: extend the note with "Agent hub H2 (16 October): mandates over executive goals,
  budgets with automatic pause, heartbeats and operator controls, synthetic brain only" and add
  `docs/evidence/hub-goals/RECEIPT.md` and `tests/test_hub_goals.py` to `acceptance_evidence`.
  Keep `partial`: no real brain and no host wiring.
- `ATT-001`: optionally note that goal heartbeats share the routines scheduling and missed-slot
  rules. Keep `partial`.
- docs/AGENT_HUB.md: mark H2 built on a branch once merged; the owner decision on starting
  autonomy per kind of work still stands (every mandate states its own).
