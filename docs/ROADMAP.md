# ALFRED current execution roadmap

<!-- ALFRED unified operational/executive baseline: 2026-09-27 -->

**Current product category: operational and executive intelligence.** See [positioning](PRODUCT_POSITIONING.md). The owner-authorised development PR stack is now merged into `main`; start new work there. The real local backend and the newer React/Three.js console are both preserved, but the console still uses fictional fixtures and needs its authenticated backend adapter. Consolidation is not deployment, external integration or completion of the planned memory jobs. The broad source-library catalogue, not earlier archive counts, is the current inventory.

27 September 2026. Requirements: [PRD.md](PRD.md). Job IDs/dependencies/acceptance cases: [memory-backlog.json](../plans/memory-backlog.json). Current integration baseline: `main`. The former planning branch is historical. Historical roadmaps are preserved in [archive/ROADMAP-through-v08.md](archive/ROADMAP-through-v08.md).

## Where we are

v0.8 provides local persistence, credential-scoped sessions, source retrieval, conversations, manually reviewed memory, fixed Pulse routines and exact approvals for local drafts. The latest functional React/Three.js fixture console is merged alongside that baseline. Source archive remains 2,073 inert files. Current appearance is not represented as a finished version of the target console.

The memory work in this revision is researched requirements and a build plan, not an implemented Obsidian connector upgrade, graph engine, account integration or new model. The v0.7 small model's known failures and the blocked v0.8 comparison remain recorded. The development stack is merged into main; no deployment has occurred.

## M01 review checkpoint, 30 September 2026

M01's bounded selected-vault/read slice is implemented on a draft review branch from current main. [Its receipt](evidence/memory-m01/RECEIPT.md) records synthetic acceptance and limitations. The backlog tracks this implementation separately from merge/deployment status. M02 through M12 remain planned; private-pilot gates M02/M05 are unchanged. M03 is the next dependent memory slice after M01 review. Full native Obsidian compatibility and the complete memory loop remain unfinished.

## Immediate deliverable

**1 October 2026 draft checkpoint:** M03 is implemented on the M01 review branch. Accepted/current/relevant actor-private statements now enter question and conversation context with exact support and review/valid-time basis. [The receipt](evidence/memory-m03/RECEIPT.md) records bounded selection, namesake qualification, stale review checks and source-only compatibility. M02 and M04-M12 remain planned; M02/M05 private-pilot gates are unchanged. The complete memory loop and real console adapter remain unfinished.

**Remember, retrieve, correct, forget.** A user selects a permitted test vault, reviews a memory, uses it in a follow-up with its original evidence, corrects it and verifies that withdrawn/stale material no longer appears. One approved inbox note can then be created and read back without overwriting human content.

## Whole-product workstreams, 2 October 2026

The M jobs below are the bounded memory programme. The whole product also needs the workstreams in this table; their requirement IDs, separate decision, implementation, integration, merge and deployment states, and owner decisions are in [the requirement register](../plans/requirement-register.json). How the 2 October owner documents were absorbed is in [the reconciliation record](RECONCILIATION_2026-10-02.md). This is one sequence, not a second roadmap.

| Order | Workstream | Requirements | State on the integration branch |
|---|---|---|---|
| A | Connected console, read-only and truthful | UX-001, UX-002, MEM-016, MEM-009 | Implemented on the branch and browser-tested against synthetic data ([receipt](evidence/console-connected/RECEIPT.md)). |
| B | Selection-aware questions on the existing queue | INT-001, UX-002, MEM-006 | Implemented on the branch; no model configured, so no reasoning quality claimed. |
| C | Remember, retrieve, correct, forget; identity and grants; lexical baseline | MEM-004 to MEM-013, SYS-001, SYS-002 (M02 to M06) | M01, M03, M04 and M06 implemented on the branch; M05 in progress (no encryption or key custody); M02 partial. Private data stays gated by M02/M05. |
| D | Executive records on authoritative data | ATT-002, ATT-001, ACT-001 | Not started. Needs C's provenance and invalidation rules. |
| E1 | Local job coordinator (research stage 0) | RUN-002, RUN-003, RUN-001, SYS-003 | Partial on the branch: durable jobs, local-subprocess worker in the host, reconnectable events, bounded cache, HTTP routes ([design and evidence](JOBS.md)). Remote stages wait for owner decisions. |
| E2 | Files, distributed nodes, remote workers | SYS-003, RUN-002, RUN-003, MEM-014 | Research complete ([evidence](../research/INFRASTRUCTURE_2026-10-02.md)); provider decisions needed. |
| E3 | Connectors, specialist products, voice, native packaging, release hardening | CON-001, OPS-001, OPS-002, VOI-001 | Not started; each needs real interfaces, accounts or hardware. |

