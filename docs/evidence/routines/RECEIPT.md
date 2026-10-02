# Authored routines receipt (M10: ATT-001, MEM-004, MEM-015)

2 October 2026. Branch `wave2/routines`, started from `claude/alfred-development-qpgxhg` at
`f358b09a8`. **Tested commit: `ac42a75ad7fce5db0cc599cb3dd91a49bb5063e1`.** The commit that
adds this receipt and its screenshots changes no code. Status: implemented on a branch against
synthetic data only. Not merged, not deployed, not reviewed by the owner. The requirement and
backlog registers were not edited; status changes are proposed to the lead separately.

Design, rules, routes and limits: [docs/ROUTINES.md](../../ROUTINES.md).

## What exists

- `alfred/routines.py` (routine schema version 1) and `alfred/routines_http.py`. Two
  allowlisted kinds, `commitment-review` and `morning-brief`, configured as authored settings:
  schedule (every 1, 2, 4, 8, 12 or 24 hours, or daily at a time) in a fixed local offset, run
  budget per day, nomination budget per run, quiet hours, interrupt choice (show now or hold
  for the next brief), draft offers and a per-routine pause. Every change is version checked.
  Only the owner credential the host was started with can author routines.
- Runs happen only in the existing foreground supervisor cycle. Each due slot leaves one run
  record: completed (read counts, cited IDs and versions, nominated, held, not nominated and
  why, budget used, missed slots), skipped with its reason (`paused`, `workspace_paused`,
  `budget_exhausted`, `authority_lost`) or failed (nothing kept). The owner credential, the
  workspace pause and current source grants are rechecked inside the run's transaction.
  Stored outcomes hold citations and counts only; views resolve them as the caller may read
  them now, and a statement that is no longer readable or usable shows no value.
- Nominations: in-app reminders with a stated reason citing the exact commitment version, and
  optional draft offers for overdue records with a responsible label. The person accepts or
  dismisses each one and both are recorded. Accepting a reminder can create a follow-up through
  the existing `ExecutiveRecords.create`. Accepting a draft offer only proposes it in the
  existing ledger; the exact text still needs its own fingerprint approval, and approval and
  dispatch recheck the cited record version (`KnowledgeStore.evidence_valid` now also accepts
  a routine binding). Nothing is delivered outside the app.
- A read-only procedure registry of statements captured as `procedural` memory, with source
  lines and review and support state, plus authored procedure notes labelled not reviewed.
- Console: `console/src/components/RoutinesPanel.tsx`, `console/src/integration/routines.ts`
  and `console/src/routines.css`. The Routines dialog (command `routines`, or Open routines
  in Console controls) has Routines, Nominations, Runs and Procedures tabs. The executive
  panel adds a Routines section only when something is shown now or a brief exists. The
  offline demonstration says routines need the connected product and runs nothing.

Small additive edits to shared files: `alfred/desk_http.py` (construct routines beside Pulse;
one route branch), `alfred/knowledge.py` (call `routines.cycle()` in the supervisor cycle;
accept a routine draft binding in `evidence_valid`), `console/src/state/ConsoleProvider.tsx`
(one modal name), `console/src/domain/commands.ts` (two aliases),
`console/src/components/ConsoleDialogs.tsx` (title, panel, wide dialog, one button),
`console/src/components/ExecutivePanel.tsx` (one section) and a new section in
`console/docs/CONNECTED_CONSOLE.md`. Pulse and its two reports are unchanged.

