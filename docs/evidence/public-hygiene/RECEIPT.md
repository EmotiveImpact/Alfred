# Receipt: public repository hygiene check (backlog A7)

Tested commit: `a10860f70` on `claude/project-thread-att046-public-hygiene`, branched from
the secret scrubber branch (`claude/project-thread-att046-secret-scrubber`, pull request
#32, not yet merged) at `704ca6054`. This receipt is committed after it.

| Command | Result |
| --- | --- |
| `python3 -m unittest tests.test_public_hygiene` | 28 tests, OK, 2.2 s |
| `python3 -m unittest discover -s tests` | 1,480 tests, OK, 258 s |
| `python3 -m unittest discover -s tools -p "test_*.py"` | 42 tests, OK |
| `python3 tools/check_public_hygiene.py` | exit 0: 562 tracked files scanned, 99,476 skipped under `third_party/`, 186 binary, 0 symbolic links, 0 submodules, 0 missing; 135 findings, all 135 allowed by 62 reviewed exceptions; 0 stale |
| `python3 tools/check_claims.py --base origin/main --branch claude/project-thread-att046-public-hygiene` | 4 claim errors, all on the scrubber's own paths (`alfred/scrub.py`, `docs/SECRET_SCRUBBING.md`, its receipt, `tests/test_scrub.py`), which this branch inherits from pull request #32 and which are still in Astra's `codex-secret-scrubber` claim on `main`. None is on this item's paths. Expected until pull request #28, which releases that claim, merges. |
| `git diff --check` | clean |

## Timing

Whole repository on the development container, three runs of the command: 1.09 s, 1.11 s
and 1.30 s. Of that, `git ls-files` takes 0.06 s and reading and checking the 562 files
about 1.0 s. The tests feed 1 MB of each of nine hostile inputs to the home path and address
patterns, with a limit of 1 s each; the slowest took 0.19 s.

## What the check found on this tree

Before the allowlist existed, 135 findings in 26 files, 62 distinct (file, kind, text).
Each was reviewed by reading it in place:

- **Workflow commit identities (10 files):** addresses on GitHub's no-reply domain that
  automated workflows in `.github/workflows/` set as their commit email. They name no
  person.
- **Invented addresses on reserved example domains:**
  - `example.org` in the connector tests and one calendar fixture;
  - `.invalid` in the prompt-injection test and its receipt, the scrubber's prose test,
    and throwaway test repositories in `tools/test_claims.py` and
    `tools/test_research_shelf.py`.
- **The scrubber's own description text** in `alfred/scrub.py` (its `REASONS` table, such
  as the text "GitHub token" after a key ending in `_token`).
- **Test inputs:**
  - format placeholders and code in `tests/test_scrub.py` templates;
  - a deliberately weak invented password that the scrubber test expects to find;
  - PEM headers used as hostile input or to prove key material is excluded;
  - a test sentinel in `tests/test_desk.py`;
  - synthetic note text named SECRET in `tests/test_jobs.py`;
  - a deliberately wrong CSRF token in four route tests.

Nothing looked real. No tracked file outside `third_party/` holds a home-directory path
naming a person or machine account: the only home references are `~/...` and `$HOME`,
which name no one. This item's own four files produce no findings, because their test
values are built at run time from pieces.

Limits: synthetic data only, no network. The CI step is not added here; `.github/` is
unchanged. A clean result does not mean the repository holds nothing private:
docs/PUBLIC_HYGIENE.md lists what the check cannot catch.
