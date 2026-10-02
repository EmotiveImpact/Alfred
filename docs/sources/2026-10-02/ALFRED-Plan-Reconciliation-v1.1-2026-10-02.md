# ALFRED: proposed amendment to the existing master plan

**Version 1.1: targeted boxd / streaming-storage coverage correction. Not an exhaustive all-chat reconciliation.**

This revision checks the earlier amendment against newly retrieved excerpts from the original infrastructure discussion. It restores named references and separates recovered requests from assistant proposals and newly checked product facts. Repository revisions and delivery states below remain the records checked for version 1; they were not refreshed in this targeted correction. No repository file, branch, deployment, account or running service was changed. The original version is retained.

Prepared 2 October 2026. This reconciles the retrieved ALFRED discussions with the repository records checked for this response. It is an amendment ready to incorporate into the existing PRD and roadmap, not a second roadmap, a code release, or a claim that all other-chat research has been ingested. No repository files, branches, merges or deployments were changed while preparing this document.

## 1. What has changed, in one paragraph

The core product remains operational and executive intelligence in a persistent personal operating environment. Its console is now a working frontend rather than only a design reference. The backend has additional stable-vault and reviewed-memory-context work on a tested draft branch. What remains missing is the authenticated connection between these pieces. The latest visual exploration further specifies project-centred graph navigation and contextual conversation; it does not establish that those connections work. Other retrieved discussions add distributed operation across computers and a VPS, expandable cloud-backed files, isolated remote workers, and a common integration contract for independent specialist products. The master plan needs to show these workstreams alongside the memory programme, with their actual delivery and decision states.

## 2. Repository truth at this check

| Area | Verified repository record | Correct planning interpretation |
|---|---|---|
| Main baseline | `8398c7437cb0ef1386d8dc4ff1f9e92fb2557ca2` | Consolidated Python/SQLite backend, backend-connected original web app, sources, conversations, manually reviewed memory, local approved drafts, bounded Pulse routines, initial premium console and research/plans. This is not an empty project. |
| Refined console | Draft PR #15, `f7c41ce228b83257ad1852ba0f122b2afbc0f2db` | Implemented and tested frontend, awaiting review/integration into main. Still demonstration data, not the live brain. |
| M01 and M03 | Draft PR #16, `18dcfb39a3244fe21caf1d7ed2887443cf490914` | Implemented and tested branch work for stable selected-vault/note identity and reviewed-memory context. Not yet merged or connected to the refined console. This is bounded acceptance, not complete production memory. |
| M02 and M06 | Draft PR #17, `07573dfdbe906fb3932a31e440d342dfafb089bc` | Partial, paused identity/grant and authorised-subset retrieval work. PR #17 includes PR #16; do not count or integrate their common changes twice. |
| Master reconciliation | `docs/MASTER_HANDOFF_2026-10-01.md` on PR #17 | Explicitly requests one whole-product plan and preservation of existing implementations. It says further research is not all reconciled. |

The M series is a memory programme with supporting integration tasks. It is not the whole ALFRED roadmap. The main PRD already retains wider system, reasoning, action, attention, connector, voice, operational and UX requirements; the execution roadmap needs to expose those workstreams rather than bury them under M12.

Do not repeat an old main-branch table as the latest development status. Conversely, code on an unmerged branch is not automatically present in main. Keep implementation, integration, merge and deployment status separate.

## 3. Amendments arising from this conversation

### A. Preserve the implemented console as the interface baseline

Map to existing `UX-001`, with references to PR #15 and its component architecture, build brief and graphics documentation.

Retain true black, shallow graphite, ivory text and restrained amber; the small metallic ALFRED logo at the top of the narrow rail; hover/focus expansion over the workspace; one executive surface; the bottom command bar; normal readable text; and a real Three.js/React Three Fiber/custom GLSL sphere. Do not reopen a visual redesign or replace it with a stock dashboard.

