### Changed: hub steps H2, H3 and H4 wired together, 16 October 2026

Proposed entry for the lead to merge into CHANGELOG.md. Branch `feat/hub-integrate-2026-10-16`,
started from `f51ba2c0b`. Receipt: [docs/evidence/hub-integrate/RECEIPT.md](RECEIPT.md).

- Routing notes (H3) now count H4's verification outcome per brain, kind of work and scope class:
  verified (declared checks passed, or the owner acknowledged the exact run), failed checks,
  could not be verified, no declared checks, and not returned, alongside budget stops. A result
  with no declared checks is its own class and never counts as verified; a brain's own
  confidence or "done" is never read. Threshold of 3 unchanged. New categories
  `often_fails_checks`, `mostly_verified` and `mostly_not_verified`; `mostly_accepted` is gone.
  Each routing note's detail carries the class counts, `verified` as a number (it was `null`)
  and `no_checks_counted_as_verified: false`.
- `alfred/verification.py`: `outcome_rows` and an evidence class per result
  (`verified`, `failed_checks`, `unverifiable`, `no_checks`, `not_returned`); `outcomes` adds
  `evidence_by_brain`. Verification follows the person (`policy.ledger`), so the owner's paired
  device can run checks and acknowledge; rows stay with the task's actor so the effect gate is
  unchanged. `verify(..., expected_runs=)` refuses a stale view (`verification_changed`).
- Goal work as learning evidence: the hub journal now records, value-free, budget warnings and
  hard stops with the brain whose task triggered them, owner pauses, stops and reassignments,
  tasks refused by the mandate gate (`task.refused`, at admission or dispatch, with the reason
  code) and missed heartbeat slots (`heartbeat.missed`). The daily learning run reads them as
  identifiers, codes, times and counts and proposes one `routing-goals:<brain>` note per brain
  with at least 3 setbacks. Routing notes only; the learning authority test now also snapshots
  every hub and verification table and the executive records, before and after a run and after
  accepting every proposal.
- Mandates declare acceptance checks (owner only, version-checked, journalled, validated with
  `verification.validate_acceptance`). `GoalHub` puts them first in every task packet it
  authorises (declared by the mandate, with the mandate as reference), merged with the task's own
  checks; the gate refuses a packet under that mandate without them. `effect_readback` cannot be
  a mandate check. The success test stays unevaluated text. Older databases gain the column.
- HTTP, through the existing guarded desk handler: `GET /desk/hub/results`,
  `GET /desk/hub/results/<job>`, `POST /desk/hub/results/<job>/verify` (with the run count seen)
  and `POST /desk/hub/results/<job>/acknowledge` (the exact run's SHA-256 and an explicit
  `accept_failures`). Owner only and person-private; a reader is told `owner_only`. A check's
  reasons are withheld when the result's sources can no longer be read under strict grants.
- Console: a "Results and checks" section in the Goals and brains dialog with the class of each
  result, a per-brain line, the last run per check, "Run checks", and "Acknowledge" behind a
  confirmation that says so when it is over failed checks. Mandate checks are listed on the goal
  card.
- Tests: `tests/test_hub_integrate.py` (17), the routing and authority tests in
  `tests/test_learning.py` updated, 4 new in `console/tests/goals.test.ts`, and
  `tools/check_hub_integrate_browser.py` (21 browser checks), also added to CI.
- Not built: a production host that constructs the goal hub (only tests and browser tools do),
  automatic verification at ingest, a real brain.

## Suggested register changes (for the integrating session)

- `INT-001`: extend the note with "Agent hub H2 to H4 wired together (16 October): mandate
  acceptance checks in every authorised packet, routing notes from verified outcomes and goal
  setbacks, verification over HTTP and in the console; synthetic brain only" and add
  `docs/evidence/hub-integrate/RECEIPT.md`, `tests/test_hub_integrate.py` and
  `tools/check_hub_integrate_browser.py` to `acceptance_evidence`. Keep `partial`: no real brain
  and no host wiring.
- docs/AGENT_HUB.md: once merged, note that H3 reads H4 outcomes and H2 journal events, that
  H2 mandates carry H4 checks, and that H4 has HTTP routes and a console view. Remove "use by a
  routing or learning job" and "HTTP routes and console view" from H4's not-built list, and
  "goals and verification as evidence" from H3's.
- docs/REMAINING_BUILD_PLAN.md: the remaining hub work is host wiring of `GoalHub`, automatic
  verification after ingest and a real brain (H5, H6).
