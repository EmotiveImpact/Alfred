"""ALFRED's runner inside the sealed Hermes box (docs/HERMES_BOX.md).

This is the box's only program. ALFRED starts the box with no network, a read-only system,
a throwaway home in memory and no credentials, and talks to this runner over its standard
input and output only. The runner:

1. moves Hermes's own printing to standard error and closes standard input to Hermes, so the
   line to ALFRED cannot be read or written by Hermes;
2. puts ALFRED's settings and tool gate into the empty Hermes home, reads the settings back
   through Hermes's own loader, checks the box really has no network, and reports all of it
   to ALFRED in a ``hello`` frame, before ALFRED sends anything private;
3. receives one ``task`` frame, writes the task's excerpts into ``/work`` (also in memory),
   and runs Hermes once on it;
4. gives Hermes a model address on the box's own loopback. Each request to it becomes a
   ``model_request`` frame; ALFRED decides, makes the call itself with its own key and
   meter, and answers with a ``model_response`` frame. Hermes never holds a key;
5. sends a ``final`` frame with Hermes's reply and the names (never the contents) of what
   Hermes left in its home, then exits. The box is removed with everything in it.

Hermes is imported from the pinned source at /opt/hermes. Standard library otherwise.
"""
from __future__ import annotations
import http.server
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import threading

BOX = Path(__file__).resolve().parent
sys.path.insert(0, str(BOX))
import alfred_box_link as link_module  # noqa: E402
from alfred_box_link import Link, LinkClosed, PROTOCOL, MAX_FRAME  # noqa: E402

HERMES_SOURCE = '/opt/hermes'
PIN_FILE = '/opt/alfred-box/pin.json'
WORK = Path('/work')
SETTINGS = BOX.parent / 'config.yaml'
PLUGIN = BOX / 'plugins' / 'alfred_gate'
RELAY_KEY = 'alfred-relay'  # Not a secret: the forwarder drops it. The real key stays with ALFRED.
MAX_LISTING = 400


def _flatten(prefix, value, out):
    if isinstance(value, dict):
        for key in sorted(value):
            _flatten(f'{prefix}.{key}' if prefix else str(key), value[key], out)
    else:
        out[prefix] = value


def _lookup(config, dotted):
    node = config
    for part in dotted.split('.'):
        if not isinstance(node, dict) or part not in node:
            return {'missing': True}
        node = node[part]
    return node


def prepare_home() -> Path:
    home = Path(os.environ['HERMES_HOME'])
    home.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(home.iterdir()):
        raise RuntimeError('home_not_empty')
    shutil.copyfile(SETTINGS, home / 'config.yaml')
    shutil.copytree(PLUGIN, home / 'plugins' / 'alfred_gate')
    return home


def read_settings() -> dict:
    """The value Hermes itself reads for every setting in ALFRED's file, by dotted name."""
    from ruamel.yaml import YAML
    from hermes_cli.config import load_config
    wanted: dict = {}
    _flatten('', YAML(typ='safe').load(SETTINGS.read_text(encoding='utf-8')), wanted)
    config = load_config()
    return {name: _lookup(config, name) for name in sorted(wanted)}


def loaded_plugins() -> dict:
    """Every plugin Hermes loaded, with where it came from, and every hook it registered.

    Hermes's bundled plugins (model providers, platforms and the like) are part of the
    pinned source. ALFRED checks that its gate is the only plugin from anywhere else and the
    only ``pre_tool_call`` hook, so nothing can wave a tool call through.
    """
    from hermes_cli.plugins import get_plugin_manager
    manager = get_plugin_manager()
    manager.discover_and_load()
    plugins = sorted({(p.manifest.name, str(p.manifest.source)) for p in manager._plugins.values()
                      if p.enabled and not p.error})
    hooks = {name: sorted(getattr(cb, '__module__', '?') for cb in callbacks)
             for name, callbacks in sorted(manager._hooks.items()) if callbacks}
    return {'loaded': [{'name': n, 'source': s} for n, s in plugins], 'hooks': hooks}


def probe_network() -> dict:
    """Try to leave the box. In a box started with no network, every attempt fails."""
    result = {}
    try:
        socket.getaddrinfo('api.anthropic.com', 443)
        result['dns'] = 'open'
    except OSError:
        result['dns'] = 'blocked'
    try:
        socket.create_connection(('1.1.1.1', 443), timeout=2).close()
        result['outbound'] = 'open'
    except OSError:
        result['outbound'] = 'blocked'
    return result


