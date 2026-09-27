"""Package the actual OS frontend over fictional, read-only in-file data."""
from pathlib import Path
import hashlib,json,re,sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore,KnowledgeSupervisor
from alfred.grounded import ask
from alfred.pulse import Pulse
from build_knowledge_preview import MOCK
ROOT=Path(__file__).resolve().parents[1]
EXAMPLES=('Opening treatment','ALFRED permissions','Production decisions')


def main():
    out=ROOT/'docs/previews/personal-os-v06';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        h=Path(temp)/'demo';keys=init_demo(h);store=KnowledgeStore(h/'desk.sqlite');sup=KnowledgeSupervisor(store,keys['owner'],keys['source'],h/'project',vault=h/'vault');sup.cycle();pulse=Pulse(store,sup)
        desk=store.desk_state(keys['reader']);desk['supervisor']=sup.view(desk['scope']);desk['role']='reader'
        knowledge=store.knowledge(keys['reader']);notes={n['id']:store.knowledge_note(keys['reader'],n['id']) for n in knowledge['nodes']}
        questions={q.casefold():ask(store,keys['reader'],{'question':q,'mode':'sources'}) for q in EXAMPLES}
        data={'desk':desk,'knowledge':knowledge,'notes':notes,'questions':questions,'pulse':pulse.view(keys['reader'])}
    additions=r'''
  if(path==='/desk/pulse')return JSON.parse(JSON.stringify(PREVIEW.pulse));
  if(path==='/desk/ask/status')return {local_model_configured:false,model:null,model_allowed:false,preview:true};
  if(path==='/desk/ask/check')return {current_index_match:true,problems:[],indexed_snapshot_only:true,preview:true};
  if(path==='/desk/ask'){
    const found=PREVIEW.questions[String(data.question||'').trim().toLowerCase()];
    if(data.mode!=='sources'||!found)throw new Error('Preview: try Opening treatment, ALFRED permissions or Production decisions. The local app accepts other questions.');
    return JSON.parse(JSON.stringify(found));
  }
'''
    mock=MOCK.replace('async function api(path,data) {','async function api(path,data) {'+additions)
    app=(ROOT/'web/app.js').read_text();start=app.index('async function api(');end=app.index('function errorText(',start);app=app[:start]+mock+app[end:]
    app=app.replace('Connected to local desk','Offline preview · fictional context')
    names=('app','knowledge','ask','os');html=(ROOT/'web/index.html').read_text()
    for name in names:
        html=html.replace('  <link rel="stylesheet" href="/assets/'+name+'.css">','').replace('  <script src="/assets/'+name+'.js" defer></script>','')
    css='\n'.join((ROOT/'web'/f'{n}.css').read_text() for n in names)
    html=html.replace('</head>','<style>'+css+'\n#space-select{pointer-events:none}.sample-label{color:#b5a58a!important}</style></head>')
    html=html.replace('DEVELOPMENT / SAMPLE WORKSPACE','OFFLINE PREVIEW / FICTIONAL CONTEXT').replace('LOCAL DEVELOPMENT BUILD / 0.6','READ-ONLY PREVIEW / 0.6')
    scripts=[app]+[(ROOT/'web'/f'{n}.js').read_text() for n in names[1:]]
    data=json.dumps(data,ensure_ascii=True).replace('<','\\u003c')
    html=html.replace('</body>','<script>window.ALFRED_PREVIEW=true;const PREVIEW='+data+';</script>'+''.join('<script>'+s.replace('</script','<\\/script')+'</script>' for s in scripts)+'</body>')
    raw=html.encode();target=out/'ALFRED-OS-v06.html';target.write_bytes(raw)
    (out/'manifest.json').write_text(json.dumps({'file':target.name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'mode':'actual frontend / fictional read-only transport','example_questions':EXAMPLES,'model_inference':False,'credentials_included':False},indent=2)+'\n')
    print('Built',target.name,len(raw),'bytes')
if __name__=='__main__':main()
