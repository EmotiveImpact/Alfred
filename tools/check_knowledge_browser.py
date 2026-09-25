"""Real browser -> real local HTTP -> real SQLite -> fictional Markdown files."""
from pathlib import Path
import json
import os
import sys
import tempfile
import threading
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore,KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evidence/knowledge-v04';OUT.mkdir(parents=True,exist_ok=True)
checks=[]

def record(name,condition=True):
    if not condition:raise AssertionError(name)
    checks.append(name)


def main():
    errors=[]
    with tempfile.TemporaryDirectory() as tmp:
        home=Path(tmp)/'desk';keys=init_demo(home);store=KnowledgeStore(home/'desk.sqlite')
        supervisor=KnowledgeSupervisor(store,keys['owner'],keys['source'],home/'project',interval=.1,vault=home/'vault')
        server=DeskHTTPServer(store,supervisor,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True)
        supervisor.start();thread.start()
        try:
            with sync_playwright() as p:
                kwargs={'headless':True}
                if os.environ.get('CHROMIUM_PATH'):kwargs['executable_path']=os.environ['CHROMIUM_PATH']
                browser=p.chromium.launch(**kwargs);page=browser.new_page(viewport={'width':1480,'height':1080},device_scale_factor=1)
                page.on('pageerror',lambda err:errors.append(str(err)))
                page.goto(server.origin);page.fill('#access-key',keys['owner']);page.locator('#login-form button').click();page.locator('#workspace').wait_for(state='visible')
                record('sign in to the actual local service')
                page.screenshot(path=str(OUT/'ALFRED-overview.png'),full_page=True)
                page.locator('[data-view=knowledge]').click();expect(page.locator('.knowledge-metric strong').nth(0)).to_have_text('20',timeout=15000)
                record('twenty actual fictional Markdown files are indexed and rendered')
                record('graph has one selectable node per indexed note',page.locator('.knowledge-node').count()==20)
                record('links render from the backend index',page.locator('.knowledge-edge').count()>20)
                page.get_by_role('button',name='Open note ALFRED',exact=True).click();expect(page.locator('.knowledge-inspector h3')).to_have_text('ALFRED')
                record('selecting a graph node loads its real indexed note')
                page.screenshot(path=str(OUT/'ALFRED-knowledge.png'),full_page=True)
                page.get_by_role('button',name='Read source text',exact=True).click();expect(page.locator('#detail')).to_be_visible();expect(page.locator('.knowledge-source')).to_contain_text('No live model')
                record('source text and file hash are inspectable')
                page.screenshot(path=str(OUT/'ALFRED-note.png'),full_page=True);page.keyboard.press('Escape')
                page.get_by_label('Search notes').fill('monochrome');expect(page.locator('#knowledge-status')).to_contain_text('matching notes',timeout=10000)
                page.wait_for_timeout(800)
                record('keyword search filters the map',0<page.locator('.knowledge-node').count()<20)
                page.get_by_role('button',name='Source packet',exact=True).click();expect(page.locator('#detail-title')).to_have_text('Your source packet');expect(page.locator('#detail-body')).to_contain_text('Nothing was sent to a model')
                record('source packet shows excerpts rather than a generated answer')
                page.screenshot(path=str(OUT/'ALFRED-source-packet.png'),full_page=True);page.keyboard.press('Escape')
                page.get_by_role('button',name='Notes',exact=True).click();record('list view renders filtered notes',page.locator('.knowledge-note-row').count()>0)
                page.get_by_label('Search notes').fill('notfoundunique');expect(page.locator('#knowledge-canvas')).to_contain_text('No matching notes',timeout=10000);record('empty search does not fabricate an answer')
                page.get_by_label('Search notes').fill('');page.get_by_label('Filter note kind').select_option('project');page.wait_for_timeout(800);record('type filter matches the three project notes',page.locator('.knowledge-note-row').count()==3)
                page.get_by_label('Filter note kind').select_option('');page.get_by_role('button',name='Map',exact=True).click();expect(page.locator('.knowledge-node')).to_have_count(20,timeout=10000)
                record('missing link is visible',page.locator('#knowledge-health').inner_text().find('Unreviewed idea')>=0)
                bad=page.request.get(server.origin+'/desk/knowledge?scope=other');record('scope injection rejected at real HTTP boundary',bad.status==400)
                post=page.request.post(server.origin+'/desk/knowledge/delete',data={});record('no unauthenticated mutation route',post.status>=400)
                page.locator('#pause').click();expect(page.locator('#paused-banner')).to_be_visible();before=store.knowledge(keys['owner'])['counts']['notes'];(home/'vault/notes/New.md').write_text('# New note\n[[projects/Alfred]]')
                page.wait_for_timeout(400);record('pause prevents background Markdown ingestion',store.knowledge(keys['owner'])['counts']['notes']==before)
                page.locator('#pause').click();expect(page.locator('.knowledge-metric strong').nth(0)).to_have_text('21',timeout=15000);record('resume indexes a real new file automatically')
                data=store.knowledge(keys['owner']);identity=next(n['id'] for n in data['nodes'] if n['path']=='notes/New.md');(home/'vault/notes/New.md').unlink();expect(page.locator('.knowledge-metric strong').nth(0)).to_have_text('20',timeout=15000)
                record('deletion removes the note from current retrieval',page.request.get(server.origin+'/desk/knowledge/notes/'+identity).status==404)
                (home/'vault/notes/Markup.md').write_text('# Markup\n<img src=x onerror="window.badNote=true">');expect(page.locator('.knowledge-metric strong').nth(0)).to_have_text('21',timeout=15000)
                page.get_by_role('button',name='Open note Markup',exact=True).click();page.get_by_role('button',name='Read source text',exact=True).click();expect(page.locator('.knowledge-source')).to_contain_text('<img');record('raw note markup never becomes HTML',page.locator('#detail img').count()==0 and page.evaluate('window.badNote') is None);page.keyboard.press('Escape')
                page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'ALFRED-knowledge-mobile.png'),full_page=True)
                record('mobile has no document-wide horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                record('no raw bearer in page text',keys['owner'] not in page.locator('body').inner_text())
                record('no browser local-storage persistence',page.evaluate('localStorage.length')==0)
                page.set_viewport_size({'width':1480,'height':1080});page.reload();page.locator('#workspace').wait_for(state='visible');record('session survives browser reload')
                page.locator('[data-view=knowledge]').click();expect(page.locator('.knowledge-node')).to_have_count(21,timeout=10000)
                node=page.locator('.knowledge-node').first;node.focus();page.keyboard.press('Enter');expect(page.locator('.knowledge-inspector h3')).not_to_have_text('Not just stored. Understood in context.');record('graph nodes support keyboard selection')
                store.revoke('demo-owner');expect(page.locator('#sign-in')).to_be_visible(timeout=15000);record('revocation clears the knowledge workspace without restart')
                record('no uncaught JavaScript errors',not errors)
                version=browser.version;browser.close()
        finally:
            supervisor.stop();server.shutdown();server.server_close();thread.join(timeout=3)
    report={'checks':checks,'count':len(checks),'errors':errors,'browser':version,'transport':'real loopback HTTP','database':'real SQLite','notes':'fictional Markdown only','live_model':False}
    (OUT/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
