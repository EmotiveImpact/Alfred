"""Browser-to-backend acceptance for the connected premium console.

Runs the real loopback ALFRED server over a synthetic vault, serves the built
console from the same origin and drives it in Chromium. Testing-only tooling;
requires `npm run build` in console/ first. No model, account or private data.
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
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor, MarkdownVault
from alfred.desk_http import DeskHTTPServer
from alfred.reviewed_memory import ReviewedMemory
from alfred.policy import IdentityPolicy
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'console' / 'dist'
out = Path(os.environ.get('ALFRED_CONSOLE_OUTPUT', ROOT / 'docs' / 'evidence' / 'console-connected'))
out.mkdir(parents=True, exist_ok=True)
checks, console_messages, page_errors, foreign = [], [], [], []


def check(name, condition=True):
    assert condition, name
    checks.append(name)


def note(store, bearer, title):
    return next(n for n in store.knowledge(bearer)['nodes'] if n['title'] == title)


if not (DIST / 'index.html').is_file():
    raise SystemExit('Build the console first: cd console && npm run build')

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp); home = root / 'demo'; keys = init_demo(home)
    store = KnowledgeStore(home / 'desk.sqlite')
    sup = KnowledgeSupervisor(store, keys['owner'], keys['source'], home / 'project', vault=home / 'vault', interval=.2)
    sup.cycle(); sup.start()
    # A second workspace that must never appear.
    other_source = store.provision('other-workspace', 'other-source', 'source')
    other = root / 'other-vault'; other.mkdir()
    (other / 'Hidden.md').write_text('# Zephyrmarker\nAnother workspace.\n')
    MarkdownVault(store, other_source, other).scan()
    server = DeskHTTPServer(store, sup, port=0, console_dist=DIST)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); thread.start()
    memory = ReviewedMemory(store)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'), headless=True,
                                        args=['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            context = browser.new_context(viewport={'width': 1648, 'height': 928}, device_scale_factor=1)
            page = context.new_page()
            page.on('console', lambda m: console_messages.append(f'{m.type}: {m.text}'))
            page.on('pageerror', lambda e: page_errors.append(str(e)))
            page.on('request', lambda r: foreign.append(r.url) if not r.url.startswith(server.origin) else None)
            page.goto(server.origin + '/console')
            check('console is served by the ALFRED origin', page.url == server.origin + '/console/')
            expect(page.get_by_role('heading', name='Sign in to ALFRED')).to_be_visible()
            body = page.locator('body').inner_text()
            check('signed-out view shows no fixture records', 'Velvet Accademy' not in body and 'Demo workspace' not in body)
            check('signed-out graph has zero records', '0 records' in page.locator('.graph-view-label').inner_text())
            page.get_by_label('Access key').fill('x' * 43); page.get_by_role('button', name='Sign in').click()
            expect(page.get_by_role('alert')).to_contain_text('not accepted')
            check('wrong key is refused without revealing data')
            page.get_by_label('Access key').fill(keys['owner']); page.get_by_role('button', name='Sign in').click()
            expect(page.locator('.connection-state')).to_have_text('Connected')
            check('owner signs in through the real session endpoint')
            expect(page.locator('.graph-view-label')).to_contain_text('21 records')
            label = page.locator('.graph-view-label').inner_text()
            links = len(store.knowledge(keys['owner'])['links'])
            check('graph counts come from permitted backend records', f'21 records · {links} links' in label)
            check('workspace selector lists only the server workspace', page.locator('#scope-select option').all_inner_texts() == ['Demo production'])
            check('command bar states connected source mode', 'CONNECTED · SOURCE MODE' in page.locator('.command-meta').inner_text())
            check('no fixture or other-workspace names after sign-in', all(x not in page.locator('body').inner_text() for x in ('Velvet Accademy', 'Zephyrmarker', 'INDIGO')))
            page.wait_for_timeout(800)
            page.screenshot(path=str(out / 'connected-desktop.png'))
            page.get_by_role('button', name='Explore projects').click()
            dialog = page.get_by_role('dialog')
            for title in ('Sample film', 'ALFRED', 'Home node concept'):
                expect(dialog.get_by_role('button', name=title)).to_be_visible()
            check('project callout lists actual project notes')
            dialog.get_by_role('button', name='Sample film').click()
            inspector = page.get_by_role('complementary', name='Record inspector')
            expect(inspector).to_contain_text('AUTHORED NOTE · NOT A VERIFIED FACT')
            expect(inspector).to_contain_text('projects/Sample Film.md')
            expect(inspector.locator('.source-lines')).to_contain_text('The fictional production brings its brief')
            check('selecting a project shows its exact source path and lines')
            expect(inspector).to_contain_text('authored link')
            inspector.get_by_role('button', name='Sample producer').first.click()
            expect(inspector.get_by_role('heading', name='Sample producer')).to_be_visible()
            check('following a supported relationship opens the neighbour record')
            page.screenshot(path=str(out / 'connected-inspector.png'))
            # Reviewed memory created through the real service appears after refresh.
            producer = note(store, keys['owner'], 'Sample producer')
            memory.create_entity(keys['owner'], {'id': 'film', 'kind': 'project', 'name': 'Sample film'})
            memory.create_entity(keys['owner'], {'id': 'producer', 'kind': 'person', 'name': 'Sample producer'})
            claim = memory.propose(keys['owner'], {'request_id': 'r1', 'subject_id': 'film', 'predicate': 'responsible_person', 'object_id': 'producer', 'value': None,
                                                   'valid_from': None, 'valid_until': None,
                                                   'evidence': {'note_id': producer['id'], 'sha256': producer['sha256'], 'revision': producer['revision'], 'start_line': 8, 'end_line': 8}})
            memory.review(keys['owner'], claim['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
            page.get_by_label('Close record inspector').click()
            expect(page.locator('.insight-section')).to_contain_text('responsible person: Sample producer', timeout=15000)
            check('accepted reviewed statement appears as an insight after refresh')
            expect(page.locator('.graph-view-label')).to_contain_text('23 records')
            page.locator('.insight-row').click()
            expect(inspector).to_contain_text('REVIEWED MEMORY · YOUR JUDGEMENT')
            expect(inspector).to_contain_text('Accepted and current')
            expect(inspector.locator('blockquote')).to_contain_text('Fictional responsibility')
            check('reviewed entity shows review basis and exact original support')
            expect(inspector).to_contain_text('reviewed relationship · responsible person')
            check('reviewed relationship is labelled separately from authored links')
            page.screenshot(path=str(out / 'connected-reviewed.png'))
            # Changing the supporting source makes the review visibly unusable.
            path = home / 'vault' / 'people' / 'Sample Producer.md'
            path.write_text(path.read_text().replace('Fictional responsibility', 'Changed responsibility'))
            expect(inspector).to_contain_text('Source changed · review needed', timeout=15000)
            expect(page.locator('.insight-section')).to_contain_text('No reviewed statement yet', timeout=15000)
            check('source change invalidates the displayed review and insight')
            check('stale quote is no longer displayed', 'Fictional responsibility' not in inspector.inner_text())
            # M05: forgetting through the console, with a server receipt.
            film_note = note(store, keys['owner'], 'Sample film')
            status = memory.propose(keys['owner'], {'request_id': 'r2', 'subject_id': 'film', 'predicate': 'status', 'object_id': None, 'value': 'in pre-production',
                                                    'valid_from': None, 'valid_until': None,
                                                    'evidence': {'note_id': film_note['id'], 'sha256': film_note['sha256'], 'revision': film_note['revision'], 'start_line': 8, 'end_line': 8}})
            memory.review(keys['owner'], status['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
            statement = inspector.locator('.statement').filter(has_text='in pre-production')
            expect(statement).to_be_visible(timeout=15000)
            statement.get_by_role('button', name='Forget this statement').click()
            inspector.get_by_role('button', name='Confirm forget').click()
            expect(page.get_by_role('status').filter(has_text='Not secure erasure')).to_be_visible()
            expect(inspector).to_contain_text('Forgotten · value removed', timeout=15000)
            check('forgetting removes the value from the open inspector', 'in pre-production' not in inspector.inner_text())
            check('forgetting is recorded with a receipt', memory.view(keys['owner'])['claims'][0]['state'] == 'forgotten')
            page.get_by_label('Close record inspector').click()
            # Stage B: the selected project is context for the next question.
            command = page.get_by_label('Command or search')
            command.fill('What still needs confirming?'); command.press('Enter')
            ask = page.get_by_role('dialog')
            expect(ask).to_contain_text('No record selected')
            expect(ask.locator('.evidence').first).to_be_visible(timeout=15000)
            unfocused = ask.locator('.evidence header .text-button').all_inner_texts()
            check('unfocused question uses the whole permitted workspace', 'Sample film' not in unfocused[:1])
            check('missing model is reported explicitly', 'no model configured' in ask.inner_text())
            page.keyboard.press('Escape')
            page.get_by_role('button', name='Explore projects').click()
            films = page.get_by_role('dialog').locator('.record-row').filter(has_text='Sample film')
            check('authored note and reviewed entity with the same name stay separate', films.count() == 2)
            films.filter(has_text='The fictional production').click()
            command.fill('What still needs confirming?'); command.press('Enter')
            expect(ask).to_contain_text('Context: Sample film')
            expect(ask.locator('.evidence').first).to_contain_text('Selected record', timeout=15000)
            check('selecting a project changes the next question', ask.locator('.evidence header .text-button').first.inner_text().strip() == 'Sample film')
            check('answer exposes source path, lines and basis', 'projects/Sample Film.md' in ask.inner_text() and 'not a generated answer' in ask.inner_text())
            page.screenshot(path=str(out / 'connected-ask.png'))
            ask.locator('summary').click()
            ask.get_by_label('Draft text').fill('Synthetic follow-up for the sample film.')
            ask.get_by_role('button', name='Propose draft').click()
            expect(page.get_by_role('status').filter(has_text='Draft proposed')).to_be_visible()
            check('proposing a draft from an answer is a separate explicit step')
            # The open answer is withdrawn when its source changes.
            film = home / 'vault' / 'projects' / 'Sample Film.md'
            film.write_text(film.read_text().replace('brings its brief', 'now brings its brief'))
            expect(ask).to_contain_text('It was withdrawn rather than shown stale', timeout=20000)
            check('changed source withdraws the displayed answer')
            page.keyboard.press('Escape')
            if page.get_by_label('Close record inspector').count():
                page.get_by_label('Close record inspector').click()
            row = page.locator('.approval-row').filter(has_text='Local message draft')
            expect(row.first).to_be_visible(timeout=15000)
            row.first.get_by_role('button', name='Review Local message draft').click()
            expect(page.get_by_role('dialog')).to_contain_text('cannot be approved')
            check('draft bound to changed evidence cannot be approved')
            page.get_by_role('dialog').get_by_label('Close panel').click()
            row.first.get_by_role('button', name='Decline Local message draft').click()
            dialog = page.get_by_role('dialog')
            dialog.get_by_text('I want to cancel this exact proposal.').click()
            dialog.get_by_role('button', name='Confirm cancellation').click()
            expect(page.locator('.approval-row')).to_have_count(0, timeout=15000)
            check('stale draft can be cancelled through the server')
            command.fill('search equipment'); command.press('Enter')
            expect(page.get_by_role('dialog')).to_contain_text('Searches permitted records')
            check('explicit search stays distinct from asking')
            page.keyboard.press('Escape')
            # A real server proposal, approved through the existing ledger.
            event = store.desk_state(keys['owner'])['events'][0]
            store.propose_from_evidence(keys['owner'], {'event_seq': event['seq'], 'text': 'Synthetic crew update for review.', 'request_id': 'console-approval'})
            row = page.locator('.approval-row').filter(has_text='Local message draft')
            expect(row).to_be_visible(timeout=15000)
            check('pending server proposal appears in approvals')
            row.get_by_role('button', name='Review Local message draft').click()
            dialog = page.get_by_role('dialog')
            expect(dialog).to_contain_text('Synthetic crew update for review.')
            approve = dialog.get_by_role('button', name='Approve exact text')
            check('approval requires explicit consent', approve.is_disabled())
            dialog.get_by_text('I approve this exact text and nothing else.').click()
            approve.click()
            expect(page.get_by_role('status').filter(has_text='Nothing is sent')).to_be_visible()
            deadline = time.time() + 15
            while time.time() < deadline and store.desk_state(keys['owner'])['actions'][0]['state'] != 'verified':
                time.sleep(.2)
            check('approved action is executed and verified by the existing outbox', store.desk_state(keys['owner'])['actions'][0]['state'] == 'verified')
            expect(page.locator('.approval-row')).to_have_count(0, timeout=15000)
            check('approvals list reflects the server result')
            # M04: remember this, review it, then an approved create-only inbox note.
            policy = IdentityPolicy(store)
            for capability in ('read', 'inbox.write'):
                policy.grant(keys['owner'], 'demo-source', capability, store.now() + 3600, policy.view(keys['owner'])['epoch'])
            expect(page.locator('.toast')).to_contain_text('Access changed', timeout=15000)
            check('a grant change is announced and rebuilds the view')
            command.fill('When is the camera collection confirmed?'); command.press('Enter')
            ask = page.get_by_role('dialog')
            equipment = ask.locator('.evidence').filter(has_text='Equipment check')
            expect(equipment).to_be_visible(timeout=15000)
            equipment.get_by_role('button', name='Remember this…').click()
            form = ask.get_by_label('Remember this', exact=True)
            form.get_by_label('Record').select_option('new')
            form.get_by_label('Name').fill('Camera collection')
            form.get_by_label('Kind').select_option('commitment')
            form.get_by_label('Statement').select_option('status')
            form.get_by_label('Value').fill('needs confirmation')
            form.get_by_label('Memory type').select_option('commitment')
            form.get_by_label('Retention').select_option(label='90 days')
            form.get_by_role('button', name='Preview proposal').click()
            preview = ask.get_by_label('Remember this preview')
            expect(preview).to_contain_text('Forgotten after', timeout=15000)
            page.screenshot(path=str(out / 'connected-remember.png'))
            check('remember previews workspace, type, source and retention', all(x in preview.inner_text() for x in ('demo-production', 'commitment', 'notes/Equipment.md')))
            check('a captured proposal is not usable before review', not any(c['usable'] for c in memory.view(keys['owner'])['claims'] if c.get('memory_type') == 'commitment'))
            preview.get_by_role('button', name='Accept as my reviewed statement').click()
            expect(preview).to_contain_text('Accepted as your reviewed statement')
            check('accepting makes the captured statement usable', any(c['usable'] for c in memory.view(keys['owner'])['claims'] if c.get('memory_type') == 'commitment'))
            preview.locator('summary').click()
            preview.get_by_label('Inbox note name').fill('Camera collection.md')
            preview.get_by_role('button', name='Propose inbox note').click()
            expect(page.get_by_role('status').filter(has_text='Inbox note proposed')).to_be_visible()
            target = home / 'vault' / 'ALFRED' / 'Inbox' / 'Camera collection.md'
            check('nothing is written before approval', not target.exists())
            ask.get_by_label('Close panel').click()
            row = page.locator('.approval-row').filter(has_text='Inbox note · Camera collection.md')
            expect(row).to_be_visible(timeout=15000)
            row.get_by_role('button', name='Review Inbox note · Camera collection.md').click()
            dialog = page.get_by_role('dialog')
            expect(dialog).to_contain_text('ALFRED/Inbox/Camera collection.md')
            dialog.get_by_text('I approve creating this exact file with this exact text.').click()
            dialog.get_by_role('button', name='Approve exact text').click()
            deadline = time.time() + 15
            while time.time() < deadline and not target.exists():
                time.sleep(.2)
            check('approved inbox note is created in the vault', target.exists() and 'needs confirmation' in target.read_text())
            expect(page.locator('.approval-row')).to_have_count(0, timeout=15000)
            page.get_by_label('Search workspace', exact=True).click()
            page.get_by_label('Search records').fill('Camera collection')
            expect(page.get_by_role('dialog').locator('.record-row').filter(has_text='Camera collection')).to_have_count(2, timeout=15000)
            check('the new inbox note is indexed and read back as an authored note beside the reviewed record')
            page.keyboard.press('Escape')
            # Laptop and mobile layouts.
            for width, height in ((1280, 800), (390, 844)):
                page.set_viewport_size({'width': width, 'height': height}); page.wait_for_timeout(600)
                check(f'{width}px has no horizontal overflow', page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
                page.screenshot(path=str(out / f'connected-{width}.png'), full_page=True)
            page.set_viewport_size({'width': 1648, 'height': 928})
            check('no browser storage used', page.evaluate('localStorage.length===0&&sessionStorage.length===0'))
            check('no access key rendered', keys['owner'] not in page.content())
            # Server loss keeps the last confirmed view labelled, never fixtures.
            port = server.server_port
            server.shutdown(); server.server_close()
            page.wait_for_timeout(9500)
            expect(page.locator('.connection-state')).to_have_text('Unreachable', timeout=10000)
            expect(page.locator('.connection-banner')).to_contain_text('last confirmed')
            check('command caption no longer claims a live connection', 'UNREACHABLE' in page.locator('.command-meta').inner_text())
            check('server loss is shown as unreachable with last confirmation time')
            check('server loss never substitutes fixtures', 'Velvet Accademy' not in page.locator('body').inner_text())
            page.screenshot(path=str(out / 'connected-unreachable.png'))
            # A restarted server keeps no in-memory sessions, so the console asks to sign in again.
            server = DeskHTTPServer(store, sup, port=port, console_dist=DIST)
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); thread.start()
            expect(page.get_by_role('heading', name='Sign in to ALFRED')).to_be_visible(timeout=20000)
            check('a restarted server requires a new sign-in and clears the stale view', '0 records' in page.locator('.graph-view-label').inner_text())
            page.get_by_label('Access key').fill(keys['owner']); page.get_by_role('button', name='Sign in').click()
            expect(page.locator('.connection-state')).to_have_text('Connected')
            # Revocation clears everything without a reload.
            page.get_by_role('button', name='Explore projects').click()
            store.revoke('demo-owner')
            expect(page.get_by_role('heading', name='Sign in to ALFRED')).to_be_visible(timeout=15000)
            check('revocation returns to sign-in and closes open dialogs', page.get_by_role('dialog').count() == 0)
            check('revocation clears every record', '0 records' in page.locator('.graph-view-label').inner_text() and 'Sample film' not in page.locator('body').inner_text())
            # Under strict grants another person sees nothing until granted. Counts leak nothing.
            page.get_by_label('Access key').fill(keys['reader']); page.get_by_role('button', name='Sign in').click()
            expect(page.locator('.connection-state')).to_have_text('Connected')
            expect(page.locator('.graph-view-label')).to_contain_text('0 records')
            check('a person without grants sees no records, names or counts', 'Sample film' not in page.locator('body').inner_text())
            csp = [m for m in console_messages if 'Content Security Policy' in m or 'Refused to' in m]
            check('no Content Security Policy violations', not csp)
            check('no requests leave the loopback origin', not foreign)
            check('no uncaught page errors', not page_errors)
            browser.close()
    finally:
        sup.stop()
        try:
            server.shutdown(); server.server_close()
        except Exception:
            pass

report = {'passed': len(checks), 'checks': checks, 'browser_console': console_messages[-20:], 'page_errors': page_errors,
          'inputs': 'synthetic Markdown vault only', 'model_inference': False, 'console_dist': 'console/dist built from this commit'}
(out / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': len(checks), 'page_errors': page_errors}))
