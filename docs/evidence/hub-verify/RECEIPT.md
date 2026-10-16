# Independent verification receipt (AGENT_HUB.md step H4)

16 October 2026. Branch `feat/hub-verify-2026-10-16`, started from `def198223` (main after the
strict grants work, which already contains the H1 brain plug). **Tested commit:
`db293e363d2e951540100dc11fff7ffc9f4e30a7` (the commit that adds this receipt changes no code).** Status: implemented on a
local branch against synthetic data only. Not pushed, not merged, not deployed, not reviewed by the
owner. The shared registers (CHANGELOG.md, BUGS_AND_FIXES.md, SESSION_HANDOFF.md, README.md, the
requirement register, the remaining build plan and docs/AGENT_HUB.md) were not edited, because the
H2 and H3 work is being built in parallel; a proposed changelog entry is in
[CHANGELOG_ENTRY.md](CHANGELOG_ENTRY.md).

No model runs anywhere in this work and nothing touches the network. Every brain in the tests is
the H1 `SyntheticBrain`, some with their bundle edited after they run (a scripted fixture, not a
model). Nothing under `third_party/` was read as code, imported, installed or executed.

## The rule this step protects

A worker's "done" is a claim. Before H4, a brain result that passed the H1 contract (literal
citations to sent excerpts, artefact hashes, tool allowlist, metered budget) was `accepted`, with
the basis `brain_claim_checked_for_citations_hashes_tools_budget_not_verified_true`. Nothing
checked that the work met the owner's own acceptance test. H4 adds that gate. As AGENTS.md
requires, a generated "done" statement, a valid citation or a provider's confidence is not
verified completion or factual entailment: the verifier never reads the brain's answer, work log,
artefacts or self-test output as a status, only as material to check.

## What exists

`alfred/verification.py` holds the whole step. Changes to `alfred/brain.py` are small and
additive (below).

### Declaring checks

A packet may carry `acceptance`, built by `BrainHub.build_packet` from the owner's request through
`verification.declare`, which fills defaults and numbers the checks `C1`, `C2`, and so on:

```json
{"version": 1, "declared_by": "owner", "ref": null,
 "checks": [{"id": "C1", "kind": "claims_cited", "refs": "excerpts", "min_words": 3}]}
```

`declared_by` is `owner` (with `ref` null) or `mandate` (with the mandate's ID as `ref`, for H2 to
use). `validate_acceptance` is strict: unknown kinds, extra or missing parameters, wrong numbering
and out-of-range values are refused, at most eight checks and 4096 bytes. A packet without
`acceptance` is exactly the H1 contract.

The brain is told the checks (they are in its packet copy) but cannot change them: the result
bundle has no field for checks (a bundle carrying one is refused by H1), and the verifier reads
the checks from the packet ALFRED recorded at submission, after checking its SHA-256 against the
`brain_tasks` record. A brain that deletes `acceptance` from its own copy changes nothing.

### Check kinds (version 1)

All deterministic. Each ends `passed`, `failed` (with per-check reasons, at most 20, flagged when
truncated) or `unverifiable`.

| Kind | Parameters (defaults) | What it checks |
|---|---|---|
| `claims_cited` | `refs` (`excerpts`, or `excerpts_or_learned`), `min_words` (3) | Every claim sentence in the answer (at least `min_words` words, or any digit) carries a `[E1]` style marker to a sent excerpt whose citation quote is literally in that excerpt. Rechecked independently of H1. An answer with no claim sentence is `unverifiable` (`no_claim_sentences`): a bare "Done." establishes nothing. |
| `numbers_cited` | `against` (`excerpt`, or `quote`), `targets` (`answer`; may add `artefacts`) | Every number in an answer sentence appears literally in the excerpts (or quotes) that sentence cites; a number in an uncited sentence fails. With `artefacts`, every number in an artefact must appear somewhere in the sent material. Reuses the number pattern of `alfred/evidence_review.py`. |
| `artefact_sections` | `artefact`, `sections`, `non_empty` (true) | A Markdown or plain-text artefact has each named ATX heading (outside fenced code, case and spacing ignored), and by default each has a non-blank, non-heading line before the next heading of the same or a higher level. |
| `artefact_fields` | `artefact`, `fields` (dotted paths), `non_empty` (true) | A JSON artefact (strict parse: duplicate keys and NaN refused) is an object with each field present and, by default, not null, blank, `[]` or `{}`. |
| `artefact_schema` | `artefact`, `schema` | A JSON artefact matches a schema in a strict subset of JSON Schema: `type`, `properties`, `required`, `additionalProperties` (boolean), `items`, `enum`, `minLength`, `maxLength`, `minimum`, `maximum`, `minItems`, `maxItems`, at most eight levels and 2048 bytes. Any other keyword (`pattern`, `$ref`, `anyOf`, `format` and so on) is refused at declaration, so no rule is silently ignored. Errors carry JSON-pointer paths. |
| `artefact_pattern` | `artefact`, `pattern` (at most 200 characters), `mode` (`search`, or `fullmatch`), `flags` (subset of `ims`) | The pattern must compile at declaration. Matching runs in a separate isolated Python process (`-I -S -B`, empty environment, its own session, 512 MiB address-space limit) with a wall-clock limit (2 seconds by default), so a pattern that backtracks badly on returned text is stopped and reported `unverifiable` (`pattern_timeout`). |
| `no_out_of_scope_content` | `targets` (`drafts`; may add `answer`, `artefacts`), `min_words` (8) | No run of `min_words` consecutive words in the brain's proposed action text (and, if chosen, its answer and artefacts) appears in a note the person may read, unless that run is also in the material sent for this task (excerpts, learned statements, instruction, goal). Reports the note and line, not the text. Notes listed but not readable during the check make it `unverifiable`. |
| `effect_readback` | none; needs autonomy 2 | Every proposal that became a pending action was executed and reads back exactly: the action's parameters equal ALFRED's proposal record and the returned bundle, the action is `verified` with a `local_sqlite_draft_readback` proof, and the stored draft's body and SHA-256 match. This repeats, read-only, the comparison the outbox makes before marking a local draft verified. Not yet executed, cancelled or blocked: `unverifiable` (`effect_not_executed`); `uncertain`: `unverifiable` (`effect_uncertain_reconcile_first`); no effect proposed: `failed`. |

