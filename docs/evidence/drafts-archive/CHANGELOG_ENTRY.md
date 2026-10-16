# Changelog entry (for the integrator to merge into CHANGELOG.md)

- Drafts are kept (owner decision, 16 October 2026): a lapsed approval no longer makes a draft disappear; drafts are listed and searchable by text, date and status (lapsed, archived, withdrawn), can be archived and unarchived (version-checked, audited) and proposed again as a new action with a fresh fingerprint and rechecked sources, over `/desk/drafts` and a console "Find drafts" panel.
- Forgetting a source or reviewed statement now also withdraws kept, archived and re-proposed drafts that depend on it (text replaced, re-propose refused, `drafts_withdrawn` in the receipt).

## Suggested register change

- `ACT-001`: stays `partial`; add `docs/evidence/drafts-archive/RECEIPT.md` and `tests/test_drafts_archive.py` to `acceptance_evidence`; note "Drafts are kept after the approval window lapses; archive, search and re-propose with fresh approval and source recheck."
- `MEM-010`: stays `partial`; add the same receipt; note "Forget withdraws kept and archived drafts through retained value-free bindings."
- Decision 0.3 in `docs/REMAINING_BUILD_PLAN.md`: "re-offering expired drafts" is answered by the owner: keep and allow owner re-offer.
