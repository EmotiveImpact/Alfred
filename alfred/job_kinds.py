"""First-party allowlisted job kinds for ALFRED's local subprocess backend.

The coordinator imports this module to validate requests. The local subprocess
backend runs this same file as a separate OS process:

    python3 -I -S -B alfred/job_kinds.py --cpu-seconds N --memory-bytes N

The child reads one JSON request on standard input, computes a deterministic
result over only the input bytes it was given and writes the result bytes to
standard output. It is given no database path, credential or environment. It
imports only the standard library and must stay importable without the
``alfred`` package, because isolated mode does not put the repository on
``sys.path``.

Honest scope: resource limits and the audit-hook tripwire below catch accidental
use of files, sockets or processes by these first-party kinds. They are not a
sandbox. Python documents audit hooks as unsuitable for sandboxing, and a local
subprocess shares the host, user account and kernel with ALFRED.
"""
from __future__ import annotations
import base64
import hashlib
import json
import sys
import time

MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_LINE_CHARS = 200
EXIT_KIND_ERROR = 2

# Every kind here reads only its declared inputs and writes only to standard
# output. A future kind with an external effect must say so, and a submitter may
# never declare such a kind side-effect free.
KINDS = {
    'word_count': {
        'side_effect_free': True, 'capability': 'read', 'parameters': {},
        'description': 'Counts bytes, lines and words in each input.',
    },
    'summarise_lines': {
        'side_effect_free': True, 'capability': 'read',
        'parameters': {'max_lines': ('int', 1, 50)},
        'description': 'Extractive: the first non-empty lines of each input. Not a model summary.',
    },
    'wait': {
        'side_effect_free': True, 'capability': 'read',
        'parameters': {'seconds': ('number', 0, 600)},
        'description': 'Sleeps, then hashes its inputs. Exercises limits, cancellation and reconnection.',
    },
}


def validate(kind, parameters):
    """Return canonical parameters or raise ValueError with a stable code."""
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError('unknown_job_kind')
    if type(parameters) is not dict:
        raise ValueError('invalid_parameters')
    spec = KINDS[kind]['parameters']
    if set(parameters) != set(spec):
        raise ValueError('invalid_parameters')
    result = {}
    for name, (form, low, high) in spec.items():
        value = parameters[name]
        if form == 'int' and type(value) is not int:
            raise ValueError('invalid_parameters')
        if form == 'number' and (type(value) not in (int, float) or value != value):
            raise ValueError('invalid_parameters')
        if not low <= value <= high:
            raise ValueError('invalid_parameters')
        result[name] = value
    return result


def _text(data):
    return data.decode('utf-8', errors='replace')


def _describe(name, data):
    return {'name': name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def run(kind, parameters, inputs):
    """Run one kind over ``inputs`` (a list of (name, bytes)) and return result bytes."""
    parameters = validate(kind, parameters)
    if kind == 'word_count':
        rows, total = [], {'bytes': 0, 'lines': 0, 'words': 0}
        for name, data in inputs:
            body = _text(data)
            row = _describe(name, data) | {'lines': len(body.splitlines()), 'words': len(body.split())}
            for key in total:
                total[key] += row[key]
            rows.append(row)
        result = {'kind': kind, 'basis': 'deterministic_count_not_interpretation', 'inputs': rows, 'total': total}
    elif kind == 'summarise_lines':
        rows = []
        for name, data in inputs:
            lines = _text(data).splitlines()
            chosen = [line.strip()[:MAX_LINE_CHARS] for line in lines if line.strip()][:parameters['max_lines']]
            rows.append(_describe(name, data) | {'lines': len(lines), 'selected': chosen})
        result = {'kind': kind, 'basis': 'extractive_first_lines_not_model_summary', 'inputs': rows}
    else:
        time.sleep(parameters['seconds'])
        result = {'kind': kind, 'seconds': parameters['seconds'],
                  'inputs': [_describe(name, data) for name, data in inputs]}
    return json.dumps(result, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


_REFUSED_PREFIXES = (
    'socket.', 'subprocess.', 'os.system', 'os.exec', 'os.posix_spawn', 'os.spawn', 'os.fork',
    'os.forkpty', 'os.kill', 'os.killpg', 'os.listdir', 'os.scandir', 'os.remove', 'os.rename',
    'os.rmdir', 'os.mkdir', 'os.chmod', 'os.chown', 'os.symlink', 'os.link', 'os.truncate',
    'os.putenv', 'os.unsetenv', 'ctypes.', 'shutil.', 'urllib.Request', 'http.client.', 'ftplib.',
    'smtplib.', 'poplib.', 'imaplib.', 'webbrowser.', 'sqlite3.', 'mmap.', 'open',
)


def install_guard():
    """Refuse file, socket and process audit events from here on.

    A tripwire for mistakes in first-party kinds, not a security boundary.
    """
    def hook(event, _args):
        if event.startswith(_REFUSED_PREFIXES):
            raise PermissionError('refused_by_job_guard:' + event)
    sys.addaudithook(hook)


def _limit(cpu_seconds, memory_bytes):
    try:
        import resource
    except ImportError:  # Not POSIX: the parent's wall-clock limit still applies.
        return
    for name, value in (('RLIMIT_CPU', cpu_seconds), ('RLIMIT_AS', memory_bytes),
                        ('RLIMIT_FSIZE', 0), ('RLIMIT_CORE', 0)):
        which = getattr(resource, name, None)
        if which is None or value is None:
            continue
        try:
            resource.setrlimit(which, (value, value))
        except (ValueError, OSError):
            pass


def _arguments(argv):
    options = {'--cpu-seconds': None, '--memory-bytes': None}
    if len(argv) % 2:
        raise ValueError('invalid_arguments')
    for flag, value in zip(argv[::2], argv[1::2]):
        if flag not in options or not value.isdigit():
            raise ValueError('invalid_arguments')
        options[flag] = int(value)
    return options['--cpu-seconds'], options['--memory-bytes']


def _request(raw):
    if len(raw) > MAX_REQUEST_BYTES:
        raise ValueError('request_too_large')
    try:
        request = json.loads(raw.decode('utf-8'))
    except (UnicodeError, ValueError):
        raise ValueError('invalid_request') from None
    if type(request) is not dict or set(request) != {'kind', 'parameters', 'inputs'}:
        raise ValueError('invalid_request')
    if type(request['inputs']) is not list:
        raise ValueError('invalid_request')
    inputs = []
    for item in request['inputs']:
        if type(item) is not dict or set(item) != {'name', 'data'}:
            raise ValueError('invalid_request')
        try:
            inputs.append((str(item['name']), base64.b64decode(item['data'], validate=True)))
        except (TypeError, ValueError):
            raise ValueError('invalid_request') from None
    return request['kind'], request['parameters'], inputs


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        cpu_seconds, memory_bytes = _arguments(argv)
        _limit(cpu_seconds, memory_bytes)
        kind, parameters, inputs = _request(sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1))
        install_guard()
        output = run(kind, parameters, inputs)
    except ValueError as exc:
        sys.stderr.write(str(exc)[:64] + '\n')
        return EXIT_KIND_ERROR
    except PermissionError:
        sys.stderr.write('guard_refused\n')
        return EXIT_KIND_ERROR
    sys.stdout.buffer.write(output)
    sys.stdout.buffer.flush()
    return 0


if __name__ == '__main__':
    sys.exit(main())
