# Executive workflows receipt (ATT-002, ATT-001), second increment

2 October 2026. Worktree branch `worktree-agent-af1ae636aa844a2dc`, started from
`claude/alfred-development-qpgxhg` at `870751368`. **Tested commit:
`205cae4ba62e0906bfa09fa2ba45330be5d4a816`.** The commit that adds this receipt and its
screenshots changes no code. Status: implemented on a branch against synthetic data only.
Not merged, not deployed, not reviewed by the owner.

This extends the [first executive receipt](../executive/RECEIPT.md), which stays as the
record of its own checkpoint. Its "Not yet" list is addressed here except where stated below.

## What exists

`alfred/executive.py` (schema version 2, migrated in place from version 1),
`alfred/executive_http.py`, the projection additions in `alfred/console_api.py`, and the
console views in `console/src/components/ExecutiveRecords.tsx`,
`ExecutiveWorkflows.tsx` and `console/src/domain/executive.ts`.

1. **Responsible label.** Optional short text the person types (up to 80 characters),
   optionally linked to a person or organisation record (an authored person note or a
   reviewed entity) only when the person picks one. Nothing reads it from note text. It
   creates no credential, person, device or grant and is never used in an authorisation
   decision. Filtering and grouping use the exact label and the explicit link together, so a
   note and its reviewed namesake, or two spellings, are never combined. A link the person
   can no longer see reads as unavailable and its name is withheld; a new link must be
   visible when it is made.
2. **Decision options.** Two to six authored options, each with a label, notes and up to
   four pros and four cons, kept in the authored order with no score or ranking. The chosen
   option, rationale and `decided_at` are written only by an explicit decide call carrying
   the record version. Changing options after a decision needs an explicit reopen; the
   earlier choice stays in an append-only decision history. A decision with options cannot
   be marked decided or reopened through the generic status update.
3. **Preparation briefs** for decisions, milestones and commitments, assembled on request in
   one transaction from what the caller may read at that moment: the record; its linked
   notes (project note, explicitly linked responsible person note and cited lines) with
   short exact excerpts; accepted and current reviewed statements about the linked entities
   or supported by a linked note, using the reviewed-memory currentness rule
   (`ReviewedMemory._claims`); related open commitments and follow-ups in the same project;
   recorded milestone progress; and open questions (no responsible label, no due date,
   options without notes, unavailable project or cited lines, namesakes, statements not
   shown). Every item cites a record version, a note revision and lines, or a reviewed
   statement version. Statements about the linked entities that are withheld, conflicting,
   outside their valid period, invalidated, proposed or disputed are counted but their values
   never appear; unusable statements reached only through a linked note are left out. The
   brief is labelled as assembled, not advice and not model output, writes nothing, and the
   console assembles it again when the projection changes.
4. **Attention.** An in-app list computed on request by four stated rules: open records past
   their due date; proposed decisions past their due date; open commitments and follow-ups
   due within seven days; open milestones with no creation, progress note or status change
   for 14 days. An authored `snooze until` (after now, at most 366 days) moves an item to a
   visible Snoozed list and also pauses its recommendation. Milestone progress notes are the
   defined input for staleness. No push, e-mail, device or Pulse delivery.
5. **Derived insights** by three stated rules, each linking to the records it came from and
   labelled `derived_from_your_records_not_accepted_fact`, never stored: one label and link
   holding overdue records in two or more currently available projects; two of the top three
   open priorities due within two days of each other; a currently available project with
   open commitments for at least 30 days and no milestone created or progressed in 30 days.
   Only projects the caller can see contribute.

Also in this increment: the record inspector now loads executive record detail (the
console client's identifier rule had excluded `exec:` ids); an explicitly linked, visible
person draws an `executive_responsible` edge with authored basis; executive values join the
projection's `dataRevision` so time-based attention reaches the console; and cited support
the caller can no longer read now says `unavailable` rather than `changed`.

All new routes sit behind the existing desk handler's loopback Host and Origin checks,
session cookie and CSRF token. Another person's record and an unknown one both return
`404 executive_record_not_found`; an unseen or unknown responsible link both return
`404 responsible_not_available`.

## Commands and results on the tested commit

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests` (Python 3.11.15) | 846 tests pass, including 27 new in `tests/test_executive_workflows.py` and the 11 existing in `tests/test_executive.py`. |
| `python3 tools/check_requirement_register.py` and `python3 tools/check_memory_plan.py` | Pass. Neither register file was edited. |
| `cd console && npm run build && npm test` (Node 22.22.0) | Typecheck and build pass; 92 unit tests pass, including 13 new in `console/tests/executive.test.ts`. |
| `CHROMIUM_PATH=/opt/pw-browsers/chromium python tools/check_executive_browser.py` (Playwright for Python 1.57.0, Chromium 141, SwiftShader) | 45 checks pass, no page errors. [Report](browser-report.json). |
| `tools/check_console_connected_browser.py`, output kept outside the repository | 64 checks pass with no page errors, so the existing connected flow, including its executive section, still holds. |
| `node tools/standalone.mjs`, then `CI=1 ALFRED_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test` in `console/` | 29 offline demonstration scenarios pass. `CI=1` makes Playwright start its own preview server instead of reusing one. |

The only browser console entry in the executive run is the expected `401` from the
signed-out session check before sign-in. The tracked `docs/evidence/console-connected`
files were not regenerated. `tools/check_executive_browser.py` is not yet part of CI; the
workflow files belong to the lead.

Run deliberately against the previous build (`7735693c0`), the new "every control stays
inside the dialog" assertion failed on a 390px overflow in the responsible filter. The
tested commit fixes it and the assertion passes.

## Screenshots

`executive-filter.png` and `executive-grouped.png` (responsible filter and grouping,
namesakes apart), `executive-decision.png` (options, choice, reopen history),
`executive-brief.png` and `executive-brief-sections.png` (assembled brief with citations),
`executive-attention.png`, `executive-insights.png`, `executive-panel.png` and
`executive-panel-insight.png` (side panel), `executive-brief-access.png` (brief after read
access is withdrawn), `executive-1280.png` and `executive-390.png`.

## Not done

- No reminder delivery of any kind, by design; attention is not wired into Pulse routines
  and keeps no history.
- Insights are three fixed rules inside one workspace per credential. They do not span
  workspaces and nothing learns or ranks relevance; ATT-001's learned relevance stays
  unmeasured.
- Briefs do not follow authored links beyond the record's own links, and are bounded to
  eight statements, twelve related records and six progress entries.
- Options cannot cite note lines or carry evidence of their own. There is no shared or
  multi-person decision.
- Responsible links accept only person or organisation records and assign nothing to an
  ALFRED account. Labels group by exact text.
- Snooze is a day (stored as 17:00 local time) and does not recur.
- Links from a follow-up to a drafted action, from the first receipt, are still not built.
- There is no meeting record kind, so no meeting preparation brief; briefs cover decisions,
  milestones and commitments.
- Software rendering only; no physical device, screen reader or GPU check.