The no-flashing requirement is an ongoing acceptance constraint. The branch removes time-driven brightness, fixes render ownership and preserves the canvas through ordinary UI changes. Software-rendered checks are evidence for those tested scenarios, not proof of universal physical-device performance. Keep target-device visual, pointer, keyboard, reduced-motion and graphics-recovery checks in the release plan.

### B. Specify project-centred graph interaction without permanent clutter

Map to `UX-001`, `MEM-016` and `INT-001`. This is a clarification/extension of the existing inspector and selection model, not an instruction to rebuild the graph from scratch.

Selecting a project sets a stable record ID and visible working context. An inspector or project workspace exposes its permitted documents, sources, people, decisions, commitments and tasks. Related items highlight; irrelevant material can recede. Open-in-workspace navigation should preserve that selection. Show an expanded project panel only when it is useful, not as another permanent sidebar.

Add a project-focus acceptance case: select a project, open its exact source, follow a supported relationship, ask a contextual question and clear the selection. Changing workspaces must clear or revalidate the selection. Shared names, branding or ownership alone must not create knowledge edges. Fictional characters inside a game project must remain distinguishable from real contacts.

The latest generated image is an illustrative connected-state concept. Its project thumbnails, counts, percentages, timestamps, claims of being online/secure and additional programme labels are not implementation evidence or automatic roadmap commitments.

### C. Implement the real read-only graph projection

Map to `MEM-003`, `MEM-009`, `MEM-012`, `MEM-016`, `SYS-001` and the console-projection part of M12.

Use the existing backend's sources and reviewed-memory records. Do not require a new graph database or adopt a second authoritative memory engine simply to draw a graph. Inspect actual server routes before implementing the proposed `ConsoleReadPort` adapter.

The projection must carry stable record IDs, workspace, source/evidence references, source revision, review basis and availability. Authored note links and reviewed claims remain distinct. Filter before returning records, counts or links; recheck grants and freshness at meaningful boundaries. Cancel obsolete requests and clear stale selections after scope changes or revocation.

Field mode can retain its atmospheric geometry, but record counts exclude it. Relationships mode displays only supported records and relationships. An unavailable source, an empty graph or a denied request must produce a truthful state, not replacement fixtures or fabricated density.

Acceptance: one permitted test project appears from real backend records rather than bundled fixtures; another workspace is excluded; source changes invalidate affected displays; refresh reconstructs current state; absent access does not leak counts, links or names.

### D. Connect selection, conversation and executive work

Map to `INT-001`, `INT-002`, `ATT-001`, `ACT-001` and relevant M03/M10/M12 work. M03's implemented context bridge is an existing dependency to reuse, not new work to repeat.

The question bar must receive the authorised workspace, selected record and relevant evidence. The UI must distinguish searching, asking, planning and proposing an action. A graph selection supplies context; it grants no new access and is not an instruction to execute.

Connect the executive panel to the same authoritative records used by the graph: priorities, proposed decisions, pending approvals, project milestones and dated insights with supporting sources. A progress indicator needs defined inputs. An inferred priority must be labelled as a recommendation, not silently become an obligation. Cross-project insights require permitted supporting data from every contributing scope.

Acceptance: selecting the test project affects the next question; the answer exposes the correct evidence and review basis; a changed source makes old material visibly stale or unavailable; a missing model reports that state rather than inventing a response. Later approved actions produce server receipts which update the relevant project/task view.

## 4. Additions recovered from other chats

### A. Distributed ALFRED: two computers and a VPS

Origin: 29 September, Open Source ALFRED Infrastructure discussion. The requested capability is continuity across computers, a VPS while mobile, cloud-backed files and a separate place to launch agents. The Home/Core/Drive/Forge labels and particular technologies were assistant proposals, not final supplier decisions.

Map to `RUN-001`, `SYS-001`, `SYS-002` and M09 where file/host lifecycle overlaps. Expand the whole-product requirements to cover:

- One user identity and explicit enrolment/revocation of trusted computers.
- An optional always-on coordinator, with a clear split between coordination and where models/jobs actually run.
- Node availability and capabilities; deliberate job placement on a local computer or an authorised remote worker.
- Offline use of permitted cached material, visible freshness and reconciliation on reconnect.
- One authority for each job's dispatch, durable job state, cancellation, bounded retries and outcome reconciliation.

