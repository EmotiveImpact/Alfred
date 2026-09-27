# ALFRED execution roadmap, Knowledge Desk v0.4

26 September 2026. Acceptance gates, not delivery-time promises or a claim of completion.

## Current source of truth

Working branch: `feat/alfred-knowledge-desk-2026-09-26`.
Based on the actual Desk checkpoint `a43c4adcbc8ca9c8bf310443fc1fc33734bacd14`, which already
contained a browser interface, a local file connector and supervised automatic draft
execution. Older handoff text describing a backend without a UI was stale.

Preserve the earlier research and the 2,073 retained upstream files across eight pins.
They remain inert reference selections, not eight integrated runtimes. Main is not
silently merged, and no external deployment is part of this increment.

## Delivered product slices

| Slice | Implemented | Boundary |
|---|---|---|
| Core | Persistent local SQLite events/actions, scoped bearer checks, approval binding, outbox and result reconciliation | Local development only, not a mature identity or multi-tenant platform |
| Desk | Sign-in, briefing, evidence, acknowledgement, approvals, activity, sources and pause/resume | JSON sample project source; verified local draft, not external delivery |
| Knowledge | Read-only Markdown index, explicit reference graph, search, type filters, backlinks, source text and hashes | Not full Obsidian compatibility or a semantic world model |
| Retrieval | Bounded source packets with exact note lines/revisions/hashes | Keyword retrieval; no generated answer or model call |
| Automatic local work | Supervisor scans while the launched process lives and executes only approved local drafts | Not a cloud daemon, chat background task or cross-device scheduler |
| Evidence | Existing regression tests plus new knowledge/backend/browser acceptance | Check committed receipts and Actions for actual counts and outcomes |

## Next 1: one grounded conversation over these sources

The next customer-visible leap is not another repository collection. Add a contained,
replaceable reasoning adapter that receives the authorised source packet and answers
with citations. Keep its data egress explicit and opt-in. Store selected model/version,
source hashes, bounded usage and request/result status without logging secrets.

Acceptance: answerable and unanswerable questions; source update/deletion; conflicting
notes; no source in another workspace; prompt injection in retrieved notes; provider
outage; no fabricated citations; no automatic authority from model text. The system must
be able to say the source does not establish the answer.

Compare Hermes, nanobot and QwenPaw against identical fixtures and permissions. Select
one runtime only after results; do not give several executors overlapping credentials.
Jev remains a possible advisory relevance component, not a permission authority. No live
benchmark or provider connection is claimed yet. Existing issue #3 is the coordination point.

## Next 2: reliable memory lifecycle and private operation

Add mature device pairing/key rotation, source-specific grants, configurable retention,
export, correction and complete derived-data deletion accounting. Separate note identity
from path changes with explicit, reviewed identity metadata rather than guessing names.
Introduce an authenticated change feed and consistent revision indicators for every view.

Acceptance: revoke without restart, lost device, changed vault root, renamed files,
crash/rebuild, concurrent edits, stale evidence, quota/backpressure and backup restoration.
Evaluate application encryption with established tools before using sensitive notes.
Existing issue #2 remains open because these identity/lifecycle gaps are not complete.

## Next 3: scheduled routines with bounded authority

Turn the foreground supervisor into a deliberately installed service only when requested.
Add a routine registry with owning node, schedule/timezone, allowed sources/actions,
maximum run time, budget, concurrency and durable execution record. Deduplicate due work
across restarts. Start with map health and a sourced daily briefing, not arbitrary scripts.

Acceptance: crash during a run, duplicate scheduler instances, clock change, overlapping
runs, missing provider, revoked source and pause. This is the useful extension of MAPS's
Pulse idea. The current map checker is a command, not an already installed nightly job.

## Next 4: voice without losing the source and action discipline

Add visible push-to-talk to the shared session, then measure barge-in, actual playback,
acknowledgement and reconnection. Evaluate one transport, LiveKit provisionally with
Pipecat as an alternative. Keep speech provider replaceable. Review plugin/model/voice
licences separately and measure real hardware power/latency before ambient claims.

Acceptance: generated versus heard text, interruption during approval, provider loss,
noise, duplicate turns and zero repeated side effects after reconnect. Microphone is
currently disabled. Existing issue #4 is the coordination point.

## Next 5: one official account connector and a narrow external effect

Use an authorised test account and official API. Start read-only; then a reversible low-risk
write with exact parameter approval. Store capability-specific receipts and reconcile
ambiguous timeouts. Extend the same evidence UI rather than invent a separate action loop.

Acceptance: fresh versus stale data, upstream deletions, rate limits, revocation, unknown
outcomes, duplicate retries and privacy boundaries. The local draft's tested read-back
semantics do not prove exactly-once execution for an external service.

## Next 6: home/local devices and controlled team contexts

Evaluate a read-only Home Assistant bridge and a minimal explicit offline capability set.
Keep different device/source credentials separate. Add team/workspace membership with real
authorisation checks before shared knowledge. Prove deployment isolation rather than
calling a workspace label a security boundary.

## Next 7: specialist engines and operational exercises

Read the actual ENDSTATE and Noir interfaces before implementing an adapter. ENDSTATE
remains a separate analysis engine; its output must retain assumptions and remain labelled
as analysis/simulation. No current integration is inferred from a document link or graph edge.

Use fictional replay first, then independently reviewed non-critical exercises. No
unrestricted security control, covert recording or autonomous use-of-force authority.
Field reliability, alarm behaviour and safety need their own acceptance programme.

## Definition of the first usable personal intelligence

A person can ask about their authorised project, receive a sourced answer, notice a
meaningful change, inspect the evidence, approve an exact action and see an honest result
that survives interruption. They can correct memory, pause work and revoke access. The
current release supplies the local workspace and knowledge substrate; live reasoning,
voice and external execution remain the next build stages.
