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
  - alfred/memory_bin.py
  - alfred/conversation.py
  - alfred/executive.py
  - alfred/drafts.py
  - alfred/routines.py
  - alfred/voice.py
  - alfred/brain.py
  - alfred/learning.py
  - alfred/verification.py
  - alfred/hub_goals.py
  - alfred/jobs.py
  - alfred/seal_workspace.py
  - alfred/knowledge_check.py
  - tools/evaluate_retrieval.py
  - requirements/
  - tests/test_keys*.py
  - tests/test_encryption*.py
  - tests/test_recovery.py
  - tests/test_sealing.py
  - tests/test_sealing_memory.py
  - tests/test_sealing_records.py
  - tests/test_sealing_work.py
  - tests/test_sealing_switch_on.py
  - tests/test_export.py
  - tests/test_deletion_accounting.py
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
and the modules that read or write note rows; part 2 (reviewed memory, its bin and capture)
works in the same ones and in the bin. Part 3 seals conversations, executive records, drafts
and actions, so those modules, routines and read-aloud records are claimed with it; the
agent brain, learning, verification and goals are claimed for the readers of actions, drafts
and record titles part 3 changes in them, and part 4 works in them too. Part 4 seals jobs, their
results and cached copies, so the job coordinator is claimed with it. Any new code that reads a
table listed in `alfred/sealing.py` must open its rows (`store.opened`); the `sealed-suite` CI
job fails if it does not.

Part 5 switches sealing on: the conversion lives in `alfred/seal_workspace.py`, the knowledge
check unlocks a sealed workspace before reading it, and the export and deletion tests open
sealed exports. It also adds the `seal`, `rotate-area` and `open-export` commands and the start
refusal to `alfred/desk.py`, which stays Claude's and is not claimed, as with the hub host.
