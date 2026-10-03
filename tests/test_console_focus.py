"""Selected-record context for questions (console Stage B), on the existing queue.

A selection narrows retrieval. It is re-authorised on every use, never becomes
evidence by itself, never grants access and is withdrawn when its record is.
Synthetic notes only; the provider is a declared fixture, not a model.
"""
from pathlib import Path
import tempfile
import unittest
from alfred.local import Fault
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.conversation import ConversationService
from alfred.grounded import retrieve
from alfred.policy import IdentityPolicy
from alfred.reviewed_memory import ReviewedMemory


class FocusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name); self.clock = [1000]
        self.store = KnowledgeStore(root / 'desk.db', clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=100000, legacy_scope=True)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=100000, legacy_scope=True)
        self.source = self.store.provision('work', 'source', 'source', ttl=100000, legacy_scope=True)
        self.vault = root / 'vault'; self.vault.mkdir()
        (self.vault / 'Atlas.md').write_text('# Atlas project\nAtlas launches after the review.\n[[Budget]]\n')
        (self.vault / 'Budget.md').write_text('# Budget\nThe budget is provisional.\n')
        (self.vault / 'Weather.md').write_text('# Weather\nRain expected on Tuesday.\n')
        self.scanner = MarkdownVault(self.store, self.source, self.vault); self.scanner.scan()
        other_source = self.store.provision('elsewhere', 'other-source', 'source', ttl=100000, legacy_scope=True)
        self.other_owner = self.store.provision('elsewhere', 'other-owner', 'owner', ttl=100000, legacy_scope=True)
        other = root / 'other'; other.mkdir(); (other / 'Secret.md').write_text('# Secret\nAnother workspace.\n')
        MarkdownVault(self.store, other_source, other).scan()
        self.memory = ReviewedMemory(self.store)
        self.service = ConversationService(self.store, None, 'work'); self.addCleanup(self.service.stop)
        self.sid = self.service.create(self.owner, {'title': 'Focus'})['id']; self.seq = 0

    def note(self, title, bearer=None):
        return next(n for n in self.store.knowledge(bearer or self.owner)['nodes'] if n['title'] == title)

    def send(self, question, focus=None, **changes):
        body = {'question': question, 'mode': 'sources', 'follow_up': False, 'request_id': 'r' + str(self.seq), 'after': self.seq}
        if focus is not None or 'focus' in changes:
            body['focus'] = focus
        body.update(changes)
        value = self.service.submit(self.owner, self.sid, body); self.seq += 1
        self.service.process_one()
        return value, self.service.view(self.owner, self.sid)['turns'][-1]

    def test_selected_note_leads_retrieval_even_without_matching_terms(self):
        atlas = self.note('Atlas project')
        packet = retrieve(self.store, self.owner, 'What changed on Tuesday?', focus='note:' + atlas['id'])
        self.assertEqual((packet['evidence'][0]['note_id'], packet['evidence'][0]['retrieved_via']), (atlas['id'], 'selected_record'))
        self.assertEqual(packet['focus']['label'], 'Atlas project')
        self.assertEqual(packet['focus']['basis'], 'user_selection_context_not_authority')
        self.assertIn(self.note('Budget')['id'], [e['note_id'] for e in packet['evidence']])
        self.assertFalse(packet['authority_granted'])

    def test_without_focus_the_same_question_does_not_use_the_selection(self):
        packet = retrieve(self.store, self.owner, 'What changed on Tuesday?')
        self.assertNotIn(self.note('Atlas project')['id'], [e['note_id'] for e in packet['evidence']])
        self.assertIsNone(packet['focus'])

    def test_other_workspace_note_cannot_be_focused(self):
        hidden = self.store.knowledge(self.other_owner)['nodes'][0]['id']
        with self.assertRaises(Fault) as caught:
            retrieve(self.store, self.owner, 'Tell me more', focus='note:' + hidden)
        self.assertEqual(caught.exception.code, 'focus_not_available')

    def test_ungranted_source_cannot_be_focused_under_strict_policy(self):
        hidden_source = self.store.provision('work', 'hidden-source', 'source', ttl=100000, legacy_scope=True)
        folder = Path(self.tmp.name) / 'hidden'; folder.mkdir(); (folder / 'Private.md').write_text('# Private\nUngranted.\n')
        MarkdownVault(self.store, hidden_source, folder).scan()
        private = self.note('Private')['id']
        policy = IdentityPolicy(self.store)
        policy.grant(self.owner, 'source', 'read', 5000, policy.view(self.owner)['epoch'])
        with self.assertRaises(Fault) as caught:
            retrieve(self.store, self.owner, 'Tell me more', focus='note:' + private)
        self.assertEqual(caught.exception.code, 'focus_not_available')

    def test_invalid_focus_values_are_rejected(self):
        for value in ('note:../x', 'claim:abc', 'note:' + 'G' * 24, 'entity:', 7, ''):
            with self.assertRaises(Fault, msg=repr(value)) as caught:
                retrieve(self.store, self.owner, 'Tell me more', focus=value)
            self.assertEqual(caught.exception.code, 'invalid_focus')

    def accepted_statement(self):
        self.memory.create_entity(self.owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas'})
        atlas = self.note('Atlas project')
        claim = self.memory.propose(self.owner, {'request_id': 'q', 'subject_id': 'atlas', 'predicate': 'status', 'object_id': None,
                                                 'value': 'awaiting review', 'valid_from': None, 'valid_until': None,
                                                 'evidence': {'note_id': atlas['id'], 'sha256': atlas['sha256'], 'revision': atlas['revision'], 'start_line': 2, 'end_line': 2}})
        self.memory.review(self.owner, claim['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})

    def test_selected_entity_brings_its_reviewed_statements(self):
        self.accepted_statement()
        unfocused = retrieve(self.store, self.owner, 'What about rain?')
        self.assertEqual(unfocused['memory'], [])
        focused = retrieve(self.store, self.owner, 'What about rain?', focus='entity:atlas')
        self.assertEqual([m['value'] for m in focused['memory']], ['awaiting review'])
        self.assertEqual(focused['memory'][0]['basis'], 'user_reviewed_statement_not_verified_fact')
        self.assertEqual(focused['focus']['label'], 'Atlas')

    def test_reader_cannot_focus_another_actors_private_entity(self):
        self.accepted_statement()
        with self.assertRaises(Fault) as caught:
            retrieve(self.store, self.reader, 'Tell me more', focus='entity:atlas')
        self.assertEqual(caught.exception.code, 'focus_not_available')

    def test_conversation_persists_focus_and_completes(self):
        atlas = self.note('Atlas project')
        _, turn = self.send('What changed on Tuesday?', 'note:' + atlas['id'])
        self.assertEqual(turn['state'], 'completed')
        self.assertEqual(turn['focus'], 'note:' + atlas['id'])
        self.assertEqual(turn['result']['packet']['focus']['label'], 'Atlas project')
        self.assertEqual(turn['result']['packet']['evidence'][0]['retrieved_via'], 'selected_record')

    def test_same_request_with_different_focus_collides(self):
        atlas = self.note('Atlas project')
        body = {'question': 'What changed?', 'mode': 'sources', 'follow_up': False, 'request_id': 'same', 'after': 0, 'focus': 'note:' + atlas['id']}
        self.service.submit(self.owner, self.sid, body)
        self.assertTrue(self.service.submit(self.owner, self.sid, dict(body))['reused'])
        with self.assertRaises(Fault) as caught:
            self.service.submit(self.owner, self.sid, {**body, 'focus': None})
        self.assertEqual(caught.exception.code, 'conversation_request_collision')

    def test_focus_removed_before_processing_fails_honestly(self):
        atlas = self.note('Atlas project')
        self.service.submit(self.owner, self.sid, {'question': 'What changed?', 'mode': 'sources', 'follow_up': False,
                                                    'request_id': 'gone', 'after': 0, 'focus': 'note:' + atlas['id']})
        (self.vault / 'Atlas.md').unlink(); self.scanner.scan()
        self.service.process_one()
        turn = self.service.view(self.owner, self.sid)['turns'][-1]
        self.assertEqual((turn['state'], turn['result']), ('focus_unavailable', None))

    def test_changed_focus_note_withdraws_the_saved_answer(self):
        atlas = self.note('Atlas project')
        self.send('What changed?', 'note:' + atlas['id'])
        (self.vault / 'Atlas.md').write_text('# Atlas project\nAtlas is cancelled.\n'); self.scanner.scan()
        turn = self.service.view(self.owner, self.sid)['turns'][-1]
        self.assertEqual((turn['state'], turn['result']), ('source_changed', None))

    def test_legacy_submit_without_focus_is_unchanged(self):
        _, turn = self.send('What about the budget?')
        self.assertEqual(turn['state'], 'completed'); self.assertIsNone(turn['focus'])
        self.assertIsNone(turn['result']['packet']['focus'])


if __name__ == '__main__':
    unittest.main()
