# Changelog entry for plan item 1.5

- **Obsidian compatibility (1.5, MEM-001, MEM-002, M01):** the vault scanner now reads frontmatter alias and tag strings, inline and nested tags, `[[link|alias]]` display text, embeds, nested heading subpaths, paragraph and standalone block IDs, callouts and `%%` comments as Obsidian does; identical conflict copies from unrecognised tools are detected by content hash. [Receipt](docs/evidence/obsidian-compat/RECEIPT.md).
- **Approved `vault.append_section` (1.5, MEM-011, M04):** a second, separately granted vault write that inserts text under a named heading after approval of an exact diff, never appends twice, refuses on any concurrent edit and reads the result back.

## Requirement register (for the integrator; not edited here)

- MEM-001, MEM-002: keep `implementation: partial` (no Obsidian app acceptance or owner pilot yet); add `tests/test_obsidian_compat.py` and `docs/evidence/obsidian-compat/RECEIPT.md` to `acceptance_evidence`.
- MEM-011: keep `implemented_on_branch`; add `tests/test_vault_append.py` and the receipt to `acceptance_evidence`; note the second capability `vault.append_section` and the new grant `vault.append`.
- MEM-014: keep `partial`; add `tests/test_obsidian_compat.py` (content-hash conflict detection) to `acceptance_evidence`.
