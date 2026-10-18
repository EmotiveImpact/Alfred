# ALFRED V2: Environmental Intelligence and Secure Presence
18 October 2026 | Research proposal | Based on ALFRED main 4cdd4d4174bd03c3ab40ca2db2af83e9650a44e4

**Status: design, not implementation.** This is a forward-compatible V2 research programme, not a claim that ALFRED can currently sense rooms, answer live calls, perform voice identification or run Hermes. No code in the research shelf is installed, imported or executed.

## Executive vision
ALFRED is an always-available, personally governed operational and executive intelligence. He can monitor authorised signals while the owner sleeps, wake the owner for genuine urgent events, and converse by push-to-talk or optional local wake word. Environmental signals help him judge whether other people may be nearby, whether a subject is private, whether to speak out loud, and which device to use. **Presence is context, not identity; identity is not authority.** The same boundary applies at home, in the office and across multiple authorised sites.

The permanent architecture principle is **many brains, one ALFRED authority**. ALFRED's Python policy, memory, goal/mandate, exact approvals and independent verification remain in command. Hermes is planned as a replaceable external brain/long-task worker using the existing typed task-packet and result-bundle contract. Claude, OpenAI or local models may be routed through the same hub. External sensors, inference models, worker agents and documents must never grant permissions.

## What V2 means
1. **Always monitoring**: ALFRED's durable background core observes *specifically authorised* calendar, communication, infrastructure or sensor event sources. It does not imply room audio capture. A human approves each connected source and the privacy/retention settings.
2. **Optional local wake-word mode**: after a clear opt-in, an on-premises microphone processes a limited wake word locally and opens a visible conversation session. This is distinct from continuously recording or exporting raw speech.
3. **Push-to-talk mode**: an intentional button or device gesture begins an authenticated session. This remains the reliable privacy baseline and fallback.
4. **Environment-aware discretion**: sensor observations provide tentative occupancy, overlap or attention cues. Private information defaults to a trusted personal device when occupancy is uncertain; no secret is spoken on environmental identity evidence alone.
5. **Overnight escalation**: a bounded, graded incident triage system delivers watch/phone notifications, with explicit acknowledgement, retries and escalation to an approved channel. Deliverability and wake-up are measurable, never assumed.
6. **Scope and mobility**: per-site sensor agents publish metadata under local policy. Unavailable sensors produce `unknown`, not `empty room`. Travelling mode relies only on paired, permitted devices and services.
7. **Full control**: per-room microphone/camera switches, privacy indicators, schedule, sensor coverage, permissions, retention, revocation and activity receipts are visible and independently enforced.

## Current repo boundary (verified 18 October)
- [AGENTS.md](../../AGENTS.md), [ARCHITECTURE](../../docs/ARCHITECTURE.md), [AGENT_HUB](../../docs/AGENT_HUB.md) and [capability contract](../../docs/CAPABILITY_CONTRACT.md) are authoritative over this research.
- Current `main` baseline is `4cdd4d4174bd03c3ab40ca2db2af83e9650a44e4`. Synthetic brain H1-H4 and the hub exist. **Hermes H5 is not yet an installed, working worker**. The existing [Hermes source snapshot](../../third_party/library/README.md) is research only.
- Current open PRs include #44 (proposal provenance), #26 (encryption keys, still not record sealing), #27, #20 and #19. Merge order and scope must be reconsidered against current refs; don't modify their files from this research PR.
- The repo is **public**. No actual voiceprints, camera frames, identifying household data, personal schedules or client recordings belong here.
- Keep ALFRED a broader personal/executive intelligence. Environmental awareness is optional, not a general mandate for workplace surveillance.

## Programme index
- [Architecture and contracts](ARCHITECTURE.md)
- [Sensors, research evidence and realistic reliability](SENSORS.md)
- [Command authorisation, privacy and adversarial tests](SECURITY_AND_TESTS.md)
- [Phased build, measures and PR integration](DELIVERY.md)
- [Upstream source catalogue, copy status and reproducible cloning](UPSTREAMS.md)
- Machine-readable [source lock](UPSTREAMS.json)
- Inert selected source snapshots in [third_party/research-v2](../../third_party/research-v2/). These are **curated source-file copies**, not full repository clones or full Git history.

## Product rule
ALFRED should notice when another person enters the room and become appropriately discreet. He must not infer that any detected person is authorised to give him an instruction. The system may defer, ask privately, or abstain rather than invent certainty.