A check that raises is `unverifiable` (`check_could_not_run`). Content checks on a result whose
bytes can no longer be read through `JobCoordinator.artefact` are `unverifiable`
(`result_not_available`): tested by withdrawing read permission on the source; a deleted source
note reaches the same path through the coordinator's existing lineage rule. Nothing that could not run ever
counts as passed.

### Result states

| State | Meaning |
|---|---|
| `returned` | The brain says it is done: its job succeeded and the bundle passed the H1 contract. Nothing has been verified. Also the state while some declared check could not run and none failed, and always when no check was declared. |
| `checked` | Every declared check passed in a run (at least one must be declared). A later run in which a check could not run does not undo it; a later failure does. |
| `failed_checks` | At least one check failed, with per-check reasons. Failure is sticky across runs: a later passing run cannot erase it. A bundle that H1 refused is `failed_checks`, reported as `C0 bundle_contract` with the H1 reason, and its declared checks as `unverifiable` (`bundle_refused`). |
| `acknowledged` | The owner accepted the result, bound to the SHA-256 of the exact run they saw, and over failed checks only with `accept_failures=True`. A later run that fails a check the owner did not accept ends the acknowledgement (audited as `verification.acknowledgement_lapsed`). |

Only `checked` and `acknowledged` count as verified (`verified: true`, `is_verified`). A stopped
job (failed, cancelled, over budget) never returned a result: `verify` refuses it
(`result_not_returned`) and views label it `not_returned`. Acknowledgement grants no authority:
every proposed draft still needs its own exact-fingerprint approval.

### Records

Schema version 1 in `verification_meta`, in the same SQLite database as the brain records:
`verification_runs` (one append-only row per run with the full report and its SHA-256; a trigger
refuses updates) and `verification_results` (current state, the sticky set of failed check IDs,
whether a complete pass has happened, run count, last run, and the acknowledgement). Both are
private to the person who submitted the task, as in H1; audit entries `verification.run_<outcome>`,
`verification.acknowledged` and `verification.acknowledgement_lapsed` go to the existing audit log.

### Gate on effects

`verification.holds_effects` is called by `brain.action_current`, which `KnowledgeStore.evidence_valid`
already consults at approval and again at dispatch. When the packet declared checks, a draft the
brain proposed at autonomy 2 cannot be approved until the checks have run once, and cannot be
approved or dispatched while any check has failed unless the owner acknowledged the result. A
failure found after approval (for example, a new note now matches a draft's text) blocks dispatch.
A `returned` result with a pending read-back is not held, because the read-back can only run after
the owner approves and the outbox executes. Packets without declared checks keep the H1 behaviour
exactly.

### Query for routing statistics (H3)

`verification.outcomes(store, bearer, brain=None)` (also `Verifier.outcomes`) returns, for the
caller's ingested results, one row each (`job`, `brain`, `task_id`, `contract`, `checks`, `state`,
`verified`, `acknowledged_over`, `runs`, times) and per-brain counts of `checked`,
`failed_checks`, `returned`, `not_returned`, `acknowledged` and `verified`. `checks` is what
ALFRED's checks established; `state` adds the owner's acknowledgement. Neither comes from a
brain's own claims (`brain_claims_counted: false`).

### Changes outside `alfred/verification.py`

| File | Change |
|---|---|
| `alfred/brain.py` | `OPTIONAL_PACKET_KEYS = {'acceptance'}`; `validate_packet` allows that one optional key and calls `verification.validate_acceptance`; `BrainHub.build_packet` accepts an optional `acceptance` in the request and builds it with `verification.declare`; `action_current` returns False when `verification.holds_effects` says so. 20 lines added, 3 replaced. |

## Tests

