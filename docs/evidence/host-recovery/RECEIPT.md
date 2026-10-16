# Host restart and recovery receipt (plan item 1.4, RUN-001, M09)

Date: 16 October 2026. Branch: `feat/host-recovery-2026-10-16`, started from `main` at `75947b8dd`.

Tested commit: `4b38c4438` (code, tests and browser tool). This receipt and the changelog entry are added in the following documentation-only commit.

## What was built

- `alfred/recovery.py` (new):
  - A private clean-stop marker, `host-state.json` in the data directory (mode 600, atomic replace, never followed through a symbolic link). It holds the run identifier, process ID, start and stop times, the last clean stop and the last recovery report. It holds no keys, question text or note content.
  - `begin` records each start under the host lock and reports the previous stop as `clean`, `unclean`, `first_start` or `unknown` (unreadable marker, not trusted).
  - `reconcile` runs before any worker or question loop starts:
    - Queued or running questions become `interrupted`. The conversation view now gives them the visible reason `host_stopped_before_answer`; the console already says "ALFRED restarted before answering. Ask again." They are never re-asked.
    - Jobs this host had started become `effect_unknown` with reason `host_stopped_while_running` and a `host_restart_reconciled` job event, even when declared side-effect free, because a local subprocess may have done part of its work or outlived the host. They are never re-run and wait for the owner's reconciliation. A lease that never started returns to the queue (`host_restarted_before_start`). Leases held by other enrolled workers are left to their own expiry.
    - Routine and Pulse slots that fell due while stopped are counted. Nothing is run by the count; the routine still runs once for its latest due slot and records the rest as missed, as before.
  - `doctor` (read-only): placement (reusing `alfred/placement.py`), repository containment, directory and live-file permissions, the database (quick integrity check), WAL state, backup age and whether its file is still present, the last stop, and the console build. It never creates the data directory, the lock, `-wal` or `-shm` files: with no host running it opens SQLite read-only and immutable, and when a write-ahead log is waiting it skips opening rather than apply it.
  - Service-file text: a systemd user unit and a launchd plist for the exact loopback `serve` command, with arguments quoted for systemd and the plist produced by `plistlib`. `RunAtLoad` is off in the plist. Writing to a file uses a new private file only and refuses `Library/LaunchAgents`, `Library/LaunchDaemons`, `.config/systemd`, any folder named `systemd` and the system service folders, so writing never installs.
- `alfred/desk.py`: `serve` calls `begin`, `reconcile` and records the report, prints one line of counts, handles SIGTERM as a clean stop (service managers stop with SIGTERM), and marks a clean stop only after the supervisor, job worker and listener stopped cleanly. If the job worker is still running a job when the host stops, the stop is not marked clean. New commands `doctor [--json]` and `service-file [--service launchd|systemd] [--output FILE]`; neither creates the data directory.
- `alfred/jobs.py`: `JobCoordinator.settle_host_restart` (additive). `start_local_jobs` halt now reports whether the worker thread stopped.
- `alfred/conversation.py`: one line adding the visible reason for interrupted turns.
- `alfred/console_api.py` and `console/src/components/HealthPanel.tsx`: host health now includes `recovery` (previous stop, last clean stop, questions interrupted, jobs needing reconciliation, jobs returned to the queue, routine slots missed). Counts only, so readers see it too. Absent when the server was not started by `serve`.

## Tests

- `tests/test_recovery.py`: 18 tests. Marker transitions and refusal to trust unreadable or symlinked markers; reconciliation of a started job, an unstarted lease, another worker's lease, a queued job and a queued question, idempotence, reader refusal and owner reconciliation afterwards; missed routine slots counted without a run; health for owner and reader; doctor on fresh, unclean, leftover-WAL, old-backup, wrong-permission, Git-tree and missing directories, and that it creates nothing; service-file quoting, plist parsing, refusal of control characters and of loading folders, and the CLI.
- Real process kill (`RealHostKillTests`): starts `python3 -m alfred.desk serve` in its own session, submits a 120-second `wait` job that the host's worker starts, leaves a queued question, kills the whole process group with SIGKILL, restarts, and checks: the start line reports an unclean stop with 1 interrupted question and 1 job needing reconciliation; the job is `effect_unknown` and stays so across worker cycles; the turn is `interrupted` with its reason; `/desk/console/health` over HTTP reports the recovery. Then SIGTERM exits 0, the marker records a clean stop and the last recovery, and the next start reports a clean previous stop; doctor then reports `last_stop` and `wal` as ok.
- Full backend suite: `python3 -m unittest discover -s tests`, 1131 tests, OK (334 s), on the tree of `4b38c4438` before its jobs.py docstring note; recovery, jobs, jobs HTTP, conversation and console API suites (140 tests) rerun on `4b38c4438` itself, OK.
- Console: `npm ci && npm run build && npm test`, build OK, 13 files and 143 tests passed.
- Browser: new `tools/check_recovery_browser.py`, 9 checks passed (report in `browser-report.json` here). The existing `tools/check_console_connected_browser.py` passed 99 checks with its output written outside the repository, so the shared console evidence file is unchanged.

## Limits

- The question in the real kill test is a queued row written beside the live host, which is the state a killed host leaves; a model-backed question was not killed mid-inference (no model is configured in tests). The job kill is a real mid-run SIGKILL.
- A job subprocess that outlives a killed host is not found or stopped by the next start; that is why started jobs are reported as effect unknown. The test kills the whole process group.
- A clean stop needs the foreground process to receive Ctrl+C or SIGTERM. SIGKILL, power loss and a second interrupt during shutdown are reported as unclean on the next start.
- Doctor reports; it never repairs, checkpoints or moves files. With a write-ahead log waiting and no host running it skips the integrity check and backup age.
- Service files are generated text only. ALFRED does not install, load, enable or start them, and they were not exercised under launchd or systemd here. The unit and plist keep the 127.0.0.1 listener; nothing widens the Host/Origin/CSRF boundary.
- Offline-first operation (the rest of RUN-001) is not part of this item.
