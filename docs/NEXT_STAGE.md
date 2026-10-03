# Next stage: pilot hardening and future-platform groundwork

**Stage ID: `PILOT-GROUNDWORK`. Date: 3 October 2026.** This is an execution gate over the existing PRD and roadmap, not a new product, a replacement M programme or infrastructure stage 0. Start here after reading the repository's current AGENTS.md.

## Owner intent and scope

The owner asked to consolidate the later conversation and audit into the repository, push a clear handoff, and let a cloud agent continue in a distinct stage: keep improving the current application, research the later platform and lay groundwork, **without rushing straight into deployment, provider commitments or commercial infrastructure**.

The earlier whole-product mandate remains the product direction. This later instruction limits what the next task may activate. Completing an item is not automatic permission to cross the next deployment gate. Existing PRD requirements remain in scope; later work is sequenced, not silently cancelled.

| Track | Work authorised in this stage | Not authorised by this stage |
|---|---|---|
| A. Current-product engineering | Audit regression tests; confirmed defect fixes; permission-default migration; local lifecycle/recovery and deletion/export accounting; measured retrieval improvements; reviewable work against existing PRD acceptance using synthetic data. | Private-data release, live account connection, microphone capture, public hosting, automatic main merge. |
| B. Future-platform groundwork | Current primary-source research; decision records; threat models; client/core/node/file interfaces; mock-independent local contract tests; bounded opt-in synthetic prototypes where supported by the existing development environment. | Selecting a paid provider by implication, provisioning external servers/buckets/GPUs, connecting the owner's devices or data, enabling production remote listeners, commercial launch. |

Ordinary reversible engineering choices do not need another owner meeting. For consequential choices, provide the recommendation, evidence, trade-offs and exact approval needed. If one choice is blocked, continue independent in-stage work.

## Verified starting point

The live GitHub baseline checked for this handoff is main `75947b8dd59a3161c862d2533850a032994778e2`, tree `243cf314bdd8f955e95ca41118eb2811cb81c829`. PR #18 is merged and includes #15, #16 and #17. Do not merge those historical PRs again or rebuild their features. Refresh current refs and concurrent PRs before editing.

