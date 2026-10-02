# Temporal review receipt (MEM-007): valid time, recorded time, disputes and supersession

2 October 2026. Worktree branch `wave2/temporal-review`, started from
`claude/alfred-development-qpgxhg` at `f358b09a8`. **Tested commit:
`cc1d0dab95c9e87e2f3f4833223b96501b2b909b`.** The commit that adds this receipt and its
screenshots changes no code. Status: implemented on a branch against synthetic data only.
Not merged, not deployed, not reviewed by the owner. First-party behaviour only: no
external temporal adapter was adopted, and the M07 adapter decision stays open.

## What exists

`alfred/memory_history.py` (new), small hooks in `alfred/reviewed_memory.py` and
`alfred/lifecycle.py`, one route branch in `alfred/desk_http.py`, two additive statement
fields in `alfred/console_api.py`, and in the console `MemoryReview.tsx`,
`StatementHistory.tsx`, `domain/temporal.ts` and `review.css`, with one-line hooks in the
dialogs, inspector, command parser, provider, read port and capture form.

1. **Recorded time.** Every review transition of a statement (proposed, accepted, disputed,
   withdrawn, superseded, invalidated, forgotten) is appended to `memory_claim_history` in the
   same transaction as the change, with ALFRED's recorded time and who made it: the reviewer,
   or ALFRED for an invalidation. Rows hold identifiers, states, times and the valid period
   only, never a statement's value.
2. **Withheld and restored, honestly.** Support that becomes unavailable or not permitted is
   not a stored state, so it is recorded only as an observation when ALFRED next reads the
   ledger ("noticed by ALFRED when it next looked"), once per change. Withheld stays distinct
   from invalidated: a withheld statement keeps its review state and its value is hidden; a
   changed source still invalidates with no revival across revisions.
3. **Migration.** Statements that predate the history are migrated once, marked `migrated`:
   the proposal time from the statement itself, later transitions from the audit log (which
   names the statement, the change and the time). A change the earlier records cannot place,
   such as an invalidation by whole-source removal, is recorded with `time_known=0` and the
   latest moment it could have happened; nothing is invented. Without audit rows, the last
   review time is used only as such an upper bound.
4. **Forgetting and restore.** Forgetting a statement or an entity and removing a whole source
   record their transitions without values. A restore replays the lifecycle journal, and a
   replayed forget is recorded as `replayed` at the journal's time. A backup older than the
   history is migrated when it is first opened. Tests check that no reviewed value appears in
   any history row, live or restored.
5. **Valid time.** Proposals and captures already carried `valid_from` and `valid_until`
   (half-open). An accept or supersede decision may now set the period too, once, while the
   statement is still proposed; after the first decision it is fixed (`memory_validity_fixed`),
   so the history remains a faithful account. The existing rules are unchanged: a statement
   outside its valid period is not used.
6. **As-of report.** `GET /desk/memory/as-of/{t}` (and `/valid/{v}` for a separate valid
   date) answers from the history alone which statements were accepted at recorded time `t`
   and valid at `v`, which were accepted but outside their valid period, and which migrated
   statements it cannot place. It applies the single-value conflict rule to what was held
   then, never comparing a value that is now removed or withheld. It is labelled
   `historical_report` with the basis "ALFRED's own review records, not a claim about the
   world", clamps a future time to now, and is deterministic for the same records. Current
   answers are unchanged.
7. **Console.** The Reviewed memory dialog (`memory`) has a review queue (accept with a valid
   period, accept as a replacement of a chosen statement, dispute, withdraw; version-checked;
   refusals explained) and the as-of view. The inspector shows each statement's valid period,
   recorded and review times, what it replaces and what replaced it, disputes, conflicts and
   its recorded history, and can dispute or withdraw an accepted statement. Same-name records
   are labelled by kind and identifier, and replacement choices come only from the same record
   by identifier and the same kind of statement.
8. **Access.** History and as-of reads authenticate the session, reconcile and recheck source
   support and grants through the same snapshot as the reviewed-memory view. Another person's
   or an unknown statement both return `404 memory_claim_not_found`. Withheld values stay
   hidden in history, lineage and the as-of report. The new routes are GETs inside the existing
   Host, Origin, session and loopback checks; decisions keep using the existing CSRF-checked
   review route.

