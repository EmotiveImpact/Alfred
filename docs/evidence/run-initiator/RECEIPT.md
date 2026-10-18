# Who started a run, shown in the goals panel (backlog C3)

17 October 2026. Branch `claude/project-thread-att046-run-initiator`, stacked on the automatic
verification branch (#33) at `95823aaa5`. **Tested commit: `3249aa615`.** Synthetic data only.

## What changed

The server already records whether each verification run was started automatically, when the
result arrived, or by the owner (#33). The console's goals panel now says so on the run line:

- `Run 1 (automatic, when the result arrived): 1 passed · 1 failed · 0 could not run`
- `Run 2 (by you): 1 passed · 1 failed · 0 could not run`

A run from a server that does not send the field keeps the old wording (`Run 2: ...`). Nothing
about how a run is judged or counted changes, and the panel sends nothing new.

Files: `console/src/integration/goals.ts` (`ResultRun.initiated`, `runLine`),
`console/tests/goals.test.ts`, `tools/check_hub_integrate_browser.py` (the expected run lines)
and one sentence in `docs/AGENT_HUB.md`.

## Commands and results at `3249aa615`

```
cd console && npx vitest run tests/goals.test.ts   # failed first on the new expectations, then 11 tests OK
cd console && npx vitest run                       # 18 files, 174 tests OK
cd console && npm run build                        # tsc --noEmit and vite build OK
tools/check_hub_integrate_browser.py               # {"passed": 23, "page_errors": []}
```

The browser check ran with Playwright 1.57.0 and the preinstalled Chromium, against the console
built from this commit. The console's own fixture browser suite (`npm run test:browser`) was not
run locally: it does not open the goals panel. CI runs it.
