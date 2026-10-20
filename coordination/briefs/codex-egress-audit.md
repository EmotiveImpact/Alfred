# Brief for Astra: network egress audit

> **Paused for Astra.** The owner moved this work to Claude on 17 October 2026, and it is
> tracked in `coordination/BACKLOG.md`. No claim exists for it, so the paste prompt below is
> kept only as a record. Read the rest of this brief as the specification.

**Paste into Codex cloud** (repository EmotiveImpact/Alfred, branch `main`):

> You are Astra, working on ALFRED alongside Claude. Read AGENTS.md and coordination/README.md,
> then build the task in coordination/briefs/codex-egress-audit.md. Your claim is
> coordination/claims/codex-egress-audit.md: change only the paths it lists, plus that claim
> file. Work on the branch codex/egress-audit and open a pull request to main when every check
> passes. Do not merge.

## Why this exists

ALFRED keeps private material on the owner's machine and talks to the network only through a
few known modules. Nothing stops a new module quietly opening a connection. This check makes
every network-capable import a reviewed decision.

## What to build

- `tools/egress_audit.py` reads every `.py` file under `alfred/` and `tools/` **as text**
  through `ast`, never importing or running it, and skips `third_party/`. It finds imports
  of network-capable modules: at least `urllib`, `http.client`, `http.server`, `socket`,
  `ssl`, `smtplib`, `ftplib`, `socketserver`, `asyncio` streams and `xmlrpc`, including
  `from x import y`, aliases and imports inside functions. It fails when a file uses one
  that is not on the allowlist, and also when an allowlist entry no longer matches anything,
  so the list cannot go stale. `--self-test` runs its own synthetic cases.
- `tools/egress_allowlist.json` lists each current user, with the module, what it imports
  and a one-line reason. Today these are `alfred/desk_http.py`, `alfred/grounded.py`,
  `alfred/httpd.py`, `alfred/knowledge.py`, `alfred/knowledge_http.py`,
  `alfred/local_model.py` and some tools. Read each file to write the reason honestly (for
  example, loopback server only, or a URL parser with no connection). Where a module imports
  only a parser such as `urllib.parse`, say so.
- `docs/EGRESS_AUDIT.md` explains in plain British English what the check covers, what it
  cannot see (`subprocess` calling `curl`, for example, which it should flag separately as a
  warning), and how an entry gets added.

## How to work

- Tests first in `tests/test_egress_audit.py`, on synthetic source strings: every import
  form, aliases, nested imports, a stale allowlist entry, syntax errors reported rather than
  crashing, and `third_party/` ignored.
- Standard library only. The audit never executes the code it reads.
- Claude adds the CI step after the merge; do not edit `.github/`.
- Run `python3 -m unittest discover -s tests`, `python3 tools/egress_audit.py` and
  `python3 tools/check_claims.py --base origin/main --branch codex/egress-audit` before
  opening the pull request.

## Done when

The audit passes on today's `main` with a reviewed allowlist, every synthetic case is pinned
by a test, and CI is green.
