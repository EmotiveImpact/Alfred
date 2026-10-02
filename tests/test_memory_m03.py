"""M03 acceptance: real Markdown/SQLite, fixed clock, no model inference.

The provider below captures a packet and returns a declared fixture abstention.
It tests the context/authority boundary, not answer quality or entailment.
"""
from copy import deepcopy
from http.client import HTTPConnection
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from alfred.conversation import ConversationService
from alfred.desk_http import DeskHTTPServer
from alfred.grounded import ask, check_packet, check_sources, references, retrieve
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.local import Fault
from alfred.local_model import LocalOllama
from alfred.reviewed_memory import ReviewedMemory, context_references


class PacketFixture:
    model='context-fixture-not-an-llm'
    def __init__(self, hook=None):self.packets=[];self.hook=hook
    def generate(self, packet):
        self.packets.append(deepcopy(packet))
        if self.hook:self.hook()
        return {'answerable':False,'claims':[]}


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.clock=[1000]
        self.store=KnowledgeStore(self.root/'desk.db',clock=lambda:self.clock[0])
        self.owner=self.store.provision('work','owner','owner',ttl=200000)
        self.reader=self.store.provision('work','reader','reader',ttl=200000)
        self.other=self.store.provision('work','another-owner','owner',ttl=200000)
        self.foreign=self.store.provision('elsewhere','foreign','owner',ttl=200000)
        self.source=self.store.provision('work','source','source',ttl=200000)
        self.vault=self.root/'vault';self.vault.mkdir();self.file=self.vault/'Record.md'
        self.file.write_text('# Original record\nThe original assignment names Mina.\nAn alternative assignment names Sam.\nThe recorded stage is planning.\n')
        self.scanner=MarkdownVault(self.store,self.source,self.vault);self.scanner.scan()
        self.memory=ReviewedMemory(self.store);self.sequence=0
        for eid,kind,name in [('beacon','project','Beacon Programme'),('mina','person','Mina'),('sam','person','Sam')]:
            self.entity(eid,kind,name)
    def entity(self, eid, kind='project', name=None):
        return self.memory.create_entity(self.owner,{'id':eid,'kind':kind,'name':name or eid})
    def ref(self, line=2):
        n=self.store.knowledge(self.owner)['nodes'][0]
        return {'note_id':n['id'],'sha256':n['sha256'],'revision':n['revision'],'start_line':line,'end_line':line}
    def claim(self, accepted=True, line=2, **changes):
        self.sequence+=1
        body={'request_id':'r'+str(self.sequence),'subject_id':'beacon','predicate':'responsible_person',
              'object_id':'mina','value':None,'valid_from':None,'valid_until':None,'evidence':self.ref(line)}
        body.update(changes);cid=self.memory.propose(self.owner,body)['id']
        if accepted:self.review(cid)
        return cid
    def get(self, cid):return next(c for c in self.memory.view(self.owner)['claims'] if c['id']==cid)
    def review(self, cid, decision='accept', **changes):
        body={'version':self.get(cid)['version'],'decision':decision,'replaces_id':None,'replaces_version':None}
        body.update(changes);return self.memory.review(self.owner,cid,body)
    def packet(self, question='Who is responsible for Beacon Programme?', bearer=None):
        return retrieve(self.store,bearer or self.owner,question)
    def answer(self, provider=None, mode='sources', question='Beacon Programme'):
        return ask(self.store,self.owner,{'question':question,'mode':mode},provider,'work')
    def fault(self, code, fn):
        with self.assertRaises(Fault) as error:fn()
        self.assertEqual(error.exception.code,code)
    def conversation(self, provider=None):
        service=ConversationService(self.store,provider,'work');self.addCleanup(service.stop)
        sid=service.create(self.owner,{'title':'Synthetic memory context'})['id'];return service,sid
    def turn(self, service, sid, question='Beacon Programme', mode='sources', follow=False):
        after=len(service.view(self.owner,sid)['turns'])
        service.submit(self.owner,sid,{'question':question,'mode':mode,'follow_up':follow,'request_id':'turn-'+str(after),'after':after})
        service.process_one();return service.view(self.owner,sid)['turns'][-1]
    def draft(self, service, sid, turn):
        return service.propose_draft(self.owner,sid,{'turn_id':turn['id'],'text':'Please confirm the assignment.','request_id':'draft-context'})


