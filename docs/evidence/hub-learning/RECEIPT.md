# Daily learning receipt (AGENT_HUB.md step H3)

16 October 2026. Branch `feat/hub-learning-2026-10-16`, started from `def198223`.
**Tested commit: `c3eda6701b0a7fc1fa2ca1491218fda7620e00ac` (the commit that adds this receipt and its screenshots
changes no code).** Status: implemented on a local branch against synthetic data only. Not
pushed, not merged, not deployed, not reviewed by the owner. The shared registers
(CHANGELOG.md, BUGS_AND_FIXES.md, SESSION_HANDOFF.md, README.md, docs/AGENT_HUB.md, the
requirement register and the remaining build plan) were not edited; a proposed changelog entry
is in [CHANGELOG_ENTRY.md](CHANGELOG_ENTRY.md).

No model runs anywhere in this work. Every learning comes from stated rules over ALFRED's own
records. Nothing under `third_party/` was imported, installed or executed: the source library
catalogue is read as JSON data and each manifest is only hashed. No network is used.

## What exists

`alfred/learning.py` holds the whole learning loop. Changes elsewhere are small and additive.

| Part | What it does |
|---|---|
| Routine kind `daily-learning` | A third allowlisted kind in `alfred/routines.py`, default daily at 21:00, off until the owner saves settings. Schedule, local offset, run budget per day, pause, workspace pause and authority checks are the existing routine machinery; "nominations per run" is the proposal budget per run. Like the morning brief it has fixed delivery (no holding for the brief, no draft offers; `FIXED_DELIVERY`). Each run is recorded once, inside one transaction. |
| Evidence (step 1) | `gather` reads the person's own records from the last 30 days: approvals and refusals, archived, lapsed and re-proposed drafts, dismissed and accepted routine nominations, dismissed brain suggestions, capture policy proposals decided, corrections to accepted statements (superseded, or disputed after acceptance), brain results (`brain_results`: accepted, refused, stopped) and budget stops (brain over budget, routine `budget_exhausted`, capture deferrals). Only identifiers, states, times and counts are kept. The one value read is a re-proposed draft's old and new text, compared for length and sentence count; only the direction is kept. |
| Proposals (step 2) | Three kinds, each bound to its evidence identifiers and a threshold of at least 3. Preferences: draft length and sentence structure (at least 3 edits, two thirds one way), capture policy dismissals (at least half), routine rule dismissals (two thirds), drafts lapsing (at least half of decided), corrections per predicate. Procedure drafts: the same recorded path of at least three steps ending in approval, seen at least 3 times (for example proposed from a reported change, lapsed, edited and proposed again, approved). Routing notes: per brain, job kind and scope class, counted from ALFRED's ingestion outcome, labelled not independently verified and never from the brain's confidence. `_candidate` refuses to build anything below its threshold. |
| Review inbox (step 3) | `learning_proposals` (state `suggested`, `accepted` or `dismissed`, versioned). One open proposal per learning. Accepting is owner only and version checked, and makes an owner-owned, versioned `learning_records` row; a changed conclusion is offered as a new version that supersedes the old one. A dismissed or retired learning is offered again only when at least 3 new pieces of evidence arrive after the decision; harvested text that was dismissed is never offered again. Capacity: 64 open proposals, 256 records, 400 decided proposals kept. |
| Packets | `select_learned` picks current preference and procedure records within H1's limits (4 items, 1600 characters, 600 per statement, one line, no credential-shaped text). `BrainHub._learned` now accepts a learning record ID in `claim_id` beside reviewed claim IDs and refuses a record that is retired, superseded, undone, someone else's or a routing note (`learned_not_usable`). Routing notes never travel in packets. |
| Procedure registry | `GET /desk/routines/procedures` adds `learned_procedures`: accepted versions and drafts awaiting review, labelled never run and granting nothing. |
| Daily digest | `digest(day)`: one list per day (the routine's local offset) of the learnings proposed that day, with each item's decision, counts and the exact approvable set. `approve_batch` accepts exactly the listed `id` and `version` pairs in one transaction; it refuses the whole set if any item changed, was decided, is from another day or is listed twice, and is idempotent on repeat. Audited as `learning.batch_accepted`. Per-item accept and dismiss remain. |
| Trusted-kinds rule | Owner authored, off by default, version checked (`trust_rule_changed`), audited (`learning.trust_rule_created`, `learning.trust_rule_updated`). It may name only categories from a closed list of writing style and presentation preferences: `writing_length` and `writing_structure`. Anything else is refused (`category_not_trustable`). Independently of what a rule names, code accepts by rule only a `preference` of a trustable category that came from ALFRED's own records (`trustable`); a fact-like, procedure, routing or harvested item is never accepted that way, and `_accept` refuses it (`learning_not_trustable`). Each rule acceptance records the rule ID and version, shows in the digest as "Accepted by your rule", and can be undone (`undo`: the record becomes `undone`, any record it replaced is current again, the proposal returns to review). |
| Harvest (step 4) | `harvest`: text artefacts (Markdown or plain text) of the person's own accepted brain result become `worker_note` proposals, each matched by name and SHA-256 to the artefacts the result recorded. `harvest_staged`: items a worker staged for approval (Hermes' `write_approval` mode, as text with hashes) become `worker_skill` procedure proposals or `worker_memory` preference proposals in the same inbox. Hash mismatch, a refused or someone else's result, credential-shaped content and text over 2000 characters are refused. Nothing harvested runs or is trusted. |
| Upstream watch (step 5) | Compares each catalogue entry's pinned commit and licence with an owner-supplied file (`upstream-latest.json` beside the database, schema version 1: commit, release, licence, changed defaults, licence notes, security notes per project). Writes one update brief per project (`newer_reported`, `release_reported_without_commit`, `pinned_matches_latest_known` or `not_in_owner_file`), stored again only when its content changes. A brief states pinned and available versions, whether the reported licence differs, the changed defaults, licence and security notes the owner recorded, which of those are missing for a newer version (`fields_to_review`), and whether the manifest still matches the catalogue. The owner file is read only if it is a regular file (no symbolic links), within size limits, valid JSON without duplicate keys. Fetching is a declared future capability (`upstream.fetch`, not built). Nothing is installed; adoption stays a separate owner-approved step. |
| No authority | Learning writes only its own tables, its audit rows and its run record. A test snapshots every other table (grants, policy, credentials, devices, routines, capture policies, brain tables and the rest) before and after a run with the trust rule on, and after accepting every proposal: unchanged. |
| HTTP | `GET /desk/learning`, `GET /desk/learning/digest`, `GET /desk/learning/digest/YYYY-MM-DD`, `POST /desk/learning/run` (through the routine, so pause, budgets and authority apply), `POST /desk/learning/digest/approve`, `POST /desk/learning/trust`, `POST /desk/learning/proposals/<id>/accept` or `/dismiss`, `POST /desk/learning/records/<lrn-id>/retire` or `/undo`. Behind the existing loopback Host and Origin, session cookie and CSRF guard. Readers can read their own (empty) view; every decision is owner only. |
| Console | `console/src/integration/learning.ts` and a Learning tab in the Routines dialog: today's list with "Accept these N", per-item accept, dismiss and undo, earlier items awaiting review, the trusted-kinds rule with its two allowed categories, accepted learnings with retire. The daily learning card shows "Proposals per run" and no interrupt, draft or quiet hours options. The Runs tab summarises a learning run. The Procedures tab lists learned procedure drafts. |

