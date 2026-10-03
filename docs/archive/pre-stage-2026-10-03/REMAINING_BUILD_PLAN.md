# Remaining build plan

2 October 2026, written on the integration branch at the checkpoint in
[CHECKPOINT_2026-10-02.md](CHECKPOINT_2026-10-02.md). This is the full plan for everything the
PRD still needs, in dependency order, so that a new session can pick any item and build it
without re-deriving the state. It extends the [roadmap](ROADMAP.md); it does not replace the
[requirement register](../plans/requirement-register.json), which stays the only record of what is
actually done. Update the register and [CHANGELOG.md](../CHANGELOG.md) as each item lands.

Sizes are rough build-session estimates with the current tooling: **S** under half a session,
**M** one session, **L** two or more, or needs a worktree agent. "Owner" marks a decision only
the owner can make; everything else can be built now against synthetic data.

## Where we are

33 requirements: 8 implemented on the branch, 24 partial, 1 not started. Every surface exists
and is tested (backend 1,112 tests; console 140 unit, 29 demo, 262 connected-browser checks).
What is left falls into four gates, matching the roadmap's release gates:

| Gate | Purpose | Blocks |
|---|---|---|
| 1. Private pilot | Real private data on one machine, safely | Encryption, strict grants by default, deletion accounting, export of history, host recovery |
| 2. Useful assistant | Measured usefulness, one real workflow | Reasoning runtime, semantic evaluation, document ingestion, capture policies, a real connector, push-to-talk |
| 3. More than one machine | Second node, isolated workers, files | Provider decisions, enrolment, isolation backend, cloud storage |
| 4. Team and operational | Role-limited workspaces and specialist products | Multi-owner identity, real specialist interfaces |

Items inside a gate are listed in build order. An item lower down never needs one above it
unless its **Needs** line says so.

## Gate 0: finish this delivery

