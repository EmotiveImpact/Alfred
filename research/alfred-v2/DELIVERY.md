# Integration sequence, dependencies and acceptance
18 October 2026; research-only. Do not merge this work into implementation tickets automatically.

**Keep ALFRED in command as Hermes is installed.** This is a new optional context provider behind current contracts, not a replacement for the Python core, BrainHub, memory or verification. Before each runtime PR, rebase/read current merged changes including #26, #44 and H5 and use the interfaces actually present, not a frozen assumed layout.

## V2 proposed PR breakdown
| Phase | Narrow implementation | Depends on | Evidence to request |
| --- | --- | --- | --- |
| V2-R | Research, source catalogue, synthetic threat model | Current main; **this PR** | Source provenance and no runtime diff |
| V2-01 | Event envelope + mock sensor gateway | Grants and identity contract review | Offline schema, stale/event replay tests |
| V2-02 | Discretion policy on synthetic occupancy | V2-01 | No confidential audio in unknown/multi-person zones |
| V2-03 | Visible PTT and session pairing | Device identity and voice product decision | Local device/browser acceptance; no silent capture |
| V2-04 | Optional local wake service and diarisation | V2-03; licence, privacy and hardware choice | Wake and overlap false-positive study; manual cut-off |
| V2-05 | Camera adapter publishing redacted metadata | V2-01, privacy impact work | Zone scope and source freshness, zero raw video by default |
| V2-06 | CSI/BLE evaluation-only adapter | V2-01, controlled test hardware | Real confusion matrix, calibrated uncertainty and abstention |
| V2-07 | Graded overnight alert delivery and acknowledgment | Existing receipts/connector grants; devices | Failure, offline, DND, no-ack and fallback tests |
| V2-08 | Multi-site enrolment and revocation | V2-01, V2-05 and robust key/grant gates | Isolation, lease expiry, outage, deletion and cross-site tests |
| V2-09 | Hermes worker tasks that can consume *sanitised context* | Real H5 adoption and permission | Brain fencing, prompt injection, privacy-egress tests |

## Interfaces to negotiate with pending PRs
- #26 encryption keys do not yet seal all application records; sensor event ingestion using real private streams waits for application encryption and related deletion/restore gates.
- #44 provenance proposal guard must continue to block untrusted action parameters, regardless of which sensor/context model proposed them.
- H5 Hermes is a **replaceable worker**, not a direct sensor or action adapter and never a keeper of the user's identity/authorisation.
- #20 LiveLens connector must not be assumed merged or given new camera capability without inspecting its current owner-approved API, grants and retention semantics.
- Existing Home Assistant and Hermes snapshots are already archived in `third_party/library`; don't clone them twice.
- ENDSTATE and 8 Ball remain separate downstream analytical candidates; this V2 research does not invent integration contracts for them.

## Pilot scorecard (targets to be decided, not invented results)
Track per-room true/false occupancy, count error, uncertainty, latency, bandwidth and power. For speaker modules measure missed activation, false wake/trigger, false speaker attribution and overlapping speech. For discretion score information-leak incidents as a critical zero-tolerance release gate in prescribed test cases. For notifications track delivered/seen/acknowledged separately with timestamps and retry/escalation compliance. Collect privacy/consent changes and retention test evidence. Report subgroup/lighting/device and acoustic-condition variance. Always compare to simple PTT baseline.

## Commercial and deployment safeguards
Before external deployment: lawful basis and DPIA; local notices; data minimisation; model-weight and dependency licence audit; human oversight for safety-impact decisions; physical sensor and network security; tested rollback; documented operational support. A source clone is not permission to use brand assets or non-commercial weights.

## Handoff
This PR is a self-contained design and read-only upstream research snapshot. No live connector, no autonomous call answerer, no microphone service, no watch app, no camera stream, no Hermes installation. Future implementation should start at latest main, respect active file claims and request owner approval for runtime/adoption changes.