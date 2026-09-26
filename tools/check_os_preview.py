"""Verify the fictional standalone shell separately from real-backend acceptance."""
from pathlib import Path
import json,os
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evidence/personal-os-v06';OUT.mkdir(parents=True,exist_ok=True)

def main():
    checks=[];errors=[];network=[]
    def check(name,condition=True):
        if not condition:raise AssertionError(name)
        checks.append(name)
    with sync_playwright() as p:
        kwargs={'headless':True}
        if os.environ.get('CHROMIUM_PATH'):kwargs['executable_path']=os.environ['CHROMIUM_PATH']
        b=p.chromium.launch(**kwargs);page=b.new_page(viewport={'width':1512,'height':982})
        page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:network.append(r.url) if r.url.startswith(('http:','https:')) else None)
        preview=ROOT/'docs/previews/personal-os-v06/ALFRED-OS-v06.html'
        # set_content mode allows layout verification where managed browsers disallow
        # localhost/file navigation. It does not test the HTTP server or its policies.
        if os.environ.get('ALFRED_PREVIEW_SET_CONTENT'):page.set_content(preview.read_text())
        else:page.goto(preview.as_uri())
        expect(page.locator('.presence')).to_be_visible();expect(page.locator('#presence-memory-count')).to_contain_text('20 notes');check('actual frontend opens without credentials');check('preview explicitly labelled','OFFLINE PREVIEW' in page.locator('body').inner_text())
        page.screenshot(path=str(OUT/'ALFRED-OS-Preview.png'),full_page=True)
        page.locator('#launcher-open').click();page.fill('#command-query','Memory');page.keyboard.press('Enter');expect(page.locator('.knowledge-node')).to_have_count(20);check('command palette navigates');check('graph target hitboxes remain transparent',page.locator('.knowledge-node rect').first.evaluate("e=>getComputedStyle(e).fill==='rgba(0, 0, 0, 0)'"))
        page.locator('.os-dock [data-view=presence]').click();page.locator('#focus-toggle').click();check('focus is a real presentation state',page.locator('body').get_attribute('class')=='os-focus');page.locator('#focus-toggle').click()
        page.locator('.os-dock [data-view=ask]').click()
        for q in ('Opening treatment','ALFRED permissions','Production decisions'):
            page.get_by_role('button',name=q,exact=True).click();expect(page.locator('.ask-source-card').first).to_be_visible();check('real retrieval example: '+q)
        page.fill('#ask-question','Unsupported question');page.locator('#ask-submit').click();expect(page.locator('#ask-status')).to_contain_text('Preview:');check('unsupported preview question is not invented')
        page.locator('.os-dock [data-view=pulse]').click();expect(page.locator('.routine-row')).to_have_count(2);expect(page.get_by_role('button',name='Run now').first).to_be_disabled();expect(page.get_by_role('button',name='Enable schedule').first).to_be_disabled();check('preview never enables execution or schedules');check('no invented routine history',page.locator('.routine-run').count()==0)
        page.locator('.os-dock [data-view=presence]').click();page.set_viewport_size({'width':390,'height':844});check('mobile has no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        page.set_viewport_size({'width':1280,'height':720});check('short desktop dock remains visible',page.locator('.os-dock').is_visible());check('no HTTP requests',not network);check('no browser errors',not errors);b.close()
    report={'count':len(checks),'checks':checks,'errors':errors,'network':network,'transport':'fictional in-file preview','real_backend':False,'model_inference':False}
    (OUT/'preview-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
