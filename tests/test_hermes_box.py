"""The sealed Hermes box (docs/HERMES_BOX.md; docs/AGENT_HUB.md step H5), offline.

No Docker, no Hermes and no network: a stand-in box speaks the runner's protocol in this
process, and a stand-in model answers for the provider. The same checks run against the real
box, with real Hermes inside, in tools/hermes_fence.py (CI job hermes-box). Synthetic data only;
addresses are assembled at run time so the public hygiene check never sees a literal one.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest

from alfred import brain as plug
from alfred import hermes_box as hb
from alfred.brain import BrainBackend, BrainFailure, BrainPolicy, BrainRegistry, BudgetExceeded, Meter, Stopped
from alfred.local import Fault
from test_brain_plug import sample_packet

ROOT = Path(__file__).resolve().parents[1]
BOX = ROOT / 'boxes' / 'hermes'
PIN = json.loads((BOX / 'pin.json').read_text(encoding='utf-8'))
IMAGE = 'sha256:' + 'c' * 64
NAME = 'alfred-hermes-' + '1' * 16
MODEL = 'stand-in-model'
BUDGET = {'wall_seconds': 30, 'tokens': 5000, 'money_pence': 0, 'steps': 50}
QUOTE = 'Alpha review is due on Friday.'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_settings_file(path):
    """The box's YAML file, flattened to dotted names. Its subset only: nested mappings,
    inline lists, quoted strings, booleans and integers; comments after #."""
    out, stack = {}, []
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.split(' #', 1)[0].rstrip() if not raw.lstrip().startswith('#') else ''
        if not line.strip():
            continue
        depth = (len(line) - len(line.lstrip())) // 2
        key, _, value = line.strip().partition(':')
        stack[depth:] = [key]
        value = value.strip()
        if not value:
            continue
        if value.startswith('['):
            parsed = [v.strip() for v in value.strip('[]').split(',') if v.strip()]
        elif value in ('true', 'false'):
            parsed = value == 'true'
        elif value.startswith('"'):
            parsed = value.strip('"')
        elif value.isdigit():
            parsed = int(value)
        else:
            parsed = value
        out['.'.join(stack)] = parsed
    return out


def good_hello(**changes):
    hello = {'type': 'hello', 'protocol': 1, 'pin': PIN, 'settings': dict(hb.OVERRIDES),
             'plugins': {'loaded': [{'name': 'alfred_gate', 'source': 'user'}, {'name': 'openai', 'source': 'bundled'}],
                         'hooks': {'pre_tool_call': ['hermes_plugins.alfred_gate']}},
             'network': {'dns': 'blocked', 'outbound': 'blocked'}, 'user': 10001}
    hello.update(changes)
    return hello


