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
