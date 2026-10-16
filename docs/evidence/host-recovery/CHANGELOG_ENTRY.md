# Changelog entry, README lines and register change for plan item 1.4

For the integrator to copy into the shared files. This branch does not edit them.

## CHANGELOG.md (two lines)

- Host restart and recovery (RUN-001, M09): `serve` records clean stops and, after an unclean one, marks waiting questions interrupted with a visible reason, reports started jobs as `effect_unknown` for reconciliation (never re-run), returns unstarted leases to the queue and counts routine slots missed; SIGTERM is a clean stop and console host health shows the previous stop and the counts.
- New read-only `doctor` (placement, permissions, WAL state, backup age, last stop, console build) and `service-file` (launchd plist or systemd user unit as text, never installed by ALFRED). Receipt: `docs/evidence/host-recovery/RECEIPT.md`.

## README.md run instructions

```
python3 -m alfred.desk doctor            # read-only checks of the data folder; changes nothing (--json for JSON)
python3 -m alfred.desk service-file      # prints a launchd plist (macOS) or systemd user unit; --service, --output FILE; ALFRED never installs it
```

## plans/requirement-register.json, RUN-001

Implementation stays `partial` (offline-first operation is still not built). Suggested changes:

- `acceptance_evidence`: add `tests/test_recovery.py` and `tools/check_recovery_browser.py`.
- `notes`: append "Restart recovery: a private clean-stop marker; interrupted questions, started jobs as effect_unknown, unstarted leases requeued and missed routine slots reported at start and in console host health. Read-only doctor. Service-file text for launchd and systemd user units, never installed by ALFRED."
