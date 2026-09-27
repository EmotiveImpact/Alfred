"""Validate the delivered single-file preview, separately from the real backend."""
from pathlib import Path
import json,os
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evidence/grounded-v05'

def main():
    checks=[];errors=[];network=[]
    def record(name,valid=True):
        if not valid:raise AssertionError(name)
        checks.append(name)
    with sync_playwright() as p:
        options={'headless':True}
        if os.environ.get('CHROMIUM_PATH'):options['executable_path']=os.environ['CHROMIUM_PATH']
        browser=p.chromium.launch(**options);page=browser.new_page(viewport={'width':1480,'height':1080})
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:network.append(request.url) if request.url.startswith(('http:','https:')) else None)
        page.goto((ROOT/'docs/previews/grounded-v05/ALFRED-Desk-v05.html').as_uri())
        expect(page.locator('#workspace')).to_be_visible();record('single file opens without a backend or credentials')
        expect(page.locator('.preview-notice')).to_contain_text('READ-ONLY OFFLINE PREVIEW');record('preview is labelled clearly')
        page.locator('[data-view=ask]').click()
        for question in ('Opening treatment','ALFRED permissions','Production decisions'):
            page.get_by_role('button',name=question,exact=True).click();expect(page.locator('.ask-source-card').first).to_be_visible();record('precomputed actual retrieval example: '+question)
        page.locator('#ask-question').fill('Arbitrary preview question');page.locator('#ask-submit').click();expect(page.locator('#ask-status')).to_contain_text('three example questions');record('unsupported query reports preview limitation')
        page.locator('[data-view=knowledge]').click();expect(page.locator('.knowledge-node')).to_have_count(20);record('same frontend graph remains interactive')
        page.get_by_role('button',name='Open note ALFRED',exact=True).click();expect(page.locator('.knowledge-inspector h3')).to_have_text('ALFRED');record('source inspection remains available offline')
        page.set_viewport_size({'width':390,'height':844});record('preview has no mobile horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
        record('no HTTP or cloud requests',not network);record('no browser storage',page.evaluate('localStorage.length')==0);record('no JavaScript errors',not errors)
        browser.close()
    (OUT/'preview-report.json').write_text(json.dumps({'count':len(checks),'checks':checks,'errors':errors,'network_requests':network,'real_backend':False,'live_model':False},indent=2)+'\n')
    print('Offline preview checks:',len(checks))

if __name__=='__main__':main()
