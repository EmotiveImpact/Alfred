# ALFRED Personal OS v0.6

26 September 2026. A new interaction shell and a bounded routine service over the
existing application. This is not a new scaffold, native operating system installation,
cloud deployment or a claim that a reasoning model is running.

## Product correction

The owner rejected the v0.5 administrative-dashboard presentation. The default experience
must be personal intelligence, not a catalogue of databases, hashes and status cards.
Preserve ALFRED's personal, work and authorised operational ambitions. The OS metaphor
is a persistent place for context and action, not a justification for unlimited access.

Implemented: black full-viewport workspace, persistent dock, conversation-first Home,
keyboard launcher (Ctrl/Cmd+K), focus view, Memory, Work, Pulse and Controls. Work contains
briefing, evidence, decisions and history. A hash is available on explicit inspection
and in exports, not repeated as the main content of every result. The interface motif
is decorative; its outer note markers derive from the local note count, capped at 32.
It does not represent inference, sensor activity or a verified semantic world model.

The dock sits outside the scrolling workspace so it does not cover interaction targets.
Memory retains the original note-reference graph; a deterministic label-separation pass
reduces overlapping hit targets. It adds no inferred graph relationships.

## Preserved behaviour

Source-first questions, exact evidence inspection, citation invalidation, export, current
project reports, acknowledgement, exact approval, local draft creation/read-back,
role checks, pause/resume and revocation remain. The foreground supervisor is still the
only execution host. No frontend interaction bypasses its existing authority checks.
Focus mode changes presentation only. A command-palette question is source retrieval,
not arbitrary tool execution. Switching to an unauthorised workspace is not available.

The optional tool-free local model adapter remains off by default and not inference-
validated. No microphone, external account, security device, ENDSTATE or Noir is connected.

## Pulse: real routines, not decorative activity

Two fixed report capabilities are implemented in alfred/pulse.py:

- Memory check: counts permitted indexed notes, unresolved references, missing map roots
  and nodes outside map coverage. This is an index check, not factual verification.
- Briefing refresh: counts current/unacknowledged reports in the latest bounded page,
  proposed actions in the latest action view and stored local drafts. It does not produce
  a generated narrative, schedule meetings or send messages.

Both schedules start OFF. Owners can run a report now or deliberately enable its interval.
Default intervals are 15 minutes and one hour. The API accepts only 60, 300, 900, 3600 or
86400 seconds. It does not accept prompts, scripts, arbitrary URLs or browser-defined
capabilities. Enabling a schedule does not immediately execute it. The current host's
provisioned owner must own scheduled work; another owner cannot silently reassign it.

Each due time is recorded durably. A transaction claims the run slot and advances the
schedule. A missed period produces at most one catch-up run per routine, not a backlog
storm. Manual request IDs are idempotent within retained history. No exactly-once external
effect claim is made: both reports only read permitted local state and write run metadata.

Pause stops new scans, drafts and reports. Credentials are checked before work and before
persisting a successful report. Expired/revoked authority, source loss, failed reporting
and interrupted runs remain explicit. Limit failures set a visible last-error value and
back off. No source bodies, question transcripts or credentials are retained in reports.
Counts are marked historical: they must not be interpreted as live state after a source
changes or permission is revoked.

Bounds: 512 retained runs per hosted workspace, 96 starts per UTC day, six per rolling
minute, two fixed routines. At the history bound, further work is blocked, not silently
pruned. A reviewed retention/clear-history workflow is still needed for indefinite use.
The UI shows the latest 40 records from the API, initially the latest eight in the view.
This is interval scheduling, not a calendar/timezone scheduler.

Pulse executes only while the explicitly launched Desk process is alive. This task does
not install systemd/launchd, use the user's ChatGPT subscription as an unattended worker,
start remote agents or deploy a host. Model calls and external messaging are not routines.

## Local run

Use Python on a POSIX development machine and a private data directory outside the repo:

```sh
python3 -m alfred.desk init --data-dir ~/.local/share/alfred/os-v06-demo
python3 -m alfred.desk access --data-dir ~/.local/share/alfred/os-v06-demo
python3 -m alfred.desk serve --data-dir ~/.local/share/alfred/os-v06-demo
```

The access command intentionally shows your key in a private terminal. Do not share it.
Open the printed loopback address on the same machine. Existing v0.5 databases receive
additive Pulse tables; initial schedules remain off. Source notes are never overwritten.
The app is not encrypted at application level and is not for sensitive operational data.

## Validation and preview

Local first-party suite: 400 passing tests at initial validation (355 retained plus 45
new Pulse checks). Tests cover real SQLite, actual loopback HTTP, permissions, schedule
slots, restart, limits, concurrency, pause, revocation and errors. They do not establish
LLM quality or production safety. The browser in the chat container blocks localhost
navigation; local visual checks use the clearly labelled standalone preview. The GitHub
acceptance workflow separately runs real-browser-to-real-server checks and records success
or failure. Do not claim remote acceptance from this plan: inspect its final receipt.

Existing browser flows are preserved and updated only for intentional navigation changes
and progressive disclosure of source hashes. Outputs use the new evidence directory, not
overwritten v0.5 screenshots. Tests, screenshots and exact source hashes belong under
`docs/evidence/personal-os-v06/` after acceptance.

`docs/previews/personal-os-v06/ALFRED-OS-v06.html` is the actual frontend over fictional
read-only in-file data. It has no credentials, sends no HTTP requests and cannot run or
schedule routines. Its three example questions use outputs of the actual retrieval code.
Arbitrary questions require the local app. No fabricated model answers are included.
