# ALFRED unified build handoff

**Latest handoff, 1 October 2026:** read
[MASTER_HANDOFF_2026-10-01.md](docs/MASTER_HANDOFF_2026-10-01.md) first. The
memory-programme checkpoint preserves paused partial M02/M06 changes on a
separate branch; it does not complete all M jobs or replace the whole-product
roadmap. Main and draft PRs #15/#16 remain unchanged. The older dated sections
below retain their historical context.

27 September 2026. Product category: **operational and executive intelligence**.

## Start from main

All nine previously stacked PRs were merged into main in dependency order: #1, #5, #6, #7, #8, #9, #10, #13, #12. The combined baseline is `03e946fc3fb6fe0b540abe5ff52204de6f0f99ed`; current main may include the subsequent source-library and documentation consolidation. Refresh main before branching. Do not use an older research branch as the current product.

Read BUILD_START_HERE.md, AGENTS.md, docs/PRODUCT_POSITIONING.md, docs/PRD.md, docs/ROADMAP.md and plans/memory-backlog.json. Current source availability is in third_party/library/README.md and CATALOGUE.json. Historical source locks and receipts remain separately intact.

## What is actually combined

The v0.8 Python/SQLite backend, functioning web/ interface, tests and all prior handoffs/evidence are present together with the later React/Three.js/GLSL console and its separate handoff. The console is no longer merely a package skeleton. Its interactive frontend works with fictional fixtures; an authenticated backend adapter is still missing. Preserve both interfaces until that connection has real browser-to-server acceptance.

The broader library covers all 42 researched upstream repositories through copied source-text snapshots or explicit pinned reference-only records. Exact copied counts, revisions, licence observations and per-file omissions are in the current catalogue. Historical focused archives contain 2,309 files and overlap with the broad library; do not claim summed counts are unique code.

No upstream application, skill, workflow or model was executed during preservation. No third-party memory/runtime library was adopted merely by copying it. Obsidian Headless remains a pinned external-client reference because a redistribution grant was not established. Preserve the distinction between UNLICENSED and Unlicense.

## Current product capabilities

Local persistence and authenticated browser sessions; read-only Markdown/project source scanning; authored note graph; exact source excerpts; bounded saved conversations and optional tool-free local model queue; manually reviewed entities/statements with source invalidation/conflict/supersession; exact local-draft approvals; fixed Pulse reports and bounded history pruning.

No dependable production brain selected. Reviewed claims are not automatically inserted into conversational context. No external account/device, voice, ENDSTATE or Noir integration. No application-level encryption or mature paired-person/device identity. Only local drafts and local report/review metadata can be written. Host must remain running; no deployed daemon or cross-device runtime sync.

## Next implementation sequence

M01 selected-vault identity/compatibility and M03 reviewed-memory context bridge, initially using synthetic data. M02 person/device/source permissions proceeds alongside them. Connect the premium console to actual authenticated read-only projections without changing the authority system. Then M04 explicit memory capture and exact approved inbox writing; M05 complete correction/deletion/restore; M06 lexical retrieval baseline.

Graphiti is a temporal-memory candidate; Cognee an alternative pipeline; Mem0 a preference component. Use the copied relevant source to inspect rather than re-research from nothing. Do not activate several competing memory authorities. Licences, source egress, dependency risks and actual interoperability still need adoption decisions. Memory private-pilot gates M02/M05 remain unfinished.

Executive intelligence includes priorities, decision briefs, planning, commitments and follow-up. Operational intelligence includes current state, change awareness, coordination and traceable authorised outcomes. Personal usefulness and personal/company/client boundaries remain fundamental. Emotive Impact versus Black State corporate ownership is not resolved by this wording change.

## Verification and limitations

The consolidation workflow rechecks the existing core, source manifests, plan consistency and console build/browser behavior against the combined source. Consult its actual finished run and docs/CONSOLIDATION_2026-09-27.md, not inherited green counts from earlier PRs. Historical receipts remain historical. Source preservation is not runtime integration, security certification, deployment or safety-critical readiness.

The previously blocked live-model-comparison operation must not be retried or rerouted. No new model inference is part of this work. Keep private data out of this public repo. Work on a short-lived branch from current main, publish tested normal source and update the handoff with evidence.

## M01 review handoff, 30 September 2026

This branch starts at current main `8398c7437cb0ef1386d8dc4ff1f9e92fb2557ca2`, preserving the consolidated application, source library and console. The only concurrent open PR found at the start was console refinement #15; it is not incorporated or modified here. M01 implements selected-vault/catalogue identity, conservative rename/revision continuity, opt-in `alfred_id`, alias/supported-anchor validation, exclusions and honest read/source failures. Read [the M01 receipt](docs/evidence/memory-m01/RECEIPT.md) and [the updated read contract](docs/OBSIDIAN_INTEGRATION.md).

The branch is for draft PR review, not a main merge or deployment. M02-M12 and issue #11 remain unfinished. Do not treat M01 as native Obsidian acceptance, fine-grained grants, private-vault readiness, safe writes, restored-backup deletion accounting or console integration. Existing reviewed-source/action validity checks remain in force; path/revision changes invalidate earlier source bindings conservatively.

## M03 review handoff, 1 October 2026

Continued the tested M01 draft PR #16 after rechecking main, open PRs and review threads. Main remained `8398c7437cb0ef1386d8dc4ff1f9e92fb2557ca2`; console refinement #15 remained separate. The reviewed-memory bridge now selects relevant, accepted, current, actor-private statements into questions and conversations, retaining exact original support, source revision, review version, recorded/valid times and explicit entity IDs. Memory shares the existing five-source/6,000-excerpt-character budget, with at most four statements and 1,600 characters of statement names/values/predicates. Namesakes are qualified by IDs and model use is withheld until identity is clarified. No automatic entity resolution is implemented.

Review/source/conflict/validity rechecks apply before optional model egress, response return/persistence/display, and draft proposal/approval/dispatch. Saved turns retain review/source bindings; current values are reconstructed from the ledger. Source-only historical conversations and approval receipts remain compatible. Read [the M03 receipt](docs/evidence/memory-m03/RECEIPT.md) for acceptance and limits.

M01 and M03 are implemented on this draft branch, subject to review. M02 and M04-M12 remain planned; issue #11 stays open. The next private-data prerequisites remain M02/M05; explicit capture/inbox writing is M04. No main merge, private-vault access, deployment, console adapter, graph-engine installation or model-quality experiment was performed.
