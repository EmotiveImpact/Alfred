"""Apply reviewed additive v0.5 hooks to the exact v0.4 source, idempotently."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[1]


def patch(path, before_blob, marker, replacements):
    file=ROOT/path;raw=file.read_bytes();text=raw.decode()
    if marker in text:return
    digest=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    if digest!=before_blob:raise RuntimeError('Source changed; review rather than overwrite '+path)
    for old,new in replacements:
        if text.count(old)!=1:raise RuntimeError('Ambiguous integration anchor '+path+': '+old)
        text=text.replace(old,new)
    file.write_text(text)


def main():
    patch('alfred/desk_http.py','79cf6928e12e28940c024d3e9e99e48b86f0374c','from .grounded import ask',[
        ('from .knowledge_http import knowledge_get','from .knowledge_http import knowledge_get\nfrom .grounded import ask, check_sources'),
        ("ASSETS = {", "ASSETS = {'/assets/ask.js': ('ask.js', 'text/javascript; charset=utf-8'),\n          '/assets/ask.css': ('ask.css', 'text/css; charset=utf-8'),"),
        ('def __init__(self, store, supervisor, port=8765, assets=None):','def __init__(self, store, supervisor, port=8765, assets=None, local_model=None):'),
        ('self.store, self.supervisor, self.sessions = store, supervisor, Sessions(store)','self.store, self.supervisor, self.sessions = store, supervisor, Sessions(store)\n        self.local_model = local_model'),
        ("elif not mutation and url.path.startswith('/desk/knowledge'):","elif not mutation and url.path == '/desk/ask/status' and not url.query:\n                p = store.principal(bearer, {'owner', 'reader'})\n                result = {'local_model_configured': self.server.local_model is not None,\n                          'model': self.server.local_model.model if self.server.local_model else None,\n                          'model_allowed': p['role'] == 'owner' and p['scope'] == self.server.supervisor.scope,\n                          'default_mode': 'sources', 'tools_enabled': False}\n            elif mutation and url.path == '/desk/ask':\n                result = ask(store, bearer, body, self.server.local_model, self.server.supervisor.scope)\n            elif mutation and url.path == '/desk/ask/check':\n                exact(body, {'references'})\n                result = check_sources(store, bearer, body['references'])\n            elif not mutation and url.path.startswith('/desk/knowledge'):")])
    patch('alfred/desk.py','85daba7c98a752723d267cd609fd980ab09d6d9f','from .local_model import LocalOllama',[
        ('from .knowledge_demo import seed_vault','from .knowledge_demo import seed_vault\nfrom .local_model import LocalOllama'),
        ('def serve(path, port, vault=None):','def serve(path, port, vault=None, model=None, model_port=11434):'),
        ('server = DeskHTTPServer(store, supervisor, port=port)','server = DeskHTTPServer(store, supervisor, port=port, local_model=LocalOllama(model, model_port) if model else None)'),
        ("print('Synthetic project files only. Microphone and live AI are OFF. No external messages are sent.', flush=True)","print('Local development data. Microphone OFF. No external messages are sent.', flush=True)\n        print('Local model available only on explicit request.' if model else 'Source mode: no model configured.', flush=True)"),
        ("parser.add_argument('--role', choices=('owner', 'reader'), default='owner')","parser.add_argument('--local-model', help='Opt-in tool-free model on an operator-managed local Ollama server; no model is downloaded')\n    parser.add_argument('--model-port', type=int, default=11434)\n    parser.add_argument('--role', choices=('owner', 'reader'), default='owner')"),
        ('serve(path, args.port, args.vault)','serve(path, args.port, args.vault, args.local_model, args.model_port)')])
    patch('web/index.html','bdf3d4c274d323a3d1757d692e1f953ad8e3b918','/assets/ask.js',[
        ('</head>','  <link rel="stylesheet" href="/assets/ask.css">\n  <script src="/assets/ask.js" defer></script>\n</head>'),
        ('ALFRED / DESK 0.4','ALFRED / DESK 0.5')])
    print('Applied additive source-first question hooks. Existing Desk and Knowledge behaviour preserved.')


if __name__=='__main__':main()
