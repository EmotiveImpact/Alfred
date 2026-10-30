# Receipt: secret scrubber (backlog A2)

Tested commit: `d861913fb` on `claude/project-thread-att046-secret-scrubber`, branched from
`main` at `d81a5d509`. This receipt is committed after it.

| Command | Result |
| --- | --- |
| `python3 -m unittest tests.test_scrub` | 25 tests, OK, 0.76 s |
| `python3 -m unittest discover -s tests` | 1,452 tests, OK, 205 s |
| `python3 tools/check_claims.py --base origin/main --branch claude/project-thread-att046-secret-scrubber` | 3 claim errors: on `main` these paths are still in Astra's `codex-secret-scrubber` claim. Expected until pull request #28, which releases it, merges. |
| The same check on a throwaway merge of this branch with pull request #28's head, against that head | `claims ok` |
| `git diff --check` | clean |

Timing of `scrub` on 1 MB of each hostile input in `tests/test_scrub.py` (`BoundedCost`), on
the development container: the slowest took 0.14 s, against the test's limit of 1 s. 1 MB of
genuine fake secrets took 0.07 s.

The scrubber was also run over every tracked file outside `third_party/` as a check for
false alarms. It reported 7 findings, all in tests: six quoted values labelled `token` or
`secret` (such as a CSRF header set to `'wrong'`), and one bare PEM BEGIN line used as test
input. No other text was flagged.

Limits: synthetic data only, no network, nothing imports `alfred.scrub` yet. A clean result
does not mean a text holds no secrets; docs/SECRET_SCRUBBING.md lists what it cannot catch.
