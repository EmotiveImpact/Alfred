# Question set harness: receipt

17 October 2026. A tooling checkpoint, not a merge, deployment or job-state change.
`plans/` and the requirement register are deliberately unchanged.

## Tested code

Branch `claude/project-thread-att046-question-set`, started from main
`d81a5d509b09637437fe8721b486fcea4224c526`. Everything below was run at commit
`e99ed123cd6cede97fa4cc371c4f0210e5f177bf`, which holds all of the code, tests, fixture
and `docs/QUESTION_SET.md`. This receipt is committed afterwards, on top of that commit,
and changes no code.

Environment: Python 3.13.16, SQLite 3.45.1 with FTS5. Standard library only. No file
under `alfred/` changed, and nothing under `third_party/` was read, imported or run.

New files:

- `tools/question_set.py`: `validate`, `run` and `compare`.
- `tests/test_question_set.py`: 46 tests.
- `tests/fixtures/question_set/`: an invented vault of 15 notes (one project, two
  people, two meetings, one place, two clients with two notes each, three personal
  notes, two daily notes; 10 resolved wikilinks) and `questions.json` with 12 questions:
  fact 3, connected 3, time 2, preference 2, refuse 2. Everything in it is made up.
- `docs/QUESTION_SET.md`: the owner's guide.

## Commands and results

```
python3 -m unittest tests.test_question_set
```

`Ran 46 tests`, `OK`.

```
python3 -m unittest discover -s tests
```

`Ran 1473 tests in 257.536s`, `OK`.

```
python3 tools/question_set.py validate tests/fixtures/question_set/questions.json
```

Exit 0:

```
Valid alfred.question-set.v1 file with 12 questions:
  fact 3
  connected 3
  time 2
  preference 2
  refuse 2
```

```
python3 tools/question_set.py run tests/fixtures/question_set/questions.json --vault tests/fixtures/question_set/vault --ranking both --synthetic --output <scratch folder outside the repository>/receipt-1.json
```

Exit 3 (report written, leak found), as designed for the deliberate leak case:

```
Report written for 12 questions (vault: 15 notes, status ready).
keywords: recall 0.9286 (13 of 14 expected notes), complete 9/10, refused 1/2, leaks 1, passed 9/12, excerpt words 1311
fts5: recall 1.0 (14 of 14 expected notes), complete 10/10, refused 1/2, leaks 1, passed 10/12, excerpt words 1293
LEAK: fact-orrin-renewal brought up 2 notes it must avoid (keywords).
LEAK: fact-orrin-renewal brought up 2 notes it must avoid (fts5).
```

The same command run again to `receipt-2.json` also exited 3, and `cmp` found the two
reports byte-identical (SHA-256
`444cfeffa62230d4b8a0b46064d43da33455c8a842809882c2aa7a1c3638b8f5` on this machine; the
report records the SQLite version, so the hash is machine-specific).

```
python3 tools/question_set.py compare receipt-1.json receipt-1.json --old-ranking keywords --new-ranking fts5
```

Exit 0:

```
Comparing old keywords with new fts5.
vault notes: 15 -> 15
overall: recall 0.9286 -> 1.0 (+0.0714), complete 9/10 -> 10/10, refused 1/2 -> 1/2, leaks 1 -> 1, passed 9/12 -> 10/12, excerpt words 1311 -> 1293 (-18)
fact: recall 1.0 -> 1.0, complete 3/3 -> 3/3, leaks 1 -> 1, passed 2/3 -> 2/3, excerpt words 292 -> 292
connected: recall 0.8333 -> 1.0 (+0.1667), complete 2/3 -> 3/3, leaks 0 -> 0, passed 2/3 -> 3/3, excerpt words 452 -> 448 (-4)
time: recall 1.0 -> 1.0, complete 2/2 -> 2/2, leaks 0 -> 0, passed 2/2 -> 2/2, excerpt words 210 -> 228 (+18)
preference: recall 1.0 -> 1.0, complete 2/2 -> 2/2, leaks 0 -> 0, passed 2/2 -> 2/2, excerpt words 222 -> 190 (-32)
refuse: refused 1/2 -> 1/2, leaks 0 -> 0, passed 1/2 -> 1/2, excerpt words 135 -> 135
changed questions:
  connected-pilot-count: recall 0.5 -> 1.0
```

