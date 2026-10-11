# ALFRED → LiveLens validation, 11 October 2026

Branch `feat/livelens-tools-2026-10-11`, based on ALFRED main
`75947b8dd59a3161c862d2533850a032994778e2`. LiveLens base
`92a19a26e358a70fe5e06ec31b96cbad16e83e13` plus the runtime files identified in
the transport receipt. These are working-tree checks; exact source SHA-256 values
in the receipts identify the tested code, and both suites assert source immutability
during their runs. Committing these same bytes does not imply deployment.

| Check | Result | Evidence |
|---|---|---|
| Complete ALFRED backend suite | 1128 passed; 0 failed/errors/skipped | [backend-receipt.json](backend-receipt.json) |
| Existing real Desk browser workflow | 33 passed; no uncaught errors | [desk-browser-report.json](desk-browser-report.json) |
| Existing real Knowledge browser workflow | 25 passed; no browser errors | [knowledge-browser-report.json](knowledge-browser-report.json) |
| Actual authenticated ALFRED transport + installed CLI to real LiveLens | 36 passed | [http-receipt.json](http-receipt.json) |
| Requirement register/self-tests | Consistent; 11 self-tests passed | `tools/check_requirement_register.py` |
| Memory/source plan/self-tests | Consistent; 12 self-tests passed | `tools/check_memory_plan.py` |
| Source-library unit checks | 21 passed | `tools/test_source_library.py` |
| Inert source-byte verification | 89788 library files; 1946 original files; 363 extension files verified | build/import/extend `--verify`; upstream code not executed |

The acceptance launched actual ALFRED DeskHTTP sessions and a real Node LiveLens
service on disposable loopback listeners. It installed private connection files
through the ordinary CLI, discovered tools and read actual fixture evidence. It
verified independent source/control grants, actor/workspace/session bounds,
Host/Origin/CSRF protection and live revocation. Exact approval dispatched one
six-second capture; three retained segments matched their SHA-256 receipts and
strict FFmpeg decoding independently confirmed 6000 ms. Service media-clock receipt
6023 ms includes codec framing. Duplicate approved dispatch created no second job.
Both fixture processes exited cleanly and private token/config/DB/media/CLI output
were removed.

The 15 new focused backend tests also cover expiry/configuration/policy binding,
revocation or pause immediately before the write, accepted-request timeout and
read-only reconciliation, conflicting job parameters, default collection revocation,
source renewal refusing revoked identities, custom-vault placement, and an actual
backup taken before source forgetting whose restore cannot resurrect action records.

Commands:

```sh
python3 -m unittest discover -s tests
python3 tools/check_requirement_register.py --self-test
python3 tools/check_requirement_register.py
python3 tools/check_memory_plan.py --self-test
python3 tools/check_memory_plan.py
python3 tools/test_source_library.py
python3 tools/build_source_library.py --verify
python3 tools/import_sources.py --verify
python3 tools/extend_sources.py --verify
python3 tools/check_livelens_http.py --livelens-root /workspace/tiktok-community-manager \
  --runtime-root /dev/shm/alfred-livelens-proof \
  --output /tmp/alfred-livelens-http-final-receipt.json
```

The cloud sandbox presents `.git` placement markers under its writable roots.
Approved narrowly scoped test commands placed disposable fixtures in `/dev/shm`
outside Git, and assigned `tempfile.tempdir` there for the unified/browser runners.
ALFRED's placement guard remained enabled. Browser scripts ran with Chromium
`/usr/bin/chromium` and their documented output variables directed to `/tmp`.
No new production dependency or source-library import was used.

The acceptance script's failed-placement regression also verified that a failed
rerun overwrites any prior green output with a failure status/run ID before launching
fixtures. Independent read-only policy/proof reviews found no material blocker.

Limits: fictional generated media only; no external LIVE account, model calls,
email, deployed service, automatic conversation tool invocation or production
scale/identity claim. Use [installation and tool commands](../../LIVELENS_INTEGRATION.md)
to configure a real operator-selected workspace. Existing private-data gates remain.
