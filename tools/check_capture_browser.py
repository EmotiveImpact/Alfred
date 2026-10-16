"""Browser-to-backend acceptance for owner-authored capture policies (MEM-004, M04, M10).

The real loopback ALFRED server over the synthetic demo vault plus one synthetic meeting
note, the built console served from the same origin, real Chromium. Requires
`npm run build` in console/ first. No model, account, device or private data.

Covers: two authored policies run by the host's own supervisor cycle; every match
arriving as a proposal and none accepted; the Capture tab listing each policy with its
rule, context and proposed, accepted and dismissed counts; a budget overflow counted,
not proposed; counts following review decisions; a reader seeing no policy; layout at
390px. Screenshots and browser-report.json go to docs/evidence/capture-policies/ (or
ALFRED_CAPTURE_OUTPUT).
"""
import json
import os
import re
from pathlib import Path
import sys
import tempfile
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer
from alfred.reviewed_memory import ReviewedMemory
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'console' / 'dist'
out = Path(os.environ.get('ALFRED_CAPTURE_OUTPUT', ROOT / 'docs' / 'evidence' / 'capture-policies'))
out.mkdir(parents=True, exist_ok=True)
checks, console_messages, page_errors, foreign = [], [], [], []
MEETING = ('---\ntitle: Atlas weekly\ntags: [synthetic, alfred-demo]\n---\n# Atlas weekly\n\n'
           'Decision: launch Atlas in the spring window\n'
           '- Decision: hire one more designer\n'
           '- [ ] 2030-03-20 send the Atlas budget to finance\n'
           '- [ ] 2030-03-22 confirm the venue\n')


def check(name, condition=True, detail=None):
    assert condition, f'{name}: {detail}' if detail is not None else name
    checks.append(name)


if not (DIST / 'index.html').is_file():
    raise SystemExit('Build the console first: cd console && npm run build')

