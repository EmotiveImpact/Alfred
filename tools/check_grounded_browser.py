"""Real-browser acceptance of source-first questions. Fictional notes only."""
from pathlib import Path
import base64
import json
import os
import sys
import tempfile
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore,KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evidence/grounded-v05';OUT.mkdir(parents=True,exist_ok=True)
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
                record('real local session sign-in')
                page.locator('[data-view=ask]').click();expect(page.locator('#ask-question')).to_be_visible()
                record('new question view is part of the existing Desk')
                expect(page.locator('#ask-mode option[value=local_model]')).to_be_disabled()
                record('unconfigured model cannot be selected')
                page.screenshot(path=str(OUT/'ALFRED-ask-empty.png'),full_page=True)
                page.locator('#ask-question').fill('Opening treatment');page.locator('#ask-submit').click()
                expect(page.locator('.ask-source-card').first).to_be_visible(timeout=15000)
                record('question retrieves real indexed note excerpts',0<page.locator('.ask-source-card').count()<=5)
                expect(page.locator('#ask-status')).to_contain_text('not an AI-generated answer')
                record('source mode does not impersonate a live model')
                record('hashes and source line ranges are displayed','SHA-256' in page.locator('#ask-results').inner_text() and 'lines' in page.locator('#ask-results').inner_text())
                record('no generated claims in source mode',page.locator('.ask-claim').count()==0)
                page.screenshot(path=str(OUT/'ALFRED-ask-desktop.png'),full_page=True)
                page.locator('.ask-source-card .text-button').first.click();expect(page.locator('#detail')).to_be_visible();expect(page.locator('.knowledge-source')).to_be_visible()
                record('citation opens actual numbered source snapshot')
                page.screenshot(path=str(OUT/'ALFRED-ask-source.png'),full_page=True);page.keyboard.press('Escape')
                with page.expect_download() as download_info:page.locator('#ask-export').click()
                download=download_info.value;file=OUT/'ALFRED-example-evidence.md';download.save_as(str(file))
                content=file.read_text();record('Markdown export has source hashes and no claimed action','SHA-256' in content and 'not a verified answer' in content)
                page.locator('#ask-question').fill('nonexistentuniqueknowledgesource');page.locator('#ask-submit').click();expect(page.locator('#ask-status')).to_contain_text('No supporting notes')
                record('missing evidence does not produce invented answer',page.locator('.ask-source-card').count()==0)
                page.get_by_role('button',name='ALFRED permissions',exact=True).click();expect(page.locator('.ask-source-card').first).to_be_visible(timeout=15000)
                record('example question traverses the same live retrieval endpoint')
                # Author a new fixture on disk, then allow the real supervisor to ingest it.
                target=home/'vault/notes/QuestionFixture.md';target.write_text('# QuestionFixture\nSpecialmarker: the fixture says green.\n<img src=x onerror="window.questionAttack=true">\n')
                page.wait_for_timeout(350);page.locator('#ask-question').fill('Specialmarker');page.locator('#ask-submit').click();expect(page.locator('.ask-source-card')).to_have_count(1,timeout=15000)
                record('new real Markdown file becomes queryable')
                record('source markup never becomes executable HTML',page.locator('.ask-source-card img').count()==0 and page.evaluate('window.questionAttack') is None)
                target.write_text('# QuestionFixture\nSpecialmarker: the fixture now says blue.\n')
                expect(page.locator('#ask-status')).to_contain_text('source changed',timeout=15000)
                record('source change invalidates and clears prior excerpts',page.locator('.ask-source-card').count()==0)
                page.locator('#ask-submit').click();expect(page.locator('.ask-excerpt')).to_contain_text('blue',timeout=15000)
                record('rerunning uses the new indexed revision')
                target.unlink();expect(page.locator('#ask-status')).to_contain_text('source changed',timeout=15000)
                record('deleted source removes previously shown material')
                page.get_by_role('button',name='Opening treatment',exact=True).click();expect(page.locator('.ask-source-card').first).to_be_visible(timeout=15000)
                page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'ALFRED-ask-mobile.png'),full_page=True)
                record('mobile has no document-wide horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                record('no bearer exposed in page text',keys['owner'] not in page.locator('body').inner_text())
                record('no browser local storage',page.evaluate('localStorage.length')==0)
                page.set_viewport_size({'width':1480,'height':1080});page.locator('[data-view=knowledge]').click();expect(page.locator('.knowledge-node')).to_have_count(20,timeout=15000)
                record('existing knowledge graph remains accessible')
                page.get_by_role('button',name='Open note ALFRED',exact=True).click();page.screenshot(path=str(OUT/'ALFRED-knowledge-desktop.png'),full_page=True)
                page.locator('[data-view=overview]').click();page.screenshot(path=str(OUT/'ALFRED-overview.png'),full_page=True)
                record('existing briefing remains accessible')
                page.locator('[data-view=ask]').click();page.get_by_role('button',name='Opening treatment',exact=True).click();expect(page.locator('.ask-source-card').first).to_be_visible(timeout=15000)
                store.revoke('demo-owner');expect(page.locator('#sign-in')).to_be_visible(timeout=15000)
                record('revocation clears question view and sources',page.locator('.ask-source-card').count()==0)
                record('no uncaught browser errors',not errors)
                version=browser.version;browser.close()
        finally:
            supervisor.stop();server.shutdown();server.server_close();thread.join(timeout=3)
    report={'count':len(checks),'checks':checks,'errors':errors,'browser':version,'transport':'real loopback HTTP','database':'real SQLite','notes':'fictional Markdown','model_inference_tested':False}
    (OUT/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n')
    # Small exact screenshot companions enable transfer without a binary connector.
    from PIL import Image
    for name in ('ALFRED-ask-desktop','ALFRED-knowledge-desktop','ALFRED-overview'):
        image=Image.open(OUT/(name+'.png'));image.thumbnail((1000,1400))
        target=OUT/(name+'.webp');image.save(target,format='WEBP',quality=65)
        (OUT/(name+'.webp.b64')).write_text(base64.b64encode(target.read_bytes()).decode()+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
