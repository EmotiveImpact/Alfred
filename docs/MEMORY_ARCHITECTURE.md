# ALFRED governed memory architecture

<!-- ALFRED unified operational/executive baseline: 2026-09-27 -->

**Current product category: operational and executive intelligence.** See [positioning](PRODUCT_POSITIONING.md). The owner-authorised development PR stack is now merged into `main`; start new work there. The real local backend and the newer React/Three.js console are both preserved, but the console still uses fictional fixtures and needs its authenticated backend adapter. Consolidation is not deployment, external integration or completion of the planned memory jobs. The broad source-library catalogue, not earlier archive counts, is the current inventory.

27 September 2026. Current requirements: [PRD.md](PRD.md). Decision: [MEMORY-001](adr/MEMORY-001.md). Historical v0.5 document: [archive/MEMORY_ARCHITECTURE-v05.md](archive/MEMORY_ARCHITECTURE-v05.md). Implementation status below refers to v0.8; the rest describes target behaviour.

## Decision

Integrate Obsidian as an optional editor/inspection surface over user-owned Markdown. Keep ALFRED's authoritative review, identity, permission and execution records outside the vault. Keep one memory gateway, with replaceable indexing/extraction adapters underneath. Do not merge several autonomous memory systems and hope their deletion, identity and truth assumptions agree.

Obsidian documents local Markdown storage and a rebuildable metadata cache: https://obsidian.md/help/data-storage . Its graph represents notes and their explicit links: https://obsidian.md/help/Plugins/Graph+view . Neither supplies ALFRED's complete personal memory or action authority.

## Layers and authority

| Layer | Contents | Authority / lifetime |
|---|---|---|
| Human knowledge | Notes, project decisions, approved preferences, maps and curated summaries. | User-owned Markdown. An imported email note is a copy with provenance, not the mailbox's live state. |
| Evidence catalogue | Original source IDs, revisions, hashes, text locations, availability and deletion records. | ALFRED records what was received and when. Source authentication does not prove its content true. |
| Working/episodic context | Active thread, selected task, prior user statements and bounded episode summaries. | Session-scoped, opt-in retention. Not automatically permanent semantic memory. |
| Reviewed semantic memory | Stable entities, relationships, preferences and commitments with source support and review. | ALFRED review ledger. Human acceptance is a judgement, not objective verification. |
| Retrieval projections | Full text, vectors, note links, temporal graph and optional rerank outputs. | Rebuildable indexes. Never the authority for permission or completed actions. |
| Procedural memory | Versioned descriptions of how the user wants work done. | Reviewed workflow proposals. Retrieved prose cannot self-execute or alter permissions. |
| Operational ledger | Approvals, dispatch, receipts, outcomes and human acknowledgements. | Transactional application records. A model's 'done' sentence cannot replace these. |

Personal, company and client/operation boundaries apply to every layer. The interface may be continuous; credentials and access are not universal.

## Current components to extend, not replace

- `alfred/knowledge.py`: bounded Markdown parsing, source catalogue, note links, source health and scans.
- `alfred/reviewed_memory.py`: manual entities/statements, exact source binding, review, limited validity/conflict handling, invalidation and export.
- `alfred/grounded.py`: bounded source retrieval and final source checking.
- `alfred/conversation.py`: private bounded threads, queued processing, expiry/forget and source-bound draft proposals.
- `alfred/evidence_review.py`: narrow numeric/amount/citation heuristics, not entailment.
- `alfred/pulse.py`: two explicit local report routines and bounded history maintenance.

These modules exist. The unified gateway, reviewed-memory retrieval bridge, vault writes, embeddings and third-party graph adapters do not yet exist. Runtime source is unchanged by this planning revision.

**1 October 2026 draft implementation checkpoint:** The M01/M03 review branch implements selected-vault identity and the bounded reviewed-memory bridge described in [the M03 receipt](evidence/memory-m03/RECEIPT.md). Existing scope/source grants and actor-private review records are enforced before selection; accepted/current/non-conflicting statements retain original support, review version, entity IDs, recorded/valid times and supersession lineage. Final checks also bind conversation-derived drafts. The broader gateway, person/device grants, capture/writes, deletion/restore, embeddings and graph adapters remain future work. This checkpoint does not claim deployment or completion of the target contracts below.

## Proposed flow

```text
Selected vaults / authorised account sources / explicit user capture
                       |
             source identity + version journal
                       |
            evidence and provenance catalogue
                /                      \
       explicit note links      proposed entities/statements
                |                      |
                |               scoped human/policy review
                |                      |
                +------ retrieval projections ------+
                                                   |
request -> authenticated scope/grants -> bounded context selection
                                                   |
                               final revision/permission recheck
                                                   |
                                  optional model interpretation
                                                   |
                               evidence checks + response record
                                                   |
                       separate proposal/approval/action gateway
```

## Proposed contracts

Memory requests carry purpose, authenticated person/device/workspace, requested time horizon, allowed source set, sensitivity/egress policy and a maximum context budget. The model cannot supply the authenticated identity or expand its own grants.

A future `ContextPacket` contains source passages; accepted relevant statements with support; unresolved conflicts; freshness/availability; selected prior user context; and a policy/record revision. Include only required fields. Return an empty/limited result honestly when no permitted evidence exists. Never expose a raw database/graph query as an unrestricted agent tool.

A future memory proposal contains subject/predicate/value, memory type, source basis, exact supporting span or authenticated direct-user statement, valid time, recorded time, expiry, intended scope and deduplication key. Review binds the exact proposal version. Model extraction is a proposal, not an accepted fact.

Initially retain the existing controlled predicate set; add preferences and commitments through reviewed schema changes. Stable entity IDs require explicit resolution. Two people named Alex are not one entity. A renamed project does not lose its history, and a duplicate document ID cannot steal another note's identity.

