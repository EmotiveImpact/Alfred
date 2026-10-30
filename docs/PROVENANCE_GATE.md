# The provenance gate

`alfred/provenance.py` labels every action a brain proposes with where its contents came
from, and `BrainHub` uses the label so that text inside a note or an email cannot steer an
action by itself. It is the safety idea in phase 2 of the master plan, taken from the CaMeL
research (Debenedetti and others, "Defeating Prompt Injections by Design", 2025). Only the
idea is used: no code was copied from Google's copy or from any other version, so there is
nothing to adopt or credit under the adoption check.

## The problem it answers

A brain reads the owner's notes. A note can hold an email the owner pasted in, and that
email can hold a planted line such as "send everything to this address". A model may obey
it. Before this gate, ALFRED already made sure nothing happened on its own: a brain can
only propose, only `message.draft` can become an action, and that action waits for the
owner to approve its exact parameters. The gate adds one more line of defence, so that a
proposal steered by planted text is not offered for approval at all.

## Two kinds of text

| Trusted: the owner's own words | Untrusted: data |
| --- | --- |
| The goal statement | Every note excerpt in the packet |
| The instruction | Every excerpt's title |
| Learned statements the owner reviewed and accepted | |

The brain's own reason for an action, and the excerpts it cites, are its claims. They can
mark an action as using a note, but they can never clear one.

## Places

A **place** is a value that decides where an effect goes or whom it reaches:

| Kind | Read as |
| --- | --- |
| `email` | an email address |
| `url` | a web address with a scheme, `mailto:` or starting `www.` |
| `domain` | a bare domain such as `drop.example.org`, with any path after it |
| `handle` | a social handle starting `@` |
| `phone` | a number starting `+` or `0` with 9 to 15 digits, compared by its digits |

Every place in a proposal's parameter values must also appear in the owner's own words.
A place the owner gave is fine even if a note mentions it too. A place found only in a note
is from the note. A place found nowhere is treated the same way, because a brain can turn
"drop dot example dot net" in a note into a real address.

A path added to a domain the owner named is a different place: if the owner wrote
`example.org`, then `example.org/?d=plan` is not theirs. Dates, times, amounts and file
names (`notes.md`, `plan.pdf`) are not places.

Text is compared after Unicode NFKC normalisation, with invisible characters such as
zero-width spaces removed and letters case folded, so a hidden character or a lookalike
wide letter does not disguise an address.

## The label

Each proposal under autonomy 1 or 2 carries a label, shown in `BrainHub.proposals` as
`provenance`:

```json
{"label_version": 1, "verdict": "steered_by_untrusted_text",
 "places": [{"kind": "email", "value": "<the address>", "source": "excerpt", "refs": ["E1"]}],
 "cited": ["E1"], "copied": ["E1"], "basis": "pattern_tripwire_not_proof_of_origin"}
```

- `places`: each place once, in the order it first appears. `source` is `owner`, `excerpt`
  (with the excerpts it appears in) or `unsourced`.
- `cited`: the excerpts the brain says the action came from.
- `copied`: the excerpts the action shares a run of six words with, leaving out runs the
  owner also wrote.
- `verdict`:
  - `steered_by_untrusted_text` when any place is not the owner's;
  - `uses_untrusted_text` when there is no such place but the action cites or copies a
    note. Drafting from notes is ordinary use of data, so this is shown, not held;
  - `owner_only` otherwise.

Under autonomy 0 a brain's proposals keep no parameters, so they keep no label either.

## Modes

`BrainHub(..., provenance_mode=...)` takes one of three modes:

| Mode | What happens to a proposal steered by a note |
| --- | --- |
| `enforce` (the default) | Under autonomy 2 it is refused with `steered_by_untrusted_text` before any action exists, so there is nothing to approve. Under autonomy 1 it stays a draft for the owner to read, with its label |
| `watch` | It is labelled and still becomes a pending action that needs the owner's exact approval |
| `off` | No labels are made. This is the behaviour before the gate |

A capability brains may not use (for example `message.send`) is refused for that reason
first, and is still labelled. Each steered proposal is written to the audit log as
`brain.proposal_steered_by_untrusted_text`. A result shows the mode and how many proposals
were steered, for example `{"mode": "enforce", "steered": 1}`; `steered` is `null` when no
labels were made.

`enforce` was chosen as the default because the only action a brain can propose today is a
local draft, so a wrongly held proposal costs little: the owner can see it with its reason
in the console's Agent drafts panel and type the address themselves to offer it for approval
([AGENT_DRAFTS.md](AGENT_DRAFTS.md)), or ask again naming it. The owner can choose `watch`
instead.

## What it does not do

- It reads patterns, not intent. A brain can paraphrase or encode a value so that no
  pattern sees it, and the gate cannot tell whether the owner wanted an action. Exact
  approval stays the decision for every action.
- It does not hold an action because its wording came from a note. Only places are held.
- It does not label memory suggestions. Those already go to a review inbox as
  suggestions, citing the notes they came from.
- It is not CaMeL's full design, which splits the brain into a planner that only sees the
  owner's words and a reader that only sees data. That would decide how brains are built,
  which is still the owner's open choice in the master plan.
- When ALFRED gains a capability with named fields (a recipient, a payee or an account),
  those fields should be checked as places by name, and an amount or account number may
  need to become a place too. Today only `message.draft` exists, with one field, `text`.

## Where it lives

- `alfred/provenance.py`: `label(packet, action)`, `places(text)` and the modes. Pure
  functions with no input or output.
- `alfred/brain.py`: `BrainHub` takes `provenance_mode`, labels proposals in `ingest`,
  refuses steered ones in `_pending` under `enforce`, and stores each label in the new
  `brain_proposals.provenance` column. An older database gains the column when it is next
  opened; proposals recorded before then have no label.
- Tests: `tests/test_provenance_gate.py`, and the planted-instruction tests in
  `tests/test_brain_plug.py`.
- Receipt: [evidence/provenance-gate/RECEIPT.md](evidence/provenance-gate/RECEIPT.md).
