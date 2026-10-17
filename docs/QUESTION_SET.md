# Your question set

ALFRED's later search and memory work only ships if it finds your notes better than
today's search does. To judge that fairly, we need questions you would really ask, with
the notes that hold each answer. This guide explains how to write that file, where to
keep it and how to score ALFRED against it.

The tool is `tools/question_set.py`. It runs on your own computer. It sends nothing over
the network and uses no AI model.

## What the scores tell you, and what they do not

The tool asks ALFRED's search each question and checks which notes came back. It counts:

- **recall**: how many of the notes you expected came up;
- **leaks**: whether a note you said must not come up did come up;
- **refusals**: whether a question your notes cannot answer brought up nothing;
- **excerpt words**: how many words of your notes were sent back. Fewer is better, as long
  as the right notes still come up.

These are simple counts. A note coming up does not prove it answers the question, and a
good score on your set is not proof that ALFRED is good in general. The scores are for
comparing one version of ALFRED's search with another on the same questions.

## Where to keep your files

Your questions and your results are private. Keep them on your own computer, in a folder
that is **outside** the ALFRED folder and **outside** your notes vault. For example, a
folder called `alfred-private` in your documents.

- Never put the real file inside the ALFRED folder. That folder is a public repository,
  and anything in it could be published by accident. The tool refuses to read or write
  there unless you are using the invented example.
- Never put the report inside your vault. The tool refuses this too, so results never
  mix with your notes.
- If you back the folder up, use a private backup, not a shared or public one.

In the commands below, `PRIVATE` stands for your private folder and `VAULT` for your notes
folder. Replace them with the real locations on your computer.

## The file

The file is plain text in JSON format, saved as something like `questions.json`. Here is a
small invented example:

```json
{
 "schema": "alfred.question-set.v1",
 "note": "My question set, started in October.",
 "questions": [
  {
   "id": "fact-depot-sign-in",
   "category": "fact",
   "question": "Who looks after the visitor sign-in at the Grellmouth depot?",
   "expect": ["places/grellmouth-depot.md"]
  },
  {
   "id": "refuse-holiday-flights",
   "category": "refuse",
   "question": "Which flight did I book for the Vellmoor trip?",
   "note": "I never wrote this down, so nothing should come up."
  }
 ]
}
```

Each question has:

- `id`: a short label of your choice, such as `fact-01` or `time-budget`. Letters, digits,
  dots, dashes and underscores only, up to 64 characters. **Ids appear in reports, so do
  not put anything private in them.**
- `category`: one of `fact`, `connected`, `time`, `preference` or `refuse` (see below).
- `question`: the question, written the way you would ask it. One line, up to 500
  characters.
- `expect`: the notes a good answer must bring up, as a list. Required for every category
  except `refuse`, and not allowed on a `refuse` question.
- `avoid` (optional): notes that must never come up for this question, such as another
  client's notes. If one comes up, the report calls it a **leak**.
- `note` (optional): a reminder for yourself. It is never copied into any report.

A note is named by its path inside your vault, with forward slashes, exactly as the
folders and file name are spelt. A note in a folder `Clients`, sub-folder `Orrin`, called
`Renewal.md`, is `Clients/Orrin/Renewal.md`. Capital letters matter.

## Writing good questions

Write the question first, in your own words, before you look at your notes. Then find the
notes that hold the answer and list them under `expect`. If you write the question while
reading the note, you will copy its words and make the test too easy.

Aim for thirty to fifty questions, with at least five in each category. List one to three
expected notes per question; ALFRED sends back at most five notes for any question.

Once you have used a question to compare two versions, do not change it. If you want a
different question, add a new one with a new id. Otherwise old and new reports no longer
measure the same thing.

### fact

One note holds the answer.

> "What is the notice period on the Orrin Textiles contract?" expects the renewal note.

### connected

The answer needs two or more notes that link to each other, such as a project note that
links to the person who runs it.

> "Who supplies the scanners for Project Heron, and how do they like to be contacted?"
> expects the project note and the supplier's person note.

### time

The question is about when something happened, or how something changed.

> "How did the Heron budget change between February and March?" expects both meeting
> notes.

### preference

How you like things done, as you have written it down somewhere.

> "How do I like to run my weekly review?" expects the note where you wrote that down.

### refuse

Nothing in your notes answers it. Leave out `expect`. A good result is that nothing at all
comes up. Use questions close to your real life, so the test is fair: something you might
ask but never wrote down.

> "Which flight did I book for the Vellmoor trip?" when you never noted the flight.

### avoid, for any category

Use `avoid` when the wrong note coming up would be a real problem. Typical cases: another
client's notes, private notes when you ask a work question, or work notes when you ask a
personal one.

> "When is the Orrin Textiles renewal due?" with the other client's renewal note under
> `avoid`.

## The commands

Open a terminal in the ALFRED folder. Each command is one line.

**Check the file** after every edit. This only reads it, and prints how many questions
there are in each category. It never prints your questions.

```
python3 tools/question_set.py validate PRIVATE/questions.json
```

If something is wrong, you get one line starting `error`, with a code in brackets and the
number and id of the question at fault. It never repeats your question text.

**Score ALFRED** and write a report:

```
python3 tools/question_set.py run PRIVATE/questions.json --vault VAULT --ranking both --output PRIVATE/report-2026-10-17.json
```

