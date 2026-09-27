"""Actual HTTP session/CSRF boundary for reviewed memory and report retention."""
from pathlib import Path
import tempfile,threading,json,unittest,http.client
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore,KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer

class MemoryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.home=Path(self.tmp.name)/'demo';self.keys=init_demo(self.home)
        self.store=KnowledgeStore(self.home/'desk.sqlite');self.sup=KnowledgeSupervisor(self.store,self.keys['owner'],self.keys['source'],self.home/'project',vault=self.home/'vault');self.sup.cycle()
        self.server=DeskHTTPServer(self.store,self.sup,port=0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.cookie=None;self.csrf=None
        self.addCleanup(self.close)
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(3)
    def req(self,path,data=None,auth=True,csrf=True,origin=True):
        headers={}
        if auth and self.cookie:headers['Cookie']=self.cookie
        if data is not None:
            headers['Content-Type']='application/json'
            if origin:headers['Origin']=self.server.origin
            if csrf and self.csrf:headers['X-CSRF-Token']=self.csrf
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        c.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,headers)
        r=c.getresponse();raw=r.read();status=r.status;cookie=r.getheader('Set-Cookie');c.close()
        return status,json.loads(raw),cookie
    def login(self,role='owner'):
        code,data,cookie=self.req('/desk/login',{'key':self.keys[role]});self.assertEqual(code,200);self.cookie=cookie.split(';')[0];self.csrf=data['csrf']
    def create(self):return self.req('/desk/memory/entities',{'id':'atlas','kind':'project','name':'Atlas'})
    def test_read_requires_auth(self):self.assertEqual(self.req('/desk/memory')[0],401)
    def test_entity_real_roundtrip(self):
        self.login();self.assertEqual(self.create()[0],200);self.assertEqual(self.req('/desk/memory')[1]['entities'][0]['name'],'Atlas')
    def test_csrf_required(self):
        self.login();self.assertEqual(self.req('/desk/memory/entities',{'id':'x','kind':'person','name':'X'},csrf=False)[0],403)
    def test_origin_required(self):
        self.login();self.assertEqual(self.req('/desk/memory/entities',{'id':'x','kind':'person','name':'X'},origin=False)[0],403)
    def test_reader_write_denied(self):self.login('reader');self.assertEqual(self.create()[0],403)
    def test_forged_scope_field_denied(self):
        self.login();self.assertEqual(self.req('/desk/memory/entities',{'id':'x','name':'X','kind':'person','scope':'foreign'})[0],400)
    def test_query_cannot_change_scope(self):self.login();self.assertEqual(self.req('/desk/memory?scope=foreign')[0],404)
    def test_export_actor_private(self):
        self.login();self.create();self.login('reader');self.assertEqual(self.req('/desk/memory/export')[1]['entities'],[])
    def test_similar_prefix_does_not_mutate(self):self.login();self.assertEqual(self.req('/desk/memory-nope/entities',{})[0],404)
    def test_unknown_review_does_not_create_record(self):
        self.login();self.assertEqual(self.req('/desk/memory/claims/nope/review',{'version':1,'decision':'accept','replaces_id':None,'replaces_version':None})[0],404)
    def test_full_http_review(self):
        self.login();self.create();n=self.req('/desk/knowledge')[1]['nodes'][0]
        body={'request_id':'http','subject_id':'atlas','predicate':'status','object_id':None,'value':'planning','valid_from':None,'valid_until':None,'evidence':{'note_id':n['id'],'sha256':n['sha256'],'revision':n['revision'],'start_line':1,'end_line':1}}
        code,r,_=self.req('/desk/memory/proposals',body);self.assertEqual(code,200)
        code,r,_=self.req('/desk/memory/claims/'+r['id']+'/review',{'version':1,'decision':'accept','replaces_id':None,'replaces_version':None});self.assertEqual(code,200);self.assertEqual(r['counts']['usable'],1)
    def test_history_csrf_and_preview(self):
        self.login();code,plan,_=self.req('/desk/pulse/history');self.assertEqual(code,200)
        self.assertEqual(self.req('/desk/pulse/history',{'fingerprint':plan['fingerprint']},csrf=False)[0],403)
        self.assertEqual(self.req('/desk/pulse/history',{'fingerprint':plan['fingerprint']})[0],200)
    def test_history_reader_denied(self):self.login('reader');self.assertEqual(self.req('/desk/pulse/history')[0],403)
    def test_revocation_clears_access(self):
        self.login();self.create();self.store.revoke('demo-owner');self.assertEqual(self.req('/desk/memory')[0],401)
if __name__=='__main__':unittest.main()