The exact-main unified run [37075687737](https://github.com/EmotiveImpact/Alfred/actions/runs/37075687737) passed. The accompanying [audit](AUDIT_2026-10-03.md) inspected source and CI evidence; it did not rerun the suite or certify security. Its counts are historical evidence, not a substitute for testing a new revision.

The existing application has an authenticated backend-connected console, reviewed-memory context, capture/review/inbox writing, executive records, temporal review, routines, local jobs and a bounded cache. It remains a foreground loopback application with no proven private-data release, installed native application, cloud coordinator, second worker or live specialist connection. See the requirement register for individual implementation boundaries.

## Track A: build the next useful, trustworthy increment

These are priorities within [REMAINING_BUILD_PLAN.md](REMAINING_BUILD_PLAN.md), not an instruction to repeat every earlier implementation.

### A1. Investigate approval visibility first

Maps to MEM-009, SYS-001 and ACT-001. The audit identified a **source-review concern, not a reproduced exploit**: `alfred/console_api.py` assembles approval rows by workspace and includes stored text/path; `mine` is ownership metadata, not a visibility filter.

Create an exact negative test with two people in one workspace, a restricted source and an action derived from it. Inspect the graph projection, action listings/detail and related metadata before/after grant revocation and credential changes. Test text, destination paths, source IDs, fingerprints and restricted counts. Decide/document intended shared visibility rather than silently assuming all workspace members can read all drafts. Keep approval authority separate from read visibility.

Reproduce against the unchanged baseline before claiming a bug. If reproduced, fix the common permission path and add positive tests for the authorised owner. If not reproduced, retain the result and explain the effective control. Do not weaken assertions to produce a green result.

### A2. Complete source-permission defaults with compatibility

Maps to SYS-001/M02 and MEM-009. New private-pilot installations and credentials should not inherit broad source access implicitly. Specify and test the migration for existing legacy workspaces; grant synthetic demonstration sources explicitly. Preserve source/model/write purpose distinctions and per-person/device identity. Test graph, questions, approvals, jobs, exports, health and routines, including revocation during work. Pairing is not proof of complete multi-device shared history.

### A3. Finish the local reliability and privacy prerequisites

Maps to SYS-002/M05, MEM-010, MEM-013 and RUN-001/M09. Extend rather than replace existing forget, backup, restore, interruption and job recovery behaviour. Account for dependent records, artefacts, caches, exports and retained history; distinguish inaccessible, deleted and retained audit metadata. Kill/restart tests must report interrupted or unknown outcomes without duplicate effects. Generate inspectable service examples if useful; do not install them on the owner's computer from this task.

Prepare a key-custody decision covering local and eventual always-on operation. Use established cryptographic implementations; do not write custom cryptography. Architecture research and synthetic test design may proceed before the custody decision. Adopting a new crypto dependency or unlocking real data needs the recorded decision and applicable repository approval. Encryption at rest is not protection against an already authorised running service with the key. Do not claim VACUUM, a clean current database scan or a VM snapshot is secure erasure across WAL, backups, exports and storage media.

### A4. Improve evidence selection and prove the loop

Maps to MEM-008/M06, INT-001 and INT-002. Retain the frozen baseline. The earlier evaluation found about 76% irrelevant evidence in a small synthetic set; that is not an answer-error rate. Investigate packet filling and link expansion, allow unsupported queries to return no supporting evidence, and measure held-out recall, precision, abstention, latency and context size. Report any trade-off, not only improved numbers. Do not install embeddings or a new graph server merely for fashion. Keep reasoning-quality evaluation separate from source-accounting tests and preserve existing restrictions on the blocked model comparison.

Prove one synthetic end-to-end project: select, ask, inspect original evidence, remember, correct, forget, restart and restore. Preserve the approved console and existing backend. Add actual browser-to-backend checks for affected interactions.

## Track B: prepare the later stage without activating it

Use [the later-chat reconciliation](sources/2026-10-03/LATER_CHAT_RECONCILIATION.md) alongside the earlier [infrastructure research](../research/INFRASTRUCTURE_2026-10-02.md). Earlier provider claims, prices, licences and startup credits must be rechecked at primary sources before a recommendation is treated as current. Research is not provider adoption.

### B1. Native client and always-on authority

Map to RUN-001, RUN-002, SYS-001, SYS-002 and UX-001/002. Preserve React/TypeScript/Three.js/GLSL and the useful Python core. Compare a Tauri/Rust shell with Electron or other justified alternatives on the actual console, packaging, sidecar lifecycle, IPC, key storage, update/signing and target-device rendering. Tauri is a recommendation to evaluate, not an approved dependency or a reason to rewrite Python. Desktop packaging and cloud hosting are independent tracks.

Compare primary laptop, always-on home host and VPS coordination. The later conversation favours an always-on Core for continuity, but data location, keys, provider and scope egress remain undecided. Record what stops when each node sleeps. Preserve exactly one active authority for each job; no writable database file synchronised between computers. Design an explicit remote transport rather than removing existing loopback, Host/Origin or CSRF checks.

A proposed acceptance scenario for the later runtime stage: with the laptop disconnected, the approved coordinator remains reachable from another enrolled client, a job continues on an available worker, cancellation and results reconcile, and reconnecting the laptop duplicates neither authority nor effects. This scenario is **not yet passed**. Localhost simulations do not prove a second-machine deployment.

### B2. Agent computers and cloud-backed files

Map to RUN-003 and SYS-003. Preserve boxd, Space/SpaceFS and the pCloud second-drive experience. Compare persistent machines with disposable sandboxes; files, installed packages, running memory, snapshots and external effects have different lifecycles. Reuse the existing WorkerBackend and job ledger, not a second executor.

Assess local/VPS workers, hosted services and open/self-hosted options separately. Verify actual project identity, licence at a pinned version, hypervisor availability, isolation, budgets, cancellation, recovery, data egress and exit portability. E2B, NVIDIA OpenShell and boxd are different candidates, not interchangeable capabilities. Do not represent a Python audit hook or local subprocess as a sandbox. A fork must not duplicate usable credentials or execution authority. Snapshot rollback cannot unsend an external message.

Keep authoritative databases, secrets, durable files, rebuildable indexes, backups and scratch space separate. Specify bounded authorised on-demand reads, offline pins, revision conflicts and deletion lineage for the file tier. A VPS worker does not supply a cloud drive; object storage does not supply shared memory or safe database synchronisation.

### B3. Commercial and partner research

This is strategic groundwork only, mapped to the existing runtime, storage, identity and operational workstreams. Preserve the shortlist from the conversation, grouped by role: OVHcloud/Scaleway/DigitalOcean/Hetzner for hosting; Cloudflare and Backblaze for edge/storage; NVIDIA, Nscale and Nebius for GPU/ecosystem investigation; boxd/E2B/OpenShell for execution; Tailscale/Headscale/NetBird/WireGuard for transport; Telehouse/Digital Realty for possible later colocation. No relationship, eligibility, pricing or service-level promise is established by being named here.

Produce a dated cost model driven by workload, not headcount alone: active users, sessions, model input/output tokens, CPU/GPU hours, idle reservations, storage, requests, egress, backups, redundancy, monitoring, tax/currency assumptions and operating staff. Separate list price, credit, discount and negotiated quote; show sensitivity and post-credit costs. Do not treat earlier chat valuation estimates as evidence of asset value or financeability.

Evaluate rent, reserved/dedicated capacity, colocation/owned hardware and possible technology licensing or acquisition as later options. Ownership is not an inevitable destination; utilisation, reliability, staffing, financing and exit costs must justify it. Draft outreach questions only. Do not contact providers, apply to programmes, make purchases or provision infrastructure under this task.

Cloud, Private and Sovereign are proposed deployment/product labels. Do not market sovereignty, compliance, multi-tenancy or confidentiality guarantees before their requirements and acceptance are defined. Commercial rollout needs its own product, cost, support and security review. Preserve specialist products as independent systems.

## Promotion gates

| Gate | Evidence needed | What happens next |
|---|---|---|
| Research to local prototype | Named question, primary sources, threat model, reversible design, synthetic data, bounded existing-environment resources. | An opt-in prototype may be reviewed. It stays out of the default runtime. |
| Prototype to application implementation | Relevant tests, compatibility evidence, dependency/licence review, failure cases and no competing authority. | A focused PR, with the implementation still distinguished from deployment. |
| Application to private pilot | A1 addressed, strict-default migration, agreed key custody, deletion/restore and recovery evidence, selected data and explicit owner go-ahead. | One controlled real workspace, not automatic import of everything. |
| Local to hosted/distributed pilot | Authority-location decision, approved egress/scopes, provider/region/budget, remote authentication, service lifecycle, recovery and isolated-worker acceptance. | Separately authorised provisioning and measured pilot. |
| Pilot to commercial/owned infrastructure | Measured usefulness and economics, tenant/security/support acceptance, capacity and exit plan, explicit business approval. | Separate later programme. No automatic activation from green CI. |

The next cloud task may complete Track A and prepare Track B. It must not infer permission to cross the private-data, hosted or commercial gates. It should stop at the boundary with a recommendation and a resumable checkpoint, while continuing independent authorised work where possible.

## Delivery and continuation

The [PRD](PRD.md) defines scope, [roadmap](ROADMAP.md) sequence, [remaining plan](REMAINING_BUILD_PLAN.md) the outstanding work packages, and [requirement register](../plans/requirement-register.json) delivery state. This file defines the active stage and gates. Do not create another competing roadmap.

For each change record requirement IDs, exact revision, what was actually exercised, positive and negative results, remaining limitations and approval needs. A test stub is not an implementation; a merged PR is not a deployment; a signed result proves origin/integrity only to the extent tested, not factual correctness. An audit hypothesis is not a confirmed defect.

At task limits, commit or preserve a usable diff and update SESSION_HANDOFF.md with the next executable step. Use the task's actual repository/PR tools; report missing access rather than pretending to push. Do not promise background work after the task ends. This stage does not automatically authorise a main merge.

**Cloud-agent launcher:** [CODEX_NEXT_STAGE_PROMPT.md](CODEX_NEXT_STAGE_PROMPT.md). No old ZIP or manual multi-document assembly is required once this branch is available to the task.
