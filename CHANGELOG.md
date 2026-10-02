# Changelog

All notable changes to ALFRED, newest first. Dates are the day the work was committed. Requirement IDs (MEM, SYS, INT, ACT, ATT, CON, VOI, OPS, UX, RUN) refer to [plans/requirement-register.json](plans/requirement-register.json); M-numbers refer to [plans/memory-backlog.json](plans/memory-backlog.json). "Implemented" always means implemented on the named branch against synthetic data, tested, and not deployed. Bugs are logged separately in [BUGS_AND_FIXES.md](BUGS_AND_FIXES.md).

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
