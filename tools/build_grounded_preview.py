"""Actual frontend packaged with fictional read-only in-file transport.

The three question examples are computed by ALFRED's actual source retrieval code.
Other questions report the preview limitation, not a fabricated answer. No credentials.
"""
from pathlib import Path
import base64,hashlib,json,lzma,tempfile,textwrap,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore,KnowledgeSupervisor
from alfred.grounded import ask
from build_knowledge_preview import MOCK
ROOT=Path(__file__).resolve().parents[1]
EXAMPLES=('Opening treatment','ALFRED permissions','Production decisions')


def main():
    output=ROOT/'docs/previews/grounded-v05';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        home=Path(temp)/'demo';keys=init_demo(home);store=KnowledgeStore(home/'desk.sqlite')
        supervisor=KnowledgeSupervisor(store,keys['owner'],keys['source'],home/'project',vault=home/'vault');supervisor.cycle()
        desk=store.desk_state(keys['reader']);desk['supervisor']=supervisor.view(desk['scope']);desk['role']='reader'
        knowledge=store.knowledge(keys['reader']);notes={n['id']:store.knowledge_note(keys['reader'],n['id']) for n in knowledge['nodes']}
        questions={q.casefold():ask(store,keys['reader'],{'question':q,'mode':'sources'}) for q in EXAMPLES}
        data={'desk':desk,'knowledge':knowledge,'notes':notes,'questions':questions}
    extra=r'''
  if(path==='/desk/ask/status')return {local_model_configured:false,model:null,model_allowed:false,preview:true};
  if(path==='/desk/ask/check')return {current_index_match:true,problems:[],indexed_snapshot_only:true,preview:true};
  if(path==='/desk/ask'){
    const found=PREVIEW.questions[String(data.question||'').trim().toLowerCase()];
    if(data.mode!=='sources'||!found)throw new Error('This read-only preview supports the three example questions. Run the local app for arbitrary questions.');
    return JSON.parse(JSON.stringify(found));
  }
'''
    mock=MOCK.replace("async function api(path,data) {","async function api(path,data) {"+extra)
    html=(ROOT/'web/index.html').read_text();app=(ROOT/'web/app.js').read_text()
    start=app.index('async function api(');end=app.index('function errorText(',start);app=app[:start]+mock+app[end:]
    app=app.replace('Connected to local desk','Offline preview · sample data')
    app=app.replace("$('role-name').textContent=pretty(s.role)+' · synthetic';","$('role-name').textContent='READ-ONLY PREVIEW';")
    css='\n'.join((ROOT/'web'/n).read_text() for n in ('app.css','knowledge.css','ask.css'))
    scripts=[app,(ROOT/'web/knowledge.js').read_text(),(ROOT/'web/ask.js').read_text()]
    for name in ('app','knowledge','ask'):
        html=html.replace('  <link rel="stylesheet" href="/assets/'+name+'.css">','').replace('  <script src="/assets/'+name+'.js" defer></script>','')
    html=html.replace('</head>','<style>'+css+'\n#switch{display:none}.preview-notice{padding:12px 22px;background:#243029;color:#d8ebdf;font:12px/1.6 sans-serif;text-align:center}</style></head>')
    html=html.replace('<body>','<body><div class="preview-notice">READ-ONLY OFFLINE PREVIEW · FICTIONAL DATA · TRY THE THREE ASK ALFRED EXAMPLES · NO LIVE MODEL OR ACCOUNT CONNECTIONS</div>')
    html=html.replace('SAMPLE DATA','OFFLINE PREVIEW')
    safe=json.dumps(data,ensure_ascii=True).replace('<','\\u003c')
    html=html.replace('</body>','<script>const PREVIEW='+safe+';</script>'+''.join('<script>'+s.replace('</script','<\\/script')+'</script>' for s in scripts)+'</body>')
    raw=html.encode();target=output/'ALFRED-Desk-v05.html';target.write_bytes(raw)
    packed=base64.b64encode(lzma.compress(raw,preset=9)).decode()
    (output/(target.name+'.xz.b64')).write_text('\n'.join(textwrap.wrap(packed,128))+'\n')
    (output/'manifest.json').write_text(json.dumps({'file':target.name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'mode':'read-only fictional preview','questions':list(EXAMPLES),'live_model':False,'credentials_included':False},indent=2)+'\n')
    print('Created fictional read-only v0.5 preview:',len(raw),'bytes')


if __name__=='__main__':main()
