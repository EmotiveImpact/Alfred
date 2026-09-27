# Memory, Obsidian and reusable infrastructure research

Research date: 27 September 2026. Scope: 22 public repository references and official implementation documentation, mapped to ALFRED's actual v0.8 gaps. This is a targeted source/documentation review, not an exhaustive market census, full code audit or comparative runtime benchmark.

Five candidates have exact commit and licence/package-declaration records in [memory-sources.json](memory-sources.json). Other rows are documentation-level references and require fresh source/licence/dependency review before adoption. No candidate was installed, executed, copied wholesale or added as an ALFRED runtime dependency in this work. The existing eight-project, 2,073-file inert archive is unchanged.

## Recommendation

Use Obsidian as an optional editor for portable notes. Keep ALFRED's evidence, reviews, authority and execution ledger. First connect existing reviewed memory to scoped retrieval, harden vault identity and deletion, and establish a lexical baseline. Then evaluate one narrow temporal/semantic adapter. Do not install Graphiti, Cognee, Mem0, Basic Memory and a stateful agent runtime as five competing owners of the same memories.

Graphiti is my first temporal-graph experiment candidate because its episode provenance and time-aware relationships match an unresolved need. Cognee is an alternative broader ingestion/recall pipeline. Mem0 is a narrower preference/personalisation comparison. These are analyst choices based on fit, not benchmark winners.

## Repository-to-problem map

