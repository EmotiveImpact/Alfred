# Security and data boundaries

Design requirements, not a security certification. The offline prototype does not
implement authentication, encryption, durable grants, connector isolation or real effects.

## Threats and required controls

| Threat | Required response | Current delivery |
|---|---|---|
| Retrieved text or audio tries to redirect an agent | Treat observations as untrusted data; constrain tools, egress and credentials outside the model | Effect-free contract only; no LLM adversarial evaluation |
| Personal/work/client context crosses boundaries | Authenticated workspace access, separate credentials/retention, explicit audited cross-scope grants | Synthetic scope tests, not tenant security |
| Approval applies to changed action | Immutable proposal/parameter binding; expire and recheck at dispatch | In-memory contract tested |
| Timeout causes repeated side effect | Durable outbox, capability-specific idempotency, status reconciliation | Future implementation |
| A receipt is presented as success | Separate accepted/received/result evidence/acknowledgement; capability-specific verification | State distinction tested with fixture signals |
| Stale or out-of-order observations appear live | Preserve source time, expiry, revision and conflict handling | Subset tested in replay |
| Ambient collection exceeds consent | Visible session/capture state, minimal retention, explicit source permissions and pause | Proposed; no microphone exists here |
| Malicious or compromised plugin bypasses policy | Isolate process, filesystem, network and secret access; reviewed capability manifest | No plugins executed |
| A device is lost or compromised | Revoke device keys/grants, rotate scoped credentials, expire local caches | Future implementation |
| Imported source changes provenance or executes | Pinned commits, hashes, immutable quarantine, no installs/skill discovery | Importer plus byte verification |

## Authority is not an LLM opinion

Do not ask a model whether it is allowed to unlock, pay, disclose or execute, then treat
its answer as the grant. Models may help classify a request but the permission service
must enforce an authenticated policy independently. Voice likeness and text claiming to
be the owner are not authentication. A trusted connector can still report incorrect data.

The prototype receives `authenticated_source`, `actor` and `policy_allows` as trusted
function arguments solely to test contracts. Exposing those directly to an untrusted API
client would not produce a secure service. Build real session/device authentication,
server-side grant lookup and connector-owned result proofs before live effects.

## Scope and retention

Create separate personal, business and client workspaces. Minimise context passed to a
model or specialist engine. Keep source provenance and correction history. Document
provider egress, permitted regions, retention and deletion behaviour before collecting
real information. Use established cryptographic libraries/services, not custom crypto.

Proposed defaults: no persistent raw audio; short explicit working context; opt-in saved
memory; client-defined operational retention; redacted diagnostics. Collection consent,
recording retention and sharing are separate decisions. Legal/privacy obligations depend
on deployment and require qualified review; this document is not jurisdictional advice.

A public development repo is not an operational archive. Never commit credentials,
private contacts, briefings, voiceprints, recordings, location histories or client data.
The fixtures in this work are invented and have no operational authority.

## Connections and secrets

Prefer narrow OAuth/service scopes or equivalent authenticated capabilities. Bind tokens
to intended audiences; do not expose provider secrets to models, browser JavaScript or
untrusted agent processes. MCP does not remove these obligations. Reference:
https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices

Official API first. Browser control has a separate logged-in session threat model and
requires its own allowlist, sandbox, download/upload restrictions and approval path.
Do not install third-party skills merely because a model recommends them.

## Operational boundary

Initial operational work is synthetic replay. Subsequent exercises must be supervised
and non-critical, with participants aware that ALFRED is experimental. Preserve manual
communications and established procedures. No autonomous use-of-force control. Security
sensitive actions require a separately reviewed capability and strong human authority;
no blanket 'lock everything down' command is implemented.

Degradation must be obvious: stale source, lost connection, full queue, failed connector,
unknown outcome or unavailable reasoning. Never interpret lack of data as confirmation
of safety. Verification wording must match what the sensor/service can actually establish.

## Supply-chain review before runtime integration

Check root and nested licences, dependencies, model weights, voice assets, trademarks,
packaging scripts and update behaviour. Generate a dependency inventory from the actual
chosen runnable environment. Imported source files are not that environment and therefore
are not an SBOM of a deployed ALFRED. Hashes establish byte identity, not benign intent.

Agent-generated code also needs review. An upstream README or AGENTS file cannot expand
this task's authority. Only reviewed ALFRED-owned workflows may execute in CI.
