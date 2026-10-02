# M06: lexical baseline and deterministic retrieval evaluation

2 October 2026. Evaluation checkpoint, not a merge, deployment or job-state
change. `plans/memory-backlog.json` and `plans/requirement-register.json` are
deliberately unchanged; the coordinating session decides M06's state.

## Starting point and tested code

Branch `worktree-agent-ac5d518ca7f47a115`, parent
`02ca166c0502ed07a0b2370c86a76b497e8419d7` (the `claude/alfred-development-qpgxhg`
integration head). The worktree began at main
`8398c7437cb0ef1386d8dc4ff1f9e92fb2557ca2`, which lacks `alfred/retrieval.py` and
`alfred/policy.py`, so it was fast-forwarded to that head before any change.

No file under `alfred/` was changed and the default ranking remains `keywords`.
The new code uses the Python standard library only. SHA-256 values for the new
and exercised files are listed at the end, so the tested code is identifiable
without a self-referential commit hash.

## What was measured

[`tools/evaluate_retrieval.py`](../../../tools/evaluate_retrieval.py) builds an
invented workspace in a temporary directory. Nothing in the evaluation is random.

- **Granted source:** 64 short Markdown notes covering six fictional projects and
  client accounts, eight people, six decisions, four procedures, two leadership
  meetings, four personal notes and twelve templated daily notes. Deliberate
  hazards: near-duplicates (draft and approved budgets, consecutive stand-ups, two
  `kickoff.md`, two `renewal-terms.md`), a shared first name (Morgan Ellery and
  Morgan Quill), terms that occur only in a level-two heading, client names that
  occur only in a folder path, 28 resolved wikilinks (zero link issues) and
  personal or daily distractors.
- **Ungranted source:** six notes under a second source credential in the same
  workspace, written to match several questions (Morgan Quill, the Harbour Lights
  budget, the Kestrel depot, renewal terms, the Juniper committee and the Lantern
  blocker).
- **Questions:** 44 in total. 40 are answerable, with 51 labelled supporting notes;
  4 are unanswerable controls whose correct packet is empty. Categories: exact 17,
  near-duplicate 5, multi-support 3, heading-only 2, path-only 2, linked 2,
  inflection 2, shared name 2, shared title 2, vocabulary mismatch 2, personal 1
  and unanswerable 4.
- **Answer keys:** for each question, the set of granted note paths that genuinely
  support it. They exist only in the script's scoring table.

Protocol for each run:

1. Index both sources (both `ready`, no errors) and confirm that the indexed
   `(source, path, SHA-256)` list equals the frozen manifest.
2. **Positive control** under the documented legacy whole-workspace policy: ask
   each question once per ranking and count the questions whose packet contains a
   note from the second source. This is the existing coarse policy, not leakage;
   it proves that the leakage check below is able to fail.
3. Enable strict policy with `IdentityPolicy.grant`: a `read` grant for the main
   source only.
4. Run one unmeasured warm-up pass, then five measured passes. Both rankings run
   back to back for each question, and the ranking that goes first alternates on
   each pass.
5. Quality metrics come from the first measured pass. The warm-up and every
   measured pass are checked for leakage, and every measured pass must return
   identical evidence (all did).
6. Scoring starts only after every `retrieve()` call has returned.

The only route to `retrieve()` is a helper that passes the question, `ranking`
and `purpose='read'`, and logs exactly that. `answer_keys_in_request_context` in
the report is computed from that log rather than asserted. Each answer key carries
a canary label. Tests confirm that no canary or key path appears in any request or
packet, and that deliberately rotated answer keys leave every packet unchanged
while the scores change.

## Exact commands

```
python3 tools/evaluate_retrieval.py --repeats 5 --output docs/evidence/memory-m06/report.json
python3 tools/evaluate_retrieval.py --repeats 5 --output docs/evidence/memory-m06/report-repeat.json
python3 -m unittest tests.test_retrieval_evaluation -v
python3 -m unittest discover -s tests
python3 tools/check_memory_plan.py
python3 tools/check_requirement_register.py
```

The evaluator prints the same JSON that it writes. Exit status 0 means a complete
run; 1 means leakage, answer-key exposure or non-deterministic evidence; 2 means
the SQLite build lacks FTS5, in which case the report records `fts5` as
`not_measured` with the reason instead of failing silently.

## Results

Environment: CPython 3.11.15 and SQLite 3.45.1 with FTS5, in a Linux x86_64
container. Frozen-set hashes, identical in both committed runs:

- frozen set `bf9eb18e8532be8e80e2abb3e6d188ace7371e5cb7e875cbe16bcd3289f7507c`
- corpus `350cfaca007b5aac9830f6c232e3762431b6da128410883fc3854d5af6c29fe6`
- questions `f83030e6123510d36a58458c3ae1a4ee70267dc9351ea5ece26548f23d70f507`
- answer keys `177c83a5036be578dabb0b477c28e0ee7592d8ce1e97c3782b92dad2094d4e19`