- `--ranking keywords` scores today's default search. `--ranking fts5` scores the other
  ranking ALFRED already has. `--ranking both` scores each. Without `--ranking`, only
  `keywords` is scored.
- The tool builds a throwaway copy of ALFRED's index in a temporary folder, reads your
  vault without changing it, asks every question and deletes the temporary folder at the
  end, also if something goes wrong.
- The report never includes your question text. If you want it there for your own
  reading, add `--include-text`. Only do that for a report you will keep private.
- Put the date in the report's name, so you can compare reports later. The tool will
  replace an earlier report of the same name, but never any other file.

The terminal then shows one summary line per ranking, for example:

```
keywords: recall 0.9286 (13 of 14 expected notes), complete 9/10, refused 1/2, leaks 1, passed 9/12, excerpt words 1311
```

If any `avoid` note came up, you also see a line starting `LEAK:` naming the question id.
If a note you listed under `expect` or `avoid` is not in your vault (often a spelling
slip), you see a `warning:` line; the report lists those paths under `not_in_vault`.

**Compare two reports**, for example before and after a change to ALFRED:

```
python3 tools/question_set.py compare PRIVATE/report-2026-10-17.json PRIVATE/report-2026-11-30.json
```

It compares rankings with the same name in both reports. To compare two different
rankings, name them, for example within one report:

```
python3 tools/question_set.py compare PRIVATE/report.json PRIVATE/report.json --old-ranking keywords --new-ranking fts5
```

## Reading the report

The report is a JSON file. For each ranking there is an `overall` block, one block per
category, and one entry per question. The words mean:

| Word | Meaning |
|---|---|
| `expected`, `found`, `recall` | Expected notes, how many came up, and found divided by expected. Higher is better. Empty (`null`) for refuse questions. |
| `complete` | Questions where every expected note came up. |
| `refuse_questions`, `refused` | Refuse questions, and how many of them brought up nothing. |
| `leaks`, `leaked_notes` | Questions where an avoid note came up, and how many such notes in all. Should be zero. |
| `passed` | Questions that did what you asked: every expected note found, or nothing for a refuse question, and no leak. |
| `sources` | How many notes came back in all. ALFRED returns at most five per question. |
| `excerpt_words` | Words of note text sent back. Lower is better if recall holds. |
| `returned` | For one question: the notes that came back, in ALFRED's order. |
| `missed`, `leaked` | For one question: expected notes that did not come up, and avoid notes that did. |
| `not_in_vault` | Paths you named that ALFRED did not find in the vault. Check the spelling. |

The `vault` block says how many notes ALFRED read and whether the scan was `ready` or
needs `attention`. `issues` counts any problems the scan met by kind, such as a note with
an unrecognised `kind`.

The report holds question ids, note paths, counts and scores. It never holds the text of
your notes or your reminders. It does list note paths, which can reveal folder and file
names, so keep it as private as the vault itself.

## Reading the compare output

```
Comparing old keywords with new fts5.
vault notes: 15 -> 15
overall: recall 0.9286 -> 1.0 (+0.0714), complete 9/10 -> 10/10, refused 1/2 -> 1/2, leaks 1 -> 1, passed 9/12 -> 10/12, excerpt words 1311 -> 1293 (-18)
connected: recall 0.8333 -> 1.0 (+0.1667), complete 2/3 -> 3/3, leaks 0 -> 0, passed 2/3 -> 3/3, excerpt words 452 -> 448 (-4)
changed questions:
  connected-pilot-count: recall 0.5 -> 1.0
```

Each line reads old value, arrow, new value, with the change in brackets. A better new
version has recall, complete, refused and passed going up, leaks staying at zero, and
excerpt words going down or staying level. Under `changed questions` you see each question
whose recall, leak or refusal changed, by id. If the two reports do not hold the same
questions, a line says so, and `only in old` and `only in new` list the ids that differ;
in that case the totals are not a fair comparison. If your vault gained or lost notes
between the two reports, the `vault notes` line shows it.

## If something goes wrong

Every refusal is one line starting `error`, with a code in brackets. The common ones:

| Code | What to do |
|---|---|
| `questions_inside_repository`, `vault_inside_repository`, `output_inside_repository` | Move the file or folder out of the ALFRED folder. |
| `output_inside_vault` | Write the report somewhere outside your vault. |
| `output_is_questions`, `output_not_a_report` | Choose a new name for the report, so nothing else is overwritten. |
| `invalid_path` | Write the note path relative to the vault, with forward slashes, ending in `.md`. |
| `expect_on_refuse`, `missing_expect` | Remove `expect` from refuse questions; add it to every other question. |
| `question_not_askable` | Shorten the question, keep it on one line, or use fewer distinct words. |
| `fts5_unavailable` | Your SQLite has no FTS5. Use `--ranking keywords`. |

The tool finishes with exit status 0 when all went well, 1 for a refusal, 2 for a mistyped
command and 3 when it wrote the report but found a leak.

## Trying it on the invented example

The repository holds an invented vault of fifteen notes and twelve questions in
`tests/fixtures/question_set/`. Everything in it is made up. To try the tool on it, add
`--synthetic`, which allows files inside the repository for invented data only, and write
the report outside the repository:

```
python3 tools/question_set.py run tests/fixtures/question_set/questions.json --vault tests/fixtures/question_set/vault --ranking both --synthetic --output PRIVATE/example-report.json
```

It reports one deliberate leak, so it finishes with exit status 3. Never use `--synthetic`
with your real questions.
