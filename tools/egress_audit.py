"""Check that every network-capable import in ALFRED's own code is a reviewed decision.

ALFRED keeps private material on the owner's machine and should reach the network only
through a few known modules. This audit reads every .py file under alfred/ and tools/ as
text through ast; it never imports or runs them. It never reads third_party/ (the inert
source library) at any depth, and refuses a root that lies inside a third_party/ folder.

It fails (exit 1) when:
- a file imports a watched network module (WATCHED below) that the allowlist,
  tools/egress_allowlist.json, does not list for that exact file and module;
- an allowlist entry no longer matches, because its file is gone or no longer imports that
  module, so the list cannot go stale;
- a file cannot be parsed or is a symbolic link, so it could not be audited.
It cannot run (exit 2) when the allowlist is malformed or unreadable, a scanned folder is
missing, or the root is inside third_party/. Exit 0 means clean; warnings alone do not fail.

Imports are found in these forms: import x, from x import y, aliases, submodules
such as urllib.request and http.client, imports inside functions, classes and try blocks,
star imports, use through a parent package (http.client after import http), asyncio
streams and event loop transports, and importlib.import_module or __import__ called with a
literal name.

What it cannot see, so review still matters:
- a module name built at run time (it warns when importlib.import_module or __import__ is
  given one), code run through exec, eval or runpy, files loaded by path, and native code
  reached through ctypes or a compiled extension;
- what another program sends: it warns when subprocess, os or asyncio runs a known network
  program such as curl, wget, ssh or git fetch named literally in the call, but not one
  reached through a wrapper function or a variable;
- network use one step removed: a file that calls an allowlisted ALFRED module (such as the
  loopback desk server) is not flagged itself, and an asyncio event loop is recognised only
  in a file that imports asyncio;
- files other than .py, and folders other than alfred/ and tools/;
- whether allowlisted code really stays on loopback: the reasons are reviewed by people.

Standard library only; reads files, never the network.

    python3 tools/egress_audit.py
    python3 tools/egress_audit.py --self-test
"""
from __future__ import annotations
import argparse
import ast
from dataclasses import dataclass, field
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCANNED = ('alfred', 'tools')
EXCLUDED = 'third_party'
ALLOWLIST = 'tools/egress_allowlist.json'

# A watched name covers itself and everything below it: urllib covers urllib.parse.
STANDARD = (
    '_socket', '_ssl',
    'asyncio.AbstractEventLoop.create_connection', 'asyncio.AbstractEventLoop.create_datagram_endpoint',
    'asyncio.AbstractEventLoop.create_server', 'asyncio.AbstractEventLoop.create_unix_connection',
    'asyncio.AbstractEventLoop.create_unix_server', 'asyncio.open_connection', 'asyncio.open_unix_connection',
    'asyncio.start_server', 'asyncio.start_unix_server', 'asyncio.streams',
    'ftplib', 'http.client', 'http.server', 'imaplib', 'multiprocessing.connection', 'nntplib', 'poplib',
    'smtplib', 'socket', 'socketserver', 'ssl', 'telnetlib', 'urllib', 'webbrowser', 'wsgiref.simple_server',
    'xmlrpc',
)
# Not dependencies of ALFRED; watched so that adopting one is also a reviewed network decision.
OTHERS = (
    'aiohttp', 'anthropic', 'boto3', 'botocore', 'grpc', 'httpcore', 'httplib2', 'httpx', 'openai', 'paramiko',
    'playwright', 'pycurl', 'requests', 'selenium', 'tornado', 'twisted', 'urllib3', 'websocket', 'websockets',
)
WATCHED = tuple(sorted(STANDARD + OTHERS))
LOOP = 'asyncio.AbstractEventLoop.'
LOOP_METHODS = frozenset(name[len(LOOP):] for name in WATCHED if name.startswith(LOOP))
# asyncio's own __all__ re-exports its stream functions, so a star import brings them in.
STAR_EXPORTS = {'asyncio': 'asyncio.streams'}
# Packages whose __init__ is empty, so any name taken from them is a submodule: from urllib
# import parse is recorded as urllib.parse, and urllib.request.urlopen as urllib.request.
SUBMODULE_PACKAGES = ('urllib', 'xmlrpc')
DYNAMIC = ('importlib.import_module', 'importlib.__import__', 'builtins.__import__')