## Commands and results on the tested commit

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests` (Python 3.11.15) | 1068 tests pass, including 32 new in `tests/test_routines.py` and 4 new in `tests/test_routines_procedures.py` (1032 before this branch). |
| `python3 tools/check_requirement_register.py` and `python3 tools/check_memory_plan.py` | Pass. Neither register file was edited. |
| `cd console && npm run build && npm test` (Node 22.22.0) | Typecheck and build pass (the existing chunk size warning only); 116 unit tests pass, including 14 new in `console/tests/routines.test.ts`. |
| `CHROMIUM_PATH=/opt/pw-browsers/chromium python tools/check_routines_browser.py` (Playwright for Python 1.57.0, Chromium 141.0.7390.37, SwiftShader) | 52 checks pass, no page errors. [Report](browser-report.json). The only browser console error is the expected 401 from the session probe before sign-in. |
| `tools/check_console_connected_browser.py` with `ALFRED_CONSOLE_OUTPUT` outside the repository | 85 checks pass, no page errors. |
| `tools/check_executive_browser.py` with `ALFRED_EXECUTIVE_OUTPUT` outside the repository | 45 checks pass, no page errors. |
| `node tools/standalone.mjs`, then `CI=1 ALFRED_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test` in `console/` | 29 offline demonstration scenarios pass. |

## What the tests show

- **Commitments and attention (ATT-001, MEM-004).** Due and overdue open commitments and
  follow-ups and dated, accepted commitment statements are nominated with reasons and cited
  versions; undated, unaccepted, conflicting, snoozed, done and non-commitment items are not;
  a version is nominated once; budgets per run and per local day; schedule slots run once with
  missed slots counted, not replayed; per-routine pause, workspace pause and revocation are
  recorded as skipped runs; a strict grant without read access hides a statement from runs and
  views; quiet hours hold and later surface; holding for the brief and the brief releasing up
  to its budget; the brief cites attention items, insights and the person's own pending
  approvals by ID and version and stores no titles; a failed run keeps nothing.
- **Decisions.** Accept, accept with one follow-up (idempotent), dismiss, refusal of a changed
  retry, refusal when the cited commitment changed, another person's nomination looking
  unknown, a reader refused; a draft offer enters the ledger only when accepted, stays proposed
  through supervisor cycles, is refused with a wrong fingerprint, verifies as a local draft
  only after exact approval, and cannot be approved once its commitment is closed.
- **Procedures (MEM-015).** The registry lists procedural statements with source, review state
  and support state, withholds values the caller cannot read and flags changed support. A
  procedure note and accepted procedural statements saying to run a command, widen grants,
  approve an action, change routine settings and submit a long job are run through routines,
  retrieval, a sources answer, the conversation queue, a word count job, Pulse and supervisor
  dispatch: grants, policy, credentials, devices, approvals, routine settings, statements,
  records and vault files are unchanged, and the only new job is the one the test submitted.
  Memory types stay distinct: only `commitment` statements feed the commitment review and only
  `procedural` statements appear in the registry.
- **HTTP.** Session, CSRF, Origin and Host checks apply to every routine route; unknown kinds
  and a POST to the registry return 404.

## Browser evidence

All screenshots are synthetic: the demo vault, one added fictional procedure note and
fictional records. `routines-settings.png` (authoring the commitment review),
`routines-runs.png` (a run's read counts, budget and citations), `routines-nominations.png`
(reminders and a draft offer with reasons), `routines-panel.png` (the executive panel section),
`routines-draft-review.png` (the existing exact-text approval for an accepted draft offer),
`routines-held.png` (a nomination held for quiet hours), `routines-brief.png` (a morning brief
and the released nomination), `routines-skips.png` (budget, workspace pause and routine pause
recorded as skipped), `routines-procedures.png` (the registry), `routines-1280.png` and
`routines-390.png` (layout), and `routines-demo.png` (the offline demonstration notice).

## Not done, and limits

- Local time is a fixed offset the person chooses; daylight saving changes are not followed.
- One routine per kind per workspace, under the hosted owner credential, reading only that
  credential's actor-private records. Other people and paired devices cannot author routines.
- Routines run only while the foreground host runs. Missed slots are counted, not replayed.
- No learned relevance or ranking, and no model; the rules are fixed and stated.
- No notification, push, e-mail, calendar or device delivery of any kind.
- An accepted draft offer's proposal expires after 15 minutes like other proposals; the
  nomination then stays accepted and is not offered again for that version.
- The executive panel shows at most three nominations. Run and decision history is bounded
  automatically and has no pruning control in the console.
- Reviewed procedures are listed, not versioned as a separate registry with its own review
  workflow; workflow learning is not attempted.
- The browser check advances the server clock by three minutes to end quiet hours; it does not
  prove behaviour across days or real scheduled firing in the browser (scheduled firing is
  covered by the backend tests with an injected clock).
- Software-rendered browser checks are not physical device or GPU certification.
