"""Same-origin browser sessions for a loopback development desk, not hosting."""
from __future__ import annotations
from collections import deque
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit, parse_qs
from .local import Fault, exact, parse_json
from .knowledge_http import knowledge_get
from .grounded import ask, check_sources
from .pulse import Pulse
from .conversation import ConversationService
from .reviewed_memory import ReviewedMemory
from . import console_api

ASSETS = {'/assets/reviewed-memory.js': ('reviewed-memory.js', 'text/javascript; charset=utf-8'),
          '/assets/reviewed-memory.css': ('reviewed-memory.css', 'text/css; charset=utf-8'),'/assets/conversation.js': ('conversation.js', 'text/javascript; charset=utf-8'),
          '/assets/conversation.css': ('conversation.css', 'text/css; charset=utf-8'),'/assets/os.js': ('os.js', 'text/javascript; charset=utf-8'),
          '/assets/os.css': ('os.css', 'text/css; charset=utf-8'),'/assets/ask.js': ('ask.js', 'text/javascript; charset=utf-8'),
          '/assets/ask.css': ('ask.css', 'text/css; charset=utf-8'),'/assets/knowledge.js': ('knowledge.js', 'text/javascript; charset=utf-8'),
          '/assets/knowledge.css': ('knowledge.css', 'text/css; charset=utf-8'),
          '/': ('index.html', 'text/html; charset=utf-8'),
          '/assets/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/assets/app.css': ('app.css', 'text/css; charset=utf-8')}
CONSOLE_ASSET = re.compile(r'/console/(assets/[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.(?:js|css)|mark\.svg)')
CONSOLE_TYPES = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml'}
CONSOLE_MODE_DEMO = b'<meta name="alfred-mode" content="demo"/>'
CONSOLE_MODE_CONNECTED = b'<meta name="alfred-mode" content="connected"/>'


class Sessions:
    def __init__(self, store):
        self.store, self.items = store, {}
        self.failures = deque(maxlen=40)

    def limited(self, call):
        """Unauthenticated calls share one failure budget: 20 refusals a minute."""
        now = self.store.now()
        while self.failures and self.failures[0] < now - 60:
            self.failures.popleft()
        if len(self.failures) >= 20:
            raise Fault('login_rate_limited', 429)
        try:
            return call()
        except Fault:
            self.failures.append(now)
            raise

    def login(self, bearer):
        p = self.limited(lambda: self.store.principal(bearer))
        now = self.store.now()
        self.items = {k: v for k, v in self.items.items() if v['expires'] > now}
        if len(self.items) >= 32:
            raise Fault('session_capacity', 429)
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.items[hashlib.sha256(token.encode()).hexdigest()] = {
            'bearer': bearer, 'csrf': csrf, 'expires': min(now + 1800, p['expires'])}
        return token, csrf

    def get(self, token):
        if type(token) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise Fault('session_required', 401)
        key = hashlib.sha256(token.encode()).hexdigest()
        row = self.items.get(key)
        if not row or row['expires'] <= self.store.now():
            self.items.pop(key, None)
            raise Fault('session_expired', 401)
        try:
            self.store.principal(row['bearer'])
        except Fault:
            self.items.pop(key, None)
            raise
        return row

    def remove(self, token):
        self.items.pop(hashlib.sha256(token.encode()).hexdigest(), None)