`tests/test_verification.py`, 36 tests, real SQLite, the real job coordinator and worker, and the
existing approval, outbox and read-back path:

- declaration: defaults and numbering, strict per-kind validation, owner or mandate only (a
  `brain` declarer is refused), read-back only at autonomy 2, the schema subset refusing `pattern`,
  `$ref`, `anyOf` and `format`, too-deep schemas, uncompilable patterns and bad flags, size limits,
  and an extra `verified_done` key in the acceptance or the packet;
- sentence splitting keeps trailing markers with their sentence and splits conservatively;
- an honest result meeting five declared checks is `checked`; with no declared checks a result
  stays `returned` until the owner acknowledges it;
- **a brain that writes "All work is complete and verified_done", adds "Self-test output: 12
  passed, 0 failed, confidence 0.99", a fake passing test log artefact and a "Self-test passed"
  work log line** is accepted by the H1 contract but stays `returned` and unverified; with an
  unrelated check it is `checked` exactly as the honest brain is (the claims neither help nor
  matter); under `claims_cited` and `numbers_cited` its claims fail as uncited sentences and
  unsupported numbers; a `verified_done` field in the bundle itself is refused by H1 and recorded
  as `failed_checks` (`C0 bundle_contract`), with nothing to acknowledge;
- **numeric hallucination**: the brain cites the budget excerpt with a valid literal quote but
  writes 1,520 for 1,250. H1 accepts it; `numbers_cited` fails it with
  `number_not_in_cited_text`. Also against quotes, in artefacts, and an uncited number;
- JSON fields and schema (passes, then empty and missing fields and five located schema errors),
  duplicate keys, missing artefacts; Markdown sections missing, empty, inside fenced code, and
  relaxed; patterns matching and not matching;
- `unverifiable` is never passed: a catastrophically backtracking pattern times out in its child
  process, a result made unreadable by withdrawing read permission, a check that crashes, an answer
  with no claim; each leaves the result unverified. A stopped job is `not_returned`;
- checks belong to ALFRED: a brain that strips `acceptance` from its packet copy is still checked
  against the recorded checks; a brain that adds checks to its bundle is refused; records are
  private to the submitter; runs cannot be updated; failure stays after the offending note is
  edited away;
- effects: a draft cannot be approved before declared checks run; a draft copying a sentence from
  a note outside the task scope (a synthetic medical appointment) fails `no_out_of_scope_content`
  with the note and line, both drafts are held with no outbox or draft rows, acknowledgement needs
  explicit acceptance of the failure and still leaves each draft needing exact approval; text
  quoted from the sent excerpt is not flagged; a failure found after approval blocks dispatch;
  read-back waits for execution and then passes; a tampered stored draft fails read-back and ends
  an earlier acknowledgement (with the audit trail); no proposed effect fails read-back; packets
  without checks keep H1 approval;
- acknowledgement binding: before any run, to an older run, malformed inputs, idempotence, and a
  later run with nothing new keeps it;
- routing query: per-brain counts across two brains (checked, failed, unverified, claimant,
  stopped, never verified) and the brain filter.

`tests/test_brain_plug.py` (46 tests) passes unchanged.

Full backend suite on the tested commit: `python3 -m unittest discover -s tests`: 1335 tests (1299 existing plus 36
new), OK, in 244 seconds on Linux (python3, real SQLite and real subprocesses).
The same command on the starting commit `def198223`: 1299 tests, OK, in 225 seconds.

## Limits

- **Deterministic rules, not truth.** A `checked` result meets the declared rules on the bytes the
  brain returned. It does not show that a cited sentence is true or follows from its excerpt (a
  sentence can carry a correct citation and still misstate it in words), that a section says
  anything useful, or that nothing else is wrong. Numbers are matched as literal tokens: "1,250"
  and "1250" differ (fails, never passes), and numbers written as words are not checked. Sentence
  splitting can split at an abbreviation (the fragment then counts as uncited and fails).
- **Out-of-scope content** is compared with the notes the person may read when the check runs, by
  runs of at least five (default eight) words. Shorter leaks, paraphrase, translation and content
  from places ALFRED cannot see (another workspace, a brain's own memory of other material) are not
  detected. A common phrase that happens to appear in an unrelated note can cause a false failure.
- **Read-back** covers local `message.draft` effects only, the only capability a brain may propose
  today. It does not cover vault writes or any external effect, none of which a brain can propose.
- **Patterns** run in a child process with a time and memory limit; that process is not a sandbox
  beyond the isolated interpreter flags and empty environment. A slow machine can turn a passing
  pattern into `unverifiable` (never into passed).
- **Declarer.** `declared_by: mandate` is recorded as given by the caller of `BrainHub.submit`
  (always the owner's credential); no mandate record exists yet to check the `ref` against (H2).
- **Not built:** HTTP routes and a console view for verification; automatic verification at ingest
  (callers run `Verifier.verify` after `BrainHub.ingest`, and the effect gate fails closed until
  they do); per-proposal rather than per-result holds; use of the outcomes by a routing or learning
  job (H3); a real brain (H5, H6).
