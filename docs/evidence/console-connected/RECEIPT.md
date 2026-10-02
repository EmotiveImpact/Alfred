# Connected console receipt (Stages A and B)

2 October 2026, branch `claude/alfred-development-qpgxhg`. Requirements advanced:
UX-001, MEM-009, MEM-016, INT-001, ACT-001 (console path), SYS-001 (session use only).
The commit that adds this receipt is the tested source; CI on that commit is the
independent rerun.

## What was exercised

A real `KnowledgeStore` and `DeskHTTPServer` over the synthetic demo vault, with a
second synthetic workspace that must stay invisible. The built `console/dist` was
served by that server and driven in Chromium 141 (SwiftShader).

| Check | Result |
|---|---|
| `python3 -m unittest discover -s tests` | 699 pass (includes 16 projection and 12 focus tests) |
| `npm run build` and `npm test` in `console/` | build passes; 79 unit tests pass |
| `npx playwright test` (offline demo) | 29 of 29 pass, unchanged behaviour |
| `tools/check_console_connected_browser.py` | 60 of 60 named checks pass (43 at the Stage A and B commit; later commits added M05 forgetting, M04 capture and inbox notes, executive records, server restart and strict-grant checks); [report](browser-report.json) |
| Existing seven backend browser scripts | all pass |

The 43 checks include: sign-in through the real session; graph counts equal to the
permitted backend records; no fixture or other-workspace names; exact source path and
lines; following a supported relationship; a reviewed statement appearing with its
review basis and exact support; source change invalidating it in the open inspector;
selection changing the next question; explicit model absence; a draft proposed from
an answer; the open answer withdrawn on source change; the stale draft refused for
approval and cancelled through the server; a fresh server proposal approved with
explicit consent and verified by the existing outbox; laptop and mobile layout;
revocation clearing every record and dialog; server loss shown as unreachable with
its last confirmation time; no CSP violations, storage use, foreign requests or page
errors.

## Defects found and fixed during this run

- Toasts were offset right in both modes: Motion's inline transform replaced the CSS
  centring. Now animated with Motion's own `x: -50%`.
- Dialog content could grow taller than the dialog frame on desktop (frame 820 px,
  content `100dvh - 58px`), so long content escaped the border. Content now caps at
  the frame height.
- Revocation cleared records but left an open dialog; authority loss now closes
  dialogs, search and answers.
- The command caption said "connected" while unreachable; it now follows the state.

## Screenshots

[Desktop](connected-desktop.png), [reviewed memory inspector](connected-reviewed.png),
[Ask with project context](connected-ask.png), [390 px](connected-390.png),
[server unreachable](connected-unreachable.png). Captured from the running console,
not generated.

## Limits

Synthetic data only. No model configured, so no reasoning quality is claimed.
Software rendering is not physical-device graphics acceptance. One workspace per
credential. Priorities and milestones are not yet recorded by the backend.
