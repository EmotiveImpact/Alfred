# Document index

Every document in the repository, what it is for and when to read it. Documents are grouped by purpose, not by folder. Dated documents are evidence of their own checkpoint; the current state of any requirement is always [plans/requirement-register.json](../plans/requirement-register.json).

## Start here

| Document | Purpose |
|---|---|
| [README.md](../README.md) | What ALFRED is, how to get it running, how to verify it |
| [CHANGELOG.md](../CHANGELOG.md) | What changed, newest first, with commits |
| [BUGS_AND_FIXES.md](../BUGS_AND_FIXES.md) | Every defect, its cause and its fix |
| [BUILD_START_HERE.md](../BUILD_START_HERE.md) | Orientation for anyone about to build |
| [AGENTS.md](../AGENTS.md) | Engineering rules that bind every contributor and agent |
| [SESSION_HANDOFF.md](../SESSION_HANDOFF.md) | Pointer to the latest checkpoint and what remains |
| [CHECKPOINT_2026-10-02.md](CHECKPOINT_2026-10-02.md) | The current resume point: branch, state, verification, owner decisions |

## Product

| Document | Purpose |
|---|---|
| [PRODUCT_POSITIONING.md](PRODUCT_POSITIONING.md) | The product category: operational and executive intelligence |
| [PRODUCT_BRIEF.md](PRODUCT_BRIEF.md) | The short product brief |
| [PRD.md](PRD.md) | Requirements, grouped by workstream, with IDs used everywhere else |
| [ROADMAP.md](ROADMAP.md) | Execution order and dependencies |
| [REMAINING_BUILD_PLAN.md](REMAINING_BUILD_PLAN.md) | Everything still to build, in order, with sizes, acceptance and owner decisions |
| [BUILD_PLAN.md](BUILD_PLAN.md) | Work packages |
| [RECONCILIATION_2026-10-02.md](RECONCILIATION_2026-10-02.md) | How the owner's mandate became the requirement register |
| [sources/2026-10-02/](sources/2026-10-02/README.md) | The owner-supplied mandate and reconciliation documents |

## Design and architecture

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System boundaries, components and where authority sits |
| [MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md) | Governed memory: sources, reviewed statements, history, deletion |
| [MEMORY_SECURITY.md](MEMORY_SECURITY.md) | Privacy and lifecycle gates for memory |
| [SECURITY_AND_DATA.md](SECURITY_AND_DATA.md) | Data boundaries, sessions, CSRF, loopback, what is never sent |
| [SYNC.md](SYNC.md) | Four kinds of sync kept apart; placement guard; conflict copies |
| [OBSIDIAN_INTEGRATION.md](OBSIDIAN_INTEGRATION.md) | Optional Obsidian over user-owned Markdown |
| [adr/MEMORY-001.md](adr/MEMORY-001.md) | Decision: optional Obsidian, first-party governed memory |
| [CAPABILITY_CONTRACT.md](CAPABILITY_CONTRACT.md) | Contract for independent specialist products (OPS-002) |

## Feature guides (how each part works)

| Document | Covers |
|---|---|
| [LOCAL_CORE.md](LOCAL_CORE.md) | The loopback service, store, sessions and approvals |
| [KNOWLEDGE.md](KNOWLEDGE.md) | Vault scanning, note identity, the knowledge desk |
| [GROUNDED_DESK.md](GROUNDED_DESK.md) | Source-first questions |
| [CONVERSATIONS.md](CONVERSATIONS.md) | The bounded conversation queue |
| [EVIDENCE_REVIEW.md](EVIDENCE_REVIEW.md) | The literal evidence checker on answers |
| [REVIEWED_MEMORY.md](REVIEWED_MEMORY.md) | Manual reviewed statements, conflicts, validity, retention |
| [PERSONAL_OS.md](PERSONAL_OS.md) | The interaction shell and Pulse |
| [ROUTINES.md](ROUTINES.md) | Authored routines, nominations and the procedure registry |
| [JOBS.md](JOBS.md) | The bounded local job coordinator |
| [CONNECTORS.md](CONNECTORS.md) | Read-only calendar and contacts export connectors |
| [console/docs/CONNECTED_CONSOLE.md](../console/docs/CONNECTED_CONSOLE.md) | Every console feature that talks to the real backend, with routes |

## Console