## Evidence

| Check | Result at the tested commit |
|---|---|
| `python3 -m unittest discover -s tests` | 1056 tests pass (1032 before this work; 24 new in `tests/test_memory_temporal.py`) |
| `cd console && npm run build` | passes (typecheck and production build) |
| `cd console && npm test` | 113 tests pass (102 before; 11 new in `console/tests/temporal.test.ts`) |
| `tools/check_temporal_review_browser.py` | 50 real-browser checks pass, [report](browser-report.json) |
| `tools/check_console_connected_browser.py` (scratch output) | 85 checks pass. The first run under heavy machine load failed at the existing jobs step (a newly submitted job not shown within that step's default five-second wait), which this work does not touch; the immediate rerun passed all 85 |
| `tools/check_executive_browser.py` (scratch output) | 45 checks pass |
| Console offline demo suite (`node tools/standalone.mjs`, `npx playwright test`) | 29 scenarios pass |

`tests/test_memory_temporal.py` covers each transition with time and reviewer; supersession
on both sides and the lineage chain both ways; invalidation by ALFRED without revival;
withheld and restored observed without invalidating, with values hidden in history and the
as-of report; forgetting, entity forgetting and source removal without values; restore
replay at the journal time; migration from the audit log with unknown times marked and
treated as uncertain; migration of an older backup; the history capacity never blocking a
forget; valid periods at proposal, capture and review, fixed after the first decision;
outside-period rules unchanged; as-of on several dates and with a separate valid date,
deterministic and clamped; conflicts held then; namesakes kept apart; current answers
unchanged; actor and workspace isolation; and the HTTP routes with session, CSRF, Origin,
query and path checks.

The browser check runs the real loopback server over the synthetic demo vault with real
Chromium (UTC). To give the as-of view earlier days, the setup records reviews through the
real service with the server clock moved back by whole days; every browser step runs at the
real time. One statement's history rows are removed before the server starts, so the server
migrates it as a statement that predates history. The browser console records two expected
failed requests: the session check before sign-in (401) and the deliberately stale decision (409).

Screenshots: [queue](temporal-queue.png), [choosing the replaced statement](temporal-supersede.png),
[stale version refused](temporal-stale.png), [inspector lineage and conflict](temporal-inspector.png),
[recorded history](temporal-history.png), [as of five days ago](temporal-asof-past.png),
[as of today](temporal-asof-today.png), [withheld values hidden](temporal-withheld.png),
[forgotten, history kept without value](temporal-forgotten.png), [1280px](temporal-1280.png),
[390px](temporal-390.png).

## Commands

```text
python3 -m unittest discover -s tests
cd console && npm run build && npm test
CHROMIUM_PATH=/opt/pw-browsers/chromium python tools/check_temporal_review_browser.py
CHROMIUM_PATH=/opt/pw-browsers/chromium ALFRED_CONSOLE_OUTPUT=<scratch> python tools/check_console_connected_browser.py
CHROMIUM_PATH=/opt/pw-browsers/chromium ALFRED_EXECUTIVE_OUTPUT=<scratch> python tools/check_executive_browser.py
cd console && node tools/standalone.mjs && ALFRED_CHROMIUM_PATH=/opt/pw-browsers/chromium npx playwright test
```

## Limits and what remains

- Recorded time is ALFRED's own clock at the moment of each change. Withheld and restored are
  observations at the next read, not exact times. Migrated history is only as complete as the
  earlier statement records and audit log; gaps are marked, not filled.
- Supersession retracts the replaced statement from current use; it does not record that the
  replaced statement remained true for an earlier period. To keep both, the person states a
  valid period that does not overlap. Valid periods are whole days in the console.
- The as-of report uses the structural single-value rule only. It is not a semantic conflict
  detector, a truth model or a general temporal query language, and it does not feed answers.
- History is actor-private like the ledger; there is no shared or cross-person history, and
  it is not included in portable exports yet (MEM-013).
- Forgetting removes values from current records and history never held them, but SQLite free
  pages, the WAL before a checkpoint and older backups may still hold earlier bytes. This is not
  secure erasure; application encryption remains an owner decision (SYS-002).
- No external temporal adapter (Graphiti or similar) was evaluated or adopted; M07 stays open.
- Synthetic data only. No model, account, device, microphone or network call.
