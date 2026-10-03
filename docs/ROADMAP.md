# ALFRED current execution roadmap

Updated 3 October 2026. **One product: operational and executive intelligence.** [PRD.md](PRD.md) defines requirements; [the register](../plans/requirement-register.json) records delivery; [the remaining plan](REMAINING_BUILD_PLAN.md) keeps the existing work-package numbers; [NEXT_STAGE.md](NEXT_STAGE.md) sets the current execution and activation gates. Earlier wording is preserved in [the pre-stage roadmap](archive/pre-stage-2026-10-03/ROADMAP.md).

## Current baseline

PR #18 merged as main `75947b8dd59a3161c862d2533850a032994778e2`, including #15/#16/#17. The console now reads authenticated backend records. M01/M03/M04/M06 bounded slices, temporal review, executive workflows, routines, jobs/cache, pairing and export importers are integrated. Broader identity, storage, reasoning, host and external-system requirements remain partial. The exact-main CI passed; [the audit](AUDIT_2026-10-03.md) gives scope and remaining concerns. No deployment or whole-product completion is implied.

## Active stage: PILOT-GROUNDWORK

This is the owner's separate next stage, not M02 and not the infrastructure report's stage 0. The full PRD stays in scope. Two tracks may proceed together:

| Track | Execute now in the authorised builder environment | Promotion boundary |
|---|---|---|
| A. Current-product engineering | Reproduce/disprove approval visibility; fix confirmed defects; migrate strict defaults; extend local privacy/lifecycle/recovery; improve evidence relevance and the synthetic end-to-end loop. | Private data requires tested safeguards and explicit selected-pilot approval. |
| B. Future-platform groundwork | Research native shell, always-on authority, trusted nodes/remote mode, persistent/disposable workers, file tier, partner/cost options; bounded opt-in synthetic prototypes. | No provider commitment, external provisioning, real devices/accounts/data, production listeners or commercial launch. |

Start A1 before widening use. Do not treat the audit hypothesis as confirmed. Do not block all local work on a future provider choice. Do not return only plans when an in-stage implementation increment is possible.

## Existing release gates, preserved

1. **Private pilot:** M02/M05 and relevant M01/M03/M04 acceptance, default-deny migration, approved custody/retention, deletion/restore and host recovery, then one explicitly selected real workspace. Synthetic testing is not private-data release.
2. **Useful assistant:** qualified reasoning/evidence selection, one approved account workflow, attention and reliable operation with measured evidence. Native appearance and green structural tests are not enough.
3. **Always-on/distributed:** authority-location and egress decisions, authenticated remote mode, supervised service, enrolled second node, isolation and cloud-file acceptance. A VPS is not a secure transport or a cloud drive. Native packaging may proceed independently; it is not a prerequisite for hosting.
4. **Team/operational:** mature roles and tenant boundaries, actual specialist interfaces, supervised non-critical exercises and independent review appropriate to deployment. No autonomous use of force.
5. **Commercial/owned-infrastructure proposal:** research now; a separate later decision after workload economics, operational support, security and customer evidence. No fixed user-count trigger, partner guarantee or requirement to own a data centre.

A completed research task or implementation PR does not automatically cross a gate. Record the evidence, limits and approval before promotion.

## Whole-product workstreams

| Workstream | Existing IDs | Next focus |
|---|---|---|
| Connected console and project focus | UX-001/002, MEM-016, MEM-009 | Preserve the implemented adapter and graph; verify action visibility and actual device behaviour. |
| Memory and lifecycle | MEM-001 to MEM-015, SYS-001/002 | Finish private-pilot safeguards without reimplementing completed slices. |
| Reasoning and context | INT-001/002, MEM-008 | Better packet relevance and measured answer usefulness; separate source tests from model quality. |
| Executive and action workflows | ATT-001/002, ACT-001 | Close explicit remaining workflows and time/authority gaps using the existing ledger. |
| Host, jobs and files | RUN-001/002/003, SYS-003, MEM-014 | Local reliability now; contracts/research/prototypes before separately approved remote rollout. |
| Connectors, voice and specialist products | CON-001, VOI-001, OPS-001/002 | Existing export importers/output-only voice/contracts are partial, not live external systems. |
| Native and commercial architecture | RUN-001/002, SYS-001/002, UX-001, OPS-001 | Preserve React/Python; compare shell, deployment and cost options before adoption. |

## M programme remains bounded

| Job | Work | Recorded implementation at the integrated baseline |
|---|---|---|
| M01 | Selected-vault identity and compatible reading | Implemented bounded slice; complete Obsidian/document/sync coverage not implied. |
| M02 | Person/device/source grants | In progress. |
| M03 | Reviewed-memory context bridge | Implemented bounded slice. |
| M04 | Explicit capture and approved inbox writes | Implemented bounded slice. |
| M05 | Correction/deletion/private storage/restore | In progress; application encryption/custody incomplete. |
| M06 | Lexical baseline and deterministic evaluation | Implemented evaluation, not hybrid retrieval or mature reasoning. |
| M07 | Optional temporal/semantic adapter decision | Planned; first-party temporal review does not mean an external engine was adopted. |
| M08 | Structured attachments/documents | Planned. |
| M09 | File sync and host lifecycle | In progress. |
| M10 | Commitment/procedure attention | In progress. |
| M11 | Official account workflow | Planned; local export importers are not account access. |
| M12 | Voice/native/console/specialist programme | Not complete; baseline backlog label is planned despite integrated console/output/contracts. Reconcile by evidence, not blanket promotion. |

The backlog's requirement mappings and acceptance cases remain authoritative for those jobs. Programme issue #11 tracks memory; other runtime/voice/core issues remain separate. An issue is not a running agent.

## Rules for the next builder

Use current main plus this handoff if still on its review branch. Preserve concurrent work, original source archives and historical receipts. Publish focused commits/PRs; do not force-push or auto-merge. Run the combined relevant checks on the actual result.

Do not rebuild the conversation queue, action ledger, reviewed-memory store or console to change libraries. Do not install several competing memory authorities. Research references, provider credits, library copies and VM snapshots are not implementation, security or spend approval. Preserve the blocked live-model-comparison restriction.

For the exact scoped task use [CODEX_NEXT_STAGE_PROMPT.md](CODEX_NEXT_STAGE_PROMPT.md). At a stage boundary or task limit leave evidence and a precise continuation, not a claim that the full programme is finished.
