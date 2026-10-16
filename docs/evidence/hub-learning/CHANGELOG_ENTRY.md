### Added: daily learning (AGENT_HUB.md step H3), 16 October 2026

Proposed entry for the lead to merge into CHANGELOG.md. Branch `feat/hub-learning-2026-10-16`.

- `alfred/learning.py`: a deterministic daily learning loop, no model. A new allowlisted routine
  kind `daily-learning` (owner authored schedule, run budget, proposal budget and pause, fixed
  delivery like the morning brief) gathers value-free evidence from the last 30 days (approvals,
  refusals, dismissals, corrections, lapsed, archived and re-proposed drafts, brain results,
  budget stops) and proposes preferences, procedure drafts and routing notes, each bound to its
  evidence and a threshold of at least 3. Routing notes count ALFRED's own ingestion outcome,
  never a brain's confidence.
- Every proposal goes to a learning review inbox. Accepting (owner only, version checked) makes
  an owner-owned, versioned record; dismissed learnings return only with new evidence. Current
  preference and procedure records can travel in a brain packet's `learned` field within H1's
  limits (`BrainHub._learned` now accepts learning record IDs). Learned procedure drafts appear
  in the procedure registry, never run.
- A daily digest per day with exact batch approval of listed IDs and versions (refused whole if
  any item changed) and per-item dismiss.
- An owner-authored trusted-kinds rule, off by default, that may accept only writing style and
  presentation preferences (`writing_length`, `writing_structure`). Each such acceptance is
  labelled "Accepted by your rule" with the rule ID and version and can be undone. Code refuses
  rule acceptance of anything fact-like, procedural, routing or harvested.
- Harvest: text artefacts of an accepted brain result, and skills or memories a worker staged for
  approval, become proposals only, checked by SHA-256.
- Upstream watch: pinned commits in the source library catalogue compared with an owner-supplied
  file of latest known versions, one update brief per project. No network, nothing installed.
- Learning never changes policy, grants, scopes, autonomy levels, budgets, routines or capture
  policies; a test compares every other table before and after a run.
- Routes under `/desk/learning` and a Learning tab in the console's Routines dialog.
- `tests/test_learning.py` (39 tests), `console/tests/learning.test.ts` (9 tests) and
  `tools/check_learning_browser.py` (28 browser checks).
- Not built: goals and verification as evidence (H2, H4), an HTTP route for harvest, upstream
  fetching, source forgetting for harvested text.
