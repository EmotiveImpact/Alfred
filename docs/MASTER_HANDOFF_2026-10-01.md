# ALFRED master conversation handoff

1 October 2026. This is a whole-project status and paused-development checkpoint,
not a claim that the full ALFRED vision or memory programme is complete.

## Read this before continuing

The owner wants one persistent personal, operational and executive intelligence
application. Preserve the approved console and existing backend. Do not rebuild
components that already work. The owner has further research and plans to fold
into the grand plan; these have not all been supplied or reconciled here.

The M series is a bounded memory programme with supporting integration work.
It is not the complete remaining product roadmap. Mapping a broad requirement
to one M job does not mean completing that job fulfils every future application
of the requirement. No reliable whole-product completion percentage exists.

The owner originally requested M01, then expanded the request to all M jobs.
After confusion about existing versus missing work, implementation was paused.
The latest instruction is to push everything for the master conversation.
This checkpoint preserves the partial edits; it does not resume all-M delivery.

## Exact repository checkpoints

Repository: <https://github.com/EmotiveImpact/Alfred>

| Checkpoint | Revision and state |
|---|---|
| Current main | `8398c7437cb0ef1386d8dc4ff1f9e92fb2557ca2`, rechecked before publishing |
| Original consolidated planning baseline | `03e946fc3fb6fe0b540abe5ff52204de6f0f99ed`, historical, not the latest main |
| Console refinement PR #15 | `f7c41ce228b83257ad1852ba0f122b2afbc0f2db`, open draft, untouched here |
| M01/M03 PR #16 | `18dcfb39a3244fe21caf1d7ed2887443cf490914`, open draft, tested, untouched here |
| This checkpoint | Branch `feat/memory-programme-2026-10-01`, parent is the PR #16 head above |

This branch contains main plus PR #16 and the partial changes documented below.
It does not contain PR #15's refinements. Its new draft PR overlaps PR #16;
reviewers should coordinate those branches rather than treating both as separate
complete memory implementations. No force push, main merge or deployment.

## What the earlier ChatGPT work built

The earlier nine-PR stack was consolidated into main on 27 September. It includes
foundation, persistent local core, desk/knowledge, grounded questions, OS/Pulse,
conversations, reviewed memory, premium console and the memory/research plan.
See [the consolidation record](CONSOLIDATION_2026-09-27.md).

| Area | Existing implementation | Remaining extension |
|---|---|---|
| Backend | Local Python/SQLite persistence, scoped credentials/sessions, audit and authenticated loopback HTTP | Mature person/device policy, private storage and production lifecycle |
| Existing web app | Real backend-connected source inspection, conversations, memory review and approvals | Additional capture/lifecycle/integration workflows |
| Markdown knowledge | Read-only scanner, explicit note graph, keyword/link retrieval and exact evidence | Documents, measured retrieval, sync and complete lifecycle |
| Conversations | Saved bounded sessions, queue, optional tool-free local model adapter and source/review checks | Qualified reasoning and wider agent-runtime capabilities |
| Reviewed memory | Explicit entities, manual statement review, validity/conflicts/supersession | Complete remember/correct/forget loop and richer temporal/semantic work if justified |
| Actions | Exact approvals, transactional outbox, expiry/revocation and verified local draft effect | Each real connector/device effect and capability-specific reconciliation |
| Attention | Fixed, explicitly enabled Pulse reports and bounded history | Task-aware commitments, procedures and useful reminders |
| Premium console | Functional React/Three.js/GLSL frontend, sphere, navigation, inspectors and fictional interactions | Authenticated projection of real backend records and review/action states |
| Research | Pinned upstream source-text collections, licence observations, manifests and plans | Deliberate adoption, interoperability and acceptance; archives are inert |

"Built" in the left column does not imply the extension on the right is built.
Console sample interactions do not establish real account/brain/microphone
connections. Source preservation does not install a memory, voice or agent engine.

## Current memory job truth

