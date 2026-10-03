"""Selection and authority regressions; synthetic source bytes, no model."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alfred.grounded import retrieve
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.local import Fault
from alfred.policy import IdentityPolicy


class SelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name); vault = root / 'vault'; vault.mkdir()
        (vault / 'Ferry.md').write_text('# Meridian ferry\nMeridian ferry inspection is due Tuesday. [[Garden]]\n')
        (vault / 'Garden.md').write_text('# Garden\nPlanting takes place on Friday.\n')
        self.store = KnowledgeStore(root / 'desk.sqlite')
        self.owner = self.store.provision('work', 'owner', 'owner')
        source = self.store.provision('work', 'source', 'source')
        self.policy = IdentityPolicy(self.store)
        self.policy.grant(self.owner, 'source', 'read', self.store.now() + 3600, 0)
        MarkdownVault(self.store, source, vault).scan()

    def test_weak_matches_and_irrelevant_link_do_not_fill_the_packet(self):
        question = 'When is the Meridian ferry inspection?'
        before = retrieve(self.store, self.owner, question, selection_policy='baseline')
        after = retrieve(self.store, self.owner, question)
        self.assertEqual({e['path'] for e in before['evidence']}, {'Ferry.md', 'Garden.md'})
        self.assertEqual([e['path'] for e in after['evidence']], ['Ferry.md'])
        self.assertFalse(after['authority_granted'])

    def test_unsupported_named_project_question_can_abstain(self):
        self.assertEqual(retrieve(self.store, self.owner, 'Meridian orbital launch velocity')['evidence'], [])
        self.assertTrue(retrieve(self.store, self.owner, 'Meridian orbital launch velocity', selection_policy='baseline')['evidence'])

    def test_summary_operation_does_not_raise_a_follow_up_topic_floor(self):
        # Same accumulated-topic shape as the actual conversation browser test.
        packet = retrieve(self.store, self.owner, 'Meridian ferry status owns Summarise Meridian ferry')
        self.assertEqual([e['path'] for e in packet['evidence']], ['Ferry.md'])

    def test_explicit_focus_keeps_bounded_authored_link_context(self):
        note = next(n for n in self.store.knowledge(self.owner)['nodes'] if n['path'] == 'Ferry.md')
        packet = retrieve(self.store, self.owner, 'What should I inspect?', focus='note:' + note['id'])
        self.assertEqual(packet['evidence'][0]['retrieved_via'], 'selected_record')
        garden = next(e for e in packet['evidence'] if e['path'] == 'Garden.md')
        self.assertEqual((garden['retrieved_via'], garden['via_note_id']), ('explicit_link_from_match', note['id']))
        self.assertLessEqual(len(packet['evidence']), packet['limits']['sources'])

    def test_mid_read_revocation_refuses_packet_including_metadata(self):
        original = self.store.knowledge_note
        changed = [False]
        def read(*args, **kwargs):
            note = original(*args, **kwargs)
            if not changed[0]:
                changed[0] = True
                self.policy.grant(self.owner, 'source', 'read', self.store.now() + 3600,
                                  self.policy.view(self.owner)['epoch'], revoke=True)
            return note
        with patch.object(self.store, 'knowledge_note', side_effect=read):
            with self.assertRaises(Fault) as failure:
                retrieve(self.store, self.owner, 'Meridian ferry')
        self.assertEqual(failure.exception.code, 'retrieval_authority_changed')

    def test_unknown_comparison_policy_is_rejected(self):
        with self.assertRaises(Fault) as failure:
            retrieve(self.store, self.owner, 'Meridian ferry', selection_policy='guess')
        self.assertEqual(failure.exception.code, 'unsupported_selection_policy')


if __name__ == '__main__':
    unittest.main()