This is not three independent ALFREDs copying their brains into one shared file. It needs explicit synchronisation and authority contracts. Do not synchronise a live SQLite database through a generic cloud folder.

### B. Expandable files and isolated agent execution

Origin: the same infrastructure discussion, plus the 1 October whole-product handoff. Track storage and job execution as separate deliverables with explicit interfaces.

The file service should provide authorised retrieval, a bounded local cache, explicit offline availability, revisions, quota/cost controls, export and backup/restore behaviour. Expandable storage is not infinite, free or instantly available. Distinguish durable user files, authoritative memory/history, rebuildable indexes, secrets and disposable agent scratch space.

The worker service should execute bounded jobs in isolation. Its contract needs declared inputs, limited file/tool permissions, scoped short-lived credentials where needed, runtime/cost limits, logs, cancellation and verifiable outputs. A worker response is a result to validate, not permission to act again. Preserve the existing approval/outbox system rather than creating a parallel authority path.

The original infrastructure discussion explicitly began with **boxd.sh**, a possible Space/SpaceFS reference (typed “spacedfs”), and **pCloud-like streaming storage as a second hard drive**. Version 1 reduced these to generic cloud files and remote workers, retaining only JuiceFS by name. That was a partial capture, not a complete reconciliation of the discussion.

Newly retrieved conversation excerpts also recover the assistant's candidate shortlist: **JuiceFS, SeaweedFS, rclone VFS, B2/R2 object storage, E2B and OpenShell**, plus private mesh networking. These are historical research candidates, not independently verified equivalents, installed dependencies or user-approved provider decisions. The exact OpenShell project and relevant versions/licences still need checking before adoption.

Preserve the requested distinction between ALFRED's continuing identity/control, files available across machines, and the computing environments used by its agents. In particular, “isolated disposable worker” must not silently replace the persistent, reusable machine model that makes boxd relevant. Compare both lifecycles explicitly. See section 8 for the targeted coverage audit. This revision does not choose, benchmark, procure or install any candidate.

### C. Independent products connected through ALFRED

Origin: the 27 September specialist-product discussion. The accepted direction keeps God's Eye, Noir, Loc8, ENDSTATE and 8BALL independent while allowing ALFRED to obtain authorised context and invoke permitted capabilities. Do not merge those codebases into ALFRED.

Map to `OPS-001`, `CON-001`, `ACT-001`, `MEM-003` and `MEM-016`. A common adapter contract was proposed under the working name ALFRED Capability Protocol/Fabric. It should describe product identity, capabilities, stable entity identifiers, source/observation basis, source timestamps, availability, permissions, supported actions and result receipts.

Start with one read-only test adapter. Do not label an event as live merely because it reached ALFRED recently: preserve the source's original observation time, replay/simulation status and health. Reading an operational observation, generating a plan and executing an action remain separate capabilities. A visual link must not imply control of a device or product.

No particular provider selection, complete protocol specification or live integration was verified in this reconciliation.

### D. Reasoning and executive workflows are explicit whole-product workstreams

Origin: the 27 September main-product conversation and 1 October master handoff. These are not wholly new ideas: the main PRD already includes `INT-001`, `INT-002`, `ATT-001` and `ACT-001`. The change is to give them visible execution plans, ownership and acceptance rather than imply that finishing M01–M12 delivers the entire product.

Reasoning/runtime work must earn claims about source support, uncertainty, multi-step tasks, model availability, interruption, context budgets and supervised tool use. Executive work covers goals, commitments, planning, decisions, preparation, follow-up and cross-project dependencies. Reuse existing queues, ledgers and Pulse routines and extend their missing behaviour deliberately.

Native packaging, voice, real account workflows, team use and deployment remain visible later workstreams. They must not disappear into an all-purpose M12 item, nor be described as completed because the interface has matching icons.

## 5. Recommended execution order

### First: reconcile completed and partial branch work