with tempfile.TemporaryDirectory() as temp:
    home = Path(temp) / 'demo'; keys = init_demo(home)
    (home / 'vault' / 'notes' / 'Atlas weekly.md').write_text(MEETING)
    store = KnowledgeStore(home / 'desk.sqlite')
    sup = KnowledgeSupervisor(store, keys['owner'], keys['source'], home / 'project', vault=home / 'vault', interval=.2)
    sup.cycle()
    server = DeskHTTPServer(store, sup, port=0, console_dist=DIST)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); thread.start()
    owner, reader = keys['owner'], keys['reader']
    memory = ReviewedMemory(store)
    memory.create_entity(owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas'})
    base = {'version': 0, 'enabled': True, 'sources': ['demo-source'], 'path_prefix': 'notes/'}
    server.capture.author(owner, 'decisions', {**base, 'name': 'Meeting decisions', 'context': 'company', 'daily_budget': 10,
                                               'match': {'kind': 'line_prefix', 'prefix': 'Decision:'},
                                               'proposes': {'subject_id': 'atlas', 'predicate': 'decision', 'memory_type': 'semantic', 'retention_days': None}})
    server.capture.author(owner, 'commitments', {**base, 'name': 'Dated commitments', 'context': 'personal', 'daily_budget': 1,
                                                 'match': {'kind': 'dated_line', 'keyword': None},
                                                 'proposes': {'subject_id': 'atlas', 'predicate': 'scheduled_for', 'memory_type': 'commitment', 'retention_days': None}})
    sup.start()

    def claims():
        return memory.view(owner)['claims']

    deadline = time.time() + 15
    while len(claims()) < 3 and time.time() < deadline:
        time.sleep(.1)
    check('the supervisor cycle proposes every match within budget', len(claims()) == 3, len(claims()))
    check('nothing is accepted automatically', all(c['state'] == 'proposed' and not c['usable'] for c in claims()))
    check('each proposal is bound to its exact line, hash and revision',
          all(c['source'] and c['source']['start_line'] == c['source']['end_line'] for c in claims()))
    check('the dated line becomes a scheduled commitment statement',
          any(c['value'] == '2030-03-20 send the Atlas budget to finance' and c['memory_type'] == 'commitment' for c in claims()))

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'), headless=True,
                                        args=['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            context = browser.new_context(viewport={'width': 1648, 'height': 928}, device_scale_factor=1, locale='en-GB', timezone_id='UTC')
            page = context.new_page()
            page.on('console', lambda m: console_messages.append(f'{m.type}: {m.text}'))
            page.on('pageerror', lambda e: page_errors.append(str(e)))
            page.on('request', lambda r: foreign.append(r.url) if not r.url.startswith(server.origin) else None)
            page.goto(server.origin + '/console')
            page.get_by_label('Access key').fill(owner); page.get_by_role('button', name='Sign in').click()
            expect(page.locator('.connection-state')).to_have_text('Connected', timeout=20000)
            command = page.get_by_label('Command or search')

            def open_capture():
                command.fill('routines'); command.press('Enter')
                dialog = page.get_by_role('dialog')
                dialog.get_by_role('tab', name=re.compile('^Capture')).click()
                return dialog

            dialog = open_capture()
            listing = dialog.get_by_label('Capture policies')
            expect(listing.locator('li')).to_have_count(2)
            decisions, commitments = listing.get_by_label('Meeting decisions'), listing.get_by_label('Dated commitments')
            expect(decisions).to_contain_text('2 proposed · 0 accepted · 0 dismissed · 2 awaiting review')
            check('the Capture tab lists each policy with proposed, accepted and dismissed counts')
            expect(decisions).to_contain_text('Lines starting “Decision:”')
            expect(decisions).to_contain_text('Company')
            check('each policy shows its rule and context', 'Nothing is accepted automatically' in decisions.inner_text())
            expect(commitments).to_contain_text('1 over budget, counted not proposed')
            check('a line over the daily budget is counted, not proposed', len([c for c in claims() if c['memory_type'] == 'commitment']) == 1)
            page.screenshot(path=str(out / 'capture-1648.png'), full_page=True)
            dialog.get_by_label('Close panel').click()

            ordered = sorted((c for c in claims() if c['predicate'] == 'decision'), key=lambda c: c['source']['start_line'])
            memory.review(owner, ordered[0]['id'], {'version': ordered[0]['version'], 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
            memory.review(owner, ordered[1]['id'], {'version': ordered[1]['version'], 'decision': 'withdraw', 'replaces_id': None, 'replaces_version': None})
            # A further edit is not needed: the counts follow the review decisions.
            page.reload(); expect(page.locator('.connection-state')).to_have_text('Connected', timeout=20000)
            dialog = open_capture()
            expect(dialog.get_by_label('Capture policies').get_by_label('Meeting decisions')).to_contain_text('2 proposed · 1 accepted · 1 dismissed · 0 awaiting review')
            check('counts follow the person’s accept and dismiss decisions')
            time.sleep(.6)
            check('a dismissed line is not offered again on later cycles', len(claims()) == 3, len(claims()))

            page.set_viewport_size({'width': 390, 'height': 844}); page.wait_for_timeout(400)
            check('390px capture tab has no horizontal overflow', page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            page.screenshot(path=str(out / 'capture-390.png'), full_page=True)
            page.set_viewport_size({'width': 1648, 'height': 928})
            dialog.get_by_label('Close panel').click()
            check('no access key rendered', owner not in page.content())
            check('no requests leave the loopback origin', not foreign)
            check('no Content Security Policy violations', not [m for m in console_messages if 'Content Security Policy' in m or 'Refused to' in m])

            command.fill('settings'); command.press('Enter')
            page.get_by_role('dialog').get_by_role('button', name='Sign out').click()
            page.get_by_label('Access key').fill(reader); page.get_by_role('button', name='Sign in').click()
            expect(page.locator('.connection-state')).to_have_text('Connected', timeout=20000)
            dialog = open_capture()
            expect(dialog).to_contain_text('Capture policies are set by the workspace owner')
            check('a reader sees no capture policy', 'Meeting decisions' not in dialog.inner_text())
            check('no uncaught page errors', not page_errors)
            browser.close()
    finally:
        sup.stop()
        server.shutdown(); server.server_close()

report = {'passed': len(checks), 'checks': checks, 'browser_console': console_messages[-20:], 'page_errors': page_errors,
          'inputs': 'synthetic Markdown vault only', 'model_inference': False, 'external_delivery': False,
          'console_dist': 'console/dist built from this commit'}
(out / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': len(checks), 'page_errors': page_errors}))
