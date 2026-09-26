"""Evidence checks in the actual synchronous and queued application paths.

All model output below is an explicitly synthetic test double, not inference.
"""
from pathlib import Path
import json,tempfile,unittest
from alfred.knowledge import KnowledgeStore,MarkdownVault
from alfred.grounded import ask
from alfred.conversation import ConversationService

class ModelFixture:
    model='literal-test-double-not-inference'
    def __init__(self,reply):self.reply=reply;self.calls=0
    def generate(self,packet):
        self.calls+=1;s=packet['evidence'][0]
        return {'answerable':True,'claims':[{'text':self.reply,'citations':[{'source_id':s['source_id'],'start_line':s['start_line'],'end_line':s['end_line']}]}]}

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        self.store=KnowledgeStore(root/'db');self.owner=self.store.provision('test','owner','owner');source=self.store.provision('test','source','source')
        v=root/'vault';v.mkdir();(v/'Inspection.md').write_text('# Harbour inspection\nThe harbour inspection is at 14:25.\nLeena coordinates it.\n')
        MarkdownVault(self.store,source,v).scan()
    def sync(self,q,reply):return ask(self.store,self.owner,{'question':q,'mode':'local_model'},ModelFixture(reply),'test')
    def queued(self,q,reply):
        service=ConversationService(self.store,ModelFixture(reply),'test');self.addCleanup(service.stop)
        cid=service.create(self.owner,{'title':'Synthetic guard test'})['id']
        service.submit(self.owner,cid,{'question':q,'mode':'local_model','follow_up':False,'request_id':'r','after':0});service.process_one()
        return service.view(self.owner,cid)['turns'][0]['result']
    def test_sync_missing_amount_withheld(self):
        r=self.sync('How much is the harbour inspection fee?','The harbour inspection is at 14:25.')
        self.assertEqual(r['status'],'model_needs_review');self.assertEqual(r['claims'],[]);self.assertTrue(r['model_used'])
    def test_queued_missing_amount_withheld(self):
        r=self.queued('How much is the harbour inspection fee?','The harbour inspection is at 14:25.')
        self.assertEqual(r['status'],'model_needs_review');self.assertEqual(r['claims'],[])
    def test_unsupported_number_withheld(self):
        r=self.sync('What time is the harbour inspection?','The harbour inspection is at 18:45.')
        self.assertEqual(r['status'],'model_needs_review');self.assertNotIn('18:45',json.dumps(r))
    def test_queued_unsupported_text_not_persisted(self):
        self.queued('What time is the harbour inspection?','The harbour inspection is at 18:45.')
        with self.store.connection() as db:value=db.execute('SELECT result FROM conversation_turns').fetchone()[0]
        self.assertNotIn('18:45',value);self.assertIn('withheld_for_review',value)
    def test_valid_literal_answer_still_passes(self):
        r=self.sync('What time is the harbour inspection?','The harbour inspection is at 14:25.')
        self.assertEqual(r['status'],'model_interpretation');self.assertFalse(r['semantic_entailment_verified'])
    def test_queued_valid_reply(self):
        r=self.queued('Who coordinates the harbour inspection?','Leena coordinates the harbour inspection.')
        self.assertEqual(r['status'],'model_interpretation')
    def test_source_mode_does_not_run_a_model(self):
        model=ModelFixture('Never invoked');r=ask(self.store,self.owner,{'question':'Harbour inspection','mode':'sources'},model,'test')
        self.assertFalse(r['model_used']);self.assertEqual(model.calls,0)
if __name__=='__main__':unittest.main()