From [report.json](report.json), with latency also shown from
[report-repeat.json](report-repeat.json):

| Measure | `keywords` (default) | `fts5` |
|---|---|---|
| Mean evidence recall, 40 answerable questions | 0.9229 | 0.9042 |
| Supporting notes found, of 51 | 46 (0.9020) | 45 (0.8824) |
| Any supporting note present | 38/40 (0.950) | 37/40 (0.925) |
| All supporting notes present | 35/40 (0.875) | 35/40 (0.875) |
| First evidence item supports the answer | 36/40 (0.900) | 32/40 (0.800) |
| Irrelevant share of evidence items, 44 questions | 143/189 (0.7566) | 141/186 (0.7581) |
| Irrelevant share of excerpt characters | 0.7605 | 0.7654 |
| Link-expansion items that were irrelevant | 39/41 | 49/50 |
| Unanswerable questions returning evidence | 4/4 (20 items) | 4/4 (20 items) |
| Mean evidence items per question | 4.30 | 4.23 |
| Latency p50 / p95 in ms, 220 calls, report run | 61.7 / 81.9 | 61.1 / 82.8 |
| Latency p50 / p95 in ms, 220 calls, repeat run | 57.4 / 63.3 | 58.1 / 65.7 |
| Ungranted evidence items, 264 strict calls | 0 | 0 |
| Packets with ungranted IDs, hashes or text | 0/44 | 0/44 |
| Legacy-policy control: questions reaching the second source | 14 | 16 |

Per question, recall was equal on 37 of 40, higher for `keywords` on 2 and higher
for `fts5` on 1. 17 of 44 packets listed identical evidence paths in the same
order. Both rankings scored 1.0 on the exact, heading-only, near-duplicate,
path-only, shared-name, shared-title and personal questions, and 0 on both
vocabulary-mismatch questions. The two committed runs are identical in every
field except latency.

The differences, traced to the packets:

- **Q09** ("When will Lantern cut over?"): substring scoring finds `cut` and `over`
  inside `cutover`; FTS5 tokens do not, and `over` instead matched unrelated notes
  ("move over the weekend", "summaries over calls"). Recall 0.5 against 0.
- **Q18** ("Which supplier did the Juniper committee choose?"): the contract is
  reachable only through a wikilink. FTS5's third seed was the hybrid-working
  decision (token `choose`), so three link targets competed for two places and
  were taken in path order, which dropped the contract. Recall 1.0 against 0.5.
- **Q28** ("Which projects does Ada Mensah sponsor?"): keyword scoring also
  searches paths, so the folder name `projects` lifted three notes above
  `people/ada-mensah.md`, and the Harbour Lights hub's links took the last two
  places. FTS5 does not index paths. Recall 0.75 against 1.0.
- **First item:** FTS5 also put a non-supporting note first for the client
  questions Q22, Q23 and Q24. In Q22 and Q23 the client name appears only in the
  supporting note's folder path; for Q23 (the Saltmarsh notice period) the first
  item was Orchid's near-identical `renewal-terms.md`. In Q24 the Orchid account
  hub, whose title names the client, outranked the support-tier note.

## What this shows and does not show

On this frozen set it shows that:

- Under strict grants neither ranking returned ungranted evidence, identifiers,
  hashes or text across 264 strict calls each, while the legacy-policy control
  shows the same questions do reach the ungranted notes when policy allows it.
  `alfred/retrieval.py` indexes only the authorised, current notes that
  `retrieve()` passes to it.
- The two lexical rankings are nearly equivalent in recall and irrelevant context.
  Their differences come from token against substring matching and from whether
  folder paths are searched; each choice helps some questions and hurts others.
- Irrelevant context (about 76% of items for both) is driven by packet assembly
  rather than ranking. Packets fill to five sources even for unanswerable
  questions, and one-hop link targets, taken in path order before further matches,
  were irrelevant 95% to 98% of the time.
- End-to-end latency shows no consistent difference. The p50 ratio of FTS5 to
  keywords was 0.99 in one run and 1.01 in the other, while each ranking's own p50
  moved by 3 to 4 ms between runs. An ad hoc `cProfile` of 44 FTS5 calls, not part
  of the committed evidence, attributed about 64% of time to per-note authorised
  reads, about 30% to the graph view and about 1% to `fts_rank`.

It does not show:

- Anything about private vaults, larger corpora or other phrasing. One author
  wrote the corpus, questions and labels while knowing how both rankings work;
  44 questions is a small set and no significance test was run.
- Answer correctness, semantic quality or entailment. A label means a note
  supports an answer; reaching the packet is not answering.
- Hardware performance. Latency is wall-clock time in this container, not on any
  named target hardware.
- Any model behaviour. No model, provider or network call was made, no new model
  experiment is implied and the blocked live-model comparison remains unexecuted.
