"""Meaning search groundwork: passages, an embedder interface, an in-memory index and blending.

Plan phase 3 adds search by meaning beside keyword search. Adopting `sqlite-vec` and a real
embedding model is the owner's choice and has not been made, so nothing here downloads,
imports or runs a model. `HashingEmbedder` is a deterministic hashed bag of words and
character trigrams: a baseline and a test double, not a model of meaning.

Passages are exact slices of a note's stored text. Offsets are Python string indices (code
points), not UTF-8 byte offsets, and line numbers follow `str.splitlines`, as the note
scanner and grounded excerpts do. Front matter, unclosed front matter and unclosed code
fences follow the scanner's rules in `alfred/knowledge.py`, so a note either passes both or
neither. The index is memory only: no file, database, pickle or copy, because vectors can
leak the text they came from; persistence waits for the sealed store (plan phase 1). An
index holds one scope's already authorised notes and cannot reach another index. A hit is
a locator, not evidence: the caller rereads the note and rechecks it (`passage_text`).
Design and limits: docs/MEANING_SEARCH.md.
"""
from __future__ import annotations
from bisect import bisect_right
from fractions import Fraction
import hashlib
import heapq
import math
import re
from typing import Protocol, Sequence
import unicodedata
from .local import Fault, ident

MAX_NOTE_CHARACTERS, MAX_TEXT_CHARACTERS, MAX_QUERY_CHARACTERS = 65536, 65536, 2000
PASSAGE_CHARACTERS, MIN_PASSAGE_CHARACTERS, MAX_PASSAGE_CHARACTERS = 1000, 64, 8000
MAX_K, MAX_PASSAGES, MAX_DIMENSIONS, MAX_RANKED, MAX_RANKED_ID, MAX_RRF_K = 100, 50000, 4096, 1000, 200, 1000
MAX_WORD, NORM_TOLERANCE = 64, 1e-4
PASSAGE_KEYS = frozenset({'note_id', 'index', 'start', 'end', 'start_line', 'end_line', 'heading_path', 'text', 'sha256'})
_FENCE = re.compile(r'\s{0,3}(`{3,}|~{3,})')
_HEADING = re.compile(r'\s{0,3}(#{1,6})\s+(.+?)\s*')
_WORD = re.compile(r'\w+')
_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}')


def _digest(text):
    return hashlib.sha256(text.encode('utf-8', 'surrogatepass')).hexdigest()


def passages(note_id, text, *, limit=PASSAGE_CHARACTERS):
    """Cut one note's stored text into bounded passages along headings and paragraphs.

    ATX headings outside code fences open sections; each passage carries the path of
    headings above it and never spans two sections. Paragraphs and whole fences are packed
    in order while the slice stays within `limit` characters. A longer block is cut at the
    last line break in the second half of the window, else the last whitespace, else hard
    (never just before a combining mark). Front matter, heading lines and blocks without a
    letter or digit are left out; HTML and `%%` comments are kept as written.
    """
    ident(note_id)
    if not isinstance(text, str):
        raise Fault('note_text_required')
    if len(text) > MAX_NOTE_CHARACTERS:
        raise Fault('note_too_large')
    try:
        text.encode('utf-8')
    except UnicodeEncodeError:
        raise Fault('note_not_utf8') from None
    if type(limit) is not int or not MIN_PASSAGE_CHARACTERS <= limit <= MAX_PASSAGE_CHARACTERS:
        raise Fault('invalid_passage_limit')
    lines = text.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    first = 0
    if lines and lines[0].strip() == '---':
        end = next((i for i in range(1, min(len(lines), 81)) if lines[i].strip() == '---'), None)
        if end is None:
            raise Fault('unclosed_or_oversized_frontmatter')
        first = end + 1
    blocks, headings, section, paragraph, fence = [], [], 0, None, None

    def close(top, bottom):
        s, e = starts[top], starts[bottom + 1]
        while s < e and text[s].isspace(): s += 1
        while e > s and text[e - 1].isspace(): e -= 1
        if _WORD.search(text, s, e):
            blocks.append((s, e, section, tuple(name for _, name in headings)))

    for i in range(first, len(lines)):
        content = lines[i].splitlines()[0]
        marker = _FENCE.match(content)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= fence[1]:
                close(fence[2], i); fence = None
            continue
        heading = None if content.startswith(('    ', '\t')) else _HEADING.fullmatch(content)
        if paragraph is not None and (marker or heading or not content.strip()):
            close(paragraph, i - 1); paragraph = None
        if marker:
            fence = (marker[1][0], len(marker[1]), i)
        elif heading:
            level = len(heading[1])
            while headings and headings[-1][0] >= level: headings.pop()
            headings.append((level, re.sub(r'\s+#+\s*$', '', heading[2]).strip()))
            section += 1
        elif content.strip() and paragraph is None:
            paragraph = i
    if fence:
        raise Fault('unclosed_code_fence')
    if paragraph is not None:
        close(paragraph, len(lines) - 1)
    spans, group = [], None
    for s, e, sect, path in blocks:
        if group and group[2] == sect and e - group[0] <= limit:
            group[1] = e; continue
        if group: spans.append(tuple(group))
        group = None
        if e - s <= limit:
            group = [s, e, sect, path]
        else:
            spans.extend((ps, pe, sect, path) for ps, pe in _split(text, s, e, limit) if _WORD.search(text, ps, pe))
    if group: spans.append(tuple(group))
    return [{'note_id': note_id, 'index': n, 'start': s, 'end': e, 'start_line': bisect_right(starts, s),
             'end_line': bisect_right(starts, e - 1), 'heading_path': list(path), 'text': text[s:e], 'sha256': _digest(text[s:e])}
            for n, (s, e, _, path) in enumerate(spans)]