# Programs whose job is to move data over a network, recognised when named literally.
NETWORK_PROGRAMS = frozenset((
    'aria2c', 'curl', 'ftp', 'gh', 'lftp', 'nc', 'ncat', 'netcat', 'npm', 'npx', 'pip', 'pip3', 'rsync', 'scp',
    'sftp', 'socat', 'ssh', 'telnet', 'wget',
))
GIT_NETWORK = frozenset(('clone', 'fetch', 'ls-remote', 'pull', 'push', 'submodule'))
# Calls that start another program, with the position of the program or command argument.
RUNNERS = dict(
    {f'subprocess.{n}': 0 for n in ('run', 'Popen', 'call', 'check_call', 'check_output', 'getoutput',
                                     'getstatusoutput')},
    **{f'os.{n}': 0 for n in ('system', 'popen', 'execl', 'execle', 'execlp', 'execlpe', 'execv', 'execve',
                               'execvp', 'execvpe', 'posix_spawn', 'posix_spawnp')},
    **{f'os.{n}': 1 for n in ('spawnl', 'spawnle', 'spawnlp', 'spawnlpe', 'spawnv', 'spawnve', 'spawnvp',
                               'spawnvpe')},
    **{f'asyncio.{n}': 0 for n in ('create_subprocess_exec', 'create_subprocess_shell')},
)
COMMAND_KEYWORDS = ('args', 'cmd', 'command', 'file', 'path', 'program')
DOTTED = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*')


class AuditError(ValueError):
    """The audit could not run, for example because the allowlist is malformed."""


@dataclass(frozen=True)
class Scan:
    imports: dict  # watched network import -> sorted tuple of line numbers
    warnings: list  # sorted (line, text) pairs for things the audit cannot follow


@dataclass
class Report:
    files: int = 0
    allowed: int = 0
    findings: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def watched(name):
    """The watched entry a dotted module name falls under, or None."""
    return next((w for w in WATCHED if name == w or name.startswith(w + '.')), None)


def _first_watched_prefix(dotted):
    parts = dotted.split('.')
    return next(('.'.join(parts[:i]) for i in range(1, len(parts) + 1) if '.'.join(parts[:i]) in WATCHED), None)


