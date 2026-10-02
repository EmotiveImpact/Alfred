# ALFRED

## Operational and executive intelligence

A personal AI operating environment for understanding what is happening, deciding what matters, coordinating people and projects, and carrying out authorised work with traceable outcomes.

**Start from `main`.** The nine previously stacked development PRs have been merged, preserving their commits. The Python application, existing web interface, latest React/Three.js console, PRD, memory plans and historical source archives now share one repository baseline. New work branches should start from current `main`, not a stale research branch.

## Start building

Read [BUILD_START_HERE.md](BUILD_START_HERE.md), [AGENTS.md](AGENTS.md) and [SESSION_HANDOFF.md](SESSION_HANDOFF.md).

| Resource | Where to go |
|---|---|
| Product definition and requirements | [Positioning](docs/PRODUCT_POSITIONING.md), [PRD](docs/PRD.md) |
| Architecture and memory | [System architecture](docs/ARCHITECTURE.md), [memory architecture](docs/MEMORY_ARCHITECTURE.md), [Obsidian integration](docs/OBSIDIAN_INTEGRATION.md) |
| What to build next | [Roadmap](docs/ROADMAP.md), [12-job backlog](plans/memory-backlog.json), [work packages](docs/BUILD_PLAN.md) |
| Broad upstream source collection | [Source-library catalogue](third_party/library/README.md), [machine-readable catalogue](third_party/library/CATALOGUE.json) |
| Earlier focused source selections | [Original shelf](third_party/BUILD_REFERENCE_SHELF.md), `third_party/sources/`, `third_party/extensions/` |
| Current consolidation evidence | [Consolidation record](docs/CONSOLIDATION_2026-09-27.md) and the `ALFRED unified build` workflow |
| Console development | [Console handoff](CONSOLE_HANDOFF.md), [console guide](console/README.md) |

## Two working surfaces, not yet one connected interface

`alfred/` and `web/` contain the local application: SQLite persistence, authenticated local sessions, read-only note/project indexing, source-backed questions, bounded conversations, reviewed memory, fixed Pulse reports and exact approvals for local drafts.

`console/` contains the newer React/TypeScript, Three.js and original GLSL console. Its sphere, navigation, inspection and review demonstrations work, but its records are fictional fixtures. **The premium console is not yet connected to the real backend.** Merging the source preserves both surfaces; it does not claim that missing adapter has been built.

Reviewed statements are not yet automatically included in conversation context. The optional tool-free local model adapter is off by default, and prior experiments exposed failures. Voice, external accounts, devices, ENDSTATE and Noir remain unconnected. Application encryption and mature person/device/source permissions are unfinished. Use synthetic data.

## Run the local application

```sh
python3 -m alfred.desk init --data-dir ~/.local/share/alfred/development
python3 -m alfred.desk access --data-dir ~/.local/share/alfred/development
python3 -m alfred.desk serve --data-dir ~/.local/share/alfred/development
```

Keep the access key private and the service on loopback. The host must remain running for scanning, queues and routines. Only local drafts are written; nothing is sent externally. This does not install an always-on service.

Keep `--data-dir` on a local disk that no sync tool watches and outside every vault. `init`, `serve` and `restore` refuse a recognised Syncthing, Dropbox, Nextcloud, iCloud Drive or macOS cloud storage folder, a Git working tree or a vault, and there is no override. To keep a copy elsewhere, `backup` writes a consistent, restorable snapshot and `export --export-dir PATH` writes a readable, filtered record; neither is encrypted. See [the sync separation](docs/SYNC.md).

For the separate fixture console, using its committed lockfile and supported Node version:

```sh
cd console
npm ci
npm run dev
```

## Use the source library without executing it

The catalogue covers all 42 repositories named in the agent/memory research and extensions. Available source snapshots contain eligible UTF-8 source, tests, documentation and configuration at exact commits, with file hashes and explicit omissions. They are **not complete forks, model downloads or installed ALFRED dependencies**.

Licence-restricted or unresolved repositories remain pinned references. `UNLICENSED` is not the permissive `Unlicense`. Obsidian Headless is an official-client reference, not redistributed application code. GPL/AGPL and other included projects retain their own rights and obligations. The collection does not relicense them or approve product incorporation.

The historical 2,309 retained files remain unchanged in the older two archives. Broad-library totals are separately reported in its catalogue, avoiding misleading unique-file totals across overlapping copies.

## Verify

```sh
python3 tools/check_memory_plan.py --self-test
python3 tools/check_memory_plan.py
python3 tools/test_source_library.py
python3 -m unittest discover -s tests -v
python3 tools/import_sources.py --verify
python3 tools/extend_sources.py --verify
python3 tools/build_source_library.py --verify
```

The unified workflow also typechecks/builds/tests the premium console and exercises both interfaces in browsers. Archive checks verify retained bytes, not upstream security or product suitability. Read actual completed CI results before claiming success.

This public development repository contains no authorised private vault, account credentials or live operational information. Preserve personal, company and client boundaries. No production deployment or operational-safety readiness is implied by consolidation.