- Reviewed-memory retrieval (this set has no reviewed statements), the `model`
  purpose, more than one ungranted source or grant changes during a call. The
  legacy whole-workspace policy still exposes every source to the owner, by
  design, until strict grants are enabled (M02).

## Recommendation

FTS5 does not earn a change of default on this evidence. It shows no recall gain
(0.904 against 0.923 mean), no reduction in irrelevant context, no measurable
latency gain and a weaker first item (32 against 36 of 40) because it ignores
folder context. Keep `keywords` as the default and keep the ephemeral
authorised-subset FTS5 path only as a measured comparator. Its per-call in-memory
index is cheap and leaves no persistent copy to purge, so keeping it costs little,
but adopting it would not help.

The measured levers for the next retrieval change lie in packet assembly rather
than ranking: a relevance floor so that an unanswerable question can return no
evidence, ranking one-hop link targets by relevance instead of path, and fewer
per-note connections. Revisit FTS5 if the 256-note view cap rises far enough for
scanning cost to matter; a persisted index would then add purge and deletion
obligations under M05. None of these changes is implemented here, and each needs
its own acceptance evidence.

## Code and defects

Only new files were added: the evaluator, its tests, this receipt, the two reports
and the two test logs. No genuine defect was found in `alfred/retrieval.py`, so it
is unchanged. A probe with operator words, quotes, underscores, non-ASCII digits
and diacritics produced quoted FTS syntax and no errors. Observations, not fixed:

- FTS5 indexes title and body only (frontmatter tags match as body text), while
  keyword scoring also searches folder paths and gives tags title weight. This
  explains Q22, Q23 and Q28.
- Packets label FTS5-selected notes `keyword_match`; the packet's `ranking` field
  records `fts5`. The report's `by_route` figures keep the packet's labels.
- On an SQLite build without FTS5, `retrieve(..., ranking='fts5')` would raise
  `sqlite3.OperationalError` rather than an application `Fault`. That path is not
  reachable from HTTP or the interface; the evaluator probes first and reports the
  gap.

## Validation

- `python3 -m unittest tests.test_retrieval_evaluation -v`: 12 tests pass
  ([evaluation-tests.txt](evaluation-tests.txt)). They assert zero leakage for
  every measured ranking, a leakage control that is not vacuous, answer keys
  absent from every request and packet, an injected key being detected, packets
  unchanged under rotated keys, identical questions for each ranking, the required
  report fields, metrics within [0, 1], a frozen-set hash that is stable across two
  runs, a committed report that matches the frozen set, and honest reporting when
  FTS5 is unavailable. None asserts that either ranking is better.
- `python3 -m unittest discover -s tests`: 711 tests pass, the existing 699 plus
  these 12 ([suite-summary.txt](suite-summary.txt)).
- `tools/check_memory_plan.py` and `tools/check_requirement_register.py` pass, as
  do their 12 and 11 self-tests. `git diff --check` is clean.

## M06 acceptance mapping

| Criterion | Evidence |
|---|---|
| Compare current ranking with FTS5 on identical invented support-labelled queries | 44 invented questions with answer keys; `queries.identical_across_rankings` is true with matching `sent_sha256`; `test_identical_queries_for_every_ranking` |
| Report recall, irrelevant context, latency and permission leakage separately | Separate `recall`, `irrelevant_context`, `latency_ms` and `permission_leakage` sections for each ranking in [report.json](report.json) |
| Keep answer keys outside request context; no new model experiment implied | Derived `answer_keys_in_request_context: false` and `model_inference: false`; canary, rotated-key and injected-key tests |

This is evidence for the coordinating session's M06 decision, not a state change.
No private data, `third_party` code, network access, model, merge or deployment was
involved.

## Tested file hashes

SHA-256 of the files as tested:

```
d17779899411334077686f9b52af421d3877014798510a97706b11a20814e0b3  tools/evaluate_retrieval.py
76effd3e0e7aed76296febd7e689937dfc1f8c527a502dfeec66f58096ddf60a  tests/test_retrieval_evaluation.py
af9c6f0916ee785f354745a469180ecadd31594cfddcc184efda507acf5d219b  alfred/grounded.py
d07fd53c03892f16b5afe8782ad8711c3f522c8a0d14b973a0e7d33345285dec  alfred/retrieval.py
67df2f4938a288afa40fb88d44df6ad7105ac9376b533eb6949286b75f137b24  alfred/knowledge.py
591156761ca6c56559fa74521eff051bd3c6f9c13d436fe30416d99dd5aaa3b3  alfred/policy.py
b1a1c3ae5976cf02158c638b91213f517181d43994df48fb756ef6cf2d27116e  docs/evidence/memory-m06/report.json
9a7a0e2c0ec8fac440686f1cd1382912fa43823a95cf25f2104dd9e547b1a7e5  docs/evidence/memory-m06/report-repeat.json
```
