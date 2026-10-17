# Brief for Astra: checks that run automatically when a result arrives

**Paste into Codex cloud** (repository EmotiveImpact/Alfred, branch `main`):

> You are Astra, working on ALFRED alongside Claude. Read AGENTS.md and coordination/README.md,
> then build the task in coordination/briefs/codex-hub-auto-verify.md. Your claim is
> coordination/claims/codex-hub-auto-verify.md: change only the paths it lists, plus that
> claim file. Work on the branch codex/hub-auto-verify and open a pull request to main when
> every check passes. Do not merge.

## Why this exists

ALFRED's agent hub (`docs/AGENT_HUB.md`) sends work to a brain, takes back a result and checks
it with the owner's acceptance checks (`alfred/verification.py`) before anything counts as
done. Today those checks run only when the owner presses "verify" (`GoalHub.verify_result`).
The hub design lists "checks run automatically when a result arrives" as still to do. This
task builds it, so a result is checked the moment the hub accounts for it, and the owner sees
an outcome instead of a button.

## What to build

1. **In `GoalHub._account`** (`alfred/hub_goals.py`), after a finished task's result is
   ingested with status `accepted`, run `self.verifier.verify(self.host, job_id)` once when
   the task's packet declares acceptance checks and no verification run exists yet.
   - A task with no declared checks is left alone: it stays "no checks", never "verified".
   - A refused or failed ingest is not verified.
   - A check that raises or cannot run gives `unverifiable`, as `Verifier` already does. An
     exception from the automatic run must never stop the supervisor cycle or block
     accounting of the other tasks: record it and carry on.
   - Never re-run automatically. Later runs stay owner-initiated through `verify_result`,
     with its `expected_runs` guard.
2. **Record who started the run.** Add an `initiated` field to each run (`automatic` or
   `owner`), stored additively the same way `hub_mandates.acceptance` was added, so existing
   databases keep working. Show it in `GoalHub.result()` and in the run history. Existing runs
   read as `owner`.
3. **Learning stays honest.** Daily learning (`alfred/learning.py`, not yours to edit) reads
   verification outcomes. Confirm with a test that an automatic run counts exactly like an
   owner-started one, and that a brain's own "done" still counts for nothing.
4. **Limits.** At most `ACCOUNT_PER_CYCLE` automatic runs per cycle (they already follow the
   accounting batch), and each run keeps the existing time limits inside `Verifier`.

## How to work

- Tests first, in `tests/test_hub_auto_verify.py`, using the synthetic brain and the helpers
  that `tests/test_hub_integrate.py` already uses: an accepted result with passing checks
  becomes `verified` with no owner action; with a failing check, `failed`; with no checks,
  untouched; a refused ingest is not verified; a crashing check is `unverifiable` and the
  cycle continues; a second cycle does not run again; an owner re-run afterwards still needs
  the right `expected_runs`; a database made before this change opens and reads old runs as
  `owner`; and the full existing hub test files still pass unchanged.
- Standard library only. Keep the style of `alfred/hub_goals.py`: compact, explicit, every
  refusal named.
- Do not change `alfred/brain.py`, `alfred/learning.py`, the web interface or the console. If
  you find you need to, stop and list it under "Needs from Claude".
- `docs/evidence/hub-auto-verify/RECEIPT.md`: the commit you tested, the commands and their
  results. Claude updates `docs/AGENT_HUB.md` after the merge.
- Run `python3 -m unittest discover -s tests` and `python3 tools/check_claims.py --base
  origin/main --branch codex/hub-auto-verify` before opening the pull request.

## Done when

A synthetic task with declared checks is verified by the next supervisor cycle without the
owner, every refusal and failure case above is pinned by a test, all existing tests pass, and
CI is green.
