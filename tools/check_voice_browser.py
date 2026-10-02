"""Browser-to-backend acceptance for read-aloud (VOI-001, output only).

Runs the real loopback server over the synthetic demo vault, serves the built console
and drives it in Chromium. The first context uses the browser's real speech API: in this
headless build no on-device voice exists, so nothing may be spoken and nothing recorded.
The second context replaces the speech API with a scripted on-device synthesiser so that
the generated, played, stopped and acknowledged states can be exercised. That is not an
audio or hardware test. No microphone is requested in either. Requires `npm run build`.

The page shows a played or stopped state first and reports it to the server afterwards, so
the server here records each outcome late on purpose and the check waits for the record:
it never depends on the report arriving before the page updates.
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
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.desk_http import DeskHTTPServer
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'console' / 'dist'
out = Path(os.environ.get('ALFRED_VOICE_OUTPUT', ROOT / 'docs' / 'evidence' / 'voice'))
out.mkdir(parents=True, exist_ok=True)
checks, page_errors, voice_requests, foreign = [], [], [], []
SCRIPTED_SYNTHESISER = """(() => {
  const voice = {name: 'Scripted on-device voice', lang: 'en-GB', localService: true, default: true, voiceURI: 'scripted'};
  const synth = {speaking: false, pending: false, paused: false,
    getVoices() { return [voice]; }, addEventListener() {}, removeEventListener() {},
    speak(u) { window.__spoken = (window.__spoken || []).concat([u.text]); window.__utterance = u;
      setTimeout(() => { u.onstart && u.onstart({}); if (!window.__holdPlayback) setTimeout(() => u.onend && u.onend({}), 300); }, 50); },
    cancel() { const u = window.__utterance; if (u && u.onerror) u.onerror({error: 'interrupted'}); },
    pause() {}, resume() {}};
  Object.defineProperty(window, 'speechSynthesis', {value: synth, configurable: true});
  window.SpeechSynthesisUtterance = function (text) { this.text = text; this.voice = null; this.lang = ''; };
})();"""
NO_MICROPHONE = """(() => { if (navigator.mediaDevices) navigator.mediaDevices.getUserMedia = () => { window.__microphoneRequested = true; return Promise.reject(new Error('refused')); }; })();"""


def check(name, condition=True):
    assert condition, name
    checks.append(name)


if not (DIST / 'index.html').is_file():
    raise SystemExit('Build the console first: cd console && npm run build')

with tempfile.TemporaryDirectory() as temp:
    home = Path(temp) / 'demo'; keys = init_demo(home)
    store = KnowledgeStore(home / 'desk.sqlite')
    sup = KnowledgeSupervisor(store, keys['owner'], keys['source'], home / 'project', vault=home / 'vault', interval=.2)
    sup.cycle(); sup.start()
    server = DeskHTTPServer(store, sup, port=0, console_dist=DIST)
    report_now = server.voice.report

    def report_late(*args, **kwargs):
        time.sleep(.6)  # A slow machine: the page has already moved on when this is written.
        return report_now(*args, **kwargs)
    server.voice.report = report_late
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); thread.start()

    def records():
        with store.connection() as db:
            # Creation order: identifiers are random, so they cannot break a tie within one second.
            return [dict(r) for r in db.execute('SELECT * FROM voice_playbacks ORDER BY created,rowid')]

    def settled(condition, timeout=10.0):
        """True once the server's records satisfy the condition; the report is sent after the page updates."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return True
            time.sleep(.05)
        return condition()

    def open_answer(context):
        page = context.new_page()
        page.on('pageerror', lambda e: page_errors.append(str(e)))
        page.on('request', lambda r: voice_requests.append(r.url) if '/desk/voice/' in r.url else None)
        page.on('request', lambda r: foreign.append(r.url) if not r.url.startswith(server.origin) else None)
        page.goto(server.origin + '/console/')
        page.get_by_label('Access key').fill(keys['owner']); page.get_by_role('button', name='Sign in').click()
        expect(page.locator('.connection-state')).to_have_text('Connected', timeout=15000)
        command = page.get_by_label('Command or search')
        command.fill('What still needs confirming?'); command.press('Enter')
        ask = page.get_by_role('dialog')
        expect(ask.locator('.evidence').first).to_be_visible(timeout=15000)
        return page, ask

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'), headless=True,
                                        args=['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            # 1. The browser's real speech API, with no on-device voice in this build.
            real = browser.new_context(viewport={'width': 1280, 'height': 860}, reduced_motion='reduce')
            real.add_init_script(NO_MICROPHONE)
            page, ask = open_answer(real)
            local = page.evaluate("speechSynthesis.getVoices().filter(v => v.localService).length")
            if local == 0:
                ask.get_by_role('button', name='Read aloud').click()
                expect(ask.get_by_role('status').filter(has_text='No on-device voice')).to_be_visible(timeout=10000)
                check('without an on-device voice nothing is spoken and nothing is recorded', not voice_requests and records() == [])
                page.screenshot(path=str(out / 'voice-no-local-voice.png'))
            else:
                check(f'this browser offers {local} on-device voice(s); the no-voice path is covered by unit tests')
            check('no microphone was requested by the real-API page', page.evaluate('window.__microphoneRequested === undefined'))
            real.close()
            # 2. A scripted on-device synthesiser: states, records and acknowledgement.
            scripted = browser.new_context(viewport={'width': 1280, 'height': 860}, reduced_motion='reduce')
            scripted.add_init_script(SCRIPTED_SYNTHESISER); scripted.add_init_script(NO_MICROPHONE)
            page, ask = open_answer(scripted)
            ask.get_by_role('button', name='Read aloud').click()
            expect(ask.get_by_role('status').filter(has_text='reported that playback ended')).to_be_visible(timeout=10000)
            ask.locator('.spoken-text summary').click()
            shown = ask.locator('.spoken-text p').inner_text().strip()
            spoken = page.evaluate('window.__spoken')
            check('exactly the text shown is the text spoken', spoken == [shown] and shown.startswith('You asked: What still needs confirming?'))
            check('the spoken text says it is the notes read aloud, not a generated answer', shown.endswith('not a generated answer.'))
            check('played is recorded as a device report, not as heard',
                  settled(lambda: [r['outcome'] for r in records()] == ['ended']) and records()[0]['acknowledged'] is None)
            page.screenshot(path=str(out / 'voice-played.png'))
            ask.get_by_role('button', name='I heard this').click()
            expect(ask.get_by_role('status').filter(has_text='You confirmed that you heard it')).to_be_visible(timeout=10000)
            check('acknowledgement is a separate, explicit record', records()[0]['acknowledged'] is not None)
            check('the server holds a hash and length, never the spoken text', shown not in json.dumps(records()) and records()[0]['characters'] == len(shown))
            page.evaluate('window.__holdPlayback = true')
            earlier = {r['id'] for r in records()}
            ask.get_by_role('button', name='Read again').click()
            expect(ask.get_by_role('status').filter(has_text='Playing on this device')).to_be_visible(timeout=10000)
            ask.get_by_role('button', name='Stop').click()
            expect(ask.get_by_role('status').filter(has_text='stopped before the end')).to_be_visible(timeout=10000)
            check('a stopped playback is recorded as stopped and cannot be acknowledged',
                  settled(lambda: [r['outcome'] for r in records() if r['id'] not in earlier] == ['stopped'])
                  and ask.get_by_role('button', name='I heard this').count() == 0)
            page.keyboard.press('Escape')
            page.get_by_role('button', name='Voice connection information').click()
            check('the voice dialog says nothing is listening', 'No microphone permission is ever requested' in page.get_by_role('dialog').inner_text())
            check('no microphone was requested by the scripted page', page.evaluate('window.__microphoneRequested === undefined'))
            check('no requests leave the loopback origin', not foreign)
            check('no uncaught page errors', not page_errors)
            browser.close()
    finally:
        sup.stop()
        server.shutdown(); server.server_close()

report = {'passed': len(checks), 'checks': checks, 'page_errors': page_errors, 'audio_hardware_tested': False,
          'synthesiser': 'scripted on-device stub in the second context; real speech API in the first', 'microphone': 'never requested'}
(out / 'browser-report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'passed': len(checks), 'page_errors': page_errors}))