## Temporal and conflict behaviour

Maintain two clocks: when a statement was reported as valid, and when ALFRED learned/recorded it. Late information must not silently rewrite history. Current questions and 'what did we know then?' questions need different selection rules.

A new statement may supplement, dispute or explicitly supersede an older one. Do not automatically choose whichever was ingested last. Competing accepted values with overlapping validity must remain visible and normally require clarification. More general semantic contradiction detection is future work, not provided by the current narrow structural conflict rules.

## Retrieval order

1. Resolve person/device/workspace and permitted sources before producing candidates. Never retrieve broadly and rely only on prompt instructions or final filtering.
2. Start with existing direct note/ID links and a measured SQLite FTS5 lexical index. Exact identifiers, names, filenames and dates must remain searchable.
3. Add only relevant, accepted, non-expired and non-conflicting reviewed statements. Include their original supporting passages and review basis.
4. Expand a bounded number of authorised graph edges. Do not cross a permission boundary through a neighbour, a global entity summary or an embedding search.
5. Optionally combine semantic vectors and reranking when measured recall improves within the same budget. Record embedding model/version, dimensions and normalisation; never mix incompatible indexes.
6. Deduplicate, allocate context, recheck source and grant versions, then call a permitted provider. Recheck before persisting/displaying a result if access or sources changed during processing.

Keep current packet limits until an explicit measured adjustment. Benchmark lexical-only, lexical-plus-reviewed-memory and hybrid alternatives on identical invented tasks. A similarity score, human review or model confidence is not a calibrated truth probability.

## Reuse and deployment choice

Keep SQLite and the existing ALFRED ledger first. FTS5 is the lexical baseline: https://www.sqlite.org/fts5.html . Evaluate sqlite-vec only as a replaceable local projection; its upstream documents pre-v1 instability: https://github.com/asg017/sqlite-vec . Move to PostgreSQL/pgvector when concurrency/deployment warrants it, not merely to use vectors: https://github.com/pgvector/pgvector .

Graphiti is the first narrow temporal-graph candidate, not a selected production dependency: https://github.com/getzep/graphiti . It offers temporal episodes/relationships and hybrid retrieval, but requires its own graph backend and model/provider configuration. A group ID is a partition label, not ALFRED authentication. Treat its extracted facts and automatic invalidations as proposals/advisory outputs mapped back to ALFRED's review contract. Managed Zep capabilities are not automatically features of self-hosted Graphiti.

Cognee is an alternative ingestion/recall pipeline candidate, not another simultaneously authoritative memory system: https://github.com/topoteretes/cognee . Mem0 may be compared for preference extraction: https://github.com/mem0ai/mem0 . Neither may flatten generated action claims into verified operational outcomes. See the dated [landscape](../research/MEMORY_LANDSCAPE_2026-09-27.md) for licensing and implementation caveats.

Basic Memory is a particularly relevant Markdown/graph/MCP reference, but its inspected current root licence is AGPL-3.0. Do not copy it into a proprietary product by assuming historic MIT terms: https://github.com/basicmachines-co/basic-memory . Commercial use is not inherently prohibited; distribution, modification, network use and commercial arrangements require a deliberate review.

## Writes and concurrent editing

A 'remember this' action first creates a scoped proposal, not a silent rewrite of all notes. Start with new notes in `ALFRED/Inbox` under a separate write capability. An approved write includes vault ID, relative path, expected prior version or expected absence, exact diff/content hash, operation ID and expiry.

Filesystem and SQLite are not one transaction. Journal intent and use staged writes plus explicit conflict/reconciliation rules. Re-read after writing. Do not claim global atomicity against an independently running editor/sync client. If content changes concurrently, stop and show a merge proposal rather than clobbering it. External edits trigger fresh indexing without write-back feedback loops. Obsidian-specific operations are specified in [OBSIDIAN_INTEGRATION.md](OBSIDIAN_INTEGRATION.md).

## Correction, forgetting and retention

Distinguish source deletion, source unavailability, access revocation, memory withdrawal and historical supersession. Temporary network/source loss means unavailable/stale, not automatically deleted. A deletion or revocation tombstone invalidates eligible dependent projections; the system returns a receipt listing current copies removed/blocked and residual retention.

Propagate through snippets, accepted statement projections, embeddings, generated summaries, cached answers, episode condensations and queued work. An old backup must not resurrect a deleted memory into current retrieval: reapply tombstones and current grants before reopening the restored index. Backups and immutable metadata have explicitly different retention; no blanket secure-erasure promise.

Do not default to retaining raw audio or full screen recordings. Working context, explicit user preferences, task commitments and client data have different retention rules. Credentials and secrets belong in a secret store, not Markdown, graph nodes or model context. A user's export should not copy another workspace's material.

## Relationship to MAPS and the console

MAPS is a useful separation of Memory, Agent, Pulse and Screen, not a complete runtime or proof of efficiency. Keep compact human maps and explicit routines without inheriting 'never delete' or private-network-without-auth assumptions. Reference: https://github.com/pavrus117/ai-os-maps-guide . Its guide was not copied wholesale.

The console can visualise current sources, reviewed relationships and uncertainty. It must not invent nodes to imply intelligence or label an authored link as a verified real-world relationship. Keep the approved premium console direction and its separate implementation work; do not substitute Obsidian's UI for ALFRED.

## Exit criteria

A synthetic end-to-end demonstration must remember an explicit statement, retrieve it in a follow-up with original support, revise it without erasing provenance, reject conflicting/unauthorised variants, forget it across current projections, and recover after restart without resurrection or duplicate writes. Inspect actual outputs. No new memory engine, real vault connection, model experiment or background deployment is delivered by this document.
