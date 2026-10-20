# Receipt: the provenance gate

Tested commit: `1b135d120` on branch `claude/project-thread-att046-provenance-gate`, from
`main` at `4cdd4d417`.

## What was built

- `alfred/provenance.py`: `label(packet, action)` gives each proposed action a label saying
  which places (email addresses, web addresses, domains, handles and phone numbers) came from
  the owner's own words, from a note excerpt or from nowhere, which excerpts the brain cited,
  and which excerpts it copied six or more words from. Pure functions; standard library only.
- `alfred/brain.py`: `BrainHub` takes `provenance_mode` (`enforce` by default, `watch` or
  `off`), labels proposals under autonomy 1 and 2, and under `enforce` refuses one steered
  by a note with `steered_by_untrusted_text` before `LocalCore.propose` is called. Labels
  are stored in a new `brain_proposals.provenance` column (added to older databases when
  they are opened), shown by `BrainHub.proposals`, counted in the result as
  `provenance: {mode, steered}`, and each steered proposal is written to the audit log.
- `docs/PROVENANCE_GATE.md`, rows in `docs/INDEX.md` and `coordination/BACKLOG.md` (C9),
  and a line in `docs/AGENT_HUB.md` beside fence test 4.

The packet and bundle contracts are unchanged (both still version 1).

## Checks run at the tested commit

| Check | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -p test_provenance_gate.py` | 30 tests, OK |
| `python3 -m unittest discover -s tests -p test_brain_plug.py` | 47 tests, OK |
| `python3 -m unittest discover -s tests` | 1,774 tests, OK |
| `python3 tools/check_claims.py --base origin/main --branch claude/project-thread-att046-provenance-gate` | claims ok |
| `python3 tools/egress_audit.py` | ok, 115 files, 0 warnings |
| `python3 tools/check_adoptions.py` | ok, nothing adopted |
| `python3 tools/check_public_hygiene.py` | ok, 137 findings all under reviewed exceptions, none stale |

The test file was written first and failed on the missing module before the module existed.

## One existing test changed on purpose

`tests/test_brain_plug.py` had `test_planted_instruction_as_a_draft_waits_for_exact_approval`:
a draft carrying an address planted in a note became a pending action. Under the new default
that draft is refused, so the test is now two:
`test_planted_instruction_as_a_draft_is_held_by_default` (refused, no action exists) and
`test_planted_instruction_as_a_draft_waits_for_exact_approval_when_only_watched`, which keeps
the old assertions under `watch`. Nothing was loosened: the old guarantee still holds in
`watch`, and `enforce` adds a stronger one.

## Adversarial inputs tried

`places()` ran on 30,000 to 50,000 character strings built to make the patterns backtrack
(one long word, thousands of dotted single letters, long digit runs, repeated `@`, a very
long web address). Each took under 0.03 seconds on this container.

## Not tested here

- Any real model. Only the deterministic synthetic brain and a scripted variant of it ran.
- Paraphrased or encoded addresses that no pattern sees. The guide says the gate is a
  tripwire, not proof, and exact approval stays the decision.

Synthetic data only. Every address in the tests is assembled from pieces at run time.
Paths the encryption thread claims (`coordination/claims/claude-encryption.md`) are untouched.
