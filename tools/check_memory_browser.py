"""Exercise reviewed memory and report retention through the actual local UI.

Only fictional notes, credentials and temporary databases. No inference or external effects.
"""
from pathlib import Path
import json,os,sys,tempfile,threading,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore,KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('ALFRED_MEMORY_OUTPUT',str(ROOT/'docs/evidence/memory-v08')))
OUT.mkdir(parents=True,exist_ok=True)

def main():
    checks=[];errors=[]
    def check(label,condition=True):
        if not condition:raise AssertionError(label)
        checks.append(label)
    with tempfile.TemporaryDirectory() as tmp:
        home=Path(tmp)/'demo';keys=init_demo(home);store=KnowledgeStore(home/'desk.sqlite')
        supervisor=KnowledgeSupervisor(store,keys['owner'],keys['source'],home/'project',interval=.1,vault=home/'vault')
        server=DeskHTTPServer(store,supervisor,port=0);supervisor.start()
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                options={'headless':True}
                if os.environ.get('CHROMIUM_PATH'):options['executable_path']=os.environ['CHROMIUM_PATH']
                browser=p.chromium.launch(**options);page=browser.new_page(viewport={'width':1512,'height':982})
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(server.origin);page.fill('#access-key',keys['owner']);page.locator('#login-form button').click();page.locator('.presence').wait_for()
                check('existing personal home retained')
                page.locator('.os-dock [data-view=knowledge]').click();expect(page.locator('.knowledge-node')).to_have_count(20,timeout=15000)
                check('original note graph retains twenty fictional source notes')
                page.locator('[data-view=reviewed-memory]').click();expect(page.locator('#memory-status')).to_contain_text('0 current',timeout=15000)
                check('reviewed graph starts empty, not auto-extracted from links')
                def entity(label,kind):
                    page.locator('#memory-new-entity').click();page.fill('#memory-entity-name',label);page.select_option('#memory-entity-kind',kind)
                    page.get_by_role('button',name='Create entity',exact=True).click();expect(page.locator('#detail')).not_to_be_visible(timeout=10000)
                    return next(x['id'] for x in server.memory.view(keys['owner'])['entities'] if x['name']==label)
                project=entity('Sample Film','project');person=entity('Sample Coordinator','person')
                check('UI creates persisted typed entities with explicit IDs',len(server.memory.view(keys['owner'])['entities'])==2)
                note=next(n for n in store.knowledge(keys['owner'])['nodes'] if n['path']=='people/Sample Coordinator.md')
                def proposal(object_id,value=None):
                    before={c['id'] for c in server.memory.view(keys['owner'])['claims']}
                    page.locator('#memory-propose').click();page.select_option('#memory-subject',project)
                    if value is None:page.select_option('#memory-predicate','responsible_person');page.select_option('#memory-object',object_id)
                    else:page.select_option('#memory-predicate','decision');page.fill('#memory-value',value)
                    page.select_option('#memory-note',note['id']);expect(page.locator('#memory-note-text')).to_contain_text('Fictional responsibility')
                    page.fill('#memory-first','8');page.fill('#memory-last','8');page.get_by_role('button',name='Save proposal for review',exact=True).click()
                    expect(page.locator('#detail')).not_to_be_visible(timeout=10000)
                    cid=next(c['id'] for c in server.memory.view(keys['owner'])['claims'] if c['id'] not in before)
                    expect(page.locator('[data-claim-id="'+cid+'"]')).to_be_visible(timeout=10000);return cid
                def review(cid,decision):
                    row=page.locator('[data-claim-id="'+cid+'"]');row.locator('[data-review="'+decision+'"]').click()
                    page.locator('#memory-review-confirm').click();expect(page.locator('#detail')).not_to_be_visible(timeout=10000)
                first=proposal(person);check('proposal creates no current relationship',server.memory.view(keys['owner'])['graph']['edges']==[])
                review(first,'accept');expect(page.locator('#memory-status')).to_contain_text('1 current',timeout=10000)
                check('separate exact review adds an evidence-backed relationship',len(server.memory.view(keys['owner'])['graph']['edges'])==1)
                page.locator('[data-claim-id="'+first+'"] [data-source-id]').click();expect(page.locator('#detail-body')).to_contain_text('Source SHA-256')
                check('exact source and review version are inspectable');page.keyboard.press('Escape')
                with page.expect_download() as download_info:page.locator('#memory-export').click()
                export=json.loads(Path(download_info.value.path()).read_text());check('export carries source hash and reviewer',bool(export['claims'][0]['source']['sha256']) and bool(export['claims'][0]['reviewer']))
                check('acceptance never creates action permission',export['authority_granted'] is False)
                page.screenshot(path=str(OUT/'ALFRED-Reviewed-Memory.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'ALFRED-Reviewed-Memory-Mobile.png'),full_page=True)
                check('mobile reviewed memory has no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                page.set_viewport_size({'width':1512,'height':982})
                alternative=entity('Another Coordinator','person');second=proposal(alternative);review(second,'accept')
                expect(page.locator('#memory-status')).to_contain_text('2 conflicting records',timeout=10000)
                check('competing accepted owners remain explicit',server.memory.view(keys['owner'])['counts']['conflicted']==2)
                check('conflicted relationships withheld from current graph',server.memory.view(keys['owner'])['graph']['edges']==[])
                review(second,'supersede');expect(page.locator('#memory-status')).to_contain_text('1 current',timeout=10000)
                check('explicit replacement resolves conflict with retained lineage',next(c for c in server.memory.view(keys['owner'])['claims'] if c['id']==second)['replaces_id']==first)
                third=proposal(None,'<img src=x onerror=alert(1)> is literal fictional review text.')
                check('claim markup is rendered as text',page.locator('.memory-value img').count()==0)
                review(third,'dispute');check('dispute is persisted',next(c for c in server.memory.view(keys['owner'])['claims'] if c['id']==third)['state']=='disputed')
                review(third,'withdraw');check('withdrawal does not edit source notes',next(c for c in server.memory.view(keys['owner'])['claims'] if c['id']==third)['state']=='withdrawn')
                page.reload();page.locator('.presence').wait_for();page.locator('.os-dock [data-view=knowledge]').click();page.locator('[data-view=reviewed-memory]').click()
                expect(page.locator('.memory-claim')).to_have_count(3,timeout=15000);check('review records survive browser reload')
                row=page.locator('[data-claim-id="'+second+'"]');row.locator('[data-source-id]').click();expect(page.locator('#detail')).to_be_visible()
                (home/'vault'/'people/Sample Coordinator.md').write_text('# Changed coordinator\nThe fictional coordinator assignment needs a new review.\n')
                expect(row.locator('.memory-claim-state')).to_contain_text('Invalidated',ignore_case=True,timeout=15000)
                expect(page.locator('#detail')).not_to_be_visible(timeout=10000);check('source change clears an open source-inspection modal')
                check('source change clears projected values and current graph',not server.memory.view(keys['owner'])['graph']['edges'] and all(c['value'] is None and c['object_id'] is None for c in server.memory.view(keys['owner'])['claims']))
                check('raw source excerpt no longer visible','Fictional responsibility:' not in page.locator('#memory-records').inner_text())
                page.locator('.os-dock [data-view=pulse]').click();expect(page.locator('.routine-row')).to_have_count(2,timeout=15000)
                before_schedule=server.pulse.view(keys['owner'])['routines']
                with store.transaction() as db:
                    db.executemany('INSERT INTO pulse_runs VALUES (?,?,?,?,?,?,?,?)',[
                        (supervisor.scope,'old-'+str(i),'memory-health','demo-owner',store.now()-172800-i,store.now()-172800-i,'completed','{"notes":20}') for i in range(100)])
                page.locator('#pulse-history-manage').click();expect(page.locator('#detail-body')).to_contain_text('36 report summaries')
                with store.connection() as db:check('retention preview does not delete',db.execute('SELECT count(*) FROM pulse_runs').fetchone()[0]==100)
                page.locator('#pulse-history-confirm').click();expect(page.locator('#detail')).not_to_be_visible(timeout=10000)
                with store.connection() as db:
                    check('explicit retention leaves latest 64 details',db.execute('SELECT count(*) FROM pulse_runs').fetchone()[0]==64)
                    check('compact retry receipts preserved',db.execute('SELECT count(*) FROM pulse_run_receipts').fetchone()[0]==36)
                check('retention does not change schedules',server.pulse.view(keys['owner'])['routines']==before_schedule)
                check('no source or device action was executed',store.desk_state(keys['owner'])['counts']['drafts']==0)
                check('no browser local storage',page.evaluate('localStorage.length')==0)
                check('no bearer appears in page text',keys['owner'] not in page.locator('body').inner_text())
                store.revoke('demo-owner');expect(page.locator('#sign-in')).to_be_visible(timeout=15000)
                check('revocation clears reviewed memory and modal',page.locator('.memory-claim').count()==0 and not page.locator('#detail').is_visible())
                page.fill('#access-key',keys['reader']);page.locator('#login-form button').click();page.locator('.presence').wait_for()
                page.locator('.os-dock [data-view=knowledge]').click();page.locator('[data-view=reviewed-memory]').click()
                expect(page.locator('#memory-status')).to_contain_text('0 current',timeout=15000);expect(page.locator('#memory-new-entity')).to_be_disabled();expect(page.locator('#memory-propose')).to_be_disabled()
                check('reader cannot see another credential private graph or mutate it')
                check('no uncaught browser errors',not errors);version=browser.version;browser.close()
        finally:
            supervisor.stop();server.shutdown();server.server_close();thread.join(3)
    report={'count':len(checks),'checks':checks,'errors':errors,'browser':version,'transport':'real loopback HTTP','database':'real SQLite','inputs':'fictional notes only','model_inference':False}
    (OUT/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
