# INT-002 receipt: what supports each answer

2 October 2026, branch `claude/alfred-development-qpgxhg`. Status: **partial**. The commit that
adds this receipt is the tested source; unified CI on that commit is the independent rerun.
Source mode only: no model, provider or network was used, and the blocked live-model
comparison was not run or rerouted.

## What exists

Every answer from the conversation queue now carries a support report
(`alfred/answer_support.py`), stored with the answer and shown in the console as "What
supports this answer":

- which of the current question's own words were found in the excerpts and reviewed
  statements about to be shown (a shown word starting with the asked word), and which were
  not found;
- how many excerpts, from how many notes, and how they were retrieved;
- reviewed statements used, and reviewed statements about the subjects asked about that were
  withheld, counted by reason (conflicting, disputed, support unavailable, needing a fresh
  review, outside their valid period, awaiting review), never with their values;
- sources skipped because they changed or were unavailable, earlier questions that shaped a
  follow-up, and whether a selected record narrowed retrieval;
- whether a model was used and what its existing literal review found.

The report says what it is: word coverage and counts, not truth, entailment or
completeness. It never changes what the answer contains.

## Evaluation with denominators

`tools/evaluate_answers.py` asks 12 fixed, invented questions through the real conversation
queue over a fixed, invented vault with reviewed statements, then scores each support report
against the expectation written in the tool. Expectations are applied only after every
answer exists. Results: [report.json](report.json).

| Category | Cases | Passed |
|---|---|---|
| found | 2 | 2 |
| missing | 2 | 2 |
| conflict | 1 | 1 |
| disputed | 1 | 1 |
| changed (fresh review needed) | 1 | 1 |
| valid time | 1 | 1 |
| access (a restricted source never leaks) | 1 | 1 |
| context (follow-ups) | 2 | 2 |
| limitation | 1 | 1 |
| **Total** | **12** | **12** |

Across the 12 questions, 27 words were asked, 14 found and 13 not found.

**Failed cases on the first run, now fixed.** The first version of the report failed 2 of
the 12 cases, and both were real defects:

1. "When does Harbour open?" reported "open" as not found although the note says "opens"
   and retrieval had found that note. Coverage now accepts a shown word that starts with the
   asked word, close to retrieval's own matching without matching inside other words.
2. "What is the Atlas status?" counted a withheld statement about a different project
   because its predicate was also "status". Withheld statements now count only when the
   question names their subject.

Both have regression tests in `tests/test_answer_support.py`.

**Published limitation.** "How much does Atlas cost?" reports "cost" as not found although
the note gives a price: a different word is a different word to these checks. That is
correct for literal coverage and would mislead if read as understanding.

## Commands and results

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests` | passes, including `tests/test_answer_support.py` (7) and `tests/test_answer_evaluation.py` (1) |
| `python3 tools/evaluate_answers.py --output docs/evidence/int-002/report.json` | 12 of 12 cases pass |
| `cd console && npm run build && npm test` | build passes; 110 unit tests, including `tests/answer-support.test.ts` (4) |
| `tools/check_console_connected_browser.py` | 94 checks pass, including the support block on a real answer and a word the sources do not contain ([screenshot](../console-connected/connected-answer-support.png)) |

## Not done

- No semantic evaluation of model answers. The live-model comparison remains blocked and
  unchanged; model answers get only the existing literal review plus this accounting.
- Contradictions inside note text are not detected; only conflicting reviewed statements are.
- Paraphrase, synonyms and translation are not recognised.
- The fixed suite is small and invented. It measures whether the report is honest about
  these cases, not answer quality on real notes.
