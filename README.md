# ALFRED

## Operational and executive intelligence

A personal AI operating environment for understanding what is happening, deciding what matters, coordinating people and projects, and carrying out authorised work with traceable outcomes. It runs on your own machine over your own Markdown notes. Models may propose; an independent policy layer decides, and every effect is recorded.

**Status, 2 October 2026.** The integration branch `claude/alfred-development-qpgxhg` (draft PR #18) holds the whole-product build: a connected console, reviewed memory with history, executive records, routines, bounded local jobs, device pairing, read-only connectors and spoken output. Of 33 requirements, 8 are implemented on the branch, 24 are partial and 1 has not started. Nothing is deployed, and synthetic data only until identity, encryption and deletion accounting are finished. See [CHANGELOG.md](CHANGELOG.md) and [BUGS_AND_FIXES.md](BUGS_AND_FIXES.md).

## Where to read

| You want to | Read |
|---|---|
| Find any document | [docs/INDEX.md](docs/INDEX.md), the map of every document and what it is for |
| Know what changed and when | [CHANGELOG.md](CHANGELOG.md) |
| See every bug found and how it was fixed | [BUGS_AND_FIXES.md](BUGS_AND_FIXES.md) |
| Start building | [BUILD_START_HERE.md](BUILD_START_HERE.md), [AGENTS.md](AGENTS.md), [SESSION_HANDOFF.md](SESSION_HANDOFF.md) |
| Resume the current build | [docs/CHECKPOINT_2026-10-02.md](docs/CHECKPOINT_2026-10-02.md) |
| Understand the product | [Positioning](docs/PRODUCT_POSITIONING.md), [PRD](docs/PRD.md), [Roadmap](docs/ROADMAP.md) |
| See what is left to build | [docs/REMAINING_BUILD_PLAN.md](docs/REMAINING_BUILD_PLAN.md) |
| Understand the design | [Architecture](docs/ARCHITECTURE.md), [memory architecture](docs/MEMORY_ARCHITECTURE.md), [security and data](docs/SECURITY_AND_DATA.md) |
| Track every requirement | [plans/requirement-register.json](plans/requirement-register.json) (checked by `tools/check_requirement_register.py`) |
| Work on the console | [CONSOLE_HANDOFF.md](CONSOLE_HANDOFF.md), [console/README.md](console/README.md), [connected console](console/docs/CONNECTED_CONSOLE.md) |

## What is in the repository

```
alfred/        Python 3.11+ backend: SQLite store, loopback HTTP server, memory, jobs, routines (standard library only)
web/           The original plain HTML/JS interface served at /
console/       The React, TypeScript and Three.js console served at /console/ once built
tests/         Backend test suite (python -m unittest)
tools/         Checks, browser acceptance scripts, evaluations and source-library tooling
docs/          Product, architecture, design notes, receipts and evidence
plans/         Requirement register, memory backlog and source coverage (machine-checked)
research/      Research notes behind the plans
third_party/   Inert source library for research. Never installed, imported or executed
```

## Get it up and running

### Requirements

- Python 3.11 or newer. The backend uses only the standard library; there is nothing to `pip install` for the application itself.
- Node.js 22.12 or newer and npm, only if you want the premium console.
- Linux or macOS. Chromium is needed only for the browser acceptance checks.
- A local disk folder for ALFRED's data that no sync tool watches. `init` refuses a Syncthing, Dropbox, Nextcloud, iCloud Drive or macOS cloud folder, a Git working tree and any vault, with no override.

### 1. Clone and choose a data folder

```sh
git clone https://github.com/EmotiveImpact/Alfred.git
cd Alfred
export ALFRED_DATA=~/.local/share/alfred/development
```

### 2. Create a private workspace

```sh
python3 -m alfred.desk init --data-dir "$ALFRED_DATA"
```

This creates a synthetic demonstration vault, the SQLite database and three local access keys (owner, reader, source) in a file only your user can read. No key is printed.

### 3. Build the console (optional, recommended)

```sh
cd console
npm ci
npm run build
cd ..
```

The build lands in `console/dist/` and the backend serves it at `/console/` from the same loopback origin, so it shares the session, CSRF and Host/Origin checks. Without a build, `/console/` answers `console_not_built` and the original interface at `/` still works.

### 4. Reveal your key and start the host

```sh
python3 -m alfred.desk access --data-dir "$ALFRED_DATA"        # prints the owner key; keep it private
python3 -m alfred.desk serve  --data-dir "$ALFRED_DATA"        # http://127.0.0.1:8765
```

Open `http://127.0.0.1:8765/console/` (or `/` for the original interface) and sign in with the owner key. The host is a foreground process: scanning, the conversation queue, Pulse and routines run only while it is running. Ctrl+C stops it; everything stays on disk. Nothing is installed as a service and nothing is sent anywhere.

### 5. Use your own notes (optional)

```sh
python3 -m alfred.desk serve --data-dir "$ALFRED_DATA" --vault ~/Notes --vault-exclude Private
```

The vault is read only. ALFRED never writes into it except through the approved create-only inbox notes. Keep the data folder outside the vault.

### Everyday commands

| Command | What it does |
|---|---|
| `access --role owner\|reader\|source` | Print a key. Never run it in a shared terminal or CI log |
| `rotate --role owner` | Replace a key; the old one stops working at once |
| `revoke --credential-id ID` | Revoke a credential; open sessions and queued work are rechecked |
| `backup` | Consistent, restorable, unencrypted SQLite snapshot under the data folder |
| `restore --backup-file FILE` | Restore while the host is stopped; forget and revocation journal entries are replayed |
| `export --export-dir PATH` | Readable JSON and Markdown export with checksums, never inside a vault |
| `rebuild-index` | Rebuild the note index and projections while the host is stopped; identities, revisions and reviews are kept |
| `connector-add --connector ics-export\|vcf-export --connector-label L` | Add a read-only calendar or contacts export connector |
| `connector-import --connector-source ID --export-file FILE [--dry-run]` | Import an export file you chose |
| `connectors` | List connectors and their freshness |

Optional flags: `--port` (1024 to 65535, default 8765), `--local-model NAME --model-port 11434` for an opt-in, tool-free model on an Ollama server you already run (nothing is downloaded; off by default), `--vault-id-key alfred_id` to adopt stable note identifiers from frontmatter.

### Verify your checkout

```sh
python3 -m unittest discover -s tests            # backend, about 1,100 tests, 3 minutes
python3 tools/check_requirement_register.py      # register consistency
python3 tools/check_memory_plan.py               # backlog and source-shelf consistency
cd console && npm run build && npm test          # typecheck, build, unit tests
```

Browser acceptance (needs Chromium and a Python virtual environment with Playwright; the backend itself has no such dependency):

```sh
python3 -m venv /tmp/alfred-browser && /tmp/alfred-browser/bin/pip install 'playwright==1.57.0' 'Pillow==11.3.0'
/tmp/alfred-browser/bin/python -m playwright install --with-deps chromium
CHROMIUM_PATH=/path/to/chromium /tmp/alfred-browser/bin/python tools/check_console_connected_browser.py
cd console && npx playwright test                # 29 offline demo scenarios
```

Each `tools/check_*_browser.py` script starts a real loopback server over the synthetic vault, drives Chromium and writes a report and screenshots under `docs/evidence/`. Set the script's `ALFRED_*_OUTPUT` variable to write elsewhere. The `ALFRED unified build` workflow in `.github/workflows/` runs all of this on every push.

## How it is built

- **Backend.** `alfred/local.py` is the store and authentication; `alfred/knowledge.py` scans vaults and indexes notes; `alfred/desk_http.py` is the loopback server with HttpOnly sessions, CSRF tokens and Host/Origin checks; `alfred/reviewed_memory.py` and `alfred/memory_history.py` hold reviewed statements and their history; `alfred/executive.py` holds goals, commitments, decisions and milestones; `alfred/routines.py` runs the two authored routines; `alfred/jobs.py` is the bounded local job coordinator; `alfred/lifecycle.py` covers forget, backup and restore; `alfred/policy.py` covers grants, invitations and device pairing.
- **Console.** `console/src/integration/` talks to the server, `console/src/state/` holds the projection, `console/src/components/` renders it. Demo mode uses fictional fixtures; connected mode reads only what the signed-in key may read.
- **Authority.** Notes, graph edges, retrieved procedures, skills and tool descriptions cannot grant permission. Approvals bind exact parameters and source revisions; dispatch rechecks them. Reviewed statements are used only while accepted, authorised, current and relevant.
- **Boundaries.** Loopback only. No microphone, no external accounts, no outbound messages, no telemetry. The source library under `third_party/` is research data and is excluded from tests, packaging and agent instructions.

## Not yet done

Application encryption and key custody, strict per-source grants by default, team workspaces, a real connector account, a second node for jobs, semantic answer evaluation, and the blocked live-model comparison. These are tracked in the register and listed with owner decisions in the [checkpoint](docs/CHECKPOINT_2026-10-02.md).

## Licence and data

This public development repository contains no private vault, credentials, recordings or client or operational data, and carries no licence grant of its own. Third-party material under `third_party/` keeps its original licences and notices; see [third_party/library/README.md](third_party/library/README.md).
