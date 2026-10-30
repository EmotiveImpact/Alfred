# Meaning search groundwork receipt (backlog A4, plan phase 3)

17 October 2026. Branch `claude/project-thread-att046-meaning-search`, based on `origin/main` at
`d81a5d509`. **Tested commit: `5e0f1c31e`.** This receipt is added in the commit after it and
changes no code. Status: **implemented and unit tested; not wired into ALFRED's questions,
conversations, desk or console.** Invented notes only. No embedding model, `sqlite-vec`, vault,
account, device or network was used, and nothing is deployed. Design and limits:
[MEANING_SEARCH.md](../../MEANING_SEARCH.md).

## Tested tree

The base commit plus these files, with their SHA-256 at the tested commit:

| File | Change | SHA-256 |
|---|---|---|
| `alfred/semantic.py` | new | `5f5ae04d14f0755b34b5f830f4b66e9b875a93ee9c9742974afedd8ab50cf652` |
| `tests/test_semantic.py` | new | `cda7a4852a471967782cc0c28aed23cb8dce1f42068ab6252fca181beccb7425` |
| `docs/MEANING_SEARCH.md` | new | `a2ac3887ba7883165e10edccb0369c083b387f73c88da6b652747380640aee24` |

No existing file is changed. `alfred/grounded.py`, `alfred/knowledge.py` and every storage module
were read only.

## Commands and results

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests -p "test_semantic.py"` | 43 tests, OK, about 0.3 s |
| `python3 -m unittest discover -s tests` | 1,470 tests, OK, 244.5 s, none skipped |
| `python3 tools/check_claims.py --base origin/main --branch claude/project-thread-att046-meaning-search` | `claims ok` |
| `python3 tools/test_claims.py` | OK |

Python 3.13 on Linux, standard library only.

## What the tests pin

- **Passages.** Exact start, end, line numbers, heading path and text on invented notes, with
  `text[start:end] == passage text` and the SHA-256 checked for every passage in every test:
  heading levels and closing hashes, lines that are not headings (no space, seven hashes,
  indented four spaces or a tab), front matter left out, unclosed or over-long front matter and
  unclosed fences refused with the note scanner's codes, fences kept whole with headings inside
  ignored, tilde and longer fences, a long fence cut at line ends, a long paragraph cut on
  whitespace within the limit, an unbroken run cut hard but never before a combining accent,
  CRLF, non-ASCII offsets as string positions, empty and wordless notes, identical output on
  repeated runs, and refusals of bad IDs, text, sizes and limits.
- **Embedder.** Name and size, unit length, the zero vector for empty and wordless text, a
  hand-checked pinned vector for `Budget` at 16 dimensions (word slot 1/√2, six trigram slots
  1/√12), case and Unicode forms folding together, related spellings overlapping, identical
  vectors and passages in two fresh processes with different `PYTHONHASHSEED`, and refusals.
- **Index.** Cosine scores on hand-written vectors (1.0, 0.6, 0.0, -1.0) in order, the heading
  path embedded with the passage, tie-breaking by note ID then start, zero vectors never
  matching, `k` and query refusals, removal, a newer revision replacing the old one, stale and
  conflicting revisions refused, failed or refused adds leaving the index unchanged (seven kinds
  of bad vector and an embedder that raises), twelve kinds of malformed passage refused, the
  capacity limit, two scopes never seeing each other's notes, embedder refusals, pickling and
  copying refused, returned hits being copies, `passage_text` refusing a changed note, and
  `best_per_note`.
- **Blend.** A pinned four-ID example with exact reciprocal rank fusion scores and the tie
  rules, the effect of `k`, one or no lists, and refusals of duplicates, bad lists, IDs, length
  and `k`.
- **Boundary.** The module imports only `bisect`, `fractions`, `functools`, `hashlib`, `heapq`,
  `math`, `re`, `typing`, `unicodedata` and `alfred.local`, and never names `open`, `exec`,
  `eval`, `compile` or `__import__`.

## Size test

2,000 invented passages (200 notes of 10 sections) are indexed with `HashingEmbedder(256)` and
searched for 10 hits. The test requires one search under 0.5 s. Measured at the tested commit:
building took 0.20 s and five searches took 7.0 to 7.6 ms each, about 65 times inside the limit.

Outside the suite, a 20,000-case random Markdown check (headings, fences, CRLF, form feeds,
line separators, comments, accents, long runs) found every accepted note's passages slicing back
exactly, trimmed, in order, within the limit, and accepted by `Index.add`; the only refusals
were the two scanner codes for unclosed fences and front matter.

## Not shown by this receipt

- That meaning search improves answers. The stand-in embedder knows spelling, not meaning, and
  nothing was measured against the real question set.
- Any real embedding model, `sqlite-vec`, saved or sealed vectors, or wiring into
  `alfred/grounded.py`.

## Review change at `a3ad599c5`

The lead's review found that `_features` was wrapped in a process-wide `lru_cache` of up to
65,536 words. Words from every area's notes stayed in memory for the life of the process, even
after a note was removed. The cache is now one dictionary per `embed` call. A new test,
`test_the_embedder_keeps_nothing_from_the_text_it_embedded`, failed on `5e0f1c31e` and passes at
`a3ad599c5`. `python3 -m unittest discover -s tests -p test_semantic.py`: 44 tests OK. No other
code changed.
