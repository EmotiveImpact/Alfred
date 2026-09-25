# ALFRED execution roadmap v0.2

25 September 2026. This roadmap supersedes the status claims in the foundation build plan,
while retaining its product direction. Milestones are acceptance gates, not time estimates.

## Objective

Build one persistent personal intelligence that understands authorised context, identifies
useful changes and follows through on approved work. The first usable product must deliver
that loop, not simply display a dramatic dashboard or wrap another agent in a new name.

The target remains personal, work, home and authorised operational assistance. Start with
a founder/producer's project: briefing, changed information, an exact next action, approval
and an honest result. Use synthetic operational scenarios to test the same contracts.

## Current position

| Workstream | Actual state | What remains |
|---|---|---|
| Research and source preservation | Original 18-repository review plus Jev SDK, QwenPaw and OpenSandbox; 2,073 retained files from eight pins | Controlled runtime comparisons, full dependency/model/asset licence checks |
| Persistent core | Runnable local SQLite event/action service, bearer lookup and static roles | Mature identity/key lifecycle, retention, source corrections and observability |
| Approved effects | Local message.draft row, durable queue, result read-back and crash reconciliation | First separately approved external connector and its own idempotency strategy |
| Jev | Offline typed request/response experiment | Authenticated transport, authorised egress, shadow evaluation and measured benefit |
| Interface | CLI and loopback JSON API | Evidence/approval web UI, accessible interaction and device pairing |
| Reasoning and voice | Not connected | One contained runtime, one provider, one voice pipeline |
| Home/field/ENDSTATE/Noir | Target architecture and synthetic contracts | Actual API review, test deployments and separate operational acceptance |

No overall percentage is assigned: a passed database test is not equivalent to usable
voice, effective reasoning or field reliability. This is a local engineering alpha.

## Milestone 1: complete the local foundation

**Delivered in this increment:** committed SQLite schema, persisted source events,
server-resolved scope/role, token expiry/revocation, exact-parameter approvals,
transactional outbox insertion, single-claim leases, one idempotent local draft effect,
actual read-back proof, explicit uncertain outcomes, real HTTP tests and process-exit tests.

**Still required before a wider pilot:** separate person/device identity from credentials;
rotate keys without orphaning historical actions; per-capability grants instead of one
static role rule; immutable/auditable policy versions; source corrections and revocations;
retention/deletion/export; snapshot/backup recovery; health/backpressure and paging.
Uncertain actions need a deliberate reviewed recovery interface, not automatic resend.

Acceptance: restart and crash tests continue to pass; revoked access cannot return data
or create effects; identity rotation preserves appropriate records; lost leases cannot
commit under stale authority; deletion/retention behaves as documented; errors are visible.

Scope owner: Track A, issue #2. Do not introduce a public deployment as part of this gate.

## Milestone 2: the first usable Alfred desktop experience

Build a small interface over the authenticated service: current briefing, changes inbox,
evidence detail, exact approval card, action history, source health and explicit pause.
The existing API rejects browser Origin requests; a reviewed session/CSRF/Origin design
must replace that restriction rather than disabling it indiscriminately.

Add ONE read-only calendar or project-document connector on an explicitly authorised
test account. Preserve source identity, observation time, revision, link and deletion.
Do not ingest every account or historical message as a shortcut to personalisation.

Acceptance: a tester selects a workspace, sees current information, receives a relevant
change, examines its source, approves a local draft and sees the result after restart.
A reader cannot approve; another workspace cannot see the content. All examples remain
synthetic until real-account use and data retention are explicitly authorised.

This is the next customer-visible increment, developed alongside the remaining core
lifecycle work. Do not postpone all usability until the entire end-state architecture exists.

## Milestone 3: one reasoning runtime, evaluated fairly

Compare Hermes, nanobot and QwenPaw using identical synthetic scenarios, model budgets,
connector mocks and ALFRED authority contracts. Keep OpenClaw as a gateway reference unless
specific evidence justifies changing the candidate set. Choose ONE primary runtime.

A runtime receives scoped evidence and returns a bounded typed proposal. It does not
receive the credentials that would allow it to bypass ALFRED's connector gate. Set tool
count, run duration, token budget, filesystem and egress limits. Persist model/prompt/runtime
versions in evaluation records. Default to official service APIs rather than browser control.

