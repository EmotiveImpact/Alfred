# Changelog

All notable changes to ALFRED, newest first. Dates are the day the work was committed. Requirement IDs (MEM, SYS, INT, ACT, ATT, CON, VOI, OPS, UX, RUN) refer to [plans/requirement-register.json](plans/requirement-register.json); M-numbers refer to [plans/memory-backlog.json](plans/memory-backlog.json). "Implemented" always means implemented on the named branch against synthetic data, tested, and not deployed. Bugs are logged separately in [BUGS_AND_FIXES.md](BUGS_AND_FIXES.md).

## 30 October 2026 (evening): the sealed box connected to Claude, on the host, branch `claude/project-thread-ujui2p`

Master plan phase 2, second part. On 30 October the owner chose which areas may use cloud AI: personal notes only, to start. Offline tests only; no real model was called, no key exists anywhere in this work, and `desk serve` does not offer Hermes yet.

- **The Claude provider.** `alfred/anthropic_provider.py` makes the relay's calls: one fixed host over TLS, one path, no redirects followed, and the key read from a key source at each call and dropped after it, never stored, logged or passed to the box. A key that cannot be read, a network failure or a reply too large each stop the call with its own reason and nothing else.
- **Hermes on the host.** `alfred/hub_host.py` builds the goal hub with Hermes beside the synthetic test brain from a `HermesSetup` the owner gives (build record, model, price, key source, cloud areas); nothing has a default. At start the image must match this checkout's pins (`load_box`), or nothing is built. The cloud is allowed for the owner's areas only, so a company or client mandate naming Hermes is refused. A personal task runs from submission, through the box and the relay, to an accepted result against stand-ins for Docker and the network.
- **Current Claude models.** The relay no longer passes on Hermes's two beta headers, which are part of the standard API on current models. What Hermes sends to current models was checked against its pinned source; the two things that would need care later (thinking across several calls, and an effort setting) are written up in the [guide](docs/HERMES_BOX.md).
- **Left for the next change.** Reading the key from the Mac keychain or a server's secret store, which reuses the readers encryption step 1 adds, and then the `desk serve --hub hermes` switch and a run on the owner's Mac.

## 30 October 2026: Hermes in a sealed box, branch `claude/project-thread-ujui2p`

Master plan phase 2, first part; agent hub step H5. The owner chose Hermes as the first worker brain, run in a sealed Docker box. Synthetic data and a scripted stand-in model only; no real model was called and nothing is wired into the host. Merged with the owner's word on 30 October.

- **The sealed box.** `boxes/hermes/` pins Hermes at commit `8fe53200` (the one reviewed in the source library), its hashed wheel list and the base image digest; `tools/build_hermes_box.py` builds only if every pin holds. One box per task: no network, read-only, not root, home and task folder in memory, no Docker log, removed when the task ends. [Guide](docs/HERMES_BOX.md).
- **Hermes behind the plug.** `alfred/hermes_box.py`: the box proves its build, its settings (as Hermes itself reads them), its tool gate and its lack of network before anything private is sent. Hermes holds no key; ALFRED makes each model call, refuses provider-side tools, caps each call to the budget and charges the provider's usage. Every tool call is asked of ALFRED first; only `file.read` inside `/work` can be granted. A brain can now report why it stopped (`BrainFailure`), instead of a bare `brain_error`.
- **The six fence tests.** `tools/hermes_fence.py` runs them against the real box with real Hermes inside: memory and skill writes, every turn through ALFRED, the skills folder, nothing fetched at start, nothing left on disk, and no private area on a cloud model unless allowed; plus a planted instruction ending as a refused proposal. All hold. A new CI job rebuilds the box and reruns them. [Receipt](docs/evidence/hermes-box/RECEIPT.md).

## 30 October 2026: the agent drafts panel, branch `claude/project-thread-att046-agent-drafts`

