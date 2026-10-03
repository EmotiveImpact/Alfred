"""One synthetic project through the connected console and offline recovery.

Real Chromium, same-origin HTTP and SQLite. Backup/restore are local maintenance
operations with the server stopped for restore. No model, provider or device.
"""
import json
import os
import re
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from alfred.desk import init_demo
from alfred.desk_http import DeskHTTPServer
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred import lifecycle

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = Path(os.environ.get('ALFRED_PILOT_OUTPUT', ROOT / 'docs/evidence/pilot-groundwork/loop'))
    output.mkdir(parents=True, exist_ok=True)
    checks, errors, foreign = [], [], []
    def check(label, condition=True):
        if not condition:
            raise AssertionError(label)
        checks.append(label)
    with tempfile.TemporaryDirectory() as temporary:
        home = Path(temporary) / 'demo'; keys = init_demo(home)
        support = home / 'vault/projects/Pilot Beacon.md'
        original = '---\ntype: project\n---\n# Pilot Beacon\nPilot Beacon review records distinguish planning from ready.\n'
        support.write_text(original)
        current = [None]; origins = set()
        def start():
            store = KnowledgeStore(home / 'desk.sqlite')
            supervisor = KnowledgeSupervisor(store, keys['owner'], keys['source'], home / 'project', vault=home / 'vault')
            supervisor.cycle()
            server = DeskHTTPServer(store, supervisor, port=0, console_dist=ROOT / 'console/dist')
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
            thread.start(); current[0] = (store, supervisor, server, thread); origins.add(server.origin)
            return store, server
        def stop():
            if current[0]:
                _, supervisor, server, thread = current[0]
                supervisor.stop(); server.conversations.stop(); server.shutdown(); server.server_close(); thread.join(3)
                current[0] = None
        store, server = start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'),
                    headless=True, args=['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
                page = browser.new_page(viewport={'width': 1512, 'height': 982})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.on('request', lambda request: foreign.append(request.url) if not any(request.url.startswith(o + '/') for o in origins) else None)
                def login():
                    page.goto(server.origin + '/console/')
                    page.get_by_label('Access key').fill(keys['owner']); page.get_by_role('button', name='Sign in', exact=True).click()
                    expect(page.locator('.connection-state')).to_have_text('Connected')
                def ask():
                    command = page.get_by_label('Command or search'); command.fill('Pilot Beacon'); command.press('Enter')
                    dialog = page.get_by_role('dialog')
                    expect(dialog.locator('.evidence').filter(has_text='projects/Pilot Beacon.md')).to_be_visible(timeout=15000)
                    return dialog
                login()
                page.get_by_role('button', name='Explore projects').click()
                page.get_by_role('dialog').locator('.record-row').filter(has_text='Pilot Beacon').click()
                inspector = page.get_by_role('complementary', name='Record inspector')
                expect(inspector.locator('.source-lines')).to_contain_text('planning from ready')
                check('select a project and inspect its original authored lines')
                dialog = ask(); expect(dialog).to_contain_text('Context: Pilot Beacon')
                check('ask uses the selected project while preserving source mode')
                evidence = dialog.locator('.evidence').filter(has_text='projects/Pilot Beacon.md')
                evidence.get_by_role('button', name='Pilot Beacon', exact=True).click()
                expect(inspector.locator('.source-lines')).to_contain_text('planning from ready')
                check('answer source inspection returns the original record')
                # Opening a source closes the answer panel; ask again from that selection.
                dialog = ask()
                def capture(value, new=False):
                    evidence = dialog.locator('.evidence').filter(has_text='projects/Pilot Beacon.md')
                    evidence.get_by_role('button', name='Remember this…').click()
                    form = dialog.get_by_label('Remember this', exact=True)
                    if new:
                        form.get_by_label('Record').select_option('new')
                        form.get_by_label('Name').fill('Beacon review')
                        form.get_by_label('Kind').select_option('project')
                    else:
                        form.get_by_label('Record').select_option(label='Beacon review (project)')
                    form.get_by_label('Statement').select_option('status')
                    form.get_by_label('Value').fill(value)
                    form.get_by_label('From line').fill('5'); form.get_by_label('To line').fill('5')
                    form.get_by_role('button', name='Preview proposal').click()
                    preview = dialog.get_by_label('Remember this preview')
                    expect(preview).to_contain_text(value)
                    return preview
                preview = capture('planning', new=True)
                check('remember remains a proposal before explicit acceptance', not any(c['usable'] for c in server.memory.view(keys['owner'])['claims']))
                preview.get_by_role('button', name='Accept as my reviewed statement').click()
                expect(preview).to_contain_text('Accepted as your reviewed statement')
                first = server.memory.view(keys['owner'])['claims'][0]['id']
                check('accepted proposal is usable with its original evidence', server.memory.view(keys['owner'])['claims'][0]['usable'])
                dialog.get_by_label('Close panel').click()
                dialog = ask(); capture('ready')
                dialog.get_by_label('Close panel').click()
                command = page.get_by_label('Command or search'); command.fill('memory'); command.press('Enter')
                queue = page.get_by_role('dialog'); card = queue.get_by_role('article', name='Proposed: Beacon review status')
                card.get_by_role('button', name='Replace an earlier statement…').click()
                card.get_by_label('Replaces').select_option(first)
                card.get_by_role('button', name='Accept as replacement').click()
                expect(queue.get_by_role('article')).to_have_count(0, timeout=15000)
                claims = server.memory.view(keys['owner'])['claims']
                second = next(c for c in claims if c['state'] == 'accepted')
                check('correct through an explicit replacement with retained lineage', second['replaces_id'] == first and next(c for c in claims if c['id'] == first)['state'] == 'superseded')
                queue.get_by_label('Close panel').click()
                dialog = ask()
                expect(dialog.locator('.statement.usable')).to_contain_text('ready', timeout=15000)
                check('corrected value is recalled through browser-to-backend retrieval', 'planning' not in dialog.locator('.statement.usable').inner_text())
                dialog.get_by_label('Close panel').click()
                manifest = lifecycle.backup(store, keys['owner'], home / 'backups')
                page.get_by_role('button', name='Explore projects').click()
                page.get_by_role('dialog').get_by_role('button', name=re.compile('^Beacon review ')).click()
                expect(inspector).to_contain_text('ready', timeout=15000)
                for index, value in enumerate(('ready', 'planning'), 1):
                    statement = inspector.locator('.statement').filter(has=page.locator('p', has_text=re.compile('^status ' + value + '$')))
                    statement.get_by_role('button', name='Forget this statement').click()
                    inspector.get_by_role('button', name='Confirm forget').click()
                    expect(inspector.locator('.statement').filter(has_text='Forgotten · value removed')).to_have_count(index, timeout=15000)
                check('forget both current and superseded values with receipts', all(c['state'] == 'forgotten' and c['value'] is None for c in server.memory.view(keys['owner'])['claims']))
                check('forget preserves the user-owned authored note', support.read_text() == original)
                page.screenshot(path=str(output / 'forgotten.png'))
                stop(); store, server = start(); login()
                check('restart replays deletion before serving', all(c['state'] == 'forgotten' for c in server.memory.view(keys['owner'])['claims']))
                stop()
                recovery = lifecycle.restore(home / 'backups' / manifest['file'], home / 'desk.sqlite')
                store, server = start(); login()
                page.get_by_role('button', name='Explore projects').click()
                page.get_by_role('dialog').get_by_role('button', name=re.compile('^Beacon review ')).click()
                expect(inspector).to_contain_text('Forgotten · value removed', timeout=15000)
                check('restore an older backup without reviving reviewed values', recovery['integrity_check'] == 'ok' and all(c['value'] is None and c['state'] == 'forgotten' for c in server.memory.view(keys['owner'])['claims']))
                page.get_by_label('Close record inspector').click(); dialog = ask()
                check('restored source mode still distinguishes authored text from forgotten memory', dialog.locator('.statement.usable').count() == 0)
                check('no model, external traffic or JavaScript errors', not foreign and not errors)
                check('no effects or inbox files were created', store.desk_state(keys['owner'])['counts']['drafts'] == 0 and not (home / 'vault/ALFRED/Inbox').exists())
                check('bearer and private browser storage stay out of rendered output', keys['owner'] not in page.locator('body').inner_text() and page.evaluate('localStorage.length') == 0)
                version = browser.version; browser.close()
        except Exception:
            print(json.dumps({'completed_checks': checks, 'claim_states': [
                {k: c[k] for k in ('id', 'state', 'version', 'value')}
                for c in server.memory.view(keys['owner'])['claims']]}, indent=2), flush=True)
            raise
        finally:
            stop()
    report = {'count': len(checks), 'checks': checks, 'errors': errors, 'foreign_requests': foreign,
              'browser': version, 'transport': 'real loopback HTTP', 'database': 'real SQLite',
              'restart': 'server process objects reopened; SIGKILL covered separately',
              'model_inference': False, 'inputs': 'synthetic project only'}
    (output / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
