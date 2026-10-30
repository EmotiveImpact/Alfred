# Receipt: the agent drafts panel

Tested at the commit that adds this receipt's review section, on branch `claude/project-thread-att046-agent-drafts`, from `main`
at `1d3398137`.

## What was built

- `alfred/brain.py`: `BrainHub.drafts` lists every draft a brain proposed under autonomy 1 or
  2, newest first, with its provenance label, the notes it came from (titles only while the
  owner may still read them), its action's state and fingerprint, and what the owner may do.
  `BrainHub.confirm_places` lets the owner type each address a note planted: the same address
  confirms it, a different one replaces it in the text as written, and the draft then becomes
  an action that waits for exact approval. `BrainHub.dismiss_draft` hides a draft, cancelling
  a waiting action. Two additive columns on `brain_proposals`: `confirmation` and `dismissed`.
- `alfred/provenance.py`: `replace(text, kind, held, new)`.
- `alfred/hub_goals.py`: `GET /desk/hub/drafts`, `POST /desk/hub/drafts/{id}/confirm` and
  `POST /desk/hub/drafts/{id}/dismiss`.
- `console/src/integration/agentDrafts.ts`, `console/src/components/AgentDraftsPanel.tsx`,
  `console/src/agent-drafts.css`, the `drafts` command and an Open agent drafts button.
- `docs/AGENT_DRAFTS.md`, a pointer in `docs/PROVENANCE_GATE.md`, a section in
  `console/docs/CONNECTED_CONSOLE.md`, rows in `docs/INDEX.md` and `coordination/BACKLOG.md`
  (C10), the new browser check named in `tools/egress_allowlist.json` and
  `docs/EGRESS_AUDIT.md`, and a CI step in the `console-connected` job.

The packet and bundle contracts are unchanged (both still version 1). Nothing sends anything:
the only effect anywhere is the existing local draft after exact approval.

## Checks run at the tested commit

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -p test_agent_drafts.py` | 34 tests, OK |
| `python3 -m unittest discover -s tests` | 1,808 tests, OK |
| `cd console && npm run build` | typecheck and build OK |
| `cd console && npx vitest run` | 183 tests in 19 files, OK (9 new) |
| `tools/check_agent_drafts_browser.py` | 21 checks passed, no page errors |
| `tools/check_hub_goals_browser.py` | 19 checks passed |
| `tools/check_console_connected_browser.py` | 108 checks passed |
| `python3 tools/check_claims.py --base origin/main --branch claude/project-thread-att046-agent-drafts` | claims ok |
| `python3 tools/egress_audit.py` | ok, 116 files, 40 allowlisted imports, 0 warnings |
| `python3 tools/check_adoptions.py` | ok, nothing adopted |
| `python3 tools/check_public_hygiene.py` | ok, 137 findings all under reviewed exceptions, none stale |

`tests/test_agent_drafts.py` was written first and failed (31 errors) before the code existed.
The two other browser checks were run because this change touches the console's dialogs and
the hub's routes.

## A race found on the way (backlog C11)

The drafts browser check first failed in 2 of 13 runs, both while other work loaded the
machine: one task never became a draft. Its job had failed at dispatch with
`mandate_required`. `BrainHub.submit` creates the job, then binds it to its mandate in a
second transaction, and a brain worker that claims the job in between refuses it. This race
is in the hub itself and predates this change; it is logged as C11 with the fix (bind in the
job's own transaction). The check now starts its worker after every task is bound, and prints
the job states and accounting rows if ingestion ever stalls. After that change it passed 10
of 10 runs beside two full test suites running at once.

## Review fixes

Two findings from the automated review, each shown by a failing test before the fix:

- A draft whose notes had changed could still be confirmed, and the action it became could
  then never be approved. `can.confirm` and `confirm_places` now run the same source check as
  approval (`brain.sources_current`, shared with `action_current`), so the panel withholds Try
  again and the server answers `sources_changed`.
- The counts in the header covered only the 100 drafts listed. Every open draft is now
  counted; only the list stops at 100.

## What the browser check drives

Real Chromium against the real loopback server over the synthetic demo vault, plus two
invented notes (one an email planting an address), with the deterministic synthetic brain
plugged in through a goal hub and the host's own supervisor cycle ingesting its results:

- the header reads "2 waiting · 1 stopped";
- the owner's own draft and a draft using a note can be approved; the note is named;
- the stopped draft names the address, the note it came from and when, offers Read in full,
  See the note it came from, Try again with an address I confirm and Dismiss, and no Approve;
- See the note it came from opens that note in the record inspector;
- typing something that is not one address is refused by the server; typing a trusted
  address replaces the planted one, and the server's action holds the new text, waiting;
- Approve asks for consent to the exact text before it is enabled, and the server queues it;
- Dismiss asks first for a waiting draft, and the server cancels its action;
- no horizontal scroll at phone width, no request leaves the loopback origin, and a reader
  key is told drafts belong to the owner.

Screenshots: `browser/agent-drafts-desktop.png` and `browser/agent-drafts-phone.png`.

## Not tested here

- Any real model. Only the deterministic synthetic brain ran.
- An address a pattern does not see (paraphrased or encoded). As with the gate, exact
  approval stays the decision.

Synthetic data only. Every address in the tests and the browser check is assembled from
pieces at run time. Paths the encryption thread claims are untouched.
