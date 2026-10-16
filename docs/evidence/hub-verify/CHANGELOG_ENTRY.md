### Added: independent verification of brain results (AGENT_HUB.md step H4), 16 October 2026

Proposed entry for the lead to merge into CHANGELOG.md. Branch `feat/hub-verify-2026-10-16`.
Receipt: [docs/evidence/hub-verify/RECEIPT.md](RECEIPT.md).

- `alfred/verification.py`: acceptance checks declared in the task packet by the owner (or, later,
  a mandate), never by the brain, and run by ALFRED on the returned bytes: `claims_cited`,
  `numbers_cited`, `artefact_sections`, `artefact_fields`, `artefact_schema` (a strict JSON Schema
  subset that refuses keywords it cannot enforce), `artefact_pattern` (matched in a separate,
  time-limited Python process), `no_out_of_scope_content` and `effect_readback` (reads back the
  executed local draft through the same records the outbox verifies).
- Result states `returned`, `checked`, `failed_checks` and `acknowledged`. Only `checked` or the
  owner's acknowledgement, bound to the exact run they saw (and explicit over failed checks), count
  as verified. A check that cannot run is `unverifiable`, never passed. Failure is sticky. A
  brain's own completion, confidence or self-test claims are never read as status.
- Append-only verification runs and per-result state, private to the submitter, schema version 1.
- Gate: a draft a brain proposed under declared checks cannot be approved until the checks have
  run, and cannot be approved or dispatched while any check has failed without acknowledgement.
- `verification.outcomes` gives per-result and per-brain check outcomes for routing statistics
  (H3).
- `alfred/brain.py`: optional packet key `acceptance` (validated), accepted by
  `BrainHub.build_packet`; `action_current` consults the gate. Packets without checks are
  unchanged.
- `tests/test_verification.py` (36 tests), including a brain claiming `verified_done` with fake
  self-test output that is still not verified, and a numeric hallucination behind a valid literal
  citation that H1 accepts and H4 catches.
- Not built: HTTP routes and console view, automatic verification at ingest, use by a routing or
  learning job (H3), a real brain.
