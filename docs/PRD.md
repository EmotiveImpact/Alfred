# ALFRED product requirements

**Current category: operational and executive intelligence. Planning revision: 3 October 2026.** The requirements remain the product source of truth. [ROADMAP.md](ROADMAP.md) gives the sequence, [REMAINING_BUILD_PLAN.md](REMAINING_BUILD_PLAN.md) the work packages, [the requirement register](../plans/requirement-register.json) their delivery states, and [NEXT_STAGE.md](NEXT_STAGE.md) the current execution and activation gates. M01-M12 is a bounded memory programme, not the whole application.

Main `75947b8dd59a3161c862d2533850a032994778e2` merged PR #18, including #15/#16/#17. The console is now authenticated and backend-connected. This documentation revision reconciles that fact and the later staged instruction; it changes no runtime, dependencies or deployment. The [previous PRD](archive/pre-stage-2026-10-03/PRD.md) is preserved verbatim, including its earlier checkpoints. Historical status wording is not present completion evidence.

## Product and problem

ALFRED is operational and executive intelligence delivered through a personal AI operating environment. It helps a person maintain context across people, projects, communications, knowledge and devices; recognise meaningful changes; reason with appropriate evidence; and carry out deliberately authorised work. It is not merely a note application, a chatbot skin, a coding agent or a military-only product.

The problem is broken continuity. People repeatedly reconstruct what was agreed, what changed, who is responsible, what remains unconfirmed and whether an action actually happened. The first experience must close that loop without demanding that the user maintain an elaborate graph manually.

Product identity remains ALFRED. Emotive Impact versus Black State ownership is unresolved. ENDSTATE stays an independent specialist analysis engine; Noir stays a separate operational system. A plan is not evidence of either integration.

## Executive and operational outcomes

Executive intelligence covers priorities, planning, decision briefs, commitments, preparation and follow-up. Operational intelligence covers current state, source health, changes, coordination and traceable authorised outcomes. Personal knowledge and everyday usefulness remain central. All 33 existing requirement IDs are retained; the stage adds no invented completed functionality or competing product catalogue.

## Users and operating contexts

Begin with an individual founder/producer using a non-sensitive project and explicitly selected sources. Extend to personal life, home devices and small teams only after the relevant access and deployment gates. Operational scenarios begin with synthetic replay and supervised non-critical exercises, not safety reliance.

Personal, company and each client/operation are separate workspaces with separate grants, retention and provider-egress settings. Working context can be temporary. Private mode must make capture and processing status visible. Offline is a capability condition, not permission to describe cached information as current. A shared team workspace must not disclose the person's private memory. The current one-workspace-per-credential implementation is not yet that complete team/multi-workspace experience.

## Implemented baseline versus release readiness

The merged implementation includes the local Python/SQLite core, original web interface, authenticated React/Three.js console projection, selected-vault identity, reviewed-memory context, preview/review capture, approved create-only inbox writes, temporal review/history, executive records, routines, device pairing/grants, bounded local jobs/cache, read-only calendar/contact export importers, read-aloud output, host health and index rebuild.

Individual requirements remain partial where specified in the register. Current source, original support, independent authority, test scope and the [audit](AUDIT_2026-10-03.md) take precedence over a polished screenshot or an old draft-PR label. The approval-visibility concern is an investigation request, not a proven exploit. No private-data, native application, live account, microphone, second-node, sandbox, cloud-storage or commercial deployment is established by this merge.

The optional local-model adapter is tool-free. A dependable general reasoning runtime and semantic answer-quality evaluation remain outstanding. Literal support accounting and reviewed-memory correctness are not semantic verification. The previously blocked live-model comparison remains blocked and must not be rerouted.

## First complete personal-memory experience

1. The user selects an allowed vault/project and can inspect what will be indexed. Obsidian is optional.
2. A question retrieves authorised source passages and relevant accepted statements, with original support, dates and uncertainty visible.
3. 'Remember this' proposes small, editable memory with source, scope, type and retention; nothing is silently promoted to fact.
4. Acceptance records the judgement. A separate exact approval may create a note under ALFRED/Inbox without overwriting human content.
5. Source changes are visible and invalidate affected context or require renewed review.
6. Correction/forgetting removes old values from current retrieval and reports remaining permitted metadata, backups and exports honestly.
7. Work follows the existing separate proposal, authority, approval, execution and result path. Remembering never grants permission.

