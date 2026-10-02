# Bugs and fixes

Every defect found in ALFRED, how it showed, the cause, the fix and the commit that carries it. Newest first. Entries marked *environment* were not code defects but broke a check and are kept so the next person does not rediscover them. Add a row here whenever a fix is committed; a fix without an entry is not finished.

Format: **ID. Title** · found · fixed in commit · status.

## Open

| ID | Title | Found | Notes |
|---|---|---|---|
| none | | | |

## Fixed

### B-025. Read-aloud browser check raced the server (and same-second playbacks had no stable order)
Found 2 October 2026 on CI for PR #18 · fixed in the commit that adds this entry.
The `console-connected` job failed at "a stopped playback is recorded as stopped and cannot be acknowledged" on a commit that only changed `.gitignore`. Two causes. First, the page shows a played or stopped state and only then reports it to the server, but the check read the database the moment the text appeared, so on a slower runner the record still held its old state. Second, playback records were ordered by creation second and then by a random identifier, so two playbacks made in the same second came back in random order and "the last record" could be the first playback. The server's own history list had the same tie. Reproduced on demand by recording each outcome 0.6 seconds late, which failed every time. The check now waits for the server record, picks the new playback by identifier and records outcomes late on purpose, so this path is exercised on every run; history and pruning order by creation second and then insertion order. New test: `tests/test_voice.py` `test_history_lists_playbacks_newest_first_within_one_second`, which fails without the change. The console's own "I heard this" cannot overtake its report today, because the desk server handles one request at a time in arrival order and the report is always sent first; a multi-threaded server would need the console to wait for the report before acknowledging.

### B-024. Playwright missing after a container restart (environment)
Found 2 October 2026 · no commit · fixed by recreating the environment.
The browser checks failed with `ModuleNotFoundError: No module named 'playwright'` and the console suite with "Executable doesn't exist". The scratch virtual environment at `/tmp/alfred-browser` and the Chromium path had gone with the container. Recreated the venv, installed `playwright` and pointed `CHROMIUM_PATH` and `ALFRED_CHROMIUM_PATH` at `/opt/pw-browsers/chromium`. The README now records the exact setup.

### B-023. Retry of an accepted reminder could silently change the decision
Found 2 October 2026 · `ac42a75ad` · fixed.
Sending the same accept twice correctly returned the recorded decision, but a retry that asked for a follow-up after a plain acceptance (or the reverse) also returned the earlier result as if it had been honoured. Now refused with `nomination_closed`. Test in `tests/test_routines.py`.

### B-022. Statements with only observed history reported as "recorded later"
Found 2 October 2026 · `cc1d0dab9` · fixed.
A statement whose history held only availability observations (withheld, restored) was treated by the as-of report as having a recorded history, so its proposal time looked later than it was. Such statements are now counted as without recorded history. Observed entries also repeated their label in the console. Tests in `tests/test_memory_temporal.py`.

### B-021. Health browser check hard-coded a note count
Found 2 October 2026 · `b5cb60a59` · fixed.
The check expected "20 notes" but the demo vault held 21 by then because an earlier step creates an inbox note. The assertion is now a pattern, and a load-sensitive jobs step was given a longer timeout.

### B-020. Voice test intermittently returned 404
Found 2 October 2026 · `1f12e123b` · fixed.
`tests/test_voice.py` created the answer through the running server, whose own conversation worker could pick the turn up first and mark it interrupted, so the playback route found no answer. The answer is now created with a separate `ConversationService` before the server starts, and the server creates its `VoiceLog` once.

### B-019. Answer support counted withheld statements by predicate alone
Found 2 October 2026 · `5566cad81` · fixed.
"What is the Atlas status?" counted a withheld statement about a different project because its predicate was also `status`. Withheld statements now count only when the question names their subject. Regression test in `tests/test_answer_support.py`; the evaluation receipt records the failed case.

### B-018. Answer support missed inflected words
Found 2 October 2026 · `5566cad81` · fixed.
"When does Harbour open?" reported "open" as not found although the note said "opens". Coverage now accepts a shown word that starts with the asked word, or with its stem after one common English ending. Regression test in `tests/test_answer_support.py`.

### B-017. Job output limit race
Found 2 October 2026 · `9ab48c367` · fixed.
Under load a job whose output exceeded the limit could exit before the reader recorded the reason, so the run showed a plain failure with no `output_too_large`. `_read_output` now sets the reason under the lock before killing the child, even if the child has already exited. A deterministic test replaced the load-dependent one.

