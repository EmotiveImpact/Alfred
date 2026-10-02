"""Browser-to-backend acceptance for executive workflows in the connected console (ATT-002, ATT-001).

Follows tools/check_console_connected_browser.py: the real loopback ALFRED server over the
synthetic demo vault, the built console served from the same origin, real Chromium. That
script runs top to bottom on import, so its two small helpers are repeated here rather
than imported. Requires `npm run build` in console/ first. No model, account or private data.

Covers responsible labels and explicit links, namesake separation, decision options with
decide and reopen, an assembled brief that changes with its sources and drops what the
caller can no longer read, milestone progress, attention with snooze, and derived insights.
Screenshots and browser-report.json go to docs/evidence/executive-2/ (or
ALFRED_EXECUTIVE_OUTPUT).
"""
import datetime
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
from alfred.executive import ExecutiveRecords
from alfred.policy import IdentityPolicy
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'console' / 'dist'
out = Path(os.environ.get('ALFRED_EXECUTIVE_OUTPUT', ROOT / 'docs' / 'evidence' / 'executive-2'))
out.mkdir(parents=True, exist_ok=True)
checks, console_messages, page_errors, foreign = [], [], [], []


def check(name, condition=True):
    assert condition, name
    checks.append(name)


def note(store, bearer, title):
    return next(n for n in store.knowledge(bearer)['nodes'] if n['title'] == title)


def day(offset):
    return (datetime.date.today() + datetime.timedelta(days=offset)).isoformat()


def expand(dialog, title):
    """Open one record's details without toggling it closed if it is already open."""
    button = dialog.get_by_role('button', name=f'Details for {title}')
    if button.get_attribute('aria-expanded') != 'true':
        button.click()
    expect(button).to_have_attribute('aria-expanded', 'true')
    return dialog.locator('.record-editor')


def top(dialog):
    dialog.locator('.dialog-content').evaluate('e => { e.scrollTop = 0; }')


if not (DIST / 'index.html').is_file():
    raise SystemExit('Build the console first: cd console && npm run build')

