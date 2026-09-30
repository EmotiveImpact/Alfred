# ALFRED product requirements

<!-- ALFRED unified operational/executive baseline: 2026-09-27 -->

**Current product category: operational and executive intelligence.** See [positioning](PRODUCT_POSITIONING.md). The owner-authorised development PR stack is now merged into `main`; start new work there. The real local backend and the newer React/Three.js console are both preserved, but the console still uses fictional fixtures and needs its authenticated backend adapter. Consolidation is not deployment, external integration or completion of the planned memory jobs. The broad source-library catalogue, not earlier archive counts, is the current inventory.

Planning revision: 27 September 2026. Product baseline: local application v0.8 and the functional, separately tested React/Three.js fixture console, consolidated in main. This is a requirements update, not a v0.9 runtime release.

This is the current product source of truth. Implementation sequencing is in [ROADMAP.md](ROADMAP.md) and [the machine-readable memory backlog](../plans/memory-backlog.json). Older documents under archive/ retain historical decisions, not current completion claims.

## Product and problem

ALFRED is operational and executive intelligence delivered through a personal AI operating environment. It helps a person maintain context across people, projects, communications, knowledge and devices; recognise meaningful changes; reason with appropriate evidence; and carry out deliberately authorised work. It is not merely a note application, a chatbot skin, a coding agent or a military-only product.

The problem is broken continuity. People repeatedly reconstruct what was agreed, what changed, who is responsible, what remains unconfirmed and whether an action actually happened. The first experience must close that loop without demanding that the user maintain an elaborate graph manually.

Product identity remains ALFRED. Emotive Impact versus Black State ownership is unresolved. ENDSTATE stays an independent specialist analysis engine; Noir stays a separate operational system. A plan is not evidence of either integration.

## Executive and operational outcomes

Executive intelligence covers priorities, planning, decision briefs, commitments, preparation and follow-up. Operational intelligence covers current state, source health, changes, coordination and traceable authorised outcomes. Personal knowledge and everyday usefulness remain central. Existing requirement IDs continue to apply; this positioning does not invent completed functionality.

## Users and operating contexts

Begin with an individual founder/producer using a non-sensitive project and explicitly selected sources. Extend to personal life, home devices and small teams only after the relevant access and deployment gates. Operational scenarios begin with synthetic replay and supervised non-critical exercises, not safety reliance.

Personal, company and each client/operation are separate workspaces with separate grants, retention and provider-egress settings. Working context can be temporary. Private mode must make capture and processing status visible. Offline is a capability condition, not permission to describe cached information as current. A shared team workspace must not disclose the person's private memory.

## Baseline: implemented versus planned

Implemented v0.8: local SQLite records; credential-scoped browser access; read-only Markdown/project scanning; explicit note links; source excerpts; saved bounded conversations; optional tool-free local-model adapter; separate manually reviewed entities/statements; exact approval and local draft execution; bounded local report routines and history controls.

Not yet implemented: automatic reviewed-memory context injection; dependable general reasoning; automatic memory capture/extraction; full Obsidian compatibility; safe note write-back; mature person/device pairing; fine-grained source grants; application-level encryption; live account/device/voice connectors; production hosting or cross-device runtime synchronisation.

The v0.7 small-model experiment has documented relevance, abstention and conflict-handling failures. v0.8 added narrow literal evidence checks, not a semantic verifier. The previously blocked model-comparison operation remains blocked and must not be rerouted by this plan. No stronger-model result is claimed.

The newer React/TypeScript/Three.js console is now present in main. Its fictional fixtures are not real backend data. Preserve this functional frontend and the existing backend-connected web interface while implementing their authenticated adapter. The internal Obsidian console name is not an Obsidian note-app integration.

## M01 implementation checkpoint, 30 September 2026

