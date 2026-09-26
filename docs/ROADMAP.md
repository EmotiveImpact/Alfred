# ALFRED current roadmap: reviewed memory v0.8

26 September 2026. Source branch: `feat/alfred-reviewed-memory-2026-09-26`.
Base v0.7: `e0a0ef973d20d3f60606423ab2035d9f9df9e68f`. No merge or deployment.
The existing OS shell remains provisional, not a newly approved visual identity.

## Completed jobs in this increment

1. Reviewed memory: typed, credential-private entities and proposals with exact source
   provenance; separate acceptance/dispute/withdraw/supersession; bounded validity/conflicts;
   source invalidation; working Memory UI and export. Not automatic semantic extraction.
2. Evidence checks: literal unsupported-number and missing-amount rejection in both
   synchronous questions and queued conversations; precise failure labels and retained sources.
   Not entailment, broad relevance assurance or a successful stronger-model evaluation.
3. Routine lifecycle: preview/confirm older Pulse report pruning while keeping recent/running
   records and compact retry receipts, without resetting rate limits or changing schedules.

## Next unfinished acceptance gates

- Independently measured reasoning: the attempted new model comparison did not run because
  its tool operation was blocked. Do not claim it passed or reroute that blocked operation.
  Preserve v0.7 failure evidence. Broader semantic support, missing-answer and conflict
  handling still need independent evaluation; the new heuristics do not solve them.
- Integrate reviewed memory into controlled contextual retrieval with clear provenance,
  revocation and no promotion of human-reviewed statements to objective facts. Currently
  the reviewed graph is inspectable/exportable, not automatically sent to the model.
- Mature person/device identity, key rotation, finer grants, entity deletion/migration and
  encrypted-data/backup/retention decisions before any sensitive real-data pilot.
- One explicitly authorised official account connector; then one harmless test-account
  action with exact approval and capability-specific result reconciliation.
- Measured visible push-to-talk, then deliberate service installation/cross-device operation.
  No implied ambient capture, remote daemon or live ENDSTATE/Noir integration.

Acceptance remains end-to-end behaviour, negative tests and actual evidence, not a test
count alone. The rest of this file is retained historical roadmap context.

---

# ALFRED current roadmap: v0.7 conversation increment

The visual direction remains provisional. Do not restart the interface or represent it
as a final approved design. Build on the source of truth branch:
`feat/alfred-conversation-2026-09-26`.

## Newly implemented

Private local conversation sessions, explicit context continuation/reset, fresh evidence
retrieval, bounded queued model processing, turn recovery/expiry/forget, and note-bound
local draft proposals through the existing exact-approval/outbox/result mechanism.
A real small-model trial has been run, with its missing-answer failure retained.
See CONVERSATIONS.md and ../research/MODEL_TRIAL_V07.md for scope and evidence.

## Next acceptance gates

1. Reasoning quality: compare stronger models on held-out source questions, contradictions,
   missing facts and multi-turn context. Current reference validation is not entailment.
2. Memory: reviewed typed entity/claim proposals with evidence lineage, conflict and
   supersession, keeping authored note links separate. No names-only identity merging.
3. Authority/lifecycle: device pairing/key rotation, finer source and capability grants,
   encryption decisions, retention/export and derived-data deletion accounting.
4. One real official read-only account connector, then one harmless test-account write
   with approval and capability-specific result reconciliation. No broad credential grants.
5. Voice: visible push-to-talk with measured turn/playback/reconnect behaviour. Preserve
   separate generated, played and acknowledged states. No hidden ambient recording.
6. Reviewed service installation/cross-device and specialist ENDSTATE/Noir adapters only
   against their actual source and interfaces. No operational-safety readiness claim.

The following v0.6 roadmap remains a historical baseline, not a reason to rebuild already
completed conversation or routine work. Current status above takes precedence.

---

# ALFRED roadmap: Personal OS v0.6