class ContextTests(Fixture):
    def test_empty_and_proposed_memory_cannot_find_an_unmentioned_entity(self):
        self.assertEqual(self.packet('Beacon Programme')['evidence'],[])
        self.claim(accepted=False)
        self.assertEqual(self.packet('Beacon Programme')['memory'],[])
        self.assertEqual(self.packet('Beacon Programme')['evidence'],[])

    def test_accepted_identity_finds_exact_original_support_without_name_in_note(self):
        cid=self.claim();p=self.packet('Beacon Programme');m=p['memory'][0];s=p['evidence'][0]
        self.assertEqual(m['claim_id'],cid);self.assertEqual(m['subject']['id'],'beacon')
        self.assertEqual(m['object']['id'],'mina');self.assertEqual(m['version'],2)
        self.assertEqual(s['excerpt'],'The original assignment names Mina.')
        self.assertEqual((s['start_line'],s['end_line']),(2,2))
        self.assertEqual(m['support']['source_id'],s['source_id'])
        for key in ('note_id','sha256','revision','start_line','end_line'):self.assertEqual(m['support'][key],s[key])
        self.assertEqual(m['basis'],'user_reviewed_statement_not_verified_fact')
        self.assertEqual(s['basis'],'authored_note_not_verified_fact');self.assertFalse(m['authority_granted'])

    def test_review_metadata_and_validity_are_retained(self):
        cid=self.claim(valid_from=900,valid_until=1100);m=self.packet()['memory'][0]
        self.assertEqual((m['valid_from'],m['valid_until'],m['recorded'],m['reviewed']),(900,1100,1000,1000))
        self.assertEqual(m['review_state'],'accepted');self.assertIsNone(m['replaces_id'])
        self.assertEqual(m['support']['quote_hash'],self.get(cid)['quote_hash'])

    def test_irrelevant_accepted_statement_is_not_context(self):
        self.claim();self.assertEqual(self.packet('xylophonezzz')['memory'],[])

    def test_disputed_value_is_not_a_reviewed_fact_or_model_input(self):
        cid=self.claim(predicate='status',object_id=None,value='unique-disputed-value')
        self.review(cid,'dispute');model=PacketFixture();self.answer(model,'local_model','original record')
        self.assertEqual(model.packets[0]['memory'],[])
        self.assertNotIn('unique-disputed-value',json.dumps(model.packets))

    def test_withdrawn_memory_is_withheld(self):
        cid=self.claim();self.review(cid,'withdraw');self.assertEqual(self.packet()['memory'],[])

    def test_validity_is_half_open_and_future_memory_is_withheld(self):
        self.claim(valid_from=1001,valid_until=1100);self.assertEqual(self.packet()['memory'],[])
        self.clock[0]=1001;self.assertEqual(len(self.packet()['memory']),1)
        self.clock[0]=1100;self.assertEqual(self.packet()['memory'],[])

    def test_source_edit_invalidates_and_clears_memory_value(self):
        cid=self.claim(predicate='status',object_id=None,value='planning')
        self.file.write_text('# Record\nChanged evidence.\n');self.scanner.scan()
        self.assertEqual(self.packet()['memory'],[]);self.assertEqual(self.get(cid)['state'],'invalidated')
        self.assertIsNone(self.get(cid)['value'])

    def test_confirmed_source_deletion_withholds_memory(self):
        self.claim();self.file.unlink();self.scanner.scan();self.assertEqual(self.packet()['memory'],[])

    def test_lost_vault_withholds_cached_memory_and_does_not_revive_review(self):
        cid=self.claim();moved=self.root/'disconnected';self.vault.rename(moved);self.scanner.scan()
        self.assertEqual(self.packet()['memory'],[]);moved.rename(self.vault);self.scanner.scan()
        self.assertEqual(self.packet()['memory'],[]);self.assertEqual(self.get(cid)['state'],'invalidated')

    def test_rename_changes_revision_and_needs_new_review(self):
        cid=self.claim();before=self.get(cid)['note_id'];self.file.rename(self.vault/'Renamed.md');self.scanner.scan()
        self.assertEqual(self.store.knowledge(self.owner)['nodes'][0]['id'],before)
        self.assertEqual(self.packet()['memory'],[]);self.assertEqual(self.get(cid)['state'],'invalidated')

    def test_same_hash_after_disconnect_is_not_the_old_revision(self):
        self.claim();before=self.packet();moved=self.root/'disconnected';self.vault.rename(moved);self.scanner.scan()
        moved.rename(self.vault);self.scanner.scan();self.assertFalse(check_packet(self.store,self.owner,before))

    def test_source_revocation_withholds_context(self):
        self.claim();self.store.revoke('source');self.assertEqual(self.packet()['memory'],[])

    def test_source_expiry_withholds_context(self):
        self.claim()
        with self.store.transaction() as db:db.execute("UPDATE credentials SET expires=1000 WHERE id='source'")
        self.assertEqual(self.packet()['memory'],[])

    def test_memory_is_actor_private_within_the_same_scope(self):
        self.claim()
        for key in (self.other,self.reader,self.foreign):
            with self.subTest(key=key):self.assertEqual(self.packet(bearer=key)['memory'],[])

    def test_foreign_actor_cannot_validate_another_review_binding(self):
        self.claim();p=self.packet()
        self.assertFalse(check_sources(self.store,self.other,references(p),context_references(p))['current_index_match'])
        self.assertFalse(check_packet(self.store,self.foreign,p))

    def test_revoked_actor_cannot_read_context(self):
        self.claim();self.store.revoke('owner')
        with self.assertRaises(Fault):self.packet()

    def test_conflicting_accepted_assignments_are_both_withheld(self):
        self.claim();self.claim(object_id='sam',line=3)
        self.assertEqual(self.packet()['memory'],[]);self.assertEqual(self.memory.view(self.owner)['counts']['conflicted'],2)

    def test_late_overlapping_report_does_not_silently_replace_owner(self):
        first=self.claim(valid_from=900);self.clock[0]=1001
        self.claim(object_id='sam',line=3,valid_from=950)
        self.assertEqual(self.packet()['memory'],[]);self.assertEqual(self.get(first)['state'],'accepted')

    def test_late_historical_record_preserves_history_without_overriding_current_owner(self):
        current=self.claim(object_id='sam',line=3,valid_from=900)
        self.clock[0]=1100;old=self.claim(valid_from=100,valid_until=800)
        p=self.packet();self.assertEqual([m['claim_id'] for m in p['memory']],[current])
        self.assertEqual(self.get(old)['created'],1100);self.assertEqual(self.get(old)['valid_from'],100)
        self.assertEqual(self.get(old)['state'],'accepted');self.assertFalse(self.get(old)['usable'])

    def test_changed_ownership_requires_explicit_replacement_and_keeps_lineage(self):
        first=self.claim();second=self.claim(accepted=False,object_id='sam',line=3)
        self.review(second,'supersede',replaces_id=first,replaces_version=self.get(first)['version'])
        p=self.packet();self.assertEqual([m['claim_id'] for m in p['memory']],[second])
        self.assertEqual(p['memory'][0]['replaces_id'],first);self.assertEqual(p['memory'][0]['object']['id'],'sam')
        self.assertEqual(self.get(first)['state'],'superseded');self.assertEqual(self.get(first)['object_id'],'mina')

    def test_namesakes_are_distinct_and_model_requires_clarification(self):
        self.entity('other-beacon',name='Beacon Programme');self.claim();self.claim(subject_id='other-beacon',object_id='sam',line=3)
        model=PacketFixture();r=self.answer(model,'local_model')
        self.assertEqual({m['subject']['id'] for m in r['packet']['memory']},{'beacon','other-beacon'})
        self.assertEqual(r['packet']['memory_ambiguities'][0]['entity_ids'],['beacon','other-beacon'])
        self.assertEqual(r['status'],'memory_needs_clarification');self.assertEqual(model.packets,[])
        self.assertFalse(r['content_sent_to_model'])

    def test_same_named_people_keep_distinct_object_ids(self):
        self.entity('other-mina','person','Mina');self.claim(object_id='other-mina')
        p=self.packet();self.assertEqual(p['memory'][0]['object']['id'],'other-mina')
        self.assertEqual(p['memory_ambiguities'][0]['entity_ids'],['mina','other-mina'])

    def test_context_and_source_budgets_share_original_support(self):
        for i in range(8):
            self.entity('beacon-'+str(i),name='Beacon '+str(i))
            self.claim(subject_id='beacon-'+str(i),predicate='status',object_id=None,value='x'*400)
        p=self.packet('Beacon');self.assertLessEqual(len(p['memory']),4)
        self.assertLessEqual(sum(len(m['subject']['name'])+len(m['predicate'])+len(m['value']) for m in p['memory']),1600)
        self.assertEqual(len(p['evidence']),1)
        self.assertLessEqual(sum(len(s['excerpt']) for s in p['evidence']),6000)
        self.assertEqual(len({m['support']['source_id'] for m in p['memory']}),1)

    def test_different_support_slices_keep_absolute_original_lines(self):
        self.claim();self.claim(predicate='status',object_id=None,value='planning',line=4)
        p=self.packet();self.assertEqual(len(p['evidence']),2)
        for m in p['memory']:
            s=next(s for s in p['evidence'] if s['source_id']==m['support']['source_id'])
            self.assertEqual(s['excerpt'],'\n'.join(self.file.read_text().splitlines()[s['start_line']-1:s['end_line']]))

    def test_memory_and_keyword_sources_cannot_expand_the_existing_five_source_budget(self):
        for i in range(4):
            self.entity('beacon-'+str(i),name='Beacon '+str(i))
            (self.vault/('Support'+str(i)+'.md')).write_text('# Source\nOriginal support '+('x'*990)+'\n')
        for i in range(6):(self.vault/('Keyword'+str(i)+'.md')).write_text('# Beacon keyword\nOther authored evidence.\n')
        self.scanner.scan()
        for i in range(4):
            n=next(n for n in self.store.knowledge(self.owner)['nodes'] if n['path']=='Support'+str(i)+'.md')
            self.claim(subject_id='beacon-'+str(i),evidence={'note_id':n['id'],'sha256':n['sha256'],'revision':n['revision'],'start_line':2,'end_line':2})
        p=self.packet('Beacon');self.assertEqual(len(p['memory']),4);self.assertEqual(len(p['evidence']),5)
        self.assertLessEqual(sum(len(s['excerpt']) for s in p['evidence']),6000)

    def test_context_order_is_deterministic_across_restart(self):
        for i in range(5):
            self.entity('beacon-'+str(i),name='Beacon '+str(i));self.claim(subject_id='beacon-'+str(i))
        before=self.packet();reopened=KnowledgeStore(self.root/'desk.db',clock=lambda:self.clock[0])
        self.assertEqual(before,retrieve(reopened,self.owner,'Who is responsible for Beacon Programme?'))

    def test_default_mode_does_not_call_provider_or_execute_an_action(self):
        self.claim();model=PacketFixture();r=self.answer(model)
        self.assertEqual(model.packets,[]);self.assertFalse(r['actions_executed']);self.assertFalse(r['model_used'])
        self.assertEqual(self.store.desk_state(self.owner)['counts']['drafts'],0)

    def test_optional_model_receives_review_basis_and_exact_evidence(self):
        self.claim();model=PacketFixture();r=self.answer(model,'local_model')
        self.assertEqual(len(model.packets),1);p=model.packets[0]
        self.assertEqual(p['memory'][0]['review_state'],'accepted');self.assertEqual(r['status'],'model_abstained')
        payload=json.loads(LocalOllama('fixture').request(p)['messages'][1]['content'])
        self.assertEqual(payload['reviewed_statements'][0]['subject']['id'],'beacon')
        self.assertEqual(payload['reviewed_statements'][0]['support'],{'source_id':'S1','start_line':2,'end_line':2})
        self.assertEqual(payload['sources'][0]['lines'],[{'line':2,'text':'The original assignment names Mina.'}])
        self.assertNotIn('note_id',json.dumps(payload));self.assertNotIn('Record.md',json.dumps(payload))

    def test_review_withdrawal_during_model_call_discards_reply(self):
        cid=self.claim();self.fault('sources_changed_during_question',lambda:self.answer(PacketFixture(lambda:self.review(cid,'withdraw')),'local_model'))

    def test_new_conflict_during_model_call_discards_reply(self):
        self.claim();self.fault('sources_changed_during_question',lambda:self.answer(PacketFixture(lambda:self.claim(object_id='sam',line=3)),'local_model'))

    def test_validity_expiry_during_model_call_discards_reply(self):
        self.claim(valid_until=1001)
        self.fault('sources_changed_during_question',lambda:self.answer(PacketFixture(lambda:self.clock.__setitem__(0,1001)),'local_model'))

    def test_namesake_created_during_model_call_discards_reply(self):
        self.claim();self.fault('sources_changed_during_question',lambda:self.answer(PacketFixture(lambda:self.entity('namesake',name='Beacon Programme')),'local_model'))

    def test_review_change_before_egress_never_calls_provider(self):
        cid=self.claim();original=retrieve
        def race(*args,**kwargs):
            p=original(*args,**kwargs);self.review(cid,'dispute');return p
        model=PacketFixture()
        with patch('alfred.grounded.retrieve',race):
            self.fault('sources_changed_during_question',lambda:self.answer(model,'local_model'))
        self.assertEqual(model.packets,[])

    def test_review_change_before_default_return_discards_packet(self):
        cid=self.claim();original=retrieve
        def race(*args,**kwargs):
            p=original(*args,**kwargs);self.review(cid,'dispute');return p
        with patch('alfred.grounded.retrieve',race):self.fault('sources_changed_during_question',self.answer)

    def test_a_reacceptance_requires_the_new_review_version(self):
        cid=self.claim();old=self.packet();self.review(cid,'dispute');self.review(cid)
        self.assertFalse(check_packet(self.store,self.owner,old));self.assertTrue(check_packet(self.store,self.owner,self.packet()))

    def test_forged_quote_hash_and_review_version_fail_currentness(self):
        self.claim();p=self.packet()
        for key,value in [('quote_hash','0'*64),('version',99)]:
            refs=context_references(p);refs[0][key]=value
            self.assertFalse(check_sources(self.store,self.owner,references(p),refs)['current_index_match'])

    def test_malformed_and_duplicate_review_bindings_are_rejected(self):
        self.claim();p=self.packet();refs=context_references(p)
        bad=[refs*5,refs*2,[dict(refs[0],version=True)],[dict(refs[0],revision=True)],[dict(refs[0],start_line=True)],[dict(refs[0],permission='owner')]]
        for value in bad:
            with self.subTest(value=value),self.assertRaises(Fault):check_sources(self.store,self.owner,references(p),value)

    def test_reading_and_context_assembly_do_not_change_vault_bytes(self):
        before=self.file.read_bytes();self.claim();self.answer();self.assertEqual(self.file.read_bytes(),before)


