# Validation: local core v0.2

Date: 25 September 2026. Tests for this increment were executed on GitHub Actions, not
locally in the chat container. Public upstream source was copied as inert data only.
No external model/account/device service or upstream package was installed or executed.

## Verified first implementation checkpoint

Commit: `1a0f7b4caee30222d791ea691fbc9f2cd4310f60`.
Tree: `fe38e9ee2c4a9d69363da21aabd81b461a96e759`.
Run: https://github.com/EmotiveImpact/Alfred/actions/runs/36193034829
Job: https://github.com/EmotiveImpact/Alfred/actions/runs/36193034829/job/108262413196

Actual log: Python 3.12.3 on Ubuntu, **146 tests passed**, both demos completed, original
1,946 source files and new 127 files verified. No skipped tests were reported. This count
includes the previous 60 checks plus 57 local-service, 17 real HTTP and 12 Jev-contract tests.
The final documentation/hardening commit adds two malformed/inconsistent Jev response tests;
its result must be checked in the current head's CI rather than inferred from this checkpoint.

## Concrete exercised behaviours

- Real SQLite persistence across reopening and a separate child process using os._exit(17)
  after a committed local effect. This is process-death testing, not power-loss testing.
- Eight concurrent workers contend for one queued action and create one local draft row.
- Approval/outbox transaction failure injection rolls back both approval state and audit.
- Revoked/expired credentials are rejected; original authority is checked at claim and
  immediately before the effect. Scope/actor comes from a credential lookup, not a request.
- Source-only ingress, owner-only proposals/actions, reader-only access, and cross-workspace
  content/action checks under the tested local application model.
- Exact immutable proposal hashes; changed parameters invalidate approval; cancellation
  cannot pretend to undo an effect; a fabricated completion without a stored result fails.
- Crash before an effect leaves uncertainty without automatic resend. Crash after an effect
  can reconcile the existing draft by actual content/hash read-back.
- Persisted duplicate/collision, out-of-order/future/expired event handling; derived data
  does not displace reported evidence in the current-state ordering key.
- Real loopback socket HTTP tests cover the draft flow, revocation without restart, invalid
  auth, role denial, Host/Origin checks, bounded body size, JSON/content validation and
  absence of public provisioning/arbitrary-execution endpoints.
- Jev fixtures exercise typed request/response handling and advisory-only output. No live
  Jev API call, classification-quality result, latency or cost measurement exists here.

## Exact meaning of the successful effect

A real row was inserted into ALFRED's local drafts table and its content read back with
its expected SHA-256 hash. The proof labels this `local_sqlite_draft_readback` and `sent:false`.
No email/message was sent, no remote draft was created and no physical device was verified.
The earlier in-memory demo remains explicitly simulated; it is not this persistent service.

## Source verification

Import run: https://github.com/EmotiveImpact/Alfred/actions/runs/36192336632
Observed retained counts: TypeSafe SDK 30, QwenPaw 53, OpenSandbox 44. Zero current failures.
Together with the prior archive: 2,073 exact retained source/text files from eight pins.
The extension verifier checks lock membership, commit/licence hashes, exact paths and
per-file SHA-256/Git hashes. This is byte/provenance verification, not a security audit or
blanket licence clearance. No copied source becomes an active runtime dependency.

## Limits not hidden by the test count

The server is a loopback-only standard-library development server without TLS, a graphical
client, production load handling or mature denial-of-service protection. Browser-origin
access is deliberately disabled. Credential IDs currently stand in for principals; device
pairing, key rotation, recovery and richer grants are not implemented. The SQLite database
is not encrypted by ALFRED and a local administrator can modify it. The audit log is not
tamper-proof. No separate hostile-runtime sandbox has been deployed.

Only one fixed capability exists. External idempotency, connector receipts and verification
need separate implementation. Worker execution is explicit, not an always-on autonomous
scheduler. Retention/deletion/export, complete pagination, source corrections and broader
health monitoring remain roadmap items. No cross-platform, voice, battery, human attention,
privacy/legal, mission-critical or real-world task-success evaluation is established.

The instruction-text test contains no model and therefore is not a prompt-injection defence
benchmark. Jev's cloud flag only gates an offline payload builder, not a deployed egress
service. Any live reasoning or connector integration must preserve these distinctions.

## Reproduction

```sh
python3 -m unittest discover -s tests -v
python3 -m alfred.demo
python3 -m alfred.run demo
python3 tools/import_sources.py --verify
python3 tools/extend_sources.py --verify
```

The authoritative result for a later commit is its actual CI run. Do not state all tests
passed merely because a workflow file exists or an earlier commit passed.