def _split(text, s, e, limit):
    pieces, pos = [], s
    while e - pos > limit:
        top = pos + limit
        cut = max(text.rfind('\n', pos + 1, top + 1), text.rfind('\r', pos + 1, top + 1))
        if cut < pos + limit // 2:
            cut = next((c for c in range(top, pos, -1) if text[c].isspace()), None)
        if cut is None:
            cut = top
            while cut > pos + 1 and unicodedata.combining(text[cut]): cut -= 1
        end = cut
        while text[end - 1].isspace(): end -= 1
        pieces.append((pos, end)); pos = cut
        while pos < e and text[pos].isspace(): pos += 1
    if pos < e:
        pieces.append((pos, e))
    return pieces


class Embedder(Protocol):
    """What a real embedding model must provide to plug in (docs/MEANING_SEARCH.md).

    `name` names the exact model and configuration; `dimensions` is the vector length;
    `embed(texts)` returns one vector per text, in order, each of unit length or all
    zeros, the same numbers for the same text on every run, offline.
    """
    name: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[Sequence[float]]: ...


def _texts(texts):
    if type(texts) not in (list, tuple) or any(not isinstance(t, str) or len(t) > MAX_TEXT_CHARACTERS for t in texts):
        raise Fault('invalid_texts')
    return texts


def _features(word, dimensions):
    """One word's hashed slots: the word itself, weight 1, and its character trigrams, together weight 1."""
    padded = '<' + word + '>'
    grams = [padded[i:i + 3] for i in range(len(padded) - 2)]
    slots = {}
    for kind, feature, weight in [('w', word, 1.0)] + [('c', g, 1 / math.sqrt(len(grams))) for g in grams]:
        h = hashlib.blake2b(f'{kind}\0{feature}'.encode('utf-8', 'surrogatepass'), digest_size=8, person=b'alfred-sem-v1').digest()
        slot = int.from_bytes(h[:4], 'big') % dimensions
        slots[slot] = slots.get(slot, 0.0) + (weight if h[4] & 1 else -weight)
    return tuple(sorted(slots.items()))