Review PR #15 and the completed M01/M03 portion of PR #16 together on an integration branch. PR #17 includes PR #16 plus paused M02/M06 work, so either retain its partial work separately or explicitly finish and validate it before promoting those capabilities. Preserve every relevant source change and run combined acceptance. Review/merge status must reflect the result, not an indefinite blanket draft policy.

### Next: one genuinely connected project slice

Use invented/non-sensitive source material with the real backend. Build the read-only graph projection and select one project. Inspect its source, ask a scoped contextual question through the existing conversation path, and refresh the same records in the executive view. Change a source and confirm stale data is not silently reused. Keep model availability honest.

This is a connection milestone, not a claim of general agent intelligence. It does not require all future storage, voice or specialist integrations to be finished first.

### In parallel: finish access, memory lifecycle and infrastructure design

Complete the necessary M02 access workflows, M05 private-storage/deletion/recovery work and the remaining useful memory loop. M06 needs its measured retrieval comparison. Real personal/company data requires the relevant access and lifecycle acceptance; synthetic development can continue without pretending those gates are already complete.

Write the distributed-node, file-service and sandbox interfaces in parallel, but do not expand the first connected-project milestone into a full cloud platform rollout.

### Then: one real connector, one bounded worker and specialist expansion

After their contracts and security prerequisites are ready, validate a read-only connector, then one harmless approved action with a reconciled outcome. Add one isolated remote job and demonstrate useful failure/cancellation behaviour. Extend across specialist products incrementally. Voice/native packaging follows explicit interaction and device tests.

## 6. How to update the existing plan without another competing backlog

Keep `docs/PRD.md` as the whole-product requirements source and `docs/ROADMAP.md` as the whole-product sequence. Keep `plans/memory-backlog.json` for M01–M12. Reference the console documentation rather than duplicating it. Promote this amendment into those existing documents after review, preserving their historical evidence.

For each requirement, record separately:

| Field | Purpose |
|---|---|
| Decision state | Accepted requirement, clarified requirement, proposal, research candidate or deferred item. |
| Implementation state | Not started, partial, implemented on branch, or accepted implementation. |
| Integration state | Isolated, fixture-connected, backend-connected or externally connected. |
| Delivery state | PR/commit, merge status and deployment status, independently. |
| Evidence | Exact tests/receipts and their limits; no single overall completion percentage. |
| Ownership and dependencies | Which builder owns it and which existing subsystem must be reused. |
| Origin and acceptance | Source discussion/document and an observable definition of done. |

A substantive handoff should list what changed, what was discovered, whether it is already covered by an existing requirement, and what remains only a candidate. Suggestions from chats are not automatically owner-approved scope. Further uncollected research should be marked awaiting reconciliation rather than represented as incorporated.

## 7. Source register and limitations

Live repository records read for this reconciliation:

- Main `8398c7437cb0ef1386d8dc4ff1f9e92fb2557ca2`: `docs/PRD.md` and `docs/ROADMAP.md`.
- PR #15: console-refinement delivery description and current open/draft metadata at `f7c41ce228b83257ad1852ba0f122b2afbc0f2db`.
- PR #16: M01/M03 delivery description and current open/draft metadata at `18dcfb39a3244fe21caf1d7ed2887443cf490914`.
- PR #17: paused checkpoint and `docs/MASTER_HANDOFF_2026-10-01.md` at `07573dfdbe906fb3932a31e440d342dfafb089bc`.

Retrieved conversation context:

- 27 September: console direction, project/graph interaction and independent specialist products connected through ALFRED.
- 29 September: Open Source ALFRED Infrastructure, two computers, mobile/VPS use, cloud-backed files and remote workers.
- 1 October: whole-product reconciliation and correction of the alleged permanent no-merge/private-vault restriction.

The latest generated image and the current user conversation provide visual exploration, not runtime evidence. The searches did not establish a complete catalogue of every unsupplied plan. No new product implementation, benchmark, provider evaluation, private-data connection, purchase, merge or deployment was performed for this amendment.


## 8. Targeted coverage audit: boxd and the infrastructure conversation

