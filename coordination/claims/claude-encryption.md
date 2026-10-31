---
id: claude-encryption
agent: claude
status: active
task: Encryption foundation, plan phase 1 (keys, unlock methods, sealed records, disk check)
claimed: 2026-10-17
paths:
  - alfred/keys.py
  - alfred/crypto/
  - alfred/placement.py
  - alfred/recovery.py
  - alfred/core.py
  - alfred/local.py
  - alfred/desk_store.py
  - alfred/knowledge.py
  - alfred/grounded.py
  - alfred/deletion.py
  - alfred/export.py
  - alfred/rebuild.py
  - alfred/sealing.py
  - alfred/connectors.py
  - alfred/sync_conflicts.py
  - alfred/lifecycle.py
  - alfred/policy.py
  - alfred/inbox.py
  - alfred/vault_append.py
  - alfred/reviewed_memory.py
  - alfred/capture_policies.py
  - tools/evaluate_retrieval.py
  - requirements/
  - tests/test_keys*.py
  - tests/test_encryption*.py
  - tests/test_recovery.py
  - tests/test_sealing.py
  - tests/sealed_suite.py
  - tests/stored_helpers.py
  - docs/ENCRYPTION.md
  - docs/MEMORY_SECURITY.md
  - docs/SECURITY_AND_DATA.md
  - docs/evidence/encryption/
---

Built by Claude in the "Encryption with both unlock options" project thread: step 1 (keys and
unlocking) is PR #26, merged 30 October 2026; step 2 seals the stored records. The storage, search and export modules
are listed because sealing reaches them. Astra stays out of them.

Step 2 part 1 (the sealing layer and vault notes) adds the sealing module, its test harness
and the modules that read or write note rows; part 2 (reviewed memory and capture) works in
the same ones. Conversations, executive records, drafts, jobs and the console API had small
reader changes in part 1 and are claimed only when parts 3 and 4 start. Any new code that
reads a table listed in `alfred/sealing.py` must open its rows (`store.opened`); the
`sealed-suite` CI job fails if it does not.