Small additive edits to shared files: `alfred/routines.py` (the kind, `FIXED_DELIVERY`, one work
function, `learned_procedures` in the registry view), `alfred/routines_http.py` (the kind in the
route pattern), `alfred/desk_http.py` (expose the learning service; one route branch),
`alfred/brain.py` (`BrainHub._learned` resolves learning record IDs), `tests/test_routines.py`
and `tests/test_routines_procedures.py` (expect the third kind; tolerate its unset `next_due`),
`console/src/integration/routines.ts` and `console/src/components/RoutinesPanel.tsx`.

## Commands and results on the tested commit

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_learning.py'` (Python 3.13.16) | 39 tests pass. |
| `python3 -m unittest discover -s tests` | 1338 tests pass in 251.7 seconds, none skipped: 39 new in `tests/test_learning.py`, and two routines tests adjusted for the third kind. |
| `cd console && npm ci && npm run build && npm test` | Build succeeds, with Vite's chunk size warning (main chunk 1618 kB against the configured 1400 kB limit). 17 files, 163 tests pass, 9 of them new in `console/tests/learning.test.ts`. |
| `node tools/standalone.mjs`, then `CI=1 ALFRED_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test` in `console/` | 29 offline demonstration scenarios pass. |
| `CHROMIUM_PATH=/opt/pw-browsers/chromium python tools/check_routines_browser.py` (Playwright for Python 1.64.0, Chromium 141.0.7390.37, SwiftShader), report written to a scratch folder | 52 checks pass, no page errors, with the new routine card and tab present. The committed routines evidence was not rewritten. |
| `CHROMIUM_PATH=/opt/pw-browsers/chromium python tools/check_learning_browser.py` | 28 checks pass, no page errors. [Report](browser-report.json) and screenshots in this folder. The two browser console errors are the expected 401 from the session probe before sign-in and the 403 a reader gets from the owner-only capture policy view, which the Routines dialog already requested before this branch (the routines check on this commit shows the same pair). |

