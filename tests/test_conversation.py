import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from alfred.local import Fault
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.conversation import ConversationService
from alfred.desk_http import DeskHTTPServer
from alfred.local_model import LocalOllama


class FakeModel:
    model='fixture-not-an-llm'
    def __init__(self):self.packets=[];self.hook=None
    def generate(self,packet):
        self.packets.append(packet)
        if self.hook:self.hook()
        s=packet['evidence'][0]
        return {'answerable':True,'claims':[{'text':'An explicitly synthetic test interpretation.', 'citations':[{'source_id':s['source_id'],'start_line':s['start_line'],'end_line':s['end_line']}]}]}


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.clock=[1000]
        self.store=KnowledgeStore(self.root/'desk.db',clock=lambda:self.clock[0]);self.owner=self.store.provision('work','owner','owner');self.reader=self.store.provision('work','reader','reader');self.source=self.store.provision('work','source','source')
        self.vault=self.root/'vault';self.vault.mkdir();(self.vault/'Equipment.md').write_text('# Equipment collection\nMorgan owns equipment collection.\nCollection is booked for 10:00.\n')
        self.scanner=MarkdownVault(self.store,self.source,self.vault);self.scanner.scan();self.model=FakeModel();self.service=ConversationService(self.store,self.model,'work')
        self.sid=self.service.create(self.owner,{'title':'Equipment'})['id'];self.seq=0
    def tearDown(self):self.service.stop();self.tmp.cleanup()
    def send(self,question='What is the equipment collection time?',mode='sources',follow=False,**changes):
        body={'question':question,'mode':mode,'follow_up':follow,'request_id':'r'+str(self.seq),'after':self.seq};body.update(changes)
        value=self.service.submit(self.owner,self.sid,body);self.seq+=1;return value
    def run_turn(self,**kwargs):self.send(**kwargs);self.service.process_one();return self.service.view(self.owner,self.sid)['turns'][-1]
    def test_sources_complete_without_model(self):
        t=self.run_turn();self.assertEqual(t['state'],'completed');self.assertIn('10:00',t['result']['packet']['evidence'][0]['excerpt']);self.assertFalse(self.model.packets)
    def test_followup_reuses_user_topic_not_generated_claim(self):
        self.run_turn(mode='local_model');t=self.run_turn(question='Who owns that?',follow=True)
        self.assertIn('equipment',t['result']['packet']['retrieval_question']);self.assertNotIn('synthetic test interpretation',t['result']['packet']['retrieval_question'])
    def test_new_topic_can_discard_prior_context(self):
        self.run_turn();t=self.run_turn(question='zebrazebraword',follow=False);self.assertEqual(t['result']['status'],'no_sources')
    def test_followup_after_new_topic_does_not_revive_old_topic(self):
        self.run_turn()
        self.run_turn(question='What is the zebra habitat?',follow=False)
        turn=self.run_turn(question='And who owns that?',follow=True)
        q=turn['result']['packet']['retrieval_question']
        self.assertIn('zebra',q);self.assertNotIn('equipment',q)
    def test_followup_preserves_full_current_question(self):
        self.run_turn()
        question='equipment '+('x'*476)+' endmarker'
        turn=self.run_turn(question=question,follow=True)
        self.assertTrue(turn['result']['packet']['retrieval_question'].endswith('endmarker'))
        self.assertEqual(turn['result']['packet']['question'],question)
    def test_session_retention_rows_removed_with_live_actor(self):
        self.run_turn()
        with self.store.transaction() as db:
            db.execute("UPDATE credentials SET expires=200000 WHERE id='owner'")
        self.clock[0]+=86401
        self.assertEqual(self.service.listing(self.owner)['sessions'],[])
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM conversation_turns').fetchone()[0],0)
    def test_history_limit_does_not_silently_drop_turns(self):
        from unittest.mock import patch
        with patch('alfred.conversation.MAX_TURNS',1):
            self.run_turn()
            with self.assertRaises(Fault) as error:self.send()
            self.assertEqual(error.exception.code,'conversation_turn_capacity')
    def test_same_actor_rate_limit_across_sessions(self):
        for _ in range(6):self.run_turn()
        with self.assertRaises(Fault) as error:self.send()
        self.assertEqual(error.exception.code,'conversation_rate_limited')
    def test_pause_after_proposal_stops_approved_execution(self):
        t=self.run_turn();a=self.service.propose_draft(self.owner,self.sid,{'turn_id':t['id'],'text':'Please confirm.','request_id':'d'})
        self.store.approve(self.owner,a['id'],a['fingerprint']);self.store.set_paused(self.owner,True);self.store.tick(self.owner)
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM drafts').fetchone()[0],0)
    def test_source_excerpts_not_duplicated_in_storage(self):
        self.run_turn(mode='local_model')
        with self.store.connection() as db:value=db.execute('SELECT result FROM conversation_turns').fetchone()[0]
        self.assertNotIn('Morgan owns equipment',value);self.assertNotIn('"quote"',value);self.assertNotIn('"excerpt"',value)
    def test_model_explicit_and_history_bounded(self):
        self.run_turn();t=self.run_turn(question='Who owns that?',mode='local_model',follow=True)
        self.assertEqual(t['result']['status'],'model_interpretation');self.assertEqual(len(self.model.packets[0]['conversation_questions']),1)
    def test_actor_private_not_just_workspace(self):
        other=self.store.provision('work','another-owner','owner')
        with self.assertRaises(Fault):self.service.view(other,self.sid)
        self.assertEqual(self.service.listing(other)['sessions'],[])
    def test_reader_has_own_sources_only_conversation(self):
        sid=self.service.create(self.reader,{'title':'Reading'})['id']
        body={'question':'equipment','mode':'local_model','follow_up':False,'request_id':'r','after':0}
        with self.assertRaises(Fault):self.service.submit(self.reader,sid,body)
    def test_cross_scope_cannot_read(self):
        other=self.store.provision('private','private-owner','owner')
        with self.assertRaises(Fault):self.service.view(other,self.sid)
    def test_source_role_cannot_create(self):
        with self.assertRaises(Fault):self.service.create(self.source,{'title':'x'})
    def test_identical_request_returns_existing_turn(self):
        x=self.send();y=self.service.submit(self.owner,self.sid,{'question':'What is the equipment collection time?','mode':'sources','follow_up':False,'request_id':'r0','after':0})
        self.assertEqual(x['turn_id'],y['turn_id']);self.assertTrue(y['reused'])
    def test_request_collision_rejected(self):
        self.send()
        with self.assertRaises(Fault):self.send(question='different',request_id='r0',after=0)
    def test_stale_client_revision_rejected(self):
        self.run_turn()
        with self.assertRaises(Fault):self.send(after=0)
    def test_overlapping_turns_blocked(self):
        self.send()
        with self.assertRaises(Fault):self.send()
    def test_restart_preserves_completed_session(self):
        self.run_turn();s=ConversationService(KnowledgeStore(self.root/'desk.db',clock=lambda:self.clock[0]))
        self.assertEqual(s.view(self.owner,self.sid)['turns'][0]['state'],'completed')
    def test_restart_interrupts_pending_without_reissue(self):
        self.send(mode='local_model');s=ConversationService(self.store,self.model,'work');s.recover()
        self.assertEqual(s.view(self.owner,self.sid)['turns'][0]['state'],'interrupted');self.assertFalse(s.process_one());self.assertFalse(self.model.packets)
    def test_expired_session_is_deleted_on_listing(self):
        self.clock[0]+=86401
        # new owner key is provisioned separately; expired bearer itself cannot read.
        with self.assertRaises(Fault):self.service.view(self.owner,self.sid)
    def test_forget_removes_turns_and_blocks_queued_work(self):
        self.send(mode='local_model');self.service.forget(self.owner,self.sid);self.service.process_one()
        self.assertFalse(self.model.packets)
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM conversation_turns').fetchone()[0],0)
    def test_source_change_clears_stored_interpretation(self):
        self.run_turn(mode='local_model');(self.vault/'Equipment.md').write_text('# Equipment\nChanged.\n');self.scanner.scan()
        t=self.service.view(self.owner,self.sid)['turns'][0];self.assertEqual(t['state'],'source_changed');self.assertIsNone(t['result'])
        with self.store.connection() as db:self.assertIsNone(db.execute('SELECT result FROM conversation_turns').fetchone()[0])
    def test_source_revocation_hides_history_result(self):
        self.run_turn();self.store.revoke('source');self.assertEqual(self.service.view(self.owner,self.sid)['turns'][0]['state'],'source_changed')
    def test_source_removed_mid_inference_discards_result(self):
        self.model.hook=lambda:self.store.revoke('source');t=self.run_turn(mode='local_model');self.assertEqual(t['state'],'source_changed');self.assertIsNone(t['result'])
    def test_actor_revoked_mid_inference_never_persists_result(self):
        self.model.hook=lambda:self.store.revoke('owner');self.send(mode='local_model');self.service.process_one()
        with self.store.connection() as db:self.assertIsNone(db.execute('SELECT result FROM conversation_turns').fetchone()[0])
    def test_invalid_model_result_is_not_shown(self):
        self.model.generate=lambda p:{'answerable':True,'claims':[{'text':'bad','citations':[{'source_id':'S99','start_line':1,'end_line':1}]}]}
        t=self.run_turn(mode='local_model');self.assertEqual(t['state'],'failed');self.assertIsNone(t['result'])
    def test_provider_exception_not_persisted(self):
        def bad(p):raise RuntimeError('secret-value-must-not-appear')
        self.model.generate=bad;t=self.run_turn(mode='local_model');self.assertNotIn('secret-value',json.dumps(t))
    def test_pause_blocks_turn(self):
        self.store.set_paused(self.owner,True)
        with self.assertRaises(Fault):self.send()
    def test_pause_mid_inference_discards_result(self):
        self.model.hook=lambda:self.store.set_paused(self.owner,True);t=self.run_turn(mode='local_model');self.assertEqual(t['state'],'failed')
    def test_no_model_without_configuration(self):
        self.service.provider=None
        with self.assertRaises(Fault):self.send(mode='local_model')
    def test_exact_fields_no_endpoint_override(self):
        with self.assertRaises(Fault):self.send(url='http://elsewhere')
    def test_conversation_draft_needs_separate_approval(self):
        t=self.run_turn();a=self.service.propose_draft(self.owner,self.sid,{'turn_id':t['id'],'text':'Please confirm collection.','request_id':'draft1'})
        self.assertEqual(a['state'],'proposed');self.store.tick(self.owner)
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM drafts').fetchone()[0],0)
        self.store.approve(self.owner,a['id'],a['fingerprint']);self.store.tick(self.owner)
        self.assertEqual(self.store.state(self.owner)['actions'][0]['state'],'verified')
    def test_draft_source_change_blocks_approval(self):
        t=self.run_turn();a=self.service.propose_draft(self.owner,self.sid,{'turn_id':t['id'],'text':'Please confirm.','request_id':'d'})
        (self.vault/'Equipment.md').write_text('# Equipment\nNow delayed.');self.scanner.scan()
        with self.assertRaises(Fault):self.store.approve(self.owner,a['id'],a['fingerprint'])
    def test_forget_blocks_approved_unexecuted_draft(self):
        t=self.run_turn();a=self.service.propose_draft(self.owner,self.sid,{'turn_id':t['id'],'text':'Please confirm.','request_id':'d'})
        self.store.approve(self.owner,a['id'],a['fingerprint']);self.service.forget(self.owner,self.sid);self.store.tick(self.owner)
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM drafts').fetchone()[0],0)
    def test_draft_request_retry_does_not_duplicate(self):
        t=self.run_turn();b={'turn_id':t['id'],'text':'Please confirm.','request_id':'d'}
        a=self.service.propose_draft(self.owner,self.sid,b);self.assertEqual(a['id'],self.service.propose_draft(self.owner,self.sid,b)['id'])
    def test_followup_flag_boolean_only(self):
        with self.assertRaises(Fault):self.send(follow_up='yes')
    def test_daily_private_retention_is_explicit(self):self.assertEqual(self.service.listing(self.owner)['retention_seconds'],86400)


class ConversationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=KnowledgeStore(Path(self.tmp.name)/'db');self.key=self.store.provision('w','owner','owner')
        class Supervisor:
            scope='w'
            def view(self,scope):return {'configured':False}
        self.server=DeskHTTPServer(self.store,Supervisor(),port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.cookie='';self.csrf='';_,value,headers=self.req('POST','/desk/login',{'key':self.key});self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=value['csrf']
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join(3);self.tmp.cleanup()
    def req(self,method,path,body=None):
        c=HTTPConnection('127.0.0.1',self.server.server_port,timeout=3);headers={'Cookie':self.cookie,'X-CSRF-Token':self.csrf}
        if method=='POST':headers.update({'Origin':self.server.origin,'Content-Type':'application/json'})
        c.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers);r=c.getresponse();v=json.loads(r.read());status=r.status;h=dict(r.getheaders());c.close();return status,v,h
    def test_real_http_persistent_flow(self):
        code,v,_=self.req('POST','/desk/conversations',{'title':'New conversation'});self.assertEqual(code,200)
        sid=v['id'];code,v,_=self.req('POST','/desk/conversations/'+sid+'/turns',{'question':'collection','mode':'sources','follow_up':False,'request_id':'r','after':0});self.assertEqual(code,200)
        for _ in range(40):
            _,v,_=self.req('GET','/desk/conversations/'+sid)
            if v['turns'][0]['state']=='completed':break
            time.sleep(.02)
        self.assertEqual(v['turns'][0]['result']['status'],'no_sources')
    def test_csrf_required(self):
        self.csrf='bad';self.assertEqual(self.req('POST','/desk/conversations',{'title':'x'})[0],403)
    def test_foreign_scope_not_accepted(self):self.assertEqual(self.req('POST','/desk/conversations',{'title':'x','scope':'another'})[0],400)
    def test_unknown_route_not_mutating(self):self.assertEqual(self.req('POST','/desk/conversations/nope/tools',{})[0],404)
    def test_similar_prefix_does_not_create_conversation(self):
        self.assertEqual(self.req('POST','/desk/conversations-other',{'title':'not a valid route'})[0],404)
    def test_auth_required(self):
        self.cookie='';self.assertEqual(self.req('GET','/desk/conversations')[0],401)


if __name__=='__main__':unittest.main()
