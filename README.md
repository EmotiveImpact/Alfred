# ALFRED

Personal and authorised operational intelligence, under the user's control.

## Current checkpoint

27 September 2026: this branch contains the current memory/Obsidian PRD and build plan,
the preserved v0.8 application plus concurrent console toolchain, and a verified in-repo
source shelf for build-critical upstream references. It is **not** a deployed runtime,
completed Obsidian integration or claim that those upstream projects are installed.

Planning/source branch: `research/alfred-memory-system-2026-09-27`.
Base product/console checkpoint: `73a255a10cb43f55a14aaf45165800bd17e60553`,
which sits over v0.8 `22e64567f69508928b164d55c578834abcb404e8`.
Main remains separate; no automatic merge or deployment.

## Start here

- [Current PRD](docs/PRD.md): product, current status and 27 traceable requirements.
- [Current roadmap](docs/ROADMAP.md) and [12-job dependency-linked backlog](plans/memory-backlog.json).
- [Memory architecture](docs/MEMORY_ARCHITECTURE.md) and [Obsidian integration specification](docs/OBSIDIAN_INTEGRATION.md).
- [22-repository memory/infrastructure review](research/MEMORY_LANDSCAPE_2026-09-27.md) and [source/licence register](research/memory-sources.json).
- [Build-reference source shelf](third_party/BUILD_REFERENCE_SHELF.md): exactly what upstream source is available inside this repo for builders.
- [Architecture decision](docs/adr/MEMORY-001.md), [memory security](docs/MEMORY_SECURITY.md) and [work packages](docs/BUILD_PLAN.md).
- [Engineering instructions](AGENTS.md) and [continuation record](SESSION_HANDOFF.md).

## What is available in GitHub

The ALFRED application source, tests, UI work, PRD/plans, research, handoffs and prior
delivery evidence are all in this repository on the relevant branches. The source shelf
now retains **2,309 exact source files across 15 pinned upstream snapshots**: 1,946 files
in the original research archive plus 363 files in the extension shelf.

The extension shelf includes exact focused selections of Obsidian API, Graphiti, Cognee,
Mem0, Basic Memory, sqlite-vec and Docling, plus the earlier Jev SDK, QwenPaw and
OpenSandbox references. They are inspectable in `third_party/extensions/` with licences,
pins and per-file hashes. They are **research data, not runtime dependencies**.

Obsidian Headless is deliberately *not* copied because the inspected package declares
UNLICENSED. Other lower-priority repositories remain dated links in the research landscape
until an implementation need justifies preserving them.

GitHub Actions run 36286506421 imported seven new memory/Obsidian selections with zero
failures and verified 363 extension files plus the unchanged 1,946-file original archive.

## What exists in ALFRED

The local application has SQLite persistence, credential-scoped browser sessions,
read-only project/Markdown scanning, a source-reference graph, source-backed questions,
bounded saved conversations, manual reviewed-memory statements, fixed local Pulse reports
and exact approvals for local drafts. Drafts are stored inside ALFRED, not sent externally.

Reviewed statements are not yet automatically conversation context. No complete upstream
agent/memory framework is integrated. The optional tool-free local Ollama adapter is off
by default; the recorded small-model trial exposed failures and is not a production-brain
selection. Read the [v0.8 delivery receipt](docs/evidence/memory-v08/DELIVERY.md).

`console/` is concurrent UI work, preserved here. Its internal Obsidian name is not the
Obsidian note application. Existing `web/` remains available.

## Run the local development application

Use synthetic data on a supported POSIX development machine. No model or external account
is required for source mode.

```sh
python3 -m alfred.desk init --data-dir ~/.local/share/alfred/memory-demo
python3 -m alfred.desk access --data-dir ~/.local/share/alfred/memory-demo
python3 -m alfred.desk serve --data-dir ~/.local/share/alfred/memory-demo
```

The access command prints a development key in the private terminal. Do not share it or
expose the loopback server. The local host must stay running for scans, routines and
queued work. No background system service is installed by this repository update.

## Validate

```sh
python3 tools/check_memory_plan.py --self-test
python3 tools/check_memory_plan.py
python3 -m unittest discover -s tests -v
python3 tools/import_sources.py --verify
python3 tools/extend_sources.py --verify
```

The plan checker validates requirements/backlog/research/source-shelf consistency and
local document links. Archive verification confirms retained bytes; it does not make
upstream code trusted or commercially cleared.

## Boundaries

Obsidian is an optional editor over user-owned Markdown. ALFRED retains review, access,
correction/deletion and action authority. Notes, MCP tools, imported code and inferred
graph edges never grant permissions. Personal, business and client scopes remain separate.

No private vault, microphone, external account/device, ENDSTATE or Noir is connected by
this work. Application encryption, mature pairing, fine-grained grants and complete
deletion/restore lifecycle remain unfinished. No operational-safety readiness or
autonomous use-of-force capability.

This repository is public. Keep credentials, recordings, private client/personal
information and live operational data out of it. Preserve all third-party rights.
Historical briefs/plans remain under docs/archive/ and Git history.
