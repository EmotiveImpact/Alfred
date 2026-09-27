"""Actual model + local HTTP + queued conversation experiment on fictional notes.

This is a two-turn development check, not a general reasoning benchmark. Requires
an already running, verified local Ollama as used in model-evaluation-v07.yml.
"""
from pathlib import Path
from http.client import HTTPConnection
import json,os,platform,subprocess,sys,tempfile,threading,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from alfred.knowledge import KnowledgeStore,MarkdownVault
from alfred.local_model import LocalOllama
from alfred.desk_http import DeskHTTPServer
OUT=Path('docs/evidence/conversation-v07/model');OUT.mkdir(parents=True,exist_ok=True)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);vault=root/'vault';vault.mkdir()
        (vault/'Equipment.md').write_text('# Equipment collection\nCollection is booked for 10:00.\nMorgan owns equipment collection.\n')
        store=KnowledgeStore(root/'db');owner=store.provision('experiment','owner','owner');source=store.provision('experiment','source','source');MarkdownVault(store,source,vault).scan()
        class Supervisor:
            scope='experiment'
            def view(self,scope):return {'configured':False}
        model=LocalOllama('alfred-eval:latest',11434,timeout=60)
        server=DeskHTTPServer(store,Supervisor(),port=0,local_model=model);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();cookie=csrf=''
        def request(method,path,body=None):
            connection=HTTPConnection('127.0.0.1',server.server_port,timeout=4)
            headers={'Cookie':cookie,'X-CSRF-Token':csrf}
            if body is not None:headers.update({'Content-Type':'application/json','Origin':server.origin})
            connection.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers)
            response=connection.getresponse();value=json.loads(response.read());status=response.status;headers=dict(response.getheaders());connection.close()
            if status!=200:raise ValueError('HTTP request failed: '+str(status))
            return value,headers
        try:
            login,headers=request('POST','/desk/login',{'key':owner});cookie=headers['Set-Cookie'].split(';')[0];csrf=login['csrf']
            session,_=request('POST','/desk/conversations',{'title':'Fictional equipment discussion'});sid=session['id'];results=[]
            for i,question in enumerate(('What time is equipment collection?','Who owns that?')):
                started=time.monotonic();turn,_=request('POST','/desk/conversations/'+sid+'/turns',{'question':question,'mode':'local_model','follow_up':bool(i),'request_id':'actual-'+str(i),'after':i})
                submission_ms=round((time.monotonic()-started)*1000,2)
                for _ in range(320):
                    session,_=request('GET','/desk/conversations/'+sid)
                    if session['turns'][-1]['state'] not in {'queued','running'}:break
                    time.sleep(.2)
                row=session['turns'][-1];results.append({'question':question,'submission_ms':submission_ms,'wall_seconds':round(time.monotonic()-started,3),'turn':row})
                print('actual conversation turn',i+1,row['state'],row['result']['status'] if row['result'] else 'no result',flush=True)
                (OUT/'session-results.json').write_text(json.dumps(results,indent=2)+'\n')
            report={'input_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'workflow_run':os.environ.get('GITHUB_RUN_ID'),
                    'python':platform.python_version(),'transport':'real same-origin local HTTP requests and queued worker','database':'real SQLite','model_inference':True,
                    'model':'Qwen2.5-1.5B-Instruct Q4_K_M','runtime':'Ollama 0.34.4','turn_count':2,'expected':['10:00 with source','Morgan with source'],
                    'review':'Inspect actual results. No automated semantic pass rate. Synthetic follow-up only, no external actions.'}
            (OUT/'session-receipt.json').write_text(json.dumps(report,indent=2)+'\n')
            if not all(r['turn']['state']=='completed' and r['turn']['result']['model_used'] for r in results):raise SystemExit('Actual conversation inference was incomplete')
        finally:server.shutdown();server.server_close();thread.join(3)
if __name__=='__main__':main()
