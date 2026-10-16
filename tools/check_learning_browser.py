"""Browser-to-backend acceptance for daily learning in the connected console (docs/AGENT_HUB.md, H3).

Follows tools/check_routines_browser.py: the real loopback ALFRED server over the synthetic
demo vault, the built console served from the same origin, real Chromium. Its small helpers are
repeated here rather than imported, because that script runs top to bottom on import. Requires
`npm run build` in console/ first. No model, account, device, network fetch or private data.

Synthetic evidence is made through ALFRED's own interfaces before the browser opens: three
drafts proposed from a synthetic event, each left to lapse, edited shorter and proposed again,
then approved. The server clock is the real clock plus a skew so drafts lapse without waiting.

Covers: the daily learning card with fixed delivery (proposals per run, no interrupt choice, no
quiet hours); authoring and running it; the trusted-kinds rule off by default, switched on for
one writing style category and audited; a run summary and outcome that name what was proposed
and accepted by the rule and that nothing was fetched or installed; today's list with every
proposal, its evidence and threshold; undoing the rule's acceptance; dismissing one item;
accepting the exact listed set in one action; the accepted learnings; proof that no grant,
policy, credential, device or other routine changed and that no draft text was stored; a
reader seeing none of it; layout at 390px. Screenshots and browser-report.json go to
docs/evidence/hub-learning/ (or ALFRED_LEARNING_OUTPUT).
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
from alfred import drafts
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'console' / 'dist'
out = Path(os.environ.get('ALFRED_LEARNING_OUTPUT', ROOT / 'docs' / 'evidence' / 'hub-learning'))
out.mkdir(parents=True, exist_ok=True)
checks, console_messages, page_errors, foreign = [], [], [], []
LONG = 'Hello team. The crew call has moved to Friday at nine. Please confirm by reply and bring the revised sheet.'
SHORT = 'Crew call moved to Friday 09:00. Please confirm.'


def check(name, condition=True, detail=None):
    assert condition, f'{name}: {detail}' if detail is not None else name
    checks.append(name)


def top(dialog):
    dialog.locator('.dialog-content').evaluate('e => { e.scrollTop = 0; }')


if not (DIST / 'index.html').is_file():
    raise SystemExit('Build the console first: cd console && npm run build')

with tempfile.TemporaryDirectory() as temp:
    home = Path(temp) / 'demo'; keys = init_demo(home)
    skew = [0]
    store = KnowledgeStore(home / 'desk.sqlite', clock=lambda: time.time() + skew[0])
    now = int(store.now())
    (home / 'project' / 'learning-brief.json').write_text(json.dumps({
        'document_id': 'learning-brief', 'title': 'Learning brief', 'revision': 1, 'observed_at': now - 10,
        'expires_at': now + 6 * 86400, 'summary': 'Synthetic crew call change.'}))
    sup = KnowledgeSupervisor(store, keys['owner'], keys['source'], home / 'project', vault=home / 'vault', interval=.2)
    sup.cycle(); sup.start()
    server = DeskHTTPServer(store, sup, port=0, console_dist=DIST)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); thread.start()
    owner, reader = keys['owner'], keys['reader']
    event = next(e['seq'] for e in store.desk_state(owner)['events'] if 'Learning brief' in json.dumps(e))

    # Synthetic evidence through ALFRED's own interfaces: propose, lapse, edit shorter, propose again, approve.
    for n in range(3):
        first = store.propose_from_evidence(owner, {'event_seq': event, 'text': LONG, 'request_id': f'learn-draft-{n}'})
        skew[0] += 901
        fresh = drafts.repropose(store, owner, first['id'], {'version': 1, 'request_id': f'learn-again-{n}', 'text': SHORT})
        store.approve(owner, fresh['id'], fresh['fingerprint'])
        skew[0] += 5

    def table(sql):
        with store.connection() as db:
            return [tuple(r) for r in db.execute(sql)]

    def authority():
        return {'grants': table('SELECT * FROM source_grants'), 'policy': table('SELECT * FROM source_policy'),
                'credentials': table('SELECT id,role,revoked,expires FROM credentials ORDER BY id'),
                'devices': table('SELECT credential,person FROM identity_devices ORDER BY credential'),
                'other_routines': table("SELECT * FROM routine_settings WHERE kind!='daily-learning'")}

    def audits(kind):
        return table(f"SELECT count(*) FROM audit WHERE kind='{kind}'")[0][0]

    before = authority()

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
            expect(page.locator('.connection-state')).to_have_text('Connected')
            check('owner signs in to the connected console')
            command = page.get_by_label('Command or search')

            def open_routines(tab=None):
                command.fill('routines'); command.press('Enter')
                dialog = page.get_by_role('dialog')
                expect(dialog.get_by_role('tab', name=re.compile('^Routines'))).to_be_visible()
                if tab:
                    dialog.get_by_role('tab', name=re.compile('^' + tab)).click()
                return dialog

            # 1. The routine card: owner authored, fixed delivery.
            dialog = open_routines()
            card = dialog.get_by_role('article', name='Daily learning')
            check('daily learning is off until the owner sets it up', card.locator('.routine-chips').inner_text().strip().upper() == 'NOT SET UP')
            form = card.get_by_role('form', name='Daily learning settings')
            check('the card asks for proposals per run, with no interrupt choice, drafts or quiet hours',
                  form.get_by_label('Proposals per run').count() == 1 and form.locator('.routine-interrupt').count() == 0
                  and form.locator('.routine-quiet').count() == 0)
            card.locator('summary').click()
            rules = card.locator('.routine-rules').inner_text()
            check('the stated rules say learning never changes authority and fetches nothing',
                  'never changes policy, grants, scopes, autonomy levels, budgets' in rules and 'Nothing is fetched or installed' in rules)
            form.get_by_label('Local time offset').select_option(label='UTC+00:00')
            form.get_by_label('Proposals per run').fill('10')
            form.get_by_role('button', name='Save settings').click()
            expect(page.locator('.toast')).to_contain_text('Daily learning settings saved')
            saved = next(r for r in server.routines.view(owner)['routines'] if r['kind'] == 'daily-learning')
            check('the saved settings are what the owner chose, with fixed delivery',
                  saved['enabled'] and saved['settings']['nominations_per_run'] == 10 and saved['settings']['interrupt'] == 'show_now'
                  and saved['settings']['propose_drafts'] is False and saved['settings']['schedule'] == {'daily_at': '21:00'})

            # 2. The trusted-kinds rule: off by default, owner switches it on for one style category.
            dialog.get_by_role('tab', name=re.compile('^Learning')).click()
            panel = dialog.get_by_role('tabpanel')
            expect(panel).to_contain_text('Your trusted-kinds rule')
            check('the rule is off by default', 'Off. Every learning waits for your review.' in panel.inner_text())
            rule_form = panel.get_by_role('form', name='Trusted-kinds rule')
            check('only writing style and presentation can be named', rule_form.get_by_role('checkbox').count() == 2)
            rule_form.get_by_label('Writing style: how long your drafts are').check()
            rule_form.get_by_role('button', name='Switch rule on').click()
            expect(page.locator('.toast')).to_contain_text('Your trusted-kinds rule is on')
            expect(panel).to_contain_text('On (version 1) for: Writing style: how long your drafts are')
            check('switching the rule on is audited', audits('learning.trust_rule_created') == 1)

            # 3. Run now, then the run's summary and outcome.
            dialog.get_by_role('tab', name=re.compile('^Routines')).click()
            dialog.get_by_role('article', name='Daily learning').get_by_role('button', name='Run now').click()
            expect(page.locator('.toast')).to_contain_text('Daily learning ran')
            dialog.get_by_role('tab', name=re.compile('^Runs')).click()
            first = dialog.locator('.run-row').first
            expect(first).to_contain_text('Learning run · 3 learnings for your review · 1 accepted by your rule')
            first.get_by_role('button').click()
            detail = first.locator('.run-detail').inner_text()
            check('the run states what it proposed, its budget, the upstream result and that no model or authority was involved',
                  '4 · 1 accepted by your rule' in detail and 'up to 10 per run' in detail and 'nothing fetched or installed' in detail
                  and 'No model was used' in detail and 'Learning changes no policy, grant, scope, autonomy level or budget' in detail)
            stored = table("SELECT outcome FROM routine_runs WHERE kind='daily-learning'")[0][0]
            check('no draft text is stored in the run or the proposals',
                  'crew call' not in stored.lower() and not any('crew call' in str(r).lower() for r in table('SELECT * FROM learning_proposals')))
            page.screenshot(path=str(out / 'learning-run.png'))

            # 4. Today's list.
            dialog.get_by_role('tab', name=re.compile('^Learning')).click()
            today = panel.get_by_label("Today's learnings")
            expect(today.locator('.nomination-row')).to_have_count(4)
            check("today's list counts what was proposed and what the rule accepted",
                  '4 proposed on ' in panel.inner_text() and '3 awaiting your review · 1 accepted by your rule' in panel.inner_text())
            length = today.get_by_role('listitem', name=re.compile('^Writing style'))
            check('the rule acceptance is labelled, can be undone and shows its evidence against the threshold',
                  'Accepted by your rule · you can undo this' in length.inner_text()
                  and 'Preference · from your records · 3 pieces of evidence, at least 3 needed' in length.inner_text())
            procedure = today.get_by_role('listitem', name=re.compile('^A sequence of steps'))
            check('a procedure is proposed for review and is never accepted by the rule',
                  'Awaiting your review' in procedure.inner_text() and 'Procedure draft' in procedure.inner_text())
            page.screenshot(path=str(out / 'learning-list.png'))

            length.get_by_role('button', name='Undo').click()
            expect(page.locator('.toast')).to_contain_text('Undone. It is back for your review.')
            length = today.get_by_role('listitem', name=re.compile('^Writing style'))
            expect(length).to_contain_text('Back for your review after you undid your rule')
            check('undo is audited and nothing accepted by the rule remains current',
                  audits('learning.undone') == 1 and table("SELECT count(*) FROM learning_records WHERE state='current'") == [(0,)])

            lapse = today.get_by_role('listitem', name=re.compile('^Whether drafts lapse'))
            lapse.get_by_role('button', name='Dismiss').click()
            expect(page.locator('.toast')).to_contain_text('Learning dismissed')
            expect(today.get_by_role('listitem', name=re.compile('^Whether drafts lapse'))).to_contain_text('Dismissed')
            check('a dismissal is audited', audits('learning.dismissed') == 1)

            accept = panel.get_by_role('button', name='Accept these 3')
            expect(accept).to_be_visible()
            accept.click()
            expect(page.locator('.toast')).to_contain_text('The listed learnings were accepted.')
            accepted = panel.get_by_label('Accepted learnings')
            expect(accepted.locator('li')).to_have_count(3)
            check('the exact listed set is accepted in one audited action',
                  audits('learning.batch_accepted') == 1 and table("SELECT count(*) FROM learning_records WHERE state='current'") == [(3,)]
                  and table("SELECT count(*) FROM learning_proposals WHERE state='suggested'") == [(0,)])
            check('accepted learnings say who accepted them and which may be sent as context',
                  'accepted by you' in accepted.inner_text() and 'may be sent to a brain as context' in accepted.inner_text())
            page.screenshot(path=str(out / 'learning-accepted.png'))
            dialog.get_by_role('tab', name=re.compile('^Procedures')).click()
            learned = dialog.get_by_label('Learned procedure drafts')
            expect(learned.locator('li')).to_have_count(1)
            check('the accepted procedure draft is in the procedure registry, labelled never run',
                  'accepted · version 1 · current' in learned.inner_text().lower() and 'never run · grants nothing' in learned.inner_text().lower(),
                  learned.inner_text())
            dialog.get_by_role('tab', name=re.compile('^Learning')).click()
            check('no grant, policy, credential, device or other routine changed', authority() == before)

            # 5. Layout at a narrow width.
            page.set_viewport_size({'width': 390, 'height': 844}); page.wait_for_timeout(500); top(dialog)
            check('390px learning view has no horizontal overflow', page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            outside = page.evaluate('''() => {
                const d = document.querySelector('dialog.dialog'), c = d.querySelector('.dialog-content'), box = d.getBoundingClientRect();
                const bad = [...d.querySelectorAll('select,input,textarea,button')].filter(e => {
                  const b = e.getBoundingClientRect(); return b.width !== 0 && (b.left < box.left - 1 || b.right > box.right + 1); });
                return (c.scrollWidth > c.clientWidth + 1 ? ['content ' + c.scrollWidth + '>' + c.clientWidth] : [])
                  .concat(bad.map(e => e.tagName + ' ' + (e.getAttribute('aria-label') || e.textContent || e.type).slice(0, 40))); }''')
            check('390px every control stays inside the dialog', not outside, outside)
            page.screenshot(path=str(out / 'learning-390.png'), full_page=True)
            page.set_viewport_size({'width': 1648, 'height': 928})
            dialog.get_by_label('Close panel').click()

            check('no browser storage used', page.evaluate('localStorage.length===0&&sessionStorage.length===0'))
            check('no access key rendered', owner not in page.content())
            csp = [m for m in console_messages if 'Content Security Policy' in m or 'Refused to' in m]
            check('no Content Security Policy violations', not csp)
            check('no requests leave the loopback origin', not foreign)
            check('no uncaught page errors', not page_errors)

            # 6. A reader sees none of the owner's learnings and cannot decide anything.
            command.fill('settings'); command.press('Enter')
            page.get_by_role('dialog').get_by_role('button', name='Sign out').click()
            page.get_by_label('Access key').fill(reader); page.get_by_role('button', name='Sign in').click()
            expect(page.locator('.connection-state')).to_have_text('Connected')
            dialog = open_routines('Learning')
            panel = dialog.get_by_role('tabpanel')
            expect(panel).to_contain_text('No accepted learnings yet.')
            check("a reader sees none of the owner's learnings and no decision buttons",
                  'Writing style' not in panel.inner_text() and panel.get_by_role('button', name=re.compile('^(Accept|Dismiss|Undo|Retire)')).count() == 0
                  and panel.get_by_role('form', name='Trusted-kinds rule').count() == 0)
            check('the reader page has no uncaught errors', not page_errors)
            browser.close()
    finally:
        sup.stop()
        server.shutdown(); server.server_close()

report = {'passed': len(checks), 'checks': checks, 'browser_console': console_messages[-20:], 'page_errors': page_errors,
          'inputs': 'synthetic demo vault and one synthetic event only', 'model_inference': False, 'network_fetch': False,
          'external_delivery': False, 'console_dist': 'console/dist built from this commit'}
(out / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': len(checks), 'page_errors': page_errors}))
