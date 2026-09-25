"""Knowledge routes inherit the existing authenticated, same-origin desk boundary."""
import re
from urllib.parse import parse_qs
from .local import Fault


def knowledge_get(store,bearer,url):
    if not hasattr(store,'knowledge'): raise Fault('knowledge_not_configured',404)
    if len(url.query)>1200: raise Fault('query_too_large')
    if url.path=='/desk/knowledge':
        query=parse_qs(url.query,keep_blank_values=True,strict_parsing=True)
        if set(query)-{'q','kind'} or any(len(v)!=1 for v in query.values()): raise Fault('invalid_query')
        return store.knowledge(bearer,query.get('q',[''])[0],query.get('kind',[''])[0])
    match=re.fullmatch(r'/desk/knowledge/notes/([0-9a-f]{24})',url.path)
    if match and not url.query: return store.knowledge_note(bearer,match[1])
    raise Fault('not_found',404)