class ConversationContextTests(Fixture):
    def test_conversation_receives_accepted_memory_and_reconstructs_after_restart(self):
        self.claim();service,sid=self.conversation();turn=self.turn(service,sid)
        self.assertEqual(turn['state'],'completed');before=turn['result']['packet']['memory']
        restarted=ConversationService(KnowledgeStore(self.root/'desk.db',clock=lambda:self.clock[0]))
        self.addCleanup(restarted.stop);self.assertEqual(restarted.view(self.owner,sid)['turns'][0]['result']['packet']['memory'],before)

    def test_durable_turn_stores_bindings_without_memory_values_or_source_text(self):
        self.claim(predicate='status',object_id=None,value='private-reviewed-value');service,sid=self.conversation()
        self.turn(service,sid)
        with self.store.connection() as db:raw=db.execute('SELECT result FROM conversation_turns').fetchone()[0]
        self.assertNotIn('private-reviewed-value',raw)
        # The user's retained question can name an entity; the memory payload is
        # bindings only and must not duplicate its display name or reviewed value.
        self.assertNotIn('Beacon Programme',json.dumps(json.loads(raw)['packet']['memory']))
        self.assertNotIn('The original assignment',raw);self.assertNotIn('"excerpt"',raw)
        self.assertIn('quote_hash',raw);self.assertIn('claim_id',raw)

    def test_changed_review_clears_stored_result_on_view(self):
        cid=self.claim();service,sid=self.conversation();self.turn(service,sid);self.review(cid,'withdraw')
        turn=service.view(self.owner,sid)['turns'][0];self.assertEqual(turn['state'],'source_changed');self.assertIsNone(turn['result'])
        with self.store.connection() as db:self.assertIsNone(db.execute('SELECT result FROM conversation_turns').fetchone()[0])

    def test_expiry_clears_saved_result(self):
        self.claim(valid_until=1001);service,sid=self.conversation();self.turn(service,sid);self.clock[0]=1001
        self.assertEqual(service.view(self.owner,sid)['turns'][0]['state'],'source_changed')

    def test_new_conflict_clears_saved_result(self):
        self.claim();service,sid=self.conversation();self.turn(service,sid);self.claim(object_id='sam',line=3)
        self.assertEqual(service.view(self.owner,sid)['turns'][0]['state'],'source_changed')

    def test_mid_inference_review_change_never_persists_packet(self):
        cid=self.claim();model=PacketFixture(lambda:self.review(cid,'withdraw'));service,sid=self.conversation(model)
        turn=self.turn(service,sid,mode='local_model');self.assertEqual(turn['state'],'source_changed');self.assertIsNone(turn['result'])

    def test_followup_uses_user_topic_to_find_reviewed_memory(self):
        self.claim();service,sid=self.conversation();self.turn(service,sid)
        turn=self.turn(service,sid,'Who owns that?',follow=True)
        self.assertEqual(len(turn['result']['packet']['memory']),1)
        self.assertIn('beacon',turn['result']['packet']['retrieval_question'])

    def test_new_topic_drops_previous_reviewed_memory(self):
        self.claim();service,sid=self.conversation();self.turn(service,sid)
        turn=self.turn(service,sid,'xylophonezzz');self.assertEqual(turn['result']['packet']['memory'],[])

    def test_namesakes_do_not_call_conversation_model(self):
        self.claim();self.entity('namesake',name='Beacon Programme');model=PacketFixture();service,sid=self.conversation(model)
        turn=self.turn(service,sid,mode='local_model')
        self.assertEqual(turn['result']['status'],'memory_needs_clarification');self.assertEqual(model.packets,[])

    def test_memory_does_not_grant_draft_authority_without_separate_approval(self):
        self.claim();service,sid=self.conversation();action=self.draft(service,sid,self.turn(service,sid))
        self.store.tick(self.owner);self.assertEqual(self.store.desk_state(self.owner)['counts']['drafts'],0)
        self.store.approve(self.owner,action['id'],action['fingerprint']);self.store.tick(self.owner)
        self.assertEqual(self.store.desk_state(self.owner)['counts']['drafts'],1)

    def test_changed_review_prevents_draft_proposal(self):
        cid=self.claim();service,sid=self.conversation();turn=self.turn(service,sid);self.review(cid,'withdraw')
        self.fault('evidence_not_current',lambda:self.draft(service,sid,turn))

    def test_changed_review_prevents_draft_approval(self):
        cid=self.claim();service,sid=self.conversation();action=self.draft(service,sid,self.turn(service,sid))
        self.review(cid,'dispute')
        with self.assertRaises(Fault):self.store.approve(self.owner,action['id'],action['fingerprint'])
        self.assertEqual(self.store.desk_state(self.owner)['counts']['drafts'],0)

    def test_changed_review_prevents_already_approved_dispatch(self):
        cid=self.claim();service,sid=self.conversation();action=self.draft(service,sid,self.turn(service,sid))
        self.store.approve(self.owner,action['id'],action['fingerprint']);self.review(cid,'withdraw');self.store.tick(self.owner)
        self.assertEqual(self.store.desk_state(self.owner)['counts']['drafts'],0)

    def test_new_conflict_prevents_already_approved_dispatch(self):
        self.claim();service,sid=self.conversation();action=self.draft(service,sid,self.turn(service,sid))
        self.store.approve(self.owner,action['id'],action['fingerprint']);self.claim(object_id='sam',line=3);self.store.tick(self.owner)
        self.assertEqual(self.store.desk_state(self.owner)['counts']['drafts'],0)

    def test_new_namesake_prevents_already_approved_dispatch(self):
        self.claim();service,sid=self.conversation();action=self.draft(service,sid,self.turn(service,sid))
        self.store.approve(self.owner,action['id'],action['fingerprint']);self.entity('namesake',name='Beacon Programme');self.store.tick(self.owner)
        self.assertEqual(self.store.desk_state(self.owner)['counts']['drafts'],0)

    def test_historical_source_only_turn_and_action_list_binding_remain_compatible(self):
        service,sid=self.conversation();turn=self.turn(service,sid,'original record');action=self.draft(service,sid,turn)
        with self.store.transaction() as db:
            row=db.execute('SELECT result FROM conversation_turns').fetchone();result=json.loads(row['result'])
            result['packet'].pop('memory');result['packet'].pop('memory_ambiguities')
            db.execute('UPDATE conversation_turns SET result=?',(json.dumps(result),))
            db.execute('UPDATE conversation_action_sources SET references_json=?',(json.dumps(references(result['packet'])),))
        self.assertEqual(service.view(self.owner,sid)['turns'][0]['state'],'completed')
        self.store.approve(self.owner,action['id'],action['fingerprint']);self.store.tick(self.owner)
        self.assertEqual(self.store.desk_state(self.owner)['counts']['drafts'],1)


