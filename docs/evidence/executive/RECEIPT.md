# Executive records receipt (Stage D, ATT-002)

2 October 2026, branch `claude/alfred-development-qpgxhg`. Status: **partial**, implemented
on the integration branch against synthetic data. Not merged, not deployed.

## What exists

`alfred/executive.py` holds goals, priorities, commitments, decisions, milestones and
follow-ups as records the person writes. They are actor-private like reviewed memory,
version-checked on every change, optionally linked to a visible project (an authored note
or a reviewed entity) and optionally cite exact note lines. A cited line that changes is
flagged as changed and the record is kept; nothing is silently trusted or deleted.

The console projection and the executive panel read the same records: each record is a
graph node in the Actions category with an `executive_link` edge to its project and an
`executive_support` edge to its cited note while that citation is current.

- **Progress** counts only recorded milestones for a project (`done/total`), never an
  estimate. Projects without milestones say so.
- **Recommendations** follow one stated rule: an open commitment or follow-up due within
  seven days, or overdue. They are labelled recommendations and never become priorities
  until the person accepts one; an accepted priority records which record it came from.
- **Authority**: records grant nothing. Approvals and effects stay on the action ledger.

## Evidence

- `tests/test_executive.py`: 11 tests (states per kind, idempotency, version conflicts,
  changed citations flagged, project visibility, milestone-only progress, the
  recommendation rule and acceptance, rank ordering, actor privacy, invalid values, and an
  HTTP test that the projection and panel data agree).
- `tools/check_console_connected_browser.py`: 60 checks in a real browser, including
  recording a milestone and a due-soon commitment, the recommendation, accepting it,
  completing the priority and the milestone, and progress moving from 0/1 to 1/1.
  [Screenshot](connected-executive.png).

## Not yet

A responsible-person field on records, meeting and decision preparation briefs, decision
options with their trade-offs, cross-project insights (which must then require permitted
support from every contributing workspace), reminders through Pulse (M10) and links from a
follow-up to a drafted action.
