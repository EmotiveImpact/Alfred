"""Real browser, local HTTP, SQLite and fictional sources; delayed fixture model.

Actual model inference is evaluated separately and never impersonated by this fixture.
"""
from pathlib import Path
import json,os,sys,tempfile,threading,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore,KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer
ROOT=Path(__file__).resolve().parents[1];OUT=Path(os.environ.get('ALFRED_CONVERSATION_OUTPUT',str(ROOT/'docs/evidence/conversation-v07')));OUT.mkdir(parents=True,exist_ok=True)

class DelayedFixture:
    model='test-fixture-not-an-llm'
    def __init__(self):self.started=threading.Event();self.release=threading.Event();self.packet=None
    def generate(self,packet):
        self.packet=packet;self.started.set();self.release.wait(12)
        source=packet['evidence'][0]
        return {'answerable':True,'claims':[{'text':'Synthetic browser-test reply, not an AI inference.',
          'citations':[{'source_id':source['source_id'],'start_line':source['start_line'],'end_line':source['end_line']}]}]}


def main():
    checks=[];errors=[]
    def check(label,condition=True):
        if not condition:raise AssertionError(label)
        checks.append(label)
    with tempfile.TemporaryDirectory() as tmp:
        home=Path(tmp)/'demo';keys=init_demo(home);store=KnowledgeStore(home/'desk.sqlite');model=DelayedFixture()
        supervisor=KnowledgeSupervisor(store,keys['owner'],keys['source'],home/'project',interval=.1,vault=home/'vault')
        server=DeskHTTPServer(store,supervisor,port=0,local_model=model);supervisor.start();thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                options={'headless':True}
                if os.environ.get('CHROMIUM_PATH'):options['executable_path']=os.environ['CHROMIUM_PATH']
                browser=p.chromium.launch(**options);page=browser.new_page(viewport={'width':1512,'height':982});page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(server.origin);page.fill('#access-key',keys['owner']);page.locator('#login-form button').click();page.locator('.presence').wait_for();check('existing personal home retained')
                page.locator('.os-dock [data-view=ask]').click();page.locator('[data-view=conversation]').click();expect(page.locator('#conversation-select')).to_contain_text('No saved');check('conversation is a mode of the existing Ask space')
                page.fill('#conversation-question','What is the equipment collection status?');page.locator('#conversation-send').click();expect(page.locator('.conversation-source').first).to_be_visible(timeout=15000);check('first question uses real indexed sources');check('source mode is not represented as a model reply',page.locator('.conversation-claim').count()==0)
                page.fill('#conversation-question','Who owns that?');page.locator('#conversation-send').click();expect(page.locator('.conversation-turn')).to_have_count(2);expect(page.locator('.conversation-turn').last.locator('.conversation-source').first).to_be_visible(timeout=15000)
                sid=server.conversations.listing(keys['owner'])['sessions'][0]['id'];turns=server.conversations.view(keys['owner'],sid)['turns'];check('follow-up carries prior user topic to fresh retrieval','equipment' in turns[1]['result']['packet']['retrieval_question']);check('prior generated statements are not source facts',not turns[1]['result']['claims'])
                page.screenshot(path=str(OUT/'ALFRED-Conversation.png'),full_page=True)
                page.locator('.conversation-source summary').first.click();page.get_by_role('button',name='Inspect source',exact=True).first.click();expect(page.locator('#detail-body')).to_contain_text('SHA-256');check('original numbered source remains inspectable');page.keyboard.press('Escape')
                page.reload();page.locator('.presence').wait_for();page.locator('.os-dock [data-view=ask]').click();page.locator('[data-view=conversation]').click();expect(page.locator('.conversation-turn')).to_have_count(2);check('saved thread survives browser reload')
                page.get_by_role('button',name='Prepare a local draft',exact=True).last.click();page.fill('#conversation-draft-text','Please confirm the equipment collection arrangements.');page.get_by_role('button',name='Review exact draft',exact=True).click();expect(page.locator('#detail-title')).to_have_text('Create this local draft?');check('draft requires an explicit second approval')
                with store.connection() as db:check('opening approval did not create a draft',db.execute('SELECT count(*) FROM drafts').fetchone()[0]==0)
                page.get_by_role('button',name='Approve local draft',exact=True).click();expect(page.locator('.action-card')).to_contain_text('verified',timeout=15000);check('approved conversation draft executes through existing outbox')
                with store.connection() as db:check('one real local draft, nothing sent',db.execute('SELECT count(*) FROM drafts').fetchone()[0]==1)
                page.locator('.os-dock [data-view=ask]').click();page.locator('[data-view=conversation]').click();expect(page.locator('.conversation-turn')).to_have_count(2)
                page.select_option('#conversation-mode','local_model');page.fill('#conversation-question','Summarise the equipment collection.');page.locator('#conversation-send').click();expect(page.locator('#conversation-status')).to_contain_text('working',timeout=15000);check('model request is queued rather than blocking HTTP',model.started.wait(2))
                start=time.monotonic();response=page.request.get(server.origin+'/desk/state');check('state endpoint responds while model is deliberately blocked',response.status==200 and time.monotonic()-start<2)
                page.locator('.os-dock [data-view=knowledge]').click();expect(page.locator('.knowledge-node')).to_have_count(20,timeout=5000);check('other workspace features remain usable during inference')
                model.release.set();page.locator('.os-dock [data-view=ask]').click();page.locator('[data-view=conversation]').click();expect(page.locator('.conversation-claim')).to_contain_text('Synthetic browser-test reply',timeout=15000);check('structured model fixture is labelled, not actual inference evidence')
                current=server.conversations.view(keys['owner'],sid)['turns'][-1];target=current['result']['packet']['evidence'][0]['path'];(home/'vault'/target).write_text('# Updated source\nEquipment arrangements changed.\n');expect(page.locator('#conversation-turns')).to_contain_text('A source changed',timeout=15000);check('changed notes invalidate stored interpretations');expect(page.locator('.conversation-claim')).to_have_count(0)
                page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'ALFRED-Conversation-Mobile.png'),full_page=True);check('mobile has no horizontal overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'));check('no browser persistent storage',page.evaluate('localStorage.length')==0);check('raw access key never rendered',keys['owner'] not in page.locator('body').inner_text())
                page.set_viewport_size({'width':1512,'height':982});page.once('dialog',lambda dialog:dialog.accept());page.locator('#conversation-forget').click();expect(page.locator('.conversation-turn')).to_have_count(0,timeout=15000);check('forget removes server thread');check('forget does not undo completed draft',store.desk_state(keys['owner'])['counts']['drafts']==1)
                page.locator('#conversation-new').click();expect(page.locator('#conversation-select')).to_contain_text('New conversation',timeout=10000);check('new session can be created deliberately')
                store.revoke('demo-owner');expect(page.locator('#sign-in')).to_be_visible(timeout=15000);check('revocation clears conversation view without restart',page.locator('.conversation-turn').count()==0);check('no uncaught JavaScript errors',not errors)
                version=browser.version;browser.close()
        finally:model.release.set();supervisor.stop();server.shutdown();server.server_close();thread.join(3)
    report={'count':len(checks),'checks':checks,'errors':errors,'browser':version,'transport':'real local HTTP','storage':'real SQLite and fictional source files','model_inference':False,'model':'delayed fixture, separate real model experiment has its own receipt'}
    (OUT/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
