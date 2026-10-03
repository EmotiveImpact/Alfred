# ALFRED architecture and current system boundaries

<!-- ALFRED unified operational/executive baseline: 2026-09-27 -->

**Current product category: operational and executive intelligence.** See [positioning](PRODUCT_POSITIONING.md). The owner-authorised development PR stack is now merged into `main`; start new work there. The real local backend and the newer React/Three.js console are both preserved, but the console still uses fictional fixtures and needs its authenticated backend adapter. Consolidation is not deployment, external integration or completion of the planned memory jobs. The broad source-library catalogue, not earlier archive counts, is the current inventory.

Updated 27 September 2026. Current requirements: [PRD.md](PRD.md). Memory specification: [MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md). The original architecture is preserved in [archive/ARCHITECTURE-v01.md](archive/ARCHITECTURE-v01.md).

## One personal intelligence, not one omnipotent model

The model proposes. ALFRED assembles authorised context. Independently enforced policy authorises. Connectors execute. A durable ledger records intent, receipt and supported outcome. Replaceable voice, reasoning, extraction and retrieval components fit inside this boundary; they do not independently acquire every account credential.

```text
Person / paired devices / optional Obsidian editor
                    |
             ALFRED console + sessions
                    |
          context and attention coordinator
            /                       \
  governed memory gateway      reasoning/runtime adapter
            |                       |
   sources, claims, indexes     typed action proposal
                                    |
                          authority and exact approval
                                    |
                        durable outbox + connector host
                                    |
                         receipt / result / audit ledger
```

## Implemented baseline

The first-party Python service persists local data in SQLite and exposes an authenticated loopback browser interface. `KnowledgeStore` builds on the local service; conversation workers and fixed Pulse routines share the existing local host lifecycle. Markdown/project sources are read-only. The only action effect is an approved draft in ALFRED's own database, not an external message.

Manual reviewed statements are stored separately from the authored note graph and have provenance/review/conflict/invalidity rules. They are not yet automatically included in model context. Model mode is optional and tool-free; current evidence rejection rules are limited heuristics. No general agent framework from the source archive has been fully integrated.

The M01/M03 draft review branch extends that baseline with a bounded, actor-private reviewed-memory bridge. Only accepted/current/relevant/non-conflicting statements enter context; their exact original support shares the existing source budget. Namesakes retain distinct IDs and block model use pending clarification. Review/source/temporal/conflict bindings are rechecked at model egress, return, conversation persistence/display and separate draft approval/dispatch. Saved conversations reconstruct current values from review bindings rather than copying them. This is not a main merge, fine-grained grants, deletion/restore accounting or a graph-engine adoption. See [M03 evidence](evidence/memory-m03/RECEIPT.md).

The functional React/Three.js `console/` implementation is preserved alongside `web/`. The console runs fictional fixture interactions; do not infer a live backend, note-app integration or deployment from the merge. This planning revision changes no application or UI source.

## Memory integration decision

Markdown is a human knowledge surface, not an action database. Retain original source references for imported account/document data. Keep working episodes, accepted semantic statements, preferences, commitments and procedures distinct. Use the existing review and authority store as the source of truth for status; graph/vector engines provide rebuildable projections and proposed extraction.

The proposed memory gateway is the only context route for conversation, attention and later ENDSTATE requests. It filters permissions before ranking and graph traversal, preserves source and review basis, enforces a context budget and rechecks grants/revisions before output. Interfaces and lifecycle are detailed in [MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md).

## Storage and deployment

Start with the existing modular local service, SQLite and a measured FTS5 lexical projection. Add vectors or a graph engine only after the contract and evaluation gate. Do not deploy a fleet of microservices to prove the first personal workflow. PostgreSQL/pgvector is a later concurrency/deployment option, not a mandatory replacement now.

Personal, company and operational/client scopes require explicit identity, grants, key custody, retention and egress policy. Credential IDs are not a mature paired-person/device system. Database labels or graph group IDs do not enforce all isolation requirements. Separate hostile workloads at a real process/filesystem/network boundary.

The application is not yet encrypted at application level and is not approved for sensitive operational data. Vault sync is independent of the live SQLite ledger. Backups must have separate retention and restore procedures that reapply current revocations/deletion tombstones.

## Candidate components, not installed dependencies

Obsidian filesystem vault: primary authoring/reading interoperability. Optional official plugin/CLI/headless clients have separate permissions and lifecycle.

Graphiti: first narrow temporal projection/extraction candidate. Cognee: alternative ingestion/recall pipeline. Mem0: preference extraction comparison. None can silently decide truth, invalidate accepted ALFRED history or alter authority. Basic Memory is a reference/interoperability candidate pending current AGPL terms.

Hermes, nanobot and QwenPaw remain runtime candidates from the earlier programme. LiveKit/Pipecat remain voice transport candidates. Jev remains an advisory classification component, not a truth or authorisation service. OpenSandbox remains an execution-containment candidate. New memory research does not install or promote any of these.

OpenFGA/OPA may inform finer authorisation. Nango may inform OAuth/connectors subject to edition/licence review. Prefer one official read-only connector first rather than adopting a universal integration platform without a tested need. References and limitations: [research landscape](../research/MEMORY_LANDSCAPE_2026-09-27.md).

## Actions and long-running work

Preserve exact proposal parameters, actor/workspace, expiry, source preconditions and approval fingerprints. Recheck before dispatch. An ambiguous timeout or interruption is not an invitation to repeat an irreversible effect. Receipt, supported result and human acknowledgement are separate records.

'Create note' will be a new capability, not a bypass through the memory API. File/database coordination needs a journal and explicit reconciliation; it is not one atomic transaction. Begin with user-reviewed new inbox notes.

Pulse currently has fixed local reports and explicit interval opt-in. Models, arbitrary scripts and external account writes are not routine payloads. A later attention engine may nominate useful work but cannot silently expand its own capabilities. The host must be running; this task installs no daemon or remote worker.

## Voice, devices, team and specialist engines

Voice must share session and permissions with text. Capture, recording retention and cloud upload are separate permissions. Generated, played and acknowledged audio require distinct states; stopping speech does not undo a dispatched action. Start visible push-to-talk and named-device tests before always-available modes.

Future Home Assistant, account and device adapters expose narrow capabilities with source freshness. ENDSTATE receives scoped evidence and returns analysis with assumptions, never a fabricated observation. Noir integration must follow its actual authenticated API and acknowledgement semantics. No such integration is claimed here. Operational scenarios remain simulated/non-critical first, with no autonomous use-of-force authority.

## Observability and changes

Record evidence age, route reasons, queues, retries, revisions, token budgets and actual outcomes without retaining secrets or default raw private transcripts. Provide inspect, pause, revoke, export and forget controls. Measure latency, recall, abstention and failures on named configurations.

Preserve the previous blocked live-model-comparison restriction. Documentation and deterministic contract tests are separate from model experiments. Upstream source quarantine remains inert; no nested prompt, script or AGENTS file can change this task's authority. Each dependency adoption needs its own code/model/service/licence/egress review.
