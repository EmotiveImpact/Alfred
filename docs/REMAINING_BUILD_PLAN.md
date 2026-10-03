# Remaining build plan

Updated 3 October 2026. This extends the [roadmap](ROADMAP.md), not the PRD or register. The detailed 2 October plan is preserved [verbatim](archive/pre-stage-2026-10-03/REMAINING_BUILD_PLAN.md). All package numbers below are retained for continuity. Current execution is limited by [PILOT-GROUNDWORK](NEXT_STAGE.md): build current-product trust/reliability; prepare later infrastructure through research and opt-in synthetic work; do not activate later stages automatically.

## Where we are

PR #18 is merged as main `75947b8dd59a3161c862d2533850a032994778e2`, including #15/#16/#17. The recorded delivery classifications remain 8 bounded implemented slices, 24 partial and 1 not started; these are not a weighted completion percentage. The merge does not make partial work complete. Runtime is still local/foreground, and no private-data/native/cloud/commercial deployment is established.

The [audit](AUDIT_2026-10-03.md) supplies the exact-main evidence and a source-review concern requiring reproduction. Code and current tests, not historical wording, determine what remains.

## Gate 0: delivery reconciliation

| Package | State and action |
|---|---|
| 0.1 | Completed: PR #18 and inherited #15/#16/#17 are in main. Do not repeat the merge. |
| 0.2 | This documentation branch reconciles the starting instructions, current architecture/PRD/roadmap and merge metadata, preserves prior blobs and publishes the stage/audit/cloud prompt. Its own merge remains separate. |
| 0.3 | Retain the earlier open questions about time zones, routine authoring across paired devices, expired draft offers, superseded valid periods, history export and forget retention. Propose choices with tests and distinguish routine implementation details from consequential authority/retention decisions. Do not block all work on them. |
| Audit follow-up | Before widening use, reproduce/disprove restricted-source action/approval visibility and fix a confirmed common-path defect. NEXT_STAGE A1 maps this to existing MEM-009/SYS-001/ACT-001; it is not a new already-proven vulnerability. |

## Gate 1: private pilot

| Package | Work retained | Acceptance and decisions |
|---|---|---|
| 1.1 | Application encryption and key custody (SYS-002/M05). | Propose vetted dependency/custody design for local and always-on use; owner decision before adoption/private activation. Test copied database/backups, unlock, rotation, retention and recovery. Do not equate OS disk protection, field encryption and end-to-end secrecy or claim secure erasure from VACUUM alone. |
| 1.2 | Strict grants by default (SYS-001/MEM-009/M02). | Default-deny new installations/credentials with explicit demonstration grants; migration and revocation tests across surfaces; complete person/device history and administration without silently merging people. |
| 1.3 | Deletion, export and restore accounting (MEM-010/013/M05). | Receipts cover relevant dependent statements, answers, drafts, artefacts, caches and controlled exports; history/routine export semantics explicit; restored data obeys deletion journal; direct fixture scans match reports without overstating erasure. |
| 1.4 | Host restart and recovery (RUN-001/M09). | Extend existing interruption/job recovery, health and diagnostics rather than rebuild them. Kill/restart mid-task without duplicate effects or false success. Service examples may be generated and inspected; no unapproved installation. |
| 1.5 | Broader Obsidian compatibility and safe note writing (MEM-001/002/M01/M04). | Preserve implemented identity/anchors/aliases and create-only inbox. Additional supported syntax and any append capability require explicit parser and concurrent-edit/diff/read-back tests. Do not require a wholesale editor clone or infer conflict solely from equal content. |

**Gate 1 exit:** relevant 1.1-1.4 safeguards plus audit disposition and complete synthetic-loop evidence, explicit selected-pilot approval, then one non-critical real workspace. 1.5 remains a scoped compatibility programme, not permission to overwrite human notes.

## Gate 2: useful assistant

