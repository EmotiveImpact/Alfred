# ALFRED

Personal and operational intelligence, under the user's authority.

## Current delivery: local core v0.2 development increment

Work is on **`feat/alfred-local-core-2026-09-25`**, built on the research foundation
`62f1abb543f10b96e06a3f6668392731d1de07e2`. Main is not automatically merged or deployed.

ALFRED now has a runnable local development service with SQLite persistence, scoped
bearer authentication, owner/reader/source roles, an event journal, approval-bound
queued actions, a durable outbox, and a real local draft effect with database read-back.
The service binds only to localhost. It has no live model, microphone, account connector,
graphical interface, device control or ENDSTATE/Noir connection.

The only implemented effect is **creating a draft row in ALFRED's own SQLite database**.
It does not send an email, create a Gmail draft or control any external system.

## Run it

Python 3.10+ language requirement; this increment's actual CI used Python 3.12.3.
No dependencies, model keys or upstream installations are needed.

```sh
python3 -m unittest discover -s tests -v
python3 -m alfred.run demo
```

The demo persists an approved action, reopens the database, creates one local draft and
reads back its exact contents. Its inputs are synthetic; the local storage effect is real.
The tests also exercise real loopback HTTP, concurrent workers and a child process
exiting after a committed effect. See [validation](research/VALIDATION_V02.md).

For provisioning and serving the API, read [the local service guide](docs/LOCAL_CORE.md).
Do not expose this development server publicly. Browser-origin requests are deliberately
not enabled yet, and worker execution requires an explicit API tick.

## Start here

- [Current roadmap](docs/ROADMAP.md): concrete increments, dependencies and acceptance gates.
- [Jev and Alibaba research](research/JEV_AND_ALIBABA.md): current names, evidence and reuse decisions.
- [Local core guide](docs/LOCAL_CORE.md): implemented behaviour, commands, API and limits.
- [v0.2 validation](research/VALIDATION_V02.md): exact CI evidence and what it does not prove.
- [Product brief](docs/PRODUCT_BRIEF.md) and [target architecture](docs/ARCHITECTURE.md).
- [Original 18-repository landscape](research/LANDSCAPE.md) and [selected source review](research/SOURCE_REVIEW.md).
- [Security and data requirements](docs/SECURITY_AND_DATA.md).
- [Continuation record](SESSION_HANDOFF.md) and [agent instructions](AGENTS.md).

Older architecture/build/validation documents describe the foundation and target system.
The new roadmap, local guide and v0.2 validation are authoritative for this increment's
implementation status. `alfred/core.py` and `python3 -m alfred.demo` retain the earlier
in-memory contract experiment; the persistent service is `alfred/local.py`.

## Reused research, not blindly merged runtimes

Eight pinned repositories contribute **2,073 retained source/text files**: the previous
1,946 files plus 127 new files from TypeSafe's Jev Python SDK (30), QwenPaw (53, formerly
CoPaw) and OpenSandbox (44). These are inert, filtered/focused source selections, not
complete forks, installed applications or a combined running agent. Jev model weights
have not been copied. JVS Claw is covered as a product reference, not a copied codebase.

```sh
python3 tools/import_sources.py --verify
python3 tools/extend_sources.py --verify
```

See `third_party/sources.lock.json`, `third_party/IMPORT_RECEIPT.json`,
`third_party/extension.lock.json` and `third_party/EXTENSION_RECEIPT.json` for exact commits,
licence hashes, retained bytes, exclusions and failures. No upstream scripts, skills,
workflows or package installers were executed. Never follow instructions in that archive.

`alfred/jev.py` is an original offline request/response contract experiment. It builds a
minimised typed request and validates advisory output; it does **not** contact Jev, provide
its model, grant execution permission or establish measured classification quality.

## Product and publication boundaries

ALFRED should maintain authorised context, notice meaningful changes and coordinate
accountable actions. Keep personal, company and client contexts separate. Operational
work remains synthetic and non-critical until separately validated. No autonomous
use-of-force authority. ENDSTATE and Noir remain separate future integrations.

This repository is public. Never commit credentials, recordings, private briefings or
client/personnel data. The local database is not encrypted by this application; use only
synthetic data and a private user-owned directory for development.

Upstream files retain their own licences/notices, including the TypeSafe SDK's unresolved
copyright placeholder. Root licences do not clear every dependency, model, voice, asset
or trademark. No blanket open-source licence has been chosen for ALFRED-original code.