26 September 2026. Current working branch: feat/alfred-personal-os-2026-09-26.
Base: af10f961665962a42d2d78f00864edb9c267db26. No automatic main merge or deployment.

## Delivered in this increment

Personal OS shell: full viewport, Home, persistent dock, Ctrl/Cmd+K, focus and task spaces.
The previous source-first Ask, Memory graph, Work approvals and local draft verification
are retained. Raw implementation details are exposed on inspection, not as the main UI.

Pulse: two fixed, bounded local report routines with opt-in intervals, durable run records,
idempotent due slots, rate/history caps, pause, expiry/revocation and visible failures.
No model, arbitrary tool, external effect or installed background service is introduced.

## Next build sequence

1. **Real source-grounded reasoning.** Run one configured model on answerable, insufficient,
   conflicting and malicious-source questions. Measure citation support and failures.
   The current optional adapter is protocol-tested, not inference-validated.
2. **Reviewed typed memory.** Add entity and claim proposals, source lineage, user review,
   conflict/supersession and stable identities. The existing note graph remains separate.
3. **Private-work readiness.** Finish source/capability grants, pairing/key rotation,
   encryption decisions, correction/deletion and backup/retention accounting. Add an explicit
   bounded Pulse history retention/clear path before its 512-record stop makes unattended
   use impractical. Source freshness and transient failures must remain honest.
4. **One real account workflow.** A test-account read connector, followed by a narrow approved
   write and capability-specific receipt/result reconciliation. Preserve the current ledger.
5. **Voice and actual host lifecycle.** Visible push-to-talk, measured interruptions and
   playback, then a deliberately installed local/private-host service. No blanket always-on
   mobile or cloud claim. Intervals already exist; calendar/timezone scheduling does not.
6. **Devices, team contexts and specialist engines.** Read the actual authorised interfaces
   before connecting Home Assistant, ENDSTATE or Noir. Keep independent data/authority
   boundaries and start operational evaluation with synthetic/non-critical exercises.

## Acceptance bar

The interface must work as a personal intelligence environment, not merely acquire more
menus. Test the whole user loop: question, relevant sources, interpretation where available,
exact approval, result, interruption/restart, correction and revocation. Record failed
cases and avoid declaring completion from a test count or an attractive screenshot.

The owner’s name preference remains ALFRED; Emotive Impact versus Black State branding is
not resolved by this engineering increment. Earlier research and source archive decisions
remain available in research/ and the prior product/architecture docs.

---

## Previous detailed roadmap (historical v0.5 context)

# ALFRED execution roadmap: Grounded Desk v0.5

Updated 26 September 2026. This supersedes the v0.4 status summary, not the product
vision or earlier research. Stages describe acceptance gates, not guaranteed dates.
The previous programme remains in docs/BUILD_PLAN.md and repository history.

## Current checkpoint

The local application has a persistent event/action/draft service, scoped local access,
a real browser interface, automatic scans while its launched supervisor is alive,
read-only project and Markdown connectors, an explicit note-reference graph and
source-first questions with line/revision/hash inspection. A local-model adapter exists
but no actual model inference has been validated. All demonstrations use fictional data.

The existing 2,073 retained upstream source files across eight projects are unchanged
research material. They are not eight integrated runtimes. The MAPS guide was assessed
and attributed; it was not copied wholesale under an assumed reuse licence.

## The first complete experience

A user can bring a question about authorised work, inspect the relevant source passages,
understand what changed, approve an exact action and see what happened. The next missing
part is evaluated reasoning over those sources and a deliberately limited external
connector, not another unbounded collection of agents.

## Stage 1: local reasoning pilot

Use the existing optional local adapter with an explicitly configured, licensed local
model. Keep personal/client data out of the evaluation. Assemble a synthetic question
set including missing answers, conflicting notes, changed sources, adversarial source
instructions, long passages and ambiguous entities. Compare keyword-only and graph-
expanded retrieval. Report source recall, unnecessary context, citation error, abstention,
latency and resource use. Keep failures visible; a valid JSON schema is not correctness.

