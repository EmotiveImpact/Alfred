# Changelog entry for plan item 1.2

- **Strict grants by default (SYS-001, MEM-009, M02).** New workspaces grant no source to anyone until the owner grants it (demo `init` grants its owner read and model explicitly); owners enrol people, list them and switch read or model per source over HTTP and in the console access panel, version-checked and journalled.
- **Review history per person.** Entities, statements, history and receipts belong to the person, so a paired device shows the same review history; each review still names the device that made it. [Receipt](docs/evidence/strict-grants/RECEIPT.md).

## Suggested register changes (for the integrating session)

- `SYS-001`: add `docs/evidence/strict-grants/RECEIPT.md` and `tests/test_policy_strict.py` to `acceptance_evidence`. Keep `implementation: partial`: one owner person per workspace, no verified identity, and multi-owner identity is gate 4.
- `MEM-009`: add the same evidence (strict default, mid-request withholding tests). Keep `partial` until M07 traversal and egress coverage is receipted.
- Mark plan item 1.2 done once merged.