class HashingEmbedder:
    """Deterministic hashed words and character trigrams. A baseline and test double, not a model.

    Text is NFKC normalised and case folded, so `BUDGET`, `budget` and composed or decomposed
    accents agree. Slots and signs come from BLAKE2b, never Python's per-process `hash()`, so
    vectors are identical across processes on the same Python version. Words are read as
    `\\w+` and their first 64 characters used. Text with no word gives the zero vector.
    """

    def __init__(self, dimensions=256):
        if type(dimensions) is not int or not 16 <= dimensions <= MAX_DIMENSIONS:
            raise Fault('invalid_dimensions')
        self.dimensions, self.name = dimensions, f'alfred-hashing-v1-d{dimensions}'

    def embed(self, texts):
        # Word slots are reused within one call only: nothing derived from a note's words
        # outlives the call, so a removed note leaves nothing behind in the embedder.
        seen = {}
        return [self._vector(t, seen) for t in _texts(texts)]

    def _vector(self, text, seen):
        vector = [0.0] * self.dimensions
        for word in _WORD.findall(unicodedata.normalize('NFKC', text).casefold()):
            word = word[:MAX_WORD]
            slots = seen.get(word)
            if slots is None:
                slots = seen[word] = _features(word, self.dimensions)
            for slot, weight in slots:
                vector[slot] += weight
        norm = math.sqrt(math.sumprod(vector, vector))
        return [x / norm for x in vector] if norm > 1e-9 else [0.0] * self.dimensions


def _locators(note_id, items):
    if type(items) not in (list, tuple):
        raise Fault('invalid_passage')
    checked, previous = [], 0
    for n, p in enumerate(items):
        if type(p) is not dict or set(p) != PASSAGE_KEYS or p['note_id'] != note_id or type(p['text']) is not str:
            raise Fault('invalid_passage')
        numbers = [p[k] for k in ('index', 'start', 'end', 'start_line', 'end_line')]
        path = p['heading_path']
        if (any(type(x) is not int for x in numbers) or p['index'] != n or not previous <= p['start'] < p['end']
                or p['end'] - p['start'] > MAX_PASSAGE_CHARACTERS or len(p['text']) != p['end'] - p['start']
                or not 1 <= p['start_line'] <= p['end_line'] or type(path) not in (list, tuple)
                or any(type(h) is not str for h in path) or p['sha256'] != _digest(p['text'])):
            raise Fault('invalid_passage')
        previous = p['end']
        names = [h for h in path if h.strip()]
        checked.append(({k: p[k] for k in ('index', 'start', 'end', 'start_line', 'end_line', 'sha256')} | {'heading_path': tuple(path)},
                        ' > '.join(names) + '\n\n' + p['text'] if names else p['text']))
    return checked


class Index:
    """Brute-force cosine search over one scope's authorised passages, in memory only.

    The caller adds only notes the scope's credential may read, removes them when access or
    the note goes, and rechecks every hit before showing it. Each index keeps its own
    records; nothing is shared between indexes, written to disk, pickled or copied.
    """

    def __init__(self, embedder, *, scope):
        self.scope = ident(scope)
        name, dimensions = getattr(embedder, 'name', None), getattr(embedder, 'dimensions', None)
        if (not isinstance(name, str) or not _NAME.fullmatch(name) or type(dimensions) is not int
                or not 2 <= dimensions <= MAX_DIMENSIONS or not callable(getattr(embedder, 'embed', None))):
            raise Fault('invalid_embedder')
        self.embedder, self._name, self._dimensions = embedder, name, dimensions
        self._notes, self._count = {}, 0

    def __reduce_ex__(self, protocol):
        raise TypeError('a meaning index is held in memory only and is never saved or copied')

    def __getstate__(self):
        raise TypeError('a meaning index is held in memory only and is never saved or copied')

    def __repr__(self):
        return f'<Index scope={self.scope!r} embedder={self._name!r} passages={self._count}>'

    def __len__(self):
        return self._count

    def __contains__(self, note_id):
        return note_id in self._notes

    def revision(self, note_id):
        entry = self._notes.get(ident(note_id))
        return entry[0] if entry else None

    def _embed(self, texts):
        vectors = self.embedder.embed(list(texts))
        if type(vectors) not in (list, tuple) or len(vectors) != len(texts):
            raise Fault('invalid_embedding')
        checked = []
        for v in vectors:
            if (type(v) not in (list, tuple) or len(v) != self._dimensions
                    or any(type(x) not in (float, int) or not math.isfinite(x) for x in v)):
                raise Fault('invalid_embedding')
            v = tuple(float(x) for x in v)
            square = math.sumprod(v, v)
            if square and abs(square - 1.0) > NORM_TOLERANCE:
                raise Fault('invalid_embedding')
            checked.append(v if square else None)
        return checked

    def add(self, note_id, revision, items):
        """Index one note revision's passages, replacing every passage of an older revision.

        All or nothing: a refused or failed call leaves the index as it was. An older
        revision is refused, and the same revision is accepted only with the same passages.
        """
        ident(note_id)
        if type(revision) is not int or not 1 <= revision <= 2**53:
            raise Fault('invalid_revision')
        checked = _locators(note_id, items)
        current = self._notes.get(note_id)
        if current:
            if revision < current[0]:
                raise Fault('stale_revision', 409)
            if revision == current[0]:
                if [loc for loc, _ in checked] == list(current[1]):
                    return
                raise Fault('revision_conflict', 409)
        if not checked:
            self.remove(note_id); return
        count = self._count - (len(current[1]) if current else 0) + len(checked)
        if count > MAX_PASSAGES:
            raise Fault('index_capacity')
        vectors = self._embed([text for _, text in checked])
        self._notes[note_id] = (revision, tuple(loc for loc, _ in checked), tuple(vectors))
        self._count = count

    def remove(self, note_id):
        entry = self._notes.pop(ident(note_id), None)
        if entry:
            self._count -= len(entry[1])
        return len(entry[1]) if entry else 0

    def search(self, query, k):
        """The k passages most similar to the query: score descending, then note ID, then start."""
        if not isinstance(query, str) or not query.strip():
            raise Fault('query_required')
        if len(query) > MAX_QUERY_CHARACTERS:
            raise Fault('query_too_long')
        if type(k) is not int or not 1 <= k <= MAX_K:
            raise Fault('invalid_k')
        [q] = self._embed([query])
        if q is None:
            return []
        scored = ((math.sumprod(q, v), note_id, revision, loc)
                  for note_id, (revision, locs, vectors) in self._notes.items()
                  for loc, v in zip(locs, vectors) if v is not None)
        best = heapq.nsmallest(k, scored, key=lambda r: (-r[0], r[1], r[3]['start']))
        return [{'scope': self.scope, 'embedder': self._name, 'note_id': note_id, 'revision': revision,
                 **loc, 'heading_path': list(loc['heading_path']), 'score': min(1.0, max(-1.0, score))}
                for score, note_id, revision, loc in best]