Acceptance: a repeatable end-to-end source-to-labelled-interpretation demonstration on
named hardware, with model/configuration/version and a published result table. No action
authority belongs to the model. Providers remain replaceable.

## Stage 2: typed memory rather than merely linked files

Add an evidence-backed claim projection alongside the existing note-reference graph.
A note link remains links_to, not assigned_to or owns. Proposed claims must carry stable
entity IDs, source/hash/line range, temporal validity, basis, reviewer and status. Start
with explicit authored metadata and manual acceptance. Model extraction produces a
proposal queue only. Do not merge names or suppress conflicting evidence automatically.

Acceptance: review, dispute, supersede and withdraw flows; changes/deletion invalidate
current derived claims; different workspaces cannot see each other's claims or snippets.
Keep Markdown portable and the index rebuildable. See MEMORY_ARCHITECTURE.md.

## Stage 3: identity and memory lifecycle hardening

Implement mature paired-device sessions, scoped key rotation, fine-grained capability
grants, expiry and revocation, secure secret handling and documented backup/retention
behaviour. Propagate deletion/revocation through indexes, derived summaries and caches.
Support bounded history and explicit export without turning audit logs into a permanent
copy of every private document.

Acceptance: negative access tests, rotation/recovery exercises, source removal and
retention tests, independent security review for any intended private-data pilot. A
local SQLite file and role checks are not a production tenancy/encryption solution.

## Stage 4: bounded continuous work

The current supervisor scans folders and processes already approved local drafts while
running. Next introduce a durable routine registry: purpose, workspace, host, schedule,
allowed inputs/capabilities, timeout, budget, lease, next due time, last run and outcome.
Run deterministic checks first; invoke reasoning only for an explicit approved task.

Acceptance: restart and duplicate-run recovery, pause/revoke, backoff, quota ceilings,
missed-run visibility and stop behaviour. The application must say when its host or
sources are offline. No implication that chat itself is continuously operating the app.

## Stage 5: one contained runtime and one real connector

Compare Hermes, nanobot and QwenPaw against identical tasks and limits, choosing one
rather than merging overlapping executors. Evaluate OpenSandbox separately for the
actual containment guarantees required. Jev remains an advisory experiment until its
classification quality is measured. Never use model confidence as a grant or truth score.

Add one official read-only account connector with test-account consent, then one low-risk
reversible effect. Preserve exact proposal/approval/outbox/result semantics. A timeout
must not cause blind repetition, and delivery receipt must not become confirmed success.

Acceptance: isolated runtime cannot obtain connector secrets, revoked permission blocks
work, external state can be reconciled, failures remain visible and useful. No blanket
browser/shell, banking, alarm-disabling or security-system authority.

## Stage 6: voice, devices and specialist engines

Start visible push-to-talk sharing the same context and permissions. Measure noise,
interruption, playback versus acknowledgement, reconnect and power use on named devices.
Then add low-risk local device integrations and an explicit disconnected capability set.
Read actual ENDSTATE and Noir contracts before implementing adapters; keep simulation,
analysis and operational observations distinct. Team information remains role-scoped.

Acceptance: actual device/voice experiments and supervised non-critical exercises before
safety reliance. No autonomous use-of-force control. Do not infer background iOS/Android
capabilities or battery life from a browser prototype.

## Execution discipline

The next development session starts from the verified current Grounded Desk branch and
its source receipt. Continue existing modules, not a replacement scaffold. Keep code,
tests, evidence, decisions and handoff in the repo. Use separate branches where parallel
work would conflict, then reconcile contracts explicitly. Never report a local tree as
pushed, a workflow file as passing or an optional adapter as validated inference.

The immediate priorities are Stage 1 and the small typed-claim contract in Stage 2,
while identifying the remaining identity/lifecycle gates for real data. More repository
imports are justified only when they resolve a named implementation need.
