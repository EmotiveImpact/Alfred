"""Browser-to-backend acceptance for reviewed-memory time, disputes and supersession (MEM-007).

Follows tools/check_console_connected_browser.py: the real loopback ALFRED server over the
synthetic demo vault, the built console served from the same origin, real Chromium. That
script runs top to bottom on import, so its two small helpers are repeated here rather than
imported. Requires `npm run build` in console/ first. No model, account or private data.

The server's clock is the real clock plus an offset this script sets, so that the setup can
record reviews on earlier days for the as-of view; every browser step runs at offset zero.
One statement has its history rows removed before the server starts, so the server migrates
it as a statement that predates recorded history.

Covers the review queue (accept with a valid period, supersede choosing the replaced
statement, dispute, withdraw, a stale version refused), namesakes kept apart, the inspector's
lineage, conflicts, disputes and recorded history, the as-of report on three dates and with a
separate valid date, current answers unchanged, withheld values hidden in history and the
as-of report, forgetting leaving no value in history, and a reader seeing nothing. Screenshots
and browser-report.json go to docs/evidence/temporal-review/ (or ALFRED_TEMPORAL_OUTPUT).
"""
import datetime
import json
import os
import re
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer
from alfred.reviewed_memory import ReviewedMemory
from alfred.policy import IdentityPolicy
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'console' / 'dist'
out = Path(os.environ.get('ALFRED_TEMPORAL_OUTPUT', ROOT / 'docs' / 'evidence' / 'temporal-review'))
out.mkdir(parents=True, exist_ok=True)
checks, console_messages, page_errors, foreign = [], [], [], []
DAY = 86400


def check(name, condition=True):
    assert condition, name
    checks.append(name)


def open_history(statement):
    """Opens a statement's recorded history unless it is already open. The inspector keeps what
    the person opened through a data refresh, so a second click would close it again."""
    if not statement.locator('details.statement-history').evaluate('d => d.open'):
        statement.locator('summary', has_text='History and lineage').click()


def note(store, bearer, title):
    return next(n for n in store.knowledge(bearer)['nodes'] if n['title'] == title)


def day(offset):
    """A UTC calendar day as the browser's date input expects it; the browser runs in UTC too."""
    return (datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=offset)).isoformat()


def midnight(offset):
    return int(datetime.datetime.combine(datetime.date.fromisoformat(day(offset)), datetime.time(), datetime.timezone.utc).timestamp())


if not (DIST / 'index.html').is_file():
    raise SystemExit('Build the console first: cd console && npm run build')

