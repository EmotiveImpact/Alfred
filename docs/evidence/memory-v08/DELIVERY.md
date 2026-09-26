# ALFRED v0.8 delivery receipt

26 September 2026. Three first-party jobs delivered without another shell redesign:
reviewed typed memory, limited model-answer evidence checks, and routine-history controls.

## Exact continuity

Branch: `feat/alfred-reviewed-memory-2026-09-26`.
Base: `e0a0ef973d20d3f60606423ab2035d9f9df9e68f` / conversation v0.7.
Final authored test input: `e8116955ffb97d067396459a72d3e86e2e1321bd`.
Verified application/evidence checkpoint: `f650666027934b44dbd632593912b290f7ffdb6c`.
Checkpoint tree: `f28fa06f95a806959f26258e398afb46dcebe667`.
This receipt is a documentation-only addition after packaging. Runtime source is unchanged.
Main was checked at `b0614d70ab6e26e8ed358e02ad8d0586ca514427`. No merge or deployment.

## Implemented, not only planned

Reviewed memory: explicit stable-ID entities and proposed relationships/value statements;
exact source line/revision/hash and quote hash; separate version-bound acceptance,
dispute, withdrawal and explicit supersession. Competing accepted single-valued statements
with overlapping validity remain visible and are excluded from the current graph. This
is a narrow structural conflict rule, not general semantic contradiction detection.

Source changes/deletion/revocation invalidate affected statements on reconciliation;
projected values are cleared and open source inspection is closed. Statement review never
grants tool permissions. The source note-reference graph remains separate. The user-created
reviewed graph is inspectable/exportable, but is not yet automatically inserted into model
context or automatically extracted by a model. Credential-private, not mature cross-device
person identity. Entity names/history remain subject to unfinished lifecycle work.

Evidence checks: canonical cited source text is checked for unsupported numeric literals
and missing recognisable monetary evidence in price/fee questions. Blocking findings withhold
the generated interpretation in both direct and queued conversation paths; rejected model
text is not saved as an accepted answer. Broad citations are flagged and exact duplicate
references removed. These are conservative heuristics, not semantic entailment, completeness,
negation/conflict resolution or factual correctness. Tests use explicit model doubles.

Pulse history: hosted owner previews the exact eligible deletion set, then confirms its
fingerprint. Keep the latest 64 detailed records, recent rate-window starts and in-flight
work. Older eligible report details are replaced by compact retry receipts, preserving
idempotency without changing schedules or resetting rate limits. Compact receipts remain
bounded at 65,536; this is not indefinite unattended retention or secure erasure of backups.

The provisional noir OS, conversation queue, source inspection, exact action approval and
local SQLite draft flow remain. Only local drafts and local report/review records can be
written. No external message, account, microphone, device, ENDSTATE or Noir integration.

## Verified acceptance

Final successful GitHub Actions run:
https://github.com/EmotiveImpact/Alfred/actions/runs/36265266991

- 554 first-party code tests on Python 3.12.3, Ubuntu.
- 171 real browser/backend checks: 33 Desk, 25 Knowledge, 23 source-question,
  35 OS/Pulse, 25 conversation and 30 reviewed-memory/retention checks.
- 14 standalone, fictional read-only preview checks.
- Both upstream archive verifiers passed: 1,946 + 127 exact retained files, unchanged.

The downloaded final developer package independently passed all 554 tests on Python 3.13.5.
All 151 PACKAGE_SHA256.json entries matched. All 82 source-receipt files matched both
SHA-256 and Git blob hashes. All 28 changed first-party source/doc files matched the local
final tested copies byte-for-byte. Browser screenshots are from real loopback HTTP/SQLite
with fictional notes; the offline preview is separately labelled and cannot mutate state.

The first full acceptance also passed. A later manual review found that re-reviewing a
replacement could clear its lineage, or replace the lineage a second time. Two added
negative tests reproduced those faults. The correction preserves the original replacement
ID, prevents overwriting it, and retains it through source invalidation. All three added
regression tests and full final acceptance pass. No assertion was waived.

## Artifact integrity

Final artifact ID: `10913328415`.
Artifact ZIP SHA-256: `3291e2e15a294fa6328964a16e820741d236ef03427ec3aa5c6e28d1154fbe86`.
Developer ZIP SHA-256: `0d60bb35920cdd74da1c195fd45874759393fe182409e200e4e044dbb7c89b75`.
Standalone preview SHA-256: `c36f3f11c1fdab948f658a28061a28ac1668b8099d1658dc78c5d4da84e9b643`.

Files are committed under `docs/previews/memory-v08/` and `docs/evidence/memory-v08/`.
The developer ZIP excludes upstream research quarantine, model weights and runtime data.
This final receipt is newer than that ZIP; the verified application source is the same.
The temporary first-party transport files were removed after acceptance. Normal source is
present at the checkpoint; a compressed transfer alone was not treated as finished delivery.

## What did not run

A tool safety check blocked the proposed new live-model-comparison workflow before its
files were published or its jobs started. That operation was not retried or rerouted.
No new model inference, model download, stronger-model benchmark or model-selection verdict
is claimed in v0.8. Prior v0.7 inference evidence and its documented failures remain.
The ordinary application/fixture/browser acceptance above is separate from that experiment.

## Remaining priorities

Deliberately connect reviewed memory to authorised retrieval with provenance and invalidation
preserved; mature person/device identity and source/capability grants; deletion/export and
encryption decisions; a qualified reasoning evaluation; one consented read-only account
connector, then low-risk approved effects and measured push-to-talk. Do not turn the model
into the authority system or flatten personal, work and client information boundaries.

The local host must stay running. No always-on service was installed, no live accounts or
private notes were accessed, and no operational-safety or autonomous use-of-force capability
is implied. Keep the existing personal OS ambition and the explicitly provisional look.