| Package | Work retained | Acceptance and decisions |
|---|---|---|
| 2.1 | Replaceable reasoning runtime (INT-001/M03/M07). | Bounded context/time/tokens, logged purpose and independent checks. Choose model/location/data terms explicitly. Existing restricted live-model comparison is not reauthorised or rerouted. |
| 2.2 | Evidence/semantic answer evaluation (INT-002/MEM-008/M06/M07). | Preserve the frozen lexical baseline; improve packet/link relevance and abstention on held-out synthetic cases. Report recall/precision, context size, latency, failures and denominators. Source accounting is separate from model correctness; a self-grading model is not sufficient proof. |
| 2.3 | Structured document ingestion (MEM-001/003/M08). | Parser dependency decision, page/block provenance, revision/hash, forget/rebuild coverage. PDF first and office formats deliberately, not arbitrary uncontrolled parsing. |
| 2.4 | Automatic capture policies (MEM-004/M04/M10). | Owner-authored per-type rules, proposal/review and budget; no silent durable acceptance. |
| 2.5 | One approved external workflow (ACT-001/CON-001/M11). | Selected account/data permission, read-only path first; harmless exact-approved write only after token custody and capability-specific read-back/unknown-result acceptance. Reuse the existing outbox. |
| 2.6 | Routines/procedures maturity (ATT-001/MEM-015/M10). | Explicit time-zone and authoring semantics, versioned procedure review, measured nomination usefulness; no retrieved-text execution or automatic expansion of rules. |
| 2.7 | Visible push-to-talk (VOI-001/M12). | Separate microphone/capture/retention permission, confirmed transcript and actual device tests. Output-only read-aloud does not authorise listening. |
| 2.8 | File-sync lifecycle (MEM-014/M09). | Named client policy, freshness/conflicts and actual client-output acceptance; no live SQLite sync. |

**Gate 2 exit:** measured useful end-to-end workflow, approved account capability where selected, honest failures and sustained owner pilot. Do not replace useful evidence with more feature surfaces. Track A may progress the synthetic engineering; real-data/account/microphone activation remains gated.

## Gate 3: always-on, multiple machines and native clients

Research and opt-in synthetic groundwork are allowed now under Track B. Production remote mode and infrastructure activation require a separate decision and tests.

| Package | Work retained | Later acceptance |
|---|---|---|
| 3.1 | Second trusted node and coordinator placement (RUN-002/SYS-001). | Compare laptop/home/VPS authority; decide data/keys, mesh/transport, expiry and spend. Enrol a worker without sharing the live DB; laptop-offline job plus second-client inspection/reconnect with no duplicate authority. |
| 3.2 | Isolated workers (RUN-003). | Evaluate persistent versus disposable backends, explicit limited inputs/network/resources/cost, cancellation and result checks. boxd/E2B/OpenShell remain candidates; a subprocess is not a VM or sandbox. |
| 3.3 | File/object-storage tier (SYS-003). | Vendor/region/egress/custody/budget decision; bounded cache, pins, revisions/conflicts, authorised reads, deletion lineage and recovery tested on an actual chosen tier before claiming cloud-file operation. |
| 3.4 | Native packaging (RUN-001/UX-001). | Preserve React/Python; compare Tauri/Rust with alternatives, IPC/sidecar/keys/signing/update and WebGL/device acceptance. An opt-in prototype may proceed separately from hosting; no rewrite or release by implication. |

Cloud build agents are not ALFRED production infrastructure. A VPS listener or single-container demonstration does not prove an always-on distributed service. Keep hardware and provider limitations visible.

## Gate 4: team and operational

| Package | Work retained | Later acceptance |
|---|---|---|
| 4.1 | Role-limited team workspaces (OPS-001/SYS-001). | Mature identity plus deployment decision, multi-owner roles, permitted shared executive/history state and explicit tenant isolation tests. No automatic private-person memory sharing. |
| 4.2 | Real specialist adapters (OPS-001/002). | Obtain/read actual independent product contracts; preserve simulation/report/analysis/observation/result/acknowledgement. Synthetic contract is not real ENDSTATE/Noir/Loc8/8BALL/God's Eye integration. |
| 4.3 | Independent review appropriate to release. | Review privacy/identity/crypto, external effects and team boundaries before operational use; no autonomous use-of-force authority. |

## Later commercial stage: research now, activation later

This does not add a second PRD. Investigate Cloud/Private/Sovereign product options, hosting/storage/GPU/worker partners and rent/reserve/dedicated/colocation/ownership economics. Preserve uncertainty in the later-chat source. Require workload-based cost/sensitivity and post-credit estimates, real support/security needs and explicit business approval before a partner application, contract, purchase or commercial launch. Headline prices and informal codebase valuations are not evidence of unit economics.

## How to execute

Choose ready work within the active stage, review source/current tests first, and record exact requirement IDs, commit, tests, limitations and next step. Use focused PRs and preserve concurrent work. Do not bypass unresolved decisions by enabling a hidden default or filling in mock success. Do not install the inert source library, weaken loopback controls or reroute a blocked experiment. At task limits leave a usable checkpoint; passing one gate does not automatically activate the next.
