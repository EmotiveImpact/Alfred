# ALFRED reviewed memory v0.8

26 September 2026. An additive first-party implementation over the v0.7 local service.
The personal OS shell remains provisional; this release does not restart its design.

## What is implemented

Memory now has two distinct views. **Source map** retains the authored Markdown-reference
graph. **Reviewed memory** holds explicitly created entities and source-backed statement
proposals. It does not infer a semantic relationship merely because two notes link.

Create a person, organisation, project, asset, decision, commitment or event with its own
stable ID. Identical display names stay separate. Propose a responsible-person relation,
a dependency or a textual status, scheduled time or decision. Select one indexed note,
its exact revision/hash and one to eight supporting lines. A proposal is not accepted
until a separate authenticated review, and acceptance records the user's judgement,
not independently established truth or any permission to act.

The API supports optional half-open validity intervals. The initial form creates an
unbounded interval; it does not silently guess dates. Names, time expressions and text
values are not entity resolution, calendar scheduling or model extraction.

## Review and conflict lifecycle

Proposed statements can be accepted, disputed or withdrawn. A new or disputed statement
can explicitly supersede a previously accepted/disputed/invalidated statement about the
same entity/predicate. Both versions and the replacement link are retained. A stale
review version is rejected. Exact source identity is rechecked in the transaction.

For the supported single-value predicates, accepted different values with overlapping
validity remain an explicit conflict. Neither is silently selected for the usable graph.
Dependencies are multi-value. This is deliberately bounded conflict detection, not a
general ontology: it cannot infer synonyms, mutually exclusive free-text meanings or
arbitrary temporal/causal contradictions.

The graph projection includes only accepted, currently valid, unconflicted entity
relationships with current indexed evidence. Textual claims remain in the statement
view. They are not automatically promoted into model prompts or operational authority.
No existing permissions or action ledger is rewritten by memory review.

## Provenance and correction

Each proposal binds a source-note ID, SHA-256, revision, exact line range and quote hash.
Quotes are reconstructed from the canonical index; they are not duplicated in the claim
store. An export includes the current source passage, its hash and review metadata.

Reconciliation occurs on memory reads/proposals/reviews. When the index reports changed,
removed, expired or revoked source material, the affected statement is invalidated and
its projected value/object reference is cleared. The UI polls while open and clears a
stale inspection/review modal. Source scanning must run to discover filesystem changes.
No instantaneous global invalidation or background secure-erasure claim is made.
Restoring the same file does not silently reinstate an invalidated statement.

Withdraw/supersede retain history. User-created entity names remain until a future
explicit entity-lifecycle feature. Indexed source removal, source-file deletion, memory
withdrawal and deletion of audit records are different operations.

## API and access boundary

Existing same-origin cookie sessions, CSRF/Host/Origin checks and server-side role/scope
resolution are retained. Memory is private to the creating credential AND workspace.
Another owner with the same workspace does not inherit it. A reader can inspect its
own projection but cannot create/review. Credential ownership is not yet mature person
or device identity; rotation/migration needs a separate design.

- GET /desk/memory and /desk/memory/export
- POST /desk/memory/entities
- POST /desk/memory/proposals
- POST /desk/memory/claims/{id}/review

128 entities and 256 claims per credential are hard bounds. At capacity, new writes fail
explicitly. There is no automatic pruning of reviewed memory or permanent-storage claim.
SQLite storage remains unencrypted at application level. Use synthetic data until the
identity, encryption, retention and deployment work has been separately accepted.

## Pulse history management

Pulse retains its two existing fixed routines. A new owner-only plan/confirm endpoint
removes eligible old report summaries while preserving compact retry receipts. It keeps
the latest 64 records, every start in the rolling 24 hours/current UTC day, and running
records. A fingerprint binds the exact eligible set. A changed plan requires review again.

Pruning cannot reset current rate-limit counters or repeat a retained manual request ID.
Schedules remain unchanged. The existing 512-detail-row cap still applies until eligible
records are deliberately pruned. Compact receipts are capped at 65,536 per hosted scope;
capacity is explicit, not an unlimited retention promise. Only the hosted owner can prune.

GET /desk/pulse/history previews; POST with its fingerprint confirms. This removes active
rows, not secure erasure of SQLite pages/WAL/backups or previously exported files. Completed
drafts/audit history are not undone. This does not install a continuously running service.

## Run and inspect

```sh
python3 -m alfred.desk init --data-dir ~/.local/share/alfred/os-v08-demo
python3 -m alfred.desk access --data-dir ~/.local/share/alfred/os-v08-demo
python3 -m alfred.desk serve --data-dir ~/.local/share/alfred/os-v08-demo
```

Keep the displayed key private. Open the loopback address on the same machine, then
Memory > Reviewed memory. Existing v0.7 data receives additive tables; source files are
not overwritten. The included preview is fictional/read-only and cannot mutate memory.
