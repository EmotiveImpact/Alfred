# Brief for Astra: meaning search groundwork

**Paste into Codex cloud** (repository EmotiveImpact/Alfred, branch `main`):

> You are Astra, working on ALFRED alongside Claude. Read AGENTS.md and coordination/README.md,
> then build the task in coordination/briefs/codex-meaning-search.md. Your claim is
> coordination/claims/codex-meaning-search.md: change only the paths it lists, plus that
> claim file. Work on the branch codex/meaning-search and open a pull request to main when
> every check passes. Do not merge.

## Why this exists

ALFRED searches notes by keywords today. Plan phase 3 (`research/INTEGRATION_PLAN_2026-10-17.md`)
adds search by meaning, using `sqlite-vec` and a small local embedding model. Adopting those
two is the owner's choice and has not been made. Everything around them can be built now:
how notes are cut into passages, the interface an embedding model plugs into, a search index,
and how meaning results blend with keyword results. When the owner approves a model, it plugs
in without changing anything else.

## What to build

**`alfred/semantic.py`**, standard library only:

1. **Passages.** `passages(note_id, text)` splits a Markdown note into passages of bounded
   size along headings and paragraphs, each carrying its heading path, character offsets and
   a SHA-256 of its text, so every hit points at an exact place in an exact note revision.
2. **The embedder interface.** A small protocol: `name`, `dimensions`, `embed(texts) -> list
   of vectors`. Ship one implementation, `HashingEmbedder`: a deterministic hashed
   bag-of-words and character n-gram vector, normalised. It is a baseline and a test double,
   not a model. No model is downloaded, imported or run.
3. **An in-memory index.** `Index(embedder)` with `add(note_id, revision, passages)`,
   `remove(note_id)` and `search(query, k)`, cosine similarity by brute force, with stable
   tie-breaking. It lives in memory only. **Nothing is written to disk**: vectors can leak the
   text they came from, so persistence waits for the sealed store (plan phase 1).
4. **Area walls.** An index is built for one area's authorised notes only. The caller passes
   notes it has already been allowed to read; `search` cannot reach another index. Test that
   two indexes never see each other's notes.
5. **Blending.** `blend(keyword_ranked, meaning_ranked, k=60)` using reciprocal rank fusion,
   deterministic, with each result keeping where it came from (keyword, meaning or both) and
   its rank in each list.

**Docs.** `docs/MEANING_SEARCH.md`, in plain British English: what is built, what waits for
the owner's model choice, why vectors stay off disk for now, and how a model will plug in.
`docs/evidence/meaning-search/RECEIPT.md`: the commit tested, commands and results.

## How to work

- Tests first in `tests/test_semantic.py`: passage boundaries and offsets on tricky Markdown
  (front matter, code blocks, long paragraphs, empty notes), identical output across runs,
  cosine maths on hand-checked vectors, removal, area isolation, blending ranks pinned on a
  small invented example, and a size test (2,000 invented passages searched well within a
  second).
- Use only invented notes. Standard library only (`hashlib`, `math`, `re`).
- Do not edit `alfred/grounded.py`, `alfred/knowledge.py` or any storage module. They are in
  Claude's encryption claim. Wiring the blend into ALFRED's search is Claude's follow-up; list
  what you would need under "Needs from Claude".
- If the question set harness (`tools/question_set.py`) has merged, you may read it, but do
  not edit it from this branch.
- Run `python3 -m unittest discover -s tests` and `python3 tools/check_claims.py --base
  origin/main --branch codex/meaning-search` before opening the pull request.

## Done when

The module and its tests pass, nothing touches disk or the network, CI is green, and the pull
request says exactly what a real embedding model will need to provide.
