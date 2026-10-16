### Added: the brain plug (AGENT_HUB.md step H1), 16 October 2026

Proposed entry for the lead to merge into CHANGELOG.md. Branch `feat/brain-plug-2026-10-16`.

- `alfred/brain.py`: the task packet and result bundle contracts (version 1) with strict
  validation; `BrainSpec`, `Brain` and `BrainRegistry` (per-brain locality, tools, scope classes,
  highest autonomy and token price); `BrainPolicy` (cloud brains refused for every scope class
  until the owner lists one, owner tool allowlist empty by default, autonomy 3 and 4 refused with
  `autonomy_requires_pilot_gates`); an ALFRED-owned `Meter` that stops a brain at the first step
  beyond its step, token, money or wall-clock budget; `BrainBackend`, a `WorkerBackend` for the
  existing job coordinator; `BrainHub` (packet building from the caller's own permitted notes and
  accepted reviewed statements, submission as a `brain_task` job, and ingestion that checks the
  bundle against the packet actually sent); and `SyntheticBrain`, a deterministic rule-based test
  brain. No model, no network.
- New job kind `brain_task` (capability `model`, side-effect free, never run by the local
  subprocess backend). `job_kinds.SUBPROCESS_KINDS` lists the kinds the subprocess may run; the
  desk's `local-host` worker now enrols only those.
- Autonomy 0 drops and reports proposed actions, 1 keeps them as drafts for the owner, 2 turns an
  allowed `message.draft` into a proposed action that needs the existing exact-fingerprint
  approval. Approval and dispatch recheck that the brain's result was accepted and that every
  excerpt it was given is still the same readable revision (`KnowledgeStore.evidence_valid`).
- Memory suggestions go to a brain review inbox as `suggested`, never accepted.
- `tests/test_brain_plug.py` (46 tests), including a prompt-injection fixture.
- Not built: HTTP routes and console view, a real brain adapter, goals and mandates (H2), the
  daily learning job (H3), independent verification (H4), autonomy 3 and 4.
