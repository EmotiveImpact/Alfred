# Meaning search groundwork (plan phase 3)

Status, 17 October 2026. This is groundwork for searching notes by meaning beside today's
keyword search. It is a standard-library module, `alfred/semantic.py`, with its tests in
`tests/test_semantic.py`. It is **not wired into ALFRED's questions or the desk yet**, no
embedding model has been chosen, downloaded or run, and nothing it builds is written to disk.
Plan: [phase 3 of the integration plan](../research/INTEGRATION_PLAN_2026-10-17.md).
Receipt: [evidence/meaning-search/RECEIPT.md](evidence/meaning-search/RECEIPT.md).

## In one paragraph

Keyword search finds a note only when it shares your words. Meaning search turns each passage
of a note, and your question, into a list of numbers (a vector) so that passages about the
same thing sit close together even when the words differ. Doing that well needs a real
embedding model and somewhere safe to keep the vectors. Both wait for you. Everything around
them is built now: how notes are cut into passages, the socket a model plugs into, a search
index held in memory, and the rule for blending meaning results with keyword results. When you
approve a model, it plugs in without anything else changing.

## What is built

| Piece | What it does |
|---|---|
| Passages | `passages(note_id, text)` cuts a note into passages, each an exact slice of the stored note text with its heading path, character offsets, line numbers and a SHA-256 of its text |
| The model socket | A small interface any embedding model must meet: `name`, `dimensions`, `embed(texts)` |
| A stand-in embedder | `HashingEmbedder`, a deterministic word-and-spelling fingerprint. It is a baseline and a test double, **not** a model of meaning |
| The index | `Index(embedder, scope=...)` with `add`, `remove` and `search`, cosine similarity worked out by brute force, in memory only |
| Area walls | One index per area (scope), holding only notes that area's credential may already read |
| Blending | `blend(keyword_ranked, meaning_ranked)` merges the two rankings by reciprocal rank fusion |
| Rechecks | `passage_text(hit, revision, text)` returns a hit's passage only if the note is still at that revision with the same text |

### How notes are cut into passages

- **Headings start sections.** ATX headings (`#` to `######`) outside code fences open a
  section. Each passage carries the path of headings above it, for example
  `["Plan", "Risks"]`, and a passage never spans two sections. Heading lines themselves are
  not passage text; their words reach the index through the heading path (below).
- **Paragraphs are packed.** Paragraphs, lists and whole code fences in one section are packed
  together in order while the passage stays within 1,000 characters (adjustable from 64 to
  8,000 with `limit`).
- **Code fences stay whole.** A fence is never cut part-way if it fits. Headings inside a fence
  are ignored. A fence longer than the limit is cut at line ends.
- **Long paragraphs are cut on whitespace.** A paragraph longer than the limit is cut at the
  last line break in the second half of the allowed length, otherwise at the last space,
  otherwise (an unbroken run such as a long link) at exactly the limit, moved back so an accent
  is never separated from its letter.
- **Front matter is left out.** The `---` block at the top of a note is metadata, not passage
  text, and is recognised exactly as the note scanner recognises it (`alfred/knowledge.py`):
  closed within the first 81 lines. Unclosed front matter and an unclosed code fence are
  refused with the scanner's own error codes, so a note is either accepted by both or by
  neither.
- **What is left out or kept.** Blocks with no letter or digit (a lone `---` rule, an empty
  fence, a line of emoji) do not become passages. HTML and Obsidian `%%` comments are kept as
  written: they are your own text in your own area. A heading written inside a comment still
  counts as a heading here, unlike in the note scanner's link reading. Setext headings (a line underlined with
  `===`) are not recognised as headings, matching the note scanner.
- **Exact places.** `text[start:end]` gives back the passage exactly, and `sha256` is the
  SHA-256 of its UTF-8 bytes. Offsets are Python string positions (Unicode code points), not
  byte positions: in `# Café`, the `é` counts as one position though it is two bytes. Line
  numbers follow Python's `str.splitlines`, the same numbering as grounded excerpts. Windows
  line endings (CRLF) are kept inside passage text exactly as stored, and never left dangling at
  a passage edge.
- **The same every time.** The same note text always gives the same passages, in any process.

### The stand-in embedder

`HashingEmbedder(dimensions=256)` reads each word (after Unicode NFKC normalisation and case
folding, so `BUDGET` and `budget` agree), and adds the word and its three-letter pieces into
fixed slots chosen by a BLAKE2b hash. The word and its pieces carry equal weight, so `budget`
and `budgets` come out similar while `budget` and `harbour` do not. The vector is then scaled
to length one. It never uses Python's built-in `hash()`, which changes between runs, so a
vector is identical in every process on the same Python version (the Unicode tables come with
Python, so a newer Python could treat a newly added character differently). Text with no words
gives a vector of zeros, which matches nothing. Its name, `alfred-hashing-v1-d256`, records the
version and size. It knows spelling, not meaning: it cannot tell that "boat" and "vessel" are
related. That is the model's job.

### The index

- **In memory only.** Vectors and passage locators live in the running process and nowhere
  else. The index refuses to be pickled or copied, and the module imports nothing that can
  reach a file, database or network (a test checks its imports).