Use a separate disposable environment to evaluate OpenSandbox for model/agent/browser
workloads. Test denied filesystem paths, network destinations, mounts, escape attempts,
TTL/termination and restart cleanup. No host Docker socket or personal credential mount.
Do not equate the word sandbox or a container process with demonstrated isolation.

Acceptance: common briefing/change/action tasks, malicious retrieved instructions,
wrong-workspace requests, changed approvals, cancellation, timeout and provider failure
are evaluated with actual outputs. Publish failed cases and adoption/rejection reasoning.
The SDKs/fixtures in this repository do not constitute that benchmark.

Scope owner: Track B, issue #3, coordinated with Track A's contract changes.

## Milestone 4: useful intelligence without unnecessary interruptions

Add objective-aware relevance classification in shadow mode: log a model's suggested route
without letting it control notifications or actions. Compare Jev with a simple deterministic
baseline and the selected general model. Jev's typed decisions might reduce overhead, but
no latency, cost or quality advantage is assumed before measurement.

Measure missed relevant changes, unnecessary alerts, decision agreement, uncertainty,
latency and total cost on the same held-out scenarios. Keep critical deterministic rules
and permission checks independent. A high model confidence must never become authorisation
or proof that a statement is factually true.

Acceptance: explicit scoped egress, revocable provider credentials, bounded context,
versioned model selection, failure fallback and evidence of better user outcomes. Only then
promote limited low-risk relevance routing beyond shadow mode. No live Jev call is enabled
by the current wire-contract experiment.

## Milestone 5: voice and one real low-risk connector

Use one voice transport, with LiveKit provisionally and Pipecat as a comparison option.
Voice/text share one session. Start with deliberate push-to-talk, visible microphone state,
no persistent raw audio and on-screen approval. Generated, played and acknowledged speech
are different states. Interrupting speech does not undo a dispatched action.

Introduce one reversible low-risk external effect on a test account. Define that service's
idempotency key, receipt and verification semantics. A local SQLite draft is not evidence
that email delivery or physical state verification is already solved.

Acceptance: real audio interruption/reconnect/noise tests on named hardware; exact approval
of destination/content; no duplicate effect after uncertain timeout; manual fallback; clear
source/provider loss. Publish latency components and device resource measurements.

Scope owner: Track C, issue #4 for voice, with Track A owning action semantics.

## Milestone 6: personal continuity, devices and controlled team use

Add editable source-linked memory with correction/deletion and separate personal/work/client
vault policies. Evaluate a read-only Home Assistant bridge before harmless reversible device
commands. Add an encrypted, bounded offline cache and explicit source freshness status.

Native phone/headset background behaviour needs actual platform, microphone, battery,
thermal and connectivity experiments. A browser demo is not an always-on mobile product.
Team workspaces receive role-appropriate shared information, not everyone's private memory.

Acceptance: inspectable memory, deletion of derived indexes, revocation during disconnection,
reconnect reconciliation, source freshness display, bounded queues and measured hardware
behaviour. Choose a sustainable deployment model from the evidence, not assumed cloud cost.

## Milestone 7: operational and specialist integrations

Keep expanding synthetic briefing revision, missing acknowledgement, contradictory report,
source loss and team-role tests. Read actual ENDSTATE/Noir APIs, identity models and current
capabilities before implementing any adapter. Neither repository was modified here.

ENDSTATE remains a separate analysis engine, not an observer. Its assumptions/simulations
must remain labelled. Preserve Noir's distinction between device receipt and human
acknowledgement. Begin only with supervised non-critical exercises; any safety-reliant
field deployment needs a separate security, privacy and operational acceptance process.
No autonomous use-of-force capability or unrestricted control over security systems.

## Parallel execution rules

Track A builds the durable product substrate and usable evidence loop. Track B measures
existing runtimes and sandbox options in isolation. Track C builds voice against the agreed
session contract. Each uses a separate branch and small PR, with exact source pins and
actual test output. Work packages are not claims that autonomous agents are running.

Changes to context, action, approval and result contracts require coordinated review.
No shared credential pool across independent agent loops. Preserve upstream archives.
No force pushes, silent merging, automatic production deployment or unrequested live data.

## Definition of success for the next demonstrable release

A user can open Alfred, select an authorised project, ask what changed, inspect the evidence,
review a proposed response and approve a limited action. Alfred retains the state after a
restart, reports uncertainty instead of inventing success, and lets the user pause or revoke
access. Prove this small complete experience before expanding the integration count.
