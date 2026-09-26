"""Reviewed memory behaviour against real SQLite and the actual source index."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from alfred.knowledge import KnowledgeStore,MarkdownVault
from alfred.local import Fault
from alfred.reviewed_memory import ReviewedMemory

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.clock=[1000]
        self.store=KnowledgeStore(self.root/'db',clock=lambda:self.clock[0]);self.owner=self.store.provision('personal','owner','owner',ttl=100000)
        self.other=self.store.provision('personal','other','owner');self.reader=self.store.provision('personal','reader','reader');self.source=self.store.provision('personal','source','source',ttl=100000)
        self.foreign=self.store.provision('other-scope','foreign','owner');self.vault=self.root/'vault';self.vault.mkdir()
        self.file=self.vault/'Atlas.md';self.file.write_text('# Atlas\nMina is responsible for Atlas.\nAtlas is in planning.\nThe alternative report names Sam.\n')
        self.scan=MarkdownVault(self.store,self.source,self.vault);self.scan.scan();self.memory=ReviewedMemory(self.store)
        for eid,kind,name in [('atlas','project','Atlas'),('mina','person','Mina'),('sam','person','Sam')]:self.memory.create_entity(self.owner,{'id':eid,'kind':kind,'name':name})
        n=self.store.knowledge(self.owner)['nodes'][0]
        self.ref={'note_id':n['id'],'sha256':n['sha256'],'revision':n['revision'],'start_line':2,'end_line':2}
        self.seq=0
    def body(self,**changes):
        self.seq+=1;return {'request_id':'request-'+str(self.seq),'subject_id':'atlas','predicate':'responsible_person',
                          'object_id':'mina','value':None,'valid_from':None,'valid_until':None,'evidence':dict(self.ref),**changes}
    def propose(self,**changes):return self.memory.propose(self.owner,self.body(**changes))['id']
    def get(self,cid):return next(c for c in self.memory.view(self.owner)['claims'] if c['id']==cid)
    def review(self,cid,decision='accept',**changes):
        return self.memory.review(self.owner,cid,{'version':self.get(cid)['version'],'decision':decision,'replaces_id':None,'replaces_version':None,**changes})
    def assertFault(self,code,fn):
        with self.assertRaises(Fault) as e:fn()
        self.assertEqual(e.exception.code,code)
    def test_proposed_not_usable(self):
        c=self.get(self.propose());self.assertEqual(c['state'],'proposed');self.assertFalse(c['usable'])
    def test_accept_builds_typed_edge(self):
        cid=self.propose();v=self.review(cid);self.assertEqual(v['graph']['edges'][0]['predicate'],'responsible_person');self.assertFalse(v['authority_granted'])
    def test_evidence_exact_line(self):
        c=self.get(self.propose());self.assertEqual(c['source']['quote'],'Mina is responsible for Atlas.');self.assertEqual(c['source']['start_line'],2)
    def test_quote_not_duplicated_in_database(self):
        self.propose()
        with self.store.connection() as db:raw=json.dumps([tuple(r) for r in db.execute('SELECT * FROM memory_claims')])
        self.assertNotIn('Mina is responsible',raw)
    def test_no_names_only_merging(self):
        self.memory.create_entity(self.owner,{'id':'other-sam','kind':'person','name':'Sam'})
        self.assertEqual(sum(n['name']=='Sam' for n in self.memory.view(self.owner)['entities']),2)
    def test_entity_retry_idempotent(self):
        self.assertTrue(self.memory.create_entity(self.owner,{'id':'sam','kind':'person','name':'Sam'})['reused'])
    def test_entity_id_collision(self):
        self.assertFault('memory_entity_id_unavailable',lambda:self.memory.create_entity(self.owner,{'id':'sam','kind':'person','name':'Other'}))
    def test_unknown_entity_type(self):
        self.assertFault('invalid_memory_entity',lambda:self.memory.create_entity(self.owner,{'id':'x','kind':'root-admin','name':'x'}))
    def test_reader_cannot_create(self):
        with self.assertRaises(Fault):self.memory.create_entity(self.reader,{'id':'x','kind':'person','name':'X'})
    def test_private_to_actor(self):
        self.propose();self.assertEqual(self.memory.view(self.other)['claims'],[]);self.assertEqual(self.memory.view(self.reader)['entities'],[])
    def test_cross_scope_hidden(self):
        self.propose();self.assertEqual(self.memory.view(self.foreign)['claims'],[])
    def test_source_cannot_read(self):
        with self.assertRaises(Fault):self.memory.view(self.source)
    def test_other_owner_cannot_reference_entity(self):
        with self.assertRaises(Fault):self.memory.propose(self.other,self.body())
    def test_request_retry_idempotent(self):
        b=self.body();a=self.memory.propose(self.owner,b);self.assertEqual(self.memory.propose(self.owner,b)['id'],a['id'])
    def test_request_collision(self):
        b=self.body();self.memory.propose(self.owner,b)
        self.assertFault('memory_request_collision',lambda:self.memory.propose(self.owner,{**b,'object_id':'sam'}))
    def test_unknown_predicate(self):
        self.assertFault('invalid_memory_predicate',lambda:self.propose(predicate='unlock'))
    def test_object_type_restricted(self):
        self.assertFault('memory_object_kind',lambda:self.propose(subject_id='mina',object_id='atlas'))
    def test_no_self_reference(self):
        self.assertFault('memory_self_relation',lambda:self.propose(subject_id='mina'))
    def test_text_not_entity(self):
        self.assertFault('memory_value_not_entity',lambda:self.propose(predicate='status',value='planning'))
    def test_missing_entity_target(self):
        self.assertFault('memory_entity_not_found',lambda:self.propose(object_id='not-created'))
    def test_invalid_line(self):
        self.assertFault('invalid_memory_source_range',lambda:self.propose(evidence={**self.ref,'end_line':999}))
    def test_boolean_line_denied(self):
        self.assertFault('invalid_memory_source_range',lambda:self.propose(evidence={**self.ref,'start_line':True}))
    def test_changed_source_hash(self):
        self.assertFault('memory_source_changed',lambda:self.propose(evidence={**self.ref,'sha256':'0'*64}))
    def test_extra_fields_no_authority(self):
        self.assertFault('invalid_fields',lambda:self.propose(approved=True))
    def test_review_is_version_bound(self):
        cid=self.propose();b={'version':1,'decision':'accept','replaces_id':None,'replaces_version':None};self.memory.review(self.owner,cid,b)
        self.assertFault('memory_review_changed',lambda:self.memory.review(self.owner,cid,b))
    def test_dispute_removes_graph(self):
        cid=self.propose();self.review(cid);v=self.review(cid,'dispute');self.assertEqual(v['graph']['edges'],[])
    def test_withdraw_closes_review(self):
        cid=self.propose();self.review(cid,'withdraw');self.assertFault('memory_review_closed',lambda:self.review(cid))
    def test_conflicting_acceptances_not_usable(self):
        a=self.propose();b=self.propose(object_id='sam');self.review(a);v=self.review(b)
        self.assertEqual(v['counts']['conflicted'],2);self.assertEqual(v['graph']['edges'],[])
    def test_explicit_supersession(self):
        a=self.propose();self.review(a);b=self.propose(object_id='sam')
        self.review(b,'supersede',replaces_id=a,replaces_version=self.get(a)['version'])
        self.assertEqual(self.get(a)['state'],'superseded');self.assertTrue(self.get(b)['usable'])
    def test_later_review_preserves_supersession_lineage(self):
        a=self.propose();self.review(a);b=self.propose(object_id='sam')
        self.review(b,'supersede',replaces_id=a,replaces_version=self.get(a)['version'])
        for decision in ('dispute','accept','withdraw'):
            self.review(b,decision)
            self.assertEqual(self.get(b)['replaces_id'],a)
    def test_second_supersession_cannot_overwrite_lineage(self):
        a=self.propose();self.review(a);b=self.propose(object_id='sam')
        self.review(b,'supersede',replaces_id=a,replaces_version=self.get(a)['version'])
        c=self.propose();self.review(c)
        self.assertFault('memory_replacement_already_recorded',lambda:self.review(b,'supersede',replaces_id=c,replaces_version=self.get(c)['version']))
        self.assertEqual(self.get(b)['replaces_id'],a);self.assertEqual(self.get(c)['state'],'accepted')
    def test_source_invalidation_keeps_supersession_lineage(self):
        a=self.propose();self.review(a);b=self.propose(object_id='sam')
        self.review(b,'supersede',replaces_id=a,replaces_version=self.get(a)['version'])
        self.file.write_text('# Atlas\nThe source has changed.\n');self.scan.scan()
        self.assertEqual(self.get(b)['state'],'invalidated');self.assertEqual(self.get(b)['replaces_id'],a)
    def test_supersession_does_not_cross_subject(self):
        a=self.propose();self.review(a);b=self.propose(subject_id='sam')
        self.assertFault('memory_replacement_mismatch',lambda:self.review(b,'supersede',replaces_id=a,replaces_version=self.get(a)['version']))
    def test_supersession_stale_version(self):
        a=self.propose();self.review(a);b=self.propose(object_id='sam')
        self.assertFault('memory_replacement_changed',lambda:self.review(b,'supersede',replaces_id=a,replaces_version=1))
    def test_non_overlapping_validity_not_conflict(self):
        a=self.propose(valid_until=1000);b=self.propose(object_id='sam',valid_from=1000);self.review(a);v=self.review(b)
        self.assertEqual(v['counts']['conflicted'],0);self.assertFalse(self.get(a)['usable']);self.assertTrue(self.get(b)['usable'])
    def test_future_claim_not_usable(self):
        cid=self.propose(valid_from=1100);self.review(cid);self.assertFalse(self.get(cid)['usable'])
    def test_bad_validity_rejected(self):
        self.assertFault('invalid_memory_validity',lambda:self.propose(valid_from=1200,valid_until=1100))
    def test_revision_change_clears_statement(self):
        cid=self.propose(predicate='status',object_id=None,value='planning');self.review(cid)
        self.file.write_text('# Atlas\nChanged evidence.\n');self.scan.scan();c=self.get(cid)
        self.assertEqual(c['state'],'invalidated');self.assertIsNone(c['value']);self.assertIsNone(c['source'])
        with self.store.connection() as db:self.assertIsNone(db.execute('SELECT value FROM memory_claims WHERE id=?',(cid,)).fetchone()[0])
    def test_delete_source_hides_statement(self):
        cid=self.propose();self.file.unlink();self.scan.scan();self.assertEqual(self.get(cid)['state'],'invalidated')
    def test_revoked_source_invalidates(self):
        cid=self.propose();self.store.revoke('source');self.assertIsNone(self.get(cid)['object_id'])
    def test_expired_source_invalidates(self):
        cid=self.propose();self.clock[0]+=100001
        with self.store.transaction() as db:db.execute("UPDATE credentials SET expires=300000 WHERE id='owner'")
        self.assertEqual(self.get(cid)['state'],'invalidated')
    def test_revoked_owner_cannot_read(self):
        self.propose();self.store.revoke('owner')
        with self.assertRaises(Fault):self.memory.view(self.owner)
    def test_no_automatic_revival(self):
        cid=self.propose();raw=self.file.read_text();self.file.unlink();self.scan.scan();self.get(cid);self.file.write_text(raw);self.scan.scan()
        self.assertEqual(self.get(cid)['state'],'invalidated')
    def test_restart_preserves_accepted_claim(self):
        cid=self.propose();self.review(cid);self.memory=ReviewedMemory(KnowledgeStore(self.root/'db',clock=lambda:self.clock[0]));self.assertTrue(self.get(cid)['usable'])
    def test_entity_capacity(self):
        with patch('alfred.reviewed_memory.MAX_ENTITIES',3):
            self.assertFault('memory_entity_capacity',lambda:self.memory.create_entity(self.owner,{'id':'new','name':'X','kind':'person'}))
    def test_claim_capacity(self):
        with patch('alfred.reviewed_memory.MAX_CLAIMS',1):
            self.propose();self.assertFault('memory_claim_capacity',lambda:self.propose())
    def test_invalid_metadata_version(self):
        with self.store.transaction() as db:db.execute('UPDATE reviewed_memory_meta SET version=99')
        self.assertFault('unsupported_reviewed_memory_version',lambda:ReviewedMemory(self.store))
    def test_html_remains_literal(self):
        cid=self.propose(predicate='decision',object_id=None,value='<img src=x onerror=alert(1)>');self.assertIn('<img',self.get(cid)['value'])
    def test_reads_do_not_write_source_files(self):
        before=self.file.read_bytes();self.review(self.propose());self.memory.view(self.owner);self.assertEqual(self.file.read_bytes(),before)
if __name__=='__main__':unittest.main()
