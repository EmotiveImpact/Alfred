# ALFRED architecture v0.1

Status: proposed architecture; only the small offline contracts in alfred/ are implemented.

## 1. Own the control layer; replace the model and runtime

The model proposes. ALFRED assembles authorised context. An independent policy service
decides. A connector executes. A ledger records what was attempted and what evidence
supports the outcome. None of these roles should disappear into one enormous prompt.

```text
User / paired device
        |
Session API and voice/text interface
        |
ALFRED context + attention + conversation coordinator
        |                     |
Evidence store            Model / agent adapter
        |                     |
Event ingress          typed action proposal only
        |                     |
Authenticated source    Authority + approval service
                              |
                        durable action outbox
                              |
                         connector gateway
                              |
                     receipt + result reconciliation
```

Begin as a modular Python service plus a browser interface, a local database and isolated
connector/runtime workers. This is a deployment proposal, not a mandate to implement all
modules as network services. Separate hostile workloads with actual process/container
boundaries; a Python class or workspace field is not a security boundary.

## 2. Runtime selection

Use one runtime behind a narrow adapter for the first integration experiment. Hermes is
a provisional first candidate because its documented memory, skills and gateway features
align with continuity, and the inspected Jarvis HUD shows a related session/voice pattern.
Compare nanobot as the smaller architectural baseline. Retain OpenClaw gateway/security
material as another reference, not as a second overlapping authority system.

Do not combine three independent schedulers, memory stores and tool executors with the
same credentials. A runtime adapter receives redacted scoped context and returns typed
proposals, not a root shell. Its subprocess must not possess the connector credentials
needed to bypass ALFRED policy. Runtime choice is gated on actual sandbox and failure tests.
See research/LANDSCAPE.md for evidence and caveats.

## 3. Data and event contracts

Proposed persisted envelope: schema version, event ID, source ID, authenticated principal,
workspace/session, subject and kind, observation time, receipt time, expiry, evidence
basis, source reference/content hash, correction/replacement links and correlation ID.
The current prototype implements only a subset: inspect Evidence rather than assuming
this whole schema exists.

Separate facts/events from materialised current state. Keep source observation time when
messages arrive late. Equal timestamps with conflicting reports require reconciliation.
Clock skew must be measured and handled explicitly; freshness is not time-since-download.
Deduplicate by scoped identity plus payload identity, not a globally reused message ID.
Bound queues, payloads, replay state and retention. A full queue must produce health
telemetry and backpressure rather than silent loss or an unbounded memory allocation.

Prototype storage is in-memory. Next: SQLite for a single local node with transactional
outbox and schema migrations. Use Postgres when multiple concurrent users/nodes require
it; evaluate row-level policies plus independent service checks. Do not claim workspace
labels alone deliver tenant isolation. Add full-text retrieval first; introduce vector
retrieval only when it improves measured tasks. No separate graph database is required
to represent initial entities/relationships in relational tables.

## 4. Ingress and attention

Connectors verify their upstream transport, normalise observations and preserve provenance.
Ingested text, tool descriptions, email bodies and web content are data, not instructions.
First run deterministic scope/freshness/duplicate/health checks. Then compare the event
with authorised objectives, responsibility and user-approved notification rules. A model
may classify low-risk relevance within a fixed budget; unknown or conflicting evidence
is routed for review rather than inflated into certainty.

Speech, display, digest, suppress and reject are different outcomes. Every route has a
reason. Generated speech, successful playback and human acknowledgement are separate
records. Reserve critical operational alerting for tested systems and explicit rules;
ALFRED v0.1 is not an emergency alarm.

## 5. Authority and execution

Proposed action: immutable actor, workspace, capability, target, exact parameters,
preconditions, expiry, idempotency key and approval hash. The authenticated device/session
is bound outside model output. A capability registry specifies schema, effects, allowed
principals, data egress, rate/budget constraints and verification strategy.

Approve only the exact proposal. Recheck grant, expiry and preconditions at dispatch.
A changed recipient, amount or parameter invalidates previous approval. The action
outbox and result ledger must be committed transactionally. Retries require a documented
idempotency strategy for that external service, not a universal 'exactly once' claim.
After an ambiguous timeout query status where supported; do not blindly repeat a side
effect. Some effects are irreversible. Cancellation stops future work, not completed work.