### 8.1 What was actually recovered

**Original discussion:** “Open Source ALFRED Infrastructure”, 29 September 2026. Relevant user requests and assistant responses were retrieved as conversation excerpts on 2 October. This is not a full verbatim export or a proof that every follow-on thread has been retrieved.

The user's request connected several ideas: boxd.sh or an open-source alternative; a Space/SpaceFS-like or cheaper cloud-backed drive; the pCloud-style experience of files appearing as a second hard drive; ALFRED on one computer with another place to launch agents; access to much more storage; and using both computers with a VPS while away. The user then asked for a properly considered recommended architecture.

The assistant proposed one distributed ALFRED with a VPS coordinator, trusted home/laptop nodes, shared cloud-backed files and isolated workers. Home/Core/Drive/Forge were proposed organisational names. The retrieved evidence does not establish a final user decision to adopt those labels, a particular provider, or a complete implementation.

### 8.2 What version 1 captured and lost

| Original element | Version 1 coverage | Version 1.1 treatment |
|---|---|---|
| boxd.sh as the motivating compute reference | Not named. Generic remote workers were recorded. | Named explicitly, with persistent-machine lifecycle kept separate from disposable sandbox execution. |
| Request for open-source or self-hosted alternatives | Broad shortlist only; JuiceFS named. | Restores the recovered candidate names and the need to verify licensing, deployability and functional fit. |
| Space/SpaceFS, originally typed “spacedfs” | Not named. | Preserves the original uncertain spelling and the recovered interpretation; current official Space documentation checked separately. |
| pCloud-like streaming second hard drive | Cloud-backed files, cache and availability captured, but the named reference and precise interaction were absent. | Makes on-demand access without fully replicating the dataset an explicit capability to evaluate. |
| ALFRED across both computers | Captured at requirement level. | Retained, without claiming an implemented sync or identity system. |
| VPS availability while away | Captured at requirement level. | Retained; coordinator placement remains an architecture proposal. |
| Another machine/service launching agents | Captured at requirement level. | Retained with explicit persistent versus disposable lifecycle comparison. |
| Expandable storage | Captured at requirement level. | Retained with capacity, cost, cache and recovery limits; not literal infinite storage. |
| Forks, snapshots, pause/resume and hibernation | Not individually specified. | Added below as currently verified boxd capabilities to evaluate, not retroactive claims that the user explicitly approved each feature. |

### 8.3 Current public checks, separate from historical recall

**boxd:** The official product page currently describes persistent isolated Linux computers and lists creating, forking, snapshots, checkpoints, pause/resume and hibernation. Its self-hosted offering is also described publicly. These are provider claims and an evaluation reference, not a benchmark or security validation performed for ALFRED. “Self-hosted” must not be treated as proof of an open-source licence. [P1, P2]

**Space:** The official documentation describes cloud-backed file access, local caching, drive forks and versioned writes. This supports distinguishing the file-access service from the machines that use it. Filesystem/drive forks and full running-machine forks are different capabilities and must not be conflated. No performance, pricing or universal application-compatibility claim is adopted here. [P3, P4]

**pCloud:** Preserved as the user's analogy for the experience. It was not selected or newly benchmarked in this correction.

**Other candidates:** JuiceFS, SeaweedFS, rclone VFS, B2/R2, E2B and OpenShell are restored because they appeared in retrieved discussion context. Their exact licences, current versions, suitability and equivalence have not been re-evaluated in this correction. Do not install them just because their names are now in this document.

### 8.4 Requirements and evaluation questions to retain

These are proposed elaborations for the existing runtime/storage workstreams, not a second authoritative backlog.

**Compute lifecycle:** Compare reusable persistent agent machines with disposable job sandboxes. Specify which jobs need package/process continuity, how a paused job resumes, what a fork copies, how outputs return, and how credentials and side effects are kept distinct after a fork. Checkpointing a machine must not imply that an external side effect can be rolled back.

