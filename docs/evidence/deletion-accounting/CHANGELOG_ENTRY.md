# Changelog entry (for the integrator to paste)

- **Deletion and restore accounting (plan 1.3; MEM-010, MEM-013, M05).** Every forget receipt (statement, entity, whole source) now counts each kind of dependent before and after from one scan that the new `deletion-report` command and `GET /desk/deletion-report/{source|entity|statement}/{id}` also use; value-free history is kept by default with an explicit, journalled `purge_history`; `restore` reports what the journal removed again and writes replayed receipts; source removal now also removes connector rows and conflict copies.
- **Export format 2.** `export` adds `review-history.json` (states and times, never values) and `routines.json` (authored routine settings), and records each export in a value-free register beside the database so receipts and reports can name exports still on disk. Evidence: `docs/evidence/deletion-accounting/RECEIPT.md`, `tests/test_deletion_accounting.py`.

## Register

No status change is justified: MEM-010 and MEM-013 stay `partial`. Secure erasure,
application encryption (1.1), a console view of the report and acceptance on a real vault
are still missing. Add to `acceptance_evidence` of both MEM-010 and MEM-013:
`tests/test_deletion_accounting.py` and `docs/evidence/deletion-accounting/RECEIPT.md`.
