# Jev, JVS Claw, QwenPaw and OpenSandbox

Research date: 25 September 2026. Three source repositories added, plus a product reference.
Evidence is primary documentation, pinned root licence inspection and byte-preserved source
selection. No upstream application or model was executed, and no comparative performance
benchmark was run. Copying a file does not mean it has been fully security-audited.

## 1. Resolve the names before designing around them

**Jev** is TypeSafe AI's structured decision-model offering, not Alibaba's assistant.
Its API accepts a state and named typed questions, returning structured answers. The
Choice primitive selects among supplied alternatives and provides their distribution;
the Score and Noul primitives serve other constrained evaluations. Primary references:
https://docs.typesafe.ai/introduction/quickstart
https://docs.typesafe.ai/api

**JVS Claw** is an Alibaba product reference. Alibaba's 26 May 2026 announcement describes
JVS Claw Teams as OpenClaw-based, with continuous cloud operation, organisation skill
distribution and central security management. The same announcement describes JVS Mobile
for cross-application automation. These are vendor-described capabilities, not ALFRED
test results. No official JVS source repository/licence was verified for copying in this
pass, so no JVS source is claimed as imported. Primary announcement:
https://www.alibabacloud.com/fr/press-room/alibaba-cloud-unveil-advanced-agentic-ai-ecosystem?_p_lc=1

**CoPaw** currently redirects to **QwenPaw**, which is the actual source reviewed/pinned.
**alibaba/OpenSandbox** currently resolves to **opensandbox-group/OpenSandbox**.
Record the canonical repository and commit, not just the older name.

## 2. Exact retained additions

| Source | Commit | Root licence | Retained files |
|---|---|---|---:|
| typesafe-ai/typesafe-sdk-python | 0ffd094c72ed9445223060b24ffd7a56aa781fb4 | MIT | 30 |
| agentscope-ai/QwenPaw | 3822ec7173d17cf37c8a02f51d3ed5628079e86e | Apache-2.0 | 53 |
| opensandbox-group/OpenSandbox | f3950db2499e8d572694bf9939e4bf985a2eab8a | Apache-2.0 | 44 |

Stored under third_party/extensions, separate from the previous five source selections.
The original 1,946 files are unchanged. New 127 files bring the combined retained count
to 2,073 across eight repositories. These are focused UTF-8 source/documentation selections,
not complete forks, installed dependencies or model weights. Legal/notice files were
retained by the importer, and all copied files have SHA-256/Git-blob hashes and exclusion
records. See extension.lock.json and EXTENSION_RECEIPT.json for exact evidence.

Import execution: https://github.com/EmotiveImpact/Alfred/actions/runs/36192336632
That completed run reported zero failures and verified both the original and new archives.

The TypeSafe SDK LICENSE contains a literal copyright placeholder. It was preserved
verbatim, not silently repaired or assigned to ALFRED. Resolve that attribution before
product redistribution. A root licence alone does not clear models, voices, datasets,
dependencies, logos, trademarks or every transitive component. No new umbrella licence
has been applied to ALFRED-original code.

## 3. Jev: useful as an advisory decision component

Proposed role: help classify low-risk relevance or route a task to a suitable specialist
before invoking a more expensive reasoning workflow. This is an experiment, not an assumed
latency/cost win. Compare against deterministic rules and the selected general model on
identical held-out synthetic events. Do not use typed output as proof of correctness.

TypeSafe describes confidence as a statistic derived from the returned distribution.
ALFRED must retain that meaning rather than relabelling it as measured factual accuracy,
source reliability or permission to act. A confident classification cannot grant access
to a different workspace. Primary explanation: https://docs.typesafe.ai/confidence

Implemented now: an original effect-free wire-contract helper in alfred/jev.py. It builds
a minimised objective/event request, pins the official example identifier jev-1.13.0,
validates a bounded Choice response and returns advisory metadata only. It does not call
the provider or include Jev's model. Preparing a payload with a trusted boolean is not a
production egress-authorisation service. Live transport requires a separate gate.

Evaluate in shadow mode first: retain suggested route, expected label, model version,
latency and input provenance, but do not let it change alerts or actions. Measure false
interruptions and missed relevant changes. Add no production thresholds merely because
a vendor example uses a particular confidence number.

## 4. QwenPaw: a serious runtime comparison, not just another name

Its current README describes local/cloud deployment, skills/plugins, several interaction
channels, persistent layered memory, multi-agent work and explicit governance/sandbox
components. These features overlap with ALFRED's proposed design; we should neither ignore
them nor claim that ALFRED invented the underlying concepts. Primary source:
https://github.com/agentscope-ai/QwenPaw

Design implication: add QwenPaw to the same controlled comparison as Hermes and nanobot.
Assess the amount of integration required, lifecycle semantics, memory correction/export,
authority boundaries, cancellation and recovery. Choose one primary runtime, not three
executors with overlapping credentials. Source selected for reading includes relevant
Python implementation paths plus licences/notices; the selection is not a working package.

The current original ALFRED service is not built on QwenPaw. The decision to adapt specific
modules or use it as a runtime remains contingent on actual tests and dependency review.
Maintain replaceable boundaries: authorised evidence in, typed proposals out, connector
secrets and approvals outside the unconstrained runtime.

## 5. OpenSandbox: evaluate isolation separately from intelligence

OpenSandbox provides a sandbox infrastructure approach with lifecycle and execution APIs.
Its public documentation describes the intended execution environment and integration
surface. Primary references:
https://github.com/opensandbox-group/OpenSandbox
https://open-sandbox.ai/

Proposed role: a contained environment for an agent's coding/browser/tool workloads, not
ALFRED's memory store or permission authority. An infrastructure service that can execute
commands must not automatically inherit the user's personal credentials or host access.

Before adopting it, test filesystem mounts, outbound networking, process cleanup, resource
limits, TTL/cancellation, restart and separation between workspaces. Record actual runtime
configuration and hostile test results. No OpenSandbox container, daemon or SDK was run in
this delivery, so ALFRED sandboxing is not claimed as implemented.

## 6. Composition decision

ALFRED owns the persistent evidence model, attention policy, identity/authority rules,
approval binding and result record. A selected runtime proposes; Jev may supply constrained
advice; OpenSandbox may contain an execution environment; connectors carry out only their
authorised effects. These are distinct jobs, not interchangeable products to merge wholesale.

Do not make research accumulation the product. The next customer-visible proof is an
inspectable briefing and approval interface, one read-only source and one reliably recorded
limited action. Every reused component must make that loop better in a measured way.
