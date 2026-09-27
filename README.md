# ALFRED

Personal and authorised operational intelligence, under the user's control.

## Current checkpoint

27 September 2026: this branch updates the memory/Obsidian research, current PRD and build plans. It preserves the local v0.8 application and the separate console toolchain. This is **not** a new deployed runtime or a completed Obsidian integration.

Planning branch: `research/alfred-memory-system-2026-09-27`.
Base: `73a255a10cb43f55a14aaf45165800bd17e60553`, the isolated console toolchain over v0.8 `22e64567f69508928b164d55c578834abcb404e8`.
Main remains separate; no automatic merge or deployment. Refresh actual remote refs before continuing parallel work.

## Start here

- [Current PRD](docs/PRD.md): product, current status and 27 traceable requirements.
- [Current roadmap](docs/ROADMAP.md) and [12-job dependency-linked backlog](plans/memory-backlog.json).
- [Memory architecture](docs/MEMORY_ARCHITECTURE.md) and [Obsidian integration specification](docs/OBSIDIAN_INTEGRATION.md).
- [22-repository memory/infrastructure review](research/MEMORY_LANDSCAPE_2026-09-27.md) and [five pinned source/licence records](research/memory-sources.json).
- [Architecture decision](docs/adr/MEMORY-001.md), [memory security](docs/MEMORY_SECURITY.md) and [work packages](docs/BUILD_PLAN.md).
- [Engineering instructions](AGENTS.md) and [continuation record](SESSION_HANDOFF.md).

## What exists

The local application has SQLite persistence, credential-scoped browser sessions, read-only project/Markdown scanning, a source-reference graph, source-backed questions, bounded saved conversations, manual reviewed-memory statements, fixed local Pulse reports and exact approvals for local drafts. These drafts are stored inside ALFRED, not sent as messages.

Reviewed statements are not yet automatically conversation context. No complete agent framework from the research archive is integrated. The optional tool-free local Ollama adapter is off by default; the recorded small-model trial exposed failures and is not a production-brain selection. Read the [v0.8 delivery receipt](docs/evidence/memory-v08/DELIVERY.md) for actual prior validation.

`console/` is concurrent UI work, preserved here. Its internal Obsidian name is not the Obsidian note application. Do not confuse a toolchain with a finished interface. Existing `web/` remains available; visual fidelity to the premium target must be judged from actual implementation.

## Run the local development application

Use synthetic data on a supported POSIX development machine. No model or external account is required for source mode.

```sh
python3 -m alfred.desk init --data-dir ~/.local/share/alfred/memory-demo
python3 -m alfred.desk access --data-dir ~/.local/share/alfred/memory-demo
python3 -m alfred.desk serve --data-dir ~/.local/share/alfred/memory-demo
```

The access command prints your development key in the private terminal. Do not share it or expose the loopback server. The local host must stay running for scans, routines and queued work. No background system service is installed by this repository update.

## Validate

```sh
python3 tools/check_memory_plan.py --self-test
python3 tools/check_memory_plan.py
python3 -m unittest discover -s tests -v
python3 tools/import_sources.py --verify
python3 tools/extend_sources.py --verify
```

The new checker validates requirements/backlog/source-register and local document-link consistency. It does not validate model quality, integration performance, legal clearance or completion of planned capabilities. Only claim CI results after reading an actual completed run.

## Boundaries

Obsidian is recommended as an optional editor over user-owned Markdown. ALFRED retains review, access, correction/deletion and action authority. Source notes, MCP tools and inferred graph edges never grant permissions. Personal, business and client scopes remain separate.

No private vault, microphone, external account/device, ENDSTATE or Noir is connected by this work. Application encryption, mature pairing, fine-grained grants and complete deletion/restore lifecycle are unfinished. No operational-safety readiness or autonomous use-of-force capability.

The 2,073 retained third-party source files remain unchanged and inert in `third_party/`. They are research selections, not eight installed runtimes. No new upstream code was copied or installed in this revision. Licence headers/package declarations and primary documentation are evidence for evaluation, not a blanket commercial clearance.

This repository is public. Keep credentials, recordings, private client/personal information and live operational data out of it. ALFRED-original licensing remains the owner's decision; preserve all third-party rights. Historical briefs/plans are retained under docs/archive/ and Git history.
