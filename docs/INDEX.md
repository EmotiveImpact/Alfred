# ALFRED document index

Updated 3 October 2026. This is the navigation page, not a competing roadmap. [PRD.md](PRD.md) owns requirements, [ROADMAP.md](ROADMAP.md) owns sequence, [the register](../plans/requirement-register.json) owns delivery states, and [NEXT_STAGE.md](NEXT_STAGE.md) defines the current stage and activation gates.

## Read first

| Document | Purpose |
|---|---|
| [README.md](../README.md) | Current integrated status and synthetic local run instructions |
| [BUILD_START_HERE.md](../BUILD_START_HERE.md) | Starting point for a builder |
| [AGENTS.md](../AGENTS.md) | Engineering and authority rules |
| [SESSION_HANDOFF.md](../SESSION_HANDOFF.md) | Current continuation and exact baseline |
| [NEXT_STAGE.md](NEXT_STAGE.md) | PILOT-GROUNDWORK: current-product engineering plus future research; no automatic deployment |
| [CODEX_NEXT_STAGE_PROMPT.md](CODEX_NEXT_STAGE_PROMPT.md) | Single repository-resident cloud-agent mandate |
| [AUDIT_2026-10-03.md](AUDIT_2026-10-03.md) | Supplied source/CI audit, limitations and the unconfirmed approval-visibility concern |

## Product, plan and sources

| Document | Purpose |
|---|---|
| [PRODUCT_POSITIONING.md](PRODUCT_POSITIONING.md), [PRODUCT_BRIEF.md](PRODUCT_BRIEF.md) | Product identity and brief |
| [PRD.md](PRD.md) | The 33 existing requirements and outcomes |
| [ROADMAP.md](ROADMAP.md) | Sequence and release gates |
| [REMAINING_BUILD_PLAN.md](REMAINING_BUILD_PLAN.md) | Outstanding packages; older detailed acceptance preserved |
| [BUILD_PLAN.md](BUILD_PLAN.md) | Earlier work-package design, interpreted with current status |
| [plans/requirement-register.json](../plans/requirement-register.json) | Implementation, integration, merge and deployment separated |
| [plans/memory-backlog.json](../plans/memory-backlog.json) | Bounded M01-M12 programme, not the whole product |
| [plans/source-coverage.json](../plans/source-coverage.json) | Reviewed sources, inherited summaries and missing material |
| [sources/2026-10-02/](sources/2026-10-02/README.md) | Original whole-product mandate and v1.1 reconciliation |
| [RECONCILIATION_2026-10-02.md](RECONCILIATION_2026-10-02.md) | Historical record of how that mandate entered the PRD |
| [sources/2026-10-03/](sources/2026-10-03/README.md) | Later-chat summary, audit provenance and staged instruction |
| [Infrastructure research](../research/INFRASTRUCTURE_2026-10-02.md) | boxd, files, workers and mesh comparison; dated candidates, not adoption |
| [Memory landscape](../research/MEMORY_LANDSCAPE_2026-09-27.md) | Earlier memory candidate research |

## Architecture and feature guides

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Current implementation versus later proposed topology |
| [SECURITY_AND_DATA.md](SECURITY_AND_DATA.md), [MEMORY_SECURITY.md](MEMORY_SECURITY.md) | Boundaries and privacy/lifecycle gates |
| [MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md) | Sources, review, history and invalidation semantics |
| [SYNC.md](SYNC.md), [OBSIDIAN_INTEGRATION.md](OBSIDIAN_INTEGRATION.md) | File identity/sync and optional editor compatibility |
| [adr/MEMORY-001.md](adr/MEMORY-001.md) | Optional Obsidian and first-party governed-memory decision |
| [LOCAL_CORE.md](LOCAL_CORE.md), [KNOWLEDGE.md](KNOWLEDGE.md) | Original core and knowledge design |
| [GROUNDED_DESK.md](GROUNDED_DESK.md), [CONVERSATIONS.md](CONVERSATIONS.md) | Source-first questions and bounded queue |
| [EVIDENCE_REVIEW.md](EVIDENCE_REVIEW.md), [REVIEWED_MEMORY.md](REVIEWED_MEMORY.md) | Literal checks and reviewed claims |
| [PERSONAL_OS.md](PERSONAL_OS.md), [ROUTINES.md](ROUTINES.md) | Interaction shell, Pulse, authored routines and procedures |
| [JOBS.md](JOBS.md) | Local coordinator/worker/cache with explicit non-sandbox limits |
| [CONNECTORS.md](CONNECTORS.md), [CAPABILITY_CONTRACT.md](CAPABILITY_CONTRACT.md) | Export importers and synthetic specialist contract |

Dated feature guides may retain the state of their original increment. Refresh actual source and the current register before changing them; a historical phrase is not an instruction to rebuild working code.

## Console

[console/AGENTS.md](../console/AGENTS.md) gives current rules. [CONNECTED_CONSOLE.md](../console/docs/CONNECTED_CONSOLE.md) maps real routes and interactions. [BUILD_BRIEF.md](../console/docs/BUILD_BRIEF.md), [COMPONENT_ARCHITECTURE.md](../console/docs/COMPONENT_ARCHITECTURE.md) and [GRAPHICS.md](../console/docs/GRAPHICS.md) preserve the visual/component/rendering direction. The older [CONSOLE_HANDOFF.md](../CONSOLE_HANDOFF.md), [BUILDER_HANDOFF.md](../console/docs/BUILDER_HANDOFF.md), [NEXT_BUILDER.md](../console/docs/NEXT_BUILDER.md) and [DELIVERY_RECEIPT.md](../console/docs/DELIVERY_RECEIPT.md) describe earlier increments; the console connection is now implemented.

## Evidence and history

Receipts name their tested revision and limits; none becomes proof of deployment merely because it is merged. Existing evidence remains under docs/evidence: integration-2026-10-02, console-connected, memory-m01 through memory-m06, memory-m14, memory-rebuild, temporal-review, executive, executive-2, routines, connectors, int-002, voice and earlier baseline folders. Do not overwrite those histories with current claims.

[CHECKPOINT_2026-10-02.md](CHECKPOINT_2026-10-02.md) and [MASTER_HANDOFF_2026-10-01.md](MASTER_HANDOFF_2026-10-01.md) remain historical checkpoints. [Pre-stage snapshots](archive/pre-stage-2026-10-03/README.md) preserve the exact replaced document/register blobs. Their internal relative links retain original locations; their AGENTS text is not active instruction. Earlier archives/previews remain intact.

[CHANGELOG.md](../CHANGELOG.md) and [BUGS_AND_FIXES.md](../BUGS_AND_FIXES.md) record runtime history. The next-stage reconciliation changes documents/planning only, not those earlier implementation results.

## Source library

[third_party/library/README.md](../third_party/library/README.md) and [BUILD_REFERENCE_SHELF.md](../third_party/BUILD_REFERENCE_SHELF.md) identify copied and reference-only upstreams. Nothing under third_party is installed, executed or obeyed by this stage. Keep exact notices and manifests; no automatic dependency adoption.