Merged with the owner's word on 30 October. Synthetic data only; nothing deployed and nothing sends.

- **Agent drafts panel (C10, #48).** The console lists every draft a brain wrote, each saying where it came from: the owner's own words, wording from a named note, or stopped because an address came from a note. A stopped draft names the address, the note and when, and has no Approve; the owner can type the address themselves (the same one confirms it, a different one replaces it), after which it waits for exact approval like any other. Approving saves a local draft only. [Guide](docs/AGENT_DRAFTS.md), [receipt](docs/evidence/agent-drafts/RECEIPT.md).
- Found on the way and logged as C11, not yet fixed: `BrainHub.submit` binds a job to its mandate in a second transaction, so a worker can refuse a job it claims in between.

## 20 October 2026: the provenance gate, branch `claude/project-thread-att046-provenance-gate`

Merged with the owner's word on 20 October, after the owner chose blocking over warning. Synthetic data only; nothing deployed.

- **Provenance gate (C9, #44; master plan phase 2, the CaMeL idea).** Every brain proposal is labelled with where its contents came from. An email address, web address, domain, handle or phone number that appears only in a note, or nowhere, and not in the owner's own words, makes the proposal `steered_by_untrusted_text`; under the default `enforce` mode it is kept with its reason but never becomes an action to approve. `watch` only labels it. No screen shows brain proposals yet. [Guide](docs/PROVENANCE_GATE.md), [receipt](docs/evidence/provenance-gate/RECEIPT.md).

## 18 October 2026: the disk encryption check and the checks in CI, branches `claude/project-thread-att046-disk-check` and `-ci-checks`

Merged with the owner's word on 18 October. Synthetic data only; nothing deployed.

- **Full-disk encryption check at start (C8, #41; master plan phase 1).** `desk serve` says once, for the data folder and the vault, whether full-disk encryption covers them: FileVault on macOS, a dm-crypt (LUKS) layer through LVM and RAID on Linux, and "not confirmed" for anything it cannot read. `--disk-encryption require` refuses to start, before the lock or the database, unless every folder is confirmed. It only reads; commands run without a shell, with no input and a five-second deadline. [Guide](docs/DISK_ENCRYPTION.md), [receipt](docs/evidence/disk-encryption/RECEIPT.md).
- **The three repository checks run in CI (C5, #42).** The unified build's core job runs the egress audit, the adoption credit check and the public hygiene check on every pull request to `main` and every push to it.
- **B-031.** Two older workflows cut the full test suite off at five minutes; both now have fifteen. See [BUGS_AND_FIXES.md](BUGS_AND_FIXES.md).

## 17 and 18 October 2026 (night): the background build backlog, branches `claude/project-thread-att046-<item>`

Eleven pull requests from [coordination/BACKLOG.md](coordination/BACKLOG.md), plus C2 (#29) in its own entry below, each built tests first on its own branch and merged with ordinary merge commits after the owner's word on 18 October. Synthetic data only; no model ran and nothing under `third_party/` was installed, run or imported. Nothing is deployed.

- **The backlog and the claim release (C1, #28).** One ordered list of the work that needs none of the owner's open decisions. Astra's two claims were released when the owner moved all of Astra's work to Claude.
- **Ask page fix (C7, #30).** B-030: a question asked before the capability answer arrived left the "Local model" option disabled. See [BUGS_AND_FIXES.md](BUGS_AND_FIXES.md).
- **Checks run when a result arrives (A3, #33).** A goal task whose mandate declares acceptance checks is verified automatically, once, when its result is accounted; a restart, a second cycle or the owner verifying at the same moment never gives a second run. [Receipt](docs/evidence/hub-auto-verify/RECEIPT.md).
- **Who started each run (C3, #40).** The console goals panel says whether a verification run was automatic or started by the owner. [Receipt](docs/evidence/run-initiator/RECEIPT.md).
- **Secret scrubber (A2, #32).** `alfred/scrub.py` finds credentials in text and blanks them as `[redacted:<kind>]`. [Guide](docs/SECRET_SCRUBBING.md), [receipt](docs/evidence/secret-scrubbing/RECEIPT.md).
- **Scrubbing wired in (C4, #36).** Brain packets are scrubbed before they leave, and harvested worker text before it is proposed; the task records how many of each kind were removed. Notes in the vault are not scrubbed on read yet, which waits on encryption step 2. [Receipt](docs/evidence/scrub-wiring/RECEIPT.md).
- **Question set harness (A1, #38).** `tools/question_set.py` runs the owner's own question file against ALFRED's search and scores which notes come back, offline and without a model. [Guide](docs/QUESTION_SET.md), [receipt](docs/evidence/question-set/RECEIPT.md).
- **Meaning search groundwork (A4, #37).** `alfred/semantic.py`: passages, an embedder interface, an in-memory index and blending with keyword results. Not wired into search, no embedding model chosen, nothing written to disk. [Guide](docs/MEANING_SEARCH.md), [receipt](docs/evidence/meaning-search/RECEIPT.md).
- **Network egress audit (A5, #34).** `tools/egress_audit.py` fails when ALFRED code outside a reviewed list imports something able to use the network. [Guide](docs/EGRESS_AUDIT.md), [receipt](docs/evidence/egress-audit/RECEIPT.md).
- **Adoption credit check (A6, #35).** `tools/check_adoptions.py` checks that any file borrowed from the shelf names its project, file, commit and licence, matching the pinned records. Nothing is borrowed yet. [Guide](docs/ADOPTION_CHECK.md), [receipt](docs/evidence/adoption-check/RECEIPT.md).
- **Public hygiene check (A7, #39).** `tools/check_public_hygiene.py` fails when a tracked file holds a credential-shaped literal, a home-directory path or a personal email address, with each reviewed exception pinned by hash. [Guide](docs/PUBLIC_HYGIENE.md), [receipt](docs/evidence/public-hygiene/RECEIPT.md).

## 17 October 2026 (night): the host builds the goal hub when asked, branch `claude/project-thread-att046-hub-host`

- **`desk serve --hub synthetic` (backlog C2).** `alfred/hub_host.py` builds the brain hub and goal hub over the host's own job coordinator, registers only the deterministic synthetic test brain, allows no cloud scope and no tool, and enrols one `local-brain` worker that takes brain tasks only. The host's supervisor loop accounts results and runs heartbeats, so `/desk/hub`, mandates, budgets and verification work end to end on the real desk with test data. Off by default: without the switch no hub tables or brain worker are created and `/desk/hub` still answers `hub_not_configured`. No real brain is offered, because which brain comes first is the owner's choice. [Receipt](docs/evidence/hub-host/RECEIPT.md).

## 17 October 2026 (evening): two agents, one repository, branch `claude/project-thread-r6ndba`

Process and tooling only; no runtime change.

- **Claude and Astra share the work through claims.** Astra (OpenAI Codex, from Codex cloud) joins Claude. [coordination/README.md](coordination/README.md) explains the split: each piece of work has a claim in `coordination/claims/` listing its exact paths; Astra edits only its live claims on `main`, Claude keeps every shared file and everything unclaimed, and the owner approves every merge. Root `AGENTS.md` gains the rules for both agents and a shared engineering bar (tests first, small pull requests, green CI, no weakened checks).
- **The boundary is checked, not trusted.** `tools/check_claims.py` validates claims (format, no overlapping live paths, no shared files claimed by Astra) and, on every pull request, fails a `codex/` branch that changes anything outside its claims and a `claude/` branch that changes a path Astra has claimed. Synthetic Git tests in `tools/test_claims.py`; both run in unified CI.
- **First claims.** Astra: the real question set harness and the secret scrubber, with briefs in `coordination/briefs/`. Claude: the encryption foundation (plan phase 1), being built in its own thread.

## 17 October 2026: research shelf and integration plan, branch `claude/project-thread-t9ssyl`

Documentation and inert reference data only; no runtime change. Nothing under `third_party/` was installed, run or imported.

- **Research shelf.** `third_party/research-shelf/` pins Tencent-Hunyuan/Hy-Memory, mnemosyne-oss/mnemosyne, vectorize-io/hindsight, OSU-NLP-Group/HippoRAG, joonspk-research/generative_agents (memory back end only) and agiresearch/A-mem at the commits reviewed, with each licence file's Git blob recorded after a manual read (MIT or Apache-2.0). 7,328 source-text files, every omission listed per manifest. `tools/build_research_shelf.py` reads files straight from Git objects, so no upstream filter or script runs; `--verify` checks every byte offline and runs in unified CI with its own synthetic tests. The 27 September library stays untouched.
- **Integration plan.** [research/INTEGRATION_PLAN_2026-10-17.md](research/INTEGRATION_PLAN_2026-10-17.md) combines the memory, brain-layer, Hermes and voice research into phases 0 to 7 with the owner's eight decisions marked. The five underlying write-ups are in [research/2026-10-17/](research/2026-10-17/).

## 16 October 2026 (afternoon): agent hub steps H2 to H4, branch `claude/project-thread-qj8beq`

All three run against the synthetic brain only; no model ran and nothing under `third_party/` was installed, run or imported.

- **Goals, mandates, budgets and heartbeats (H2; INT-001, ATT-001).** `alfred/hub_goals.py` links the owner's executive goals to mandates: scope class, deadline, success test text, autonomy 0 to 2 per kind of work (3 and 4 still refused), allowed and assigned brains, a tool allowlist, a budget and an optional heartbeat. With the goal hub attached, a brain task outside a current mandate is refused before a job exists, and checked again just before the brain starts. Budgets per goal, per brain and overall pause work at the hard stop and cancel what is running; nothing resumes on its own. Heartbeats run from the supervisor cycle and missed slots are counted, never replayed. Pause, resume, stop and reassign from `/desk/hub` and a "Goals and brains" console dialog; a stop is journalled so a restore cannot undo it. The host does not construct a goal hub until a real brain exists. [Receipt](docs/evidence/hub-goals/RECEIPT.md).
- **Daily learning (H3; INT-001, ATT-001, MEM-015).** `alfred/learning.py`, a deterministic `daily-learning` routine, gathers value-free evidence and proposes preferences, procedure drafts and routing notes, each tied to at least three pieces of evidence. Every proposal goes to a review inbox; a daily list can be approved in one action for exactly the listed versions, or dismissed item by item. An owner-authored trusted-kinds rule, off by default, may accept only writing length and structure preferences, labelled "Accepted by your rule" and undoable; facts, procedures, routing and harvested items always ask. Accepted records can travel in a task packet's `learned` field. Worker-staged skills and memories become proposals only. An upstream watch compares pinned versions with an owner-supplied file and writes update briefs; it fetches and installs nothing. A test shows learning changes no policy, grant, scope, autonomy or budget. Learning tab in the Routines dialog. [Receipt](docs/evidence/hub-learning/RECEIPT.md).
- **Independent verification (H4; ACT-001, INT-001).** `alfred/verification.py` runs owner-declared acceptance checks on what a brain returned: citations, cited numbers, artefact sections, fields, a strict schema subset, a time-limited pattern, out-of-scope content and read-back of an executed local draft. Only passed checks or the owner's acknowledgement of the exact run count as verified; a check that cannot run is "unverifiable", never passed, and a brain's own "done" is never read as status. A draft a brain proposed cannot be approved until its checks have run, nor while any has failed without acknowledgement. [Receipt](docs/evidence/hub-verify/RECEIPT.md).
- **The three steps wired together.** Routing notes in the daily learning count how each brain's results fared under the verification checks (verified, failed checks, could not be verified, no checks, not returned), never the brain's own confidence, and a result with no declared checks never counts as verified. Goal setbacks (budget stops, pauses, mandate refusals, missed heartbeats) become routing notes too. Mandates can declare acceptance checks that ALFRED adds to every task they authorise. Verification is available under `/desk/hub/results` and in a "Results and checks" section of the Goals and brains dialog, with acknowledgement behind a confirmation. [Receipt](docs/evidence/hub-integrate/RECEIPT.md).
- **Agent hub design** updated with the owner's direction to redirect Hermes's memory and self-learning into ALFRED rather than switch them off, and the one-tap daily list with the trusted-kinds rule.

## 16 October 2026: the six decision-free build items and the agent hub, branch `claude/project-thread-qj8beq`

- **Drafts are kept (owner decision).** A lapsed approval no longer makes a draft disappear. Drafts are listed and searchable by text, date and status (lapsed, archived, withdrawn), can be archived and unarchived (version-checked, audited) and proposed again as a new action with a fresh fingerprint and rechecked sources, over `/desk/drafts` and a console "Find drafts" panel. Forgetting a source or statement withdraws dependent kept and archived drafts. [Receipt](docs/evidence/drafts-archive/RECEIPT.md).
- **Strict grants by default (plan 1.2; SYS-001, MEM-009, M02).** New workspaces grant no source to anyone, the owner included, until the owner grants it; existing databases keep their access and are recorded as legacy once. Owners enrol people with a single-use code, list them and switch read or model per source over HTTP and in the console access panel, version-checked and journalled. Review history now belongs to the person, so a paired device shows the same history. [Receipt](docs/evidence/strict-grants/RECEIPT.md).
- **Deletion and restore accounting (plan 1.3; MEM-010, MEM-013, M05).** Every forget receipt counts each kind of dependent before and after from one scan, shared with the new `deletion-report` command and `GET /desk/deletion-report/{source|entity|statement}/{id}`. Value-free history is kept by default, with an explicit, journalled `purge_history`. `restore` reports what the journal removed again. Export format 2 adds review history and routine settings and a value-free register of exports on disk. [Receipt](docs/evidence/deletion-accounting/RECEIPT.md).
- **Host restart and recovery (plan 1.4; RUN-001, M09).** `serve` records clean stops; after an unclean one it marks waiting questions interrupted with a reason, reports started jobs as `effect_unknown` (never re-run), requeues unstarted leases and counts missed routine slots. New read-only `doctor` and `service-file` (text only, never installed). [Receipt](docs/evidence/host-recovery/RECEIPT.md).
- **Obsidian compatibility (plan 1.5; MEM-001, MEM-002, M01).** The scanner reads frontmatter aliases and tags, inline and nested tags, `[[link|alias]]`, embeds, nested heading links, paragraph and standalone block IDs, callouts and `%%` comments as Obsidian does; identical conflict copies from unrecognised tools are found by content hash. **Approved `vault.append_section` (MEM-011, M04):** a separately granted write that inserts under a named heading after approval of an exact diff, never appends twice, refuses on any concurrent edit and reads back. [Receipt](docs/evidence/obsidian-compat/RECEIPT.md).
- **Capture policies (plan 2.4; MEM-004, M04, M10).** Owner-authored, versioned, deterministic rules (line prefix, dated line) propose reviewed-memory statements bound to exact note, revision and line. Nothing is auto-accepted; rescans and dismissed lines are not re-offered; daily budgets count excess. HTTP under `/desk/capture` and a read-only Capture tab in the console. [Receipt](docs/evidence/capture-policies/RECEIPT.md).
- **Agent hub design and brain plug (INT-001, RUN-003).** [docs/AGENT_HUB.md](docs/AGENT_HUB.md): many swappable brains (Hermes, Claude, local Qwen, optionally Paperclip) under one ALFRED authority, with daily learning that stays in ALFRED. Step H1 built in `alfred/brain.py`: task packet and result bundle contracts, brain registry and policy (cloud brains refused until the owner allows one, empty tool allowlist by default, autonomy 3 and 4 refused), an ALFRED-owned budget meter, a `brain_task` job kind on the existing coordinator, strict result checks and a deterministic synthetic brain. No real model. [Receipt](docs/evidence/brain-plug/RECEIPT.md).

## Unreleased: branch `claude/alfred-development-qpgxhg`, draft PR #18

### 2 October 2026 (evening)

- **Fixed:** an open confirmation or form in the record inspector no longer disappears when the workspace changes ([B-026](BUGS_AND_FIXES.md)).
- **Fixed:** the read-aloud browser check no longer races the server, and playback history keeps creation order within a second ([B-025](BUGS_AND_FIXES.md)).
- **Documentation system.** Rewritten README with a full run-through, this changelog, [BUGS_AND_FIXES.md](BUGS_AND_FIXES.md) and [docs/INDEX.md](docs/INDEX.md), a map of every document, and [docs/REMAINING_BUILD_PLAN.md](docs/REMAINING_BUILD_PLAN.md), the ordered plan for everything still to build.
- **Routines (M10: ATT-001, MEM-004, MEM-015), merge `e5917441e`.** Two allowlisted routines, commitment review and morning brief, authored by the hosted owner with schedules, run and nomination budgets, quiet hours, a show-now or hold-for-brief choice, and per-routine and workspace pause. Authority, grants and the pause are rechecked inside every run; run outcomes hold citations and counts only. Reminders are accepted, accepted with a follow-up or dismissed. A draft offer only proposes a `message.draft` that still needs exact approval. A read-only procedure registry; tests show procedure text changes nothing. Routines dialog in the console. `tools/check_routines_browser.py` added to CI.
- **Temporal review (MEM-007), merge `afbf72b8d`.** A value-free recorded history of every review transition (earlier statements migrated, unknown times marked); valid periods fixed after the first decision; disputes, withdrawal and supersession with lineage both ways; withheld and restored support recorded as observations; a deterministic as-of report. Console review queue, statement history and as-of view. `tools/check_temporal_review_browser.py` added to CI.
- **Host health and pause (RUN-001), `b5cb60a59`.** `GET /desk/console/health`; a health panel in Console controls; owner pause and resume with confirmation.
- **Spoken output (VOI-001), `1f12e123b`.** Read an answer aloud with on-device voices only. Generated, playing, played (a device report), stopped and acknowledged are distinct states. The server stores a hash and length of the spoken text, never the text. No microphone.
- **Index rebuild (MEM-012), `b45bc2ac7`.** `rebuild-index` rebuilds projections atomically while the host is stopped, keeping identities, revisions and reviews, and reports what changed.
- **Answer support (INT-002), `5566cad81`.** Every answer reports which asked words were found, withheld reviewed statements by reason, retrieval counts and model review findings. A 13-case evaluation with published denominators (`tools/evaluate_answers.py`).
- **Console: sync conflicts and connectors, `df306d41e`.** Conflict copies and export connectors shown in the inspector; imported items labelled; `connector.read` Import switch in the access panel.

### 2 October 2026 (afternoon)

- **Sync safety and export (MEM-014, MEM-013), `0059bdea8`.** Syncthing, Dropbox and Nextcloud conflict copies recognised and never indexed; a placement guard keeps the live database out of synced folders, Git trees and vaults; portable JSON and Markdown export with checksums.
- **Executive workflows (ATT-002, ATT-001), merge `f358b09a8`.** Responsible labels, decision options with decide and reopen trails, assembled briefs, in-app attention rules with snooze, derived insights; all in the connected console.
- **Whole-source removal (MEM-010), `9ab48c367`.** Remove a source with a receipt; journalled and replayed on restore; dependent statements, answers, drafts and job results handled.
- **Read-only connectors (CON-001), merge `a6d8fd10e`.** `.ics` and `.vcf` export-file importers with freshness and dry runs.
- **Device pairing (SYS-001, M02), `fcdf7e9ae`.** Pair another device with a single-use code; each device gets its own bounded key; people revoke their own other devices.
- **Console jobs view, `73519da62`.** Bounded jobs on the selected note; job history follows strict grants.
- **Specialist capability contract (OPS-002), `d248b4dc8`.** Contract version 1 with a synthetic simulation adapter.
- **Identity grants (M02), `870751368`.** Grant workflows, single-use invitations and offline rotation.
- **Executive records (ATT-002), `a6be61708`.** Goals, priorities, commitments, decisions and milestones shared by the panel and the graph.
- **Local jobs (RUN-002, RUN-003, SYS-003), merges `d77f99987` and `9ec0f7904`.** Stage 0 coordinator, subprocess backend, bounded cache; results follow forget and revocation.
- **Remember-this capture and inbox notes (MEM-005, MEM-011), `fd85dd785`.** Previewed, reviewed captures; approved create-only inbox notes verified after writing.
- **Lexical retrieval evaluation (MEM-008, M06), `b036cee87`.** Deterministic baseline evaluation.
- **Forget and restore (MEM-010, M05), `19c4c75ea`.** Forget statements and entities with receipts; restore without resurrection; withheld support kept distinct from destroyed.
- **Requirement register, `02ca166c0`.** The owner's reconciliation and mandate turned into a machine-checked requirement-to-delivery register.
- **Connected console (UX-001, UX-002, MEM-016), `8d0f5cb9e`.** The premium console attached to the real backend: authenticated read-only projection, selection-aware questions, access-loss handling.
- **Integration of PRs #15, #16 and #17**, `dd096d26b` to `dc1935f75`.

### 30 September to 1 October 2026 (PRs #16 and #17)

- **M03 reviewed-memory context bridge, `18dcfb39a`.** Accepted, current, authorised statements enter bounded conversation context with exact support.
- **M01 selected-vault identity, `1d83f601c` and `87a2b0604`.** Stable note identity across renames and reused paths; validated anchors.
- Paused memory programme handoff and owner clarification recorded (`165e24376`, `07573dfdb`).

### 27 September 2026 (PR #15, console refinement)

- Compact operational shell, component boundaries and stable shader rendering (`88bee6e70`); delicate graph material and builder handoff (`0826be04d`); renderer-aware browser tests; navigation state separated into pointer, focus and pinned (`b22399327`).

## main, 27 September 2026: unified baseline `8398c7437`

The owner authorised merging the stacked development PRs (#1, #5, #6, #7, #8, #9, #10, #13, #12) into `main` in dependency order with ordinary merge commits:

1. Foundation (`167e8d07c`): product brief, architecture, security and data boundaries.
2. Persistent local core (`be806434c`): SQLite store, authenticated loopback sessions, exact approvals for local drafts.
3. Desk and knowledge workspace (`9e1c5d1c8`): read-only note and project indexing, source inspection.
4. Source-grounded questions (`b44d8c9bd`): answers built only from permitted excerpts.
5. OS shell and Pulse (`aed704446`): the interaction shell and fixed bounded routines.
6. Persistent conversations (`fa1626583`): bounded conversation queue and evidence review.
7. Reviewed memory and retention (`27e2c17ed`): manual reviewed statements, conflicts, validity, retention.
8. React Three Fiber console (`cead85d38`): the premium console with fictional fixtures.
9. Current PRD, memory programme and source shelf (`03e946fc3`): the 12-job memory backlog and inert source library.
10. Unified operational and executive baseline (`8398c7437`): positioning, consolidation record and unified CI.

## 25 September 2026

- Repository created (`b0614d70a`).
