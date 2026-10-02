"""M03 real browser acceptance, fictional vault and real loopback/SQLite only.

The packet fixture declares abstention and performs no model inference. This
exercises the reviewed-memory bridge without retrying the blocked benchmark.
"""
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
OUT=Path(os.environ.get('ALFRED_M03_OUTPUT',str(ROOT/'docs/evidence/memory-m03-browser')))


class PacketFixture:
    model='context-browser-fixture-not-an-llm'
    def __init__(self):self.packets=[]
    def generate(self,packet):
        self.packets.append(packet)
        return {'answerable':False,'claims':[]}


def main():
    OUT.mkdir(parents=True,exist_ok=True);checks=[];errors=[]
    def check(label,condition=True):
        if not condition:raise AssertionError(label)
        checks.append(label)
    with tempfile.TemporaryDirectory() as tmp:
        home=Path(tmp)/'demo';keys=init_demo(home);store=KnowledgeStore(home/'desk.sqlite');model=PacketFixture()
        support=home/'vault'/'M03-Support.md';support.write_text('# Synthetic original support\nThe original review record is in planning.\n')
        supervisor=KnowledgeSupervisor(store,keys['owner'],keys['source'],home/'project',interval=.1,vault=home/'vault')
        supervisor.start()
        deadline=time.monotonic()+8
        while not any(n['path']=='M03-Support.md' for n in store.knowledge(keys['owner'])['nodes']):
            if time.monotonic()>deadline:raise AssertionError('synthetic source did not index')
            time.sleep(.05)
        server=DeskHTTPServer(store,supervisor,port=0,local_model=model)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        entity={'id':'beacon-context','kind':'project','name':'Beacon Programme'};server.memory.create_entity(keys['owner'],entity)
        n=next(n for n in store.knowledge(keys['owner'])['nodes'] if n['path']=='M03-Support.md')
        cid=server.memory.propose(keys['owner'],{'request_id':'synthetic-context','subject_id':entity['id'],
             'predicate':'status','object_id':None,'value':'reviewed-planning-marker','valid_from':None,'valid_until':None,
             'evidence':{'note_id':n['id'],'sha256':n['sha256'],'revision':n['revision'],'start_line':2,'end_line':2}})['id']
        def review(decision):
            c=next(c for c in server.memory.view(keys['owner'])['claims'] if c['id']==cid)
            server.memory.review(keys['owner'],cid,{'version':c['version'],'decision':decision,'replaces_id':None,'replaces_version':None})
        try:
            with sync_playwright() as p:
                options={'headless':True}
                if os.environ.get('CHROMIUM_PATH'):options['executable_path']=os.environ['CHROMIUM_PATH']
                browser=p.chromium.launch(**options);page=browser.new_page(viewport={'width':1512,'height':982})
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(server.origin);page.fill('#access-key',keys['owner']);page.locator('#login-form button').click();page.locator('.presence').wait_for()
                page.locator('.os-dock [data-view=ask]').click()
                def ask_question(mode='sources'):
                    page.select_option('#ask-mode',mode);page.fill('#ask-question','Beacon Programme');page.locator('#ask-submit').click()
                    expect(page.locator('#ask-submit')).to_be_enabled(timeout=10000)
                ask_question();expect(page.locator('#ask-status')).to_contain_text('No supporting notes',timeout=10000)
                check('unaccepted proposal cannot retrieve an entity absent from authored text',page.locator('.ask-memory').count()==0)
                review('accept');ask_question();expect(page.locator('.ask-memory')).to_have_count(1,timeout=10000)
                expect(page.locator('.ask-memory')).to_contain_text('beacon-context')
                check('accepted memory is labelled with distinct stable entity identity')
                expect(page.locator('.ask-reviewed-memory')).to_contain_text('not verified facts or permissions')
                check('review basis is visible rather than presented as verified truth')
                expect(page.locator('.ask-excerpt')).to_have_text('The original review record is in planning.')
                expect(page.locator('.ask-provenance')).to_contain_text('Original support for a reviewed memory')
                check('exact original support is retrieved within source mode')
                expect(page.locator('.ask-source-path')).to_contain_text('lines 2 to 2')
                check('source has absolute original line numbers')
                check('source mode does not call the model fixture',model.packets==[])
                page.get_by_role('button',name='S1 · Open source',exact=True).click();expect(page.locator('#detail-body')).to_contain_text('SHA-256')
                check('original numbered note and hash remain inspectable');page.keyboard.press('Escape')
                page.screenshot(path=str(OUT/'ALFRED-M03-Ask.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                check('accepted memory fits a narrow viewport',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                page.screenshot(path=str(OUT/'ALFRED-M03-Ask-Mobile.png'),full_page=True)
                page.set_viewport_size({'width':1512,'height':982})
                ask_question('local_model');expect(page.locator('#ask-status')).to_contain_text('could not establish an answer',timeout=10000)
                check('explicit model mode sends a bounded labelled memory packet',len(model.packets)==1 and model.packets[0]['memory'][0]['claim_id']==cid)
                page.locator('[data-view=conversation]').click();page.fill('#conversation-question','Beacon Programme');page.locator('#conversation-send').click()
                expect(page.locator('.conversation-memory-statement')).to_have_count(1,timeout=10000)
                check('conversation also uses accepted current reviewed memory')
                sid=server.conversations.listing(keys['owner'])['sessions'][0]['id']
                with store.connection() as db:
                    raw=db.execute('SELECT result FROM conversation_turns').fetchone()[0]
                    check('saved turn stores bindings instead of reviewed value or source quote','reviewed-planning-marker' not in raw and 'The original review record' not in raw)
                page.reload();page.locator('.presence').wait_for();page.locator('.os-dock [data-view=ask]').click();page.locator('[data-view=conversation]').click()
                expect(page.locator('.conversation-memory-statement')).to_have_count(1,timeout=10000)
                check('reload reconstructs current accepted memory from its ledger')
                page.get_by_role('button',name='Prepare a local draft',exact=True).click();page.fill('#conversation-draft-text','Please confirm the assignment.')
                page.get_by_role('button',name='Review exact draft',exact=True).click();expect(page.locator('#detail-title')).to_have_text('Create this local draft?')
                check('memory does not remove the separate exact draft approval')
                review('dispute');page.get_by_role('button',name='Approve local draft',exact=True).click()
                expect(page.locator('#toast')).to_contain_text('approval is no longer current',timeout=10000)
                with store.connection() as db:check('changed review blocks the open draft approval',db.execute('SELECT count(*) FROM drafts').fetchone()[0]==0)
                page.keyboard.press('Escape');expect(page.locator('#conversation-turns')).to_contain_text('reviewed memory changed',timeout=15000)
                expect(page.locator('.conversation-memory-statement')).to_have_count(0)
                check('changed review clears the saved conversation response')
                check('cleared conversation storage has no stale response',server.conversations.view(keys['owner'],sid)['turns'][0]['result'] is None)
                page.locator('.os-dock [data-view=ask]').click();ask_question('sources')
                expect(page.locator('#ask-status')).to_contain_text('No supporting notes',timeout=10000)
                check('a disputed reviewed value cannot be recalled as accepted memory',page.locator('.ask-memory').count()==0)
                review('accept');ask_question();expect(page.locator('.ask-memory')).to_have_count(1,timeout=10000)
                page.get_by_role('button',name='S1 · Open source',exact=True).click();expect(page.locator('#detail')).to_be_visible()
                review('withdraw');expect(page.locator('#ask-status')).to_contain_text('reviewed memory changed',timeout=15000)
                expect(page.locator('#detail')).not_to_be_visible();expect(page.locator('.ask-memory')).to_have_count(0)
                check('withdrawal clears displayed memory and open source modal without editing the note')
                check('read and review operations did not write the vault',support.read_text()=='# Synthetic original support\nThe original review record is in planning.\n')
                # A separate accepted claim demonstrates explicit namesake handling.
                cid=server.memory.propose(keys['owner'],{'request_id':'namesake-context','subject_id':entity['id'],
                    'predicate':'status','object_id':None,'value':'planning','valid_from':None,'valid_until':None,
                    'evidence':{'note_id':n['id'],'sha256':n['sha256'],'revision':n['revision'],'start_line':2,'end_line':2}})['id'];review('accept')
                server.memory.create_entity(keys['owner'],{'id':'beacon-namesake','kind':'project','name':'Beacon Programme'})
                before=len(model.packets);ask_question('local_model');expect(page.locator('#ask-status')).to_contain_text('Clarify the entity',timeout=10000)
                expect(page.locator('.ask-reviewed-memory')).to_contain_text('beacon-namesake')
                check('namesakes preserve separate IDs and withhold model use until clarified',len(model.packets)==before)
                check('no browser local storage',page.evaluate('localStorage.length')==0)
                check('no bearer rendered',keys['owner'] not in page.locator('body').inner_text())
                check('no effect executed',store.desk_state(keys['owner'])['counts']['drafts']==0)
                check('no uncaught JavaScript errors',not errors);version=browser.version;browser.close()
        finally:
            supervisor.stop();server.shutdown();server.server_close();thread.join(3)
    report={'count':len(checks),'checks':checks,'errors':errors,'browser':version,
            'transport':'real loopback HTTP','database':'real SQLite','inputs':'fictional notes only',
            'model_inference':False,'model':'packet-capture abstention fixture'}
    (OUT/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