class ContextHTTPTests(Fixture):
    def setUp(self):
        super().setUp();self.claim()
        class Supervisor:scope='work'
        self.server=DeskHTTPServer(self.store,Supervisor(),port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close_server);self.cookie='';self.csrf=''
        _,value,headers=self.request('/desk/login',{'key':self.owner})
        self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=value['csrf']
    def close_server(self):
        self.server.conversations.stop();self.server.shutdown();self.server.server_close();self.thread.join(3)
    def request(self, path, body):
        conn=HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        headers={'Host':self.server.host,'Origin':self.server.origin,'Content-Type':'application/json'}
        if self.cookie:headers.update(Cookie=self.cookie,**{'X-CSRF-Token':self.csrf})
        conn.request('POST',path,json.dumps(body),headers);response=conn.getresponse();raw=json.loads(response.read())
        status=response.status;hs=dict(response.getheaders());conn.close();return status,raw,hs
    def test_actual_http_ask_and_combined_review_validation(self):
        status,result,_=self.request('/desk/ask',{'question':'Beacon Programme','mode':'sources'})
        self.assertEqual(status,200);p=result['packet'];self.assertEqual(len(p['memory']),1)
        body={'references':references(p),'memory_references':context_references(p),'memory_ambiguities':p['memory_ambiguities']}
        status,result,_=self.request('/desk/ask/check',body);self.assertEqual(status,200);self.assertTrue(result['current_index_match'])
        self.review(p['memory'][0]['claim_id'],'withdraw')
        status,result,_=self.request('/desk/ask/check',body);self.assertEqual(status,200);self.assertFalse(result['current_index_match'])
    def test_http_combined_check_detects_new_namesake(self):
        p=self.packet();self.entity('namesake',name='Beacon Programme')
        status,result,_=self.request('/desk/ask/check',{'references':references(p),'memory_references':context_references(p),'memory_ambiguities':[]})
        self.assertEqual(status,200);self.assertFalse(result['current_index_match'])
    def test_source_only_http_check_remains_compatible(self):
        status,result,_=self.request('/desk/ask/check',{'references':references(self.packet())})
        self.assertEqual(status,200);self.assertTrue(result['current_index_match'])


if __name__=='__main__':unittest.main()
