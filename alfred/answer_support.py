"""What supports one answer, stated plainly and deterministically (INT-002).

For every answer, ALFRED reports which of the question's own words were found (a shown
word starting with the asked word) in the excerpts and reviewed statements it is about to
show, which were not found, how many reviewed statements about the subjects asked about
were withheld and why (conflicting, disputed or not current), which sources were skipped
because they changed or became unavailable, what earlier questions shaped a follow-up,
and whether a model was used and what its review found.

This is coverage and accounting, not truth. A found word is not an answer, and a word
that is not found may be phrased differently in the person's notes. No model is used to
produce this report, and it never changes what the answer contains.
"""
from __future__ import annotations
from collections import Counter
import re

VERSION = 1
BASIS = 'deterministic_term_coverage_not_truth_or_entailment'
LIMITS = ('Counts and word matches only (a shown word starting with the asked word). A found word is '
          'not an answer, a word that is not found may be phrased differently in your notes, and contradictions inside note text '
          'are not detected; only conflicting reviewed statements are.')


def _words(text):
    return set(re.findall(r'\w+', text.casefold()))


def assess(packet, result, asked):
    """Return the support report for one answer. `asked` are the current question's own terms."""
    shown = set()
    for item in packet['evidence']:
        shown |= _words(item['title'] + '\n' + item['excerpt'])
    for statement in packet['memory']:
        for part in (statement.get('subject'), statement.get('object')):
            if isinstance(part, dict):
                shown |= _words(part.get('name') or '')
        shown |= _words((statement.get('predicate') or '').replace('_', ' ') + ' ' + (statement.get('value') or ''))
    # A word counts as found when a shown word starts with it ("open" finds "opens"),
    # close to retrieval's own substring matching without matching inside other words.
    found = [t for t in asked if any(w.startswith(t) for w in shown)]
    missing = [t for t in asked if t not in found]
    withheld = dict(packet.get('memory_withheld') or {})
    review = result.get('evidence_review') or {}
    if not packet['evidence'] and not packet['memory']:
        status = 'nothing_found'
    elif missing:
        status = 'partly_covered'
    else:
        status = 'all_words_found'
    return {
        'version': VERSION, 'status': status,
        'words': {'asked': list(asked), 'found': found, 'not_found': missing},
        'evidence': {'excerpts': len(packet['evidence']), 'notes': len({e['note_id'] for e in packet['evidence']}),
                     'retrieved_via': dict(sorted(Counter(e['retrieved_via'] for e in packet['evidence']).items()))},
        'reviewed_statements': {'used': len(packet['memory']), 'withheld': withheld,
                                'ambiguous_names': sorted({a['name'] for a in packet['memory_ambiguities']})},
        'skipped_sources': dict(sorted(Counter(s['reason'] for s in packet.get('skipped', [])).items())),
        'context': {'earlier_questions': len(packet.get('conversation_questions') or []),
                    'selected_record': bool(packet.get('focus'))},
        'model': {'used': bool(result.get('model_used')), 'claims': len(result.get('claims') or []),
                  'review': review.get('status'), 'issues': sorted({i['code'] for i in review.get('issues', [])})},
        'basis': BASIS, 'limits': LIMITS, 'truth_verified': False, 'entailment_verified': False,
    }
