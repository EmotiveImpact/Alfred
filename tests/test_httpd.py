import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from alfred.httpd import make_server
from alfred.local import LocalCore


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.core=LocalCore(Path(self.temp.name)/'api.sqlite',lambda:100)
        self.owner=self.core.provision('work','owner','owner')
        self.source=self.core.provision('work','source','source')
        self.reader=self.core.provision('work','reader','reader')
        self.server=make_server(self.core,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()
    def call(self,method,path,data=None,token=None,headers=None,raw=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        h={'Content-Type':'application/json'}
        if token: h['Authorization']='Bearer '+token
        h.update(headers or {})
        body=raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
        connection.request(method,path,body=body,headers=h)
        result=connection.getresponse(); status=result.status; response_headers=dict(result.getheaders())
        value=json.loads(result.read()); connection.close()
        return status,value,response_headers
    def test_real_socket_health(self):
        status,data,_=self.call('GET','/health')
        self.assertEqual(status,200); self.assertFalse(data['live_ai'])
    def test_missing_bearer(self): self.assertEqual(self.call('GET','/v1/state')[0],401)
    def test_invalid_bearer(self): self.assertEqual(self.call('GET','/v1/state',token='x'*43)[0],401)
    def test_authenticated_state(self):
        status,data,_=self.call('GET','/v1/state',token=self.owner)
        self.assertEqual((status,data['scope']),(200,'work'))
    def test_host_rebinding_rejected(self):
        self.assertEqual(self.call('GET','/health',headers={'Host':'evil.example'})[0],403)
    def test_browser_origin_not_enabled(self):
        self.assertEqual(self.call('GET','/v1/state',token=self.owner,headers={'Origin':'https://evil.example'})[0],403)
    def test_no_cache(self):
        self.assertEqual(self.call('GET','/v1/state',token=self.owner)[2]['Cache-Control'],'no-store')
    def test_read_only_cannot_tick(self):
        self.assertEqual(self.call('POST','/v1/worker/tick',{},self.reader)[0],403)
    def test_no_bootstrap_endpoint(self):
        self.assertEqual(self.call('POST','/v1/provision',{},self.owner)[0],404)
    def test_no_arbitrary_execute_endpoint(self):
        self.assertEqual(self.call('POST','/v1/execute',{'command':'echo not-run'},self.owner)[0],404)
    def test_strict_content_type(self):
        self.assertEqual(self.call('POST','/v1/worker/tick',{},self.owner,{'Content-Type':'text/plain'})[0],415)
    def test_duplicate_keys_denied(self):
        self.assertEqual(self.call('POST','/v1/worker/tick',token=self.owner,raw=b'{"x":1,"x":2}')[1]['error'],'duplicate_json_key')
    def test_large_payload_denied(self):
        self.assertEqual(self.call('POST','/v1/worker/tick',token=self.owner,raw=b' '*16385)[0],413)
    def test_full_http_draft_flow(self):
        payload={'id':'http-draft','capability':'message.draft','parameters':{'text':'Synthetic API draft'},'expires_at':200}
        status,p,_=self.call('POST','/v1/actions',payload,self.owner); self.assertEqual(status,200)
        status,_,_=self.call('POST','/v1/actions/http-draft/approve',{'fingerprint':p['fingerprint']},self.owner); self.assertEqual(status,200)
        status,result,_=self.call('POST','/v1/worker/tick',{},self.owner)
        self.assertEqual((status,result['state']),(200,'verified')); self.assertFalse(result['proof']['sent'])
    def test_scope_override_rejected(self):
        self.assertEqual(self.call('POST','/v1/worker/tick',{'scope':'other'},self.owner)[0],400)
    def test_source_can_ingest(self):
        event={'id':'e1','subject':'project','kind':'note','basis':'reported','observed_at':90,'expires_at':200,'summary':'Synthetic event'}
        self.assertEqual(self.call('POST','/v1/events',event,self.source)[0],200)
    def test_revocation_effective_without_server_restart(self):
        self.core.revoke('owner')
        self.assertEqual(self.call('GET','/v1/state',token=self.owner)[0],401)


if __name__=='__main__': unittest.main()
