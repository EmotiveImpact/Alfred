# Connected console: real backend adapter

2 October 2026. Implements the read-only projection, selection-to-question and
server-approval connection that `COMPONENT_ARCHITECTURE.md` described as proposed.
The offline demonstration build is unchanged and still uses labelled fixtures.

## How to run it

```text
cd console && npm ci && npm run build      # produces console/dist
python3 -m alfred.desk init                # synthetic workspace, outside the repository
python3 -m alfred.desk access              # reveals the local owner key in a private terminal
python3 -m alfred.desk serve               # then open http://127.0.0.1:8765/console/
```

The Python server serves `console/dist` from its own loopback origin. The console
therefore inherits the existing HttpOnly session cookie, CSRF token, exact Host and
Origin checks and `default-src 'none'` content security policy without any change.
No cross-origin proxy, CORS header or relaxed loopback rule was added.

## Mode is decided by the serving origin, never by failure

`console/index.html` carries `<meta name="alfred-mode" content="demo"/>`. When the
ALFRED server serves the page it rewrites exactly that marker to `connected`. Vite
preview and the standalone file keep `demo`. A failed request in connected mode shows
an honest state (signed out, refused, unreachable); it never loads fixtures.

## Server contract

| Route | Returns |
|---|---|
| `GET /desk/console/workspaces` | The credential's single permitted workspace and current grant revision. |
| `GET /desk/console/projection` | Authorised projection: nodes, edges, server approvals, insights, model availability, data and grant revisions. |
| `GET /desk/console/records/{note|entity|source}:{id}` | Exact note lines, reviewed statements with original support, or source status. Unknown and denied records are both `404 record_not_available`. |
| `POST /desk/conversations/{id}/turns` | Existing queue, now with optional `focus`: the selected record. |

Implementation: `alfred/console_api.py`. The projection is built only from what
`KnowledgeStore.knowledge` and `ReviewedMemory.view` already return to this bearer,
so source grants filter records, counts, labels and links before anything is counted.
Authored note references (`note_reference`), reviewed relationships between
entities (`reviewed_claim`) and the excerpt a reviewed statement cites
(`review_support`) are separate edge layers. Proposed, disputed, conflicting or
invalidated statements produce no edge. Same-name entities remain separate nodes.

If the grant revision changes while the projection is assembled, the server returns
`409 projection_authority_changed` instead of possibly stale data; the console
retries once.

## Console behaviour

- `state/useConnection.ts` checks the session, signs in and out, reads the projection
  with an `AbortController`, polls every eight seconds while the tab is visible and
  replaces the projection wholesale.
- A grant or workspace change clears the selection, dialogs, search and any open answer.
  Revocation or sign-out clears every record. Network loss keeps the last confirmed
  view, labelled `Unreachable` with its confirmation time.
- The record inspector re-reads the selected record from the server whenever the
  projection changes. Changed support appears as "Source changed · review needed".
- Plain text in the command bar asks; `search …` searches; local commands open panels.
  The selected note or reviewed entity travels as `focus`. The server re-authorises
  it, labels it `user_selection_context_not_authority` and refuses an unavailable one.
- The Ask panel shows exact excerpts, retrieval reason, reviewed statements with
  their basis, same-name ambiguities and the model state. With no model configured
  it says so; nothing is generated. An open answer is withdrawn when a source changes.
- Proposing a draft from an answer is a separate step on the existing
  `/desk/conversations/{id}/draft` route. Approval and cancellation use the existing
  `/desk/actions/{id}/approve|cancel` routes with the exact fingerprint. Demo review
  receipts are never converted into server actions.

## Bounded jobs

An owner can run a first-party job (word and line count, or extractive first lines) on the
exact note revision open in the inspector, through `/desk/jobs`. The Bounded jobs panel
(command `jobs`, or Open jobs in Console controls) follows the job's server events from an
in-memory cursor, stops polling when closed, resumes after the last seen event when
reopened, and reads everything back from the server after a reload. Results are text with
their stated basis, never markup. The panel says plainly that the backend is a local
subprocess, not a sandbox. Readers can see jobs on sources they may read but cannot submit
or cancel. Authority loss clears the panel with every other view.

## Pairing another device

The sign-in screen offers "Pair this device with a code". A person signed in elsewhere
creates a single-use code in Data and permissions; the new device redeems it with a name,
receives its own key once (the console asks the person to confirm they kept it), and then
signs in as the same person with no more authority than the offering device. Devices are
listed per person and can be revoked from any other device of that person. See the M02
receipt for the rules.

## Removing a source

An owner can remove a whole source from the source inspector after explicit consent. The
server journals the removal, deletes the source's indexed content and everything derived
from it, and returns a receipt that the console summarises. The person's files are never
touched. Answers withdrawn this way, or by forgetting a statement, end with a plain message
instead of waiting.

## Host health and pause

Console controls show `GET /desk/console/health`: what the foreground host reports about
itself, vault scanning, waiting questions, jobs and, for owners, the last backup. The owner
can pause and resume background work with a confirmation; readers see the state only.

## What supports an answer

Each answer carries the server's support report (INT-002): which of the question's words
appear in what is shown and which do not, excerpt and note counts, reviewed statements
used and withheld by reason, skipped sources, follow-up context and model review findings.
It is quiet when everything is covered and uses sparse amber when something is missing. It
states its limits and never claims truth, entailment or completeness.

## Sync conflicts and export connectors

A note with a sync conflict copy beside it shows the copy, the tool that made it and plain
guidance; ALFRED never merges or chooses. A source lists all its conflict copies, including
those whose original is missing. Items imported by a read-only export connector are
labelled as unchecked export reports, not authored notes. The access panel lists export
connectors with their freshness, item count and scopes, and shows an Import switch
(`connector.read`) for connector sources in place of inbox writing. Imports themselves stay
an offline command.