`tests/test_learning.py` covers: the routine off by default, fixed delivery, pause, workspace
pause, run budget and proposal budget; each rule and its threshold, with nothing proposed below
it; evidence stored without values; accept, idempotent repeat, owner only and person private;
dismissal not re-offered until new evidence; a changed conclusion as version 2; retire; the
procedure registry; the digest and exact batch approval, including refusal of a changed, stale,
other-day or duplicated item and of a reader; the trusted-kinds rule (off by default, closed
list, audited, accepts only style and presentation, undo, and a rule naming every category in
the database still accepting no fact-like, procedure, routing or worker item); harvest of
artefacts and staged skills and memories as proposals only, with hash, ownership, refused result,
credential and length faults; packet selection within H1's limits and refusal of retired,
foreign and routing records; the authority snapshot; upstream briefs over a synthetic catalogue
and manifests, missing, invalid, linked and duplicate-key owner files, and the real catalogue
read as data; and the HTTP routes with their guards.

## Limits and open points

- **Divergence to note.** AGENT_HUB.md step 3 says "Nothing becomes accepted automatically."
  The trusted-kinds rule is an owner direction relayed by the coordinator during this build. It
  is off by default, owner authored and narrowed in code to writing style and presentation
  preferences, every acceptance is labelled and can be undone. The lead should reconcile the
  document wording.
- Step 1 does not yet read goals advanced or missed (H2 is built in parallel) or independent
  verification results (H4). Routing notes count ALFRED's ingestion outcome; their `verified`
  field is `null` until H4's verdicts are wired in.
- Harvest is a Python interface only; there is no HTTP route and no real worker home to copy
  from or delete, because no outside worker (Hermes included) is adopted. Harvested text is held
  in learning tables and is not yet covered by source forgetting or deletion accounting.
- Upstream fetching is not built; the owner supplies the file of latest known versions. Briefs
  are comparisons of what that file reports, not verified release notes.
- Proposals and records are per person and live in the workspace database; decided proposals
  beyond the newest 400 are pruned (their audit rows remain).
- Learned preferences are carried as context in packets only. Nothing yet changes how ALFRED
  itself drafts or ranks; that would be a separate, reviewed step.
- The console browser check uses the synthetic demo vault and one synthetic event; it does not
  exercise harvest or upstream briefs in the browser.
