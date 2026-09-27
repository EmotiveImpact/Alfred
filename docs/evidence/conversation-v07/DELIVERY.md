# ALFRED conversation v0.7 delivery receipt

26 September 2026. Appearance remains provisional. This increment develops conversation
continuity and reviewable work within the existing personal OS shell, not a replacement UI.

## Repository checkpoint

Branch: feat/alfred-conversation-2026-09-26.
Predecessor v0.6: f5a3be2f093ae38a669de6f07ff1c9609c175ba2.
Final authored application/test input: 0127f029d78f5bc00dac3a8f7295bf374dd4f872.
Verified application/evidence checkpoint: 3279b90efcfae9881cac93ca0faca7ea56cf9869.
Verified checkpoint tree: 516ffa86c7fd5ccd8bbcb216ce4265cd6353698a.
This receipt and the supplemental model bundle are documentation/evidence-only additions
to that checkpoint. They do not change runtime code or inherit a new code test count.
Main has not been merged and no deployment was performed by this work.

## Delivered behaviour

- Private saved conversation threads, scoped to both workspace and creating credential.
- Explicit follow-up or new-topic choice with bounded previous user questions, fresh
  source retrieval and no automatic promotion of earlier generated text into evidence.
- Queued model work outside the HTTP request loop, so navigation remains responsive.
- Source revision, deletion and access invalidation before/after generation and on reads.
- Editable, source-bound local draft proposals through the existing separate approval
  and result-verification flow. No message delivery or external account is implemented.
- Thread expiry, forget behaviour, request idempotency, interrupted-run state and bounds.
- A real local-model experiment, with disclosed semantic failures, not just a fake response.

Default source mode does not generate an answer. The optional local model is explicitly
configured and tool-free. It is not selected or certified as the production brain.
The source evidence graph, Pulse, permissions and prior work remain intact.

## Actual acceptance

https://github.com/EmotiveImpact/Alfred/actions/runs/36221287760
Input: 0127f029d78f5bc00dac3a8f7295bf374dd4f872.
Job: 108346906567. Completed successfully.

- 451 first-party code tests on Linux/Python 3.12.3.
- 141 real-backend browser checks: 33 Desk, 25 Knowledge, 23 source-question,
  35 personal OS/Pulse, 25 conversation checks.
- 17 standalone read-only preview checks.
- Both upstream archive verifiers: 1,946 original and 127 extension files, unchanged.

The exact downloaded final developer package independently passed all 451 tests under
local Python 3.13.5. All 145 files named in PACKAGE_SHA256.json matched their SHA-256
values, and all 69 first-party source-receipt entries matched the packaged bytes.

Browser acceptance exercised the real HTTP server and SQLite with fictional sources.
A delayed model double tests UI responsiveness and lifecycle deterministically. Real
inference is separately documented in MODEL_SESSION_REVIEW.md and the preserved trial
files. These checks are not 141 independent security proofs or a broad model benchmark.

The initial conversation acceptance failed because forget removed the stored thread
but left old text visible. The interface now explicitly clears rendered turns, and the
same browser assertion passed. The initial model protocol also rejected contradictory
answerable=false/nonempty-claims output; the adapter now has one abstention representation.
Neither failure was waived or hidden.

## Downloadable build

Preview: docs/previews/conversation-v07/ALFRED-OS-v07.html
Bytes: 206822.
SHA-256: bdb25409172d30007e061466eda8017a5d31b3f1dba026c0beefc0e0bed72481

Developer package: docs/previews/conversation-v07/ALFRED-OS-v07-Developer-Package.zip
Bytes: 2697366.
SHA-256: c94ad8c4c2fb048a216f362ad4155aedbe6f8149b2753eb0df7d10127f6ae2f5

Downloaded final acceptance artifact: 10899383150.
Artifact SHA-256: 83bbf8ad7763d5ea0496a5297f3ae3043d1c94bff469c27de0d27796dce01691

The preview is the actual frontend with fictional in-file transport and selected
precomputed source examples. It cannot run inference, persist threads, approve work or
connect accounts. The developer package is runnable first-party source, not a hosted
service; upstream quarantine and model weights are excluded. The last supplemental
model evidence bundle is in the repository, not in the already verified developer ZIP.

## Remaining boundaries

No voice/microphone, external account/device control, ENDSTATE or Noir integration.
No general agent runtime with tools has been connected. Real-model relevance, abstention,
conflict handling and citation support remain under evaluation. Known failures are in
MODEL_SESSION_REVIEW.md. A syntactically valid citation does not prove entailment.

Threads currently belong to an access credential, not a mature person/device identity,
and expire after 24 hours. Forget removes active conversation data and invalidates
unexecuted linked proposals, not completed drafts/audit records or SQLite/WAL/backups.
Storage is not application-encrypted. The loopback development service must not be exposed
publicly. Use synthetic data pending the identity, retention and deployment gates.

The host must remain running for scans, conversation processing and opted-in routines.
No operating-system daemon, remote agent, cross-device sync or background ChatGPT task
was installed. Source archives remain inert; private data does not belong in this public repo.

## Continue from here

Fetch the actual branch head and read AGENTS.md, SESSION_HANDOFF.md, docs/CONVERSATIONS.md,
docs/ROADMAP.md and this receipt. Preserve the provisional shell. Next work: a held-out
model/retrieval evaluation, precise source-support checks, richer source-bound work and
reviewed typed memory. Do not claim the complete personal OS is finished or replace
this progress with another dashboard rebuild.
