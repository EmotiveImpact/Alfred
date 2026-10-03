"""INT-002: the per-answer support report. Deterministic coverage and accounting, never truth.

Synthetic notes, real SQLite and the real conversation queue in source mode. No model.
"""
from pathlib import Path
import tempfile
import unittest
from alfred.answer_support import assess
from alfred.conversation import ConversationService
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.reviewed_memory import ReviewedMemory


def packet(evidence=(), memory=(), **extra):
    return {'evidence': list(evidence), 'memory': list(memory), 'memory_ambiguities': [], **extra}


def excerpt(note, title, text, via='keyword_match'):
    return {'note_id': note, 'title': title, 'excerpt': text, 'retrieved_via': via}


class AssessTests(unittest.TestCase):
    def test_nothing_found_is_reported_as_such(self):
        report = assess(packet(), {'model_used': False, 'claims': []}, ['budget'])
        self.assertEqual((report['status'], report['words']['not_found']), ('nothing_found', ['budget']))
        self.assertFalse(report['truth_verified'] or report['entailment_verified'])

    def test_words_are_found_only_in_what_is_shown(self):
        report = assess(packet([excerpt('n1', 'Atlas', 'Atlas is awaiting review.')]), {'model_used': False}, ['atlas', 'budget'])
        self.assertEqual((report['status'], report['words']['found'], report['words']['not_found']), ('partly_covered', ['atlas'], ['budget']))
        full = assess(packet([excerpt('n1', 'Atlas', 'The Atlas budget is fixed.')]), {'model_used': False}, ['atlas', 'budget'])
        self.assertEqual(full['status'], 'all_words_found')

    def test_inflected_words_count_as_found_but_words_inside_other_words_do_not(self):
        # Found by the evaluation: "open" must find "opens", as retrieval already does.
        report = assess(packet([excerpt('n1', 'Harbour', 'Harbour opens in spring. Confirmation pending.')]), {'model_used': False},
                        ['harbour', 'open', 'ring', 'confirming', 'sting'])
        self.assertEqual((report['words']['found'], report['words']['not_found']), (['harbour', 'open', 'confirming'], ['ring', 'sting']))

    def test_reviewed_statements_count_as_shown_and_withheld_ones_are_only_counted(self):
        statement = {'subject': {'name': 'Atlas'}, 'object': None, 'predicate': 'budget_status', 'value': 'approved'}
        report = assess(packet([], [statement], memory_withheld={'conflicting': 2}), {'model_used': False}, ['atlas', 'budget'])
        self.assertEqual(report['words']['found'], ['atlas', 'budget'])
        self.assertEqual(report['reviewed_statements'], {'used': 1, 'withheld': {'conflicting': 2}, 'ambiguous_names': []})

    def test_model_review_findings_and_context_are_carried(self):
        review = {'status': 'withheld_for_review', 'issues': [{'code': 'number_not_in_cited_text', 'blocking': True}]}
        report = assess(packet([excerpt('n1', 'Atlas', 'Atlas')], conversation_questions=['earlier'], focus={'record_id': 'note:x'},
                               skipped=[{'note_id': 'n2', 'reason': 'source_changed'}]),
                        {'model_used': True, 'claims': [], 'evidence_review': review}, ['atlas'])
        self.assertEqual(report['model'], {'used': True, 'claims': 0, 'review': 'withheld_for_review', 'issues': ['number_not_in_cited_text']})
        self.assertEqual(report['context'], {'earlier_questions': 1, 'selected_record': True})
        self.assertEqual(report['skipped_sources'], {'source_changed': 1})


class ConversationSupportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.store = KnowledgeStore(root / 'desk.sqlite')
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=100000, legacy_scope=True)
        source = self.store.provision('work', 'source', 'source', ttl=100000, legacy_scope=True)
        vault = root / 'vault'; vault.mkdir()
        (vault / 'Atlas.md').write_text('# Atlas\nAtlas is awaiting review.\nAtlas is approved.\n')
        MarkdownVault(self.store, source, vault).scan()
        self.service = ConversationService(self.store, None, 'work'); self.addCleanup(self.service.stop)
        self.session = self.service.create(self.owner, {'title': 'Atlas'})['id']

    def ask(self, question, request, follow_up=False):
        after = len(self.service.view(self.owner, self.session)['turns'])
        self.service.submit(self.owner, self.session, {'question': question, 'mode': 'sources', 'follow_up': follow_up,
                                                        'request_id': request, 'after': after})
        self.service.process_one()
        return self.service.view(self.owner, self.session)['turns'][-1]['result']

    def test_every_answer_states_what_was_and_was_not_found(self):
        result = self.ask('What is the Atlas budget?', 'q1')
        support = result['support']
        self.assertEqual(support['status'], 'partly_covered')
        self.assertIn('budget', support['words']['not_found'])
        self.assertIn('atlas', support['words']['found'])
        self.assertEqual(support['basis'], 'deterministic_term_coverage_not_truth_or_entailment')
        follow = self.ask('And the status?', 'q2', follow_up=True)['support']
        self.assertEqual(follow['context']['earlier_questions'], 1)
        self.assertEqual(follow['words']['asked'], ['status'])

    def test_conflicting_reviewed_statements_are_counted_never_shown(self):
        memory = ReviewedMemory(self.store)
        memory.create_entity(self.owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas'})
        note = self.store.knowledge(self.owner)['nodes'][0]
        for request, line, value in (('a', 2, 'awaiting review'), ('b', 3, 'approved')):
            made = memory.propose(self.owner, {'request_id': request, 'subject_id': 'atlas', 'predicate': 'status', 'object_id': None,
                                               'value': value, 'valid_from': None, 'valid_until': None,
                                               'evidence': {'note_id': note['id'], 'sha256': note['sha256'], 'revision': note['revision'],
                                                            'start_line': line, 'end_line': line}})
            memory.review(self.owner, made['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        # A withheld statement about another subject sharing the predicate is not counted.
        memory.create_entity(self.owner, {'id': 'lantern', 'kind': 'project', 'name': 'Lantern'})
        made = memory.propose(self.owner, {'request_id': 'c', 'subject_id': 'lantern', 'predicate': 'status', 'object_id': None,
                                           'value': 'awaiting review', 'valid_from': None, 'valid_until': None,
                                           'evidence': {'note_id': note['id'], 'sha256': note['sha256'], 'revision': note['revision'],
                                                        'start_line': 2, 'end_line': 2}})
        self.assertEqual(made['state'], 'proposed')
        result = self.ask('What is the Atlas status?', 'q3')
        self.assertEqual(result['packet']['memory'], [])
        self.assertEqual(result['support']['reviewed_statements']['withheld'], {'conflicting': 2})
        self.assertNotIn('approved', str(result['support']))


if __name__ == '__main__':
    unittest.main()