## Work order

| Job | Work | Main acceptance |
|---|---|---|
| M01 | Harden selected-vault identity and Obsidian-compatible reading. | App-closed reads, rename/duplicate-ID/anchor fixtures, explicit exclusions, conflicts and source availability. |
| M02 | Person/device identity and finer source/capability grants. | Rotation/revocation, no accidental person merge, pre-retrieval and mid-request access denial. |
| M03 | Connect reviewed memory to conversation/context. | Only accepted/current/relevant authorised statements; sources and review basis retained; disputes and namesakes require clarification. |
| M04 | Explicit capture and approved inbox write-back. | Editable proposal, exact destination/diff approval, concurrency conflict, idempotent retry and result read-back. |
| M05 | Correction, deletion, private storage and restore lifecycle. | Dependency invalidation, export/deletion receipts, backup policy and no resurrection after restore. |
| M06 | Measured lexical retrieval baseline and deterministic fixtures. | FTS5 versus existing ranking, evidence recall, irrelevant context, bounded latency and no access leakage. |
| M07 | One optional temporal/semantic memory adapter. | Graphiti first candidate, Cognee alternative; provenance, permission, invalidation and deployment costs compared. No automatic installation. |
| M08 | Structured attachment/document ingestion. | Supported PDF/office parser output has page/block provenance, exact location checks and deletion lineage. |
| M09 | Explicit vault sync and host lifecycle. | One sync client per device, clear freshness/conflicts, no live DB file sync, backup/restore and stop behaviour. |
| M10 | Commitments, reviewed procedures and attention. | Explainable reminders/proposals, separate reports/observations, bounded routines and no retrieved-text execution. |
| M11 | One official account connector and approved external workflow. | Read-only test account first; then one harmless write with exact approval and capability-specific outcome reconciliation. |
| M12 | Voice, console projection and specialist/device integration contracts. | Visible push-to-talk and true graph states; actual engine/API review, no fabricated telemetry or operational-readiness claim. |

## Dependencies and parallelism

M01, M02 and retrieval-fixture preparation can begin independently. M03 can be developed on synthetic data against existing coarse scope checks while M02 matures; private-data release still requires M02 and M05. M04 requires the vault/context/grant contracts. M07 is an optional candidate experiment after the lexical and lifecycle baseline, not a dependency that blocks useful local memory.

Console work starts on a new focused branch from main against reviewed data contracts. The next missing console task is the authenticated real-backend adapter, not another visual restart. Do not overwrite it with an Obsidian clone or another admin dashboard. Design target remains the premium true-black/graphite/ivory console with sparse amber and a meaningful graph view.

The [programme issue #11](https://github.com/EmotiveImpact/Alfred/issues/11) coordinates memory work. Existing #2 core, #3 runtime and #4 voice remain separate workstreams; none is an already running autonomous agent. See [BUILD_PLAN.md](BUILD_PLAN.md) for handoff boundaries.

## Release gates

**Synthetic development:** source/claim/context contracts work with invented files; failures are retained. No model downloads, private vault access or external accounts are implicit.

**Personal test pilot:** M02 and M05 plus the relevant M01/M03/M04 tests pass, provider/data retention is approved, and a real selected test vault is exercised. Local encryption/key custody and backup limitations must be explicit.

**Useful personal assistant:** qualified reasoning, one real account workflow, attention and reliable host behaviour have measured evidence. A graph or procedural green CI is not sufficient.

**Team/operational expansion:** separate identity/tenancy, actual ENDSTATE/Noir contracts, supervised non-critical exercises and independent security/safety acceptance. No autonomous use of force.

## What not to restart

Do not rebuild the existing conversation queue, local draft ledger or manual reviewed-memory UI merely to change libraries. Do not install multiple memory engines with overlapping authority. Do not confuse official Obsidian headless file sync with an always-on ALFRED service. Do not infer semantic correctness from citations or dependency reuse from a public licence label.

The blocked live-model-comparison operation is not reauthorised by this roadmap and must not be rerouted. A permitted future evaluation requires its own tool access and explicit evidence; no new comparison result is claimed here.
