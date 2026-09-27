# MEMORY-001: optional Obsidian, first-party governed memory

Date: 27 September 2026.
Status: planning decision adopted for implementation; library/provider selection remains provisional.
Requirements: [PRD.md](../PRD.md). Detailed design: [MEMORY_ARCHITECTURE.md](../MEMORY_ARCHITECTURE.md).

## Context

ALFRED already has a local source index, note-reference graph, private conversations, manually reviewed claims and an approval ledger. The missing piece is controlled contextual use and lifecycle, not a reason to replace the whole backend. The owner wants Obsidian's readable notes plus richer personal intelligence and wants all plans preserved in GitHub.

## Decision

1. Keep Markdown as a portable human knowledge format and Obsidian as an optional editor. Support selected filesystem vaults first.
2. Keep source provenance, claims review, identity/grants and operational effects authoritative inside ALFRED's transactional services. Notes and inferred edges never grant authority.
3. Separate note links, reviewed statements, temporary episodes and procedures. Every derived memory carries source/revision and invalidation lineage.
4. Expose one bounded memory gateway to conversation, attention and specialist adapters. Permission checks precede retrieval and egress, with a final revision/grant recheck.
5. Keep SQLite first and establish a lexical baseline. Graph/vector infrastructure is a replaceable projection, introduced only with measured benefit.
6. Evaluate Graphiti as a temporal adapter and Cognee as an alternative composition. Mem0 is a possible preference extractor. Do not install all three as memory authorities.
7. Treat Basic Memory's current AGPL and the official headless package's UNLICENSED declaration as explicit integration gates, not assumed permissive licences.
8. Add reviewed capture and narrow exact-diff inbox write-back only after source identity/grants. File sync and ALFRED runtime/database sync are separate systems.
9. Preserve concurrent console work. The internal console name does not establish Obsidian app integration.

## Alternatives not selected now

Obsidian alone lacks ALFRED's permissioned action and reviewed-memory lifecycle. A vector database alone cannot represent review, temporal conflicts or execution outcomes. A single giant transcript loses useful distinctions. A mandatory graph cluster adds deployment cost before proving retrieval value. Multiple full agent/memory runtimes duplicate authority, schedules and deletion responsibilities.

Basic Memory could be used under appropriate terms; reference-only initially is not a claim that AGPL forbids commercial use. Managed memory services remain deployment options under separately approved privacy, service and commercial terms.

## Consequences

More first-party integration work is necessary, but existing tested behaviour is preserved and components remain replaceable. Human notes are not locked to a proprietary ALFRED format. Complete deletion, provenance and authorisation are harder than adding a graph visualisation, so they become acceptance gates rather than optional cleanup.

This decision does not install dependencies, change runtime source, run a model experiment, connect private data, merge main or deploy. Revisit adapter choices after a permitted comparison using the same data, grants, budgets and failure cases. Preserve the previously blocked model-comparison restriction.