| # | Item | Size | Needs |
|---|---|---|---|
| 0.1 | Owner reviews and merges [PR #18](https://github.com/EmotiveImpact/Alfred/pull/18) into `main` with an ordinary merge commit; close #15, #16, #17 as superseded. | Owner | CI green (it is) |
| 0.2 | After the merge, restart the development branch from `main`, update `SESSION_HANDOFF.md` and the register's `merge` column (`merged_to_main` where true). | S | 0.1 |
| 0.3 | Answer the five open design questions from the wave 2 work (time zones, who may author routines, re-offering expired drafts, closing the replaced statement's valid period, history in exports and purge on forget). Defaults if unanswered: fixed offsets; owner only; no re-offer; keep supersession as retraction; include history in export, keep value-free rows on forget. | Owner | |

## Gate 1: private pilot

### 1.1 Application encryption and key custody (SYS-002, M05) · L · Owner first

**Decide (owner):** where the key lives. Options, from least to most work: (a) rely on OS disk encryption (FileVault, LUKS, BitLocker) and have ALFRED verify and record it; (b) a passphrase-derived key held only in memory while the host runs, entered at `serve`; (c) OS keychain integration per platform. The backend is standard-library only, which has no AES; (b) or (c) needs a vetted dependency (`cryptography`) or the SQLCipher build of SQLite. That dependency is a deliberate adoption under AGENTS.md rules.

**Build:** `alfred/crypto.py` sealing the fields that hold private text (note excerpts in the index, reviewed values, conversation packets, job artefacts, exports and backups) with a per-workspace key; key rotation with re-sealing; `serve` refuses to open an encrypted workspace without the key; `backup` and `export` stay encrypted unless `--plain` is typed with a warning. Secure erasure stays explicitly out of scope (free pages and WAL); `VACUUM` after forget as a best effort, documented.

**Accept:** a copied database and backup reveal no private text without the key; rotation keeps every test passing; forget followed by `VACUUM` leaves no trace of the value in the file. Tests in `tests/test_encryption.py`; receipt `docs/evidence/encryption/`.

### 1.2 Strict grants by default (SYS-001, MEM-009, M02) · M

**Build:** new credentials receive no source grants until the owner grants them; the demo `init` grants the owner and source keys explicitly. Enrolment and administration over HTTP: invite, accept, list people, grant and revoke per source, all version-checked, all journalled. Shared review history across a person's devices (the history is per person, not per credential). Console access panel grows a people list and per-source switches.

**Accept:** a new reader sees nothing until granted; losing a grant withholds mid-request (`tests/test_policy_strict.py`); pairing a device shows the same review history.

### 1.3 Deletion and restore accounting (MEM-010, MEM-013, M05) · M

**Build:** a single `forget` receipt that counts every dependent (statements, answers, drafts, job artefacts, cache copies, history rows, exports on disk that ALFRED wrote); `export` includes review history and routine settings (decision 0.3); `restore` reports what the journal removed again; a `deletion-report` command listing what the workspace still holds about a subject and where. Purge of value-free history rows on forget if the owner chooses.

**Accept:** forget, backup, restore, export on a fixture with every kind of dependent; the receipt and the report agree with a direct database scan.

### 1.4 Host restart and recovery (RUN-001, M09) · M

**Build:** on `serve`, reconcile interrupted work: queued questions marked interrupted with a visible reason, running jobs marked `effect_unknown`, routine slots missed counted; health reports the last clean stop; a `doctor` command checking data folder placement, permissions, WAL state, backup age and console build. Optional user-level service files (launchd plist, systemd user unit) generated by `python3 -m alfred.desk service-file`, never installed by ALFRED.

**Accept:** kill the host mid-job and mid-question, restart, see honest states (`tests/test_recovery.py`).

### 1.5 Full Obsidian compatibility and safe note writing (MEM-001, MEM-002, M01, M04) · L

**Build:** frontmatter aliases, `[[link|alias]]`, headings and block anchors (`^id`), embeds, callouts and tags read as Obsidian reads them; `.obsidian` ignored; a second approved write capability `vault.append_section` that appends under a named heading with a diff approval, idempotent retry and read-back; never rewrites human text. Conflict copies from unrecognised tools detected by content hash, not only by name.

**Accept:** the fixture vault from the Obsidian help site renders identically; writes survive a concurrent edit by refusing, never clobbering.

**Gate 1 exit:** 1.1 to 1.4 done and receipted; a real selected test vault exercised by the owner on one machine; limitations stated in a pilot receipt.

## Gate 2: useful assistant

### 2.1 Reasoning runtime selection (INT-001, M03, M07) · Owner, then M

**Decide (owner):** which model runs and where (local Ollama model already supported, tool free; or a provider with data terms). The blocked live-model comparison stays blocked until the owner reauthorises it with its own tool access.

**Build:** `alfred/runtime.py` as the one replaceable boundary: packet in, answer plus literal citations out, bounded time and tokens, purpose logged; the existing literal evidence checker and support report run on every answer; a provider adapter only when terms are recorded in the register. Model answers stay labelled as model proposals.

### 2.2 Semantic answer evaluation (INT-002, MEM-008, M06, M07) · M

**Build:** extend `tools/evaluate_answers.py` with a frozen 60-question set over the synthetic vault, scored for entailment by a second, independent check (the model judging its own answers is not evidence); publish denominators and failures; the same harness compares keyword, FTS5 and any hybrid retrieval. Hybrid retrieval is built only if the harness shows a measured gain.

### 2.3 Document ingestion (MEM-001, MEM-003, M08) · L · Owner on parser

**Decide (owner):** which parser dependency for PDF and office files, or text and Markdown only.

**Build:** `alfred/documents.py` giving every extracted block a page or block anchor, a hash and a revision; excerpts cite page and block; forget and source removal cover document blocks; documents join the rebuild. Office formats after PDF.

### 2.4 Automatic capture policies (MEM-004, M04, M10) · M

**Build:** per-type capture rules the owner authors (for example "a dated commitment in a meeting note proposes a commitment statement"); every proposal still enters the inbox for review; nothing becomes accepted automatically; a daily capture budget. Console: the policy list with counts of proposed, accepted and dismissed per policy.

### 2.5 Approved external workflow (ACT-001, CON-001, M11) · L · Owner on account

**Decide (owner):** the first real read-only account (calendar or contacts) and the one harmless write.

**Build:** an outbox with exact fingerprints, idempotency keys, capability-specific result reconciliation (read back after write; `effect_unknown` on timeout, never retried blindly), token custody under 1.1, and revocation that stops dispatch. Read-only first; the write only after the read path has run for the owner.

### 2.6 Routines maturity (ATT-001, MEM-015, M10) · M

**Build:** IANA time zones if 0.3 says so; per-person routine credentials so paired devices may author; a third routine kind only when a rule can be stated; measured relevance (accepted versus dismissed nominations over time, shown, never used to change rules automatically); a versioned procedure workflow (procedure drafts, review, supersession) that still never executes.

### 2.7 Push-to-talk (VOI-001, M12) · M · Owner first

**Decide (owner):** whether ALFRED may ever listen. If yes: a visible, held control; on-device recognition only; the transcript shown before it becomes a question; recording state in the health panel; nothing stored but the text the person confirms.

### 2.8 Sync lifecycle (MEM-014, M09) · M

**Build:** one sync client per device recorded in the workspace; freshness shown per vault; Dropbox, Nextcloud and iCloud conflict handling tested against real client output (owner supplies samples); conflict copies for unrecognised tools by hash (1.5).

**Gate 2 exit:** one real account read path and one approved write with reconciliation; measured answer quality; owner uses it daily for a month with the health panel showing no silent failures.

## Gate 3: more than one machine

### 3.1 Second trusted node (RUN-002, SYS-001) · L · Owner on provider and mesh

**Decide (owner):** where the authoritative database and job coordinator live; mesh (for example a private WireGuard or Tailscale network) and key expiry; spending ceiling.

**Build:** node enrolment by pairing code (reusing 1.2); one job authority with leases already in place; a second node that runs jobs only; events over the mesh; no second database. Research in [research/INFRASTRUCTURE_2026-10-02.md](../research/INFRASTRUCTURE_2026-10-02.md).

### 3.2 Isolated workers (RUN-003) · L · Owner on backend

**Decide (owner):** container, VM or remote sandbox backend.

**Build:** a worker backend behind the existing job interface with no network, declared inputs only, resource limits and signed results; the local-subprocess backend remains for development.

### 3.3 Files and object storage (SYS-003) · M · Owner on vendor and region

**Build:** the bounded cache gains a remote tier under the same hash verification and pins; which scopes may leave the primary machine is a per-scope setting the owner sets.

### 3.4 Native packaging (RUN-001) · M

**Build:** a signed single-folder distribution per platform with the console built in; service files from 1.4; an update check that only reports, never installs.

## Gate 4: team and operational

### 4.1 Role-limited team workspaces (OPS-001, SYS-001) · L

**Needs:** 1.2 and 3.1. Multi-owner administration, team roles (owner, lead, member, observer), per-workspace tenancy with separate databases, shared executive records with named responsibility, review history visible per role, and an acceptance that one tenant can never read another.

### 4.2 Real specialist adapters (OPS-001, OPS-002) · L · Owner supplies interfaces

**Needs:** actual ENDSTATE, Noir or other product interfaces, read before any adapter is written; contract version 1 already defines manifests, observation validation and labelling. Simulation, analysis, observation, receipt and human acknowledgement stay distinct; actions remain declared, never enabled, until an independent safety acceptance exists.

### 4.3 Independent security and safety acceptance · Owner

External review of 1.1, 1.2, 2.5 and 4.1 before any operational use. No autonomous use-of-force authority at any point.

## How to run this plan

1. Take the lowest-numbered item whose **Needs** are met and whose owner decisions are answered or defaulted.
2. Build on a branch from `main` (after 0.1) with a focused PR; large items go to a worktree agent from the branch head, never from `main` while the integration PR is open.
3. For each item: tests first where possible, a receipt under `docs/evidence/<item>/` naming the tested commit, the register row updated with evidence, a changelog entry, and any defect logged in [BUGS_AND_FIXES.md](../BUGS_AND_FIXES.md).
4. Run the unified CI on the combined branch; for console changes, build, unit and browser acceptance; for runtime changes, the backend suite and the affected browser checks.
5. Never: install `third_party/` code, retry the blocked model comparison, expose the host beyond loopback, add a dependency without a register entry, or mark anything implemented without evidence.

## Decisions the owner holds, collected

| Decision | Unblocks |
|---|---|
| Key custody model and whether to adopt a crypto dependency | 1.1, 2.5 |
| The five wave 2 questions (0.3) | 1.3, 2.6 |
| Model and provider for reasoning; reauthorising the model comparison | 2.1, 2.2 |
| Parser dependency for documents | 2.3 |
| First real account and first harmless write | 2.5 |
| Whether voice may listen | 2.7 |
| Database and coordinator location, mesh, spending ceiling, worker isolation, storage vendor and region, scopes allowed off the machine | 3.1 to 3.3 |
| Specialist product interfaces and external security review | 4.2, 4.3 |
| Repository licence or private visibility | Everything shared outside this repository |
