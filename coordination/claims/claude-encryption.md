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
  - requirements/
  - tests/test_keys*.py
  - tests/test_encryption*.py
  - tests/test_recovery.py
  - docs/ENCRYPTION.md
  - docs/MEMORY_SECURITY.md
  - docs/SECURITY_AND_DATA.md
  - docs/evidence/encryption/
---

Built by Claude in the "Encryption with both unlock options" project thread: step 1 (keys and
unlocking) is PR #26; step 2 seals the stored records. The storage, search and export modules
are listed because sealing reaches them. Astra stays out of them.
