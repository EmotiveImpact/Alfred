# Adoption credit check receipt

17 October 2026. Branch `claude/project-thread-att046-adoption-check`, started from `origin/main`
at `d81a5d509b09637437fe8721b486fcea4224c526`. **Tested commit:
`32582f5744d4683b01f729d93e4e2481256255ef`.** The commit that adds this receipt changes no code.
Status: implemented on a branch. Not merged, not wired into CI, not reviewed by the owner.

Design, header format and limits: [docs/ADOPTION_CHECK.md](../../ADOPTION_CHECK.md).

## What exists

- `tools/check_adoptions.py`: scans `alfred/`, `tools/`, `web/` and `console/src/` for
  `Adapted from:` credit blocks and checks each against the research shelf and source library
  catalogues and manifests, read as JSON data. Exit 0 clean, 1 credit problems, 2 could not run.
- `tests/test_check_adoptions.py`: 51 offline tests. Synthetic catalogues, manifests, snapshot
  files and credits are in `tests/fixtures/adoptions/` (invented projects, repeated-pattern
  commits, real SPDX licence identifiers). One test reads the real catalogues as data and
  requires the repository to pass.

No adopted code exists, so the real run checks nothing and says so.

## Commands and results on the tested commit

Python 3.13.16, offline.

| Command | Result |
|---|---|
| `python3 -m unittest tests.test_check_adoptions` | `Ran 51 tests`, `OK` |
| `python3 tools/check_adoptions.py` | Exit 0. "Scanned 182 files in alfred/, tools/, web/, console/src/ against 39 copied snapshots (research shelf 6, source library 33); 9 reference-only entries cannot be adapted from." then "No adopted code yet: ...", "adoptions ok" |
| `python3 -m unittest discover -s tests` | `Ran 1478 tests in 236.143s`, `OK` |
| `python3 tools/check_claims.py --base origin/main --branch claude/project-thread-att046-adoption-check` | `claims ok` |
| `git diff --check origin/main...HEAD` | No output, exit 0 |

Mutation checks during development (each rule disabled in turn, then restored): disabling the
notice quote check, the minimum copy size, continuation lines, the UNLICENSED rule or the
skipped folders each made at least one test fail.

## Left for others

- CI: add a step running `python3 tools/check_adoptions.py` (a separate follow-up; `.github/`
  was not edited).
- Owner: agree notice rules before code under any licence other than MIT or Apache-2.0
  (BSD-2-Clause, PostgreSQL, GPL-3.0, AGPL-3.0 and others are in the library) can pass, and
  decide where full licence texts for adopted code will live in ALFRED.