def listing(*roots) -> list:
    """Names and sizes under each root, never contents, for ALFRED's receipt."""
    found = []
    for root in roots:
        root = Path(root)
        for path in sorted(root.rglob('*')):
            if len(found) >= MAX_LISTING:
                found.append({'path': '...', 'truncated': True})
                return found
            entry = {'path': f'{root.name}/{path.relative_to(root)}'}
            if path.is_file() and not path.is_symlink():
                entry['bytes'] = path.stat().st_size
            elif path.is_dir():
                entry['dir'] = True
            found.append(entry)
    return found


def write_work(files) -> None:
    if not isinstance(files, dict):
        raise ValueError('bad_task_files')
    for name, content in files.items():
        if not isinstance(name, str) or not name.replace('.', '').replace('-', '').replace('_', '').isalnum() \
                or name.startswith('.') or not isinstance(content, str):
            raise ValueError('bad_task_file')
        target = WORK / name
        target.write_text(content, encoding='utf-8')


class Forwarder(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, link: Link):
        self.link = link
        super().__init__(('127.0.0.1', 0), _ForwardHandler)


class _ForwardHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def _relay(self, method):
        length = int(self.headers.get('content-length') or 0)
        if length < 0 or length > MAX_FRAME // 2:
            self._answer(413, 'application/json', '{"error":"too_large"}')
            return
        body = self.rfile.read(length).decode('utf-8', 'replace') if length else ''
        try:
            reply = self.server.link.ask({'type': 'model_request', 'method': method, 'path': self.path,
                                          'betas': self.headers.get('anthropic-beta', ''), 'body': body})
        except LinkClosed:
            self._answer(503, 'application/json', '{"error":"alfred_gone"}')
            return
        if reply.get('type') != 'model_response':
            self._answer(502, 'application/json', '{"error":"bad_reply"}')
            return
        self._answer(int(reply.get('status', 502)), str(reply.get('content_type', 'application/json')),
                     str(reply.get('body', '')))

    def _answer(self, status, content_type, body):
        data = body.encode('utf-8')
        self.send_response(status)
        self.send_header('content-type', content_type)
        self.send_header('content-length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self._relay('POST')

    def do_GET(self):
        self._relay('GET')


def run_task(link: Link, task: dict) -> str:
    server = Forwarder(link)
    threading.Thread(target=server.serve_forever, name='alfred-forwarder', daemon=True).start()
    from run_agent import AIAgent
    agent = AIAgent(
        base_url=f'http://127.0.0.1:{server.server_address[1]}', api_key=RELAY_KEY, provider='anthropic',
        model=task['model'], enabled_toolsets=list(task['toolsets']), quiet_mode=True,
        skip_context_files=True, skip_memory=True, skip_background_review=True, load_soul_identity=False,
        max_iterations=int(task['max_iterations']), run_budget_seconds=float(task['wall_seconds']),
        max_tokens=int(task['max_tokens']), ephemeral_system_prompt=task['system'],
        save_trajectories=False, checkpoints_enabled=False, cwd=str(WORK))
    return agent.chat(task['prompt'])


def main() -> int:
    frames_out, frames_in = os.dup(1), os.dup(0)
    os.dup2(2, 1)
    quiet = os.open(os.devnull, os.O_RDONLY)
    os.dup2(quiet, 0)
    link = Link(frames_in, frames_out)
    link_module.LINK = link
    try:
        sys.path.insert(0, HERMES_SOURCE)
        home = prepare_home()
        pin = json.loads(Path(PIN_FILE).read_text(encoding='utf-8'))
        link.send({'type': 'hello', 'protocol': PROTOCOL, 'pin': pin, 'settings': read_settings(),
                   'plugins': loaded_plugins(), 'network': probe_network(), 'user': os.getuid()})
        task = link.read()
        if task.get('type') != 'task' or task.get('protocol') != PROTOCOL:
            link.send({'type': 'error', 'code': 'no_task'})
            return 2
        write_work(task.get('files', {}))
        link.start_replies()
        text = run_task(link, task)
        link.send({'type': 'final', 'text': text if isinstance(text, str) else '',
                   'left': listing(home, WORK)})
        return 0
    except LinkClosed:
        return 3
    except BaseException as error:  # Only the kind of failure leaves the box, never its message.
        try:
            link.send({'type': 'error', 'code': type(error).__name__[:60]})
        except Exception:
            pass
        return 4


if __name__ == '__main__':
    code = main()
    sys.stdout.flush()
    os._exit(code)