```
python3 tools/question_set.py run tests/fixtures/question_set/questions.json --vault tests/fixtures/question_set/vault --output <scratch>/receipt-3.json
```

Exit 1, nothing written:

```
error (questions_inside_repository): the questions file is inside the ALFRED repository; keep real questions outside it, or pass --synthetic for invented data.
```

```
git diff --check origin/main..HEAD
```

No output (clean).

```
python3 tools/check_claims.py --base origin/main --branch claude/project-thread-att046-question-set
```

Exit 1 with 19 errors, one per changed file, each `claimed by Astra in
codex-question-set`. This is expected: the paths were claimed for Astra, and this work
was done by Claude instead. The check passes only once Claude releases or reassigns that
claim in `coordination/`, which is outside this change.

## What the pinned scores show

| Ranking | Recall | Complete | Refused | Leaks (notes) | Passed | Sources | Excerpt words |
|---|---|---|---|---|---|---|---|
| keywords | 13/14 = 0.9286 | 9/10 | 1/2 | 1 (2) | 9/12 | 51 | 1311 |
| fts5 | 14/14 = 1.0 | 10/10 | 1/2 | 1 (2) | 10/12 | 50 | 1293 |

Per category, keywords then fts5: fact recall 1.0 and 1.0 (292 words each); connected
0.8333 and 1.0 (452 and 448); time 1.0 and 1.0 (210 and 228); preference 1.0 and 1.0
(222 and 190); refuse 1 of 2 refused under both (135 words each).

- The one keyword miss is `connected-pilot-count`, which does not bring up
  `people/nell-vantrick.md`; fts5 does.
- The deliberate leak, `fact-orrin-renewal`, brings up both Pellham Glassworks notes
  under both rankings. `fact-depot-hours` names an avoid note that does not come up, so
  it is not a leak.
- `refuse-telescope` brings up nothing and passes. `refuse-quarrow-office` brings up four
  unrelated notes through shared words such as "office" and fails.

These numbers describe lexical retrieval on fifteen invented notes. They are not a
quality claim, they say nothing about which ranking is better on real notes, and no
model, provider or network was used. The tests pin them so that any change to
retrieval shows up as a visible test change.

## What the tests cover

Every format refusal (unknown fields at top level and per question, duplicate JSON
fields, duplicate ids, empty and whitespace-only text, text ALFRED cannot ask, missing
`expect`, `expect` on a refuse question, wrong schema, wrong types, non-list fields, bad
categories, bad and duplicate note paths, overlaps between `expect` and `avoid`, size
limits); every path refusal (questions, vault and report inside the repository without
`--synthetic`, including through a symbolic link; the report replacing the questions
file directly, through a symbolic link or a hard link; the report inside the vault; an
existing file that is not a report; a folder or a missing folder as the report path);
refusals happening before any store is built; the vault left byte-for-byte unchanged;
exact scores for both rankings per question, per category and overall; byte-identical
reports across two runs; question text only with `--include-text`; no question text,
note reminders, excerpt text or machine paths in reports or messages; no network use;
the temporary store deleted after success, after a raised error, after a retrieval
refusal and after an unreadable vault; and exact `compare` output for hand-built and
fixture reports.

## Left for others

- **Claude:** release or reassign the `codex-question-set` claim so the claims check
  passes, and add `docs/QUESTION_SET.md` to `docs/INDEX.md` if wanted.
- **Owner:** write the real question set, keep it outside the repository, and run it as
  `docs/QUESTION_SET.md` describes. No real question or result belongs in this
  repository.
