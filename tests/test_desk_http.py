"""Real-socket tests for the dedicated browser API and sessions."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from alfred.desk import init_demo
from alfred.desk_store import DeskStore
from alfred.desk_runtime import Supervisor
from alfred.desk_http import DeskHTTPServer, Sessions
from alfred.local import Fault


class DeskHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.keys=init_demo(self.root);self.store=DeskStore(self.root/'desk.sqlite')
        self.sup=Supervisor(self.store,self.keys['owner'],self.keys['source'],self.root/'project');self.sup.cycle()
        self.server=DeskHTTPServer(self.store,self.sup,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.01},daemon=True);self.thread.start()
        self.cookie=None;self.csrf=None
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.sup.stop();self.tmp.cleanup()
    def request(self,path,body=None,headers=None,method=None):
        method=method or ('POST' if body is not None else 'GET')
        h={'Host':self.server.host}
        if self.cookie:h['Cookie']=self.cookie
        if body is not None:h.update({'Origin':self.server.origin,'Content-Type':'application/json','X-CSRF-Token':self.csrf or ''})
        if headers:
            for k,v in headers.items():
                if v is None:h.pop(k,None)
                else:h[k]=v
        data=json.dumps(body).encode() if body is not None and not isinstance(body,bytes) else body
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        conn.request(method,path,body=data,headers=h);r=conn.getresponse();raw=r.read();head=dict(r.getheaders());status=r.status;conn.close()
        value=json.loads(raw) if head.get('Content-Type','').startswith('application/json') else raw
        return status,value,head
    def login(self,role='owner'):
        status,data,headers=self.request('/desk/login',{'key':self.keys[role]});self.assertEqual(status,200)
        self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=data['csrf'];return headers
    def test_home_is_real_static_app(self):
        status,data,h=self.request('/');self.assertEqual(status,200);self.assertIn(b'ALFRED',data);self.assertIn("script-src 'self'",h['Content-Security-Policy'])
    def test_javascript_and_css_served(self):
        for name in ('app.js','app.css'):self.assertEqual(self.request('/assets/'+name)[0],200)
    def test_state_requires_session(self):self.assertEqual(self.request('/desk/state')[0],401)
    def test_bearer_is_not_a_browser_session(self):self.assertEqual(self.request('/desk/state',headers={'Authorization':'Bearer '+self.keys['owner']})[0],401)
    def test_login_cookie_attributes(self):
        value=self.login()['Set-Cookie'];self.assertIn('HttpOnly',value);self.assertIn('SameSite=Strict',value);self.assertNotIn('Domain=',value)
    def test_cookie_key_not_exposed_in_json(self):
        self.login();status,data,h=self.request('/desk/session');self.assertEqual(status,200);self.assertNotIn(self.keys['owner'],json.dumps(data))
    def test_login_invalid_key(self):self.assertEqual(self.request('/desk/login',{'key':'bad'})[0],401)
    def test_login_rejects_source_role(self):self.assertEqual(self.request('/desk/login',{'key':self.keys['source']})[0],403)
    def test_login_requires_origin(self):self.assertEqual(self.request('/desk/login',{'key':self.keys['owner']},{'Origin':None})[0],403)
    def test_cross_origin_login_rejected(self):self.assertEqual(self.request('/desk/login',{'key':self.keys['owner']},{'Origin':'https://other.example'})[0],403)
    def test_host_rebinding_denied(self):self.assertEqual(self.request('/',headers={'Host':'attacker.example'})[0],403)
    def test_proxy_headers_denied(self):self.assertEqual(self.request('/',headers={'X-Forwarded-Host':self.server.host})[0],403)
    def test_cross_site_get_denied(self):
        self.login();self.assertEqual(self.request('/desk/state',headers={'Sec-Fetch-Site':'cross-site'})[0],403)
    def test_missing_csrf_denied(self):
        self.login();self.assertEqual(self.request('/desk/pause',{'paused':True},{'X-CSRF-Token':None})[0],403)
    def test_wrong_csrf_denied(self):
        self.login();self.assertEqual(self.request('/desk/pause',{'paused':True},{'X-CSRF-Token':'bad'})[0],403)
    def test_same_origin_mutation_works(self):
        self.login();self.assertEqual(self.request('/desk/pause',{'paused':True})[0],200);self.assertTrue(self.store.paused(self.sup.scope))
    def test_reader_cannot_pause(self):
        self.login('reader');self.assertEqual(self.request('/desk/pause',{'paused':True})[0],403)
    def test_revocation_kills_live_session(self):
        self.login();self.store.revoke('demo-owner');self.assertEqual(self.request('/desk/state')[0],401)
    def test_logout_removes_session(self):
        self.login();self.assertEqual(self.request('/desk/logout',{})[0],200);self.assertEqual(self.request('/desk/state')[0],401)
    def test_sessions_do_not_survive_server_restart(self):
        self.login();self.server.sessions=Sessions(self.store);self.assertEqual(self.request('/desk/state')[0],401)
    def test_duplicate_cookie_rejected(self):
        self.login();self.assertEqual(self.request('/desk/state',headers={'Cookie':self.cookie+'; '+self.cookie})[0],401)
    def test_duplicate_json_keys_rejected(self):
        self.login();self.assertEqual(self.request('/desk/pause',b'{"paused":true,"paused":false}')[0],400)
    def test_large_body_rejected(self):
        self.login();self.assertEqual(self.request('/desk/pause',b'x'*16385)[0],413)
    def test_content_type_required(self):
        self.login();self.assertEqual(self.request('/desk/pause',{'paused':True},{'Content-Type':'text/plain'})[0],415)
    def test_unknown_fields_denied(self):
        self.login();self.assertEqual(self.request('/desk/pause',{'paused':True,'scope':'other'})[0],400)
    def test_get_cannot_execute_action(self):
        self.login();self.assertEqual(self.request('/desk/pause')[0],404)
    def test_no_arbitrary_filesystem_endpoint(self):
        self.login();self.assertEqual(self.request('/desk/files?path=/etc/passwd')[0],404)
    def test_state_not_cached(self):
        self.login();h=self.request('/desk/state')[2];self.assertEqual(h['Cache-Control'],'no-store')
    def test_permissions_policy_disables_microphone(self):self.assertIn('microphone=()',self.request('/')[2]['Permissions-Policy'])
    def test_cross_scope_evidence_denied(self):
        seq=self.store.desk_state(self.keys['owner'])['events'][0]['seq'];self.keys['other']=self.store.provision('other','other-owner','owner');self.login('other')
        self.assertEqual(self.request('/desk/evidence/'+str(seq))[0],404)
    def test_whole_socket_approval_flow(self):
        self.login();seq=self.request('/desk/state')[1]['events'][0]['seq']
        status,p,_=self.request('/desk/proposals',{'event_seq':seq,'text':'A real local draft.','request_id':'http-draft'});self.assertEqual(status,200)
        self.assertEqual(self.request('/desk/actions/http-draft/approve',{'fingerprint':p['fingerprint']})[0],200)
        self.sup.cycle();a=self.request('/desk/state')[1]['actions'][0];self.assertEqual(a['state'],'verified');self.assertFalse(a['proof']['sent'])
    def test_review_is_separate_from_acknowledgement(self):
        self.login();seq=self.request('/desk/state')[1]['events'][0]['seq'];self.assertEqual(self.request('/desk/evidence/'+str(seq)+'/acknowledge',{})[0],200)
        self.assertEqual(self.request('/desk/state')[1]['counts']['drafts'],0)
    def test_invalid_cursor_fails(self):
        self.login();self.assertEqual(self.request('/desk/state?before=bad')[0],400)
    def test_credential_not_in_error_response(self):
        self.login();self.store.revoke('demo-owner');self.assertNotIn(self.keys['owner'],json.dumps(self.request('/desk/state')[1]))
    def test_no_csrf_cookie_or_url(self):
        h=self.login();self.assertNotIn(self.csrf,h['Set-Cookie'])
    def test_existing_v02_api_not_exposed_by_new_server(self):
        self.login();self.assertEqual(self.request('/v1/worker/tick',{})[0],404)


if __name__=='__main__':unittest.main()
