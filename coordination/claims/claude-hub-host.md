---
id: claude-hub-host
agent: claude
status: active
task: The host builds the goal hub behind a switch that defaults to off (backlog C2)
claimed: 2026-10-17
paths:
  - alfred/hub_host.py
  - tests/test_hub_host.py
  - docs/evidence/hub-host/
---

Built by Claude from coordination/BACKLOG.md item C2. It also adds one hook to `serve` in
`alfred/desk.py` and updates `docs/AGENT_HUB.md`; both stay Claude's and are not claimed so
other Claude work on them is not blocked. Astra stays out of these paths.