| Job | State at handoff |
|---|---|
| M01 | Implemented on PR #16: selected-vault/note identity, conservative rename/revision compatibility, aliases and supported anchors, unsafe/duplicate rejection, exclusions and honest availability |
| M02 | In progress and paused: local identity/grant scaffolding and retrieval checks; complete acceptance and user/admin workflows unfinished |
| M03 | Implemented on PR #16: bounded accepted/current reviewed-memory context with exact support and final validity checks |
| M04 | Planned: explicit capture and exact approved inbox-only writes |
| M05 | Planned: complete correction/deletion, application encryption, key custody, restore and residual-retention accounting |
| M06 | In progress and paused: authorised-subset FTS5 path; frozen support-labelled comparison and measured report unfinished |
| M07 | Planned optional adapter decision; no temporal/semantic engine adopted |
| M08 | Planned document/attachment ingestion |
| M09 | Planned deliberate sync and reliable host lifecycle |
| M10 | Planned commitment/procedure-aware attention |
| M11 | Planned official account workflow; no real account connected |
| M12 | Planned real console projection, voice and actual specialist/device contracts |

Machine-readable tracker: [memory-backlog.json](../plans/memory-backlog.json).
Issue [#11](https://github.com/EmotiveImpact/Alfred/issues/11) remains open.
Its last consolidation comment predates M01/M03; it is not the newest delivery
record. Historical receipts and baseline tables may likewise describe older
states. Use exact revisions and this handoff to interpret them.

## Partial code preserved in this checkpoint

- `alfred/policy.py`: distinct local person/device records, explicit pairing,
  credential rotation, opt-in strict source grants and policy epochs. Existing
  review/conversation histories stay credential-private; pairing is not a silent
  history merge. Default workspaces retain the documented legacy scope policy.
- LocalCore and DeskStore initialise that schema; authentication returns identity
  metadata. Knowledge filters sources before graph construction; exact note reads,
  reviewed-source checks, packet currentness and conversation action checks use
  source policy. Model retrieval has a separate `model` purpose.
- `alfred/retrieval.py`: opt-in FTS5 ranking using an ephemeral index containing
  only authorised current notes. No embedding, model, external service or answer
  key is introduced. Existing keyword ranking remains the default.
- Two M03 race-injection wrappers forward the new retrieval keyword arguments;
  their stale-review assertions remain intact. Eight new synthetic checkpoint
  tests cover distinct identities, rotations, filtering, separate model grants,
  policy epochs, expiry and mid-generation revocation.

These changes are not a completed M02/M06 release. In particular, mature
enrolment/recovery/admin/HTTP workflows, permission-loss versus durable review
invalidation semantics, full mid-request persistence/display coverage and the
retrieval evaluation still need deliberate review and implementation.
`memory_tombstones` is only a schema placeholder; M05 deletion/restore is not
implemented. Do not treat its existence as a deletion guarantee.

## Evidence and boundaries

PR #16's exact head passed [unified CI 36796267517](https://github.com/EmotiveImpact/Alfred/actions/runs/36796267517):
663 application tests, 195 backend/browser checks and the preserved console's
build, 33 unit tests and 23 browser scenarios. Those results are historical
evidence for that head, not automatically evidence for this checkpoint.
PR #15 passed [its unified CI 36299698267](https://github.com/EmotiveImpact/Alfred/actions/runs/36299698267).

Current checkpoint evidence and outstanding gates are in
[the WIP receipt](evidence/memory-programme-wip/RECEIPT.md). Retain failed checks
honestly. Passing legacy tests or fixture providers does not establish production
security, reasoning quality, native hardware, real audio or external-account
acceptance.

The existing user limits remain: **do not merge main or start private-vault
deployment**. No private account, notes, audio, device effects or background
service were connected or installed. No model inference/download/benchmark was
performed. The previously blocked live-model comparison must not be rerouted.
No third-party source archive or concurrent console implementation was changed.

## Next work for the master conversation

1. Read current refs, this handoff, BUILD_START_HERE.md and AGENTS.md. Preserve
   main, both existing draft PRs and this paused checkpoint. Do not infer that an
   open issue is an active agent or that a planning document is working code.
2. Collect the owner's remaining research/plans and reconcile one whole-product
   roadmap against actual source. Separate implemented capability, partial
   capability, draft delivery, research candidate and future goal.
3. Retain existing components. Decide explicit integration/review order for the
   tested console and M01/M03 PRs, then finish the partial M02/M06 work and the
   useful memory loop. Private-data gates remain M02/M05.
4. Track dependable reasoning/runtime, broader executive workflows, additional
   connectors/devices, remote workers/storage, native applications, deployment
   and specialist systems beyond the bounded M programme. Unprovided research
   must not be invented or represented as already incorporated.
5. Run affected acceptance and exact combined CI on the chosen integration
   branch. Keep implemented status, merge status and deployment status separate.
