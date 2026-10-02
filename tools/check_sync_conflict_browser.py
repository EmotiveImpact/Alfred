"""Real browser -> real local HTTP -> real SQLite: a sync conflict copy in the knowledge view (MEM-014).

The fictional demo vault plus one Syncthing-named copy. No sync client runs and no
model is contacted. Writes a JSON report and a screenshot to ALFRED_SYNC_OUTPUT.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import expect, sync_playwright
from alfred.desk import init_demo
from alfred.desk_http import DeskHTTPServer
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get('ALFRED_SYNC_OUTPUT', ROOT / 'docs' / 'evidence' / 'memory-m14'))
COPY = 'notes/Brief.sync-conflict-20261002-101500-ABCDEFG.md'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []

    def check(name, condition=True):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / 'desk'; keys = init_demo(home)
        (home / 'vault' / COPY).write_text('# Creative brief\nZephyrmarker: a colour opening instead.\n')
        store = KnowledgeStore(home / 'desk.sqlite')
        supervisor = KnowledgeSupervisor(store, keys['owner'], keys['source'], home / 'project', interval=.1, vault=home / 'vault')
        server = DeskHTTPServer(store, supervisor, port=0); thread = threading.Thread(target=server.serve_forever, daemon=True)
        supervisor.start(); thread.start()
        try:
            with sync_playwright() as p:
                kwargs = {'headless': True}
                if os.environ.get('CHROMIUM_PATH'):
                    kwargs['executable_path'] = os.environ['CHROMIUM_PATH']
                browser = p.chromium.launch(**kwargs)
                page = browser.new_page(viewport={'width': 1480, 'height': 1080}, device_scale_factor=1)
                page.on('pageerror', lambda err: errors.append(str(err)))
                page.goto(server.origin); page.fill('#access-key', keys['reader']); page.locator('#login-form button').click()
                page.locator('#workspace').wait_for(state='visible')
                page.locator('[data-view=knowledge]').click()
                expect(page.locator('.knowledge-metric strong').nth(0)).to_have_text('20', timeout=15000)
                check('the copy is not indexed: the twenty demo notes remain twenty')
                check('the map draws one node per indexed note', page.locator('.knowledge-node').count() == 20)
                health = page.locator('#knowledge-health')
                expect(health).to_contain_text(COPY + ': sync conflict copy', timeout=10000)
                check('the existing issue view names the copy as a sync conflict copy')
                page.get_by_label('Search notes').fill('Zephyrmarker')
                expect(page.locator('#knowledge-canvas')).to_contain_text('No matching notes', timeout=10000)
                check('text that exists only in the copy is not searchable')
                page.get_by_label('Search notes').fill('')
                health.scroll_into_view_if_needed()
                page.screenshot(path=str(OUT / 'web-knowledge-conflict.png'), full_page=True)
                check('no uncaught JavaScript errors', not errors)
                browser.close()
        finally:
            supervisor.stop(); server.shutdown(); server.server_close()
    report = {'checks': checks, 'count': len(checks), 'errors': errors, 'session': 'reader', 'transport': 'real loopback HTTP',
              'database': 'real SQLite', 'inputs': 'fictional demo vault plus one Syncthing-named copy',
              'sync_client': False, 'live_model': False}
    (OUT / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
