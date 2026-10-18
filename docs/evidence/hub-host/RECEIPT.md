# The host builds the goal hub when asked: receipt (backlog C2)

17 October 2026. Branch `claude/project-thread-att046-hub-host`, started from `main` at
`d81a5d509`. **Tested commit: `d33a26a6580f01c420a7e7089ce7e24409bff645`** (the commit that adds
this receipt changes no code). Status: implemented against synthetic data only. Not merged, not
deployed, not reviewed by the owner.

No model runs anywhere in this work. The only brain is the deterministic H1 `SyntheticBrain`.
Nothing under `third_party/` was read as code, imported, installed or executed.

## What exists

| Part | What it does |
|---|---|
| `alfred/hub_host.py` | `start_goal_hub(store, jobs, owner, choice)` returns the goal hub and a stop function. `off` builds nothing. `synthetic` registers only `SyntheticBrain`, builds `BrainHub` with the default `BrainPolicy` (no cloud scope, no tool) and `GoalHub` over the host's own job coordinator, enrols one `local-brain` worker for `brain_task` only (once per data directory) and runs it on a thread through the hub's backend, so the hub is asked again before any brain starts. Any other choice is refused with `invalid_hub_brain` before anything is built. |
| `alfred/desk.py` | `serve` takes `--hub off|synthetic` (default `off`), passes the hub to the HTTP server, which attaches it to the supervisor, prints `Goal hub on: synthetic test brain only. No model, no cloud, no tools.` when on, and stops the brain worker on shutdown before the local job worker. |
| Docs | `docs/AGENT_HUB.md`, `docs/REMAINING_BUILD_PLAN.md`, `README.md` and `CHANGELOG.md` say the host builds the hub with the switch, off by default. |

## What was run

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests -p test_hub_host.py` | 9 tests, OK |
| `python3 -m unittest discover -s tests -p 'test_hub*.py'` | 62 tests, OK |
| `python3 -m unittest discover -s tests -p 'test_desk*.py'` | 85 tests, OK |
| `python3 -m unittest discover -s tests -p test_recovery.py` | 18 tests, OK |
| `python3 -m unittest discover -s tests` | 1,436 tests, OK (Python 3.13.16) |
| `python3 tools/check_claims.py --base origin/main --branch claude/project-thread-att046-hub-host` | `claims ok` |
| `python3 tools/test_claims.py` | OK |

`tests/test_hub_host.py` covers, in process: `off` creates no table and no worker; unknown
choices (`claude`, `hermes`, empty, `None`, wrong case) are refused with nothing built; the
synthetic hub has exactly one local brain, no cloud scope and no tool, and a `local-brain` worker
with `brain_task` only; a task submitted under a mandate is run by the host's worker thread with
nobody driving it, then accounted by the host supervisor's cycle as `accepted` with
`no_checks` evidence; a second start over the same data enrols no second worker; stopping is
clean and repeatable. With a real `serve` process: without the switch `/desk/hub` answers
`409 hub_not_configured` and no hub table is created; with `--hub synthetic` it answers `200` with
`available: true` and prints the line above; the next start without the switch is off again;
`--hub claude` is refused by the command line; every stop by SIGTERM exits 0.

## Limits

- Only the synthetic test brain. A real brain (Claude direct or Hermes) is the owner's choice
  (integration plan decision 4) and is not offered.
- Brain tasks queued while the hub was on and then started without it stay queued until the hub
  is on again; nothing runs them meanwhile.
- Checks still run only when the owner presses verify; automatic checks are Astra's
  `codex-hub-auto-verify`.
- The browser checks in unified CI were not run locally; CI runs them.