def _literal(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _argument(call, index, keywords):
    if len(call.args) > index:
        return call.args[index]
    return next((k.value for k in call.keywords if k.arg in keywords), None)


def _program_name(word):
    return PurePosixPath(word).name.lower().removesuffix('.exe')


def network_program(node):
    """The network program a literal command names, such as 'curl' or 'git fetch', or None."""
    text = _literal(node)
    if text is not None:
        words = [_program_name(w) for w in re.split(r'[\s;&|()<>`]+', text) if w]
        program = next((w for w in words if w in NETWORK_PROGRAMS), None)
        sub = next((w for w in words if w in GIT_NETWORK), None) if 'git' in words else None
        return program or (sub and 'git ' + sub)
    if isinstance(node, (ast.List, ast.Tuple)) and node.elts and _literal(node.elts[0]) is not None:
        program = _program_name(_literal(node.elts[0]))
        if program in NETWORK_PROGRAMS:
            return program
        if program == 'git':
            sub = next((w for w in map(_literal, node.elts[1:]) if w in GIT_NETWORK), None)
            return sub and 'git ' + sub
    return None


def scan_source(source, filename='<source>'):
    """Find watched network imports in Python source text without running it.

    Raises SyntaxError (or ValueError) when the source cannot be parsed."""
    tree = ast.parse(source, filename)
    found, notes, bindings = {}, set(), {}

    def note(name, line):
        found.setdefault(name, set()).add(line)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if watched(alias.name):
                    note(alias.name, node.lineno)
                top = alias.name.partition('.')[0]
                bindings[alias.asname or top] = alias.name if alias.asname else top
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            module = node.module
            for alias in node.names:
                if alias.name == '*':
                    hit = module if watched(module) else STAR_EXPORTS.get(module)
                else:
                    full = module + '.' + alias.name
                    if module in SUBMODULE_PACKAGES:
                        hit = full
                    else:
                        hit = module if watched(module) else (full if watched(full) else None)
                    bindings[alias.asname or alias.name] = full
                if hit:
                    note(hit, node.lineno)

    def resolve(expr):
        """The dotted name an expression refers to through this file's imports, and its base."""
        parts = []
        while isinstance(expr, ast.Attribute):
            parts.append(expr.attr)
            expr = expr.value
        if isinstance(expr, ast.Name) and expr.id in bindings:
            base = bindings[expr.id]
            return '.'.join([base] + parts[::-1]), base
        return None, None

    uses_asyncio = any(v == 'asyncio' or v.startswith('asyncio.') for v in bindings.values())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            full, base = resolve(node)
            if full and base in SUBMODULE_PACKAGES and full != base:
                note('.'.join(full.split('.')[:base.count('.') + 2]), node.lineno)
            elif full and not watched(base):
                hit = _first_watched_prefix(full)
                if hit:
                    note(hit, node.lineno)
            elif not full and uses_asyncio and node.attr in LOOP_METHODS:
                note(LOOP + node.attr, node.lineno)
        elif isinstance(node, ast.Call):
            target = resolve(node.func)[0]
            if isinstance(node.func, ast.Name) and node.func.id == '__import__' and '__import__' not in bindings:
                target = '__import__'
            elif target not in DYNAMIC and isinstance(node.func, ast.Attribute) and \
                    node.func.attr in ('import_module', '__import__'):
                target = node.func.attr
            if target in DYNAMIC or target in ('__import__', 'import_module'):
                name = _literal(_argument(node, 0, ('name',)))
                if name is None:
                    notes.add((node.lineno, f'imports a module named at run time through {target}; '
                                            'this audit cannot see which'))
                elif not name.startswith('.'):
                    fromlist = _argument(node, 3, ('fromlist',))
                    extra = [name + '.' + w for w in map(_literal, getattr(fromlist, 'elts', ())) if w]
                    whole = watched(name) and not (name in SUBMODULE_PACKAGES and extra)
                    for hit in ([name] if whole else [n for n in extra if watched(n)]):
                        note(hit, node.lineno)
            elif target in RUNNERS:
                program = network_program(_argument(node, RUNNERS[target], COMMAND_KEYWORDS))
                if program:
                    notes.add((node.lineno, f'runs {program} through {target}; '
                                            'this audit cannot see what another program sends'))
    return Scan({name: tuple(sorted(lines)) for name, lines in sorted(found.items())}, sorted(notes))


def _module_path(value):
    if type(value) is not str or '\\' in value or not value.endswith('.py'):
        return False
    parts = value.split('/')
    if value.startswith('/') or any(part in ('', '.', '..') for part in parts):
        return False
    return len(parts) > 1 and parts[0] in SCANNED and EXCLUDED not in parts


def load_allowlist(path, shown=None):
    """Read and validate the allowlist: {module path: {'imports': tuple, 'reason': str}}."""
    shown = shown or str(path)
    try:
        text = Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        raise AuditError(f'{shown} cannot be read ({getattr(exc, "strerror", None) or exc})') from None

    def bad(message):
        return AuditError(f'{shown} is malformed: {message}')

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise bad(f'not valid JSON ({exc.msg} at line {exc.lineno} column {exc.colno})') from None
    if type(data) is not dict:
        raise bad('the top level must be a JSON object')
    unknown = sorted(set(data) - {'schema', 'about', 'entries'})
    if unknown:
        raise bad('unknown key ' + unknown[0])
    if type(data.get('schema')) is not int or data['schema'] != 1:
        raise bad('schema must be 1')
    if 'about' in data and (type(data['about']) is not str or not data['about'].strip()):
        raise bad('about must be text')
    if type(data.get('entries')) is not list:
        raise bad('entries must be a list')
    result = {}
    for number, item in enumerate(data['entries'], 1):
        where = f'entry {number}'
        if type(item) is not dict:
            raise bad(where + ' must be an object')
        for key in ('module', 'imports', 'reason'):
            if key not in item:
                raise bad(f'{where} is missing {key}')
        extra = sorted(set(item) - {'module', 'imports', 'reason'})
        if extra:
            raise bad(f'{where} has unknown key {extra[0]}')
        module, imports, reason = item['module'], item['imports'], item['reason']
        if not _module_path(module):
            raise bad(f'{where}: module must be a relative path to a .py file under '
                      f'{" or ".join(s + "/" for s in SCANNED)}, outside {EXCLUDED}/')
        if module in result:
            raise bad(f'{where} repeats {module}')
        if type(imports) is not list or not imports:
            raise bad(f'{where}: imports must be a non-empty list')
        if not all(type(name) is str and DOTTED.fullmatch(name) for name in imports):
            raise bad(f'{where}: imports must be dotted module names')
        for name in imports:
            if imports.count(name) > 1:
                raise bad(f'{where} lists {name} twice')
            if not watched(name):
                raise bad(f'{where}: {name} is not a watched network module')
        if type(reason) is not str or not reason.strip() or '\n' in reason or '\r' in reason:
            raise bad(f'{where}: reason must be one non-empty line')
        result[module] = {'imports': tuple(imports), 'reason': reason}
    return result


def _python_files(root, problems, skipped):
    """Yield (relative path, path) for each .py file to audit, in sorted order, never
    entering third_party/ and never following a symbolic link. Links are reported in
    problems and their paths added to skipped."""
    def rel(path):
        return Path(path).relative_to(root).as_posix()

    for folder in SCANNED:
        def unlisted(exc):
            problems.append((rel(exc.filename), 0, 'cannot be listed, so it was not audited'))
        for current, dirs, files in os.walk(root / folder, onerror=unlisted):
            here = Path(current)
            for name in sorted(dirs):
                if name == EXCLUDED or (here / name).is_symlink():
                    dirs.remove(name)
                    if name != EXCLUDED:
                        skipped.add(rel(here / name))
                        problems.append((rel(here / name), 0, 'is a symbolic link, so it was not audited'))
            dirs.sort()
            for name in sorted(files):
                if not name.endswith('.py'):
                    continue
                if (here / name).is_symlink():
                    skipped.add(rel(here / name))
                    problems.append((rel(here / name), 0, 'is a symbolic link, so it was not audited'))
                else:
                    yield rel(here / name), here / name


def _also(lines):
    rest = lines[1:]
    if not rest:
        return ''
    return f' (also line{"s" if len(rest) > 1 else ""} {", ".join(map(str, rest))})'


def _shown(path, root):
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _format(items):
    return [f'{path}:{line}: {text}' if line else f'{path}: {text}' for path, line, text in sorted(items)]


def audit(root=ROOT, allowlist=None):
    """Audit the alfred/ and tools/ folders under root against the allowlist."""
    root = Path(root)
    if EXCLUDED in root.resolve().parts:
        raise AuditError(f'{root} is inside a {EXCLUDED}/ folder, which this audit never reads')
    for folder in SCANNED:
        if not (root / folder).is_dir() or (root / folder).is_symlink():
            raise AuditError(f'{folder}/ is missing under {root} or is a symbolic link')
    allow_path = Path(allowlist) if allowlist else root / ALLOWLIST
    shown = _shown(allow_path, root)
    entries = load_allowlist(allow_path, shown)
    report, scans, unaudited, problems, notes = Report(), {}, set(), [], []
    for rel, path in _python_files(root, problems, unaudited):
        report.files += 1
        try:
            scan = scans[rel] = scan_source(path.read_bytes(), rel)
        except SyntaxError as exc:
            unaudited.add(rel)
            problems.append((rel, exc.lineno or 0, f'cannot be parsed, so it was not audited ({exc.msg})'))
            continue
        except (ValueError, RecursionError) as exc:
            unaudited.add(rel)
            problems.append((rel, 0, f'cannot be parsed, so it was not audited ({exc})'))
            continue
        except OSError as exc:
            unaudited.add(rel)
            problems.append((rel, 0, f'cannot be read, so it was not audited ({exc.strerror or "error"})'))
            continue
        listed = entries.get(rel, {}).get('imports', ())
        for name, lines in scan.imports.items():
            if name in listed:
                report.allowed += 1
            else:
                problems.append((rel, lines[0], f'{name} is a network import that is not on the allowlist'
                                 + _also(lines)))
        notes += [(rel, line, text) for line, text in scan.warnings]
    for module, item in entries.items():
        if any(module == path or module.startswith(path + '/') for path in unaudited):
            continue  # already reported as not audited; whether the entry is stale is unknown
        if module not in scans:
            problems.append((shown, 0, f'stale entry: {module} no longer exists'))
            continue
        for name in item['imports']:
            if name not in scans[module].imports:
                problems.append((shown, 0, f'stale entry: {module} no longer imports {name}'))
    report.findings, report.warnings = _format(problems), _format(notes)
    return report


SELF_TEST = (
    ('plain import', 'import socket\n', {'socket': (1,)}),
    ('alias', 'import ssl as tls\n', {'ssl': (1,)}),
    ('from import', 'from smtplib import SMTP\n', {'smtplib': (1,)}),
    ('submodule from its parent', 'from http import client, HTTPStatus\n', {'http.client': (1,)}),
    ('parser only', 'from urllib.parse import quote\n', {'urllib.parse': (1,)}),
    ('nested in a try block', 'def f():\n    try:\n        import ftplib\n    except ImportError:\n        pass\n',
     {'ftplib': (3,)}),
    ('literal dynamic import', 'import importlib\nimportlib.import_module("socketserver")\n', {'socketserver': (2,)}),
    ('use through a parent', 'import asyncio\nasyncio.open_connection("host", 1)\n', {'asyncio.open_connection': (2,)}),
    ('relative import is first party', 'from . import socket\n', {}),
    ('text is not code', 'NOTE = "import socket"\n# import ssl\n', {}),
    ('harmless parent', 'import http, json\nfrom http import HTTPStatus\n', {}),
)


def self_test():
    """Run the built-in synthetic cases. Returns 0 when every case passes."""
    failures, total = [], len(SELF_TEST) + 1
    for label, source, expected in SELF_TEST:
        got = scan_source(source).imports
        if got != expected:
            failures.append(f'{label}: expected {expected}, got {got}')
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        files = {'alfred/net.py': 'import socket\n', 'alfred/broken.py': 'def broken(:\n',
                 'tools/third_party/net.py': 'import ssl\n', 'tools/fine.py': 'import json\n',
                 ALLOWLIST: json.dumps({'schema': 1, 'entries': [
                     {'module': 'tools/fine.py', 'imports': ['urllib.parse'], 'reason': 'Synthetic.'}]})}
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding='utf-8')
        report = audit(root)
        got = [f.split(' (')[0] for f in report.findings]
        expected = ['alfred/broken.py:1: cannot be parsed, so it was not audited',
                    'alfred/net.py:1: socket is a network import that is not on the allowlist',
                    ALLOWLIST + ': stale entry: tools/fine.py no longer imports urllib.parse']
        if got != expected or report.files != 3:
            failures.append(f'synthetic tree: expected {expected} from 3 files, got {got} from {report.files}')
    for failure in failures:
        print('FAIL: ' + failure)
    passed = total - len(failures)
    print(f'self-test ok: {total} cases' if not failures else f'self-test failed: {passed} of {total} cases passed')
    return 1 if failures else 0


def _count(number, word):
    return f'{number} {word}{"" if number == 1 else "s"}'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--root', default=str(ROOT), help='repository root to audit (default: this repository)')
    parser.add_argument('--allowlist', help='allowlist file (default: <root>/' + ALLOWLIST + ')')
    parser.add_argument('--self-test', action='store_true', help='run the built-in synthetic cases and exit')
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    try:
        report = audit(args.root, args.allowlist)
    except AuditError as exc:
        print('error: ' + str(exc), file=sys.stderr)
        print('egress audit could not run')
        return 2
    for finding in report.findings:
        print('error: ' + finding, file=sys.stderr)
    for warning in report.warnings:
        print('warning: ' + warning, file=sys.stderr)
    if report.findings:
        print('egress audit failed: ' + _count(len(report.findings), 'finding'))
        return 1
    print(f'egress audit ok: {_count(report.files, "file")} scanned, '
          f'{_count(report.allowed, "allowlisted network import")}, {_count(len(report.warnings), "warning")}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
