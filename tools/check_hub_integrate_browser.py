"""Browser-to-backend check for results and checks in the goals panel (docs/AGENT_HUB.md,
steps H2 to H4 wired together).

Runs the real loopback ALFRED server over the synthetic demo vault with the H1
SyntheticBrain plugged in through a GoalHub (and its verifier), a real job coordinator and
a brain worker thread, serves the built console from the same origin and drives it in
Chromium. Three synthetic goals: one whose mandate declares checks the brain's result fails,
one whose checks it passes and one with no checks. The checks run once on their own as each
result arrives (backlog A3); the owner runs them again and acknowledges a failed result
through the confirmation; the server's records are compared
after each step. Testing-only tooling; requires `npm run build` in console/ first. No model,
network brain, account or private data.

Output goes to docs/evidence/hub-integrate/browser unless ALFRED_HUB_INTEGRATE_OUTPUT names
another folder.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alfred.brain import BrainHub, BrainPolicy, BrainRegistry, SyntheticBrain
from alfred.desk import init_demo
from alfred.desk_http import DeskHTTPServer
from alfred.executive import ExecutiveRecords
from alfred.hub_goals import GoalHub
from alfred.jobs import JobCoordinator, JobWorker
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'console' / 'dist'
out = Path(os.environ.get('ALFRED_HUB_INTEGRATE_OUTPUT', ROOT / 'docs' / 'evidence' / 'hub-integrate' / 'browser'))
out.mkdir(parents=True, exist_ok=True)
checks, console_messages, page_errors, foreign = [], [], [], []
NONE = {'tokens': None, 'money_pence': None, 'wall_seconds': None, 'tasks': None}
TASK_BUDGET = {'wall_seconds': 10, 'tokens': 30, 'money_pence': 0, 'steps': 50}
SECTIONS = {'kind': 'artefact_sections', 'artefact': 'notes.md', 'sections': ['Synthetic brain notes']}
CITED = {'kind': 'claims_cited'}


def check(name, condition=True):
    assert condition, name
    checks.append(name)


def budget(daily=None, total=None, warn=80):
    return {'daily': {**NONE, **(daily or {})}, 'total': {**NONE, **(total or {})}, 'warn_percent': warn, 'utc_offset_minutes': 0}


if not (DIST / 'index.html').is_file():
    raise SystemExit('Build the console first: cd console && npm run build')

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp); home = root / 'demo'; keys = init_demo(home)
    owner = keys['owner']
    store = KnowledgeStore(home / 'desk.sqlite')
    sup = KnowledgeSupervisor(store, owner, keys['source'], home / 'project', vault=home / 'vault', interval=.2)
    sup.cycle()
    jobs = JobCoordinator(store)
    jobs.enrol_worker(owner, 'brain-host', 'Synthetic brain worker', ['brain_task'])
    registry = BrainRegistry()
    registry.register(SyntheticBrain())
    brains = BrainHub(store, jobs, registry, BrainPolicy())
    hub = GoalHub(store, brains, owner)
    stop_worker = threading.Event()
    worker = threading.Thread(target=JobWorker(jobs, hub.backend(), owner, 'brain-host', poll_seconds=.05, heartbeat_seconds=.1).run,
                              args=(stop_worker,), kwargs={'idle_seconds': .1}, daemon=True)
    worker.start()
    records = ExecutiveRecords(store)

    def goal(request_id, title):
        return records.create(owner, {'request_id': request_id, 'kind': 'goal', 'title': title, 'detail': '',
                                      'project': None, 'due': None, 'rank': None, 'support': None})
    hub.set_budget(owner, 'overall', None, {'version': 0, 'budget': budget(total={'tasks': 20})})
    now = store.now()

    def mandate(request_id, goal_id, acceptance):
        body = {'request_id': request_id, 'goal': goal_id, 'scope_class': 'company', 'deadline': now + 7 * 86400,
                'success_test': 'The producer approves the synthetic deck.', 'autonomy': {'research': 1},
                'brains': ['synthetic'], 'assigned_brain': 'synthetic', 'tools': [], 'budget': budget(total={'tasks': 10}),
                'schedule': None}
        if acceptance is not None:
            body['acceptance'] = acceptance
        return hub.create_mandate(owner, body)
    failing = mandate('m1', goal('g1', 'Check the synthetic briefing')['id'], [SECTIONS, CITED])
    passing = mandate('m2', goal('g2', 'Prepare the sample schedule')['id'], [SECTIONS])
    unchecked = mandate('m3', goal('g3', 'Summarise the sample notes')['id'], None)
    check('the owner attaches acceptance checks to a mandate', [c['id'] for c in failing['acceptance']] == ['C1', 'C2'])
    job = {}
    for name, view in (('failing', failing), ('passing', passing), ('unchecked', unchecked)):
        # No excerpt is sent, so the synthetic answer makes an uncited claim: claims_cited fails.
        submitted = hub.submit_task(owner, view['id'], {'request_id': f'task-{name}', 'brain': None, 'work': 'research',
                                                        'instruction': 'Summarise the plan.', 'context': [], 'learned': [],
                                                        'tools': [], 'budget': dict(TASK_BUDGET), 'autonomy': 1})
        job[name] = submitted['job']['id']
    packet = jobs.view(owner, job['failing'])['parameters']['packet']
    check('every task packet carries the mandate checks first, declared by the mandate',
          (packet['acceptance']['declared_by'], packet['acceptance']['ref'], [c['kind'] for c in packet['acceptance']['checks']])
          == ('mandate', failing['id'], ['artefact_sections', 'claims_cited']))
    server = DeskHTTPServer(store, sup, port=0, console_dist=DIST, jobs=jobs, goals=hub)
    check('the host hands its goal hub to the supervisor cycle', sup.goals is hub)
    sup.start()
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); thread.start()

    def outcome(name):
        return next(r for r in hub.verifier.outcomes(owner)['results'] if r['job'] == job[name])

    def settled():
        results = hub.verifier.outcomes(owner)['results']
        return len(results) == 3 and all(outcome(n)['runs'] == 1 for n in ('failing', 'passing'))

    deadline = time.time() + 30
    while time.time() < deadline and not settled():
        time.sleep(.1)
    check('the supervisor cycle ingested all three results', len(hub.verifier.outcomes(owner)['results']) == 3)
    check('the declared checks ran once on their own as the results arrived, and the unchecked result has none',
          [(outcome(n)['evidence'], outcome(n)['runs']) for n in ('failing', 'passing', 'unchecked')]
          == [('failed_checks', 1), ('verified', 1), ('no_checks', 0)])
    check('the automatic runs are recorded as automatic',
          [r['initiated'] for n in ('failing', 'passing') for r in hub.verifier.runs(owner, job[n])] == ['automatic', 'automatic'])

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
            page.get_by_label('Access key').fill(owner); page.get_by_role('button', name='Sign in').click()
            expect(page.locator('.connection-state')).to_have_text('Connected')
            command = page.get_by_label('Command or search')
            command.fill('goals'); command.press('Enter')
            dialog = page.get_by_role('dialog')
            expect(dialog.get_by_role('heading', name='Goals and brains')).to_be_visible()
            card = dialog.locator('article', has=page.get_by_role('heading', name='Check the synthetic briefing'))
            expect(card).to_contain_text('Acceptance checks (yours, run by ALFRED on every task): C1 notes.md has “Synthetic brain notes”'
                                         ' · C2 every claim cites a sent excerpt')
            expect(card).to_contain_text('Success test (yours, not evaluated by ALFRED)')
            plain = dialog.locator('article', has=page.get_by_role('heading', name='Summarise the sample notes'))
            expect(plain).to_contain_text('No acceptance checks on this goal')
            check('the goal card shows the mandate checks, and says when there are none')
            results = dialog.get_by_label('Results and checks', exact=True)
            expect(results).to_contain_text('A result with no declared checks is never counted as verified')
            cards = {name: results.get_by_label(f'Result {job[name]}', exact=True) for name in job}
            chip = {name: cards[name].get_by_label(f'Result {job[name]} verification', exact=True) for name in job}
            expect(chip['failing']).to_have_text('Failed checks')
            expect(chip['passing']).to_have_text('Verified by checks')
            expect(chip['unchecked']).to_have_text('No checks declared')
            expect(cards['unchecked']).to_contain_text('never counted as verified')
            expect(cards['failing']).to_contain_text('Run 1: 1 passed · 1 failed · 0 could not run')
            check('each result shows its class from ALFRED, after the automatic run and before the owner acts')
            check('a result with no checks offers no run and no acknowledgement', cards['unchecked'].get_by_role('button').count() == 0)
            expect(results.get_by_label('Results per brain')).to_contain_text('synthetic: 1 verified · 1 failed checks · 0 not verified · 1 no checks declared')
            check('the per-brain line counts verified, failed, unverifiable and unchecked results apart')
            page.wait_for_timeout(300)
            dialog.screenshot(path=str(out / 'results-on-arrival.png'))

            cards['passing'].get_by_role('button', name='Run checks').click()
            expect(chip['passing']).to_have_text('Verified by checks', timeout=15000)
            check('the owner running the checks again keeps a passing result verified on the server',
                  (outcome('passing')['state'], outcome('passing')['runs']) == ('checked', 2))
            cards['failing'].get_by_role('button', name='Run checks').click()
            expect(cards['failing']).to_contain_text('Run 2: 1 passed · 1 failed · 0 could not run', timeout=15000)
            expect(chip['failing']).to_have_text('Failed checks')
            expect(cards['failing']).to_contain_text('C2 claims cited: failed')
            check('a failing check is shown as failed, matching the server',
                  (outcome('failing')['state'], outcome('failing')['runs']) == ('failed_checks', 2))
            check('the owner\'s runs are recorded as the owner\'s',
                  [r['initiated'] for r in hub.verifier.runs(owner, job['failing'])] == ['automatic', 'owner'])
            # Another run recorded elsewhere: the panel's run count is now stale and the server refuses it.
            hub.verifier.verify(owner, job['passing'])
            cards['passing'].get_by_role('button', name='Run checks').click()
            expect(results.get_by_role('alert')).to_contain_text('Checks ran again since you opened this')
            check('a stale run count is refused by the server', outcome('passing')['runs'] == 3)

            cards['failing'].get_by_role('button', name=f'Acknowledge result {job["failing"]}').click()
            confirm = cards['failing'].get_by_role('group', name=f'Confirm acknowledge result {job["failing"]}')
            expect(confirm).to_contain_text('Run 2 failed C2. Accepting it over failed checks is recorded as your decision')
            check('acknowledging asks for confirmation first and nothing is sent yet', outcome('failing')['state'] == 'failed_checks')
            confirm.scroll_into_view_if_needed()
            page.wait_for_timeout(200)
            dialog.screenshot(path=str(out / 'acknowledge-confirmation.png'))
            confirm.get_by_role('button', name='Cancel').click()
            expect(confirm).to_have_count(0)
            check('cancel leaves the result as it was', outcome('failing')['state'] == 'failed_checks')
            cards['failing'].get_by_role('button', name=f'Acknowledge result {job["failing"]}').click()
            confirm.get_by_role('button', name='Accept with failed checks').click()
            expect(chip['failing']).to_have_text('Acknowledged over failed checks', timeout=15000)
            state = hub.verifier.state(owner, job['failing'])
            check('the server records the owner accepting the exact run over failed checks',
                  (state['state'], state['acknowledged']['over'], state['acknowledged']['failed_accepted']) == ('acknowledged', 'failed_checks', ['C2']))
            check('acknowledgement grants no authority', state['authority_granted'] is False)
            expect(results.get_by_label('Results per brain')).to_contain_text('synthetic: 2 verified · 0 failed checks · 0 not verified · 1 no checks declared')
            check('the unchecked result is still not counted as verified', outcome('unchecked')['evidence'] == 'no_checks')
            page.wait_for_timeout(300)
            dialog.screenshot(path=str(out / 'results-desktop.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            page.wait_for_timeout(300)
            check('no horizontal scroll at phone width', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
            page.screenshot(path=str(out / 'results-phone.png'))
            context.close()
            # A reader key sees that goals belong to the owner, and no results or controls.
            reader = browser.new_context(viewport={'width': 1280, 'height': 800}).new_page()
            reader.on('pageerror', lambda e: page_errors.append(str(e)))
            reader.on('request', lambda r: foreign.append(r.url) if not r.url.startswith(server.origin) else None)
            reader.goto(server.origin + '/console')
            reader.get_by_label('Access key').fill(keys['reader']); reader.get_by_role('button', name='Sign in').click()
            expect(reader.locator('.connection-state')).to_have_text('Connected')
            command = reader.get_by_label('Command or search')
            command.fill('goals'); command.press('Enter')
            expect(reader.get_by_role('dialog')).to_contain_text('Goals are set by the workspace owner')
            text = reader.get_by_role('dialog').inner_text()
            check('a reader sees no results and no controls', 'Results and checks' not in text and job['failing'] not in text)
            check('no requests leave the loopback origin', not foreign)
            check('no uncaught page errors', not page_errors)
            browser.close()
    finally:
        sup.stop(); stop_worker.set(); worker.join(5)
        server.shutdown(); server.server_close()

report = {'passed': len(checks), 'checks': checks, 'browser_console': console_messages[-20:], 'page_errors': page_errors,
          'inputs': 'synthetic demo vault and synthetic executive goals only', 'brain': 'H1 SyntheticBrain (deterministic, no model)',
          'model_inference': False, 'console_dist': 'console/dist built from this commit'}
(out / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': len(checks), 'page_errors': page_errors}))