def sse(text=None, *, tool=None, input_tokens=100, output_tokens=20, cache=0):
    block = {'type': 'text', 'text': text or ''}
    events = [{'type': 'message_start', 'message': {'usage': {'input_tokens': input_tokens, 'output_tokens': 1,
                                                              'cache_read_input_tokens': cache}}},
              {'type': 'content_block_start', 'index': 0, 'content_block': block},
              {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn'}, 'usage': {'output_tokens': output_tokens}},
              {'type': 'message_stop'}]
    return ''.join(f'event: {e["type"]}\ndata: {json.dumps(e)}\n\n' for e in events).encode()


class StandInModel(hb.ModelProvider):
    """Answers every call with one stored reply and records what it was sent."""

    def __init__(self, status=200, content_type='text/event-stream', body=None, locality='cloud'):
        self.status, self.content_type, self.body, self.locality = status, content_type, body or sse('ok'), locality
        self.sent = []

    def call(self, body, betas, timeout):
        self.sent.append((json.loads(body), betas))
        return self.status, self.content_type, self.body


def request(**changes):
    body = {'model': MODEL, 'messages': [{'role': 'user', 'content': 'Hello.'}], 'max_tokens': 128000, 'stream': True}
    body.update(changes)
    return {'type': 'model_request', 'id': 7, 'method': 'POST', 'path': '/v1/messages',
            'betas': 'interleaved-thinking-2025-05-14,something-else', 'body': json.dumps(body)}


def reply_text(**changes):
    reply = {'answer': f'{QUOTE} [E1]', 'citations': [{'ref': 'E1', 'quote': QUOTE}], 'drafts': [], 'remember': []}
    reply.update(changes)
    return json.dumps(reply)


class StandInBox:
    """Plays the runner: a hello, then for each step of a script a frame, checking ALFRED's
    reply. ``script`` items are ('model', request frame), ('tool', name, args) or
    ('final', text) or ('error',) or ('silent',)."""

    def __init__(self, script, hello=None):
        self.script, self.hello = list(script), hello or good_hello()
        self.received, self.stopped, self.started = [], False, None
        self.queue = [self.hello]

    def __call__(self, command, name):
        self.started = (command, name)
        return self

    def read(self, timeout):
        if self.queue:
            return self.queue.pop(0)
        if not self.script:
            raise BrainFailure('hermes_box_closed')
        step = self.script.pop(0)
        if step[0] == 'model':
            return dict(step[1])
        if step[0] == 'tool':
            return {'type': 'tool_check', 'id': 3, 'tool': step[1], 'args': step[2]}
        if step[0] == 'final':
            return {'type': 'final', 'text': step[1], 'left': [{'path': '.hermes/state.db', 'bytes': 1}]}
        if step[0] == 'error':
            return {'type': 'error', 'code': 'ValueError'}
        time.sleep(timeout)
        self.script.insert(0, step)
        return None

    def send(self, frame):
        self.received.append(frame)

    def stop(self):
        self.stopped = True


def brain(box, provider=None, **options):
    return hb.HermesBrain(image_id=IMAGE, pin=PIN, provider=provider or StandInModel(), model=MODEL, launch=box,
                          **options)


class SettingsAndPins(unittest.TestCase):
    def test_the_settings_file_is_the_table_alfred_checks(self):
        self.assertEqual(read_settings_file(BOX / 'config.yaml'), hb.OVERRIDES)

    def test_every_default_docs_agent_hub_lists_is_overridden(self):
        for name, value in {'auth.adopt_external_logins': False, 'approvals.mode': 'manual',
                            'memory.memory_enabled': False, 'memory.user_profile_enabled': False,
                            'memory.write_approval': True, 'skills.write_approval': True,
                            'auxiliary.background_review.enabled': False, 'curator.enabled': False,
                            'security.allow_lazy_installs': False, 'updates.check': False,
                            'telemetry.shared_metrics.enabled': False}.items():
            self.assertEqual(hb.OVERRIDES[name], value, name)

    def test_the_pins_hold_for_the_files_in_this_repository(self):
        build = load(ROOT / 'tools' / 'build_hermes_box.py', 'build_hermes_box')
        build.check_box(PIN)
        self.assertEqual(hashlib.sha256((BOX / 'requirements.lock').read_bytes()).hexdigest(), PIN['requirements']['sha256'])
        self.assertEqual(PIN['hermes']['commit'], '8fe53200c7fcb65ef0650d6ede59b28d5cd761e9')
        lines = (BOX / 'requirements.lock').read_text(encoding='utf-8').splitlines()
        pinned = [line for line in lines if line and not line.startswith((' ', '#'))]
        # Every line is an exact version with hashes, except one Android-only line pip never installs here.
        self.assertTrue(pinned and all(('==' in line and line.endswith('\\')) or line.endswith("sys_platform == 'android'")
                                       for line in pinned))

    def test_a_changed_lock_breaks_the_pin(self):
        build = load(ROOT / 'tools' / 'build_hermes_box.py', 'build_hermes_box')
        changed = json.loads(json.dumps(PIN))
        changed['requirements']['sha256'] = '0' * 64
        with self.assertRaises(build.PinBroken):
            build.check_box(changed)
        changed = json.loads(json.dumps(PIN))
        changed['base_image']['digest'] = 'sha256:' + '0' * 64
        with self.assertRaises(build.PinBroken):
            build.check_box(changed)

    def test_the_dockerfile_runs_the_runner_as_the_box_user_with_no_pip_left(self):
        dockerfile = (BOX / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('USER 10001:10001', dockerfile)
        self.assertIn('--require-hashes --only-binary=:all:', dockerfile)
        self.assertIn('rm -rf /opt/venv/bin/pip*', dockerfile)
        self.assertIn('ENTRYPOINT ["/opt/venv/bin/python", "-I", "/opt/alfred-box/runner/alfred_box.py"]', dockerfile)


class DockerCommand(unittest.TestCase):
    def test_the_exact_sealed_run_line(self):
        command = hb.docker_command(IMAGE, NAME)
        self.assertEqual(command, [
            'docker', 'run', '--rm', '--interactive', '--name', NAME, '--pull', 'never', '--network', 'none',
            '--read-only', '--init', '--user', '10001:10001', '--cap-drop', 'ALL', '--security-opt',
            'no-new-privileges', '--pids-limit', '256', '--memory', '2g', '--memory-swap', '2g', '--cpus', '2',
            '--ulimit', 'nofile=1024:1024', '--log-driver', 'none',
            '--tmpfs', '/hermes-home:rw,nosuid,nodev,size=128m,mode=0700,uid=10001,gid=10001',
            '--tmpfs', '/work:rw,nosuid,nodev,noexec,size=16m,mode=0700,uid=10001,gid=10001',
            '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777', IMAGE])
        self.assertFalse(any(part in ('-v', '--volume', '--mount', '--env-file', '-e', '--env', '-p', '--publish')
                             for part in command))

    def test_an_image_by_tag_or_a_strange_name_is_refused(self):
        for image in ('alfred/hermes-box:latest', 'sha256:abc', ''):
            with self.assertRaises(Fault) as caught:
                hb.docker_command(image, NAME)
            self.assertEqual(caught.exception.code, 'hermes_image_not_pinned')
        for name in ('box', 'alfred-hermes-1; rm -rf /', NAME + '0'):
            with self.assertRaises(Fault):
                hb.docker_command(IMAGE, name)


class LoadBox(unittest.TestCase):
    """What a host checks when it starts: the build record, pin.json and the image agree."""
    DIGEST = hashlib.sha256((BOX / 'pin.json').read_bytes()).hexdigest()

    def inspect(self, labels):
        self.asked = []

        def inspect(image, docker):
            self.asked.append((image, docker))
            return labels
        return inspect

    def test_an_image_built_from_these_pins_loads(self):
        record = {'image': IMAGE, 'pin_sha256': self.DIGEST, 'tag': 'alfred/hermes-box:8fe53200c7fc'}
        image, pin = hb.load_box(record, docker='/usr/bin/docker', inspect=self.inspect({hb.PIN_LABEL: self.DIGEST}))
        self.assertEqual((image, pin, self.asked), (IMAGE, PIN, [(IMAGE, '/usr/bin/docker')]))
        self.assertEqual(hb.PIN_FILE, BOX / 'pin.json')

    def test_a_record_or_image_from_other_pins_is_refused(self):
        cases = [({'image': 'alfred/hermes-box:latest', 'pin_sha256': self.DIGEST}, {}, 'invalid_hermes_record'),
                 ({'pin_sha256': self.DIGEST}, {}, 'invalid_hermes_record'),
                 ('not a record', {}, 'invalid_hermes_record'),
                 ({'image': IMAGE, 'pin_sha256': '0' * 64}, {hb.PIN_LABEL: self.DIGEST}, 'hermes_record_not_this_pin'),
                 ({'image': IMAGE, 'pin_sha256': self.DIGEST}, {hb.PIN_LABEL: '0' * 64}, 'hermes_image_not_pinned'),
                 ({'image': IMAGE, 'pin_sha256': self.DIGEST}, {}, 'hermes_image_not_pinned'),
                 ({'image': IMAGE, 'pin_sha256': self.DIGEST}, None, 'hermes_image_not_pinned')]
        for record, labels, code in cases:
            with self.subTest(code=code, record=record), self.assertRaises(Fault) as caught:
                hb.load_box(record, inspect=self.inspect(labels))
            self.assertEqual(caught.exception.code, code)


class Hello(unittest.TestCase):
    def refused(self, hello):
        with self.assertRaises(BrainFailure) as caught:
            hb.check_hello(hello, PIN)
        return caught.exception.reason

    def test_a_good_hello_passes(self):
        hb.check_hello(good_hello(), PIN)

    def test_each_mismatch_refuses_the_box(self):
        changed = dict(hb.OVERRIDES, **{'memory.memory_enabled': True})
        self.assertEqual(self.refused(good_hello(settings=changed)), 'hermes_box_settings_not_in_force')
        missing = dict(hb.OVERRIDES)
        missing['curator.enabled'] = {'missing': True}
        self.assertEqual(self.refused(good_hello(settings=missing)), 'hermes_box_settings_not_in_force')
        other_pin = json.loads(json.dumps(PIN))
        other_pin['hermes']['commit'] = '0' * 40
        self.assertEqual(self.refused(good_hello(pin=other_pin)), 'hermes_box_not_pinned_build')
        self.assertEqual(self.refused(good_hello(network={'dns': 'open', 'outbound': 'blocked'})),
                         'hermes_box_network_reachable')
        self.assertEqual(self.refused(good_hello(user=0)), 'hermes_box_wrong_user')
        self.assertEqual(self.refused(good_hello(protocol=2)), 'hermes_box_no_hello')
        self.assertEqual(self.refused({'type': 'final'}), 'hermes_box_no_hello')

    def test_another_plugin_or_another_tool_hook_refuses_the_box(self):
        extra = good_hello()['plugins']
        extra['loaded'].append({'name': 'helpful', 'source': 'user'})
        self.assertEqual(self.refused(good_hello(plugins=extra)), 'hermes_box_gate_not_loaded')
        second = good_hello()['plugins']
        second['hooks']['pre_tool_call'].append('hermes_plugins.helpful')
        self.assertEqual(self.refused(good_hello(plugins=second)), 'hermes_box_gate_not_loaded')
        none = good_hello()['plugins']
        none['hooks'] = {}
        self.assertEqual(self.refused(good_hello(plugins=none)), 'hermes_box_gate_not_loaded')
        self.assertEqual(self.refused(good_hello(plugins=[])), 'hermes_box_gate_not_loaded')


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.model = StandInModel()
        self.meter = Meter(BUDGET)
        self.relay = hb.Relay(self.model, self.meter, model=MODEL)

    def test_a_call_goes_out_capped_and_is_charged_from_the_usage_report(self):
        answer = self.relay.handle(request())
        self.assertEqual((answer['type'], answer['id'], answer['status'], answer['content_type']),
                         ('model_response', 7, 200, 'text/event-stream'))
        sent, betas = self.model.sent[0]
        # Both betas Hermes sends are standard on current models, so none is passed on.
        self.assertEqual((betas, hb.BETAS), ((), frozenset()))
        estimate = -(-len(json.dumps(json.loads(request()['body']), ensure_ascii=False).encode()) // 2)
        self.assertEqual(sent['max_tokens'], BUDGET['tokens'] - estimate)
        self.assertEqual(self.meter.snapshot(), {'steps': 1, 'tokens': 120, 'money_pence': 0})

    def test_anything_but_the_messages_call_is_answered_here(self):
        for frame in (dict(request(), path='/api/show'), dict(request(), method='GET'),
                      dict(request(), path='/v1/messages?beta=true'), request(model='another-model'),
                      request(metadata={'user_id': 'x'}), request(mcp_servers=[{'url': 'x'}]),
                      request(tools=[{'type': 'web_search_20250305', 'name': 'web_search'}]),
                      dict(request(), body='not json')):
            answer = self.relay.handle(frame)
            self.assertIn(answer['status'], (400, 404))
        self.assertEqual(self.model.sent, [])
        self.assertEqual((self.relay.calls, self.relay.refused), (0, 8))
        self.assertEqual(self.meter.snapshot()['steps'], 0)

    def test_ordinary_tools_pass(self):
        self.relay.handle(request(tools=[{'name': 'read_file', 'input_schema': {}},
                                         {'type': 'custom', 'name': 'x', 'input_schema': {}}]))
        self.assertEqual(len(self.model.sent), 1)

    def test_no_room_left_stops_before_the_call(self):
        meter = Meter(dict(BUDGET, tokens=100))
        with self.assertRaises(BudgetExceeded):
            hb.Relay(self.model, meter, model=MODEL).handle(request())
        self.assertEqual(self.model.sent, [])

    def test_money_limits_the_room_too(self):
        meter = Meter(dict(BUDGET, tokens=1_000_000, money_pence=1), pence_per_1k_tokens=10)
        relay = hb.Relay(self.model, meter, model=MODEL, price=10)
        self.assertEqual(relay.remaining_tokens(), 100)

    def test_a_missing_usage_report_is_charged_in_full(self):
        relay = hb.Relay(StandInModel(content_type='application/json', body=b'{"content": []}'), self.meter, model=MODEL)
        relay.handle(request(max_tokens=200))
        estimate = -(-len(json.dumps(json.loads(request(max_tokens=200)['body']), ensure_ascii=False).encode()) // 2)
        self.assertEqual(self.meter.snapshot()['tokens'], estimate + 200)

    def test_a_refused_call_costs_nothing_but_a_step(self):
        relay = hb.Relay(StandInModel(status=429, content_type='application/json', body=b'{}'), self.meter, model=MODEL)
        self.assertEqual(relay.handle(request())['status'], 429)
        self.assertEqual(self.meter.snapshot(), {'steps': 1, 'tokens': 0, 'money_pence': 0})

    def test_usage_is_read_from_streams_and_plain_replies(self):
        self.assertEqual(hb.usage_tokens('text/event-stream', sse('x', input_tokens=10, output_tokens=7, cache=5)), 22)
        self.assertEqual(hb.usage_tokens('application/json', json.dumps(
            {'usage': {'input_tokens': 3, 'output_tokens': 4, 'cache_creation_input_tokens': 2}}).encode()), 9)
        self.assertIsNone(hb.usage_tokens('application/json', b'{}'))
        self.assertIsNone(hb.usage_tokens('text/event-stream', b'data: {"type": "ping"}\n\n'))
        self.assertIsNone(hb.usage_tokens('application/json', b'\xff'))


class Gate(unittest.TestCase):
    def test_nothing_is_allowed_unless_granted(self):
        gate = hb.ToolGate([])
        for tool in ('read_file', 'memory', 'skill_manage', 'terminal', 'tool_call', 'delegate_task', ''):
            allowed, message, name = gate.decide(tool, {'path': '/work/E1.md'})
            self.assertEqual((allowed, name), (False, None))
            self.assertTrue(message.startswith('ALFRED has not granted the tool'))

    def test_a_granted_read_stays_inside_work(self):
        gate = hb.ToolGate(['file.read'])
        self.assertEqual(gate.decide('read_file', {'path': '/work/E1.md'}), (True, '', 'file.read'))
        self.assertEqual(gate.decide('search_files', {'pattern': 'x', 'path': 'E1.md'}), (True, '', 'file.read'))
        for path in ('/etc/passwd', '/work/../etc/passwd', '../hermes-home/.hermes/config.yaml', '/workshop/x',
                     '', 'a\x00b', 7):
            self.assertEqual(gate.decide('read_file', {'path': path})[0], False, path)
        self.assertEqual(gate.decide('write_file', {'path': '/work/x', 'content': 'y'})[0], False)
        self.assertEqual(gate.decide('read_file', ['/work/E1.md'])[0], False)

    def test_a_tool_the_box_does_not_offer_cannot_be_granted(self):
        with self.assertRaises(Fault) as caught:
            hb.ToolGate(['calculator'])
        self.assertEqual(caught.exception.code, 'tool_not_available_in_hermes_box')


class Reply(unittest.TestCase):
    def test_a_reply_becomes_a_well_formed_bundle(self):
        bundle = hb.build_bundle('```json\n' + reply_text(drafts=[{'text': 'Thanks for Friday.'}],
                                                          remember=[{'statement': 'Reviews are on Fridays.',
                                                                     'cites': ['E1']}]) + '\n```', [])
        plug.validate_bundle(bundle)
        self.assertEqual(bundle['proposed_actions'][0]['capability'], 'message.draft')
        self.assertEqual(bundle['memory_suggestions'], [{'statement': 'Reviews are on Fridays.', 'cites': ['E1']}])
        self.assertIsNone(plug.check_bundle(sample_packet(), bundle))

    def test_text_around_the_object_is_tolerated_but_the_shape_is_not_negotiable(self):
        self.assertEqual(hb.build_bundle('Here it is: ' + reply_text() + ' Done.', [])['answer']['text'],
                         f'{QUOTE} [E1]')
        for bad in ('not json', reply_text(actions=[{'capability': 'message.send'}]), json.dumps({'answer': 'x'}),
                    reply_text(answer=' '), reply_text(drafts=[{'text': 'x', 'to': 'y'}]), reply_text(citations={})):
            with self.assertRaises(Fault) as caught:
                hb.build_bundle(bad, [])
            self.assertEqual(caught.exception.code, 'hermes_reply_not_in_shape')

    def test_a_misquote_is_left_for_the_hub_to_refuse(self):
        bundle = hb.build_bundle(reply_text(citations=[{'ref': 'E1', 'quote': 'paraphrased'}]), [])
        self.assertEqual(plug.check_bundle(sample_packet(), bundle), 'citation_quote_not_literal')

    def test_the_task_carries_the_excerpts_and_limits_and_nothing_else(self):
        packet = sample_packet(tools=['file.read'], budget=dict(BUDGET))
        task = hb.build_task(packet, model=MODEL, max_output_tokens=512)
        self.assertEqual(set(task), {'type', 'protocol', 'model', 'system', 'prompt', 'files', 'toolsets',
                                     'max_iterations', 'wall_seconds', 'max_tokens'})
        self.assertEqual(task['files'], {'E1.md': f'# Plan\n\n{QUOTE}\n'})
        self.assertEqual((task['toolsets'], task['max_iterations'], task['wall_seconds'], task['max_tokens']),
                         (['file'], 50, 30, 512))
        self.assertIn(f'[E1] Plan\n{QUOTE}', task['prompt'])
        self.assertNotIn(packet['context'][0]['note_id'], json.dumps(task))


class Runs(unittest.TestCase):
    def run_brain(self, box, packet=None, meter=None, **options):
        b = brain(box, **options)
        return b, b.run(packet or sample_packet(budget=dict(BUDGET)), meter or Meter(BUDGET))

    def test_a_whole_task_through_the_box(self):
        box = StandInBox([('model', request()), ('tool', 'terminal', {'command': 'id'}), ('model', request()),
                          ('final', reply_text())])
        b, bundle = self.run_brain(box)
        self.assertTrue(box.stopped)
        kinds = [f['type'] for f in box.received]
        self.assertEqual(kinds, ['task', 'model_response', 'tool_decision', 'model_response'])
        self.assertEqual(box.received[2], {'type': 'tool_decision', 'id': 3, 'allow': False,
                                           'message': 'ALFRED has not granted the tool terminal for this task.'})
        self.assertEqual(box.started[0], hb.docker_command(IMAGE, box.started[1]))
        self.assertEqual([e['kind'] for e in bundle['work_log']], ['read', 'reason', 'reason', 'reason', 'write'])
        self.assertIsNone(plug.check_bundle(sample_packet(), bundle))
        self.assertEqual((b.last_report.model_calls, b.last_report.tools, b.last_report.ended),
                         (2, [{'tool': 'terminal', 'allowed': False}], 'final'))

    def test_a_box_that_fails_its_hello_gets_nothing(self):
        box = StandInBox([('final', reply_text())], hello=good_hello(network={'dns': 'open', 'outbound': 'open'}))
        with self.assertRaises(BrainFailure) as caught:
            self.run_brain(box)
        self.assertEqual(caught.exception.reason, 'hermes_box_network_reachable')
        self.assertEqual(box.received, [])
        self.assertTrue(box.stopped)

    def test_the_box_is_removed_whatever_happens(self):
        for script, expected in (([('error',)], BrainFailure), ([('final', 'nonsense')], Fault),
                                 ([('model', request())] * 60, BudgetExceeded)):
            box = StandInBox(script)
            with self.assertRaises(expected):
                self.run_brain(box, meter=Meter(dict(BUDGET, steps=3)))
            self.assertTrue(box.stopped)

    def test_a_cancel_stops_the_box(self):
        meter = Meter(BUDGET)
        box = StandInBox([('silent',)])
        threading.Timer(0.3, meter.cancelled.set).start()
        with self.assertRaises(Stopped):
            self.run_brain(box, meter=meter)
        self.assertTrue(box.stopped)

    def test_the_deadline_stops_the_box(self):
        clock = [0.0]
        meter = Meter(dict(BUDGET, wall_seconds=1), clock=lambda: clock[0])
        box = StandInBox([('silent',)])
        threading.Timer(0.3, lambda: clock.__setitem__(0, 5.0)).start()
        with self.assertRaises(BudgetExceeded):
            self.run_brain(box, meter=meter)
        self.assertTrue(box.stopped)

    def test_the_brain_declares_what_its_provider_is(self):
        self.assertEqual(brain(StandInBox([])).spec.locality, 'cloud')
        self.assertEqual(brain(StandInBox([]), StandInModel(locality='local')).spec.locality, 'local')
        self.assertEqual(brain(StandInBox([])).spec.version, PIN['hermes']['commit'])
        for bad in ({'tools': frozenset({'calculator'})}, {'extra_toolsets': ('Bad name',)}):
            with self.assertRaises(Fault):
                brain(StandInBox([]), **bad)
        with self.assertRaises(Fault):
            hb.HermesBrain(image_id=IMAGE, pin=PIN, provider=StandInModel(), model='Bad Model', launch=StandInBox([]))


class Backend(unittest.TestCase):
    """Through the plug's real backend: the policy decides first, and the box's reasons arrive."""

    def submit(self, b, packet, cloud_scopes=()):
        registry = BrainRegistry()
        registry.register(b)
        backend = BrainBackend(registry, BrainPolicy(cloud_scopes=cloud_scopes))
        inputs = [{'data': ('# Plan\n' + QUOTE + '\n').encode()}]
        backend.submit('job-1.1', plug.KIND, {'brain': 'hermes', 'packet': packet}, inputs)
        return backend.collect('job-1.1', timeout=10)

    def test_a_cloud_hermes_is_refused_for_an_area_not_allowed_and_nothing_starts(self):
        box = StandInBox([('final', reply_text())])
        with self.assertRaises(Fault) as caught:
            self.submit(brain(box), sample_packet(budget=dict(BUDGET)))
        self.assertEqual(caught.exception.code, 'cloud_brain_refused_for_scope')
        self.assertIsNone(box.started)

    def test_an_allowed_area_runs_and_a_box_refusal_keeps_its_reason(self):
        result = self.submit(brain(StandInBox([('final', reply_text())])), sample_packet(budget=dict(BUDGET)),
                             cloud_scopes={'personal'})
        self.assertTrue(result.ok)
        envelope = json.loads(result.output)
        self.assertEqual((envelope['brain'], envelope['brain_version']), ('hermes', PIN['hermes']['commit']))
        changed = dict(hb.OVERRIDES, **{'approvals.mode': 'smart'})
        result = self.submit(brain(StandInBox([], hello=good_hello(settings=changed))),
                             sample_packet(budget=dict(BUDGET)), cloud_scopes={'personal'})
        self.assertEqual((result.ok, result.reason), (False, 'hermes_box_settings_not_in_force'))


class FailureReasons(unittest.TestCase):
    def test_a_reason_must_be_a_job_reason_code(self):
        self.assertEqual(BrainFailure('hermes_box_silent').reason, 'hermes_box_silent')
        for bad in ('Not A Code', 'x' * 65, '', None, 'with space'):
            self.assertEqual(BrainFailure(bad).reason, 'brain_error')


class RunnerLink(unittest.TestCase):
    """The runner's side of the line, which runs inside the box. Standard library only, so it
    is tested here directly; the gate plugin with it."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(BOX / 'runner'))
        cls.link_module = load(BOX / 'runner' / 'alfred_box_link.py', 'alfred_box_link')
        sys.modules['alfred_box_link'] = cls.link_module
        cls.gate = load(BOX / 'runner' / 'plugins' / 'alfred_gate' / '__init__.py', 'alfred_gate_plugin')

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop('alfred_box_link', None)
        sys.path.remove(str(BOX / 'runner'))

    def pair(self):
        to_box_r, to_box_w = os.pipe()
        from_box_r, from_box_w = os.pipe()
        link = self.link_module.Link(to_box_r, from_box_w)
        alfred_in = os.fdopen(from_box_r, 'rb')
        self.addCleanup(alfred_in.close)
        self.addCleanup(link._reader.close)
        self.addCleanup(lambda: os.close(to_box_w) if not link.closed.is_set() else None)
        return link, alfred_in, to_box_w

    def answer(self, alfred_in, to_box_w, make_reply, count=1):
        def serve():
            for _ in range(count):
                frame = json.loads(alfred_in.readline())
                os.write(to_box_w, (json.dumps(make_reply(frame)) + '\n').encode())
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        return thread

    def test_replies_find_the_thread_that_asked(self):
        link, alfred_in, to_box_w = self.pair()
        link.start_replies()
        self.answer(alfred_in, to_box_w, lambda f: {'type': 'tool_decision', 'id': f['id'], 'allow': f['tool'] == 'a'},
                    count=4)
        results = {}

        def ask(tool):
            results[tool] = link.ask({'type': 'tool_check', 'tool': tool, 'args': {}})['allow']
        threads = [threading.Thread(target=ask, args=(t,)) for t in 'abcd']
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertEqual(results, {'a': True, 'b': False, 'c': False, 'd': False})

    def test_only_an_explicit_yes_allows_a_tool(self):
        link, alfred_in, to_box_w = self.pair()
        link.start_replies()
        self.link_module.LINK = link
        self.addCleanup(setattr, self.link_module, 'LINK', None)
        for reply, allowed in (({'type': 'tool_decision', 'allow': True}, True),
                               ({'type': 'tool_decision', 'allow': 'yes'}, False),
                               ({'type': 'model_response', 'allow': True}, False),
                               ({'type': 'tool_decision', 'allow': False, 'message': 'No.'}, False)):
            self.answer(alfred_in, to_box_w, lambda f, r=reply: {**r, 'id': f['id']})
            self.assertEqual(self.link_module.check_tool('read_file', {'path': '/work/E1.md'})['allow'], allowed, reply)
        self.answer(alfred_in, to_box_w, lambda f: {'type': 'tool_decision', 'id': f['id'], 'allow': True})
        self.assertIsNone(self.gate._check(tool_name='read_file', args={'path': '/work/E1.md'}))
        self.answer(alfred_in, to_box_w, lambda f: {'type': 'tool_decision', 'id': f['id'], 'allow': False,
                                                    'message': 'ALFRED allows files in /work only.'})
        self.assertEqual(self.gate._check(tool_name='read_file', args={'path': '/etc/passwd'}),
                         {'action': 'block', 'message': 'ALFRED allows files in /work only.'})

    def test_with_alfred_gone_every_tool_is_refused(self):
        link, alfred_in, to_box_w = self.pair()
        link.start_replies()
        os.close(to_box_w)
        link.closed.wait(5)
        self.link_module.LINK = link
        self.addCleanup(setattr, self.link_module, 'LINK', None)
        self.assertEqual(self.link_module.check_tool('read_file', {})['allow'], False)
        self.assertEqual(self.gate._check(tool_name='read_file', args={})['action'], 'block')
        self.link_module.LINK = None
        self.assertEqual(self.link_module.check_tool('read_file', {}),
                         {'allow': False, 'message': 'ALFRED is not connected.'})

    def test_the_gate_never_raises(self):
        broken = type('Broken', (), {'check_tool': staticmethod(lambda *a: 1 / 0)})
        real = sys.modules['alfred_box_link']
        sys.modules['alfred_box_link'] = broken
        try:
            self.assertEqual(self.gate._check(tool_name='x', args={}),
                             {'action': 'block', 'message': 'ALFRED refused this tool.'})
        finally:
            sys.modules['alfred_box_link'] = real

    def test_frames_too_large_or_cut_short_are_refused(self):
        link, alfred_in, to_box_w = self.pair()
        with self.assertRaises(ValueError):
            link.send({'type': 'x', 'body': 'a' * self.link_module.MAX_FRAME})
        os.write(to_box_w, b'{"type": "task"')
        os.close(to_box_w)
        with self.assertRaises(self.link_module.LinkClosed):
            link.read()
        link.closed.set()


if __name__ == '__main__':
    unittest.main()
