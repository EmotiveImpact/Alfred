# Integration receipt: PR #15, PR #16 and PR #17 combined

2 October 2026. Branch `claude/alfred-development-qpgxhg`, started from main
`8398c7437cb0ef1386d8dc4ff1f9e92fb2557ca2`.

## What was combined

Ordinary merge commits, in this order, with no conflict resolution required
(the console branch and the memory branches touch disjoint files):

| Order | Source | Head | Merge commit |
|---|---|---|---|
| 1 | PR #16, M01/M03 (completed, tested) | `18dcfb39a3244fe21caf1d7ed2887443cf490914` | `dd096d26b` |
| 2 | PR #15, console refinement | `f7c41ce228b83257ad1852ba0f122b2afbc0f2db` | `002f019a6` |
| 3 | PR #17, partial M02/M06 checkpoint | `07573dfdbe906fb3932a31e440d342dfafb089bc` | `e16926c9d` |

PR #17 contains PR #16. Git applied only PR #17's two additional commits in
step 3; nothing was applied twice. PR #17's M02/M06 code is present so it can be
finished on this branch; it is **not** promoted to implemented by this merge.

## Combined acceptance on `e16926c9d` (local container)

| Check | Command | Result |
|---|---|---|
| Application tests | `python3 -m unittest discover -s tests` | 671 pass |
| Plan self-test | `python3 tools/check_memory_plan.py --self-test` | 12 pass; consistency report passes |
| Source library | `python3 tools/test_source_library.py` | 21 pass |
| Console typecheck/build | `npm ci && npm run build` (console/) | pass |
| Console unit | `npm test` | 61 pass (3 files) |
| Console browser | `node tools/standalone.mjs && npx playwright test` | 29 of 29 pass |
| Backend browser | the seven `tools/check_*_browser.py` scripts CI runs, plus `check_memory_context_browser.py` | 195 named checks pass; reports in [browser-reports](browser-reports/) |

Environment notes, kept visible:

- The container's pre-installed Chromium is build 1194 (141.0.7390.37).
  Playwright 1.63 expects a newer headless shell, so the first console browser
  run failed 29 of 29 with "Executable doesn't exist". `playwright.config.ts`
  now honours an opt-in `ALFRED_CHROMIUM_PATH`; unset, behaviour is unchanged
  (CI installs its own browser). The rerun used `/opt/pw-browsers/chromium`.
- The first full console run then failed one test (`offline preview`) because
  `ALFRED-Console.html` had not been generated. CI runs `tools/standalone.mjs`
  before the browser suite; doing the same made it pass. Generated console
  outputs are now listed in `.gitignore`.
- Running `check_memory_browser.py` rewrites the historical v0.8 evidence files
  in place. Those historical files were restored unchanged; this run's report
  is kept here instead.
- Python Playwright 1.57.0 and Pillow 11.3.0 were installed in a scratch
  virtual environment outside the repository, matching CI.

Software-rendered (SwiftShader) graphics checks are evidence for the tested
scenarios only, not physical-device performance. No model inference, private
vault, account, device, deployment or upstream execution was involved.