The bounded selected-vault/read slice is implemented on a draft review branch from current main. [M01 acceptance and limits](evidence/memory-m01/RECEIPT.md) and the [read contract](OBSIDIAN_INTEGRATION.md) record catalogue identity, conservative rename/revision continuity, opt-in IDs, validated supported anchors, exclusions and availability. This advances MEM-001/002/003/012 for Markdown without claiming complete sync, deletion/restore, native Obsidian, private-vault or model-context acceptance. M02-M12 remain planned.

## First complete personal-memory experience

1. The user selects an allowed local vault/project and can inspect what will be indexed. Obsidian is optional.
2. The user asks a question. ALFRED retrieves authorised source passages and relevant accepted statements, with dates and uncertainty visible.
3. The user says 'remember this'. ALFRED proposes a small, editable memory with a source, scope, memory type and retention policy. Nothing is silently promoted to permanent fact.
4. The user accepts it. ALFRED records the judgement and optionally writes an explicitly approved note to its own inbox area, without overwriting unrelated human writing.
5. A relevant source changes. ALFRED shows the difference, invalidates affected context and asks for a fresh review where necessary.
6. The user corrects or forgets it. Current retrieval stops using the old value; the UI reports what remains in permitted audit metadata or backups.
7. A follow-up asks for work. The existing separate authority, approval, execution and result path applies. Remembering something never grants permission to act on it.

This is a target workflow. Some steps exist separately, but the complete loop is not shipped by this planning update.

## Memory requirements

| ID | Requirement | Current status / acceptance |
|---|---|---|
| MEM-001 | Optional human-owned Markdown vaults, readable without ALFRED or Obsidian. | Partial: bounded read-only scanner exists. Harden configuration, exclusions and source health. |
| MEM-002 | Stable document identity and revision history across edits, renames, deletes and sync conflicts. | Planned extension: do not infer identity from a filename or same display name alone; duplicate IDs require review. |
| MEM-003 | Preserve source location, revision/hash and evidence basis on every derived memory. | Partial: note/claim provenance exists. Extend to all derived records and new document types. |
| MEM-004 | Keep working, episodic, semantic, preference, commitment and procedural memory distinct. | Partial bounded conversations/manual statements; policies and automatic capture remain planned. |
| MEM-005 | Proposed memories are inspectable, editable and reviewable before durable promotion. | Manual statement review exists; explicit capture and extraction proposals are planned. |
| MEM-006 | Use reviewed statements in questions only while accepted, authorised, current, unambiguous and relevant. | Planned bridge; keep original evidence and human-judgement labels. |
| MEM-007 | Preserve changing relationships using valid time and recorded time, disputes and supersession. | Partial narrow validity/conflict rules; full temporal history/query contract remains planned. |
| MEM-008 | Hybrid retrieval earns its complexity against a lexical baseline. | Current simple keyword/link retrieval. FTS5, optional embeddings and reranking are planned experiments. |
| MEM-009 | Apply identity/source access before retrieval, traversal, embeddings, reranking and provider egress; recheck before response. | Coarse credential/workspace checks exist; finer grants and opaque-leakage tests are required. |
| MEM-010 | Correct/delete/revoke through dependent statements, snippets, indexes, summaries, vectors and caches. | Partial current-source invalidation. Complete deletion receipts, tombstones and backup accounting are planned. |
| MEM-011 | Any vault write is a separate capability with exact content, destination, precondition and approval. | Not implemented. Start new notes in ALFRED/Inbox only; no unrestricted agent edits. |
| MEM-012 | Search indexes and graph projections can be rebuilt without losing source or review history. | Some index rebuild exists; complete reconciliation and migration tests are required. |
| MEM-013 | Provide portable, inspectable exports and clear retention settings. | Partial exports exist. Redaction, scope-limited manifests and lifecycle completeness remain planned. |
| MEM-014 | Sync files without conflating file sync with identity, memory-ledger or runtime sync. | Not implemented. One selected sync client per device, explicit conflicts and restore rules. |
| MEM-015 | Procedures are reviewed descriptions/workflow proposals, never executable instructions merely because retrieved. | Boundary retained; workflow learning and versioned procedure registry are future work. |
| MEM-016 | Keep authored note links, reviewed claims and speculative suggestions visually distinct. | Separate v0.8 graphs exist. Bind future sphere/console views to real scoped data and truthful states. |

