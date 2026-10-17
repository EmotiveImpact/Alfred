# Brief for Astra: the secret scrubber

**Paste into Codex cloud** (repository EmotiveImpact/Alfred, branch `main`):

> You are Astra, working on ALFRED alongside Claude. Read AGENTS.md and coordination/README.md,
> then build the task in coordination/briefs/codex-secret-scrubber.md. Your claim is
> coordination/claims/codex-secret-scrubber.md: change only the paths it lists, plus that
> claim file. Work on the branch codex/secret-scrubber and open a pull request to main when
> every check passes. Do not merge.

## Why this exists

ALFRED will save notes, learned items and task results, and send some of them to models.
Before anything is saved or sent, credentials pasted into a note or returned by a worker must
be found and blanked (integration plan phase 5, "secret scrubbing before anything is saved
or sent"). This task builds the scrubber as a standalone module. Claude wires it into the
save and send paths later, because those files sit next to the encryption work.

## What to build

1. **`alfred/scrub.py`**, pure functions:
   - `find_secrets(text)` returns findings, each with a `kind`, `start`, `end` and a short
     reason. A finding never holds the secret itself, and its `repr` must not show it.
   - `scrub(text)` returns the text with each secret replaced by `[redacted:<kind>]`, and the
     findings.
2. **What it catches**, at least: PEM private key blocks; cloud access key ids and secret
   keys; GitHub, Slack, Stripe, Google, OpenAI and Anthropic style tokens; JSON web tokens;
   `Authorization: Bearer` and `Basic` headers; URLs with a password in them; and
   `password=`, `secret:`, `api_key` style assignments with a value. Each kind has its own
   pattern and tests.
3. **What it must leave alone**: ordinary prose, Git commit hashes, SHA-256 digests (ALFRED
   stores these everywhere), UUIDs, ALFRED's own ids, version numbers, dates and Markdown
   links without passwords. Pin these with tests too.
4. **Bounded cost.** Patterns must not backtrack badly: a test runs `scrub` on 1 MB of
   adversarial input and requires it to finish within a second. Overlapping findings are
   merged so the output is stable.

## How to work

- Tests first in `tests/test_scrub.py`.
- **Never write a realistic-looking secret as a literal**, in tests or docs. This repository
  is public and GitHub blocks pushes that look like leaked keys. Build every fake token at
  run time from pieces, for example `'gh' + 'p_' + 'A' * 36`.
- Standard library only (`re`). Python 3.12 or later. Match the style of nearby modules such
  as `alfred/verification.py`.
- You may read the Hindsight project on the research shelf (`third_party/research-shelf/`)
  for ideas, but write your own code. Copying code from the shelf needs the owner's
  approval and is not part of this task.
- Do not import `alfred.scrub` from any existing module. Wiring is Claude's follow-up.
- `docs/SECRET_SCRUBBING.md`: what it catches, what it cannot (for example a password typed
  as plain words), and how it will be wired in. `docs/evidence/secret-scrubbing/RECEIPT.md`:
  the commit you tested, the commands and their results.
- Run `python3 -m unittest discover -s tests` and `python3 tools/check_claims.py --base
  origin/main --branch codex/secret-scrubber` before opening the pull request.

## Done when

Every kind is caught and every look-alike is left alone in tests, the 1 MB test passes, CI is
green, and the pull request lists under "Needs from Claude" where the scrubber should be
called.