with tempfile.TemporaryDirectory() as temp:
    home = Path(temp) / 'demo'; keys = init_demo(home)
    store = KnowledgeStore(home / 'desk.sqlite')
    sup = KnowledgeSupervisor(store, keys['owner'], keys['source'], home / 'project', vault=home / 'vault', interval=.2)
    sup.cycle(); sup.start()
    server = DeskHTTPServer(store, sup, port=0, console_dist=DIST)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); thread.start()
    memory, records = ReviewedMemory(store), ExecutiveRecords(store)
    owner = keys['owner']
    # A reviewed statement supported by the project note, and a reviewed namesake of an authored person note.
    film = note(store, owner, 'Sample film')
    memory.create_entity(owner, {'id': 'film', 'kind': 'project', 'name': 'Sample film'})
    memory.create_entity(owner, {'id': 'producer', 'kind': 'person', 'name': 'Sample producer'})
    status = memory.propose(owner, {'request_id': 's1', 'subject_id': 'film', 'predicate': 'status', 'object_id': None, 'value': 'in pre-production',
                                    'valid_from': None, 'valid_until': None,
                                    'evidence': {'note_id': film['id'], 'sha256': film['sha256'], 'revision': film['revision'], 'start_line': 8, 'end_line': 8}})
    memory.review(owner, status['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})

    def mine(title):
        return next(r for r in records.view(owner)['records'] if r['title'] == title)

    def people_count():
        with store.connection() as db:
            return [db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('credentials', 'identity_devices')]

    identities = people_count()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'), headless=True,
                                        args=['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            context = browser.new_context(viewport={'width': 1648, 'height': 928}, device_scale_factor=1, locale='en-GB')
            page = context.new_page()
            page.on('console', lambda m: console_messages.append(f'{m.type}: {m.text}'))
            page.on('pageerror', lambda e: page_errors.append(str(e)))
            page.on('request', lambda r: foreign.append(r.url) if not r.url.startswith(server.origin) else None)
            page.goto(server.origin + '/console')
            page.get_by_label('Access key').fill(owner); page.get_by_role('button', name='Sign in').click()
            expect(page.locator('.connection-state')).to_have_text('Connected')
            check('owner signs in to the connected console')
            command = page.get_by_label('Command or search')
            command.fill('tasks'); command.press('Enter')
            tasks = page.get_by_role('dialog')
            expect(tasks.get_by_role('tab', name=re.compile('^Records'))).to_have_attribute('aria-selected', 'true')
            check('the executive dialog opens on its records view with attention and insight tabs',
                  tasks.get_by_role('tab', name=re.compile('^Attention')).is_visible() and tasks.get_by_role('tab', name=re.compile('^Insights')).is_visible())
            form = tasks.get_by_label('New executive record')
            people = form.get_by_label('Linked person')
            expect(people.locator('option', has_text='(reviewed)')).to_have_count(1, timeout=15000)
            options = people.locator('option').all_inner_texts()
            check('the person picker keeps an authored note and its reviewed namesake apart',
                  'Sample producer' in options and 'Sample producer (reviewed)' in options)

            def add(kind, title, project=None, due=None, responsible=None, linked=None):
                form.get_by_label('Kind').select_option(kind)
                form.get_by_label('Project').select_option(label=project) if project else form.get_by_label('Project').select_option('')
                form.get_by_label('Title').fill(title)
                form.get_by_label('Due').fill(due or '')
                form.get_by_label('Responsible').fill(responsible or '')
                form.get_by_label('Linked person').select_option(label=linked) if linked else form.get_by_label('Linked person').select_option('')
                form.get_by_role('button', name='Add record').click()
                expect(tasks.locator('.task-row').filter(has_text=title)).to_be_visible(timeout=15000)

            add('decision', 'Choose the opening', 'Sample film', day(3), 'Producer', 'Sample producer')
            add('commitment', 'Approve the edit', 'Sample film', None, 'Producer', 'Sample producer (reviewed)')
            add('commitment', 'Send the crew update', 'Sample film', day(1), 'Coordinator')
            add('commitment', 'Book the grade', 'Sample film', day(-1), 'Coordinator')
            add('follow_up', 'Review the draft policy', 'ALFRED', day(-2), 'Coordinator')
            add('milestone', 'Picture lock', 'Sample film')
            check('records are added with a typed responsible label and an explicitly picked link')
            check('the label is never filled from note text', mine('Picture lock')['responsible'] is None
                  and 'Fictional responsibility' in (home / 'vault' / 'people' / 'Sample Producer.md').read_text())
            check('a label is not an account: no credential or person is created', people_count() == identities)
            decision, edit = mine('Choose the opening'), mine('Approve the edit')
            check('namesake links stay distinct on the server',
                  decision['responsible_link'].startswith('note:') and edit['responsible_link'] == 'entity:producer')
            tasks.get_by_label('Filter by responsible').select_option(label='Coordinator')
            rows = tasks.locator('.task-row')
            expect(rows).to_have_count(3)
            shown = rows.all_inner_texts()
            check('filtering by a responsible label shows only its records',
                  all(any(t in row for row in shown) for t in ('Send the crew update', 'Book the grade', 'Review the draft policy'))
                  and all('Coordinator' in row for row in shown))
            top(tasks); page.screenshot(path=str(out / 'executive-filter.png'))
            tasks.get_by_label('Filter by responsible').select_option(label='Everyone')
            tasks.get_by_label('Group records by').select_option('responsible')
            headings = tasks.locator('.ask-section h3').all_text_contents()
            check('grouping by responsible never merges namesakes or spellings',
                  'Producer · linked to Sample producer' in headings and 'Producer · linked to Sample producer (reviewed)' in headings
                  and 'Coordinator' in headings and headings[-1] == 'No responsible label')
            top(tasks); page.screenshot(path=str(out / 'executive-grouped.png'))
            tasks.get_by_label('Group records by').select_option('kind')
            tasks.get_by_label('Close panel').click()
            # The explicitly picked link is an authored edge in the graph and the inspector.
            page.get_by_role('button', name='Explore operations').click()
            page.get_by_role('dialog').locator('.record-row').filter(has_text='Choose the opening').click()
            inspector = page.get_by_role('complementary', name='Record inspector')
            expect(inspector).to_contain_text('EXECUTIVE RECORD · AUTHORED BY YOU')
            expect(inspector).to_contain_text('responsible (your link) · responsible')
            expect(inspector.locator('.detail-list')).to_contain_text('Producer', timeout=15000)
            check('the inspector reads the executive record and labels the responsible link as yours')
            inspector.get_by_role('button', name='Open in next steps').click()
            tasks = page.get_by_role('dialog')
            editor = tasks.locator('.record-editor')
            expect(editor).to_be_visible()
            check('the inspector opens the record details in the executive dialog')
            # Decision options, decide, reopen.
            editor.get_by_label('Option 1 name').fill('Monochrome')
            editor.get_by_label('Option 1 notes').fill('As the treatment proposes.')
            editor.get_by_label('Option 1 pros, one per line').fill('Matches the brief')
            editor.get_by_label('Option 1 cons, one per line').fill('Needs a grade pass')
            editor.get_by_label('Option 2 name').fill('Colour')
            editor.get_by_role('button', name='Save options').click()
            expect(page.get_by_role('status').filter(has_text='Nothing scores them')).to_be_visible()
            expect(editor.get_by_role('radio', name='Monochrome')).to_be_visible(timeout=15000)
            saved = mine('Choose the opening')['options']
            check('options are saved in the authored order with no score', [o['label'] for o in saved] == ['Monochrome', 'Colour']
                  and all(set(o) == {'id', 'label', 'notes', 'pros', 'cons'} for o in saved))
            check('nothing is decided by saving options', mine('Choose the opening')['choice'] is None)
            editor.get_by_role('button', name='Prepare brief').click()
            brief = tasks.get_by_label('Assembled brief')
            expect(brief).to_contain_text('Not advice and not model output', timeout=15000)
            expect(brief).to_contain_text('The fictional production brings its brief, people and decisions into one view.')
            expect(brief).to_contain_text('Fictional responsibility: review changes to the sample film brief.')
            expect(brief).to_contain_text('in pre-production')
            expect(brief).to_contain_text('Options without notes: "Colour".')
            check('the brief cites the project note, the linked person note and a reviewed statement with revisions and lines',
                  'line 8' in brief.inner_text() and 'Reviewed statement v' in brief.inner_text())
            related = brief.locator('.brief-related .record-row').all_inner_texts()
            check('the brief gathers open commitments in the same project, nearest due first',
                  [r.split('\n')[0] for r in related] == ['Book the grade', 'Send the crew update', 'Approve the edit'])
            check('the brief reports recorded milestone progress only', '0 of 1 recorded milestones done' in brief.inner_text())
            top(tasks); page.screenshot(path=str(out / 'executive-brief.png'))
            brief.locator('.brief-questions').scroll_into_view_if_needed()
            page.screenshot(path=str(out / 'executive-brief-sections.png'))
            with store.connection() as db:
                before = [db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('executive_records', 'executive_progress', 'executive_decisions')]
            # The source changes: the brief is assembled again and the stale quote and statement drop out.
            path = home / 'vault' / 'projects' / 'Sample Film.md'
            path.write_text(path.read_text().replace('brings its brief, people and decisions', 'now brings its revised brief and people'))
            expect(brief).to_contain_text('now brings its revised brief and people', timeout=20000)
            check('a changed source re-assembles the brief without the old excerpt', 'brings its brief, people and decisions' not in brief.inner_text())
            check('a reviewed statement whose support changed is no longer shown', 'in pre-production' not in brief.inner_text())
            with store.connection() as db:
                after = [db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('executive_records', 'executive_progress', 'executive_decisions')]
            check('assembling briefs stores nothing', before == after)
            brief.get_by_role('button', name='Back to records').click()
            editor = expand(tasks, 'Choose the opening')
            editor.get_by_role('radio', name='Monochrome').check()
            editor.get_by_label('Rationale').fill('Matches the approved treatment.')
            editor.get_by_role('button', name='Record decision').click()
            expect(editor.locator('.decision-outcome')).to_contain_text('Monochrome', timeout=15000)
            check('a choice and rationale are recorded only on an explicit decision', mine('Choose the opening')['choice']['rationale'] == 'Matches the approved treatment.')
            check('a decided decision cannot have its options edited', editor.get_by_role('button', name='Save options').count() == 0)
            editor.get_by_role('button', name='Reopen decision').click()
            expect(editor.get_by_role('button', name='Save options')).to_be_visible(timeout=15000)
            expect(editor.get_by_label('Decision history')).to_contain_text('Reopened (was Monochrome)')
            editor.get_by_role('radio', name='Colour').check()
            editor.get_by_label('Rationale').fill('The client asked for colour throughout.')
            editor.get_by_role('button', name='Record decision').click()
            expect(editor.locator('.decision-outcome')).to_contain_text('Colour', timeout=15000)
            history = [h['event'] for h in mine('Choose the opening')['decision_history']]
            check('reopening is explicit and the earlier choice stays in the history', history == ['decided', 'reopened', 'decided'])
            editor.locator('.decision-outcome').scroll_into_view_if_needed()
            page.screenshot(path=str(out / 'executive-decision.png'))
            editor = expand(tasks, 'Picture lock')
            editor.get_by_label('Progress note').fill('Rough cut reviewed')
            editor.get_by_role('button', name='Record progress').click()
            expect(editor.get_by_label('Recorded progress')).to_contain_text('Rough cut reviewed', timeout=15000)
            check('milestone progress is an authored, dated entry', mine('Picture lock')['progress'][0]['note'] == 'Rough cut reviewed')
            # Attention: stated rules, in-app only, with an authored snooze.
            tasks.get_by_role('tab', name=re.compile('^Attention')).click()
            items = tasks.locator('.attention-item')
            expect(items.filter(has_text='Book the grade')).to_contain_text('Overdue')
            expect(items.filter(has_text='Review the draft policy')).to_contain_text('Overdue')
            expect(items.filter(has_text='Send the crew update')).to_contain_text('Due soon')
            check('attention lists overdue and due-soon items by the stated rules', items.filter(has_text='Choose the opening').count() == 0)
            check('attention says it is shown in the console only', 'nothing is pushed, e-mailed or sent to a device' in tasks.inner_text())
            top(tasks); page.screenshot(path=str(out / 'executive-attention.png'))
            tasks.get_by_role('button', name='Snooze Send the crew update').click()
            tasks.get_by_role('button', name='Confirm snooze').click()
            snoozed = tasks.locator('.ask-section').filter(has_text='Snoozed')
            expect(snoozed).to_contain_text('Send the crew update', timeout=15000)
            check('a snoozed item leaves the attention list and stays visible as snoozed',
                  items.filter(has_text='Send the crew update').filter(has_text='Due soon').count() == 0)
            view = records.view(owner)
            check('snooze is stored on the record and also pauses the recommendation',
                  mine('Send the crew update')['snoozed'] and all(r['title'] != 'Send the crew update' for r in view['recommendations']))
            # Derived insight: one label with overdue records in two projects.
            tasks.get_by_role('tab', name=re.compile('^Insights')).click()
            insight = tasks.locator('.derived-insight').filter(has_text='"Coordinator" holds overdue records in 2 projects.')
            expect(insight).to_be_visible()
            check('a derived insight is labelled as derived and links to its records',
                  'Derived · responsible overdue across projects' in insight.text_content() and insight.get_by_role('button', name='Book the grade').is_visible()
                  and insight.get_by_role('button', name='Review the draft policy').is_visible())
            check('insights state they are not accepted facts and are not stored', 'not accepted facts and are not stored' in tasks.inner_text())
            top(tasks); page.screenshot(path=str(out / 'executive-insights.png'))
            count = len(records.view(owner)['records'])
            insight.get_by_role('button', name='Book the grade').click()
            expect(inspector.get_by_role('heading', name='Book the grade')).to_be_visible(timeout=15000)
            check('following an insight opens the record it came from', len(records.view(owner)['records']) == count)
            page.get_by_label('Close record inspector').click()
            panel = page.locator('.executive-panel')
            expect(panel.locator('.attention-section')).to_contain_text('Book the grade', timeout=15000)
            expect(panel.locator('.derived-row')).to_contain_text('Derived from your records · not an accepted fact')
            check('the side panel shows attention and the derived insight from the same records')
            page.screenshot(path=str(out / 'executive-panel.png'))
            panel.locator('.derived-row').scroll_into_view_if_needed()
            page.screenshot(path=str(out / 'executive-panel-insight.png'))
            panel.locator('.derived-row').click()
            tasks = page.get_by_role('dialog')
            expect(tasks.get_by_role('tab', name=re.compile('^Insights'))).to_have_attribute('aria-selected', 'true')
            check('the side panel opens the insight view')
            tasks.get_by_label('Close panel').click()
            # Access is rechecked when a brief is assembled.
            policy = IdentityPolicy(store)
            policy.enable(owner, policy.view(owner)['epoch'])
            expect(page.locator('.toast')).to_contain_text('Access changed', timeout=15000)
            command.fill('tasks'); command.press('Enter')
            tasks = page.get_by_role('dialog')
            expand(tasks, 'Choose the opening').get_by_role('button', name='Prepare brief').click()
            brief = tasks.get_by_label('Assembled brief')
            expect(brief).to_contain_text('The linked project is not currently available to you.', timeout=15000)
            text = brief.inner_text()
            check('after access is withdrawn the brief omits the project and person notes',
                  'now brings its revised brief' not in text and 'Fictional responsibility' not in text)
            check('the brief names what is unavailable instead of guessing', 'The linked responsible record is not currently available to you.' in text)
            top(tasks); page.screenshot(path=str(out / 'executive-brief-access.png'))
            brief.get_by_role('button', name='Back to records').click()
            linked = expand(tasks, 'Choose the opening').get_by_label('Linked person')
            check('a link the person can no longer see is shown as unavailable, never as a name',
                  linked.locator('option:checked').inner_text() == 'Linked record not available')
            tasks.locator('.record-editor').get_by_label('Responsible label').fill('Producer and editor')
            tasks.locator('.record-editor').get_by_role('button', name='Save responsible').click()
            expect(page.get_by_role('status').filter(has_text='Responsible label saved')).to_be_visible()
            check('the label can still change while the hidden link is kept, not revealed',
                  mine('Choose the opening')['responsible'] == 'Producer and editor' and mine('Choose the opening')['responsible_state'] == 'unavailable')
            for width, height in ((1280, 800), (390, 844)):
                page.set_viewport_size({'width': width, 'height': height}); page.wait_for_timeout(500); top(tasks)
                check(f'{width}px executive dialog has no horizontal overflow', page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                page.screenshot(path=str(out / f'executive-{width}.png'), full_page=True)
            check('no browser storage used', page.evaluate('localStorage.length===0&&sessionStorage.length===0'))
            check('no access key rendered', owner not in page.content())
            csp = [m for m in console_messages if 'Content Security Policy' in m or 'Refused to' in m]
            check('no Content Security Policy violations', not csp)
            check('no requests leave the loopback origin', not foreign)
            check('no uncaught page errors', not page_errors)
            browser.close()
    finally:
        sup.stop()
        server.shutdown(); server.server_close()

report = {'passed': len(checks), 'checks': checks, 'browser_console': console_messages[-20:], 'page_errors': page_errors,
          'inputs': 'synthetic Markdown vault only', 'model_inference': False, 'console_dist': 'console/dist built from this commit'}
(out / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': len(checks), 'page_errors': page_errors}))