Substantial parts are integrated, but private-pilot acceptance still requires the remaining identity, storage and lifecycle safeguards plus selected real-data authorisation. Test the complete flow, not merely each button.

## Memory requirements

| ID | Requirement | Acceptance direction |
|---|---|---|
| MEM-001 | Optional human-owned Markdown vaults, readable without ALFRED or Obsidian. | Preserve the bounded scanner; configuration, exclusions, source health, compatibility and documents remain explicit. |
| MEM-002 | Stable document identity and revision history across edits, renames, deletes and sync conflicts. | Do not infer identity from filename or shared display name; retain rename evidence and duplicate-ID review. |
| MEM-003 | Preserve source location, revision/hash and evidence basis on every derived memory. | Extend the implemented note/claim provenance to every derived record and new document type. |
| MEM-004 | Keep working, episodic, semantic, preference, commitment and procedural memory distinct. | Preserve bounded conversations/manual types; capture policies and automatic proposals must remain explicit. |
| MEM-005 | Proposed memories are inspectable, editable and reviewable before durable promotion. | Preserve preview and separate acceptance; extraction never silently accepts itself. |
| MEM-006 | Use reviewed statements in questions only while accepted, authorised, current, unambiguous and relevant. | Preserve the implemented bridge, exact original evidence and human-judgement labels. |
| MEM-007 | Preserve changing relationships using valid time and recorded time, disputes and supersession. | Preserve temporal review/history and explicit lineage; state the limits of as-of queries and historical validity. |
| MEM-008 | Hybrid retrieval earns its complexity against a lexical baseline. | Keep frozen evaluation, evidence recall, irrelevant context, abstention, latency and access tests. No automatic new engine. |
| MEM-009 | Apply identity/source access before retrieval, traversal, embeddings, reranking and provider egress; recheck before response. | Default-deny migration, opaque-leakage and mid-request revocation tests, including projections and action visibility. |
| MEM-010 | Correct/delete/revoke through dependent statements, snippets, indexes, summaries, vectors and caches. | Complete receipts, tombstones, dependent deletion and backup/restore accounting; no unsupported secure-erasure claim. |
| MEM-011 | Any vault write is a separate capability with exact content, destination, precondition and approval. | Preserve approved create-only ALFRED/Inbox writes; any broader write has independent acceptance. |
| MEM-012 | Search indexes and graph projections can be rebuilt without losing source or review history. | Preserve atomic rebuild, catalogue/review history and migration tests; extend deliberately to new sources. |
| MEM-013 | Provide portable, inspectable exports and clear retention settings. | Scope-limited manifests, redaction, history/lifecycle completeness, encryption and explicit exclusions. |
| MEM-014 | Sync files without conflating file sync with identity, memory-ledger or runtime sync. | One selected file-sync policy per device, conflict/freshness and restore tests; no live database folder sync. |
| MEM-015 | Procedures are reviewed descriptions/workflow proposals, never executable instructions merely because retrieved. | Preserve read-only registry and no-execution boundary; learning/versioned workflows remain reviewed future work. |
| MEM-016 | Keep authored note links, reviewed claims and speculative suggestions visually distinct. | Preserve the real scoped graph layers; no decorative counts or fabricated suggestion layer. |

## Whole-product requirements retained

| ID | Requirement | Acceptance direction |
|---|---|---|
| SYS-001 | Persistent person identity, paired devices, scoped credentials and revocation. | Mature pairing and source defaults; migrate credential-private history without joining different people. |
| SYS-002 | Private storage, secrets, exports, backups and restore lifecycle. | Approved key custody, deletion accounting and tested recovery before sensitive data. |
| INT-001 | Replaceable reasoning/session runtime and bounded context assembly. | One authoritative executor; no model holds connector-wide credentials. |
| INT-002 | Evaluate answer support, missing facts, contradictions and multi-turn context. | Publish failed cases and denominators; schema-valid citations and word coverage are insufficient. |
| ACT-001 | Exact action approvals, outbox, capability-specific idempotency and result verification. | Preserve local machinery; each external effect needs separate visibility, dispatch and reconciliation acceptance. |
| ATT-001 | Task-aware attention and durable, explicitly authorised routines. | Preserve stated rules, budgets and pause; learned relevance advisory until measured, delivery modes explicit. |
| CON-001 | Official account/device connectors with least access and observable freshness. | Existing export importers are not live accounts; read-only test account first, then a harmless approved write. |
| VOI-001 | Voice shares context without confusing generated, played and acknowledged speech. | Existing read-aloud is output only; visible push-to-talk needs approval and actual interruption/reconnect hardware tests. |
| OPS-001 | Role-limited team and operational workspaces, specialist-engine adapters. | Read actual interfaces, preserve tenancy and distinguish simulation from observation. |
| UX-001 | Premium operational and executive intelligence console, not an admin-dashboard default. | Preserve approved black/graphite/ivory, sparse amber, interactive sphere and actual connected acceptance. |
| RUN-001 | Explicit host lifecycle, pause, recovery, bounded offline capability and health. | Foreground host exists; managed service, native client and remote hosting have separate tests and activation gates. |

