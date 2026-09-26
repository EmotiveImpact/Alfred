"""The actual frontend with labelled fictional in-file transport, not the backend."""
from pathlib import Path
import json,os
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evidence/memory-v08';OUT.mkdir(parents=True,exist_ok=True)

def main():
    checks=[];errors=[];network=[]
    def check(label,condition=True):
        if not condition:raise AssertionError(label)
        checks.append(label)
    with sync_playwright() as p:
        options={'headless':True}
        if os.environ.get('CHROMIUM_PATH'):options['executable_path']=os.environ['CHROMIUM_PATH']
        browser=p.chromium.launch(**options);page=browser.new_page(viewport={'width':1512,'height':982})
        page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:network.append(r.url) if r.url.startswith(('http:','https:')) else None)
        preview=ROOT/'docs/previews/memory-v08/ALFRED-OS-v08.html'
        if os.environ.get('ALFRED_PREVIEW_SET_CONTENT'):page.set_content(preview.read_text())
        else:page.goto(preview.as_uri())
        expect(page.locator('.presence')).to_be_visible();check('existing personal OS home opens without credentials');check('preview explicitly labelled','OFFLINE PREVIEW' in page.locator('body').inner_text())
        page.locator('.os-dock [data-view=knowledge]').click();expect(page.locator('.knowledge-node')).to_have_count(20);check('existing note graph is retained')
        page.locator('[data-view=reviewed-memory]').click();expect(page.locator('.memory-claim')).to_have_count(2);expect(page.locator('#memory-status')).to_contain_text('1 current')
        check('reviewed statements are separate from source-note graph');expect(page.locator('#memory-new-entity')).to_be_disabled();expect(page.locator('#memory-propose')).to_be_disabled();check('offline preview cannot mutate memory')
        check('fictional accepted and pending states distinguished','proposed' in page.locator('#memory-records').inner_text().casefold() and 'accepted' in page.locator('#memory-records').inner_text().casefold())
        page.locator('.memory-graph summary').click();expect(page.locator('.memory-graph')).to_contain_text('Sample Coordinator');check('actual reviewed projection is inspectable')
        page.locator('[data-source-id]').first.click();expect(page.locator('#detail-body')).to_contain_text('Source SHA-256');check('source inspection includes exact hash');page.keyboard.press('Escape')
        page.locator('#view-content').evaluate('e=>{let p=e;while(p){p.scrollTop=0;p=p.parentElement;}}')
        page.screenshot(path=str(OUT/'ALFRED-Memory-Preview.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844});check('mobile reviewed memory has no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
        page.screenshot(path=str(OUT/'ALFRED-Memory-Preview-Mobile.png'),full_page=True)
        page.set_viewport_size({'width':1512,'height':982});page.locator('.os-dock [data-view=ask]').click();page.get_by_role('button',name='Opening treatment',exact=True).click();expect(page.locator('.ask-source-card').first).to_be_visible();check('existing source lookup remains usable')
        page.locator('[data-view=conversation]').click();expect(page.locator('.conversation-turn')).to_have_count(2);expect(page.locator('#conversation-send')).to_be_disabled();check('example conversation retained without fake live replies')
        page.locator('.os-dock [data-view=pulse]').click();expect(page.locator('.routine-row')).to_have_count(2);expect(page.locator('#pulse-history-manage')).to_be_disabled();check('preview cannot prune or schedule routines')
        check('no HTTP requests',not network);check('no uncaught browser errors',not errors);browser.close()
    report={'count':len(checks),'checks':checks,'errors':errors,'network':network,'transport':'fictional in-file preview','real_backend':False,'model_inference':False}
    (OUT/'preview-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
