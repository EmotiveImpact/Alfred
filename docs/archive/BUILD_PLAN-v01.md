# ALFRED implementation programme

25 September 2026. Milestones are acceptance gates, not delivery-time promises.
Read research/VALIDATION.md before interpreting the current prototype's capabilities.

## Completed foundation scope

Research and source/licence inspection; reproducible inert source import; original
in-memory evidence/attention/action contracts; 60 local unit tests; synthetic replay.
Actual remote imports and CI results must be checked in the receipt and Actions runs.
No complete assistant, live integration, UI, deployment or field validation is claimed.

## PR 1: durable local core and authenticated API

Build SQLite migrations, transactional event journal/outbox, bounded retention and
restart recovery. Authenticate a paired development client and resolve scope/actor on
the server. Add separate source registries and capability policy, not caller-provided
booleans as authority. Introduce correction/revision links and health events.

Acceptance: crash/restart replay, duplicate/collision handling, clock-skew tests,
wrong-scope denial, revoked/expired grant rejection and exact action approval binding.
No live side effects until the service can preserve intent and outcome across restart.

## PR 2: one project connector and evidence UI

Implement one read-only calendar or document connector using an official API and explicit
test-account consent. Provide current briefing, changes inbox, evidence drill-down,
connection status, workspace switch and audit view. Treat external text as untrusted.

Acceptance: source timestamp and link visible, missing permissions handled honestly,
changed/deleted content reconciled, forbidden workspace unavailable, private data not
written to logs or repository. Build a manual baseline for usefulness comparison.

## PR 3: one contained agent runtime

Compare the pinned Hermes candidate with nanobot against the same synthetic tasks. Choose
one, or reject both with evidence. Expose only a narrow context/proposal contract. Runtime
cannot read connector secrets or invoke effects outside the gateway. Limit tokens,
iterations, time, filesystem and network. Do not enable arbitrary shell tools.

Acceptance: malicious document/tool response, forged authority, wrong-context retrieval,
provider outage, tool timeout and cancelled session tests. Publish model/dependency pins,
licence inventory, result traces and failure cases. No invented benchmark scores.

## PR 4: one voice transport

Prototype LiveKit, comparing Pipecat only where there is a concrete unmet requirement.
Text and voice share session state; transport is independent of model/provider choice.
Start with push-to-talk, visible capture state, no retained raw audio and explicit stop.

Acceptance: interrupted playback, echo/noise tests, turn ownership, reconnect, source
loss and speech/action cancellation distinction. Measure end-to-end latency components
and actual target-device resource use. Do not claim native always-on mobile support from
a browser demo. Test background constraints separately.

## PR 5: one low-risk action with real result reconciliation

Use a test account and harmless reversible capability. Present exact parameters, record
approval, dispatch via outbox, retain receipt and verify the appropriate service state.
Add failure, partial outcome, retry and user cancellation UI.

Acceptance: no duplicate side effect after crash/timeout; changed proposal invalidates
approval; revoked grant blocks dispatch; unknown outcome remains unknown. A physical
safety statement is never inferred solely from a service accepting a command.

## PR 6: home node and privacy/offline contract

Add a read-only Home Assistant bridge, optional local processing and encrypted bounded
cache. Implement capture pause and source revocation. Keep personal/home/work credentials
separate. Demonstrate useful offline scope with honest stale/source status.

Acceptance: lost-cloud/reconnect exercises, cache expiry and deletion, key revocation,
limited local commands, health/backpressure and hardware power/resource measurements.
Custom hardware is not needed before a software prototype meets these gates.

## PR 7: operational simulator and specialist contracts

Expand synthetic scenarios for briefing revisions, conflicting reports, acknowledgement,
source loss and restricted team roles. Review actual ENDSTATE/Noir interfaces only under
separate authorised access. Implement mocks first; keep analysis and simulation labelled.

Acceptance: personal/client separation, least-privilege distribution, no silent promotion
of simulation to fact, no automatic operational control and explicit human review. Live
field use requires a separate independent safety/security acceptance programme.

## Independent agent workstreams

These are prepared work packages, not a claim that autonomous reasoning agents have
already been launched. The GitHub import workflow is a deterministic copying/verification
worker, not a second research model.

**Track A, original core:** own alfred/, tests/ and the durable API proposal. Input:
PRODUCT_BRIEF, ARCHITECTURE and existing contracts. Output: small reviewed PR with crash,
authentication and ledger tests. Do not change third_party snapshots or choose voice UI.

**Track B, upstream evaluation:** own research/, reviewed adapter experiments and licence
records. Inspect exact pinned files, compare one runtime at a time in an isolated test
environment with no personal credentials. Output: adoption/rejection evidence and a typed
adapter proposal. Do not mutate core contracts or execute code from quarantine directly.

**Track C, voice:** own a separate voice experiment once the session contract is approved.
Output: interruption/playback/reconnect evidence on named hardware with documented model
and plugin licences. No live operational recording or hidden background microphone.

Every track starts from the current remote branch, uses a separate branch and records
its source commit. No force pushes, silent merges or conflicting authority systems.
Coordination point: reviewed evidence, proposal, session and result contracts.

## Definition of a useful first ALFRED

A person can inspect today's authorised project context, receive one meaningful sourced
change, review an exact action, approve it and see what actually happened. They can pause,
revoke access and recover from disconnection. Demonstrate that before adding twenty
connectors, an ambient microphone or a spectacular 'runs everything' claim.
