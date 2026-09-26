"""Personal OS acceptance against the real local server, SQLite and source files."""
from pathlib import Path
import json,os,sys,tempfile,threading,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore,KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evidence/personal-os-v06';OUT.mkdir(parents=True,exist_ok=True)

def main():
    checks=[];errors=[]
    def check(name,condition=True):
        if not condition:raise AssertionError(name)
        checks.append(name)
    with tempfile.TemporaryDirectory() as tmp:
        h=Path(tmp)/'demo';keys=init_demo(h);now=[int(time.time())];store=KnowledgeStore(h/'desk.sqlite',clock=lambda:now[0]);sup=KnowledgeSupervisor(store,keys['owner'],keys['source'],h/'project',interval=.1,vault=h/'vault');server=DeskHTTPServer(store,sup,port=0);sup.start();thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                options={'headless':True}
                if os.environ.get('CHROMIUM_PATH'):options['executable_path']=os.environ['CHROMIUM_PATH']
                browser=p.chromium.launch(**options);page=browser.new_page(viewport={'width':1512,'height':982})
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(server.origin);page.fill('#access-key',keys['owner']);page.locator('#login-form button').click();page.locator('.presence').wait_for();expect(page.locator('#presence-memory-count')).to_contain_text('20 notes',timeout=15000)
                check('default landing is personal home, not dashboard');check('admin sidebar removed',page.locator('.sidebar').count()==0);check('viewport workspace excludes dock',page.evaluate("document.querySelector('main').getBoundingClientRect().bottom <= document.querySelector('.os-dock').getBoundingClientRect().top"))
                check('source-derived current context visible',page.locator('.presence-update').count()==2)
                page.screenshot(path=str(OUT/'ALFRED-OS-Home.png'),full_page=True)
                page.locator('#focus-toggle').click();check('focus mode switches only presentation',page.locator('body').get_attribute('class')=='os-focus' and not store.paused('demo-production'))
                page.locator('#focus-toggle').click();check('focus exit restores full view','os-focus' not in (page.locator('body').get_attribute('class') or ''))
                page.keyboard.press('Control+k');expect(page.locator('#command-palette')).to_be_visible();check('keyboard opens launcher')
                page.locator('#command-query').fill('Memory');page.screenshot(path=str(OUT/'ALFRED-OS-Command.png'),full_page=True);page.keyboard.press('Enter');expect(page.locator('.knowledge-node')).to_have_count(20,timeout=15000);check('launcher navigates to actual memory')
                page.get_by_role('button',name='Open note ALFRED',exact=True).click();expect(page.locator('.knowledge-inspector h3')).to_have_text('ALFRED');check('graph inspection preserved')
                page.screenshot(path=str(OUT/'ALFRED-OS-Memory.png'),full_page=True)
                page.get_by_role('button',name='Read source text').click();expect(page.locator('#detail-body')).to_contain_text('SHA-256');page.keyboard.press('Escape');check('hashes remain behind explicit inspection')
                page.locator('.os-dock [data-view=presence]').click();page.fill('#presence-query','Opening treatment');page.locator('.presence-send').click();expect(page.locator('.ask-source-card').first).to_be_visible();check('home question uses real source retrieval')
                expect(page.locator('#ask-status')).to_contain_text('not an AI-generated answer');check('does not impersonate a live model')
                page.screenshot(path=str(OUT/'ALFRED-OS-Ask.png'),full_page=True)
                page.locator('#launcher-open').click();page.locator('#command-query').fill('Sources');page.keyboard.press('ArrowDown');check('arrow key selects another command',page.locator('#command-query').get_attribute('aria-activedescendant')=='cmd-1');page.keyboard.press('Escape');check('escape closes palette',not page.locator('#command-palette').is_visible())
                page.locator('#launcher-open').click();page.locator('#command-query').fill('<img src=x onerror=window.commandAttack=true>');check('command text is literal',page.locator('#command-results img').count()==0 and page.evaluate('window.commandAttack') is None);page.keyboard.press('Escape')
                page.locator('.os-dock [data-view=pulse]').click();expect(page.locator('.routine-row')).to_have_count(2,timeout=15000);check('two backed local routines visible');expect(page.locator('#routine-history')).to_contain_text('Nothing has run');check('schedules start off without fabricated activity')
                page.get_by_role('button',name='Run now').first.click();expect(page.locator('.routine-run')).to_have_count(1,timeout=15000);check('manual run creates a persisted report',len(server.pulse.view(keys['owner'])['runs'])==1)
                memory=page.locator('.routine-row').filter(has_text='Memory check');memory.get_by_role('button',name='Enable schedule').click();expect(memory).to_contain_text('Every 15m');check('owner explicitly enables schedule')
                now[0]+=901;expect(page.locator('.routine-run')).to_have_count(2,timeout=15000);check('real foreground supervisor runs due report automatically')
                page.screenshot(path=str(OUT/'ALFRED-OS-Pulse.png'),full_page=True)
                # Keep the scheduling exercise within the real 30-minute session TTL.
                server.pulse.configure(keys['owner'],'memory-health',{'enabled':True,'interval_seconds':60})
                page.locator('#pause').click();expect(page.locator('#paused-banner')).to_be_visible();expect(page.get_by_role('button',name='Run now').first).to_be_disabled(timeout=10000);check('pause disables routine execution');before=len(server.pulse.view(keys['owner'])['runs']);now[0]+=61;page.wait_for_timeout(300);check('no due work while paused',len(server.pulse.view(keys['owner'])['runs'])==before)
                page.locator('#pause').click();expect(page.locator('.routine-run')).to_have_count(3,timeout=15000);check('resume processes one due report, not catchup storm')
                memory.get_by_role('button',name='Turn schedule off').click();expect(memory).to_contain_text('schedule off');check('schedule can be disabled')
                page.reload();page.locator('.presence').wait_for();page.locator('.os-dock [data-view=pulse]').click();expect(page.locator('.routine-run')).to_have_count(3,timeout=15000);check('reports survive browser reload')
                page.locator('.os-dock [data-view=overview]').click();expect(page.locator('.evidence-card')).to_have_count(3);check('existing work briefing still accessible');page.locator('[data-view=approvals]').click();expect(page.locator('#view-content')).to_contain_text('Nothing awaiting');check('decisions accessible within Work')
                page.locator('.os-dock [data-view=presence]').click();page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'ALFRED-OS-Mobile.png'),full_page=True);check('mobile has no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                check('mobile dock remains visible',page.locator('.os-dock').is_visible());check('no bearer rendered',keys['owner'] not in page.locator('body').inner_text());check('no browser persistence',page.evaluate('localStorage.length')==0)
                page.set_viewport_size({'width':1512,'height':982});page.locator('.os-dock [data-view=settings]').click();page.get_by_role('button',name='Sign out / switch workspace',exact=True).click();expect(page.locator('#sign-in')).to_be_visible();check('signout removes the OS session')
                page.fill('#access-key',keys['reader']);page.locator('#login-form button').click();page.locator('.presence').wait_for();page.locator('.os-dock [data-view=pulse]').click();expect(page.locator('.routine-row')).to_have_count(2);expect(page.get_by_role('button',name='Run now').first).to_be_disabled();expect(page.get_by_role('button',name='Enable schedule').first).to_be_disabled();check('reader cannot run or schedule')
                page.locator('#launcher-open').click();store.revoke('demo-reader');expect(page.locator('#sign-in')).to_be_visible(timeout=15000);check('revocation clears workspace and open palette',not page.locator('#command-palette').is_visible() and page.locator('#command-query').input_value()=='')
                check('no uncaught JavaScript errors',not errors);version=browser.version;browser.close()
        finally:sup.stop();server.shutdown();server.server_close();thread.join()
    report={'count':len(checks),'checks':checks,'errors':errors,'browser':version,'transport':'real loopback HTTP','database':'real SQLite','fixture':'synthetic notes and project only','model_inference':False}
    (OUT/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
