# Brief for Astra: public repository hygiene check

> **Paused for Astra.** The owner moved this work to Claude on 17 October 2026, and it is
> tracked in `coordination/BACKLOG.md`. No claim exists for it, so the paste prompt below is
> kept only as a record. Read the rest of this brief as the specification.

**Start only after the secret scrubber (`codex-secret-scrubber`) has merged.**

**Paste into Codex cloud** (repository EmotiveImpact/Alfred, branch `main`):

> You are Astra, working on ALFRED alongside Claude. Read AGENTS.md and coordination/README.md,
> then build the task in coordination/briefs/codex-public-hygiene.md. Your claim is
> coordination/claims/codex-public-hygiene.md: change only the paths it lists, plus that
> claim file. Work on the branch codex/public-hygiene and open a pull request to main when
> every check passes. Do not merge.

## Why this exists

This repository is public. Credentials, home-directory paths and personal email addresses
must never land in it. This check scans what is committed and fails before they do.

## What to build

- `tools/check_public_hygiene.py` scans every file Git tracks (`git ls-files`), skipping
  `third_party/` and binary files, for credential-shaped strings (reusing `alfred.scrub`
  patterns, not copying them), home-directory paths such as `/Users/<name>/` and
  `/home/<name>/`, and email addresses. It reports file, line and kind, never the matched
  value itself.
- `tools/public_hygiene_allowlist.json` holds reviewed exceptions, each with file, kind, a
  hash of the exact match and a reason (for example, `noreply@anthropic.com` in commit
  attribution text, or an invented address in a test). An entry that no longer matches fails
  the check.
- It must pass on today's `main`. Where it finds something real, do not edit the file; list
  it under "Needs from Claude".

## How to work

- Tests first in `tests/test_public_hygiene.py`, on a temporary Git repository with
  synthetic files. Build every fake credential at run time from pieces, never as a literal.
- Standard library plus `alfred.scrub` only.
- Claude adds the CI step after the merge; do not edit `.github/`.
- Run `python3 -m unittest discover -s tests` and `python3 tools/check_claims.py --base
  origin/main --branch codex/public-hygiene` before opening the pull request.

## Done when

The check passes on `main` with a reviewed allowlist, never prints a matched value, every
case is pinned by a test, and CI is green.