| Document | Purpose |
|---|---|
| [CONSOLE_HANDOFF.md](../CONSOLE_HANDOFF.md) | The console lane and its rules |
| [console/README.md](../console/README.md) | Running, building and testing the console |
| [console/AGENTS.md](../console/AGENTS.md) | Console-specific engineering rules |
| [console/docs/BUILD_BRIEF.md](../console/docs/BUILD_BRIEF.md) | Owner-selected visual direction |
| [console/docs/COMPONENT_ARCHITECTURE.md](../console/docs/COMPONENT_ARCHITECTURE.md) | Component and state architecture |
| [console/docs/GRAPHICS.md](../console/docs/GRAPHICS.md) | Three.js and shader implementation |
| [console/docs/BUILDER_HANDOFF.md](../console/docs/BUILDER_HANDOFF.md), [NEXT_BUILDER.md](../console/docs/NEXT_BUILDER.md), [DELIVERY_RECEIPT.md](../console/docs/DELIVERY_RECEIPT.md) | Handoffs and receipt for refinement 02 |

## Plans and registers (machine-checked)

| File | Purpose | Check |
|---|---|---|
| [plans/requirement-register.json](../plans/requirement-register.json) | Decision, implementation, integration, merge and deployment state of every requirement, with evidence | `tools/check_requirement_register.py` |
| [plans/memory-backlog.json](../plans/memory-backlog.json) | The 12 memory jobs M01 to M12 | `tools/check_memory_plan.py` |
| [plans/source-coverage.json](../plans/source-coverage.json) | Which owner documents each requirement came from | `tools/check_requirement_register.py` |
| [research/](../research/) | Memory landscape and infrastructure research behind the plans | |

## Evidence and receipts

Each receipt names the exact tested commit, the commands run and their results, and what is not done. They are evidence of their checkpoint, never a claim about the current branch.

| Folder | Evidence for |
|---|---|
| [evidence/integration-2026-10-02](evidence/integration-2026-10-02/RECEIPT.md) | Integrating PRs #15, #16 and #17 |
| [evidence/console-connected](evidence/console-connected/RECEIPT.md) | The connected console |
| [evidence/memory-m01](evidence/memory-m01/RECEIPT.md) to [memory-m06](evidence/memory-m06/RECEIPT.md), [memory-m14](evidence/memory-m14/RECEIPT.md), [memory-rebuild](evidence/memory-rebuild/RECEIPT.md) | Memory jobs |
| [evidence/temporal-review](evidence/temporal-review/RECEIPT.md) | Temporal review (MEM-007) |
| [evidence/executive](evidence/executive/RECEIPT.md), [executive-2](evidence/executive-2/RECEIPT.md) | Executive records and workflows |
| [evidence/routines](evidence/routines/RECEIPT.md) | Routines (M10) |
| [evidence/connectors](evidence/connectors/RECEIPT.md) | Export connectors |
| [evidence/int-002](evidence/int-002/RECEIPT.md) | Answer support evaluation |
| [evidence/voice](evidence/voice/RECEIPT.md) | Spoken output |
| [evidence/unified-2026-09-27](evidence/unified-2026-09-27/) | The unified baseline |
| desk-v03, knowledge-v04, grounded-v05, personal-os-v06, conversation-v07, memory-v08 | The pre-baseline increments |

## History and archive

| Document | Purpose |
|---|---|
| [CONSOLIDATION_2026-09-27.md](CONSOLIDATION_2026-09-27.md) | How the stacked PRs were merged into main |
| [MASTER_HANDOFF_2026-10-01.md](MASTER_HANDOFF_2026-10-01.md) | The paused-programme handoff before the 2 October build |
| [archive/](archive/) | Superseded versions of architecture, build plan, brief and roadmap, kept verbatim |
| [previews/](previews/) | Static previews of earlier interface increments |

## Source library

| Document | Purpose |
|---|---|
| [third_party/library/README.md](../third_party/library/README.md) | The catalogue of research repositories, their licences and what was copied |
| [third_party/BUILD_REFERENCE_SHELF.md](../third_party/BUILD_REFERENCE_SHELF.md) | The earlier focused shelf |

Nothing under `third_party/` is ALFRED code. It is not installed, imported, executed or obeyed.

## Keeping this index current

Add a row when a document is created, move it to history when it is superseded, and never delete the superseded file; archive it. The checks in `tools/check_memory_plan.py` verify local links in the documents it tracks.