## Whole-product requirements added 2 October 2026

Origins remain the [earlier reconciliation](RECONCILIATION_2026-10-02.md) and preserved sources. The [later conversation](sources/2026-10-03/LATER_CHAT_RECONCILIATION.md) clarifies the deployment research without choosing providers or relocating data by implication.

| ID | Requirement | Acceptance direction |
|---|---|---|
| UX-002 | Project-centred focus: selecting a record sets a stable, visible working context that the inspector, graph and next question share; changing workspace or authority clears or revalidates it. | Select, inspect, follow supported links, ask contextually and clear focus. Shared names never create edges; unavailable/denied states never fall back to fixtures. |
| ATT-002 | Executive records: goals, priorities, commitments, decisions, project milestones, preparation and follow-up held as authoritative records, with sources, owners and dates. | Panel and graph read the same records; recommendations are not obligations, progress has defined inputs, cross-project insight requires permitted support. |
| RUN-002 | Distributed operation across enrolled trusted computers and an optional always-on coordinator, with one authority per job. | Enrolment/revocation, node capabilities, placement, durable jobs, cancellation, bounded retries, reconciliation and offline freshness; no shared writable database file. |
| RUN-003 | Isolated execution of bounded jobs on local or remote workers, with persistent and disposable lifecycles evaluated separately. | Limited inputs/files/tools, scoped credentials, resource/cost limits, cancellation and verifiable outputs; forks never duplicate authority or effects. |
| SYS-003 | Expandable file access: authorised on-demand reads, a bounded local cache, explicit offline availability, revisions, conflicts, quotas, export and recovery. | Read without a full local copy, exclude revoked/unapproved files, enforce cache bounds and separate database/secrets/files/indexes/scratch. |
| OPS-002 | Common capability contract for independent specialist products (ENDSTATE, 8BALL, Noir/Black State, Loc8, God's Eye). | Stable identity, capabilities, observation basis, original timestamps, freshness, simulation/replay, permissions and receipts. Contract v1/synthetic adapter is not real product integration. |

## Acceptance and evaluation

Evaluate the complete loop with invented data before private pilot. Mandatory negative cases include wrong workspace, same-name people, duplicate IDs, lost source, revoked permission during model work, disputed memory, changed source during approval, sync conflict, stale backup restoration and hostile source instructions.

Report evidence recall, unsupported-answer rate, appropriate abstention, temporal/conflict handling, stale-memory use, deletion completion, p50/p95 retrieval latency, tokens and indexing resources on named configurations. Separate correctness from responsiveness. Do not enlarge bounded packets without measured justification.

LongMemEval and LongMemEval-V2 remain evaluation references, not proof ALFRED passes them. A permitted future evaluation keeps answer keys out of inputs and records frozen data/configuration. No new model evaluation or bypass of the earlier restriction is authorised by this document.

## Scope and non-goals

Do not train a foundation model, rewrite a note editor, require a graph server, install every framework or introduce custom hardware to prove the first loop. Do not store everything forever. No covert audio/screen capture, unattended financial/security-sensitive control, autonomous use of force or safety-critical availability claim.

Obsidian is optional. Code, model, plugin and service terms need separate review. Third-party candidates require pinned source/licence, egress, deletion and failure testing before adoption. Tauri, always-on VPS Core and Cloud/Private/Sovereign are research proposals with separate promotion gates, not runtime facts. Commercial provider/ownership research stays groundwork; no partner relationship, validated valuation or spend authority is implied.

The full PRD remains. Under PILOT-GROUNDWORK, build current-product trust/reliability and prepare later native/distributed/commercial work; do not automatically activate later stages because a task or PR passes.