### B-016. Source removal browser scenario timed out and lost its receipt
Found 2 October 2026 · `9ab48c367` · fixed.
Two rendering pages in one Chromium made screenshots and form fills time out, and the "Access changed" notice overwrote the removal receipt because the console treated the owner's own removal as a lost grant. The check closes the main context and uses reduced motion; the console calls `expectAccessChange` before the POST so a self-initiated change keeps its receipt. A `\b0 records` assertion also matched "field0" and became `(^|[^0-9])0 records`.

### B-015. Revoked-device check compared text too early
Found 2 October 2026 · `fcdf7e9ae` · fixed.
"revoking another device leaves this device connected" read `inner_text` before the list re-rendered. Changed to Playwright's retrying `to_have_text`.

### B-014. Playwright strict-mode and label collisions in the connected check
Found 2 October 2026 · `73519da62` · fixed.
"Sample film" matched two records and the jobs form's labels matched by substring. The record locator uses an anchored pattern and the form controls have explicit `aria-label`s ("Job kind", "Number of lines").

### B-013. Owner's own jobs hidden after a revocation
Found 2 October 2026 · `73519da62` · fixed.
The first strict visibility rule hid a job from its own submitter once a grant was revoked, which broke existing tests and hid work the person had started. The submitter, or the same person on another device, always sees their job's metadata; only the artefact stays gated by current read access.

### B-012. Requirement register reformatted on every write
Found 2 October 2026 · `02ca166c0` · fixed.
Writing the register with default JSON formatting produced a whole-file diff. The register is written with `indent=1`, `ensure_ascii=False` and no trailing newline; the backlog with `indent=2` and a trailing newline. `tools/check_requirement_register.py` validates both.

### B-011. Executive dialog controls overflowed at phone width
Found 2 October 2026 · `205cae4ba` · fixed.
At 390px the responsible filter grew to its longest option because a wrapping column flexbox sizes to its content. The toolbar is a single shrinkable grid column and controls may shrink. The browser check asserts every control stays inside the dialog at 1280px and 390px.

### B-010. Scheduling iCalendar messages accepted as full exports
Found 2 October 2026 · `c669579df` · fixed.
An `.ics` file with a scheduling METHOD (invitation, reply, cancellation) is a message, not a snapshot; importing it could remove every other item. Only `METHOD:PUBLISH` or no method is accepted, and a calendar-wide `X-WR-TIMEZONE` is never applied to floating times.

### B-009. Executive record scrolled back into view after every refresh
Found 2 October 2026 · `7735693c0` · fixed.
A refreshed view pulled the reader back to the open record after they had scrolled away. It now scrolls once, when the record is opened.

### B-008. Sync-safety patch hunks rejected on merge
Found 2 October 2026 · `0059bdea8` · fixed.
The sync agent's worktree started from `main`, so its patch did not apply cleanly to the branch; two hunks were applied by hand and the whole suite rerun. Later agents received lead-created worktrees from the branch head.

### B-007. Temporal captures started during hover navigation (console)
Found 27 September 2026 · `7cc9bd9ea`, `3f0eb3f88` · fixed.
Browser captures began before the renderer had initialised and while hover navigation changed layout, giving unstable frames. Tests now wait for actual renderer initialisation and start captures outside hover.

### B-006. Navigation hit area out of step with open state (console)
Found 27 September 2026 · `f7c41ce22` · fixed.
The rail's clickable region did not follow its expanded state. Hit area is now derived from the same state.

### B-005. Pointer, focus and pinned navigation state entangled (console)
Found 27 September 2026 · `b22399327` · fixed.
Hover, keyboard focus and pinning shared one flag, so keyboard users could lose the rail. The three are separate.

### B-004. Knowledge sphere clipped on portrait viewports (console)
Found 27 September 2026 · `9790d1f0a` · fixed.
Camera framing assumed landscape. The sphere now fits the shorter axis.

### B-003. Provenance delayed and ambient rendering continued behind dialogs (console)
Found 27 September 2026 · `04d451f1e` · fixed.
Source provenance appeared a frame late and the sphere kept rendering under modal dialogs, wasting GPU time. Provenance shows immediately and ambient rendering is suspended while a dialog is open.

### B-002. Context restoration not verified by a new frame (console)
Found 27 September 2026 · `d12ccb2d8` · fixed.
After a WebGL context loss the test accepted restoration without proof of rendering. It now verifies a newly rendered frame.

### B-001. Rename identity lost when an old path was reused
Found 30 September 2026 · `87a2b0604` · fixed.
When a note was renamed and a new note later took the old path, the scanner could hand the old identity to the new file. Identity now follows content and the stable identifier, and validated anchors are reported.

## How to log a bug

1. Add it under **Open** with an ID, a title and where it showed.
2. Fix it with a test that fails before and passes after, where a test is possible.
3. Move it to **Fixed** with the commit, the cause and the fix, in the format above.
4. Reference the ID in the commit message when it helps.
