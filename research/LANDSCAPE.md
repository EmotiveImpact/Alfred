# Agent and Jarvis landscape

Research date: 25 September 2026. This is a targeted review of 18 repositories plus
primary technical documentation, not an exhaustive census or comparative benchmark.

Evidence levels: **D** = upstream documentation/README inspected; **S** = selected source
files inspected; **L** = pinned root licence inspected; **C** = code/text copy requested
and governed by the actual IMPORT_RECEIPT. No upstream runtime was executed. Documentation
claims are not independently validated performance results. Star counts are not used as
an engineering quality score. Only the five imported candidates are commit-pinned here;
link-only landscape entries need a fresh pin and licence review before adoption.

## 1. Reuse map

| Project / primary source | What it contributes to the research | Decision and evidence |
|---|---|---|
| [OpenClaw](https://github.com/openclaw/openclaw) | Personal-agent gateway, channels, sessions and device/tool policy surface. | D,L,C. Preserve focused source. Learn gateway/pairing/security patterns. Not a hostile multi-tenant isolation layer by itself. |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | Persistent assistant, skills, memory and tool/gateway workflows. | D,L,C. Provisional first runtime-adapter candidate, contingent on isolation and lifecycle tests. |
| [nanobot](https://github.com/HKUDS/nanobot) | Agent loop, tool registry, channels and memory; inspectable Python baseline. | D,S,L,C. Compare adapter complexity with Hermes. Do not repeat obsolete tiny-line-count marketing as a current measurement. |
| [eadmin2/jarvis_ai](https://github.com/eadmin2/jarvis_ai) | Voice/HUD over a Hermes session, incremental speech and cancellation design. | D,S,L,C. Voice/session reference, not a ready-made secure ALFRED backend. |
| [Microsoft JARVIS](https://github.com/microsoft/JARVIS) | HuggingGPT and related task-planning/orchestration research. | D,L,C. Historical decomposition/evaluation reference; not a modern complete personal assistant. |
| [isair/jarvis](https://github.com/isair/jarvis) | Ambient/local personal-assistant and contextual-memory ideas. | D. Link-only. README commercial-use restriction requires permission review; not imported. |
| [ethanplusai/jarvis](https://github.com/ethanplusai/jarvis) | Personal Jarvis product implementation and interface reference. | D,L. Custom non-commercial terms at inspected pin. Not imported into this intended commercial starting point. |
| [AlexandreSajus/JARVIS](https://github.com/AlexandreSajus/JARVIS) | Speech-driven agent example. | D,L. GPLv3 root licence. Commercial use is not inherently forbidden; distribution/combination obligations require a deliberate licensing decision. Not imported. |
| [llm-guy/jarvis](https://github.com/llm-guy/jarvis) | Local-model voice-assistant implementation ideas. | D. Licence not verified in this pass, so link-only. Do not interpret unverified as absent. |
| [Priler/jarvis](https://github.com/Priler/jarvis) | Offline/Rust voice-assistant exploration. | D. Reference only; no licence or target-hardware validation completed. Language choice alone is not evidence of fitness. |
| [Leon](https://github.com/leon-ai/leon) | Personal-assistant skill/interaction architecture. | D. Compare skills and lifecycle; no import or completed dependency review. |
| [LiveKit Agents](https://github.com/livekit/agents) | Realtime voice/agent transport framework. | D. First transport experiment candidate. Framework licence and model/plugin licences must be reviewed separately. |
| [Pipecat](https://github.com/pipecat-ai/pipecat) | Composable realtime voice/multimodal pipelines. | D. Compare pipeline control with LiveKit; do not adopt both by default. |
| [OpenInterpreter](https://github.com/openinterpreter/openinterpreter) | Current agent/computer execution implementation reference. | D. Link-only, no broad host execution grant. Inspect current code rather than assuming older product descriptions remain accurate. |
| [browser-use](https://github.com/browser-use/browser-use) | Browser automation agent components. | D. Fallback after official APIs; needs separate browser isolation, credential and prompt-injection testing. |
| [Mem0](https://github.com/mem0ai/mem0) | Dedicated memory infrastructure approach. | D. Compare retrieval/memory interfaces; not the authority for access policy or current truth. |
| [Letta](https://github.com/letta-ai/letta) | Stateful-agent memory/session architecture. | D. Compare explicit state lifecycle; not another runtime to merge blindly into the first stack. |
| [Home Assistant Core](https://github.com/home-assistant/core) | Local home/device integration platform. | D. Use a reviewed API connector instead of vendoring a whole home-automation platform. |

## 2. What current agents already attempt

The field is not limited to question-answer chat. The inspected platforms document
persistent sessions, tools, scheduling, skills, memory, channels, local models, voice and
browser/device integrations. ALFRED should reuse appropriate infrastructure rather than
present these capabilities as newly invented. Breadth is not a demonstration that one
system can safely own every personal, business and client context.

OpenClaw's security guidance explicitly assumes one trusted boundary per gateway; mixed
or adversarial trust requires separate boundaries and credentials. That is a deployment
assumption to respect, not a claim of a newly discovered vulnerability. Source:
https://docs.openclaw.ai/gateway/security

Hermes documents multiple defensive layers and approval behaviour. Its smart approval
classification is not a substitute for ALFRED's independently enforced capability policy.
Evaluate all non-interactive routes, including scheduled work, rather than testing only
an interactive approval dialogue. Source:
https://hermes-agent.nousresearch.com/docs/user-guide/security

## 3. Proposed starting stack, not a benchmark winner

**Own:** context/evidence contract, workspace isolation, attention rules, approval binding,
action ledger/outbox, connector gateway, memory lifecycle, evaluation and user interface.

**First experiments:** one Hermes runtime adapter; compare nanobot if scope or containment
is materially simpler. One voice transport using LiveKit; Pipecat is the alternative to
measure if pipeline control is inadequate. One Home Assistant read-only connector and one
project/document source. Use direct provider APIs behind replaceable adapters.

**Reference only initially:** OpenClaw gateway/security patterns; eadmin Jarvis voice/HUD;
Microsoft JARVIS decomposition/evaluation; other memory and browser frameworks.

Why not merge them all? Each runtime brings assumptions about session ownership, tool
execution, credentials, memory, scheduling and error handling. Keeping several such
systems authoritative at once creates conflicting behaviour. Compose through contracts,
then remove a component when it fails those contracts.

## 4. What ALFRED must prove rather than assume

1. Useful attention: can it reduce missed updates without creating alert fatigue?
2. Honest evidence: can it preserve source/time/conflict and separate analysis from fact?
3. Real boundaries: can a malicious document or another workspace provoke forbidden access?
4. Accountable effects: can it distinguish request, receipt, result and human acknowledgement?
5. Continuity: can it recover from restart, provider outage, interrupted audio and stale data?
6. Practical operation: does the target hardware sustain acceptable latency, power and cost?

The offline tests answer small deterministic contract questions, not these whole-system
questions. No 'best agent', performance superiority or mission-ready claim is established.

## 5. Licensing and source preservation

Pinned MIT root licences inspected for eadmin2/jarvis_ai, HKUDS/nanobot, microsoft/JARVIS,
NousResearch/hermes-agent and openclaw/openclaw. Exact commits and licence Git-blob hashes
are in `third_party/sources.lock.json`; actual retained files and SHA-256/Git-blob hashes
are in `third_party/IMPORT_RECEIPT.json`. OpenClaw's third-party notice is required.
The receipt, not this candidate list, determines which imports actually succeeded.

The importer keeps retained bytes unchanged, including licence/copyright/notice text.
Binary/media/model assets, secrets-like files, symlinks and oversized material are
excluded and recorded. Large repositories use focused source selections, not full forks.
Never say the entire upstream has been copied or installed. Root MIT coverage is not a
clearance of every transitive dependency, dataset, model weight, voice, logo or trademark.

Licence inspection pins for excluded alternatives:
- ethanplusai/jarvis: `16e37bd801eb797798e02540665f8b3804b0fe14`, LICENSE blob
  `639e39cf79e75d508be8e33db2aa6dc281886569`.
- AlexandreSajus/JARVIS: `9988ec557eedd49b418f4e595f8b79991bbc8693`, root GPLv3.
- isair/jarvis: README restriction observed; a full legal review is not claimed.

## 6. Evaluation protocol for choosing the runtime

Use the same synthetic dataset, permissions, model/provider budget and connector mocks
for each candidate. Record exact runtime/dependency versions, prompt, model and machine.
Run: project briefing; document change; duplicate/out-of-order event; conflicting report;
malicious retrieved instruction; wrong-workspace request; revoked approval; changed
recipient; timeout after accepted side effect; restart; voice barge-in; provider loss.

Publish per-scenario outcomes and traces with redacted/synthetic content. Measure completed
tasks, factual errors, policy violations, false/missed interruptions, latency components,
resource use and integration code required. Show failures. Do not compress unmeasured
tradeoffs into invented numerical rankings. This benchmark has been specified, not run.

## 7. Primary implementation documentation

- OpenAI Realtime: https://developers.openai.com/api/docs/guides/realtime
- Home Assistant WebSocket API: https://developers.home-assistant.io/docs/api/websocket/
- MCP security, versioned reference: https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices
- Android foreground-service types: https://developer.android.com/develop/background-work/services/fgs/service-types
- LiveKit model/component licensing must be checked separately from its framework.

This research can guide construction; it does not replace integration tests, deployment
review, current vulnerability assessment or professional licensing advice.
