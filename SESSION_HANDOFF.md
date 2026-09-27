# ALFRED continuation: governed-memory planning revision

27 September 2026. Start with AGENTS.md, docs/PRD.md, docs/ROADMAP.md and plans/memory-backlog.json.

## Source checkpoint

Planning branch: research/alfred-memory-system-2026-09-27.
Base commit: 73a255a10cb43f55a14aaf45165800bd17e60553 on feat/alfred-obsidian-console-2026-09-27.
Base tree: a7b21f02338036a7c1b96aed5e87262133cae27a.
This is one console-toolchain commit ahead of v0.8 22e64567f69508928b164d55c578834abcb404e8. It preserves the full local application. Refresh refs and compare concurrent console work before continuing. No automatic merge/main update or deployment.

## User request addressed

Research Obsidian plus deeper memory and useful repositories, update product/build plans across ALFRED, and publish them. The conclusion is optional Obsidian/Markdown authoring plus ALFRED-owned evidence, reviews, authority and lifecycle. Do not require Obsidian to be open for selected-folder reading. Do not confuse the console's internal name with an integrated note application.

## Delivered by this revision

Current canonical PRD; updated architecture/product brief/roadmap/work packages; detailed memory architecture, Obsidian interoperability and privacy/deletion specification; architecture decision; 22-repository research map with five exact commit/licence/package observations; 12 dependency-linked future jobs; deterministic plan consistency checker. Superseded briefs/plans are archived without deleting their history.

This revision changes no alfred/, web/ or console/ runtime source and no third_party/ files. No new library, model, private vault, account or service was installed or connected. The new validation is about plan/source-link consistency plus regression tests of unchanged code, not completion of the memory programme.

## What already works at v0.8

Local persistence, credential-scoped access, read-only project/Markdown scanning, explicit note graph, source questions, bounded saved conversations, manual reviewed entities/statements, exact local-draft approvals, fixed Pulse reports and controlled report-history pruning. Optional tool-free local model exists with a small real v0.7 experiment and documented failures. No production brain selected.

Reviewed memory is not yet automatically conversation context. The current scanner is not complete Obsidian compatibility. Note write-back, mature person/device identity, fine-grained grants, application encryption, full deletion/restore accounting and actual external connectors remain unfinished.

## Immediate implementation work

M01: selected-vault compatibility and stable identity/rename/collision fixtures.
M03: bounded reviewed-memory context bridge, first on synthetic data, retaining source/review/validity/conflict and access checks.
M02 in parallel: mature person/device identity and per-source/capability grants. M02 and M05 are release gates for private-data pilot.
Then M04 explicit capture and separately approved inbox writes; M05 correction/deletion/restore; M06 measured lexical baseline. M07 graph/vector engines are optional, not a reason to block the useful local loop.

Graphiti is the first temporal adapter candidate; Cognee is an alternative; Mem0 may help preference extraction. Basic Memory is a strong architectural reference but current AGPL terms must not be mistaken for MIT. Official headless package is UNLICENSED; use only as a deliberately configured service client under appropriate terms, not a silent fork.

## Preserve these boundaries

No source content or graph edge grants tool permissions. No automatic names-only entity merging. No blind file overwrite or live SQLite/WAL file sync. A sync receipt is not remote-device execution. Temporary unavailability is not deletion. A restored backup must not resurrect forgotten current memory. Separate generated claims, source reports, observations, receipts and human acknowledgements.

Preserve the approved premium console direction and parallel UI work. Do not restore an admin-dashboard default or claim the current source already matches the target. This task is research/planning, not another design pass.

The previously blocked live-model-comparison operation remains unexecuted and must not be rerouted. No new model benchmark is claimed. No microphone, account/device, ENDSTATE or Noir integration, daemon, cross-device runtime sync or safety-critical deployment was added.

## Verification

Run the plan checker/self-tests, the existing first-party unit suite and both source archive verifiers. Inspect the actual planning PR/Actions receipt for current results. Do not inherit counts as proof for modified code. Use the current PR head, not a remembered branch, and publish normal files plus exact commit and limitations.
