"""Original desk integration tests. Real SQLite/files, no upstream runtime."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from alfred.desk import init_demo
from alfred.desk_store import DeskStore
from alfred.desk_runtime import ProjectFiles, Supervisor
from alfred.local import Fault


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.keys=init_demo(self.root); self.now=[int(time.time())]
        self.store=DeskStore(self.root/'desk.sqlite',clock=lambda:self.now[0])
        self.sup=Supervisor(self.store,self.keys['owner'],self.keys['source'],self.root/'project',interval=.05)
        self.sup.cycle()
    def tearDown(self):
        self.sup.stop(); self.tmp.cleanup()
    def state(self, role='owner', **kwargs):
        return self.store.desk_state(self.keys[role],**kwargs)
    def event(self):
        return next(e for e in self.state()['events'] if e['filename']=='schedule.json')
    def propose(self, request_id='test-draft'):
        return self.store.propose_from_evidence(self.keys['owner'],{'event_seq':self.event()['seq'],'text':'Please review the sample change.','request_id':request_id})
    def queue(self):
        p=self.propose(); self.store.approve(self.keys['owner'],p['id'],p['fingerprint']);return p
    def revise(self, **updates):
        path=self.root/'project/schedule.json'; value=json.loads(path.read_text())
        value.update({'revision':value['revision']+1,'observed_at':self.now[0],'expires_at':self.now[0]+600})
        value.update(updates);path.write_text(json.dumps(value))
    def test_old_core_refuses_desk_database(self):
        from alfred.local import LocalCore
        with self.assertRaises(Fault): LocalCore(self.root/'desk.sqlite')
    def test_three_documents_imported(self):
        self.assertEqual(self.state()['counts']['events'],3)
        self.assertTrue(all(e['status']=='current' for e in self.state()['events']))
    def test_connector_does_not_change_source_bytes(self):
        before={p.name:p.read_bytes() for p in (self.root/'project').iterdir()};self.sup.cycle()
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'project').iterdir()})
    def test_source_hash_is_exact(self):
        e=self.event();self.assertEqual(e['source_sha256'],hashlib.sha256((self.root/'project/schedule.json').read_bytes()).hexdigest())
    def test_repeated_scan_no_duplicate_event(self):
        self.sup.cycle();self.sup.cycle();self.assertEqual(self.state()['counts']['events'],3)
    def test_restart_keeps_events_and_dedup(self):
        self.store=DeskStore(self.root/'desk.sqlite',clock=lambda:self.now[0]);self.sup.cycle();self.assertEqual(self.state()['counts']['events'],3)
    def test_revision_preserves_history_and_supersedes(self):
        old=self.event();self.revise();self.sup.cycle()
        self.assertEqual(self.store.evidence(self.keys['owner'],old['seq'])['status'],'superseded')
        self.assertEqual(self.event()['revision'],2)
    def test_same_revision_different_bytes_is_error(self):
        self.revise(revision=1);self.sup.cycle();self.assertEqual(self.event()['status'],'source_unavailable')
        self.assertEqual(self.sup.view(self.sup.scope)['source']['errors'][0]['code'],'revision_content_conflict')
    def test_revision_rollback_is_error(self):
        self.revise();self.sup.cycle();self.revise(revision=1);self.sup.cycle();self.assertEqual(self.event()['status'],'source_unavailable')
    def test_same_time_rejected_on_every_retry(self):
        self.revise(observed_at=self.event()['observed_at']);self.sup.cycle();self.sup.cycle()
        self.assertTrue(all(e['status']!='current' for e in self.state()['events'] if e['subject']=='schedule'))
    def test_deletion_removes_current_status_not_history(self):
        (self.root/'project/schedule.json').unlink();self.sup.cycle()
        self.assertEqual(self.event()['status'],'source_unavailable');self.assertEqual(self.state()['counts']['events'],3)
    def test_restoration_recovers_identical_document(self):
        p=self.root/'project/schedule.json';raw=p.read_bytes();p.unlink();self.sup.cycle();p.write_bytes(raw);self.sup.cycle();self.assertEqual(self.event()['status'],'current')
    def test_invalid_json_fails_closed(self):
        (self.root/'project/schedule.json').write_text('{broken');self.sup.cycle();self.assertEqual(self.event()['status'],'source_unavailable')
    def test_duplicate_json_keys_rejected(self):
        (self.root/'project/schedule.json').write_text('{"revision":1,"revision":2}');self.sup.cycle();self.assertEqual(self.sup.source.health['errors'][0]['code'],'duplicate_json_key')
    def test_file_size_cap(self):
        (self.root/'project/schedule.json').write_bytes(b'x'*16385);self.sup.cycle();self.assertEqual(self.sup.source.health['errors'][0]['code'],'source_file_too_large')
    def test_symlink_not_followed(self):
        p=self.root/'project/schedule.json';p.unlink();p.symlink_to(self.root/'desk-access.json');self.sup.cycle();self.assertEqual(self.event()['status'],'source_unavailable')
    def test_fifo_does_not_block(self):
        p=self.root/'project/schedule.json';p.unlink();os.mkfifo(p);self.sup.cycle();self.assertEqual(self.sup.source.health['errors'][0]['code'],'regular_file_required')
    def test_nested_directory_not_scanned(self):
        d=self.root/'project/nested';d.mkdir();(d/'secret.json').write_text('bad');self.sup.cycle();self.assertEqual(self.sup.source.health['scanned_files'],3)
    def test_source_directory_replacement_fails_closed(self):
        d=self.root/'project';d.rename(self.root/'old-project');d.mkdir();self.sup.cycle();self.assertTrue(all(e['status']=='source_unavailable' for e in self.state()['events']))
    def test_document_identity_change_fails(self):
        self.revise(document_id='new-identity');self.sup.cycle();self.assertEqual(self.sup.source.health['errors'][0]['code'],'document_identity_changed')
    def test_revoked_source_invalidates_read_view(self):
        self.store.revoke('demo-source');self.assertTrue(all(e['status']=='source_unavailable' for e in self.state()['events']))
    def test_scope_is_resolved_from_reader_key(self):
        other=self.store.provision('other','other-reader','reader');self.assertEqual(self.store.desk_state(other)['events'],[])
        with self.assertRaises(Fault):self.store.evidence(other,self.event()['seq'])
    def test_reader_cannot_propose(self):
        with self.assertRaises(Fault):self.store.propose_from_evidence(self.keys['reader'],{'event_seq':self.event()['seq'],'text':'hello','request_id':'x'})
    def test_acknowledgement_is_per_actor_and_idempotent(self):
        seq=self.event()['seq'];self.store.acknowledge(self.keys['reader'],seq);self.store.acknowledge(self.keys['reader'],seq)
        self.assertTrue(self.store.evidence(self.keys['reader'],seq)['acknowledged']);self.assertFalse(self.store.evidence(self.keys['owner'],seq)['acknowledged'])
    def test_proposal_has_no_effect_without_approval(self):
        self.propose();self.sup.cycle();self.assertEqual(self.state()['counts']['drafts'],0)
    def test_approval_executes_automatically_on_cycle(self):
        self.queue();self.sup.cycle();a=self.state()['actions'][0];self.assertEqual(a['state'],'verified');self.assertFalse(a['proof']['sent'])
    def test_actual_background_loop_creates_approved_draft(self):
        self.queue();self.sup.start()
        deadline=time.monotonic()+3
        while self.state()['counts']['drafts']==0 and time.monotonic()<deadline:time.sleep(.02)
        self.assertEqual(self.state()['counts']['drafts'],1)
    def test_proposal_retry_is_idempotent(self):
        p=self.propose();self.now[0]+=1;self.assertEqual(self.propose()['fingerprint'],p['fingerprint']);self.assertEqual(self.state()['counts']['actions'],1)
    def test_request_id_collision_rejected(self):
        self.propose()
        with self.assertRaises(Fault):self.store.propose_from_evidence(self.keys['owner'],{'event_seq':self.event()['seq'],'text':'different','request_id':'test-draft'})
    def test_approval_hash_required(self):
        p=self.propose()
        with self.assertRaises(Fault):self.store.approve(self.keys['owner'],p['id'],'wrong')
    def test_new_revision_invalidates_approval(self):
        p=self.propose();self.revise();self.sup.cycle()
        with self.assertRaises(Fault):self.store.approve(self.keys['owner'],p['id'],p['fingerprint'])
    def test_new_revision_blocks_queued_effect(self):
        self.queue();self.revise();self.sup.cycle();self.assertEqual(self.state()['actions'][0]['state'],'blocked');self.assertEqual(self.state()['counts']['drafts'],0)
    def test_deleted_source_blocks_queued_effect(self):
        self.queue();(self.root/'project/schedule.json').unlink();self.sup.cycle();self.assertEqual(self.state()['counts']['drafts'],0)
    def test_pause_stops_scan_and_execution(self):
        self.queue();self.sup.set_paused(self.keys['owner'],True);self.revise();self.sup.cycle()
        self.assertEqual(self.state()['counts']['events'],3);self.assertEqual(self.state()['counts']['drafts'],0)
    def test_pause_survives_restart(self):
        self.sup.set_paused(self.keys['owner'],True);self.store=DeskStore(self.root/'desk.sqlite');self.assertTrue(self.store.paused(self.sup.scope))
    def test_resume_rechecks_source_before_execution(self):
        self.queue();self.sup.set_paused(self.keys['owner'],True);self.revise();self.sup.set_paused(self.keys['owner'],False);self.sup.cycle();self.assertEqual(self.state()['counts']['drafts'],0)
    def test_reader_cannot_pause(self):
        with self.assertRaises(Fault):self.sup.set_paused(self.keys['reader'],True)
    def test_cancel_before_worker_cycle(self):
        p=self.queue();self.store.cancel(self.keys['owner'],p['id']);self.sup.cycle();self.assertEqual(self.state()['counts']['drafts'],0)
    def test_source_expiry_is_recomputed(self):
        self.now[0]+=4000;self.assertEqual(self.event()['status'],'expired')
    def test_expired_evidence_cannot_propose(self):
        self.now[0]+=4000
        with self.assertRaises(Fault):self.propose()
    def test_expired_session_authority_blocks_worker(self):
        self.queue();self.store.revoke('demo-owner');self.sup.cycle();self.assertEqual(self.sup.worker_status,'attention')
    def test_unknown_post_crash_never_auto_resent(self):
        p=self.queue()
        with self.assertRaises(RuntimeError):self.store.tick(self.keys['owner'],crash_at='before_effect')
        self.now[0]+=31;self.sup.cycle();self.assertEqual(self.state()['actions'][0]['state'],'uncertain');self.assertEqual(self.state()['counts']['drafts'],0)
    def test_result_survives_restart(self):
        self.queue();self.sup.cycle();self.store=DeskStore(self.root/'desk.sqlite');self.assertEqual(self.state()['actions'][0]['state'],'verified')
    def test_page_cursor_has_no_duplicate_events(self):
        first=self.state(limit=2);second=self.state(before=first['next_cursor'],limit=2)
        self.assertEqual(len(first['events']),2);self.assertEqual(len(second['events']),1);self.assertNotEqual(first['events'][-1]['seq'],second['events'][0]['seq'])
    def test_invalid_page_limit_rejected(self):
        with self.assertRaises(Fault):self.state(limit=0)
    def test_source_health_no_other_workspace(self):
        self.assertIsNone(self.sup.view('other')['source'])
    def test_no_source_key_in_state(self):
        raw=json.dumps(self.state())
        for value in self.keys.values():self.assertNotIn(value,raw)
    def test_unknown_field_not_forwarded(self):
        self.revise(shell='bad');self.sup.cycle();self.assertEqual(self.event()['status'],'source_unavailable')
    def test_error_diagnostics_do_not_echo_secret_content(self):
        secret='PRIVATE_TEST_SENTINEL';(self.root/'project/schedule.json').write_text(secret);self.sup.cycle();self.assertNotIn(secret,json.dumps(self.sup.source.health))


if __name__=='__main__':unittest.main()
