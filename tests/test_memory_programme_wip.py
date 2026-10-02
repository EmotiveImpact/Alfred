"""Synthetic regression checks for the paused M02/M06 checkpoint.

These do not certify complete job acceptance, pairing recovery, an HTTP grants
UI, private-data readiness or retrieval quality. No real provider is called.
"""
from pathlib import Path
import tempfile
import unittest
from alfred.local import Fault
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.policy import IdentityPolicy
from alfred.grounded import ask, retrieve


class ProgrammeCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.clock=[1000]
        self.store=KnowledgeStore(root/'ledger.db',clock=lambda:self.clock[0])
        self.owner=self.store.provision('work','owner','owner',ttl=10000)
        self.other=self.store.provision('work','other','owner',ttl=10000)
        self.source=self.store.provision('work','source','source',ttl=10000)
        self.hidden=self.store.provision('work','hidden','source',ttl=10000)
        self.vault=root/'vault';self.vault.mkdir()
        (self.vault/'Beacon.md').write_text('# Beacon\nA synthetic planning record.\n')
        self.scanner=MarkdownVault(self.store,self.source,self.vault);self.scanner.scan()
        hidden=root/'hidden';hidden.mkdir()
        (hidden/'Secret.md').write_text('# Classifiedmarker\nAn unauthorised synthetic record.\n')
        MarkdownVault(self.store,self.hidden,hidden).scan()
        self.policy=IdentityPolicy(self.store)

    def grant(self, capability='read', *, revoke=False):
        return self.policy.grant(self.owner,'source',capability,5000,
                                 self.policy.view(self.owner)['epoch'],revoke=revoke)

    def test_distinct_credentials_migrate_to_distinct_people(self):
        self.assertNotEqual(self.policy.view(self.owner)['person_id'],self.policy.view(self.other)['person_id'])

    def test_rotation_keeps_person_device_and_rejects_old_token(self):
        before=self.policy.view(self.owner)
        replacement=self.policy.rotate(self.owner,before['generation'])
        after=self.policy.view(replacement)
        self.assertEqual(after['person_id'],before['person_id'])
        self.assertEqual(after['device_id'],before['device_id'])
        self.assertEqual(after['generation'],before['generation']+1)
        with self.assertRaises(Fault):self.policy.view(self.owner)

    def test_source_rotation_preserves_selected_vault_and_note_identity(self):
        before=self.store.knowledge(self.owner)
        replacement=self.policy.rotate(self.source,1)
        MarkdownVault(self.store,replacement,self.vault).scan()
        after=self.store.knowledge(self.owner)
        self.assertEqual([(n['id'],n['revision'],n['vault_id']) for n in before['nodes']],
                         [(n['id'],n['revision'],n['vault_id']) for n in after['nodes']])

    def test_grants_filter_graph_before_keyword_and_fts_ranking(self):
        self.grant()
        self.assertEqual(len(self.store.knowledge(self.owner)['nodes']),1)
        for ranking in ('keywords','fts5'):
            self.assertEqual(retrieve(self.store,self.owner,'Classifiedmarker',ranking=ranking)['evidence'],[])
            packet=retrieve(self.store,self.owner,'Beacon',ranking=ranking)
            self.assertEqual(len(packet['evidence']),1)
            self.assertNotIn('Classifiedmarker',str(packet))
        self.assertEqual(self.store.knowledge(self.other)['nodes'],[])

    def test_read_grant_does_not_authorise_model_context(self):
        self.grant()
        self.assertTrue(retrieve(self.store,self.owner,'Beacon')['evidence'])
        self.assertEqual(retrieve(self.store,self.owner,'Beacon',purpose='model')['evidence'],[])

    def test_policy_epoch_rejects_stale_edit(self):
        self.grant()
        with self.assertRaises(Fault) as error:
            self.policy.grant(self.owner,'hidden','read',5000,0)
        self.assertEqual(error.exception.code,'policy_changed')

    def test_expired_grant_hides_current_source(self):
        self.grant();self.clock[0]=5000
        self.assertEqual(self.store.knowledge(self.owner)['nodes'],[])

    def test_revocation_during_fixture_generation_prevents_result_return(self):
        self.grant();self.grant('model')
        outer=self
        class DeclaredFixture:
            model='synthetic-policy-fixture'
            def generate(self, packet):
                outer.assertEqual(len(packet['evidence']),1)
                outer.grant('model',revoke=True)
                return {'answerable':False,'claims':[]}
        with self.assertRaises(Fault) as error:
            ask(self.store,self.owner,{'question':'Beacon','mode':'local_model'},DeclaredFixture(),'work')
        self.assertEqual(error.exception.code,'sources_changed_during_question')