## Executive workflows (ATT-002, ATT-001)

The executive dialog ("tasks") reads `GET /desk/executive` directly and re-reads it
whenever the projection revision changes. Every write sends the record's exact version.

| Route | Purpose |
|---|---|
| `POST /desk/executive/records/{id}` | Existing update, now also `responsible`, `responsible_link` and `snoozed_until`. |
| `POST /desk/executive/records/{id}/options` | Replace a proposed decision's two to six authored options. |
| `POST /desk/executive/records/{id}/decide` | Record the chosen option, rationale and time. Only on this explicit call. |
| `POST /desk/executive/records/{id}/reopen` | Return a decision to proposed; the earlier choice stays in its history. |
| `POST /desk/executive/records/{id}/progress` | An authored progress note on an open milestone. |
| `GET /desk/executive/records/{id}/brief` | Assemble a brief for a decision, milestone or commitment. Computed, never stored. |

All of them pass through the same Host, Origin, session and CSRF checks as every other
desk route. Another person's record and an unknown one both return
`404 executive_record_not_found`.

- **Responsible** is a label the person types, optionally linked to a person record
  they explicitly pick. The records view filters and groups by label and link together,
  so namesakes and different spellings stay apart. A link the person can no longer see
  shows as "Linked record not available", never as a name.
- **Decisions** keep options in the authored order; nothing scores them. A decided
  decision must be reopened before its options change.
- **Briefs** say they are assembled, not advice and not model output. Each item cites
  its record version, or note revision and lines, or reviewed statement version. The
  brief is assembled again when the projection changes, so withdrawn material drops out.
- **Attention** lists overdue, decision past due, due soon and stale milestone items by
  stated rules, with an authored snooze. It is shown in the console only.
- **Insights** are derived from the person's own records by three stated rules and
  labelled as derived, never accepted.
- The projection adds `executive.attention`, `attentionCount`, `snoozedCount` and
  `derivedInsights`, a `responsible` field on executive nodes, and an
  `executive_responsible` edge (authored basis) to an explicitly linked, visible person.
  Executive values join `dataRevision`, so time-based attention changes reach the view.

Acceptance: `tests/test_executive_workflows.py`, `console/tests/executive.test.ts` and
`tools/check_executive_browser.py`. Receipt: `docs/evidence/executive-2/RECEIPT.md`.

## Reviewed memory over time (MEM-007)

The Reviewed memory dialog (command `memory`, or Open reviewed memory in Console controls)
has two views. Both read the server directly and read again whenever the projection changes.

| Route | Purpose |
|---|---|
| `GET /desk/memory` | Existing ledger view; the review queue reads proposed and disputed statements from it. |
| `POST /desk/memory/claims/{id}/review` | Existing decision, version-checked. Accept or supersede may now also carry `valid_from` and `valid_until`, once, while the statement is still proposed. |
| `GET /desk/memory/claims/{id}/history` | Recorded history (states, times, who, how ALFRED knows) and the replacement lineage both ways. |
| `GET /desk/memory/as-of/{t}` and `/as-of/{t}/valid/{v}` | What was accepted at recorded time `t` and valid at `v` (default `t`), from the history alone. |

- **Review queue.** Proposed statements oldest first, then disputed ones. Accept (optionally
  with a valid period), accept as a replacement of a statement the person chooses (only the
  same record by identifier and the same kind of statement are offered, so a namesake's
  statements never are), dispute or withdraw. A refused decision, such as a stale version,
  is explained above the queue after it refreshes. A statement whose support is withheld
  shows no value and cannot be decided until access returns.
- **As of a date.** The person picks the day they held something and, optionally, a
  different day for validity. The report is labelled as ALFRED's own review records, not a
  statement about the world. It lists what was accepted and valid then, what was accepted
  but outside its valid period, and what migrated history cannot place, with conflicts under
  the single-value rule. Values withheld, invalidated or forgotten now are named as such and
  never shown.
- **Inspector.** Each reviewed statement shows its valid period, recorded and review times,
  what it replaces and what replaced it, a dispute, any current conflict, and its recorded
  history on request. An accepted statement can be disputed or withdrawn there.
- The capture form ("Remember this") can set a valid period; the preview shows the period
  the server recorded.

Current answers are unchanged: they still use only accepted, current, authorised and valid
statements. Acceptance: `tests/test_memory_temporal.py`, `console/tests/temporal.test.ts`
and `tools/check_temporal_review_browser.py`. Receipt: `docs/evidence/temporal-review/RECEIPT.md`.

## Not provided by this increment

Priorities, recommendations and milestone progress now come from executive records
(`alfred/executive.py`); without records the panel says so rather than inventing them.
There is one workspace per credential. No voice, account, device or
specialist-system connection. Software-rendered browser checks are not physical
device or GPU certification.

## Acceptance

- `tests/test_console_api.py` (16) and `tests/test_console_focus.py` (12): real HTTP
  and service checks, including other-workspace exclusion, strict-grant non-leakage,
  source change, revocation, same-name entities, static-path traversal and a race.
- `console/tests/connected.test.ts` (18): mapping, reducer selection rules, command
  routing and mode detection. `console/tests/jobs.test.ts` (8): job event merging, result
  reading, wording and command routing. `console/tests/pairing.test.ts` (2): pairing
  redemption and its in-memory CSRF token.
- `tools/check_console_connected_browser.py` (98 checks): real Chromium against the
  real server and a synthetic vault. Evidence: `docs/evidence/console-connected/`.
