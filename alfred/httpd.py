"""Loopback-only development HTTP API. Not a production web server."""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import sqlite3
from .local import Fault, LocalCore, exact, parse_json


def make_server(core: LocalCore, port: int = 8765) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = 'ALFRED-Local/0.2'
        sys_version = ''
        def log_message(self,*args):
            pass  # Never log bearer values or request bodies.
        def setup(self):
            super().setup()
            self.connection.settimeout(3)
        def reply(self,status,value):
            raw=json.dumps(value,allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)
        def dispatch(self):
            try:
                hosts={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
                if self.headers.get('Host') not in hosts:
                    raise Fault('host_rejected',403)
                if self.headers.get('Origin') is not None:
                    raise Fault('browser_origin_not_enabled',403)
                if self.command=='GET' and self.path=='/health':
                    self.reply(200,{'service':'alfred-local','version':'0.2.0-dev','live_ai':False,'effect':'local_draft_only'})
                    return
                values=self.headers.get_all('Authorization',[])
                if len(values)!=1 or not values[0].startswith('Bearer '):
                    raise Fault('unauthorised',401)
                bearer=values[0][7:]
                if self.command=='GET' and self.path=='/v1/state':
                    self.reply(200,core.state(bearer)); return
                if self.command!='POST':
                    raise Fault('not_found',404)
                if self.headers.get('Transfer-Encoding') is not None:
                    raise Fault('transfer_encoding_rejected')
                lengths=self.headers.get_all('Content-Length',[])
                if len(lengths)!=1 or not re.fullmatch(r'[0-9]{1,6}',lengths[0]):
                    raise Fault('length_required',411)
                size=int(lengths[0])
                if size>16384:
                    raise Fault('payload_too_large',413)
                if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
                    raise Fault('json_required',415)
                data=parse_json(self.rfile.read(size))
                if self.path=='/v1/events':
                    result=core.ingest(bearer,data)
                elif self.path=='/v1/actions':
                    result=core.propose(bearer,data)
                elif self.path=='/v1/worker/tick':
                    exact(data,set()); result=core.tick(bearer)
                else:
                    match=re.fullmatch(r'/v1/actions/([A-Za-z0-9][A-Za-z0-9_.-]{0,79})/(approve|cancel|reconcile)',self.path)
                    if not match:
                        raise Fault('not_found',404)
                    action_id,verb=match.groups()
                    if verb=='approve':
                        exact(data,{'fingerprint'}); result=core.approve(bearer,action_id,data['fingerprint'])
                    else:
                        exact(data,set()); result=getattr(core,verb)(bearer,action_id)
                self.reply(200,result)
            except Fault as exc:
                self.reply(exc.status,{'error':exc.code})
            except (ValueError,TypeError,KeyError):
                self.reply(400,{'error':'invalid_request'})
            except (sqlite3.Error,OSError):
                self.reply(503,{'error':'temporarily_unavailable'})
        do_GET=dispatch
        do_POST=dispatch
    return HTTPServer(('127.0.0.1',port),Handler)
