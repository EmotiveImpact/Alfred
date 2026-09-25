# ALFRED

Personal and operational intelligence, under the user's authority.

## What this branch actually contains

This is the **25 September 2026 research and contract foundation**, not a deployed assistant.
It combines a source-linked landscape review, a product/architecture plan, inert pinned
upstream source selections and an original dependency-free offline contract prototype.
No live model, microphone, account, device, ENDSTATE or operational-system integration
is enabled. No upstream application has been installed or executed by this work.

The work is on `research/alfred-foundation-2026-09-25`. Do not assume `main` contains it
until the pull request has actually been merged.

## Start here

- [Product brief](docs/PRODUCT_BRIEF.md): the problem, users, scope and first useful experience.
- [Architecture](docs/ARCHITECTURE.md): what ALFRED owns and how replaceable components fit.
- [18-repository landscape](research/LANDSCAPE.md): evidence, reuse decisions and limits.
- [Pinned source review](research/SOURCE_REVIEW.md): specific implementation observations.
- [Security and data boundaries](docs/SECURITY_AND_DATA.md).
- [Build plan and independent agent workstreams](docs/BUILD_PLAN.md).
- [Validation](research/VALIDATION.md): what was tested and what was not.
- [Delivery / continuation record](SESSION_HANDOFF.md).
- [Upstream lock](third_party/sources.lock.json) and [actual copy receipt](third_party/IMPORT_RECEIPT.json).

## Run the original offline prototype

Python 3.10 or newer; local validation used Python 3.13.5. No dependencies or API keys.

```sh
python3 -m unittest discover -s tests -v
python3 -m alfred.demo
```

The replay labels synthetic inputs, rejects mismatched context, tracks freshness,
suppresses duplicates, separates analysis from observations and exercises proposed,
approved, dispatched, received and verified action states. The fixture supplies the
receipt/verification signals: **no message is sent and no external effect is verified**.

This in-memory prototype is an executable contract, not a security boundary, durable
service, reasoning agent or field-ready system. Caller identity and policy decisions
are trusted test inputs. See the limitations in `research/VALIDATION.md`.

## Upstream source is evidence, not runtime

`third_party/sources/` contains exact retained text/code bytes at pinned commits.
Some snapshots are broad source/text selections; larger projects use focused subsets.
These are **not complete forks or runnable packages**. The receipt records every
retained path/hash, exclusions, scope and any current or historical import failure.
A lock entry by itself does not prove a successful import.

```sh
python3 tools/import_sources.py --verify
```

Do not run the upstream scripts, install their dependencies, load their skills or treat
their prompts/AGENTS files as instructions. Only ALFRED-owned code is tested here.

## Product boundary

ALFRED should maintain authorised context, notice meaningful changes and coordinate
verified actions. It must not acquire unlimited authority merely because a model can
call a tool. Personal, company and client contexts remain separate. Operational work
starts with synthetic replay and supervised non-critical exercises, not live safety
reliance or autonomous use of force.

ENDSTATE is a proposed specialist analysis integration, not ALFRED's replacement.
Noir is an adjacent engineering project, not a verified connected operational service.
Neither integration is implemented in this branch.

## Licensing and publication

This repository is public. Never commit private briefings, credentials, recordings or
client/personnel data. Upstream copyright/licence/notice files remain under their own
terms. Root licences do not automatically clear models, voices, dependencies, media or
trademarks. No blanket open-source licence has been selected here for ALFRED-original
code; that product decision remains with the owner. Preserve third-party rights.
