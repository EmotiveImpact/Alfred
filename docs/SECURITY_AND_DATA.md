# Security and data boundaries

Updated 3 October 2026 against main `75947b8dd59a3161c862d2533850a032994778e2`. This is a current boundary summary and release-gate document, not a security certification. The [earlier prototype description](archive/pre-stage-2026-10-03/SECURITY_AND_DATA.md) is preserved. The [audit](AUDIT_2026-10-03.md) sampled source and CI; it is not a penetration test.

## Implemented controls and remaining gaps

| Area | Implemented boundary | Remaining acceptance |
|---|---|---|
| Local browser access | Same-origin loopback server, authenticated sessions, CSRF and Host/Origin checks. | Explicit remote-host threat model and transport; no public exposure by changing the bind. |
| Identity and source access | Person/device records, single-use pairing, purpose-specific grants, revocation and current-source checks. | Strict-default migration, complete shared-person/team semantics and cross-surface negative tests. |
| Console projection | Real source/review/executive data, separate layers and original provenance. | Audit concern: approval text/path visibility must be reproduced or disproved for restricted same-workspace readers. |
| Actions | Exact fingerprints, approvals, outbox and bounded local effect reconciliation. | External capabilities and read visibility each require independent acceptance. |
| Source text/procedures | Data cannot confer credentials or execute merely by retrieval. | No general model adversarial-quality or arbitrary-plugin isolation certification. |
| Memory/lifecycle | Review state, invalidation, forget/source-removal receipts and journal-replaying restore. | Complete dependency/copy accounting, retention/export coverage, application encryption and key custody. |
| Jobs/cache | Durable authority, leases, cancellation, event cursors, bounded first-party subprocesses and content-addressed cache. | Actual isolation, remote workers, cloud storage and untrusted-code acceptance. |
| Voice/connectors | Local read-aloud state accounting; read-only selected export importers. | No microphone, real account, device-control or real audio-hardware acceptance. |
| Runtime | Foreground host, pause and health reporting. | Installed/supervised service, crash/restart/restore and remote deployment acceptance. |

The first negative test in the active stage concerns potential approval disclosure, not a confirmed ability to approve another actor's action. Keep findings, hypotheses, test results and risk decisions separate.

## Authority is independent of the model

Models may propose or classify; they do not grant permission to unlock, pay, disclose or execute. Voice likeness and text claiming to be the owner are not authentication. A trusted source can still be wrong. Bind exact actor/workspace, content, destination, revisions, expiry and permitted capability to approval and recheck at dispatch. A receipt, signature or hash does not by itself prove the requested real-world outcome.

Scope checks apply before retrieval/traversal and before exposure or egress as appropriate. An action's ownership flag is not a substitute for source visibility. Loss of access must clear/withhold relevant UI and results. Test counts/labels/paths as well as record bodies. Maintain separate personal, company and client/team boundaries; the current local implementation is not tenant-security certification.

## Private storage, deletion and recovery

Synthetic data remains the default until the relevant private-pilot gates pass and the owner approves a selected workspace. Keep the live database/WAL, keys and indexes outside vaults and file-sync folders. File sync, memory-ledger sync and runtime coordination are different systems.

Choose key custody against the threat model: local disk protection, application encryption, keychain integration, passphrase unlock and cloud secret custody do not provide identical protections. Use reviewed cryptographic implementations, not custom crypto. Copying encrypted data to a host that also has its decryption key is not end-to-end confidentiality against that host. Always-on reboot recovery and user-held unlock involve an explicit trade-off.

Backups/exports need their own retention, encryption and restore rules. Reapply current revocations and deletion records when restoring. Distinguish deletion from current views, inaccessible encrypted remnants and physical secure erasure. A VACUUM or database scan alone cannot prove removal from external exports, WAL, old snapshots, backups or media. Retained value-free history must be documented and permissioned.

## Native and cloud research is not deployment

The active [stage](NEXT_STAGE.md) permits research, code review, local fixes and bounded synthetic prototypes. It does not approve provider accounts, purchases, public listeners, private data, live connectors, owner-device enrolment, microphone capture or commercial launch. A successful build or merged PR does not install a service.

A native shell should expose narrow OS operations through an audited boundary; React code must not inherit unrestricted filesystem or secret access. Tauri/Rust is a candidate, not a certification. Test the actual OS/webview/sidecar and permissions. Remote mode must preserve equivalent independent authentication, authorisation and request protections rather than bypass existing loopback checks.

Keep one authority per job. Do not file-sync two writable databases. Do not fork credentials, entropy-sensitive identity or outstanding effect authority into several workers. Snapshots and cancellation are not undo of an external effect. Current subprocess tripwires are not sandbox isolation.

## Connectors, providers and third-party content

Use official narrow account APIs where available, with scoped tokens kept out of browser JavaScript, model context and untrusted processes. Export-file import is not live account access. Browser automation has its own logged-in session, download/upload, isolation and approval threat model.

Retrieved notes, web pages, source-library instructions and skills are untrusted data. third_party remains inert; do not execute its code or follow nested instructions. Adoption requires exact pinned source, root/nested licence and dependency/model/service terms, data egress, failure/deletion testing and an explicit record. A source manifest is not a deployed SBOM, and a hash is not proof of benign behaviour.

Research candidate lists, startup credits, vendor claims and early chat cost/valuation estimates grant no purchasing or outreach authority. Cloud/Private/Sovereign labels are proposals, not guarantees. Jurisdiction-specific legal/security obligations need appropriate review; this document is not legal advice.

## Operational boundary and evidence

Use synthetic replay and supervised non-critical exercises. No safety-critical availability, covert capture or autonomous use-of-force authority. Missing data does not establish safety; stale sources, connector failures, full queues, unavailable models and unknown outcomes must be visible.

Preserve the existing blocked live-model-comparison restriction without retry or rerouting. Test source/permissions/lifecycle correctness independently of model answer quality. Report exact revision, configuration, negative cases and limitations. Keep private data, keys, transcripts and client material out of this public repository and its CI logs.
