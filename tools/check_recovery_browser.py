"""Browser acceptance for host recovery in the connected console (RUN-001, M09).

Leaves synthetic interrupted work as a killed host would (a started job, an
unstarted lease, a queued question, no clean-stop marker), reconciles it exactly
as `serve` does at start, then drives the built console in Chromium and checks
the Host health panel reports the previous stop and the recovery counts.
Testing-only tooling; requires `npm run build` in console/ first. No model,
account or private data.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alfred import recovery
from alfred.conversation import ConversationService
from alfred.desk import init_demo
from alfred.desk_http import DeskHTTPServer
from alfred.jobs import JobCoordinator
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'console' / 'dist'
out = Path(os.environ.get('ALFRED_RECOVERY_OUTPUT', ROOT / 'docs' / 'evidence' / 'host-recovery'))
out.mkdir(parents=True, exist_ok=True)
checks, console_messages, page_errors, foreign = [], [], [], []


def check(name, condition=True):
    assert condition, name
    checks.append(name)


if not (DIST / 'index.html').is_file():
    raise SystemExit('Build the console first: cd console && npm run build')

with tempfile.TemporaryDirectory() as temp:
    home = Path(temp) / 'demo'; keys = init_demo(home); owner = keys['owner']
    store = KnowledgeStore(home / 'desk.sqlite')
    jobs = JobCoordinator(store)
    jobs.enrol_worker(owner, 'local-host', 'This computer (local subprocess)', ['wait'])
    # The previous host: it started, never stopped cleanly, and left work behind.
    recovery.begin(home)
    wait = lambda key: {'idempotency_key': key, 'kind': 'wait', 'parameters': {'seconds': 60}, 'inputs': [], 'side_effect_free': True}
    running = jobs.submit(owner, wait('was-running'))['id']
    grant = jobs.lease(owner, 'local-host', ttl=600)
    jobs.start(owner, 'local-host', grant['job'], grant['lease'], backend='local_subprocess')
    jobs.submit(owner, wait('was-leased')); jobs.lease(owner, 'local-host', ttl=600)
    conversations = ConversationService(store)
    sid = conversations.create(owner, {'title': 'Synthetic question'})['id']
    conversations.submit(owner, sid, {'question': 'collection', 'mode': 'sources', 'follow_up': False, 'request_id': 'r1', 'after': 0})
    # The new host's start, as serve does it.
    start = recovery.begin(home)
    report = recovery.reconcile(store, owner, start)
    check('reconciliation marks the started job effect unknown', jobs.view(owner, running)['state'] == 'effect_unknown')
    sup = KnowledgeSupervisor(store, owner, keys['source'], home / 'project', vault=home / 'vault', interval=.2)
    sup.cycle(); sup.start()
    server = DeskHTTPServer(store, sup, port=0, console_dist=DIST, jobs=jobs)
    server.recovery = report
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'), headless=True,
                                        args=['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            page = browser.new_context(viewport={'width': 1648, 'height': 928}).new_page()
            page.on('console', lambda m: console_messages.append(f'{m.type}: {m.text}'))
            page.on('pageerror', lambda e: page_errors.append(str(e)))
            page.on('request', lambda r: foreign.append(r.url) if not r.url.startswith(server.origin) else None)
            page.goto(server.origin + '/console')
            page.get_by_label('Access key').fill(owner); page.get_by_role('button', name='Sign in').click()
            expect(page.locator('.connection-state')).to_have_text('Connected')
            command = page.get_by_label('Command or search')
            command.fill('settings'); command.press('Enter')
            health = page.get_by_role('dialog').get_by_role('region', name='Host health')
            expect(health).to_contain_text('Did not stop cleanly', timeout=15000)
            check('the console reports that the previous host did not stop cleanly')
            text = health.inner_text()
            check('the console reports the interrupted question', '1 questions interrupted' in text)
            check('the console reports the job needing reconciliation', '1 jobs need reconciliation (effect unknown)' in text)
            check('the console reports the unstarted lease returned to the queue', '1 returned to queue' in text)
            check('the console states no clean stop has been recorded yet', 'last clean stop never' in text)
            check('the job counts include the effect unknown state', '1 effect unknown' in text)
            check('no request leaves the ALFRED origin', not foreign)
            browser.close()
    finally:
        sup.stop()
        server.shutdown(); server.server_close()

check('no page errors', not page_errors)
result = {'passed': len(checks), 'checks': checks, 'browser_console': console_messages[-20:], 'page_errors': page_errors,
          'inputs': 'synthetic workspace only', 'model_inference': False, 'console_dist': 'console/dist built from this commit'}
(out / 'browser-report.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'passed': len(checks), 'page_errors': page_errors}))