**Shared files:** Test authorised on-demand reads from a cloud-backed drive without requiring the whole dataset to fit locally. Define cached versus unavailable content, writes and conflict handling, revision identity, quotas, network loss and backup/restore. Keep authoritative databases, secrets and temporary worker files separate from a generic synced folder.

**Multi-machine operation:** Make the laptop-disconnected case explicit. Distinguish the interface closing, a worker losing its connection, a job continuing on a remote host, and a job actually failing. Use one reconciled job identity and avoid duplicate dispatch. The user should be able to tell where work runs and whether its result is current.

**Provider choice:** Keep hosted boxd, self-hosted offerings and open-source alternatives as separately evaluated options. Compare actual persistence/isolation, supported hardware and operating systems, resource requirements, licence obligations, data access, operational burden and cost before selecting a stack. No procurement or deployment follows from this document alone.

**First infrastructure acceptance proposal:** With synthetic files, start one bounded remote job, disconnect the local interface, reconnect and inspect its recorded outcome. Verify that authorised files are accessible without a full dataset copy and that a revoked or unapproved source is excluded. Test cancellation and retry without duplicate effects. Persistent-machine checkpoint/fork behaviour should be a separate test only if that capability is selected.

### 8.5 Coverage of other ALFRED chats

Targeted retrieval also surfaced original ALFRED source/agent research, Obsidian and broader-memory discussions, the independent-specialist-product direction, and the console design/build discussions. It corroborates that these streams exist; it does not establish that all messages and artefacts in them are incorporated here.

| Discussion stream | Evidence used so far | Coverage conclusion |
|---|---|---|
| Original ALFRED foundation and source/agent research, 25–27 September | Retrieved conversation excerpts and the repository records listed in section 7. | Partial historical reconciliation; not every candidate/adoption rationale checked. |
| Console and graph design/build | Current conversation, supplied reference images, source and named delivery records from version 1. | Detailed local coverage, not a claim that every visual iteration was inventoried. |
| Specialist products and capability interfaces, 27 September | Retrieved excerpts and existing integration requirements. | Direction captured; exact external product contracts and every connected-product discussion not fully reconciled. |
| boxd / Space / cloud files / two computers / VPS, 29 September | Newly retrieved original excerpts plus targeted public identity checks. | Named discussion now explicitly covered at requirements/candidate level; no implementation or final provider choice verified. |
| M-series and whole-product master handoff, 30 September–1 October | Named PRs and master handoff read for version 1. | Those checkpoints are covered; not proof that all later or unpublished work is captured. |
| Other ALFRED chats, commercial planning, device/runtime research and unsupplied artefacts | No complete source inventory established. | Still awaiting systematic reconciliation; do not label complete. |

The master-plan coverage register should attach every incorporated requirement to its originating chat/document, date, decision state and destination requirement. It should also retain a reviewed-with-no-new-requirements outcome, duplicates, superseded decisions, retrieval-only summaries and inaccessible/missing sources. There is currently no verified denominator for “all chats”, so no meaningful completeness percentage is claimed.

### 8.6 Evidence register for this correction

**Historical conversation evidence:** Relevant excerpts retrieved from the 29 September “Open Source ALFRED Infrastructure” thread, including the first request about boxd/cloud drives and the follow-up about both computers and a VPS. Further excerpts from original ALFRED foundation/memory, specialist integration and console discussions were used only for the partial coverage register above. These are retrieved context, not full transcript exports.

**Original artefact checked:** The complete 164-line version-1 plan amendment supplied in this conversation. Sections 4A–4B contained the high-level infrastructure requirements but did not name boxd, Space/SpaceFS or pCloud.

**Public references checked on 2 October 2026:**

```text
[P1] boxd official product page: https://boxd.sh/
[P2] boxd official self-host/pricing description: https://boxd.sh/pricing/
[P3] Space official documentation: https://docs.spacefs.com/
[P4] Space official enterprise file-access description: https://spacefs.com/enterprise/
```

This is a targeted correction that closes a demonstrated omission. It is not the completed all-chat master plan. It makes no new claim of code execution, tested infrastructure, service connection, merge or deployment.
