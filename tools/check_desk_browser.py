"""Browser acceptance on actual loopback HTTP using installed Playwright + Chromium.

Testing-only dependency, never an ALFRED runtime dependency. No external accounts.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alfred.desk import init_demo
from alfred.desk_store import DeskStore
from alfred.desk_runtime import Supervisor
from alfred.desk_http import DeskHTTPServer
from playwright.sync_api import sync_playwright, expect

out=Path(os.environ.get('ALFRED_BROWSER_OUTPUT','/mnt/data/alfred-visual'))
out.mkdir(parents=True,exist_ok=True)
checks=[]
def check(name, condition=True):
    assert condition, name
    checks.append(name)

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);keys=init_demo(root);store=DeskStore(root/'desk.sqlite')
    sup=Supervisor(store,keys['owner'],keys['source'],root/'project',interval=.1)
    sup.cycle();sup.start()
    server=DeskHTTPServer(store,sup,port=0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':1440,'height':1080},device_scale_factor=1)
            page=context.new_page();errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            def go(view):
                if view in {'evidence','approvals','activity'}:
                    page.locator('.os-dock [data-view=overview]').click()
                elif view=='sources':
                    page.locator('.os-dock [data-view=settings]').click()
                page.locator(f'[data-view="{view}"]').click()
            page.goto(server.origin)
            expect(page.locator('#sign-in')).to_be_visible();check('sign-in screen loads')
            page.screenshot(path=str(out/'ALFRED-sign-in.png'),full_page=True)
            page.fill('#access-key','not-valid');page.get_by_role('button',name='Open your workspace').click()
            expect(page.locator('#login-error')).to_contain_text('invalid');check('bad key shows a useful error')
            page.fill('#access-key',keys['owner']);page.get_by_role('button',name='Open your workspace').click()
            expect(page.locator('#workspace')).to_be_visible();check('owner signs in against real HTTP');go('overview')
            expect(page.locator('.evidence-card')).to_have_count(3);check('three real file records rendered')
            check('owner key not in rendered text',keys['owner'] not in page.inner_text('body'))
            check('access key not persisted in local storage',page.evaluate('localStorage.length')==0)
            check('HttpOnly session cookie hidden from scripts', 'alfred_desk' not in page.evaluate('document.cookie'))
            page.screenshot(path=str(out/'ALFRED-desktop.png'),full_page=True)
            page.get_by_role('button',name='Inspect evidence').first.click()
            expect(page.locator('#detail')).to_be_visible();check('evidence drill-down opens')
            expect(page.locator('#detail-body')).to_contain_text('Source SHA-256');check('source hash available to inspect')
            page.screenshot(path=str(out/'ALFRED-evidence.png'))
            page.get_by_role('button',name='Mark as acknowledged').click()
            expect(page.locator('#detail-body')).to_contain_text('Acknowledged by this');check('explicit acknowledgement recorded')
            page.get_by_role('button',name='Prepare a response draft').click()
            expect(page.locator('#draft-text')).to_be_visible();check('draft editor is usable')
            message='Please review the sample production update before confirming.'
            page.fill('#draft-text',message)
            page.get_by_role('button',name='Review exact proposal').click()
            expect(page.locator('#detail-body')).to_contain_text(message);check('approval presents exact proposed text')
            expect(page.locator('#detail-body')).to_contain_text('Approval fingerprint');check('approval fingerprint visible')
            page.screenshot(path=str(out/'ALFRED-approval.png'))
            page.get_by_role('button',name='Approve local draft',exact=True).click()
            expect(page.locator('.action-card .badge')).to_have_text('verified',timeout=12000)
            check('automatic worker creates and verifies a real local draft')
            expect(page.locator('.action-card')).to_contain_text('Not sent');check('result does not claim message delivery')
            page.reload();expect(page.locator('#workspace')).to_be_visible();check('browser reload retains authenticated view')
            go('approvals');expect(page.locator('.action-card')).to_contain_text(message);check('draft remains after reload')
            page.locator('#pause').click();expect(page.locator('#paused-banner')).to_be_visible();check('pause control shows explicit state')
            file=root/'project/schedule.json';value=json.loads(file.read_text());value.update(revision=2,observed_at=int(time.time()),expires_at=int(time.time())+600,summary='The sample call time is now 11:00. Please confirm the change.')
            file.write_text(json.dumps(value));time.sleep(.25)
            check('paused worker does not ingest changes',store.desk_state(keys['owner'])['counts']['events']==3)
            page.locator('#pause').click();expect(page.locator('#paused-banner')).to_be_hidden()
            deadline=time.monotonic()+3
            while store.desk_state(keys['owner'])['counts']['events']<4 and time.monotonic()<deadline:time.sleep(.03)
            go('evidence');page.locator('#refresh').click()
            expect(page.locator('#view-content')).to_contain_text('11:00',timeout=12000);check('resume imports changed file without manual worker tick')
            for view in ['activity','sources','settings','overview']:
                go(view);expect(page.locator('#view-content')).not_to_be_empty();check('navigation works: '+view)
            # Literal HTML remains data in title and summary.
            value.update(revision=3,observed_at=int(time.time())+1,title='<img src=x onerror=window.pwned=true>',summary='Literal <script>window.pwned=true</script> in a sample document.')
            time.sleep(1.1);file.write_text(json.dumps(value));time.sleep(.3)
            page.locator('#refresh').click();expect(page.locator('#view-content')).to_contain_text('Literal <script>',timeout=12000)
            check('untrusted document markup is rendered as text',page.evaluate('window.pwned === undefined'))
            check('untrusted markup does not create image nodes',page.locator('.evidence-card img').count()==0)
            # Restore a normal sample title for the mobile screenshot.
            value.update(revision=4,observed_at=int(time.time())+1,title='Call time has changed',summary='The sample call time is now 11:00. The crew update needs review.')
            time.sleep(1.1);file.write_text(json.dumps(value));time.sleep(.3);page.locator('#refresh').click()
            expect(page.locator('#view-content')).to_contain_text('crew update needs review',timeout=12000)
            page.set_viewport_size({'width':390,'height':844});check('mobile page has no document overflow',page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            page.screenshot(path=str(out/'ALFRED-mobile.png'),full_page=True)
            page.get_by_role('button',name='Inspect evidence').first.click();expect(page.locator('#detail')).to_be_visible();page.keyboard.press('Escape');expect(page.locator('#detail')).not_to_be_visible();check('native dialog keyboard dismissal works')
            go('settings');page.get_by_role('button',name='Sign out / switch workspace',exact=True).click()
            expect(page.locator('#sign-in')).to_be_visible();check('sign-out clears the working view')
            page.fill('#access-key',keys['reader']);page.get_by_role('button',name='Open your workspace').click();expect(page.locator('#workspace')).to_be_visible();go('overview')
            expect(page.locator('#pause')).to_be_disabled();check('reader pause control disabled')
            page.get_by_role('button',name='Inspect evidence').first.click()
            expect(page.locator('#detail')).to_be_visible()
            check('reader has no draft preparation action',page.get_by_role('button',name='Prepare a response draft').count()==0)
            page.keyboard.press('Escape')
            expect(page.locator('#detail')).not_to_be_visible()
            store.revoke('demo-reader')
            expect(page.locator('#sign-in')).to_be_visible(timeout=12000)
            check('credential revocation removes browser access automatically without restart')
            check('no uncaught JavaScript errors',not errors)
            report={'browser':browser.version,'platform':'Linux Chromium, installed Playwright','checks':checks,'count':len(checks),'uncaught_errors':errors,'transport':'real loopback HTTP','live_model':False,'data':'generated synthetic files only'}
            (out/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps({'passed':len(checks),'browser':browser.version,'uncaught_errors':errors}))
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join();sup.stop()
