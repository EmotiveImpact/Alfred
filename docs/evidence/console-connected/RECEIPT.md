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
| `tools/check_console_connected_browser.py` | 98 of 98 named checks pass (43 at the Stage A and B commit; later commits added M05 forgetting, M04 capture and inbox notes, executive records, server restart, strict grants and invitations, bounded jobs, device pairing, whole-source removal, sync conflict copies, export connectors, answer support and host health with pause); [report](browser-report.json) |
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
[server unreachable](connected-unreachable.png), [bounded jobs](connected-jobs.png),
[pairing a device](connected-pairing.png), [device list](connected-devices.png),
[source removed](connected-source-removed.png), [sync conflict](connected-sync-conflict.png),
[export connectors](connected-connectors.png), [answer support](connected-answer-support.png).
Captured from the running console, not generated.

## Bounded jobs (added after the Stage A and B commit)

The jobs checks run the real host worker (`start_local_jobs`, local subprocess) behind the
same server. From the inspector an owner runs a word and line count on the open revision
of a synthetic note; the panel shows the server events in order and the exact count with
its basis, and a finished job is not polled again. A second, extractive job is submitted and the panel closed at once; after a
full page reload the panel reads both jobs, the events and the exact first lines back from
the server. Under strict grants a person without a read grant sees no job history; after
redeeming a read invitation the history for that source appears, and the reader can
inspect the note but has no control to submit jobs. Backend rule and tests:
`docs/JOBS.md` (console view and job visibility).

## Limits

Synthetic data only. No model configured, so no reasoning quality is claimed.
Software rendering is not physical-device graphics acceptance. One workspace per
credential. Priorities and milestones come from executive records (see `../executive/RECEIPT.md`).

## Device pairing (added later on 2 October)

The owner creates a reader pairing code in the Security panel. A second browser context,
standing in for another device, pairs from the sign-in screen, is shown its own new key
once, must confirm it has kept the key before continuing, and then reads with the same
person's grants; the key is no longer on the page afterwards. The owner sees the device in
their own list and revokes it; the second context returns to sign-in with no records,
while the owner's session stays connected. Backend rules and tests: the M02 receipt.

## Whole-source removal (added later on 2 October)

In a second, fresh synthetic workspace (so the flow above is unaffected), the owner opens the
source in the inspector, asks to remove it, must tick explicit consent, and confirms. The
receipt summary appears, the view drops to zero records, the synthetic files on disk are
still there, and the removal is in the lifecycle journal. The first page is closed before
this scenario so that two software-rendered scenes do not compete for the CPU.

## Sync conflict copies and export connectors (added later on 2 October)

The fresh workspace also holds a Syncthing conflict copy beside a synthetic note and one
imported calendar export (explicit grants, `connector.read` and `read` for its owner). The
graph counts 23 records: the copy is not a record. The note's inspector names the copy and
the tool, and says ALFRED never merges or chooses; the source inspector lists the copy as
beside its original. The imported event is labelled as an unchecked export report rather
than an authored note. The access panel shows the connector, its freshness and item count,
and an Import switch for that source in place of inbox writing. Removing the vault source
then leaves the connector's two records.

## Answer support (added later on 2 October)

Each answer now shows "What supports this answer": word coverage, excerpt and note counts,
withheld reviewed statements by reason, and whether a model was used, with its limits. A
question about a word the synthetic vault does not contain names that word as not found.
Details and the evaluation with denominators: [INT-002 receipt](../int-002/RECEIPT.md).

## Host health and pause (added later on 2 October)

Console controls now show the host's own report: host state, last background cycle, vault
scan and note count, waiting questions, jobs by state, and for owners the last backup and
journal size, stated as a report from a foreground process, not an installed service. The
owner pauses with a confirmation, a question is then refused with "ALFRED is paused", and the
owner resumes from the same panel.
