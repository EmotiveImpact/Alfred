# Brief for Astra: adoption credit check

**Paste into Codex cloud** (repository EmotiveImpact/Alfred, branch `main`):

> You are Astra, working on ALFRED alongside Claude. Read AGENTS.md and coordination/README.md,
> then build the task in coordination/briefs/codex-adoption-check.md. Your claim is
> coordination/claims/codex-adoption-check.md: change only the paths it lists, plus that
> claim file. Work on the branch codex/adoption-check and open a pull request to main when
> every check passes. Do not merge.

## Why this exists

The integration plan ("How borrowing code works") lets ALFRED adapt code from the research
shelf only with credit: a header naming the upstream project, path, commit and licence, plus
the notice that licence requires. No code has been adapted yet. This check makes sure that
when it is, the credit is complete and true.

## What to build

- `tools/check_adoptions.py` scans ALFRED's own source (`alfred/`, `tools/`, `web/`,
  `console/src/`), never `third_party/`, for files headed `Adapted from`. For each it
  requires: the upstream project, the exact path, the full commit, and the licence. It then
  checks them against the pinned manifests in `third_party/research-shelf/` and
  `third_party/library/` (read as data): the project is pinned at that commit, the path
  exists in that snapshot, and the licence matches what the manifest records. MIT needs the
  copyright notice; Apache-2.0 needs its notice and a statement of changes.
- Read the manifest format from the files themselves; do not guess it. Report each problem
  with the file and line.
- Today it should pass with nothing to check, and say so.

## How to work

- Tests first in `tests/test_check_adoptions.py`, with synthetic headers and synthetic
  manifests in `tests/fixtures/adoptions/`: a complete MIT header, a complete Apache header,
  and failures for a missing field, an unknown project, a wrong commit, a path absent from
  the snapshot, a licence mismatch and a missing notice.
- Standard library only. Nothing under `third_party/` is imported or run; manifests are read
  as JSON or text.
- Claude adds the CI step after the merge; do not edit `.github/`.
- Run `python3 -m unittest discover -s tests` and `python3 tools/check_claims.py --base
  origin/main --branch codex/adoption-check` before opening the pull request.

## Done when

Every case is pinned by a test, the check passes on `main`, and CI is green.