## Whole-product requirements retained

| ID | Requirement | Acceptance direction |
|---|---|---|
| SYS-001 | Persistent person identity, paired devices, scoped credentials and revocation. | Migrate from credential-private history without automatically joining different people. |
| SYS-002 | Private storage, secrets, exports, backups and restore lifecycle. | Approved key custody, deletion accounting and tested recovery before sensitive data. |
| INT-001 | Replaceable reasoning/session runtime and bounded context assembly. | One authoritative executor; no model holds connector-wide credentials. |
| INT-002 | Evaluate answer support, missing facts, contradictions and multi-turn context. | Publish failed cases and denominators; schema-valid citations are insufficient. |
| ACT-001 | Exact action approvals, outbox, capability-specific idempotency and result verification. | Local drafts exist; each future connector needs its own effect/reconciliation acceptance. |
| ATT-001 | Task-aware attention and durable, explicitly authorised routines. | Fixed routines exist; learned relevance remains advisory until measured. |
| CON-001 | Official account/device connectors with least access and observable freshness. | Read-only test account first, then one harmless approved write. |
| VOI-001 | Voice shares context without confusing generated, played and acknowledged speech. | Visible push-to-talk first; interruption/reconnect tests on actual hardware. |
| OPS-001 | Role-limited team and operational workspaces, specialist-engine adapters. | Read actual ENDSTATE/Noir contracts; keep simulation distinct from observation. |
| UX-001 | Premium operational and executive intelligence console, not an admin-dashboard default. | Preserve the approved black/graphite/ivory, sparse-amber direction and concurrent console work; do not claim implementation matches the target before inspection. |
| RUN-001 | Explicit host lifecycle, pause, recovery, bounded offline capability and health. | Local process exists; no always-on deployment or native background-device claim yet. |

## Acceptance and evaluation

Evaluate the complete remember/retrieve/correct/forget/action loop with invented data before private-data pilot. Mandatory negative cases include wrong workspace, same-name people, duplicate document IDs, lost source, revoked permission during model work, disputed memory, changed source during approval, sync conflict, stale backup restoration and a source note containing hostile instructions.

Report evidence recall, unsupported-answer rate, appropriate abstention, temporal/conflict handling, stale-memory use, deletion completion, p50/p95 retrieval latency, model tokens and indexing resource costs. Separate correctness from responsiveness. Initial retrieval budget is no larger than the existing bounded packet until a measured change is approved. Set performance targets against named hardware and data volumes, not invented product-wide numbers.

LongMemEval and LongMemEval-V2 are evaluation references, not proof that ALFRED passes them. No new model evaluation is launched by this document. A later permitted evaluation must keep answer keys out of model inputs, record frozen datasets/configuration, and respect the earlier tool restriction.

## Scope and non-goals

Do not train a foundation model, rewrite a note editor, require a graph server, install every memory framework or introduce custom hardware to prove the first loop. Do not store everything forever. No covert audio/screen collection, unattended financial/security-sensitive control, autonomous use of force or safety-critical availability claim.

Obsidian is the recommended optional editor, not a mandatory dependency. Third-party capabilities are candidates until version, licence, data egress, deletion and failure behaviour are tested. Code, model, plugin and hosted-service terms require separate review. A root permissive licence is not blanket clearance.

## Delivery status for this revision

This revision changes research, requirements and execution plans. It does not connect a real vault, install memory engines, add external actions or upgrade the runtime. Existing source/tests and separate console work must be preserved. See [memory architecture](MEMORY_ARCHITECTURE.md), [Obsidian integration](OBSIDIAN_INTEGRATION.md), [repository landscape](../research/MEMORY_LANDSCAPE_2026-09-27.md) and [architecture decision](adr/MEMORY-001.md).
