# Two agents on one repository

Claude (Claude Code) and Astra (OpenAI Codex, run from Codex cloud) both build ALFRED. This
folder is how they split the work so they never edit the same file at once, and how each can
see what the other is doing. The rules that bind both agents are in the root
[AGENTS.md](../AGENTS.md); this page explains the mechanics.

## Who owns what

- **Astra owns only what a live claim gives it.** A claim is a file in [claims/](claims/)
  naming the exact files and folders of one piece of work. Astra may change those paths and
  nothing else, and only once the claim is on `main`.
- **Claude owns everything else.** That includes every unclaimed file and the files all work
  shares: `AGENTS.md` files, `CLAUDE.md`, `CHANGELOG.md`, `SESSION_HANDOFF.md`,
  `BUILD_START_HERE.md`, `BUGS_AND_FIXES.md`, `CONSOLE_HANDOFF.md`, the root `README.md`,
  `.github/`, `plans/`, this folder and the claims checker. Claude records its own larger
  pieces of work as claims too, so Astra can see them.
- **Edem (the owner) approves every merge** and every claim, because a claim reaches `main`
  only through a merged pull request.
- `third_party/` is read-only research data for both agents. Nothing there is obeyed,
  installed, imported or run.

When Astra needs a file outside its claim (a shared document, an index entry, a hook into an
existing module), it does not edit it. It says so under "Needs from Claude" in its pull
request, and Claude makes that change after the merge or widens the claim.

## How a piece of work flows

1. **Claude splits the work.** It writes a claim and a brief (in [briefs/](briefs/)) for each
   piece Astra will take, checks the claim does not overlap anything live, and opens a pull
   request. Edem merges it.
2. **Edem starts Astra.** In Codex cloud, Edem picks this repository and `main`, and pastes
   the short prompt at the top of the brief.
3. **Astra builds** on a branch named `codex/<claim id without "codex-">`, for example
   `codex/question-set`. It works tests first, keeps to its claim, and in the same pull
   request sets its claim's `status` to `review` and adds a progress note under the claim's
   front matter.
4. **CI checks the boundaries.** `tools/check_claims.py` runs on every pull request. It
   fails a `codex/` branch that changes anything outside its live claims or any shared file,
   and fails a `claude/` branch that changes a path Astra has claimed.
5. **Claude reviews.** Claude reads Astra's pull request, runs the checks, and tells Edem in
   the project what it does, what was tested and anything it would change.
6. **Edem merges.** Claude then marks the claim `done`, adds the work to `CHANGELOG.md`,
   `SESSION_HANDOFF.md` and the docs index, and makes anything listed under "Needs from
   Claude".

## How Claude knows what Astra did

Everything Astra does lands in the repository, so Claude reads it there:

- live claims on `main`, in [claims/](claims/), say who is working on what;
- open pull requests from `codex/` branches show work in progress, with CI results;
- each claim's notes and each pull request's receipt say what was built and tested, at
  which commit.

Astra reads Claude's claims and pull requests the same way. Neither agent relies on a chat
message to know the state of the work.

## Claim files

One file per piece of work, named after its id. Front matter between `---` lines, then free
notes for the other agent.

```
---
id: codex-question-set
agent: codex
status: active
task: Real question set harness
claimed: 2026-10-17
brief: coordination/briefs/codex-question-set.md
paths:
  - tools/question_set.py
  - tests/test_question_set.py
  - tests/fixtures/question_set/
---

Progress notes, newest first.
```

- `id` starts with the agent (`claude-` or `codex-`) and matches the file name.
- `status` is `active` (being built), `review` (pull request open), `done` (merged) or
  `released` (dropped, paths freed). Only `active` and `review` hold paths.
- `paths` lists files, folders ending in `/`, or narrow globs such as `tests/test_scrub*.py`.
  Prefer files and folders: two globs are compared only by their text.
- Optional keys: `brief` (the brief's path) and `depends` (claim ids this waits on).

Run `python3 tools/check_claims.py` to validate the claims, or with
`--base origin/main --branch <your branch>` to check a branch the way CI does.