- **One area per index.** An index is created for one scope and holds only the notes that
  scope's credential may already read. Nothing is shared between indexes, so a search can never
  reach another area's notes, counts or neighbours. Two indexes holding the same note ID keep
  separate records (tested).
- **Exact revisions.** `add(note_id, revision, passages)` replaces every passage of the note's
  older revision. An older revision is refused (`stale_revision`), and the same revision with
  different passages is refused (`revision_conflict`). A refused or failed add leaves the index
  exactly as it was. Adding an empty passage list, or `remove(note_id)`, drops the note; the
  caller does this when a note is deleted, becomes unavailable, or access is revoked.
- **Checked inputs.** Passages must be internally consistent (offsets match the text, digest
  matches, in order, no overlap, at most 8,000 characters). Every vector from the embedder is
  checked for count, length, real finite numbers and unit length. At most 50,000 passages per
  index.
- **What is embedded.** Each passage is embedded with its heading path in front, for example
  `Plan > Risks` then a blank line then the passage, so a passage under "Risks" can be found
  by a question about risks.
- **Search.** `search(query, k)` returns at most `k` hits (1 to 100), best first. Ties are
  broken by note ID and then passage start, so the order is always the same. A question with
  no words returns nothing. Each hit gives the scope, the embedder's name, the note ID and
  revision, the offsets, line numbers, heading path, the passage SHA-256 and the score. It
  does not carry the passage text.
- **A hit is a pointer, not evidence.** The score is a similarity between numbers, not
  confidence, relevance proven, or truth. Before anything is shown or cited, the caller rereads
  the note through the normal access checks and calls `passage_text`, which refuses
  (`passage_changed`) if the revision or the text no longer matches.

The index is meant for one thread at a time; it has no locking.

### Blending with keyword search

`blend(keyword_ranked, meaning_ranked, k=60)` takes two ranked lists of IDs, best first, and
gives each ID a score of 1/(60 + rank) from each list it appears in, added together. This is
reciprocal rank fusion: it uses positions, not raw scores, so keyword and meaning scores never
need to be on the same scale. Each result keeps where it came from (`keyword`, `meaning` or
both) and its rank in each list. Scores are added as exact fractions, so equal scores really
are equal. Ties go to the better single rank, then the better keyword rank (an exact word match
is easier for you to check), then the ID. An ID listed twice in one list is refused, as is a
list of more than 1,000. Today's keyword ranking works per note, so `best_per_note(hits)` turns
passage hits into note IDs, in the order of each note's best passage, for blending.

## Why vectors stay off disk for now

A vector is not a harmless summary. Published attacks recover much of the original text from
its embedding, and a vector index also reveals which notes are close to which. Written to disk
unencrypted, it would be a second, readable copy of your notes outside the protections planned
for them, and one that deletion would also have to find. So the index lives only in memory
until the sealed store exists (plan phase 1): one key per area, records and indexes sealed, and
deleting a note or destroying an area's key also removing its vectors. Until then the index is
rebuilt from the notes each time ALFRED starts: a moment with the stand-in, and a one-off wait
at start-up with a real model.

## What waits for you

- **Choice 5: adopting `sqlite-vec` and an embedding model**, as a normal adoption sign-off
  (exact source, licence, containment, no data leaving the machine). Recommended after phase 2.
- **The sealed store (phase 1)** before any vector is saved.
- **The real question set.** Meaning search ships only if it beats keyword search on your real
  questions. The stand-in embedder has not been measured against anything, and these tests prove
  the mechanics, not that answers improve.

## How a real model plugs in

A model is wrapped in a small object with three things. Nothing else in ALFRED changes.

1. **`name`**: one short identifier naming the exact model, its version and configuration (for
   example the model name, a release or file hash, and the pooling used). Letters, digits and
   `_ . : -`, at most 80 characters. Every hit records it, so results from two models are
   never mixed; changing the model means building a new index.
2. **`dimensions`**: the vector length, a whole number from 2 to 4,096, fixed for the model.
3. **`embed(texts)`**: given a list of strings, returns a list of the same length, in the same
   order, each a list of exactly `dimensions` real, finite numbers. The rules:
   - **Normalised.** Each vector has length one (within 0.0001), so that similarity is a plain
     dot product. Empty or wordless text may give all zeros, which matches nothing. Anything
     else is refused, not quietly rescaled, because it usually means the model is set up wrongly.
   - **Deterministic.** The same text gives the same numbers on every call, in every process,
     on the same machine. No sampling, no randomness, no dependence on batch size or order.
     If a model's last decimal places shift with batch size, the wrapper embeds one text at a time.
   - **Offline.** It runs on your machine with the model files already present. It never
     downloads at run time, calls a service or sends text anywhere.
   - **Bounded.** It accepts texts of up to 65,536 characters (truncating to the model's own
     limit is acceptable and should be stated), and raises an error rather than returning
     partial results.
   - **Quiet.** It keeps no copy of the texts, writes no cache of them to disk, and logs no text.

A model that meets this can be tested with the same tests as the stand-in, by passing it to
`Index` in place of `HashingEmbedder`.

## Not done here

- Wiring meaning search into grounded questions, conversations or the desk, and any HTTP or
  console surface.
- Building indexes from the knowledge store at start-up and updating them as the vault scanner
  sees changes, deletions and revocations.
- Any saved or sealed vector store, `sqlite-vec`, or any model.
- Any measurement of answer quality.
