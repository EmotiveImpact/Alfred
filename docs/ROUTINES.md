# Authored routines (M10)

2 October 2026. Requirements ATT-001, MEM-004 and MEM-015; memory backlog job M10. This
describes what `alfred/routines.py` does on the `wave2/routines` branch and what it does not.
It is implemented against synthetic data only, not merged, not deployed and not reviewed by
the owner. Evidence: [receipt](evidence/routines/RECEIPT.md).

## What a routine is

A setting the person authors, not an agent. There are two allowlisted kinds, fixed in code.
Nothing in a note, a reviewed statement, a procedure or generated text can add a kind,
change a setting or start a run.

| Kind | Reads | May produce |
|---|---|---|
| `commitment-review` | Open executive commitments and follow-ups, and accepted, current reviewed statements captured with memory type `commitment` | A reminder for each one due within 24 hours or overdue; optionally a draft offer for an overdue record with a responsible label |
| `morning-brief` | Executive attention items (not snoozed), derived insights, and the person's own proposals awaiting approval whose evidence is current | An in-app brief stored as citations and counts; surfaces nominations held for it |

Each kind states its rules in the view the console shows. A commitment statement has a date
only when its `scheduled_for` value starts with `YYYY-MM-DD`, optionally followed by `HH:MM`,
read in the routine's local offset; a date alone means 17:00, the same convention the console
uses for executive due dates. Any other commitment statement is read and counted as undated.

## Settings

Every change carries the routine's version and is refused if it changed elsewhere.

- **Enabled** and a **schedule**: every 1, 2, 4, 8, 12 or 24 hours (aligned to local midnight)
  or daily at a chosen `HH:MM`.
- **Local time offset**: a fixed number of minutes from UTC, in 15-minute steps. Daylight
  saving changes are not followed automatically; the person changes the offset.
- **Run budget per day** (1 to 24, counted from local midnight) and **nominations per run**
  (1 to 10; for the brief, how many held nominations it surfaces).
- **Quiet hours**: nominations made inside them are held and shown when they end.
- **Interrupt choice** (commitment review only): show nominations now, or hold them for the
  next morning brief.
- **Offer local drafts** (commitment review only).
- **Pause**, per routine. The existing workspace pause also stops every routine.

Only the owner credential the host was started with can author routines
(`routine_owner_not_hosted` otherwise), because runs execute under that credential. A reader
sees that routines are set by the owner and nothing else.

## Runs

Routines run only inside the existing foreground supervisor cycle; there is no thread,
service or off-device runner. Each due slot produces exactly one run record, inside one
transaction that re-authenticates the owner credential, reads the workspace pause and
applies current source grants through the shared reviewed-memory currentness rule.

- **Completed**: what it read (counts), what it cited (record or statement IDs with versions,
  and note revision and lines for statements), what it nominated and why, what it held and
  until when, what it did not nominate and why (already nominated, over the budget, over the
  open limit, snoozed), budget used and slots missed while ALFRED was not running.
- **Skipped**, with the reason: `paused`, `workspace_paused`, `budget_exhausted` or
  `authority_lost` (the credential was revoked or expired, or is not the one now hosting).
  Nothing is read or nominated.
- **Failed**: nothing the run did is kept; the error code is recorded and the slot moves on.

Missed slots are counted, never run afterwards in a burst. Stored outcomes hold citations and
counts only, never titles or values. Views resolve each citation as the caller may read it
now; a statement that is no longer usable or readable shows as "no longer available" with no
value.

## Nominations

A nomination is a suggestion with a stated reason and the exact commitment version it cites.
A commitment version is nominated at most once; editing it makes a new version. The person
accepts or dismisses each one, and both are recorded with time and outcome.

- Accepting a **reminder** records the acceptance. With "add follow-up", it creates an
  executive follow-up through the existing `ExecutiveRecords.create`, with a request ID fixed
  to the nomination so a retry cannot create a second one.
- Accepting a **draft offer** proposes a `message.draft` action in the existing ledger, bound
  to the cited record version. It is never approved automatically: the person approves the
  exact text with its fingerprint through the existing review, and approval and dispatch both
  recheck that the cited record is unchanged and open. The proposal expires after 15 minutes,
  like other proposals; the nomination stays accepted. Nothing is ever sent.
- A changed or unavailable commitment can only be dismissed.
- Another person's nomination and an unknown one both return `404 nomination_not_found`.

## Procedures (MEM-015)

`GET /desk/routines/procedures` lists statements captured with memory type `procedural`: the
statement, its review state, its support state (current, changed or withheld) and its exact
source lines, plus authored notes of type `procedure` labelled as not reviewed. It is
read-only and has no write route. `tests/test_routines_procedures.py` indexes, captures and
accepts procedure text that says to run a command, widen grants, approve an action, change
routine settings and submit a long job, then runs routines, retrieval, answers, the
conversation queue, a job, Pulse and supervisor dispatch, and shows that no grant, policy,
credential, approval, routine setting, job or file changed.

## Routes

All sit behind the existing desk handler: loopback Host and Origin checks, session cookie,
and CSRF on every POST.

| Route | Purpose |
|---|---|
| `GET /desk/routines` | Settings, stated rules, recent runs with resolved citations, nominations |
| `GET /desk/routines/nominations` | What the executive panel shows: nominations shown now and the latest brief |
| `GET /desk/routines/procedures` | The read-only procedure registry |
| `POST /desk/routines/{kind}/configure` | Save settings with the routine's version |
| `POST /desk/routines/{kind}/pause` | Pause or resume with the routine's version |
| `POST /desk/routines/{kind}/run` | Run now; budgets, pauses and authority apply as on schedule |
| `POST /desk/routines/nominations/{id}/accept` | `{version, create_follow_up}` |
| `POST /desk/routines/nominations/{id}/dismiss` | `{version}` |

## Limits

- One routine per kind per workspace, running under the hosted owner credential, reading
  that credential's actor-private records only.
- Fixed offsets, not time zones. No learned relevance, ranking or model is involved.
- In-app only: no push, e-mail, device, calendar or notification delivery of any kind.
- Bounded storage: run records older than two days beyond the latest 400 are removed, and
  decided nominations beyond the latest 400; at most 64 open nominations at a time.
- The executive panel shows at most three nominations; the rest are in the Routines panel.
- No connection to Pulse's two existing reports, which are unchanged.
