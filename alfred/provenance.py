"""Where each value in a brain's proposed action came from (docs/PROVENANCE_GATE.md).

A brain reads two kinds of text in its task packet. The owner's own words say what the
owner wants: the goal statement, the instruction and the owner-reviewed learned
statements. Note excerpts, titles included, are data: anything written in a note or an
email, including text planted there to look like an instruction. This module labels each
proposed action with what in it came from which kind, so that data can never steer an
action by itself. It is the CaMeL idea (Google research, 2025) applied at ALFRED's gate,
written here from the idea, with no code taken from any implementation of it.

A **place** is a value that decides where an effect goes or whom it reaches: an email
address, a web address, a bare domain (with any path), a social handle or a phone number.
Every place in an action's parameter values must appear in the owner's own words. One
found only in an excerpt, or nowhere at all (a brain can decode an address spelled out in
a note), makes the verdict ``steered_by_untrusted_text``. Without such a place, an action
that cites an excerpt or copies a run of its words is ``uses_untrusted_text``: drafting
from notes is ordinary data use, so it is labelled, not held. Otherwise ``owner_only``.

Text is compared after NFKC normalisation, removal of invisible format characters and
case folding. The patterns are a tripwire, not proof of origin: a brain can paraphrase
or encode a value so no pattern sees it, and nothing here reads intent. Approval with the
exact fingerprint stays the decision for every action. Pure functions; no I/O.
"""
from __future__ import annotations
import re
import unicodedata

MODES = ('off', 'watch', 'enforce')
DEFAULT_MODE = 'enforce'
LABEL_VERSION = 1
BASIS = 'pattern_tripwire_not_proof_of_origin'
OWNER_ONLY, USES, STEERED = 'owner_only', 'uses_untrusted_text', 'steered_by_untrusted_text'
COPY_RUN = 6  # Consecutive words shared with an excerpt, and not with the owner, that count as copying.

# File names look like domains ("notes.md"); these endings are never read as one.
FILE_ENDINGS = frozenset({'md', 'txt', 'pdf', 'csv', 'json', 'py', 'js', 'ts', 'html', 'htm', 'css', 'xml', 'yml',
                          'yaml', 'toml', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'doc', 'docx', 'xls', 'xlsx', 'ppt',
                          'pptx', 'zip', 'log', 'db', 'sh', 'ics'})
TRAILING = '.,;:!?)]}\'">'
PLACE = re.compile(r'''
    (?P<url>(?<![\w.+-])(?:[a-z][a-z0-9+.-]*://|mailto:|www\.)\S+)
  | (?P<email>(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+)
  | (?P<handle>(?<![\w@.])@\w{2,30})
  | (?P<domain>(?<![\w@./-])(?:[^\W_](?:[\w-]*[^\W_])?\.)+(?P<end>[^\W\d_]{2,24})(?![\w-])(?:/\S*)?)
  | (?P<phone>(?<![\w+])(?:\+|0)\d[\d ()-]{7,}\d)
''', re.VERBOSE)


def normalise(value: str) -> str:
    """NFKC, without invisible format characters (zero-width spaces and the like), case folded."""
    value = unicodedata.normalize('NFKC', value)
    return ''.join(c for c in value if unicodedata.category(c) != 'Cf').casefold()


def places(value: str) -> list:
    """``(kind, value)`` for each place in ``value``, normalised, in order of appearance."""
    found = []
    for m in PLACE.finditer(normalise(value)):
        kind = m.lastgroup if m.lastgroup != 'end' else 'domain'
        shown = m.group(kind)
        if kind == 'phone':
            digits = re.sub(r'\D', '', shown)
            if not 9 <= len(digits) <= 15:
                continue
            shown = ('+' if shown.startswith('+') else '') + digits
        else:
            shown = shown.rstrip(TRAILING)
        if kind == 'domain' and m.group('end') in FILE_ENDINGS:
            continue
        found.append((kind, shown))
    return found


_RAW = re.compile(PLACE.pattern, re.VERBOSE | re.IGNORECASE)


def replace(value: str, kind: str, held: str, new: str) -> tuple:
    """``(text, count)``: ``value`` with each place of ``kind`` that normalises to ``held``
    replaced by ``new``, as written, leaving the words and punctuation around it alone. A
    place disguised with invisible characters is not found here, so it is never swapped."""
    parts, last, count = [], 0, 0
    for m in _RAW.finditer(value):
        span = m.group(0)
        if (m.lastgroup if m.lastgroup != 'end' else 'domain') != 'phone':
            span = span.rstrip(TRAILING)
        if places(span) != [(kind, held)]:
            continue
        parts += [value[last:m.start()], new]
        last, count = m.start() + len(span), count + 1
    return ''.join(parts) + value[last:], count


def _words(value: str) -> list:
    return re.findall(r'\w+', normalise(value))


def _runs(value: str) -> set:
    words = _words(value)
    return {tuple(words[i:i + COPY_RUN]) for i in range(len(words) - COPY_RUN + 1)}


def _values(value):
    """Every string value in an action's parameters, nested lists and objects included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _values(item)


def _ordered(refs) -> list:
    return sorted(set(refs), key=lambda ref: (ref[0], int(ref[1:])))


def label(packet: dict, action: dict) -> dict:
    """The provenance label for one proposed action of a packet's result bundle.

    ``packet`` needs its goal, instruction, context and learned fields; ``action`` its
    parameters and cites. The action's reason is the brain's own claim and never clears
    a place."""
    owner_text = [packet['goal']['statement'], packet['instruction'], *(item['statement'] for item in packet['learned'])]
    owner_places = {key for text in owner_text for key in places(text)}
    owner_runs = set().union(*map(_runs, owner_text))
    excerpts = [(item['id'], item['title'] + '\n' + item['text']) for item in packet['context']]
    excerpt_places = {ref: set(places(text)) for ref, text in excerpts}
    excerpt_runs = {ref: _runs(text) - owner_runs for ref, text in excerpts}
    seen, listed, copied = set(), [], set()
    for value in _values(action['parameters']):
        for key in places(value):
            if key in seen:
                continue
            seen.add(key)
            refs = [] if key in owner_places else _ordered(r for r, keys in excerpt_places.items() if key in keys)
            source = 'owner' if key in owner_places else 'excerpt' if refs else 'unsourced'
            listed.append({'kind': key[0], 'value': key[1], 'source': source, 'refs': refs})
        runs = _runs(value)
        copied.update(ref for ref, shared in excerpt_runs.items() if runs & shared)
    cited = _ordered(ref for ref in action['cites'] if ref.startswith('E'))
    if any(p['source'] != 'owner' for p in listed):
        verdict = STEERED
    elif cited or copied:
        verdict = USES
    else:
        verdict = OWNER_ONLY
    return {'label_version': LABEL_VERSION, 'verdict': verdict, 'places': listed, 'cited': cited,
            'copied': _ordered(copied), 'basis': BASIS}