class DeskHTTPServer(HTTPServer):
    allow_reuse_address = True
    def __init__(self, store, supervisor, port=8765, assets=None, local_model=None, console_dist=None, jobs=None):
        self.store, self.supervisor, self.sessions = store, supervisor, Sessions(store)
        self.jobs = jobs
        self.local_model = local_model
        self.memory = ReviewedMemory(store) if hasattr(store, 'knowledge') else None
        from .executive import ExecutiveRecords
        self.executive = ExecutiveRecords(store) if hasattr(store, 'knowledge') else None
        from .voice import VoiceLog
        self.voice = VoiceLog(store) if hasattr(store, 'knowledge') else None
        self.conversations = ConversationService(store, local_model, supervisor.scope) if hasattr(store, 'knowledge') else None
        self.pulse = Pulse(store, supervisor) if hasattr(store, 'knowledge') and hasattr(supervisor, 'owner') else None
        if self.pulse is not None: supervisor.pulse = self.pulse
        self.assets = Path(assets) if assets else Path(__file__).resolve().parents[1] / 'web'
        # The built premium console is served from this same loopback origin so
        # it inherits the session, CSRF, Host/Origin and CSP boundary unchanged.
        self.console_dist = Path(console_dist) if console_dist else Path(__file__).resolve().parents[1] / 'console' / 'dist'
        super().__init__(('127.0.0.1', port), Handler)
        self.host = f'127.0.0.1:{self.server_port}'
        self.origin = 'http://' + self.host
        # Cookies are not port-scoped: use a per-listener name to avoid accidental
        # collision. This remains unsuitable against a compromised local host.
        self.cookie_name = f'alfred_desk_{self.server_port}'

    def serve_forever(self, poll_interval=.1):
        if self.conversations: self.conversations.start()
        try: super().serve_forever(poll_interval)
        finally:
            if self.conversations: self.conversations.stop()

    def get_request(self):
        sock, addr = super().get_request()
        sock.settimeout(3)
        return sock, addr


