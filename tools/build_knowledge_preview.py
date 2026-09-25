"""Package the actual Desk frontend with a read-only, fictional offline transport.

No production data, tokens, live API, local writes or model calls in the preview.
"""
from pathlib import Path
import base64
import hashlib
import json
import lzma
import tempfile
import textwrap
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore,KnowledgeSupervisor

ROOT=Path(__file__).resolve().parents[1]
MOCK=r'''
async function api(path,data) {
  if(data!==undefined) throw new Error('Offline preview is read only. Run the local application to use approvals.');
  const url=new URL(path,'http://preview.invalid');
  const copy=v=>JSON.parse(JSON.stringify(v));
  if(url.pathname==='/desk/session')return {csrf:'offline-preview',scope:PREVIEW.desk.scope,role:'reader'};
  if(url.pathname==='/desk/state')return copy(PREVIEW.desk);
  if(url.pathname.startsWith('/desk/evidence/')){const item=PREVIEW.desk.events.find(e=>e.seq===Number(url.pathname.split('/').pop()));if(item)return copy(item);}
  const q=(url.searchParams.get('q')||'').toLowerCase(),kind=url.searchParams.get('kind')||'';
  const terms=q.split(/\s+/).filter(Boolean);
  const matches=PREVIEW.knowledge.nodes.filter(n=>(!kind||n.kind===kind)&&terms.every(t=>(n.path+' '+n.title+' '+PREVIEW.notes[n.id].body).toLowerCase().includes(t)));
  if(url.pathname==='/desk/knowledge'){const result=copy(PREVIEW.knowledge);result.query=q;result.kind=kind;result.results=copy(matches);result.counts.matches=matches.length;return result;}
  if(url.pathname.startsWith('/desk/knowledge/notes/')){const note=PREVIEW.notes[url.pathname.split('/').pop()];if(note)return copy(note);}
  if(url.pathname==='/desk/knowledge/context')return {evidence:matches.slice(0,5).map(n=>{const v=PREVIEW.notes[n.id],lines=v.body.split('\n');const found=lines.findIndex(l=>terms.some(t=>l.toLowerCase().includes(t)));const start=Math.max(0,found-2);const text=lines.slice(start,start+10).join('\n').slice(0,1200);return {...n,start_line:start+1,end_line:start+1+text.split('\n').length-1,excerpt:text};}),no_answer_generated:true,content_egress:false};
  throw new Error('This route is not part of the offline preview');
}
'''


def main():
    output=ROOT/'docs/previews';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        home=Path(temp)/'demo';keys=init_demo(home);store=KnowledgeStore(home/'desk.sqlite')
        supervisor=KnowledgeSupervisor(store,keys['owner'],keys['source'],home/'project',vault=home/'vault');supervisor.cycle()
        desk=store.desk_state(keys['reader']);desk['supervisor']=supervisor.view(desk['scope']);desk['role']='reader'
        knowledge=store.knowledge(keys['reader']);notes={n['id']:store.knowledge_note(keys['reader'],n['id']) for n in knowledge['nodes']}
        data={'desk':desk,'knowledge':knowledge,'notes':notes}
    html=(ROOT/'web/index.html').read_text();app=(ROOT/'web/app.js').read_text();extra=(ROOT/'web/knowledge.js').read_text()
    start=app.index('async function api(');end=app.index('function errorText(',start);app=app[:start]+MOCK+app[end:]
    app=app.replace('Connected to local desk','Offline preview · sample data')
    app=app.replace("$('role-name').textContent=pretty(s.role)+' · synthetic';","$('role-name').textContent='READ-ONLY PREVIEW';")
    app=app.replace("$('pause').disabled=s.role!=='owner'", "$('pause').disabled=s.role!=='owner'")
    css='\n'.join((ROOT/'web'/name).read_text() for name in ('app.css','knowledge.css'))
    for tag in ('  <link rel="stylesheet" href="/assets/app.css">','  <script src="/assets/app.js" defer></script>','  <link rel="stylesheet" href="/assets/knowledge.css">','  <script src="/assets/knowledge.js" defer></script>'):
        html=html.replace(tag,'')
    html=html.replace('</head>','<style>'+css+'\n#switch{display:none}</style></head>')
    html=html.replace('SAMPLE DATA','OFFLINE PREVIEW').replace('ALFRED / DESK 0.4','ALFRED / DESK 0.4 / OFFLINE PREVIEW')
    html=html.replace('RULE-BASED BRIEFING · LOCAL DRAFTS ONLY · NOT A LIVE AI ASSISTANT','READ-ONLY FRONTEND PREVIEW · FICTIONAL NOTES · NO NETWORK OR LIVE AI')
    safe=json.dumps(data,ensure_ascii=True).replace('<','\\u003c')
    html=html.replace('</body>','<script>const PREVIEW='+safe+';</script><script>'+app.replace('</script','<\\/script')+'</script><script>'+extra.replace('</script','<\\/script')+'</script></body>')
    target=output/'ALFRED-Desk-v04.html';raw=html.encode();target.write_bytes(raw)
    packed=base64.b64encode(lzma.compress(raw,preset=9)).decode()
    (output/'ALFRED-Desk-v04.html.xz.b64').write_text('\n'.join(textwrap.wrap(packed,128))+'\n')
    (output/'manifest.json').write_text(json.dumps({'file':target.name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'mode':'read-only fictional offline transport','live_ai':False,'contains_tokens':False},indent=2)+'\n')
    print('Built actual frontend offline preview:',len(raw),'bytes; fictional notes only, no credentials.')


if __name__=='__main__':main()
