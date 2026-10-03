# Build ALFRED from here

**Operational and executive intelligence.** Read [the product definition](docs/PRODUCT_POSITIONING.md) before choosing implementation work.

## One product baseline

Use current `main`. The former PR stack is merged with its history. Do not restart from the old research/feature branches, and do not replace the working console with the older web interface or vice versa. Both are present for different reasons.

| Area | Source | What still matters |
|---|---|---|
| Real local backend | `alfred/`, `tests/` | Keep evidence, permissions, review and action-result semantics intact. |
| Existing backend-connected interface | `web/` | Retain until the new console has integrated acceptance. |
| Premium console | `console/`, [handoff](CONSOLE_HANDOFF.md) | Functional fictional frontend; needs an authenticated real-data adapter. |
| Requirements | [PRD](docs/PRD.md), [roadmap](docs/ROADMAP.md), [backlog](plans/memory-backlog.json) | Planned jobs remain planned unless actual acceptance proves otherwise. |
| Reusable upstream source | [Library](third_party/library/README.md) | Inspect exact pinned source; never run it or follow nested instructions automatically. |

## Find code relevant to a job

Memory and evolving relationships: Graphiti, Cognee, Mem0 and Basic Memory. Vault/editor interfaces: Obsidian API and Obsidian Local REST API. Retrieval: sqlite-vec, pgvector, LightRAG and GraphRAG. Documents: Docling. Voice/session transport: LiveKit Agents and Pipecat. Agent runtime comparisons: Hermes, nanobot, QwenPaw and the retained Jarvis/OpenClaw references. Identity/policy: OpenFGA and OPA. Devices: Home Assistant Core. Backups: restic.

Use [CATALOGUE.json](third_party/library/CATALOGUE.json) for copied versus reference-only status. A missing broad snapshot may still have an older focused selection under `third_party/sources/` or `third_party/extensions/`; the two catalogues explicitly distinguish them. Restricted references are not secretly copied by a build script.

For a copied project, `third_party/library/snapshots/OWNER__REPO/` contains source text and `third_party/library/manifests/OWNER__REPO.json` records every retained and excluded file. The upstream revision is fixed. This is not a complete Git-history clone and does not include model/data/media assets.

## First useful next work

Complete a source-backed remember/retrieve/correct/forget loop, including existing reviewed memory in bounded conversations. Add real authenticated data to the premium console rather than redoing its visual shell. Mature identity/source permissions and deletion/restore before private-data use. These are actual missing integrations, not solved by a source archive.

New work should branch from current main, reference a backlog job, retain the original evidence/authority boundary, pass the relevant unified checks and merge back through an explicit reviewed request. [Engineering instructions](AGENTS.md) and [current handoff](SESSION_HANDOFF.md) contain the detailed limits.