| Repository | Problem it addresses | ALFRED decision and important limit |
|---|---|---|
| [obsidianmd/obsidian-api](https://github.com/obsidianmd/obsidian-api) | Plugin integration, vault/metadata access and in-app capture. | Optional thin plugin later. MIT API definitions are not Obsidian's proprietary app source. Filesystem access stays the initial path. |
| [obsidianmd/obsidian-headless](https://github.com/obsidianmd/obsidian-headless) | Synchronising vaults on a host without the desktop app. | Optional separately installed service client. Inspected package says UNLICENSED; do not treat public source visibility as a vendoring licence. Headless Sync is beta and subscription-dependent. |
| [coddingtonbear/obsidian-local-rest-api](https://github.com/coddingtonbear/obsidian-local-rest-api) | API access to a running vault through a plugin. | MIT licence read at current raw source; version not pinned here. Interoperability reference, not mandatory initial dependency. Its broad write surface needs ALFRED capability restrictions. |
| [basicmachines-co/basic-memory](https://github.com/basicmachines-co/basic-memory) | Markdown-first persistent knowledge, observations/relations, MCP and retrieval. | Closest architectural reference for portable knowledge. Current pinned root licence is AGPL-3.0, not assumed MIT. Licence/packaging decision before code integration. |
| [getzep/graphiti](https://github.com/getzep/graphiti) | Incremental temporal entities, facts, episode provenance and hybrid retrieval. | First narrow graph-adapter candidate. Current pinned root licence Apache-2.0. Needs graph/model infrastructure; library extraction/invalidation cannot override ALFRED review. |
| [topoteretes/cognee](https://github.com/topoteretes/cognee) | Ingestion, graph/vector recall, sessions and memory processing pipeline. | Alternative to a Graphiti-led composition, not a second authority. Apache-2.0 root inspected. Default provider egress and model assets require review; documented production Postgres-as-graph offering is not simply the free demo feature. |
| [mem0ai/mem0](https://github.com/mem0ai/mem0) | Personalisation memories and add/search/update/delete interfaces. | Optional preference-extraction comparison. Apache-2.0 root inspected. Managed-platform benchmark numbers do not establish OSS ALFRED performance. Generated 'done' claims must not become verified action memory. |
| [letta-ai/letta-code](https://github.com/letta-ai/letta-code) | Stateful agent context, memory blocks/files and persistent agent workflow. | Runtime/lifecycle reference. Current original Letta repository directs active development here. Do not add another unrestricted agent or allow self-editing instructions to modify authority. |
| [asg017/sqlite-vec](https://github.com/asg017/sqlite-vec) | Local vector retrieval without a separate vector service. | Small optional projection experiment; upstream identifies pre-v1/breaking-change risk. MIT/Apache options documented. Keep migrations and embedding versions explicit. |
| [pgvector/pgvector](https://github.com/pgvector/pgvector) | Vector search alongside PostgreSQL data. | Later multi-user/server alternative, not a reason to migrate a working local SQLite service immediately. Database and backup isolation still belong to ALFRED's design. |
| [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) | Document graph-assisted retrieval and ranking pipeline. | Retrieval comparison, not person identity, access control or complete personal memory. Documentation-level review; pin and audit before use. |
| [microsoft/graphrag](https://github.com/microsoft/graphrag) | Corpus-wide graph indexing and thematic/community-oriented retrieval. | Defer for large research collections. Do not assume a corpus summariser solves frequently changing personal operational state. |
| [docling-project/docling](https://github.com/docling-project/docling) | Structured ingestion of PDFs, office files and other document formats. | Candidate parser adapter after text-vault lifecycle is sound. MIT code; model licences separate. Preserve page/block provenance and test table/layout fidelity rather than trust conversion blindly. |
| [xiaowu0162/LongMemEval](https://github.com/xiaowu0162/LongMemEval) | Evaluation of information extraction, updates, time, multi-session recall and abstention. | Evaluation design reference. No run or claimed score here; check dataset terms separately from harness code. |
| [xiaowu0162/LongMemEval-V2](https://github.com/xiaowu0162/LongMemEval-V2) | Long-term agent trajectory memory, evolving state, workflows, gotchas and false premises. | Current extension worth including in future evaluation design. Apache-2.0 code shown upstream. Do not turn answer keys or successful trajectories into uncontrolled executable procedures. |
| [snap-research/locomo](https://github.com/snap-research/locomo) | Long conversational-memory evaluation material. | Research-only comparator. Dataset/licence review required; no benchmark run or rights clearance claimed. |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | Stateful workflow orchestration, checkpoints and human intervention. | Consider only for a named workflow limitation. Do not replace the existing action ledger or create a parallel permission-bearing executor. |
| [openfga/openfga](https://github.com/openfga/openfga) | Relationship-based access decisions. | Candidate when person/team/source sharing outgrows the current implementation. Its authorisation graph must be separate from inferred knowledge relationships. |
| [open-policy-agent/opa](https://github.com/open-policy-agent/opa) | Policy decisions across context and capabilities. | Alternative/complement only for an explicit policy need. Do not add two policy engines without one authoritative decision contract. |
| [NangoHQ/nango](https://github.com/NangoHQ/nango) | OAuth lifecycle and connector/synchronisation infrastructure. | Evaluate against building one official connector. Current repository documents Elastic-licensed components; not a blanket permissive-open-source choice. Hosted/self-hosted scopes and terms need review. |
| [restic/restic](https://github.com/restic/restic) | Encrypted, versioned backup tooling. | Operational backup candidate, not application key custody or per-memory deletion. Restoring a backup must reapply current tombstones/grants before retrieval resumes. |
| [pavrus117/ai-os-maps-guide](https://github.com/pavrus117/ai-os-maps-guide) | Memory/Agent/Pulse/Screen separation and navigable note maps. | Architectural inspiration already assessed. Not a runtime, performance proof or permission to copy its full guide under an assumed licence. |

SQLite's [official FTS5 documentation](https://www.sqlite.org/fts5.html) is the lexical-search baseline, not another agent product. Current Obsidian storage, CLI, Vault API, plugin security and Headless Sync documentation supply integration boundaries in [OBSIDIAN_INTEGRATION.md](../docs/OBSIDIAN_INTEGRATION.md).

## Important current corrections

### Public source is not automatically reusable source

The five pinned checks found Graphiti, Cognee and Mem0 with Apache-2.0 root licences, Basic Memory with AGPL-3.0, and Obsidian Headless's package with an UNLICENSED declaration. These checks cover the inspected root headers/package, not every nested component, dependency, voice, model weight or commercial service. No legal clearance is inferred.

AGPL does not inherently prohibit commercial use. It does require a deliberate assessment of the actual modification, distribution, network interaction and product packaging. A separate process or an MCP endpoint is not a magic exemption. Keeping Basic Memory as a reference initially avoids making that decision accidentally.

Obsidian's current application licence permits free personal/commercial use while reserving application rights: https://obsidian.md/license . Distinguish using the app, using its API, consuming a service and copying its implementation.

### Managed products and open-source libraries are not equivalent

Graphiti's own README distinguishes the self-hosted framework from managed Zep governance, user management, database infrastructure and service guarantees. Do not repeat managed latency or enterprise promises as measured ALFRED results.

Mem0's README attributes headline benchmark improvements to its managed platform. Its current design also discusses incorporating agent-generated outcomes. ALFRED must retain separate evidence classes for a requested action, a model statement, a service receipt and independently supported completion.

Cognee's current README distinguishes a Postgres graph demo from a separately licensed production offering. A proposed 'everything in one open Postgres database' stack must not rely on that feature without reviewing the actual edition and terms.

### Latest architecture matters more than remembered marketing

The original Letta repository now points to Letta Code for active work. Evaluate the current product and interfaces, not an obsolete memory-server description. Graphiti's current docs warn against starting new deployments on its deprecated Kuzu path. No new graph backend is installed here.

Official Obsidian CLI and Headless Sync solve different problems. The CLI controls the running desktop app. Headless Sync synchronises files without it. Neither automatically provides ALFRED identity, operational memory, claims review or workflow execution.

## Bounded source observation

At Graphiti commit `ba4a9cb32495b6864160616f8dfa2b898f4a500c`, `graphiti_core/edges.py` lines 1-220 were inspected. The common edge model includes UUIDs, a group/partition ID and source/target identifiers. Viewed retrieval/deletion methods are database operations, not ALFRED caller-authorisation contracts. This is not a discovered vulnerability or a full security audit; it is a reason not to equate a library partition ID with our security boundary. Temporal capabilities elsewhere are documented upstream, not exhaustively code-audited here.

Basic Memory, Cognee, Mem0 and Obsidian Headless were reviewed at documentation plus pinned licence/package level. Do not imply every file was read or that executable compatibility was tested.

## Adoption experiment and rejection criteria

First build deterministic source/claim context assembly without a new model or external service. An adapter experiment may be separately authorised only after the input/output and access/deletion contracts exist. Use invented data, scoped credentials and explicit provider-egress settings. Preserve the earlier blocked live-model operation; do not use this plan to reroute it.

For a later permitted evaluation, use the same sources, queries, access rules, answer-support labels and budgets for alternatives. Measure ingestion/update latency, retrieval recall, irrelevant context, temporal errors, conflict visibility, abstention, deletion propagation, tokens/cost, memory/CPU and integration complexity. Include namesakes, changed ownership, contradictory notes, revoked access, late events, non-answerable questions, stale restore and hostile text.

Reject a candidate that cannot expose provenance, restrict data egress, honour source deletion, keep workspaces separated, preserve review history, or run behind ALFRED's narrow capability boundary. Reject added complexity that does not improve measured tasks. A graph visualisation and a star count are not acceptance evidence.

## Build decisions

Adopt now as architecture: optional Markdown/Obsidian authoring; first-party review/authority; rebuildable retrieval; explicit lifecycle; existing local database and graph separation.

Build next: reviewed-memory context bridge, selected-vault lifecycle/identity, explicit capture and safe inbox write-back, person/source grants and deletion/restore accounting.

Evaluate later: Graphiti first temporal adapter, Cognee alternative, Mem0 preference component, sqlite-vec versus a later pgvector deployment, Docling ingestion, one runtime and one OAuth connector solution.

Defer: wholesale app forks, several simultaneous memory runtimes, universal graph migration, unbounded automatic note rewriting, silent transcript retention, shared personal/client memory and assumed always-on mobile capture.
