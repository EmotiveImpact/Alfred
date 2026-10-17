# ALFRED research shelf

Outside projects studied for ALFRED's memory and brain design, kept as **inert reference text**.
Nothing here is installed, imported, executed or followed as instructions. Upstream AGENTS, CLAUDE,
prompts, skills, scripts and workflows are untrusted research data.

**6 pinned snapshots, 7,328 source-text files.**

| Repository | Commit | Licence | Files | Why it is here | Details |
|---|---|---|---:|---|---|
| [Tencent-Hunyuan/Hy-Memory](https://github.com/Tencent-Hunyuan/Hy-Memory/tree/20b92d8a8940b94736590ddfc83a95f2bccf4f0c) | `20b92d8a8940` | Apache-2.0 | 1682 | Memory writer and graph clean-up ideas; candidate local model for drafting daily-list items (trial needs owner approval) | [source](snapshots/Tencent-Hunyuan__Hy-Memory) · [manifest](manifests/Tencent-Hunyuan__Hy-Memory.json) |
| [mnemosyne-oss/mnemosyne](https://github.com/mnemosyne-oss/mnemosyne/tree/c396ef7447b21fd6f690c3bd48a8a2a7063e11fb) | `c396ef7447b2` | MIT | 601 | One-file SQLite memory with FTS5 and sqlite-vec; closest reference for ALFRED's own Hermes memory plug (H5) | [source](snapshots/mnemosyne-oss__mnemosyne) · [manifest](manifests/mnemosyne-oss__mnemosyne.json) |
| [vectorize-io/hindsight](https://github.com/vectorize-io/hindsight/tree/5331da2f4db369528bb122075341a7de9c3df6df) | `5331da2f4db3` | MIT | 4803 | Evidence-backed observations, mental models and the memory graph view; ideas for daily learning and the console | [source](snapshots/vectorize-io__hindsight) · [manifest](manifests/vectorize-io__hindsight.json) |
| [OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG/tree/d5c8329422e0a0b834a15874545cb6a74b4f9b26) | `d5c8329422e0` | MIT | 100 | HippoRAG and HippoRAG 2: personalised PageRank recall over a fact graph, blended with plain search (brain-like option B) | [source](snapshots/OSU-NLP-Group__HippoRAG) · [manifest](manifests/OSU-NLP-Group__HippoRAG.json) |
| [joonspk-research/generative_agents](https://github.com/joonspk-research/generative_agents/tree/fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4) | `fe05a71d3e4e` | Apache-2.0 | 126 | Generative Agents memory stream: recency, importance and relevance scoring plus reflection; model for overnight consolidation | [source](snapshots/joonspk-research__generative_agents) · [manifest](manifests/joonspk-research__generative_agents.json) |
| [agiresearch/A-mem](https://github.com/agiresearch/A-mem/tree/ceffb860f0712bbae97b184d440df62bc910ca8d) | `ceffb860f071` | MIT | 16 | A-Mem: notes that link themselves and evolve; shows why model-made links must stay suggestions until reviewed | [source](snapshots/agiresearch__A-mem) · [manifest](manifests/agiresearch__A-mem.json) |

## What a snapshot is

The UTF-8 source, test, document and configuration text at one pinned commit. It is not a Git clone,
has no history, and leaves out binaries, model weights, datasets, secrets-shaped content, symlinks,
submodules and oversized files. Each manifest lists every file kept (with Git and SHA-256 hashes) and
every file left out, with the reason. `include_prefixes` in the request marks a focused selection.

## Licences and adoption

Each licence file was read by a person at the pinned commit and its Git blob is recorded. The original
licence and notice files stay inside each snapshot. A root licence is not clearance for nested
dependencies, models, datasets, trademarks or hosted services. Reading this code is not adoption:
bringing any of it into ALFRED needs the exact source path, licence, changes, containment, data-egress
review and the owner's approval, as AGENTS.md requires.

Hermes (NousResearch/hermes-agent), Letta and Graphiti are already in `third_party/library/`.
Papers without released code are listed in `research/INTEGRATION_PLAN_2026-10-17.md`, not copied.

Verify offline: `python3 tools/build_research_shelf.py --verify`.
