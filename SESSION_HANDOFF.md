# ALFRED continuation: reviewed memory v0.8

26 September 2026. Read AGENTS.md, docs/REVIEWED_MEMORY.md, docs/EVIDENCE_REVIEW.md and
current docs/ROADMAP.md. Branch `feat/alfred-reviewed-memory-2026-09-26` extends verified
v0.7 `e0a0ef973d20d3f60606423ab2035d9f9df9e68f`. Refresh its actual remote head.
No force push, automatic merge or deployment. Main remains separate.

The user's goal is personal/operational intelligence, not an admin dashboard. They said
the shell is still not quite right but asked to keep moving. Preserve it as provisional;
do not repeatedly restart its design or falsely record final approval.

## New source

alfred/reviewed_memory.py: additive private entity/claim store with source binding,
review/version transitions, temporal conflicts, projection invalidation and graph/export.
web/reviewed-memory.js/css: Memory > Reviewed memory plus exact review and source inspector.
The original note graph remains separate. Entity names do not merge identities.

alfred/evidence_review.py: narrow rejection heuristics after reference validation in
both grounded.py and conversation.py. Withheld interpretations have model_needs_review
status. No entailment, factual truth or model quality guarantee. The checker is not an
agent permission system and does not prevent egress already made to a configured model.

Pulse report-retention endpoints/UI preserve recent detail, active records, rate counters
and compact idempotency receipts. They do not erase WAL/backups, undo drafts, or change
schedules. Read the explicit capacities and host-lifecycle limits.

## Blocked operation and evidence discipline

One proposed new live-model comparison GitHub workflow was blocked by tool safety before
any files from it were committed or any experiment ran. It was not rerouted. No new
stronger-model benchmark is delivered. The first-party application, test doubles and
UI acceptance are separate work. Prior v0.7 actual inference remains documented with
its material failures; no production brain selected.

## Validation and delivery

Run `python3 -m unittest discover -s tests -v`, then ordinary first-party browser checks.
The chat-container browser blocks localhost; in-file preview checks do not validate the
backend. GitHub acceptance must independently test actual HTTP/SQLite/files/UI. Consult
`docs/evidence/memory-v08/` and the PR for the exact completed result and source receipt,
not an assumed green status. Test fixtures contain no private user/client data.

The delivery workflow can add an evidence commit containing tested source and screenshots.
Normal source must be in GitHub, not left only in a transport bundle. Read the actual
branch/commit/receipt, never a remembered ref. All 2,073 upstream files stay unchanged
and inert. No upstream workflows, scripts, skills or AGENTS instructions may execute.

## Limits and next

Memory remains credential-private (not mature user identity), manually proposed/reviewed
and bounded. It is not yet automatic model context. Source invalidation reconciles when
memory is accessed, after scanner updates; no instantaneous global purge. Withdrawal
retains history. SQLite is not application-encrypted. Use synthetic data only.

No microphone, actual accounts/devices, ENDSTATE or Noir. Only approved local drafts,
explicit memory records and fixed reports are writable. No remote service installed.
The next gates are independently evaluated reasoning, controlled reviewed-memory retrieval,
identity/grants/retention hardening, then an authorised account workflow and measured voice.