def passage_text(hit, revision, text):
    """The hit's passage from the note as read now, refused if the note moved on since indexing."""
    if not isinstance(text, str):
        raise Fault('note_text_required')
    piece = text[hit['start']:hit['end']]
    if revision != hit['revision'] or _digest(piece) != hit['sha256']:
        raise Fault('passage_changed', 409)
    return piece


def best_per_note(hits):
    """Note IDs in the order of each note's best passage, for blending with note-level keyword ranks."""
    return list(dict.fromkeys(h['note_id'] for h in hits))


def blend(keyword_ranked, meaning_ranked, k=60):
    """Reciprocal rank fusion of two ranked ID lists: each ID scores the sum of 1/(k + rank).

    Ranks start at 1. An ID listed twice in one list is refused. Scores are summed exactly;
    ties go to the better single rank, then the better keyword rank, then the ID.
    """
    if type(k) is not int or not 1 <= k <= MAX_RRF_K:
        raise Fault('invalid_rrf_k')
    ranks = {}
    for source, ranked in (('keyword', keyword_ranked), ('meaning', meaning_ranked)):
        if type(ranked) not in (list, tuple):
            raise Fault('invalid_ranked_list')
        if len(ranked) > MAX_RANKED:
            raise Fault('ranked_list_too_long')
        if any(not isinstance(i, str) or not 1 <= len(i) <= MAX_RANKED_ID for i in ranked):
            raise Fault('invalid_ranked_id')
        if len(set(ranked)) != len(ranked):
            raise Fault('duplicate_ranked_id')
        for rank, identity in enumerate(ranked, 1):
            ranks.setdefault(identity, {})[source] = rank
    fused = []
    for identity, found in ranks.items():
        score = sum((Fraction(1, k + r) for r in found.values()), Fraction(0))
        fused.append(((-score, min(found.values()), found.get('keyword', MAX_RANKED + 1), identity), score, identity, found))
    return [{'id': identity, 'score': float(score), 'sources': [s for s in ('keyword', 'meaning') if s in found],
             'keyword_rank': found.get('keyword'), 'meaning_rank': found.get('meaning')}
            for _, score, identity, found in sorted(fused)]