class Handler(BaseHTTPRequestHandler):
    server_version = 'ALFRED-OS/0.8'
    sys_version = ''
    def log_message(self, *_):
        pass

    def console_file(self, path):
        root = self.server.console_dist.resolve()
        if path == '/console/':
            relative = 'index.html'
        else:
            match = CONSOLE_ASSET.fullmatch(path)
            if not match:
                raise Fault('not_found', 404)
            relative = match[1]
        file = root / relative
        if file.is_symlink() or not file.is_file() or root not in file.resolve().parents:
            raise Fault('console_not_built' if relative == 'index.html' else 'not_found', 404)
        data = file.read_bytes()
        if relative == 'index.html':
            if data.count(CONSOLE_MODE_DEMO) != 1:
                raise Fault('console_mode_marker_missing', 500)
            return data.replace(CONSOLE_MODE_DEMO, CONSOLE_MODE_CONNECTED), 'text/html; charset=utf-8'
        return data, CONSOLE_TYPES[file.suffix]

    def identity_route(self, path, mutation, bearer, body):
        """Identity, source grants and device pairing. Key rotation stays offline (it needs a stopped host)."""
        from .policy import IdentityPolicy
        policy, store = IdentityPolicy(self.server.store), self.server.store
        if not mutation and path == '/desk/identity':
            return policy.view(bearer)
        if not mutation:
            raise Fault('not_found', 404)
        def expiry(source, days):
            if type(days) is not int or not 1 <= days <= 30:
                raise Fault('invalid_grant_days')
            limit = next((s['credential_expires'] for s in policy.view(bearer)['sources'] if s['source'] == source), None)
            if limit is None:
                raise Fault('source_not_available', 404)
            return min(store.now() + days * 86400, limit)
        if path == '/desk/identity/enable':
            exact(body, {'epoch'})
            return policy.enable(bearer, body['epoch'])
        if path == '/desk/identity/grants':
            exact(body, {'source', 'capability', 'days', 'epoch', 'revoke'})
            if body['revoke'] is True:
                return policy.grant(bearer, body['source'], body['capability'], store.now() + 1, body['epoch'], revoke=True)
            return policy.grant(bearer, body['source'], body['capability'], expiry(body['source'], body['days']), body['epoch'])
        if path == '/desk/identity/invitations':
            exact(body, {'source', 'capability', 'days', 'epoch'})
            return policy.invite(bearer, body['source'], body['capability'], expiry(body['source'], body['days']), body['epoch'])
        if path == '/desk/identity/invitations/redeem':
            exact(body, {'code'})
            return policy.redeem(bearer, body['code'])
        if path == '/desk/identity/pairing':
            exact(body, {'role'})
            return policy.offer_pairing(bearer, body['role'])
        match = re.fullmatch(r'/desk/identity/devices/([A-Za-z0-9-]{1,40})/revoke', path)
        if match:
            exact(body, set())
            return policy.revoke_device(bearer, match.group(1))
        raise Fault('not_found', 404)

    def jobs_route(self, url, mutation, bearer, body):
        """Owner and reader job calls. Worker calls stay in-process with the host."""
        jobs = self.server.jobs
        if jobs is None:
            raise Fault('jobs_not_configured', 409)
        parts = url.path.split('/')[3:]
        if url.query and not (len(parts) == 2 and parts[1] == 'events' and not mutation):
            raise Fault('invalid_query')
        if parts == []:
            if mutation:
                return jobs.submit(bearer, body)
            from .jobs import BACKEND_NOTE
            return {'jobs': jobs.jobs(bearer), 'backend': BACKEND_NOTE}
        if parts == ['workers']:
            if not mutation:
                return {'workers': jobs.workers(bearer)}
            exact(body, {'id', 'label', 'capabilities'})
            return jobs.enrol_worker(bearer, body['id'], body['label'], body['capabilities'])
        if len(parts) == 3 and parts[0] == 'workers' and parts[2] == 'revoke' and mutation:
            exact(body, set())
            return jobs.revoke_worker(bearer, parts[1])
        if parts == ['recover'] and mutation:
            exact(body, set())
            return jobs.recover(bearer)
        if len(parts) == 2 and parts[0] == 'artefacts' and not mutation:
            artefact = jobs.artefact(bearer, parts[1])
            data = artefact.pop('data')
            # Returned as a JSON value, never served as a page.
            if artefact['media_type'] in ('application/json', 'text/plain'):
                artefact['text'] = data.decode('utf-8', errors='replace')
            else:
                import base64
                artefact['base64'] = base64.b64encode(data).decode('ascii')
            return artefact
        if len(parts) == 1 and not mutation:
            return jobs.view(bearer, parts[0])
        if len(parts) == 2 and parts[1] == 'events' and not mutation:
            query = parse_qs(url.query, strict_parsing=True) if url.query else {}
            if set(query) - {'after'} or any(len(v) != 1 for v in query.values()):
                raise Fault('invalid_query')
            after = query.get('after', ['0'])[0]
            if not re.fullmatch(r'[0-9]{1,9}', after):
                raise Fault('invalid_cursor')
            return jobs.events(bearer, parts[0], int(after))
        if len(parts) == 2 and parts[1] == 'cancel' and mutation:
            exact(body, set())
            return jobs.cancel(bearer, parts[0])
        if len(parts) == 2 and parts[1] == 'reconcile' and mutation:
            exact(body, {'finding'})
            return jobs.reconcile(bearer, parts[0], body['finding'])
        raise Fault('not_found', 404)

    def send_payload(self, status, value, *, content_type='application/json; charset=utf-8', cookie=None):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=True).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Permissions-Policy', 'microphone=(), camera=(), geolocation=()')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Connection', 'close')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def cookie(self):
        headers = self.headers.get_all('Cookie', [])
        if len(headers) != 1:
            raise Fault('session_required', 401)
        matches = []
        for part in headers[0].split(';'):
            k, sep, value = part.strip().partition('=')
            if sep and k == self.server.cookie_name:
                matches.append(value)
        if len(matches) != 1:
            raise Fault('session_required', 401)
        return matches[0]

    def request_guard(self, mutation=False):
        if self.headers.get_all('Host', []) != [self.server.host]:
            raise Fault('invalid_host', 403)
        origins = self.headers.get_all('Origin', [])
        if mutation and origins != [self.server.origin]:
            raise Fault('invalid_origin', 403)
        if origins and origins != [self.server.origin]:
            raise Fault('invalid_origin', 403)
        if self.headers.get('Sec-Fetch-Site') in {'cross-site', 'same-site'}:
            raise Fault('cross_origin_request', 403)
        if any(h in self.headers for h in ('X-Forwarded-Host', 'X-Forwarded-For', 'Forwarded')):
            raise Fault('proxy_not_supported', 403)

    def read_body(self):
        sizes = self.headers.get_all('Content-Length', [])
        if len(sizes) != 1 or not re.fullmatch(r'[0-9]{1,5}', sizes[0]):
            raise Fault('content_length_required', 411)
        if 'Transfer-Encoding' in self.headers:
            raise Fault('transfer_encoding_rejected')
        if self.headers.get_all('Content-Type', []) != ['application/json']:
            raise Fault('json_required', 415)
        size = int(sizes[0])
        if size > 16384:
            raise Fault('payload_too_large', 413)
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise Fault('incomplete_body')
        return parse_json(raw)

    def do_GET(self):
        self.handle_request(False)

    def do_POST(self):
        self.handle_request(True)

    def handle_request(self, mutation):
        try:
            self.request_guard(mutation)
            url = urlsplit(self.path)
            if url.scheme or url.netloc or url.fragment:
                raise Fault('invalid_path')
            if not mutation and url.path in ASSETS and not url.query:
                filename, mime = ASSETS[url.path]
                self.send_payload(200, (self.server.assets / filename).read_bytes(), content_type=mime)
                return
            if not mutation and url.path == '/console' and not url.query:
                self.send_response(308)
                self.send_header('Location', '/console/')
                self.send_header('Content-Length', '0')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Connection', 'close')
                self.end_headers()
                self.close_connection = True
                return
            if not mutation and url.path.startswith('/console/') and not url.query:
                data, mime = self.console_file(url.path)
                self.send_payload(200, data, content_type=mime)
                return
            if not mutation and url.path == '/favicon.ico':
                self.send_payload(200, b'', content_type='image/x-icon')
                return
            if not mutation and url.path == '/health' and not url.query:
                self.send_payload(200, {'version': '0.8.0-dev', 'local_only': True, 'live_ai': False, 'model_configured': self.server.local_model is not None})
                return
            if mutation and url.query:
                raise Fault('query_not_allowed')
            body = self.read_body() if mutation else None
            if mutation and url.path == '/desk/login':
                exact(body, {'key'})
                token, csrf = self.server.sessions.login(body['key'])
                # No Secure attribute on this HTTP-loopback-only development server.
                cookie = f'{self.server.cookie_name}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=1800'
                self.send_payload(200, {'csrf': csrf}, cookie=cookie)
                return
            if mutation and url.path == '/desk/identity/pairing/redeem':
                # The new device holds only a one-time code, so this precedes the session check.
                exact(body, {'code', 'label'})
                from .policy import IdentityPolicy
                paired = self.server.sessions.limited(
                    lambda: IdentityPolicy(self.server.store).redeem_pairing(body['code'], body['label']))
                token, csrf = self.server.sessions.login(paired['key'])
                cookie = f'{self.server.cookie_name}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=1800'
                self.send_payload(200, {'csrf': csrf, **paired}, cookie=cookie)
                return
            session_token = self.cookie()
            session = self.server.sessions.get(session_token)
            bearer, store = session['bearer'], self.server.store
            if mutation:
                csrf = self.headers.get_all('X-CSRF-Token', [])
                if len(csrf) != 1 or not secrets.compare_digest(csrf[0], session['csrf']):
                    raise Fault('csrf_rejected', 403)
            if not mutation and url.path == '/desk/session' and not url.query:
                p = store.principal(bearer)
                result = {'csrf': session['csrf'], 'scope': p['scope'], 'role': p['role'], 'expires_at': session['expires']}
            elif not mutation and url.path == '/desk/state':
                query = parse_qs(url.query, strict_parsing=True)
                if set(query) - {'before'} or any(len(v) != 1 for v in query.values()):
                    raise Fault('invalid_query')
                before = int(query['before'][0]) if 'before' in query else None
                result = store.desk_state(bearer, before=before)
                result['supervisor'] = self.server.supervisor.view(result['scope'])
            elif (url.path == '/desk/conversations' or url.path.startswith('/desk/conversations/')) and not url.query:
                service = self.server.conversations
                if service is None: raise Fault('conversation_not_configured',409)
                parts = url.path.split('/')[3:]
                if parts == []:
                    result = service.create(bearer,body) if mutation else service.listing(bearer)
                elif len(parts)==1 and not mutation:
                    result = service.view(bearer,parts[0])
                elif len(parts)==2 and mutation and parts[1] in {'turns','forget','draft'}:
                    if parts[1]=='turns': result=service.submit(bearer,parts[0],body)
                    elif parts[1]=='draft': result=service.propose_draft(bearer,parts[0],body)
                    else:
                        exact(body,set());result=service.forget(bearer,parts[0])
                else: raise Fault('not_found',404)
            elif (url.path == '/desk/memory' or url.path.startswith('/desk/memory/')) and not url.query:
                memory = self.server.memory
                if memory is None: raise Fault('memory_not_configured',409)
                if not mutation and url.path in ('/desk/memory','/desk/memory/export'):
                    result = memory.view(bearer)
                elif mutation and url.path == '/desk/memory/entities':
                    result = memory.create_entity(bearer,body)
                elif mutation and url.path == '/desk/memory/proposals':
                    result = memory.propose(bearer,body)
                elif mutation and url.path == '/desk/memory/capture':
                    result = memory.capture(bearer,body)
                elif mutation and re.fullmatch(r'/desk/memory/claims/[A-Za-z0-9_.-]+/review',url.path):
                    result = memory.review(bearer,url.path.split('/')[4],body)
                elif mutation and re.fullmatch(r'/desk/memory/claims/[A-Za-z0-9][A-Za-z0-9_.-]{0,79}/forget',url.path):
                    result = memory.forget(bearer,url.path.split('/')[4],body)
                elif mutation and re.fullmatch(r'/desk/memory/entities/[A-Za-z0-9][A-Za-z0-9_.-]{0,79}/forget',url.path):
                    result = memory.forget_entity(bearer,url.path.split('/')[4],body)
                elif not mutation and url.path == '/desk/memory/receipts':
                    from .lifecycle import receipts
                    result = receipts(store,bearer)
                elif not mutation and (url.path.endswith('/history') or url.path.startswith('/desk/memory/as-of/')):
                    # Recorded review history and the as-of report (MEM-007); reads only.
                    from .memory_history import MemoryHistory, route as history_route
                    result = history_route(MemoryHistory(memory),url.path,mutation,bearer)
                else: raise Fault('not_found',404)
            elif url.path.startswith('/desk/voice/playbacks') and not url.query:
                # VOI-001 playback records only. No route here accepts audio or requests a microphone.
                voice, rest = self.server.voice, url.path[len('/desk/voice/playbacks'):]
                if mutation and rest == '':
                    result = voice.generated(bearer, body)
                elif mutation and re.fullmatch(r'/voice-[0-9a-f]{20}/report', rest):
                    result = voice.report(bearer, rest.split('/')[1], body)
                elif mutation and re.fullmatch(r'/voice-[0-9a-f]{20}/acknowledge', rest):
                    result = voice.acknowledge(bearer, rest.split('/')[1], body)
                elif not mutation and re.fullmatch(r'/turn/[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', rest):
                    result = voice.history(bearer, rest.split('/')[2])
                else:
                    raise Fault('not_found', 404)
            elif mutation and re.fullmatch(r'/desk/sources/[A-Za-z0-9][A-Za-z0-9_.-]{0,79}/forget', url.path):
                # Removes the source from ALFRED, never the person's own files.
                exact(body, {'confirm'})
                if body['confirm'] != url.path.split('/')[3]:
                    raise Fault('confirmation_mismatch')
                from .lifecycle import forget_source
                jobs = self.server.jobs
                result = forget_source(store, bearer, url.path.split('/')[3], cache=jobs.cache if jobs is not None else None)
            elif url.path == '/desk/pulse/history' and not url.query:
                if self.server.pulse is None: raise Fault('pulse_not_configured',409)
                result = self.server.pulse.prune_history(bearer,body) if mutation else self.server.pulse.history_plan(bearer)
            elif not mutation and url.path == '/desk/pulse' and not url.query:
                if self.server.pulse is None: raise Fault('pulse_not_configured', 409)
                result = self.server.pulse.view(bearer)
            elif mutation and re.fullmatch(r'/desk/pulse/(memory-health|briefing-refresh)/(configure|run)', url.path):
                if self.server.pulse is None: raise Fault('pulse_not_configured', 409)
                routine, operation = url.path.split('/')[3:5]
                result = (self.server.pulse.configure if operation == 'configure' else self.server.pulse.manual)(bearer, routine, body)
            elif not mutation and url.path == '/desk/ask/status' and not url.query:
                p = store.principal(bearer, {'owner', 'reader'})
                result = {'local_model_configured': self.server.local_model is not None,
                          'model': self.server.local_model.model if self.server.local_model else None,
                          'model_allowed': p['role'] == 'owner' and p['scope'] == self.server.supervisor.scope,
                          'default_mode': 'sources', 'tools_enabled': False}
            elif mutation and url.path == '/desk/ask':
                if body.get('mode') == 'local_model' and getattr(self.server.local_model,'timeout',6)>6:
                    raise Fault('use_conversation_for_model',409)
                result = ask(store, bearer, body, self.server.local_model, self.server.supervisor.scope)
            elif mutation and url.path == '/desk/ask/check':
                keys={'references'}
                if 'memory_references' in body:keys.add('memory_references')
                if 'memory_ambiguities' in body:keys.add('memory_ambiguities')
                exact(body, keys)
                result = check_sources(store, bearer, body['references'], body.get('memory_references'),body.get('memory_ambiguities'))
            elif (url.path == '/desk/identity' or url.path.startswith('/desk/identity/')) and not url.query:
                result = self.identity_route(url.path, mutation, bearer, body)
            elif (url.path == '/desk/executive' or url.path.startswith('/desk/executive/')) and not url.query:
                executive = self.server.executive
                if executive is None: raise Fault('executive_not_configured', 409)
                if not mutation and url.path == '/desk/executive':
                    result = executive.view(bearer)
                elif mutation and url.path == '/desk/executive/records':
                    result = executive.create(bearer, body)
                elif mutation and url.path == '/desk/executive/recommendations/accept':
                    result = executive.accept_recommendation(bearer, body)
                elif mutation and re.fullmatch(r'/desk/executive/records/[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', url.path):
                    result = executive.update(bearer, url.path.rsplit('/', 1)[1], body)
                else:
                    from .executive_http import route as executive_route
                    result = executive_route(executive, url.path, mutation, bearer, body)
            elif url.path == '/desk/jobs' or url.path.startswith('/desk/jobs/'):
                result = self.jobs_route(url, mutation, bearer, body)
            elif not mutation and url.path == '/desk/console/workspaces' and not url.query:
                result = console_api.workspaces(store, bearer)
            elif not mutation and url.path == '/desk/console/projection' and not url.query:
                result = console_api.projection(self.server, bearer)
            elif not mutation and url.path == '/desk/console/health' and not url.query:
                result = console_api.health(self.server, bearer)
            elif not mutation and url.path.startswith('/desk/console/records/') and not url.query:
                result = console_api.record(self.server, bearer, url.path[len('/desk/console/records/'):])
            elif not mutation and url.path == '/desk/connectors' and not url.query:
                # Read-only status. Creating and importing stay offline commands.
                from .connectors import status as connector_status
                result = connector_status(store, bearer)
            elif not mutation and url.path.startswith('/desk/knowledge'):
                result = knowledge_get(store, bearer, url)
            elif not mutation and re.fullmatch(r'/desk/evidence/[0-9]+', url.path) and not url.query:
                result = store.evidence(bearer, int(url.path.rsplit('/', 1)[1]))
            elif mutation and url.path == '/desk/logout':
                exact(body, set())
                self.server.sessions.remove(session_token)
                self.send_payload(200, {'signed_out': True}, cookie=f'{self.server.cookie_name}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')
                return
            elif mutation and url.path == '/desk/pause':
                exact(body, {'paused'})
                result = self.server.supervisor.set_paused(bearer, body['paused'])
            elif mutation and url.path == '/desk/inbox/proposals':
                if not hasattr(store, 'vault_writers'): raise Fault('knowledge_not_configured', 409)
                from .inbox import propose as propose_inbox
                result = propose_inbox(store, bearer, body)
            elif mutation and url.path == '/desk/proposals':
                result = store.propose_from_evidence(bearer, body)
            elif mutation and re.fullmatch(r'/desk/evidence/[0-9]+/acknowledge', url.path):
                exact(body, set())
                result = store.acknowledge(bearer, int(url.path.split('/')[3]))
            elif mutation and re.fullmatch(r'/desk/actions/[A-Za-z0-9][A-Za-z0-9_.-]{0,79}/(approve|cancel|reconcile)', url.path):
                action_id, command = url.path.split('/')[3:5]
                if command == 'approve':
                    exact(body, {'fingerprint'})
                    result = store.approve(bearer, action_id, body['fingerprint'])
                else:
                    exact(body, set())
                    result = getattr(store, command)(bearer, action_id)
            else:
                raise Fault('not_found', 404)
            self.send_payload(200, result)
        except Fault as exc:
            self.send_payload(exc.status, {'error': exc.code})
        except (ValueError, UnicodeError):
            self.send_payload(400, {'error': 'invalid_request'})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except Exception:
            self.send_payload(500, {'error': 'internal_error'})
