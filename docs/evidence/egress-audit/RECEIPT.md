# Network egress audit: receipt

Branch `claude/project-thread-att046-egress-audit`, started from `main` at
`d81a5d509b09637437fe8721b486fcea4224c526`.
Tested revision: `fd6e4b1ac67182a0be8b9230f6209f7ff8700ae7` (the implementation commit). This
receipt is added in the following commit and changes no code.

Synthetic data only. Nothing under `third_party/` was read, imported, installed or executed;
the audit skips it and a test proves it is never read. No network was used. Python 3.13.16.

## What was added

- `tools/egress_audit.py`: reads every `.py` file under `alfred/` and `tools/` through `ast`,
  never importing or running it. Fails on an unlisted network import, a stale allowlist entry
  or a file it could not audit (exit 1); refuses a malformed allowlist, a missing scanned
  folder or a root inside `third_party/` (exit 2). Warns, without failing, on literal network
  programs run through `subprocess`, `os` or `asyncio`, and on dynamic imports of run-time
  names. `--self-test` runs 12 built-in synthetic cases.
- `tools/egress_allowlist.json`: 33 files, 39 exact imports, each with a one-line reason.
- `tests/test_egress_audit.py`: 57 tests on synthetic sources and temporary trees, plus the
  shipped allowlist against the real tree.
- `docs/EGRESS_AUDIT.md`: plain explanation for the owner, then scope, blind spots, the
  current entries and how to change them.

## How it was built

Tests first: `tests/test_egress_audit.py` was written before the tool and run at
`d81a5d509`, where it failed with `ImportError: cannot import name 'egress_audit' from
'tools'`. The tool was then written until the tests passed. One test (submodules reached
through `urllib` and `xmlrpc`) was added alongside the fix it pins.

Mutation check, in a scratch copy of the tested commit: each of these deliberate breakages
made `tests.test_egress_audit` fail: no `third_party/` pruning, no stale-import check, no
missing-file check, top-level imports only, no dynamic-import handling, unsorted output, no
symbolic link check, no refusal of a root inside `third_party/`, aliases ignored.

## Commands and results at the tested revision

| Command | Result |
|---|---|
| `python3 -m unittest tests.test_egress_audit` | `Ran 57 tests`, `OK` |
| `python3 tools/egress_audit.py --self-test` | `self-test ok: 12 cases`, exit 0 |
| `python3 tools/egress_audit.py` | `egress audit ok: 107 files scanned, 39 allowlisted network imports, 0 warnings`, exit 0 |
| `python3 -m unittest discover -s tests` | `Ran 1484 tests in 234.191s`, `OK` |
| `python3 tools/check_claims.py --base origin/main --branch claude/project-thread-att046-egress-audit` | `4 changed files ... (claude)`, `claims ok`, exit 0 |
| `git diff --check` | no output, exit 0 |

## Not done here

- CI does not yet run the tool as its own step; `.github/` was not edited. The follow-up step
  is `python3 tools/egress_audit.py --self-test` then `python3 tools/egress_audit.py`. Until
  then the existing `python3 -m unittest discover -s tests` step already fails on an unlisted
  or stale import through `test_real_tree_passes_with_the_shipped_allowlist`.
- `tests/` and `console/` are not scanned (see the document for why).
- The audit cannot see network use through wrappers, such as `git fetch` inside
  `tools/build_research_shelf.py`; the document lists this and the other blind spots.
