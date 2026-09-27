# ALFRED product brief v0.1

Status: proposed product direction and acceptance criteria, 25 September 2026.
This document describes the intended product, not already implemented functionality.

## 1. The problem is broken continuity, not a shortage of chatbots

A person works across messages, schedules, documents, people, places and devices. They
must repeatedly reconstruct context, notice changes, decide what matters, open the right
application and confirm whether an action really happened. A conversational interface
alone does not remove that coordination burden.

Our product hypothesis: a persistent, authorised intelligence can reduce this burden
while leaving the person in control. It should remember appropriate context, maintain
awareness of relevant changes, explain evidence and coordinate accountable action.
This hypothesis needs user and task evaluation; research does not establish demand,
commercial superiority or an already solved engineering problem.

**Promise to test:** stay focused on your work; ALFRED keeps track of what you need to
know and carries out only what you have actually authorised.

## 2. One identity, several explicitly separated contexts

Personal: diary, reminders, household state, personal knowledge and preferences.
Work: project decisions, document changes, approved communications and outstanding work.
Home: authorised local devices and low-risk automations.
Operational: an explicitly started, time-bounded team/client workspace with role-limited
information, clear source status and strict records. Initially simulation only.
Private: stop ambient capture, pause proactive processing and show what remains active.
Offline: a capability state across the other modes, not permission to invent fresh data.

The product should feel continuous across phone, desk and ear without making their
security permissions identical. A user's personal memory is not a team's shared memory.
A compromised device must not grant access to every other context.

## 3. First user and first useful loop

Start with a founder/producer managing a real project. This is a tractable first context
for comparing assistance with a manual workflow. Do not begin with operational safety
claims or universal device control.

Example intended experience:
1. The user selects the project, approved calendar/documents and limited sources.
2. ALFRED presents a sourced briefing with current decisions and unresolved confirmations.
3. A material schedule/document change arrives through a connector.
4. ALFRED checks freshness, provenance, scope and the user's notification preferences.
5. It queues or presents the change and offers a tightly specified next action.
6. The user reviews the exact recipient/content or other relevant parameters.
7. A policy-checked connector acts, returns a receipt and supports result reconciliation.
8. ALFRED reports the actual state, including unknown or partially completed outcomes.

A parallel synthetic operational replay can exercise briefing versions, missing
acknowledgements, stale device status and connection failure without anyone depending
on it for protection. Reuse the same contracts, not the same private data.

## 4. Jobs to be done

Orient me: what is current, what changed and what is not confirmed?
Remember correctly: retrieve decisions with their source, date, scope and corrections.
Relieve attention: surface relevant exceptions without narrating every event.
Act carefully: propose, obtain authority, execute and reconcile the result.
Coordinate: distribute approved updates to the people entitled to receive them.
Recover: make disconnection, uncertainty, expiry and partial failure visible.
Explain: why did you interrupt, what evidence supports this, and what did you actually do?

## 5. What makes ALFRED original

The candidate differentiation is not a British voice, an animated orb or a large list
of tools. It is the combination of:
- An objective/context model with explicit information boundaries and provenance.
- An attention policy that can explain its interruptions and stay usefully quiet.
- A common authority and action record across replaceable agents and connectors.
- Personal continuity with controlled team cooperation, not universal shared memory.
- Explicit separation of observation, report, analysis, prediction and simulation.

These are proposed advantages to demonstrate. Several upstream projects already tackle
parts of memory, approvals, scheduling and device access; do not claim we invented them.

## 6. v0.1 scope and exclusions

Included now: research, pinned inert source selections, contract replay, unit tests.
Next deliverable: durable local context/event service, authenticated local API, read-only
project connector, approval interface and one sandboxed runtime adapter.
Then: one voice pipeline, one low-risk write connector, restart/retry tests and usage
measurement. Native mobile background capture is a separate hardware/platform experiment.

Excluded from the first live release: arbitrary shell/browser authority, banking,
unattended security-system changes, covert ambient recording, face/person tracking,
weapon control, autonomous use of force and claims of mission-critical availability.
No custom foundation-model training, bespoke earpiece or distributed microservice estate
is required to validate the initial experience.

## 7. Attention is a product contract

Every alert must carry an event/evidence ID, current scope, source and observation time,
freshness window, evidence basis and a reason it was routed to speech/display/digest.
A source's authenticated identity does not prove its statements are true. Avoid invented
confidence scores. Conflicting current reports require reconciliation, not silent overwrite.

Keep three separate questions: did ALFRED generate a statement, did the device play it,
and did the person acknowledge it? Do not mark information as known merely because
speech was queued. Barge-in must update playback state without pretending to undo actions.

Explicit user-approved high-priority rules remain deterministic. Model ranking may assist
with ordinary relevance but cannot grant permissions or silently change critical rules.

## 8. Memory promises and lifecycle

Working context: bounded current session with a clear expiry.
Evidence/history: source-linked events, corrections and decision records.
Preferences: editable user-approved facts rather than inferred immutable identity.
Procedures: reviewed workflows, not automatically executable lessons from arbitrary text.
Operational context: purpose-bound retention and access, separate from personal memories.

A memory needs provenance, scope, access policy, retention, correction state and deletion
behaviour. Deleting a source must address derived summaries/index entries and backups
according to a documented policy. A vector index is a retrieval aid, not the authority
for identity, permissions or current device state.

## 9. Experience and acceptance gates

The interface needs a conversation, a current briefing, an attention inbox, an action
ledger, evidence drill-down, context switcher and visible listening/connectivity state.
Voice must be optional; the same approval must be reviewable on screen.

Measure task completion, missed relevant changes, unnecessary interruptions, evidence
errors, stale statements, correct result reporting, recovery success and user trust.
Report denominators, scenarios, model versions and failure cases. No arbitrary '99.9%'
marketing target, assumed latency, battery figure or cost claim is established here.

Before a pilot, every restricted-action test must be denied without an actual grant;
every simulated/derived fact must remain labelled; reconnection must reconcile rather
than duplicate work; users must be able to inspect, pause and revoke the system.
Field deployment requires a separate independently reviewed acceptance process.

## 10. Ownership questions left open

Keep ALFRED as the product identity. Emotive Impact versus Black State ownership,
commercial licensing, approved provider/data residency, first target operating system,
budget and initial users remain explicit decisions. These do not block building and
testing the effect-free foundation. They do block pretending a production rollout is
already authorised.