Receipt means acceptance/delivery. Verification means capability-specific evidence of
the result. A read-back from the same device is not independent physical confirmation.
For a lock, 'device reports locked' is more accurate than 'the house is safe'. Some
capabilities can never support a strong verified state; preserve unknown/partial states.

## 6. Interfaces and voice

First prove text + push-to-talk. Candidate transport: LiveKit Agents, with Pipecat a
comparison option, not a parallel production dependency. Keep the voice transport,
turn detection, speech model, conversation session and tool execution separable.
OpenAI Realtime is one possible speech/model adapter, not ALFRED's identity or sole route.
Official reference: https://developers.openai.com/api/docs/guides/realtime

Maintain turn IDs, cancellation generations, input/output audio buffers, playback offsets,
acknowledgement and reconnect state. Do not store a response as heard when barge-in stopped
playback. Do not auto-cancel or repeat an already dispatched action when voice disconnects.
Never grant authority solely from an overheard command or a voice likeness.

Long-lived edge agents need an appropriate process host. A static site or request/response
function alone does not provide a continuously running microphone/event service. A desktop
or home node can host local processing; native mobile background behaviour must be proven
on actual devices. Android microphone foreground services have permission and background
start restrictions: https://developer.android.com/develop/background-work/services/fgs/service-types
No iOS/Android always-on battery or entitlement guarantee is made here.

## 7. Local/cloud split

Local node: visible capture control, optional wake detection, bounded ephemeral audio,
paired-device identity, encrypted cache, source health and a small approved offline
capability set. Cloud: optional heavier reasoning, scoped retrieval and synchronisation.
The deployment must be useful and honest when cloud access disappears, not silently
continue presenting stale cached information as live.

Explicit listening does not imply recording retention or cloud upload. Those are separate
permissions. Define provider egress per workspace and exclude credentials from model
context. Local inference can reduce egress but is not automatically fast, secure or free;
measure CPU, memory, power, accuracy and thermal behaviour on the target device.

## 8. Device and service integration

Use official APIs before browser control. Home Assistant is a candidate device gateway,
not a reason to duplicate thousands of device integrations. Begin with read-only state
and one harmless reversible action in a test environment. Its WebSocket API supports
state/event interaction: https://developers.home-assistant.io/docs/api/websocket/

MCP is an interoperability mechanism, not a trust guarantee. ALFRED still validates
server identity, tool schema, effects, destination and grants. Do not pass upstream
credentials through indiscriminately; respect audience and consent boundaries. Reference:
https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices

## 9. ENDSTATE, Noir and teams

ENDSTATE remains an independent analysis/planning engine and 8BALL remains a separate
client. Proposed request includes objective, assumptions, scoped evidence and constraints;
proposed response includes alternatives, dependencies, uncertainty and citations. This
is not an existing API contract. Analyse actual engine capabilities before implementing.
Simulation output is never promoted to a live observation.

Noir is an adjacent Black State engineering project, not an established live operational
record service in this delivery. Future integration must read its actual API/auth/version
and preserve its receipt versus operator-acknowledgement semantics. No other repository
was changed for ALFRED.

Team cooperation uses a role-limited shared workspace plus separate personal workspaces.
The UI can feel like one Alfred per person without giving every instance unrestricted
access to all team data. Multi-tenant deployments require separate credential and runtime
boundaries, not merely prompts. OpenClaw itself documents its one-trust-boundary design:
https://docs.openclaw.ai/gateway/security

## 10. Observability, costs and upgrades

Record route reasons, evidence age, action-state changes, latency components, queue depth,
retries and connection state without default raw transcripts or secrets. Redaction is
not a substitute for data minimisation. Provide pause, revoke, export and health controls.

Cost model to measure: processed speech duration + model input/output tokens + generated
speech + storage/egress + continuously running compute. Apply session/workspace budgets,
maximum tool depth, timeouts and provider failover policies. No current price assumptions
or cost savings have been benchmarked in this branch.

Pin deployments and adapter schemas, test upgrades against saved synthetic scenarios,
review licence changes and support rollback. Preserve the original source snapshot while
placing reviewed modifications outside quarantine with explicit attribution.
