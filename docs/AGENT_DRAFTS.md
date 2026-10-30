# Agent drafts

The **Agent drafts** panel in the console lists every draft an agent (a brain plugged into
ALFRED's hub) wrote for the owner, says where each draft's contents came from, and offers
only what is safe for that draft. It is the owner-facing side of the
[provenance gate](PROVENANCE_GATE.md): the gate decides, and this panel shows the decision and
its reason. Approving a draft saves a local draft only. Nothing is ever sent from here.

Open it by typing `drafts` (or `agent drafts`) in the command bar, or with **Open agent
drafts** in Console controls. It needs a host started with `desk serve --hub synthetic`;
without brains plugged in, the panel says so.

## What each card shows

| Chip | When | What the owner can do |
| --- | --- | --- |
| From your own words | Every address in the draft is in the goal, the instruction or a statement the owner reviewed, and the draft uses no note | Read in full, Approve, Dismiss |
| Uses wording from a note | No address came from a note, but the draft cites a note or copies six or more words from one. The card names the note | Read in full, Approve, See the note it came from, Dismiss |
| Stopped | The gate refused it. For an address that came from a note, the card names the kind of address, its value, the note it was found in and when it stopped | Read in full, See the note it came from, Try again with an address I confirm, Dismiss. No Approve |
| Address you confirmed | The owner typed the address themselves (below) | Read in full, Approve, Dismiss |
| Address from a note | Under autonomy 1 (suggest), a draft is never offered for approval, so one steered by a note is shown, not held | Read in full, Dismiss |

Each card also says the draft's state: waiting for approval, stopped, suggested only,
approved and being saved, saved as a local draft, cancelled, approval window closed, or that
its notes changed so it cannot be approved. A draft that asked for something agents may not
do (for example `message.send`) is shown as stopped for that reason and can never be
confirmed.

The agent's own note on why it wrote the draft is shown as the agent's words. It never
clears an address.

## Try again with an address I confirm

A draft stopped because an address came from a note can be offered for approval in one way
only: the owner types each such address into its own box, from somewhere they trust (their
contacts, a call, a letter), not copied from the email that held it.

- Typing the **same** address confirms it. The draft keeps its text.
- Typing a **different** address puts the owner's in the draft instead, wherever the held
  one appears, keeping the words and punctuation around it.
- Either way the draft becomes an action through the existing `LocalCore.propose`, and still
  waits for the owner to approve its exact text with its fingerprint. Confirming approves
  nothing.

The server checks every part of this:

- each box must hold exactly one address of the same kind as the held one, and nothing else
  (`invalid_places`); there must be one box per held address, in the order ALFRED found them;
- the confirmation is bound to the fingerprint of the draft the owner saw (`proposal_changed`);
- only a draft refused with `steered_by_untrusted_text` can be confirmed (`not_held`), and
  not once dismissed (`proposal_dismissed`);
- every note the draft came from must still be readable and unchanged since the draft was
  written (`sources_changed`);
- an address disguised with invisible characters can be confirmed as it is, but not swapped,
  because ALFRED cannot find it in the text as written (`address_hidden_in_text`);
- after the change ALFRED labels the draft again, counting the typed addresses as the owner's
  words. If an address the owner did not give is still there, nothing changes
  (`address_not_confirmed`).

Confirming again with the same addresses changes nothing. The brain's own proposal is kept as
it was: `BrainHub.proposals` still shows the brain's text, and the confirmation (when, what
was held, what was typed, whether it replaced the address, and the new label) is stored
beside it in `brain_proposals.confirmation` and written to the audit log as
`brain.proposal_places_confirmed`. Approval and dispatch still run `brain.action_current`,
so a changed source or a failed acceptance check holds the draft as before. When the owner
replaced an address, a declared `effect_readback` check reports that the saved draft differs
from what the brain returned, which is true.

## Dismiss

Dismissing hides a draft from the list and keeps its record (`brain_proposals.dismissed`,
audit `brain.draft_dismissed`). A draft still waiting for approval has its action cancelled
too, after the panel asks. One already approved and not yet saved cannot be dismissed
(`draft_in_progress`). The panel counts dismissed drafts without showing them.

## What is withheld

Once the notes a result came from can no longer be read under the owner's grants, the card
withholds the draft's text, the agent's note, the address values and the note titles, and
offers neither Approve nor Try again. Readers see that drafts belong to the owner and nothing
else; another owner sees none of them.

## Routes

All reached only through the guarded desk handler (loopback Host and Origin, the session
cookie and, for every POST, the CSRF token), and answered by the brain hub the host built.

| Route | What it does |
| --- | --- |
| `GET /desk/hub/drafts` | `BrainHub.drafts`: up to 100 drafts, newest first, with counts covering every open draft |
| `POST /desk/hub/drafts/{id}/confirm` | `BrainHub.confirm_places`, body `{"fingerprint": "<the draft's>", "places": ["<one per held address>"]}` |
| `POST /desk/hub/drafts/{id}/dismiss` | `BrainHub.dismiss_draft`, body `{}` |
| `POST /desk/actions/{action}/approve` | The existing approval route, with the action's exact fingerprint |

## Where it lives

- `alfred/brain.py`: `BrainHub.drafts`, `confirm_places` and `dismiss_draft`; two additive
  columns on `brain_proposals` (`confirmation`, `dismissed`), added to an older database when
  it is next opened.
- `alfred/provenance.py`: `replace(text, kind, held, new)` swaps one place as written.
- `alfred/hub_goals.py`: the three routes.
- `console/src/integration/agentDrafts.ts` and `console/src/components/AgentDraftsPanel.tsx`.
- Tests: `tests/test_agent_drafts.py`, `console/tests/agent-drafts.test.ts`, and the browser
  check `tools/check_agent_drafts_browser.py`.
- Receipt: [evidence/agent-drafts/RECEIPT.md](evidence/agent-drafts/RECEIPT.md).
