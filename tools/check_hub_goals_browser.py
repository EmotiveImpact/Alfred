"""Browser-to-backend check for the goals panel (docs/AGENT_HUB.md, step H2).

Runs the real loopback ALFRED server over the synthetic demo vault with the H1
SyntheticBrain plugged in through a GoalHub, a real job coordinator and a brain
worker thread, serves the built console from the same origin and drives it in
Chromium. Testing-only tooling; requires `npm run build` in console/ first. No
model, network brain, account or private data.

Output goes to docs/evidence/hub-goals/browser unless ALFRED_HUB_GOALS_OUTPUT names
another folder.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alfred import lifecycle
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
out = Path(os.environ.get('ALFRED_HUB_GOALS_OUTPUT', ROOT / 'docs' / 'evidence' / 'hub-goals' / 'browser'))
out.mkdir(parents=True, exist_ok=True)
checks, console_messages, page_errors, foreign = [], [], [], []
NONE = {'tokens': None, 'money_pence': None, 'wall_seconds': None, 'tasks': None}
TASK_BUDGET = {'wall_seconds': 10, 'tokens': 30, 'money_pence': 0, 'steps': 50}


def check(name, condition=True):
    assert condition, name
    checks.append(name)


def budget(daily=None, total=None, warn=50):
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
    goal = records.create(owner, {'request_id': 'g1', 'kind': 'goal', 'title': 'Deliver the synthetic review', 'detail': '',
                                  'project': None, 'due': None, 'rank': None, 'support': None})
    other = records.create(owner, {'request_id': 'g2', 'kind': 'goal', 'title': 'Prepare the sample schedule', 'detail': '',
                                   'project': None, 'due': None, 'rank': None, 'support': None})
    records.create(owner, {'request_id': 'g3', 'kind': 'goal', 'title': 'Unlinked synthetic goal', 'detail': '',
                           'project': None, 'due': None, 'rank': None, 'support': None})
    hub.set_budget(owner, 'overall', None, {'version': 0, 'budget': budget(total={'tasks': 20})})
    now = store.now()

    def mandate(request_id, goal_id, limits):
        return hub.create_mandate(owner, {'request_id': request_id, 'goal': goal_id, 'scope_class': 'company',
                                          'deadline': now + 7 * 86400, 'success_test': 'The producer approves the synthetic deck.',
                                          'autonomy': {'research': 1, 'drafting': 2}, 'brains': ['synthetic'],
                                          'assigned_brain': 'synthetic', 'tools': [], 'budget': limits, 'schedule': None})
    spent = mandate('m1', goal['id'], budget(daily={'tasks': 2}))
    running = mandate('m2', other['id'], budget(total={'tokens': 5000}))
    for n in range(2):
        hub.submit_task(owner, spent['id'], {'request_id': f'task-{n}', 'brain': None, 'work': 'research',
                                             'instruction': 'Summarise the plan.', 'context': [], 'learned': [], 'tools': [],
                                             'budget': dict(TASK_BUDGET), 'autonomy': 1})
    server = DeskHTTPServer(store, sup, port=0, console_dist=DIST, jobs=jobs, goals=hub)
    check('the host hands its goal hub to the supervisor cycle', sup.goals is hub)
    sup.start()
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); thread.start()

    def state(mandate_id):
        return next(g for g in hub.view(owner)['goals'] if g['id'] == mandate_id)

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
            check('the goals command opens the goals panel')
            card = dialog.locator('article', has=page.get_by_role('heading', name='Deliver the synthetic review'))
            expect(card.get_by_label('Deliver the synthetic review status')).to_contain_text('Paused: daily tasks budget reached', timeout=20000)
            check('a goal whose budget is spent shows it was paused by the budget')
            check('the server agrees the goal is paused by its budget', state(spent['id'])['state_reason'] == 'budget_daily_tasks')
            expect(card).to_contain_text('2 tasks of 2 tasks today')
            expect(card).to_contain_text('research: suggest (1)')
            expect(card).to_contain_text('company scope · assigned to synthetic')
            check('the card shows mandate, autonomy per kind of work and measured budget use')
            expect(dialog.get_by_label('Budget attention')).to_contain_text('Goal Deliver the synthetic review · tasks today')
            expect(dialog.get_by_label('Budget attention')).to_contain_text('limit reached, paused')
            check('the hard stop is listed as an attention item')
            expect(dialog).to_contain_text('1 active goal has no mandate')
            check('goals without a mandate are counted, not worked on')
            page.wait_for_timeout(400)
            dialog.screenshot(path=str(out / 'goals-desktop.png'))
            card.get_by_role('button', name='Resume Deliver the synthetic review').click()
            expect(dialog.get_by_role('alert')).to_contain_text('still spent')
            check('resuming while the budget is still spent is refused by the server')
            second = dialog.locator('article', has=page.get_by_role('heading', name='Prepare the sample schedule'))
            second.get_by_role('button', name='Pause Prepare the sample schedule').click()
            expect(second.get_by_label('Prepare the sample schedule status')).to_contain_text('Paused by you')
            check('pause goes to the server and the card shows it', state(running['id'])['state'] == 'paused')
            second.get_by_role('button', name='Resume Prepare the sample schedule').click()
            expect(second.get_by_label('Prepare the sample schedule status')).to_contain_text('Running')
            check('resume goes to the server', state(running['id'])['state'] == 'active')
            brain = dialog.get_by_label('Brain synthetic', exact=True)
            brain.get_by_role('button', name='Pause brain synthetic').click()
            expect(brain.get_by_label('Brain synthetic status')).to_contain_text('Paused by you')
            check('a brain can be paused', next(b for b in hub.view(owner)['brains'] if b['id'] == 'synthetic')['state'] == 'paused')
            brain.get_by_role('button', name='Resume brain synthetic').click()
            expect(brain.get_by_label('Brain synthetic status')).to_contain_text('Running')
            second.get_by_role('button', name='Stop Prepare the sample schedule').click()
            confirm = second.get_by_role('group', name='Confirm stop Prepare the sample schedule')
            expect(confirm).to_contain_text('Stopping is final')
            check('stop asks for confirmation first', state(running['id'])['state'] == 'active')
            confirm.get_by_role('button', name='Stop for good').click()
            expect(second.get_by_label('Prepare the sample schedule status')).to_contain_text('Stopped')
            check('stop goes to the server', state(running['id'])['state'] == 'stopped')
            entries = lifecycle.entries(lifecycle.journal_path(store))
            check('the stop is written to the lifecycle journal', [e['subject'] for e in entries if e['kind'] == 'hub_stopped']
                  == ['goal:' + running['id']])
            check('a stopped goal offers no controls', second.get_by_role('button').count() == 0)
            page.set_viewport_size({'width': 390, 'height': 844})
            page.wait_for_timeout(300)
            check('no horizontal scroll at phone width', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
            page.screenshot(path=str(out / 'goals-phone.png'))
            context.close()
            # A reader key sees that goals belong to the owner, and nothing else.
            reader = browser.new_context(viewport={'width': 1280, 'height': 800}).new_page()
            reader.on('pageerror', lambda e: page_errors.append(str(e)))
            reader.on('request', lambda r: foreign.append(r.url) if not r.url.startswith(server.origin) else None)
            reader.goto(server.origin + '/console')
            reader.get_by_label('Access key').fill(keys['reader']); reader.get_by_role('button', name='Sign in').click()
            expect(reader.locator('.connection-state')).to_have_text('Connected')
            command = reader.get_by_label('Command or search')
            command.fill('goals'); command.press('Enter')
            expect(reader.get_by_role('dialog')).to_contain_text('Goals are set by the workspace owner')
            check('a reader sees no goals and no controls', 'Deliver the synthetic review' not in reader.get_by_role('dialog').inner_text())
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
