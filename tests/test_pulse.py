"""Actual SQLite and HTTP checks for two bounded, non-AI local routines."""
import concurrent.futures
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer
from alfred.local import Fault
from alfred.pulse import Pulse


class PulseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)/'desk';self.keys=init_demo(self.home)
        self.now=[1800000000]
        # Use freshly provisioned keys relative to the injectable clock.
        self.store=KnowledgeStore(self.home/'desk.sqlite',clock=lambda:self.now[0])
        self.keys={role:self.store.provision('pulse-space','pulse-'+role,role,ttl=2592000) for role in ('owner','reader','source')}
        self.sup=KnowledgeSupervisor(self.store,self.keys['owner'],self.keys['source'],self.home/'project',vault=self.home/'vault')
        self.pulse=Pulse(self.store,self.sup);self.sup.pulse=self.pulse
        self.sup.vault.scan()
    def run_report(self,identity='memory-health',request_id='test'):
        return self.pulse.manual(self.keys['owner'],identity,{'request_id':request_id})
    def configure(self,identity='memory-health',enabled=True,interval=60):
        return self.pulse.configure(self.keys['owner'],identity,{'enabled':enabled,'interval_seconds':interval})
    def test_initial_schedules_are_off(self):
        v=self.pulse.view(self.keys['owner']);self.assertEqual(len(v['routines']),2);self.assertTrue(all(not r['enabled'] for r in v['routines']));self.assertEqual(v['runs'],[])
    def test_no_automatic_run_without_opt_in(self):
        self.now[0]+=1000;self.pulse.cycle();self.assertEqual(self.pulse.view(self.keys['owner'])['runs'],[])
    def test_actual_memory_report(self):
        r=self.run_report();self.assertEqual(r['summary']['notes'],20);self.assertGreater(r['summary']['links_to_review'],0);self.assertFalse(r['external_effects'])
    def test_actual_briefing_report(self):
        r=self.run_report('briefing-refresh');self.assertEqual(r['summary']['local_drafts'],0);self.assertEqual(r['summary']['basis'],'latest_bounded_workspace_view')
    def test_manual_retry_does_not_repeat(self):
        a=self.run_report();b=self.run_report();self.assertEqual(a['id'],b['id']);self.assertTrue(b['duplicate']);self.assertEqual(len(self.pulse.view(self.keys['owner'])['runs']),1)
    def test_manual_runs_do_not_enable_schedule(self):
        self.run_report();self.assertFalse(self.pulse.view(self.keys['owner'])['routines'][1]['enabled'])
    def test_no_schedule_before_due(self):
        self.configure();self.now[0]+=59;self.pulse.cycle();self.assertEqual(self.pulse.view(self.keys['owner'])['runs'],[])
    def test_schedule_executes_when_due(self):
        self.configure();self.now[0]+=60;self.pulse.cycle();self.assertEqual(len(self.pulse.view(self.keys['owner'])['runs']),1)
    def test_due_slot_no_duplicate(self):
        self.configure();self.now[0]+=60
        for _ in range(5):self.pulse.cycle()
        self.assertEqual(len(self.pulse.view(self.keys['owner'])['runs']),1)
    def test_no_catchup_storm(self):
        self.configure();self.now[0]+=86400;self.pulse.cycle();self.assertEqual(len(self.pulse.view(self.keys['owner'])['runs']),1)
    def test_runs_and_schedule_survive_restart(self):
        self.configure();self.run_report();p=Pulse(KnowledgeStore(self.home/'desk.sqlite',clock=lambda:self.now[0]),self.sup)
        self.assertEqual(len(p.view(self.keys['owner'])['runs']),1);self.assertTrue(next(r for r in p.view(self.keys['owner'])['routines'] if r['id']=='memory-health')['enabled'])
    def test_pause_stops_manual(self):
        self.store.set_paused(self.keys['owner'],True)
        with self.assertRaises(Fault):self.run_report()
    def test_pause_stops_scheduled(self):
        self.configure();self.store.set_paused(self.keys['owner'],True);self.now[0]+=60;self.pulse.cycle();self.assertEqual(self.pulse.view(self.keys['owner'])['runs'],[])
    def test_disabled_schedule_stops_due_work(self):
        self.configure();self.now[0]+=60;self.configure(enabled=False);self.pulse.cycle();self.assertEqual(self.pulse.view(self.keys['owner'])['runs'],[])
    def test_reader_cannot_run(self):
        with self.assertRaises(Fault):self.pulse.manual(self.keys['reader'],'memory-health',{'request_id':'a'})
    def test_reader_cannot_enable(self):
        with self.assertRaises(Fault):self.pulse.configure(self.keys['reader'],'memory-health',{'enabled':True,'interval_seconds':60})
    def test_reader_can_inspect_history(self):
        self.run_report();self.assertTrue(self.pulse.view(self.keys['reader'])['runs'][0]['historical'])
    def test_source_cannot_inspect(self):
        with self.assertRaises(Fault):self.pulse.view(self.keys['source'])
    def test_revoked_owner_cannot_run(self):
        self.store.revoke('pulse-owner')
        with self.assertRaises(Fault):self.run_report()
    def test_expired_owner_cannot_run(self):
        self.now[0]+=2592001
        with self.assertRaises(Fault):self.run_report()
    def test_other_scope_has_no_history(self):
        self.run_report();other=self.store.provision('other','other-reader','reader');v=self.pulse.view(other);self.assertFalse(v['configured']);self.assertEqual(v['runs'],[])
    def test_other_scope_cannot_run(self):
        other=self.store.provision('other','other-owner','owner')
        with self.assertRaises(Fault):self.pulse.manual(other,'memory-health',{'request_id':'x'})
    def test_other_owner_cannot_reassign_running_host(self):
        other=self.store.provision('pulse-space','second-owner','owner')
        with self.assertRaises(Fault):self.pulse.configure(other,'memory-health',{'enabled':True,'interval_seconds':60})
    def test_extra_fields_cannot_execute_scripts(self):
        with self.assertRaises(Fault):self.pulse.manual(self.keys['owner'],'memory-health',{'request_id':'x','command':'echo forbidden'})
    def test_unknown_routine_rejected(self):
        with self.assertRaises(Fault):self.run_report('shell.execute')
    def test_interval_allowlist(self):
        for i in [True,-1,0,1,59,61,'60']:
            with self.subTest(i=i),self.assertRaises(Fault):self.configure(interval=i)
    def test_enabled_requires_boolean(self):
        with self.assertRaises(Fault):self.configure(enabled=1)
    def test_run_rate_limit(self):
        for i in range(6):self.run_report(request_id=str(i))
        with self.assertRaises(Fault) as e:self.run_report(request_id='extra')
        self.assertEqual(e.exception.code,'pulse_run_limit')
    def test_scheduled_rate_failure_visible_and_backed_off(self):
        self.configure()
        self.now[0]+=60
        for i in range(6):self.run_report(request_id=str(i))
        self.pulse.cycle();r=next(r for r in self.pulse.view(self.keys['owner'])['routines'] if r['id']=='memory-health')
        self.assertEqual(r['last_error'],'pulse_run_limit');self.assertGreater(r['next_due'],self.now[0])
    def test_output_does_not_store_bodies_or_credentials(self):
        self.run_report();s=json.dumps(self.pulse.view(self.keys['owner']));self.assertNotIn('monochrome',s)
        for key in self.keys.values():self.assertNotIn(key,s)
    def test_fault_is_recorded_not_success(self):
        with patch.object(self.store,'knowledge',side_effect=RuntimeError('PRIVATE-CONTENT')):
            with self.assertRaises(Fault):self.run_report()
        v=self.pulse.view(self.keys['owner']);self.assertEqual(v['runs'][0]['status'],'failed');self.assertNotIn('PRIVATE-CONTENT',json.dumps(v))
    def test_revocation_during_computation_discards_report(self):
        original=self.store.knowledge
        def revoke(*args):
            r=original(*args);self.store.revoke('pulse-owner');return r
        with patch.object(self.store,'knowledge',side_effect=revoke):
            with self.assertRaises(Fault):self.run_report()
        v=self.pulse.view(self.keys['reader']);self.assertEqual(v['runs'][0]['status'],'failed');self.assertNotIn('notes',v['runs'][0]['summary'])
    def test_source_revocation_removes_current_notes(self):
        self.store.revoke('pulse-source');r=self.run_report();self.assertEqual(r['summary']['notes'],0);self.assertEqual(r['state'],'attention')
    def test_concurrent_manual_requests_single_run(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _:self.run_report(),range(6)))
        self.assertEqual(len({r['id'] for r in results}),1);self.assertEqual(len(self.pulse.view(self.keys['owner'])['runs']),1)
    def test_unknown_metadata_version_rejected(self):
        with self.store.connection() as db:db.execute('UPDATE pulse_meta SET version=99')
        with self.assertRaises(Fault):Pulse(self.store,self.sup)
    def test_stale_inflight_is_not_success(self):
        with self.store.connection() as db:db.execute('INSERT INTO pulse_runs VALUES (?,?,?,?,?,?,?,?)',('pulse-space','x','memory-health','pulse-owner',self.now[0]-31,None,'running',None))
        self.assertEqual(self.pulse.view(self.keys['owner'])['runs'][0]['status'],'interrupted')


class PulseHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);h=Path(self.tmp.name)/'d';self.keys=init_demo(h)
        store=KnowledgeStore(h/'desk.sqlite');sup=KnowledgeSupervisor(store,self.keys['owner'],self.keys['source'],h/'project',vault=h/'vault');sup.cycle()
        self.server=DeskHTTPServer(store,sup,port=0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.stop)
        self.cookie=None;self.csrf=None
    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,path,body=None,headers=None):
        h={'Host':self.server.host,'Origin':self.server.origin,'Content-Type':'application/json'}
        if self.cookie:h['Cookie']=self.cookie
        if self.csrf:h['X-CSRF-Token']=self.csrf
        if headers:h.update(headers)
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3);c.request('POST' if body is not None else 'GET',path,body=json.dumps(body) if body is not None else None,headers=h);r=c.getresponse();data=json.loads(r.read());status=r.status
        if path=='/desk/login' and status==200:self.cookie=r.getheader('Set-Cookie').split(';')[0];self.csrf=data['csrf']
        c.close();return status,data
    def login(self,role='owner'):self.request('/desk/login',{'key':self.keys[role]})
    def test_no_auth_no_pulse(self):self.assertEqual(self.request('/desk/pulse')[0],401)
    def test_authenticated_view(self):self.login();self.assertEqual(len(self.request('/desk/pulse')[1]['routines']),2)
    def test_real_http_run(self):self.login();s,r=self.request('/desk/pulse/memory-health/run',{'request_id':'test'});self.assertEqual(s,200);self.assertEqual(r['summary']['notes'],20)
    def test_no_csrf_no_run(self):self.login();self.csrf=None;self.assertEqual(self.request('/desk/pulse/memory-health/run',{'request_id':'test'})[0],403)
    def test_reader_run_denied(self):self.login('reader');self.assertEqual(self.request('/desk/pulse/memory-health/run',{'request_id':'test'})[0],403)
    def test_scope_override_rejected(self):self.login();self.assertGreaterEqual(self.request('/desk/pulse?scope=other')[0],400)
    def test_remote_origin_rejected(self):self.login();self.assertEqual(self.request('/desk/pulse/memory-health/run',{'request_id':'test'}, {'Origin':'http://evil.invalid'})[0],403)
    def test_shell_endpoint_absent(self):self.login();self.assertEqual(self.request('/desk/pulse/execute/run',{'request_id':'test'})[0],404)
    def test_configuration_round_trip(self):
        self.login();s,r=self.request('/desk/pulse/memory-health/configure',{'enabled':True,'interval_seconds':300});self.assertEqual(s,200);self.assertTrue(next(v for v in r['routines'] if v['id']=='memory-health')['enabled'])
