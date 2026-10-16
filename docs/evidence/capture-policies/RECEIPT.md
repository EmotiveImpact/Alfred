# Capture policies receipt (plan item 2.4: MEM-004, M04, M10)

16 October 2026. Branch `feat/capture-policies-2026-10-16`, started from `main` at
`75947b8dd`. Tested revision: `476c5cfd132b36552681573cc3aa09f40e1dca2b` (code, tests and
browser evidence). This receipt is added in the following commit and changes no code.

## What was built

- `alfred/capture_policies.py`: owner-authored capture policies stored as data. Each policy
  has an identifier, a version (0 creates; every change must name the current version, else
  `409 capture_policy_changed`), on or off, a name, a context label (personal, company or
  client), one or more vault sources from the caller's own workspace, an optional folder
  prefix, a per-policy daily budget and what a match proposes (an existing entity chosen by
  the owner, a text predicate, a memory type and an optional retention). Authoring and the
  overall budget are journalled in the audit log (`capture.policy_created`,
  `capture.policy_updated`, `capture.settings_updated`).
- Two deterministic rule kinds, no model and no free regular expressions:
  `line_prefix` (for example a line starting `Decision:`, after an optional bullet) and
  `dated_line` (an open line holding a valid `YYYY-MM-DD`, optionally `HH:MM`, and an
  optional whole-word keyword; the value is normalised to "date rest of line" so the
  commitment review routine can read the date once the person accepts it). Frontmatter,
  fenced code and ticked tasks never match. Each policy carries a plain-language
  description of exactly what it does.
- Every match goes through the existing `ReviewedMemory.propose` path with a capture
  record, so it enters the existing memory review queue as a `proposed` statement bound to
  the exact note, hash, revision and single line. Nothing is accepted automatically; the
  run result reports `auto_accepted: 0`.
- Dedupe: a line already offered by a policy is not offered again on rescan (keyed by
  policy, note and line text hash, so moving a line does not re-offer it). A proposal the
  person dismissed (withdrawn or disputed at any point) is never re-offered while the line
  text is unchanged; changing the text offers it again. A forgotten proposal is never
  re-offered. A proposal whose support was invalidated by an edit before anyone dismissed
  it may be offered again against the new revision, for fresh review.
- Budgets: a per-policy daily budget (1 to 50) and an overall daily budget per owner
  (default 20, at most 200, version-checked). Matches over either budget are counted per
  UTC day, never proposed; the next day's budget may propose them.
- Scope: the workspace comes from the authenticated credential. Policies, counts and
  proposals are private to the owner who wrote them. A policy can only name vaults in its
  own workspace, reads only sources the owner may read now (strict grants respected), and
  the reader role cannot read, author or run policies.
- Runs: `POST /desk/capture/run` and a hook in the host's supervisor cycle, which runs only
  when notes, enabled policies, settings or the day changed, and never while paused.
- HTTP (inside the existing loopback Host/Origin, session and CSRF boundary):
  `GET /desk/capture`, `POST /desk/capture/policies/{id}`, `POST /desk/capture/settings`,
  `POST /desk/capture/run`. Shared modules changed additively only: `alfred/desk_http.py`
  (construct and route) and `alfred/knowledge.py` (supervisor hook).
- Console: a read-only Capture tab in the Routines dialog listing each policy with its
  rule, context, version, description, counts of proposed, accepted, dismissed and awaiting
  review, and today's budget use and overflow. Decisions stay in memory review. A reader is
  told policies are owner-only.

## Tests run on the tested revision

| Check | Result |
|---|---|
| `python3 -m unittest tests.test_capture_policies` | 24 passed: matching, authoring, versioning, validation, owner only, bound proposals, nothing accepted, rescan dedupe, dismissal and re-offer on text change, forgotten not re-offered, per-policy and overall budgets, disabled policy, forgotten subject, revoked read grant, supervisor cycle on change and pause, workspace separation, HTTP with CSRF and versions, reader refused, supervisor wiring |
| `python3 -m unittest discover -s tests` | 1,137 passed |
| `cd console && npm ci && npm run build && npm test` | build (tsc and vite) passed; 147 unit tests passed (4 new in `console/tests/capture.test.ts`) |
| `tools/check_capture_browser.py` (new, real Chromium) | 15 checks passed in three runs; report and screenshots in this folder. One earlier run, made while the backend suite ran in parallel, timed out after 5 seconds waiting for sign-in, so the sign-in wait was raised to 20 seconds before the passing runs |
| `tools/check_routines_browser.py` (affected dialog) | 52 checks passed (output kept outside the repository) |
| `tools/check_console_connected_browser.py` | 99 checks passed (output kept outside the repository) |

All inputs are synthetic (the demo vault plus one synthetic meeting note).

## Limits

- A policy proposes statements about one entity the owner chose; it never creates or
  merges entities, and it does not guess a subject from the line.
- Only text-valued predicates (`status`, `scheduled_for`, `decision`) can be proposed.
- The personal, company or client context is a recorded label; separation between
  workspaces is enforced by the credential scope and the listed vaults, not by the label.
- The day boundary for budgets is UTC, not the routine offset or an IANA zone.
- Capture proposal rows keep identifiers, line numbers and a hash of the line text after a
  statement is forgotten (like the claim's quote hash); they hold no value. The lifecycle
  forget receipt does not yet count them (plan item 1.3).
- Policies are authored over HTTP only; the console lists them but has no authoring form.
- No register status change is claimed beyond MEM-004's note; see CHANGELOG_ENTRY.md.
