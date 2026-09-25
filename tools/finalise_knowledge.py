"""Apply reviewed additive hardening and UI integration to named owned files."""
from integrate_knowledge import replace, main as integrate


def main():
    integrate()
    replace('alfred/knowledge.py',"    value.encode('utf-8')\n    return value", "    try: value.encode('utf-8')\n    except UnicodeError: raise Fault('invalid_note_unicode') from None\n    return value")
    replace('alfred/knowledge.py',"item = re.fullmatch(r'\\s+-\\s+(.+)', line)","item = re.fullmatch(r'\\s*-\\s+(.+)', line)")
    replace('alfred/knowledge.py',"    parsed = urlsplit(target)","    try: parsed = urlsplit(target)\n    except ValueError: return None, 'malformed_link'")
    replace('alfred/knowledge.py',"        with self.connection() as db:\n            p = self.authenticate(db,bearer,{'owner','reader'}); scope = p['scope']", "        with self.transaction() as db:\n            p = self.authenticate(db,bearer,{'owner','reader'}); scope = p['scope']")
    replace('alfred/knowledge.py',"            old = db.execute('SELECT snapshot FROM knowledge_sources WHERE scope=? AND source=?', (scope, source)).fetchone()", "            if db.execute('SELECT count(*) FROM knowledge_notes WHERE scope=?', (scope,)).fetchone()[0] + len(notes) > 10000:\n                raise Fault('knowledge_history_capacity')\n            old = db.execute('SELECT snapshot FROM knowledge_sources WHERE scope=? AND source=?', (scope, source)).fetchone()")
    replace('alfred/knowledge.py',"                except Fault:\n                    pass\n            super().cycle()", "                except Exception:\n                    self.vault.health={'configured':True,'status':'unavailable','last_scan':self.store.now(),'errors':[{'code':'knowledge_scan_failed'}]}\n            super().cycle()")
    replace('alfred/desk.py',"from .local import Fault", "from .local import Fault\nfrom .knowledge_demo import seed_vault")
    replace('alfred/desk.py',"    return credentials", "    seed_vault(path / 'vault')\n    return credentials")
    replace('alfred/knowledge_http.py',"from .local import Fault", "from .local import Fault\nfrom .knowledge_context import build_packet")
    replace('alfred/knowledge_http.py',"    if url.path=='/desk/knowledge':", "    if url.path=='/desk/knowledge/context':\n        query=parse_qs(url.query,keep_blank_values=True,strict_parsing=True)\n        if set(query)!={'q'} or len(query['q'])!=1: raise Fault('invalid_query')\n        return build_packet(store,bearer,query['q'][0])\n    if url.path=='/desk/knowledge':")
    replace('alfred/desk_http.py',"server_version = 'ALFRED-Desk/0.3'", "server_version = 'ALFRED-Desk/0.4'")
    replace('alfred/desk_http.py',"{'version': '0.3.0-dev', 'local_only': True, 'live_ai': False}","{'version': '0.4.0-dev', 'local_only': True, 'live_ai': False}")
    replace('web/knowledge.js',"bar.append(search,select,views);", "const packet=button('Source packet','outline',()=>act(async()=>{\n      if(!state.query.trim()){showToast('Enter search keywords to prepare a source packet.');return;}\n      const gen=ui.generation;const result=await api('/desk/knowledge/context?q='+encodeURIComponent(state.query));\n      if(gen!==ui.generation||ui.view!=='knowledge')return;\n      setDialog('KNOWLEDGE / RETRIEVAL PACKET');const root=$('detail-body');root.replaceChildren();\n      const title=node('h2','','Your source packet');title.id='detail-title';root.append(title,node('p','accessible-note','Exact note excerpts, not an AI-generated answer. Nothing was sent to a model.'));\n      result.evidence.forEach(e=>{root.append(node('h3','',e.title),node('p','knowledge-path',e.path+' · lines '+e.start_line+'–'+e.end_line),node('pre','knowledge-source',e.excerpt),node('p','mono','SHA-256 '+e.sha256));});\n      if(!result.evidence.length)root.append(node('p','','No matching source excerpts. Try more specific keywords.'));\n      if(!$('detail').open)$('detail').showModal();\n    }));\n    bar.append(search,select,views,packet);")


if __name__=='__main__':main()
