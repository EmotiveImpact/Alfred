"""Deterministic answer-support evaluation for INT-002, in source mode only.

Asks fixed, invented questions through the real conversation queue over a fixed,
invented vault and reviewed statements, then compares each answer's support report
with the expectation written here. Expectations are used only for scoring, after every
answer has been produced; they never reach retrieval or the answer.

No model, provider, network, private vault or third_party code is used, and the blocked
live-model comparison is not run or rerouted. Every case, the denominators and every
failed case are written to the report. A "limitation" case records behaviour that is
correct for these literal checks but would mislead if read as understanding, such as a
paraphrase reported as not found.

    python3 tools/evaluate_answers.py --output report.json
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alfred.conversation import ConversationService  # noqa: E402
from alfred.knowledge import KnowledgeStore, MarkdownVault  # noqa: E402
from alfred.policy import IdentityPolicy  # noqa: E402
from alfred.reviewed_memory import ReviewedMemory  # noqa: E402

SCHEMA = 'alfred.answer-support-evaluation.v1'
FIXED_NOW = 1790000000
NOTES = {
    'Atlas.md': '# Atlas\nAtlas is awaiting review.\nAtlas is approved.\nThe Atlas price is 40 pounds.\n',
    'Harbour.md': '# Harbour\nHarbour opens in spring.\nHarbour is led by Mina.\n',
    'Lantern.md': '# Lantern\nLantern status is on hold.\nLantern was paused last week.\n',
}
RESTRICTED = {'Vault Room.md': '# Vault Room\nThe Zephyr code word lives here.\n'}
# (id, category, question, follow_up, expectation). Expectations name only support-report fields.
CASES = [
    ('found-1', 'found', 'When does Harbour open?', False, {'status': 'all_words_found'}),
    ('found-2', 'found', 'Who leads Harbour?', False, {'found_includes': ['harbour']}),
    ('found-3', 'found', 'Is Lantern pausing?', False, {'found_includes': ['lantern', 'pausing']}),
    ('missing-1', 'missing', 'What is the Harbour budget?', False, {'not_found_includes': ['budget'], 'status': 'partly_covered'}),
    ('missing-2', 'missing', 'Which supplier delivers the turbines?', False, {'status': 'nothing_found'}),
    ('conflict-1', 'conflict', 'What is the Atlas status?', False, {'withheld': {'conflicting': 2}, 'statements_used': 0}),
    ('disputed-1', 'disputed', 'Who leads Harbour?', False, {'withheld_includes': 'disputed'}),
    ('changed-1', 'changed', 'What is the Lantern status?', False, {'withheld_includes': 'needs_fresh_review'}),
    ('valid-1', 'valid_time', 'When does Harbour open?', False, {'withheld_includes': 'outside_valid_period'}),
    ('restricted-1', 'access', 'Where does the Zephyr code word live?', False, {'not_found_includes': ['zephyr'], 'no_text': 'Zephyr code word lives'}),
    ('followup-1', 'context', 'Who leads Harbour?', False, {'earlier_questions': 0}),
    ('followup-2', 'context', 'And when does it open?', True, {'earlier_questions': 1, 'asked': ['open']}),
    ('paraphrase-1', 'limitation', 'How much does Atlas cost?', False, {'not_found_includes': ['cost'], 'limitation': 'The price is in the note, but "cost" is a different word, so it is reported as not found.'}),
]


def _accept(memory, owner, request, subject, predicate, value, note, line, *, valid=(None, None), decision='accept', obj=None):
    made = memory.propose(owner, {'request_id': request, 'subject_id': subject, 'predicate': predicate, 'object_id': obj, 'value': value,
                                  'valid_from': valid[0], 'valid_until': valid[1],
                                  'evidence': {'note_id': note['id'], 'sha256': note['sha256'], 'revision': note['revision'],
                                               'start_line': line, 'end_line': line}})
    memory.review(owner, made['id'], {'version': 1, 'decision': decision, 'replaces_id': None, 'replaces_version': None})


def build(root, clock):
    """The fixed corpus, statements and grants on a controlled clock. Returns (store, owner)."""
    store = KnowledgeStore(root / 'desk.sqlite', clock=lambda: clock[0])
    owner = store.provision('evaluation', 'owner', 'owner', ttl=2592000, legacy_scope=True)
    main = store.provision('evaluation', 'notes', 'source', ttl=2592000, legacy_scope=True)
    hidden = store.provision('evaluation', 'restricted', 'source', ttl=2592000, legacy_scope=True)
    vault, other = root / 'vault', root / 'restricted'
    for folder, notes, bearer in ((vault, NOTES, main), (other, RESTRICTED, hidden)):
        folder.mkdir()
        for name, body in notes.items():
            (folder / name).write_text(body)
        MarkdownVault(store, bearer, folder).scan()
    policy = IdentityPolicy(store)
    policy.grant(owner, 'notes', 'read', store.now() + 86400, policy.view(owner)['epoch'])
    memory = ReviewedMemory(store)
    notes = {n['title']: n for n in store.knowledge(owner)['nodes']}
    for entity, kind in (('atlas', 'project'), ('harbour', 'project'), ('lantern', 'project'), ('mina', 'person')):
        memory.create_entity(owner, {'id': entity, 'kind': kind, 'name': entity.capitalize()})
    _accept(memory, owner, 'a1', 'atlas', 'status', 'awaiting review', notes['Atlas'], 2)
    _accept(memory, owner, 'a2', 'atlas', 'status', 'approved', notes['Atlas'], 3)
    _accept(memory, owner, 'h1', 'harbour', 'responsible_person', None, notes['Harbour'], 3, decision='dispute', obj='mina')
    _accept(memory, owner, 'h2', 'harbour', 'scheduled_for', 'spring', notes['Harbour'], 2, valid=(1, 2))
    _accept(memory, owner, 'l1', 'lantern', 'status', 'on hold', notes['Lantern'], 2)
    (vault / 'Lantern.md').write_text('# Lantern\nLantern status is active again.\nLantern was paused last week.\n')
    MarkdownVault(store, main, vault).scan()
    return store, owner


def score(case, result):
    """Compare one support report with its expectation. Returns a list of failures."""
    _, _, _, _, expect = case
    support, failures = result['support'], []
    words, statements = support['words'], support['reviewed_statements']
    checks = {
        'status': lambda v: support['status'] == v,
        'found_includes': lambda v: set(v) <= set(words['found']),
        'not_found_includes': lambda v: set(v) <= set(words['not_found']),
        'withheld': lambda v: statements['withheld'] == v,
        'withheld_includes': lambda v: statements['withheld'].get(v, 0) > 0,
        'statements_used': lambda v: statements['used'] == v,
        'earlier_questions': lambda v: support['context']['earlier_questions'] == v,
        'asked': lambda v: words['asked'] == v,
        'no_text': lambda v: v not in json.dumps(result),
        'limitation': lambda v: True,
    }
    for key, value in expect.items():
        if not checks[key](value):
            failures.append(key)
    return failures


def evaluate():
    with tempfile.TemporaryDirectory() as temporary:
        clock = [FIXED_NOW]
        store, owner = build(Path(temporary), clock)
        service = ConversationService(store, None, 'evaluation')
        try:
            session, results = service.create(owner, {'title': 'Evaluation'})['id'], []
            for index, case in enumerate(CASES):
                identifier, category, question, follow_up, expect = case
                clock[0] += 120  # Keeps the fixed questions inside the per-minute question limit.
                if not follow_up:
                    session = service.create(owner, {'title': identifier})['id']
                after = len(service.view(owner, session)['turns'])
                service.submit(owner, session, {'question': question, 'mode': 'sources', 'follow_up': follow_up,
                                                'request_id': f'eval-{index}', 'after': after})
                service.process_one()
                turn = service.view(owner, session)['turns'][-1]
                results.append((case, turn['result']))
        finally:
            service.stop()
    cases, totals = [], {'asked': 0, 'found': 0, 'not_found': 0}
    for case, result in results:
        failures = score(case, result)
        support = result['support']
        for key in totals:
            totals[key] += len(support['words'][key])
        cases.append({'id': case[0], 'category': case[1], 'question': case[2], 'follow_up': case[3], 'expected': case[4],
                      'observed': {'status': support['status'], 'words': support['words'],
                                   'reviewed_statements': support['reviewed_statements'], 'context': support['context']},
                      'passed': not failures, 'failed_checks': failures})
    failed = [c for c in cases if not c['passed']]
    categories = sorted({c['category'] for c in cases})
    return {'schema': SCHEMA, 'mode': 'sources_only_no_model', 'cases': cases,
            'denominators': {'cases': len(cases), 'passed': len(cases) - len(failed), 'failed': len(failed),
                             'by_category': {k: {'cases': sum(c['category'] == k for c in cases),
                                                 'passed': sum(c['category'] == k and c['passed'] for c in cases)} for k in categories},
                             'words': totals},
            'failed_cases': [{'id': c['id'], 'failed_checks': c['failed_checks']} for c in failed],
            'limitations': [{'id': c['id'], 'note': c['expected']['limitation']} for c in cases if 'limitation' in c['expected']],
            'claims': 'Literal coverage and accounting only. Not truth, entailment, completeness or model quality.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = evaluate()
    text = json.dumps(report, indent=1, ensure_ascii=False) + '\n'
    if args.output:
        args.output.write_text(text)
    print(json.dumps(report['denominators'] | {'failed_cases': report['failed_cases']}))
    return 1 if report['failed_cases'] else 0


if __name__ == '__main__':
    sys.exit(main())