with tempfile.TemporaryDirectory() as temp:
    home = Path(temp) / 'demo'; keys = init_demo(home)
    offset = [0]
    store = KnowledgeStore(home / 'desk.sqlite', clock=lambda: time.time() + offset[0])
    sup = KnowledgeSupervisor(store, keys['owner'], keys['source'], home / 'project', vault=home / 'vault', interval=.2)
    sup.cycle()
    owner, reader = keys['owner'], keys['reader']
    setup = ReviewedMemory(store)
    film, producer, coordinator = (note(store, owner, t) for t in ('Sample film', 'Sample producer', 'Sample coordinator'))
    for identity, kind, name in (('film', 'project', 'Sample film'), ('producer', 'person', 'Sample producer'),
                                 ('producer-b', 'person', 'Sample producer'), ('coordinator', 'person', 'Sample coordinator')):
        setup.create_entity(owner, {'id': identity, 'kind': kind, 'name': name})

    def propose(request, subject, predicate, line_note, value=None, obj=None, capture=False):
        body = {'request_id': request, 'subject_id': subject, 'predicate': predicate, 'object_id': obj, 'value': value,
                'valid_from': None, 'valid_until': None,
                'evidence': {'note_id': line_note['id'], 'sha256': line_note['sha256'], 'revision': line_note['revision'], 'start_line': 8, 'end_line': 8}}
        if capture:
            return setup.capture(owner, body | {'memory_type': 'commitment', 'retention_days': None, 'captured_from': {'note_id': line_note['id']}})['id']
        return setup.propose(owner, body)['id']

    def version(identity):
        return next(c for c in setup.view(owner)['claims'] if c['id'] == identity)['version']

    def decide(identity, decision, replaces=None):
        setup.review(owner, identity, {'version': version(identity), 'decision': decision, 'replaces_id': replaces,
                                       'replaces_version': version(replaces) if replaces else None})

    def at(days):
        offset[0] = days * DAY

    # Earlier days, recorded through the real service with the clock moved back.
    at(-25); legacy = propose('l1', 'producer-b', 'status', producer, 'on leave')
    at(-24); decide(legacy, 'accept')
    at(-20); first = propose('s1', 'film', 'status', film, 'in development')
    at(-19); decide(first, 'accept')
    at(-15); lead = propose('r1', 'film', 'responsible_person', producer, obj='producer'); decide(lead, 'accept')
    at(-12); second = propose('s2', 'film', 'status', film, 'in pre-production')
    at(-10); decide(second, 'supersede', first)
    at(-8); on_set = propose('a1', 'producer', 'status', producer, 'on set'); decide(on_set, 'accept')
    at(-6); rival = propose('r2', 'film', 'responsible_person', coordinator, obj='coordinator'); decide(rival, 'accept')
    # Today: proposals waiting for review, one of them captured with "Remember this".
    at(0)
    scheduled = propose('p1', 'film', 'scheduled_for', film, 'first week of November', capture=True)
    production = propose('p2', 'film', 'status', film, 'in production')
    unavailable = propose('p3', 'producer-b', 'status', producer, 'unavailable')
    reviewing = propose('p4', 'coordinator', 'status', coordinator, 'reviewing equipment')
    opening = propose('p5', 'film', 'decision', film, 'monochrome opening')
    # The legacy statement predates recorded history: the server migrates it on start.
    with store.connection() as db:
        db.execute('DELETE FROM memory_claim_history WHERE claim_id=?', (legacy,))
        db.execute('DELETE FROM memory_history_meta')
    sup.start()
    server = DeskHTTPServer(store, sup, port=0, console_dist=DIST)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); thread.start()
    memory = server.memory

    def claim(identity):
        return next(c for c in memory.view(owner)['claims'] if c['id'] == identity)

    def history_rows():
        con = sqlite3.connect(home / 'desk.sqlite')
        try:
            return [tuple(r) for r in con.execute('SELECT * FROM memory_claim_history')]
        finally:
            con.close()

    check('the server migrated the statement that predates history, from its own earlier records',
          [(r[4], r[8]) for r in history_rows() if r[3] == legacy] == [('proposed', 'migrated'), ('accepted', 'migrated')])

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

            def open_memory(tab=None):
                command.fill('memory'); command.press('Enter')
                dialog = page.get_by_role('dialog')
                expect(dialog.get_by_role('heading', name='Reviewed memory')).to_be_visible()
                if tab:
                    dialog.get_by_role('tab', name=tab).click()
                return dialog

            def card(dialog, label):
                return dialog.get_by_role('article', name=re.compile('^' + re.escape(label)))

            # Review queue.
            dialog = open_memory()
            expect(dialog.locator('.review-card')).to_have_count(5, timeout=15000)
            check('the review queue lists the five proposals, oldest first',
                  dialog.locator('section[aria-label="Proposed statements"] h3').inner_text().endswith('5'))
            check('a captured proposal shows its source lines and memory type',
                  'The fictional production' in card(dialog, 'Proposed: Sample film scheduled for').inner_text()
                  and 'commitment' in card(dialog, 'Proposed: Sample film scheduled for').inner_text())
            namesake = card(dialog, 'Proposed: Sample producer status')
            check('a namesake is labelled by identifier and kept separate',
                  'Sample producer (person, record producer-b)' in namesake.inner_text() and 'kept separate' in namesake.inner_text())
            page.screenshot(path=str(out / 'temporal-queue.png'))
            # Accept with a valid period.
            scheduled_card = card(dialog, 'Proposed: Sample film scheduled for')
            scheduled_card.get_by_label('Holds from').fill(day(0)); scheduled_card.get_by_label('Holds until').fill(day(30))
            scheduled_card.get_by_role('button', name='Accept', exact=True).click()
            expect(page.get_by_role('status').filter(has_text='Accepted as your reviewed statement')).to_be_visible()
            expect(dialog.locator('.review-card')).to_have_count(4, timeout=15000)
            made = claim(scheduled)
            check('accepting records the chosen valid period on the server',
                  (made['state'], made['valid_from'], made['valid_until']) == ('accepted', midnight(0), midnight(30)))
            # Supersede: only the same record and statement kind can be chosen, never the namesake's.
            namesake.get_by_role('button', name='Replace an earlier statement…').click()
            options = namesake.get_by_label('Replaces').locator('option').all_inner_texts()
            check('the replacement choice lists only the same record, not its namesake',
                  any('on leave' in o for o in options) and not any('on set' in o for o in options))
            namesake.get_by_role('button', name='Cancel replacement').click()
            namesake.get_by_role('button', name='Dispute').click()
            expect(page.get_by_role('status').filter(has_text='Disputed')).to_be_visible()
            production_card = card(dialog, 'Proposed: Sample film status')
            production_card.get_by_role('button', name='Replace an earlier statement…').click()
            choices = production_card.get_by_label('Replaces').locator('option').all_inner_texts()
            check('the replacement choice lists the accepted statement and not the superseded one',
                  any('in pre-production' in o for o in choices) and not any('in development' in o for o in choices))
            production_card.get_by_label('Replaces').select_option(label=next(o for o in choices if 'in pre-production' in o))
            page.screenshot(path=str(out / 'temporal-supersede.png'))
            production_card.get_by_role('button', name='Accept as replacement').click()
            expect(page.get_by_role('status').filter(has_text='Accepted as the replacement')).to_be_visible()
            expect(dialog.locator('section[aria-label="Proposed statements"] .review-card')).to_have_count(2, timeout=15000)
            check('supersession is recorded with its lineage',
                  claim(production)['replaces_id'] == second and claim(second)['state'] == 'superseded' and claim(production)['usable'])
            card(dialog, 'Proposed: Sample coordinator status').get_by_role('button', name='Withdraw').click()
            expect(page.get_by_role('status').filter(has_text='Withdrawn')).to_be_visible()
            expect(dialog.locator('section[aria-label="Proposed statements"] .review-card')).to_have_count(1, timeout=15000)
            check('withdrawing keeps the statement as withdrawn', claim(reviewing)['state'] == 'withdrawn')
            # A decision against a version that changed underneath is refused.
            def changed_underneath(route):
                memory.review(owner, opening, {'version': 1, 'decision': 'dispute', 'replaces_id': None, 'replaces_version': None})
                route.continue_()
            page.route(f'**/desk/memory/claims/{opening}/review', changed_underneath)
            card(dialog, 'Proposed: Sample film decision').get_by_role('button', name='Accept', exact=True).click()
            expect(dialog.get_by_role('alert').filter(has_text='changed since you opened it')).to_be_visible(timeout=15000)
            page.screenshot(path=str(out / 'temporal-stale.png'))
            page.unroute(f'**/desk/memory/claims/{opening}/review')
            check('a stale version is refused and nothing is accepted', claim(opening)['state'] == 'disputed')
            expect(dialog.locator('section[aria-label="Disputed statements"] .review-card')).to_have_count(2, timeout=15000)
            check('the queue refreshes to show disputed statements separately')
            page.keyboard.press('Escape')

            # Inspector: lineage, conflicts, disputes and recorded history.
            command.fill('search Sample film'); command.press('Enter')
            page.get_by_role('dialog').locator('.record-row').filter(has_text='reviewed statement').click()
            inspector = page.get_by_role('complementary', name='Record inspector')
            expect(inspector).to_contain_text('REVIEWED MEMORY · YOUR JUDGEMENT')

            def statement(text):
                return inspector.locator('.statement').filter(has_text=re.compile('^' + re.escape(text)))
            expect(statement('status in production')).to_contain_text('Replaces “in pre-production” (superseded)', timeout=15000)
            expect(statement('status in pre-production')).to_contain_text('Replaced by “in production” (accepted)')
            check('the inspector shows the lineage both ways')
            expect(statement('responsible person Sample coordinator')).to_contain_text('Conflicts with 1 other accepted statement')
            expect(statement('responsible person Sample producer')).to_contain_text('Conflicts with 1 other accepted statement')
            check('the inspector shows a conflict between two accepted statements')
            expect(statement('scheduled for first week of November')).to_contain_text('Holds from')
            check('the inspector shows the valid period')
            page.screenshot(path=str(out / 'temporal-inspector.png'))
            statement('responsible person Sample coordinator').get_by_role('button', name='Dispute').click()
            expect(statement('responsible person Sample coordinator')).to_contain_text('You disputed this statement', timeout=15000)
            expect(statement('responsible person Sample producer')).not_to_contain_text('Conflicts with')
            check('disputing from the inspector resolves the conflict for current use', claim(lead)['usable'] and claim(rival)['state'] == 'disputed')
            older = statement('status in pre-production')
            open_history(older)
            expect(older.locator('.history-list li')).to_have_count(3, timeout=15000)
            items = older.locator('.history-list li').all_inner_texts()
            check('recorded history lists each transition with time and reviewer',
                  items[0].startswith('Proposed') and items[1].startswith('Accepted') and 'as a replacement' in items[1]
                  and items[2].startswith('Superseded') and all('by you' in i for i in items))
            check('the history view names lineage without copying values into history', 'Replaced by' in older.inner_text())
            page.screenshot(path=str(out / 'temporal-history.png'))
            statement('responsible person Sample coordinator').get_by_role('button', name='Decide in the review queue').click()
            dialog = page.get_by_role('dialog')
            disputed = card(dialog, 'Disputed: Sample film responsible person')
            disputed.get_by_role('button', name='Withdraw').click()
            expect(page.get_by_role('status').filter(has_text='Withdrawn')).to_be_visible()
            check('a disputed statement is decided again from the queue', claim(rival)['state'] == 'withdrawn')

            # As of a date: recorded time and valid time, from history alone.
            dialog.get_by_role('tab', name='As of a date').click()

            def as_of(held_on, valid_on=''):
                dialog.get_by_label('Held on').fill(held_on); dialog.get_by_label('Valid on').fill(valid_on)
                dialog.get_by_role('button', name='Show what I held').click()
                report = dialog.get_by_label('Historical report')
                chosen = datetime.date.fromisoformat(held_on)
                expect(report).to_contain_text(re.compile(rf'Held on {chosen.day} \w+ {chosen.year}'), timeout=15000)
                return report
            report = as_of(day(-16))
            text = report.inner_text()
            check('the report is labelled as ALFRED records, not a claim about the world',
                  "ALFRED's own review records" in text and 'not a statement about what was true in the world' in text)
            check('sixteen days ago: the first status and the migrated statement were held',
                  'in development' in text and 'on leave' in text and 'in pre-production' not in text and 'responsible person' not in text)
            report = as_of(day(-5))
            text = report.inner_text()
            check('five days ago: the replacement status was held, and the earlier one superseded',
                  'in pre-production' in text and 'in development' not in text and '1 superseded' in text)
            check('five days ago: the two responsible people conflicted under the single-value rule',
                  text.count('Conflicted then with 1 other accepted statement') == 2)
            page.screenshot(path=str(out / 'temporal-asof-past.png'))
            report = as_of(day(0))
            text = report.inner_text()
            check('today: the current statements and the new valid period',
                  'in production' in text and 'first week of November' in text and 'Sample coordinator' not in text and 'Conflicted' not in text)
            page.screenshot(path=str(out / 'temporal-asof-today.png'))
            report = as_of(day(0), day(40))
            outside = report.locator('h3', has_text='outside their valid period')
            expect(outside).to_be_visible()
            check('a separate valid date moves a statement outside its valid period', 'first week of November' in report.inner_text())
            page.keyboard.press('Escape')

            # Current answers still use only accepted, current, authorised and valid statements.
            command.fill('What is the Sample film status?'); command.press('Enter')
            ask = page.get_by_role('dialog')
            reviewed = ask.locator('.ask-section').filter(has_text='Your reviewed statements')
            expect(reviewed).to_be_visible(timeout=15000)
            check('current answers use the current statement only',
                  'in production' in reviewed.inner_text() and 'in pre-production' not in reviewed.inner_text() and 'in development' not in reviewed.inner_text())
            page.keyboard.press('Escape')

            # Withheld: losing access hides values in history and the as-of report, without invalidating.
            policy = IdentityPolicy(store)
            policy.enable(owner, policy.view(owner)['epoch'])
            expect(page.locator('.toast')).to_contain_text('Access changed', timeout=15000)
            dialog = open_memory('As of a date')
            report = as_of(day(-16))
            text = report.inner_text()
            check('withheld values are hidden in the as-of report',
                  'Value withheld' in text and 'in development' not in text and 'on leave' not in text)
            dialog.get_by_role('tab', name='Review queue').click()
            expect(dialog.locator('.review-card').first).to_contain_text('cannot be decided until access returns', timeout=15000)
            check('withheld proposals cannot be decided and show no value',
                  'monochrome opening' not in dialog.inner_text() and dialog.get_by_role('button', name='Accept', exact=True).count() == 0)
            page.screenshot(path=str(out / 'temporal-withheld.png'))
            page.keyboard.press('Escape')
            command.fill('search Sample film'); command.press('Enter')
            page.get_by_role('dialog').locator('.record-row').filter(has_text='Sample film').filter(has_text='withheld').click()
            expect(inspector.locator('.statement').first).to_be_visible(timeout=15000)
            target = inspector.locator('.statement').filter(has=page.locator('.statement-temporal', has_text='Replaced by')).first
            open_history(target)
            expect(target.locator('.history-list')).to_contain_text('Support unavailable or not permitted', timeout=15000)
            check('history notes that ALFRED saw the support become unavailable, as an observation',
                  'noticed by ALFRED' in target.inner_text())
            check('no withheld value is visible anywhere on the page',
                  all(v not in page.locator('body').inner_text() for v in ('in development', 'in pre-production', 'in production', 'on leave')))
            check('withheld is not invalidated', {claim(first)['state'], claim(second)['state'], claim(production)['state']} == {'superseded', 'accepted'})
            expect(page.locator('.toast')).to_be_hidden(timeout=15000)
            policy.grant(owner, 'demo-source', 'read', int(time.time()) + 3600, policy.view(owner)['epoch'])
            expect(page.locator('.toast')).to_contain_text('Access changed', timeout=15000)
            command.fill('search Sample film'); command.press('Enter')
            page.get_by_role('dialog').locator('.record-row').filter(has_text='reviewed statement').click()
            expect(statement('status in development')).to_be_visible(timeout=15000)
            older = statement('status in development')
            open_history(older)
            expect(older.locator('.history-list')).to_contain_text('Support readable again', timeout=15000)
            check('restored access restores values and records that support is readable again')

            # Forgetting: history keeps identifiers, states and times, never the value.
            older.get_by_role('button', name='Forget this statement').click()
            inspector.get_by_role('button', name='Confirm forget').click()
            expect(page.get_by_role('status').filter(has_text='Not secure erasure')).to_be_visible()
            forgotten = inspector.locator('.statement').filter(has_text='Forgotten · value removed')
            expect(forgotten).to_have_count(1, timeout=15000)
            open_history(forgotten)
            expect(forgotten.locator('.history-list li').last).to_contain_text('Forgotten', timeout=15000)
            check('the forget is recorded in history by you', 'by you' in forgotten.locator('.history-list li').last.inner_text())
            page.screenshot(path=str(out / 'temporal-forgotten.png'))
            dialog = open_memory('As of a date')
            report = as_of(day(-16))
            check('the as-of report says the value was removed rather than showing it',
                  'Value removed: you forgot this statement' in report.inner_text() and 'in development' not in page.locator('body').inner_text())
            check('no reviewed value is stored in the history table',
                  not any(v in str(history_rows()) for v in ('in development', 'in production', 'on leave', 'first week', 'monochrome')))
            for width, height in ((1280, 800), (390, 844)):
                page.set_viewport_size({'width': width, 'height': height}); page.wait_for_timeout(400)
                for tab in ('Review queue', 'As of a date'):
                    dialog.get_by_role('tab', name=tab).click(); page.wait_for_timeout(200)
                    if tab == 'As of a date':
                        as_of(day(-5))
                    check(f'{width}px {tab.lower()} has no horizontal overflow', page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                    check(f'{width}px {tab.lower()} keeps every control inside the dialog', page.evaluate('''() => {
                        const d = document.querySelector('dialog.dialog'), c = d.querySelector('.dialog-content'), box = d.getBoundingClientRect();
                        return c.scrollWidth <= c.clientWidth + 1 && [...d.querySelectorAll('select,input,textarea,button')].every(e => {
                          const b = e.getBoundingClientRect(); return b.width === 0 || (b.left >= box.left - 1 && b.right <= box.right + 1); }); }'''))
                page.screenshot(path=str(out / f'temporal-{width}.png'), full_page=True)
            page.set_viewport_size({'width': 1648, 'height': 928})
            page.keyboard.press('Escape')

            # A reader sees none of the owner's statements or history.
            command.fill('settings'); command.press('Enter')
            page.get_by_role('dialog').get_by_role('button', name='Sign out').click()
            page.get_by_label('Access key').fill(reader); page.get_by_role('button', name='Sign in').click()
            expect(page.locator('.connection-state')).to_have_text('Connected')
            dialog = open_memory()
            expect(dialog).to_contain_text('Only the owner who proposed a statement can review it.', timeout=15000)
            check('a reader has nothing to review', dialog.locator('.review-card').count() == 0)
            dialog.get_by_role('tab', name='As of a date').click()
            report = as_of(day(-5))
            check('a reader sees no owner statement in the as-of report', 'No accepted statement was valid then.' in report.inner_text()
                  and 'in pre-production' not in page.locator('body').inner_text())
            check('no browser storage used', page.evaluate('localStorage.length===0&&sessionStorage.length===0'))
            check('no access key rendered', owner not in page.content() and reader not in page.content())
            csp = [m for m in console_messages if 'Content Security Policy' in m or 'Refused to' in m]
            check('no Content Security Policy violations', not csp)
            check('no requests leave the loopback origin', not foreign)
            check('no uncaught page errors', not page_errors)
            browser.close()
    finally:
        sup.stop()
        server.shutdown(); server.server_close()

report = {'passed': len(checks), 'checks': checks, 'browser_console': console_messages[-20:], 'page_errors': page_errors,
          'inputs': 'synthetic Markdown vault only; server clock offset during setup only', 'model_inference': False,
          'console_dist': 'console/dist built from this commit'}
(out / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': len(checks), 'page_errors': page_errors}))
