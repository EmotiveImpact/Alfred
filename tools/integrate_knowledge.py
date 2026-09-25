"""One-shot, reviewed additive source patch. Fails on unexpected baseline text.

Not an installer. Operates only on named ALFRED-owned source files in this repo.
"""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def replace(path,old,new):
    file=ROOT/path;data=file.read_text()
    if new in data: return
    if data.count(old)!=1: raise RuntimeError('Unexpected baseline: '+path)
    file.write_text(data.replace(old,new))


def main():
    replace('alfred/desk.py','from .desk_store import DeskStore','from .knowledge import KnowledgeStore as DeskStore')
    replace('alfred/desk.py','from .desk_runtime import Supervisor','from .knowledge import KnowledgeSupervisor as Supervisor')
    replace('alfred/desk.py','def serve(path, port):','def serve(path, port, vault=None):')
    replace('alfred/desk.py',"supervisor = Supervisor(store, keys['owner'], keys['source'], path / 'project')", "supervisor = Supervisor(store, keys['owner'], keys['source'], path / 'project', vault=vault or (path / 'vault' if (path / 'vault').is_dir() else None))")
    replace('alfred/desk.py',"parser.add_argument('--credential-id')", "parser.add_argument('--credential-id')\n    parser.add_argument('--vault', help='Explicit read-only Markdown folder; no Obsidian plugins are loaded')")
    replace('alfred/desk.py','serve(path, args.port)','serve(path, args.port, args.vault)')
    replace('alfred/desk_http.py',"from .local import Fault, exact, parse_json", "from .local import Fault, exact, parse_json\nfrom .knowledge_http import knowledge_get")
    replace('alfred/desk_http.py',"ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),", "ASSETS = {'/assets/knowledge.js': ('knowledge.js', 'text/javascript; charset=utf-8'),\n          '/assets/knowledge.css': ('knowledge.css', 'text/css; charset=utf-8'),\n          '/': ('index.html', 'text/html; charset=utf-8'),")
    replace('alfred/desk_http.py',"elif not mutation and re.fullmatch(r'/desk/evidence/[0-9]+', url.path) and not url.query:","elif not mutation and url.path.startswith('/desk/knowledge'):\n                result = knowledge_get(store, bearer, url)\n            elif not mutation and re.fullmatch(r'/desk/evidence/[0-9]+', url.path) and not url.query:")
    replace('web/index.html','  <script src="/assets/app.js" defer></script>', '  <script src="/assets/app.js" defer></script>\n  <link rel="stylesheet" href="/assets/knowledge.css">\n  <script src="/assets/knowledge.js" defer></script>')
    replace('web/index.html','      <button data-view="activity">', '      <button data-view="knowledge"><span aria-hidden="true">⌬</span>Knowledge</button>\n      <button data-view="activity">')
    replace('web/index.html','ALFRED / DESK 0.3','ALFRED / DESK 0.4')


if __name__=='__main__': main()
