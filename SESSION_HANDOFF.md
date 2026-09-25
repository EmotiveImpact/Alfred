# ALFRED continuation record: local core v0.2

25 September 2026. Public repository: EmotiveImpact/Alfred.

## Where to continue

Current development branch: `feat/alfred-local-core-2026-09-25`.
Foundation branch: `research/alfred-foundation-2026-09-25`, draft PR #1.
Foundation head: `62f1abb543f10b96e06a3f6668392731d1de07e2`.
First persistent-core commit: `1a0f7b4caee30222d791ea691fbc9f2cd4310f60`.
Source-extension commit: `cc0813605c58412ad1cce01cd9fbf410b89d5c99`.

Read the actual current remote branch and latest PR/CI before continuing; later commits
add documentation and hardening. No main merge or hosted deployment was performed. Do
not restart from the README-only main as though it contains the application.

## Product direction

Keep ALFRED, persistent personal/work/authorised operational context, optional voice and
future device integrations. Brand ownership remains open. ENDSTATE and Noir are separate,
not implemented connections. No autonomous use-of-force capability.

## What is actually implemented

The original in-memory contracts remain in core.py. The new local.py service adds SQLite
persistence, scoped bearer credentials and roles, event provenance/freshness/deduplication,
immutable action proposals, approval/outbox transactions, worker leases, cancellation,
revocation/expiry rechecks and local result reconciliation. httpd.py exposes a loopback
API; run.py provides provisioning, revocation, server and synthetic demo commands.

Only message.draft is executable. It creates and reads back a row in ALFRED's SQLite
database. It does not send a message or create a draft in a third-party account. Worker
execution is an explicit tick, not an autonomous background daemon. No UI, microphone,
live reasoning model, account connector, home device, ENDSTATE or Noir connection exists.

jev.py is an offline typed-wire-contract experiment, not a live API integration. It has
no credentials or network transport. Permissions remain independent of model advice.

## Source extension

The old 1,946 retained files are unchanged. Added 127 files from three pinned projects:
TypeSafe Python SDK 30; QwenPaw 53 (CoPaw redirect); OpenSandbox 44 (new canonical owner).
Total: 2,073 retained source/text files, eight repositories, not complete forks/runtimes.
All third_party content is inert, including nested agent instructions. JVS Claw is a
researched product reference; no source licence/repository was verified for copying it.

Import CI run 36192336632 succeeded and verified both archives. First local-core CI run
36193034829 passed 146 tests, both demos and both archive verifiers using Python 3.12.3.
See research/VALIDATION_V02.md and latest CI for subsequent test additions/results.
Current increment was executed on GitHub Actions, not locally in the chat container.

## Next implementation work

Follow docs/ROADMAP.md. Finish core lifecycle gaps alongside a usable evidence/approval UI
and one read-only connector. Compare Hermes, nanobot and QwenPaw under identical tests;
choose one runtime instead of combining credential-bearing executors. Evaluate Jev in
shadow mode only after scoped egress/keys are authorised. OpenSandbox remains an isolated
experiment until its actual containment is tested. Voice starts with visible push-to-talk.

Issues #2, #3 and #4 are work packages, not claims of running agents. Preserve shared
contracts, use separate branches, and report evidence rather than roadmap percentages.

## Commands

```sh
git fetch origin
git switch feat/alfred-local-core-2026-09-25
python3 -m unittest discover -s tests -v
python3 -m alfred.run demo
python3 tools/import_sources.py --verify
python3 tools/extend_sources.py --verify
```

Create the next implementation branch from the verified current head. Read AGENTS.md.
Do not merge/deploy automatically or put local tokens/databases in this public repository.
