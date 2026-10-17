# Brief for Astra: the real question set harness

**Paste into Codex cloud** (repository EmotiveImpact/Alfred, branch `main`):

> You are Astra, working on ALFRED alongside Claude. Read AGENTS.md and coordination/README.md,
> then build the task in coordination/briefs/codex-question-set.md. Your claim is
> coordination/claims/codex-question-set.md: change only the paths it lists, plus that claim
> file. Work on the branch codex/question-set and open a pull request to main when every
> check passes. Do not merge.

## Why this exists

ALFRED's next search and memory phases (plan phases 3 and 4 in
`research/INTEGRATION_PLAN_2026-10-17.md`) ship only if they beat today's search on a set of
questions the owner would really ask. This task builds the harness that holds those
questions and scores ALFRED against them. The owner writes the real questions later; they
stay on the owner's computer and never enter this public repository.

## What to build

1. **A question set format**, schema `alfred.question-set.v1`, as JSON. Each question has an
   `id`, a `category` (`fact`, `connected`, `time`, `preference` or `refuse`), the `question`
   text, `expect` (the note paths a good answer must bring up, at least one unless the
   category is `refuse`), optional `avoid` (note paths that must not come up, such as another
   area's notes) and an optional free `note`. Reject unknown fields, duplicate ids, empty
   text and `expect` on a `refuse` question.
2. **`tools/question_set.py`** with three commands:
   - `validate QUESTIONS` checks a file and prints a value-free summary (counts per category).
   - `run QUESTIONS --vault FOLDER [--ranking keywords|fts5|both] --output REPORT` builds a
     throwaway ALFRED store in a temporary folder from a Markdown vault, asks every question
     through `alfred.grounded.retrieve` and scores it. Follow the setup in
     `tools/evaluate_retrieval.py` (`KnowledgeStore`, `provision`, `MarkdownVault.scan`,
     `IdentityPolicy.grant`), which already does this for synthetic notes. Delete the
     temporary store when done, also on error.
   - `compare OLD NEW` prints the difference between two reports.
3. **Scores**, per category and overall: how many expected notes came up (recall within the
   returned sources), whether any `avoid` note came up (a leak, reported loudly), whether a
   `refuse` question returned nothing, and how many words of excerpt were returned (the plan
   judges later phases partly on "fewer words sent to the model"). Plain arithmetic, no model.
4. **Privacy guards.** `run` refuses a questions file, vault or output path inside the
   repository unless `--synthetic` is given, so real questions and results cannot be
   committed by accident. Nothing is sent over the network. Reports hold question ids and
   scores; question text appears only with `--include-text`.
5. **A synthetic example** in `tests/fixtures/question_set/`: an invented vault of about
   fifteen short notes (fictional people, projects and places, nothing real) and about
   twelve questions covering all five categories, including one deliberate leak case and one
   refusal.
6. **Docs.** `docs/QUESTION_SET.md` explains, in plain British English for the owner, how to
   write good questions, where to keep the file on their own computer and how to run it.
   `docs/evidence/question-set/RECEIPT.md` records the commit you tested, the commands you
   ran and their results.

## How to work

- Tests first in `tests/test_question_set.py`: format errors, path refusals, scoring on the
  fixture (exact expected numbers), leak detection, refusal scoring, a deterministic report
  (the same run twice gives byte-identical output), and clean-up of the temporary store.
- Standard library only. Python 3.12 or later. Match the style of `tools/evaluate_retrieval.py`.
- Run `python3 -m unittest discover -s tests` and `python3 tools/check_claims.py --base
  origin/main --branch codex/question-set` before opening the pull request.
- If you need anything outside your claim (for example a line in `docs/INDEX.md`), do not
  edit it. List it under "Needs from Claude" in the pull request.

## Done when

The fixture run gives the scores your tests pin, CI is green, and the pull request explains
what a reader would see, what was tested at which commit, and anything Claude must add.
