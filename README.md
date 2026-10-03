# ALFRED

## Operational and executive intelligence

A personal AI operating environment for understanding what is happening, deciding what matters, coordinating people and projects, and carrying out authorised work with traceable outcomes. Models may propose; independent policy decides, and effects have explicit records.

**Status, 3 October 2026.** PR #18 is merged in main `75947b8dd59a3161c862d2533850a032994778e2`, including #15/#16/#17. The local Python/SQLite application and React/Three.js console are connected. Reviewed memory/history, executive workflows, routines, local jobs/cache, device pairing, read-only export importers and output-only read-aloud have bounded implementations. This is not a private-data release, installed native app, always-on cloud service or commercial deployment.

**Next stage: [pilot hardening and future-platform groundwork](docs/NEXT_STAGE.md).** Build current-product reliability and trust while researching native/cloud/provider/partner choices. Do not activate later infrastructure automatically. [The Codex Cloud prompt is in the repository](docs/CODEX_NEXT_STAGE_PROMPT.md); no old handoff ZIP is required. The [audit](docs/AUDIT_2026-10-03.md) records the evidence and a visibility concern still requiring reproduction.

## Where to read

| Need | Document |
|---|---|
| Start or resume building | [BUILD_START_HERE.md](BUILD_START_HERE.md), [AGENTS.md](AGENTS.md), [SESSION_HANDOFF.md](SESSION_HANDOFF.md) |
| Current stage and approval gates | [docs/NEXT_STAGE.md](docs/NEXT_STAGE.md) |
| Launch the next cloud-agent task | [docs/CODEX_NEXT_STAGE_PROMPT.md](docs/CODEX_NEXT_STAGE_PROMPT.md) |
| Product scope and build sequence | [PRD](docs/PRD.md), [roadmap](docs/ROADMAP.md), [remaining plan](docs/REMAINING_BUILD_PLAN.md) |
| What is actually implemented/merged/deployed | [Requirement register](plans/requirement-register.json) |
| Where research came from | [Later-chat reconciliation](docs/sources/2026-10-03/LATER_CHAT_RECONCILIATION.md), [source coverage](plans/source-coverage.json) |
| System and security boundaries | [Architecture](docs/ARCHITECTURE.md), [memory](docs/MEMORY_ARCHITECTURE.md), [security](docs/SECURITY_AND_DATA.md) |
| Every document and historical evidence | [docs/INDEX.md](docs/INDEX.md) |
| Changes and recorded defects | [CHANGELOG.md](CHANGELOG.md), [BUGS_AND_FIXES.md](BUGS_AND_FIXES.md) |

## Source layout

```
alfred/        Python backend, SQLite, loopback HTTP, memory/actions/jobs/routines
web/           Original browser interface
console/       React/TypeScript/Three.js console and tests
plans/         Requirement register, M backlog and source coverage
research/      Dated candidate research, not installed providers
docs/          Requirements, stage gates, architecture, sources and evidence
tests/, tools/ First-party checks and acceptance tooling
third_party/   Inert research source library, never installed or executed
```

## Run a synthetic local workspace

Requirements: Python 3.11+, Node.js 22.12+ and npm for the console, Linux or macOS. Keep the data folder on a local disk outside the repository, vault and watched sync folders. Do not add private information until the pilot safeguards and selected-data approval are complete.

```sh
git clone https://github.com/EmotiveImpact/Alfred.git
cd Alfred
export ALFRED_DATA=~/.local/share/alfred/development
python3 -m alfred.desk init --data-dir "$ALFRED_DATA"
cd console
npm ci
npm run build
cd ..
python3 -m alfred.desk access --data-dir "$ALFRED_DATA"
python3 -m alfred.desk serve --data-dir "$ALFRED_DATA"
```

`access` prints the owner key: use a private terminal, never a shared log. Open `http://127.0.0.1:8765/console/` and sign in. The original interface remains at `/`. Without the console build, `/console/` reports `console_not_built`; it does not silently replace connected data with a mock-up.

The host is a foreground process. Closing its terminal or stopping it stops its loops; no service is installed. Do not expose the listener publicly by changing its bind or removing Host/Origin/CSRF checks. Codex's cloud build environment is not ALFRED's production cloud.

The existing optional local-model flag connects only to a model server the operator has already configured; it downloads nothing and remains off by default. A working model adapter is not evidence of dependable general reasoning. For complete original command examples see the [preserved pre-stage README](docs/archive/pre-stage-2026-10-03/README.pre-stage.md), interpreted with the current privacy/stage gates.

## Verify

```sh
python3 -m unittest discover -s tests
python3 tools/check_requirement_register.py
python3 tools/check_memory_plan.py
cd console && npm run build && npm test
```

The unified workflow runs first-party backend and real browser-to-backend acceptance with synthetic data, as well as the standalone console tests and source-byte checks. Inspect the exact tested revision and reports. The audited main baseline passed 1,113 backend tests and 143 console unit tests, but these historical counts are not a substitute for a new run or a security/performance certification.

## Important boundaries

The graph is a view of permitted records, not a separate brain. Decorative particles do not count as memories. Reviewed statements are not automatically verified facts. Exact local approvals are not general external-action authority. A local subprocess is not a sandbox; a bounded cache is not cloud storage; export importers are not live accounts; read-aloud is not listening.

Application encryption/key custody, strict defaults, complete lifecycle/recovery, measured reasoning, real accounts, multiple nodes and deployment remain separate work. Follow the current register and stage gates rather than the old pre-merge descriptions preserved in dated receipts.

This public repository is not a place for private vaults, credentials, recordings or client/operational data. It carries no licence grant of its own; third-party material retains upstream notices. Runtime adoption and commercial redistribution need explicit licence review. Source preservation does not approve installing the library.
