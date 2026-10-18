"""Synthetic offline tests for the network egress audit (tools/egress_audit.py).

Every tree is invented in a temporary directory. The audit reads files as text through
ast and never imports or runs them; one test proves that by planting a file that would
leave a marker if it ever ran.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools import egress_audit as ea

ROOT = Path(__file__).resolve().parents[1]
ALLOW = 'tools/egress_allowlist.json'


def names(source):
    return {name: list(lines) for name, lines in ea.scan_source(source).imports.items()}


def warnings(source):
    return list(ea.scan_source(source).warnings)


def entry(module, imports, reason='Synthetic reason.'):
    return {'module': module, 'imports': imports, 'reason': reason}


class Tree:
    """A synthetic repository with alfred/ and tools/ folders and an allowlist."""

    def __init__(self, test, files=None, entries=(), allowlist=None, root_name='repo'):
        holder = tempfile.TemporaryDirectory()
        test.addCleanup(holder.cleanup)
        self.root = Path(holder.name) / root_name
        for folder in ea.SCANNED:
            (self.root / folder).mkdir(parents=True)
        for path, content in (files or {}).items():
            self.write(path, content)
        if allowlist is None:
            allowlist = json.dumps({'schema': 1, 'entries': list(entries)}, indent=2)
        self.write(ALLOW, allowlist)

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding='utf-8')
        return target

    def audit(self):
        return ea.audit(self.root)

    def run(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ea.main(['--root', str(self.root), *extra])
        return code, out.getvalue().splitlines(), err.getvalue().splitlines()


class ImportFormTests(unittest.TestCase):
    def test_plain_import(self):
        self.assertEqual(names('import socket\n'), {'socket': [1]})

    def test_several_modules_in_one_statement(self):
        self.assertEqual(names('import json, ssl, os\n'), {'ssl': [1]})

    def test_from_import(self):
        self.assertEqual(names('from smtplib import SMTP\n'), {'smtplib': [1]})

    def test_aliased_imports(self):
        source = 'import ftplib as transfer\nfrom socket import socket as raw\n'
        self.assertEqual(names(source), {'ftplib': [1], 'socket': [2]})

    def test_submodules(self):
        source = ('import urllib.request\nimport http.client\nfrom http.server import HTTPServer\n'
                  'import xmlrpc.client as rpc\nfrom wsgiref.simple_server import make_server\n')
        self.assertEqual(names(source), {'urllib.request': [1], 'http.client': [2], 'http.server': [3],
                                         'xmlrpc.client': [4], 'wsgiref.simple_server': [5]})

    def test_submodule_named_from_its_parent_package(self):
        source = ('from http import client, HTTPStatus\nfrom urllib import parse\n'
                  'from asyncio import open_connection, sleep\nfrom multiprocessing import connection\n')
        self.assertEqual(names(source), {'http.client': [1], 'urllib.parse': [2], 'asyncio.open_connection': [3],
                                         'multiprocessing.connection': [4]})

    def test_submodule_reached_through_an_empty_package(self):
        source = ('import urllib\nurllib.request.urlopen(address)\nimport xmlrpc\nxmlrpc.client.ServerProxy(a)\n'
                  '__import__("urllib", fromlist=["error"])\n')
        self.assertEqual(names(source), {'urllib': [1], 'urllib.request': [2], 'xmlrpc': [3], 'xmlrpc.client': [4],
                                         'urllib.error': [5]})

    def test_parser_only_import_is_still_reported(self):
        self.assertEqual(names('from urllib.parse import urlsplit\n'), {'urllib.parse': [1]})

    def test_harmless_parent_packages_are_not_network(self):
        source = ('import http\nfrom http import HTTPStatus\nimport asyncio\nasyncio.run(main())\n'
                  'import json, email.utils, multiprocessing, wsgiref\nmultiprocessing.Pool(2)\n')
        self.assertEqual(names(source), {})

    def test_network_submodule_reached_through_parent_package(self):
        source = ('import http\nhttp.client.HTTPConnection("example.invalid")\n'
                  'import asyncio as aio\naio.start_server(handler)\n'
                  'import multiprocessing\nmultiprocessing.connection.Client(address)\n')
        self.assertEqual(names(source), {'http.client': [2], 'asyncio.start_server': [4],
                                         'multiprocessing.connection': [6]})

    def test_asyncio_streams_and_event_loop_transports(self):
        source = ('import asyncio\nfrom asyncio import streams\nasync def connect():\n'
                  '    loop = asyncio.get_running_loop()\n    await loop.create_connection(Protocol, "host", 1)\n'
                  '    await asyncio.get_running_loop().create_server(Protocol, "host", 2)\n')
        self.assertEqual(names(source), {'asyncio.streams': [2], 'asyncio.AbstractEventLoop.create_connection': [5],
                                         'asyncio.AbstractEventLoop.create_server': [6]})

    def test_event_loop_method_names_need_asyncio(self):
        self.assertEqual(names('server.create_server()\nthing.create_connection()\n'), {})

    def test_socket_function_is_not_mistaken_for_an_event_loop(self):
        source = 'import asyncio, socket\nsocket.create_connection(("host", 1))\n'
        self.assertEqual(names(source), {'socket': [1]})

    def test_star_imports(self):
        source = 'from socket import *\nfrom asyncio import *\nfrom http import *\n'
        self.assertEqual(names(source), {'socket': [1], 'asyncio.streams': [2]})

    def test_imports_inside_functions_classes_and_try_blocks(self):
        source = ('def open_link():\n    import socket\ntry:\n    import ssl\nexcept ImportError:\n'
                  '    from urllib import request\nclass Mailer:\n    def send(self):\n        if True:\n'
                  '            import smtplib\nasync def later():\n    with context():\n        import poplib\n')
        self.assertEqual(names(source), {'socket': [2], 'ssl': [4], 'urllib.request': [6], 'smtplib': [10],
                                         'poplib': [13]})

    def test_every_line_of_a_repeated_import_is_kept(self):
        self.assertEqual(names('import socket\ndef again():\n    import socket\n'), {'socket': [1, 3]})

    def test_literal_dynamic_imports(self):
        source = ('import importlib\nimportlib.import_module("socket")\n__import__("http.client")\n'
                  'from importlib import import_module as load\nload("ssl")\n'
                  '__import__("http", fromlist=["server"])\nimportlib.import_module(name="smtplib")\n'
                  'importlib.import_module(".local", "alfred")\nimportlib.import_module("json")\n')
        self.assertEqual(names(source), {'socket': [2], 'http.client': [3], 'ssl': [5], 'http.server': [6],
                                         'smtplib': [7]})
        self.assertEqual(warnings(source), [])

    def test_dynamic_import_of_a_run_time_name_warns(self):
        source = 'import importlib\nname = "so" + "cket"\nimportlib.import_module(name)\n__import__(name)\n'
        self.assertEqual(names(source), {})
        self.assertEqual(warnings(source), [
            (3, 'imports a module named at run time through importlib.import_module; this audit cannot see which'),
            (4, 'imports a module named at run time through __import__; this audit cannot see which')])

    def test_relative_imports_are_first_party(self):
        source = 'from . import socket\nfrom .httpd import make_server\nfrom ..ssl import context\n'
        self.assertEqual(names(source), {})

    def test_names_in_strings_and_comments_are_ignored(self):
        source = '"""import socket"""\n# import ssl\nBANNED = ("socket.", "urllib.request")\n'
        self.assertEqual(names(source), {})

    def test_third_party_network_clients(self):
        source = ('import requests\nfrom httpx import Client\nfrom playwright.sync_api import sync_playwright\n'
                  'import urllib3\n')
        self.assertEqual(names(source), {'requests': [1], 'httpx': [2], 'playwright.sync_api': [3], 'urllib3': [4]})

    def test_similar_names_are_not_confused(self):
        source = 'import sockets_helper\nimport sslkeys\nimport requests_cache_free_lookalike\n'
        self.assertEqual(names(source), {})

    def test_syntax_error_raises_for_the_caller_to_report(self):
        with self.assertRaises(SyntaxError):
            ea.scan_source('def broken(:\n')


class SubprocessWarningTests(unittest.TestCase):
    def test_network_programs_run_through_subprocess_warn(self):
        source = ('import subprocess, os\nfrom subprocess import run as go\n'
                  'subprocess.run(["curl", "-s", address])\ngo(["/usr/bin/wget", address])\n'
                  'os.system("cd work && ssh host true")\nsubprocess.check_output(["git", "fetch", "origin"])\n'
                  'subprocess.run(["git", "diff"])\nsubprocess.run(command)\nsubprocess.run(["python3", "-c", "1"])\n'
                  'os.execvp("rsync", ["rsync", "a", "b"])\nos.spawnlp(os.P_WAIT, "scp", "scp", "a", "b")\n')
        self.assertEqual(names(source), {})
        tail = '; this audit cannot see what another program sends'
        self.assertEqual(warnings(source), [
            (3, 'runs curl through subprocess.run' + tail),
            (4, 'runs wget through subprocess.run' + tail),
            (5, 'runs ssh through os.system' + tail),
            (6, 'runs git fetch through subprocess.check_output' + tail),
            (10, 'runs rsync through os.execvp' + tail),
            (11, 'runs scp through os.spawnlp' + tail)])

    def test_unrelated_calls_named_run_do_not_warn(self):
        self.assertEqual(warnings('runner.run(["curl"])\nrun("wget")\n'), [])


class AuditTests(unittest.TestCase):
    def test_clean_tree_passes(self):
        tree = Tree(self, {'alfred/core.py': 'import json\n', 'tools/report.py': 'import os\n'})
        report = tree.audit()
        self.assertEqual((report.files, report.findings, report.warnings), (2, [], []))
        self.assertEqual(tree.run(), (0, ['egress audit ok: 2 files scanned, 0 allowlisted network imports, '
                                          '0 warnings'], []))

    def test_unlisted_network_import_fails(self):
        tree = Tree(self, {'alfred/net.py': 'import json\nimport socket\n\ndef f():\n    import socket\n'})
        self.assertEqual(tree.audit().findings,
                         ['alfred/net.py:2: socket is a network import that is not on the allowlist (also line 5)'])
        self.assertEqual(tree.run(), (1, ['egress audit failed: 1 finding'], [
            'error: alfred/net.py:2: socket is a network import that is not on the allowlist (also line 5)']))

    def test_allowlisted_module_passes(self):
        source = 'from http.server import HTTPServer\nfrom urllib.parse import urlsplit\n'
        tree = Tree(self, {'alfred/server.py': source},
                    [entry('alfred/server.py', ['http.server', 'urllib.parse'], 'Loopback server only.')])
        report = tree.audit()
        self.assertEqual((report.findings, report.allowed), ([], 2))
        self.assertEqual(tree.run()[0], 0)

    def test_allowlist_is_exact_per_module_and_per_import(self):
        tree = Tree(self, {'alfred/server.py': 'import http.server\nimport socket\n',
                           'alfred/other.py': 'import http.server\n'},
                    [entry('alfred/server.py', ['http.server'])])
        self.assertEqual(tree.audit().findings, [
            'alfred/other.py:1: http.server is a network import that is not on the allowlist',
            'alfred/server.py:2: socket is a network import that is not on the allowlist'])

    def test_allowing_a_parser_does_not_allow_the_whole_package(self):
        tree = Tree(self, {'tools/fetch.py': 'import urllib.parse\nimport urllib.request\n'},
                    [entry('tools/fetch.py', ['urllib.parse'])])
        self.assertEqual(tree.audit().findings,
                         ['tools/fetch.py:2: urllib.request is a network import that is not on the allowlist'])

    def test_stale_entry_for_a_file_that_no_longer_exists(self):
        tree = Tree(self, {'alfred/core.py': 'import json\n'}, [entry('alfred/gone.py', ['socket'])])
        self.assertEqual(tree.audit().findings, [ALLOW + ': stale entry: alfred/gone.py no longer exists'])
        self.assertEqual(tree.run()[0], 1)

    def test_stale_entry_for_an_import_no_longer_used(self):
        tree = Tree(self, {'alfred/server.py': 'import http.server\n'},
                    [entry('alfred/server.py', ['http.server', 'socket'])])
        self.assertEqual(tree.audit().findings, [ALLOW + ': stale entry: alfred/server.py no longer imports socket'])

    def test_stale_entry_for_a_module_with_no_network_use_left(self):
        tree = Tree(self, {'alfred/core.py': 'import json\n'}, [entry('alfred/core.py', ['urllib.parse'])])
        self.assertEqual(tree.audit().findings,
                         [ALLOW + ': stale entry: alfred/core.py no longer imports urllib.parse'])

    def test_syntax_error_is_reported_and_the_rest_still_audited(self):
        tree = Tree(self, {'alfred/broken.py': 'import socket\ndef broken(:\n', 'alfred/net.py': 'import ssl\n'},
                    [entry('alfred/broken.py', ['socket'])])
        findings = tree.audit().findings
        self.assertEqual(len(findings), 2)
        self.assertTrue(findings[0].startswith('alfred/broken.py:2: cannot be parsed, so it was not audited ('))
        self.assertEqual(findings[1], 'alfred/net.py:1: ssl is a network import that is not on the allowlist')
        self.assertEqual(tree.run()[0], 1)

    def test_undecodable_and_null_byte_files_are_reported(self):
        tree = Tree(self, {'alfred/latin.py': b'NAME = "\xff"\n', 'alfred/nul.py': b'import os\x00\n'})
        findings = tree.audit().findings
        self.assertEqual([f.split(':')[0] for f in findings], ['alfred/latin.py', 'alfred/nul.py'])
        self.assertTrue(all('cannot be parsed, so it was not audited' in f for f in findings))

    def test_declared_source_encoding_is_respected(self):
        tree = Tree(self, {'alfred/legacy.py': b'# -*- coding: latin-1 -*-\nimport socket\nNAME = "\xe9"\n'})
        self.assertEqual(tree.audit().findings,
                         ['alfred/legacy.py:2: socket is a network import that is not on the allowlist'])

    def test_third_party_is_never_read(self):
        tree = Tree(self, {'third_party/pkg/net.py': 'import socket\n',
                           'alfred/third_party/broken.py': 'def broken(:\n',
                           'tools/third_party/net.py': 'import ssl\n',
                           'alfred/core.py': 'import json\n'})
        report = tree.audit()
        self.assertEqual((report.files, report.findings), (1, []))

    def test_root_inside_third_party_is_refused(self):
        tree = Tree(self, {'alfred/core.py': 'import json\n'}, root_name='third_party/clone')
        with self.assertRaisesRegex(ea.AuditError, 'third_party'):
            tree.audit()
        code, out, err = tree.run()
        self.assertEqual((code, out), (2, ['egress audit could not run']))
        self.assertTrue(err[0].startswith('error: '))

    def test_missing_scanned_folder_is_refused(self):
        tree = Tree(self, {})
        (tree.root / 'alfred').rmdir()
        with self.assertRaisesRegex(ea.AuditError, 'alfred/ is missing'):
            tree.audit()
        self.assertEqual(tree.run()[0], 2)

    def test_scanned_code_is_never_executed(self):
        with tempfile.TemporaryDirectory() as outside:
            marker = Path(outside) / 'ran.txt'
            boom = f'import pathlib\npathlib.Path({str(marker)!r}).write_text("ran")\nraise SystemExit(3)\n'
            tree = Tree(self, {'alfred/boom.py': boom, 'tools/boom_tool.py': boom})
            self.assertEqual(tree.audit().findings, [])
            self.assertFalse(marker.exists())

    @unittest.skipUnless(hasattr(os, 'symlink'), 'symbolic links are unavailable')
    def test_symbolic_links_are_reported_not_followed(self):
        tree = Tree(self, {'tools/real/net.py': 'import socket\n'})
        os.symlink(tree.root / 'tools/real/net.py', tree.root / 'alfred/linked.py')
        os.symlink(tree.root / 'tools/real', tree.root / 'alfred/linked_dir')
        self.assertEqual(tree.audit().findings, [
            'alfred/linked.py: is a symbolic link, so it was not audited',
            'alfred/linked_dir: is a symbolic link, so it was not audited',
            'tools/real/net.py:1: socket is a network import that is not on the allowlist'])

    def test_output_is_sorted_and_deterministic(self):
        files = {'tools/z.py': 'import ssl\n', 'alfred/b/c.py': 'import socket\nimport ftplib\n',
                 'alfred/a.py': 'import subprocess\nsubprocess.run(["curl", url])\nimport smtplib\n'}
        tree = Tree(self, files, [entry('alfred/gone.py', ['socket'])])
        first, second = tree.run(), tree.run()
        self.assertEqual(first, second)
        self.assertEqual(first, (1, ['egress audit failed: 5 findings'], [
            'error: alfred/a.py:3: smtplib is a network import that is not on the allowlist',
            'error: alfred/b/c.py:1: socket is a network import that is not on the allowlist',
            'error: alfred/b/c.py:2: ftplib is a network import that is not on the allowlist',
            'error: tools/egress_allowlist.json: stale entry: alfred/gone.py no longer exists',
            'error: tools/z.py:1: ssl is a network import that is not on the allowlist',
            'warning: alfred/a.py:2: runs curl through subprocess.run; this audit cannot see what another '
            'program sends']))

    def test_warnings_alone_do_not_fail(self):
        tree = Tree(self, {'tools/fetch.py': 'import subprocess\nsubprocess.run(["curl", address])\n'})
        self.assertEqual(tree.run(), (0, ['egress audit ok: 1 file scanned, 0 allowlisted network imports, '
                                          '1 warning'], [
            'warning: tools/fetch.py:2: runs curl through subprocess.run; this audit cannot see what another '
            'program sends']))

    def test_explicit_allowlist_path(self):
        tree = Tree(self, {'alfred/net.py': 'import socket\n'})
        other = tree.write('elsewhere.json', json.dumps({'schema': 1, 'entries': [entry('alfred/net.py', ['socket'])]}))
        self.assertEqual(tree.run('--allowlist', str(other))[0], 0)
        self.assertEqual(tree.run()[0], 1)

    def test_unknown_argument_is_a_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            ea.main(['--no-such-option'])
        self.assertEqual(caught.exception.code, 2)


class MalformedAllowlistTests(unittest.TestCase):
    def assert_malformed(self, allowlist, fragment):
        tree = Tree(self, {'alfred/core.py': 'import json\n'}, allowlist=allowlist)
        with self.assertRaises(ea.AuditError) as caught:
            tree.audit()
        self.assertIn(fragment, str(caught.exception))
        code, out, err = tree.run()
        self.assertEqual((code, out, len(err)), (2, ['egress audit could not run'], 1))
        self.assertTrue(err[0].startswith('error: ' + ALLOW + ' is malformed: '))

    def bad_entry(self, item, fragment):
        self.assert_malformed(json.dumps({'schema': 1, 'entries': [item]}), fragment)

    def test_not_json(self):
        self.assert_malformed('{"schema": 1,', 'not valid JSON')

    def test_top_level_shape(self):
        self.assert_malformed('[]', 'must be a JSON object')
        self.assert_malformed('{"schema": 2, "entries": []}', 'schema must be 1')
        self.assert_malformed('{"schema": true, "entries": []}', 'schema must be 1')
        self.assert_malformed('{"schema": 1}', 'entries must be a list')
        self.assert_malformed('{"schema": 1, "entries": [], "extra": 1}', 'unknown key extra')

    def test_entry_shape(self):
        self.bad_entry([], 'entry 1 must be an object')
        self.bad_entry({'module': 'alfred/core.py', 'imports': ['socket']}, 'entry 1 is missing reason')
        self.bad_entry(dict(entry('alfred/core.py', ['socket']), note='x'), 'entry 1 has unknown key note')
        self.bad_entry(entry('alfred/core.py', ['socket'], ''), 'reason must be one non-empty line')
        self.bad_entry(entry('alfred/core.py', ['socket'], 'Two\nlines'), 'reason must be one non-empty line')
        self.bad_entry(entry('alfred/core.py', ['socket'], 7), 'reason must be one non-empty line')
        self.bad_entry(entry('alfred/core.py', []), 'imports must be a non-empty list')
        self.bad_entry(entry('alfred/core.py', 'socket'), 'imports must be a non-empty list')
        self.bad_entry(entry('alfred/core.py', ['socket', 'socket']), 'lists socket twice')
        self.bad_entry(entry('alfred/core.py', [3]), 'imports must be dotted module names')

    def test_import_that_is_not_a_watched_network_module(self):
        self.bad_entry(entry('alfred/core.py', ['json']), 'entry 1: json is not a watched network module')
        self.bad_entry(entry('alfred/core.py', ['http']), 'entry 1: http is not a watched network module')

    def test_module_paths(self):
        for module in ('/abs/alfred/core.py', 'alfred/../tools/x.py', 'alfred\\core.py', 'alfred/./core.py',
                       'alfred/core.txt', 'tests/test_core.py', 'alfred/third_party/x.py', 'third_party/x.py', 7):
            with self.subTest(module=module):
                self.bad_entry(entry(module, ['socket']), 'entry 1: module must be')

    def test_duplicate_module(self):
        self.assert_malformed(json.dumps({'schema': 1, 'entries': [entry('alfred/core.py', ['socket']),
                                                                    entry('alfred/core.py', ['ssl'])]}),
                              'entry 2 repeats alfred/core.py')

    def test_missing_allowlist(self):
        tree = Tree(self, {'alfred/core.py': 'import json\n'})
        (tree.root / ALLOW).unlink()
        with self.assertRaisesRegex(ea.AuditError, 'cannot be read'):
            tree.audit()
        self.assertEqual(tree.run()[0], 2)


class ShippedAuditTests(unittest.TestCase):
    def test_watched_modules_cover_the_brief(self):
        for name in ('urllib', 'http.client', 'http.server', 'socket', 'ssl', 'smtplib', 'ftplib', 'socketserver',
                     'xmlrpc', 'asyncio.streams', 'asyncio.open_connection', 'asyncio.start_server'):
            self.assertIn(name, ea.WATCHED)
        self.assertEqual(list(ea.WATCHED), sorted(ea.WATCHED))

    def test_self_test_passes(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ea.main(['--self-test'])
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        self.assertTrue(out.getvalue().splitlines()[-1].startswith('self-test ok: '))

    def test_real_tree_passes_with_the_shipped_allowlist(self):
        report = ea.audit(ROOT)
        self.assertEqual(report.findings, [])
        self.assertGreater(report.files, 0)

    def test_shipped_allowlist_is_sorted_and_explained(self):
        data = json.loads((ROOT / ALLOW).read_text(encoding='utf-8'))
        modules = [item['module'] for item in data['entries']]
        self.assertEqual(modules, sorted(modules))
        for item in data['entries']:
            self.assertEqual(item['imports'], sorted(item['imports']))
            self.assertNotIn('\N{EM DASH}', item['reason'])

    def test_every_allowlisted_module_is_named_in_the_documentation(self):
        data = json.loads((ROOT / ALLOW).read_text(encoding='utf-8'))
        document = (ROOT / 'docs/EGRESS_AUDIT.md').read_text(encoding='utf-8')
        for item in data['entries']:
            self.assertIn('`' + item['module'] + '`', document)


if __name__ == '__main__':
    unittest.main()
