"""The public repository hygiene check (tools/check_public_hygiene.py, backlog item A7).

Every credential, home-directory path and email address below is invented and built at run
time from pieces, so this file holds none of them as a literal and the check itself finds
nothing here. Each test builds a throwaway Git repository in a temporary folder, with
invented user settings set only inside it. Nothing touches the network or the real
repository's files, apart from one test that reads the committed allowlist.
"""
from __future__ import annotations
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from alfred import scrub
from tools import check_public_hygiene as hygiene

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools' / 'check_public_hygiene.py'
A36 = 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8'
B64 = 'Zm9vYmFyYmF6cXV4' * 4


def fake(*parts):
    return ''.join(parts)


def pem():
    dashes = '-' * 5
    body = '\n'.join(['MII' + B64[:61]] * 3)
    return f'{dashes}BEGIN PRIVATE KEY{dashes}\n{body}\n{dashes}END PRIVATE KEY{dashes}'


HOME = fake('/ho', 'me/')
USERS = fake('/Us', 'ers/')
AT = '@'
EMAIL = fake('alice.writer', AT, 'example.invalid')

# One invented value per kind and the line it sits on. The value is the exact text the
# check hashes; it must never appear in anything the check prints.
SAMPLES = {
    'private_key': ('key file:\n{}\nend', pem()),
    'anthropic_key': ('claude key {} set', fake('sk', '-ant-', 'api03-', A36, A36)),
    'openai_key': ('use {} for it', fake('sk', '-proj-', A36, '_', A36)),
    'github_token': ('remote uses {} today', fake('gh', 'p_', A36)),
    'gitlab_token': ('token {} here', fake('gl', 'pat-', A36[:20])),
    'slack_webhook': ('post to {} now', fake('https://hooks.', 'slack.com/services/', 'T0ABC1DEF/', 'B0GHI2JKL/', A36[:24])),
    'slack_token': ('bot {} set', fake('xo', 'xb-', '1234567890-0987654321-', A36[:24])),
    'stripe_key': ('charge with {}', fake('sk', '_live_', A36[:24])),
    'google_api_key': ('maps {} ok', fake('AI', 'za', 'Sy', A36[:33])),
    'google_oauth': ('client {} here', fake('GOC', 'SPX-', A36[:28])),
    'npm_token': ('publish with {}', fake('np', 'm_', A36)),
    'aws_access_key_id': ('key id {}', fake('AK', 'IA', 'Q3EXAMPLE7KEYID9')),
    'aws_secret_access_key': (fake('aws_secret', '_access_key={}'), fake('wJalr', 'XUtnF', 'EMI/K7MDENG/bPxRfi', 'CYEXAMPLEKEY')),
    'azure_storage_key': (fake('Account', 'Key={};EndpointSuffix=core'), fake('a' * 40, 'B' * 40, '0123==')),
    'jwt': ('session {} expired', fake('ey', 'JhbGciOiJIUzI1NiJ9', '.', 'ey', 'JzdWIiOiIxMjM0NTY3ODkwIn0', '.', 'SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV')),
    'url_password': (fake('db at postgres://owner', ':{}', AT, 'db.example.invalid:5432/x'), fake('s3cr', 'etPass!')),
    'authorization_header': (fake('Author', 'ization: Bearer {}'), fake('abc', '123DEF456ghi789')),
    'password': (fake('login pass', 'word: {} for the drive'), fake('Hunt', 'er-42')),
    'secret_assignment': (fake('client', '_secret = "{}"'), fake('q8W', 'e7rT6', 'y5U4')),
    'home_path': ('notes live in {}/notes', fake(HOME, 'alice')),
    'email': ('write to {} today', EMAIL),
}


def sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def git(root, *args):
    return subprocess.run(('git', '-C', str(root)) + args, check=True, capture_output=True, text=True).stdout


class Repo:
    """A throwaway Git repository with invented user settings set only inside it."""

    def __init__(self, test):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'repo'
        self.root.mkdir()
        git(self.root, 'init', '-q')
        for key, value in (('user.name', 'Invented Writer'), ('user.email', fake('writer', AT, 'example.invalid')),
                           ('commit.gpgsign', 'false'), ('core.autocrlf', 'false'),
                           ('core.hooksPath', str(Path(self.tmp.name) / 'no-hooks'))):
            git(self.root, 'config', key, value)

    def write(self, path, content):
        full = self.root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            full.write_bytes(content)
        else:
            full.write_text(content, encoding='utf-8', newline='')
        return full

    def add(self, path, content):
        self.write(path, content)
        git(self.root, 'add', '--', path)

    def commit(self):
        git(self.root, 'commit', '-q', '-m', 'synthetic', '--allow-empty')

    def allowlist(self, entries, name='allow.json', raw=None):
        path = Path(self.tmp.name) / name
        path.write_text(raw if raw is not None else json.dumps({'entries': entries}), encoding='utf-8')
        return path

    def run(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = hygiene.main(['--root', str(self.root), *args])
        return code, out.getvalue(), err.getvalue()


def entry(file, kind, value, reason='Invented value in a synthetic test file.'):
    return {'file': file, 'kind': kind, 'sha256': sha(value), 'reason': reason}


class Kinds(unittest.TestCase):
    def test_the_kinds_are_the_scrubber_kinds_then_two_more(self):
        self.assertEqual(hygiene.KINDS, scrub.KINDS + ('home_path', 'email'))
        self.assertEqual(sorted(SAMPLES), sorted(hygiene.KINDS))

    def test_each_sample_is_exactly_one_finding_of_its_kind(self):
        for kind, (template, value) in SAMPLES.items():
            with self.subTest(kind=kind):
                text = template.format(value)
                found = hygiene.find(text)
                self.assertEqual([k for k, _, _ in found], [kind])
                self.assertEqual(text[found[0][1]:found[0][2]], value)


class HomePaths(unittest.TestCase):
    def matches(self, text):
        return [text[s:e] for k, s, e in hygiene.find(text) if k == 'home_path']

    def test_named_home_folders_are_found(self):
        win = fake('C:', '\\', 'Users', '\\')
        cases = {
            fake('cd ', HOME, 'alice/x'): fake(HOME, 'alice'),
            fake('see ', HOME, 'claude/wt-hygiene/tools'): fake(HOME, 'claude'),
            fake(USERS, 'bob.smith/Documents'): fake(USERS, 'bob.smith'),
            fake('"', USERS, 'carol_1"'): fake(USERS, 'carol_1'),
            fake('file://', HOME, 'dave/notes'): fake(HOME, 'dave'),
            fake('../', HOME[1:], 'ivan/x'): fake(HOME, 'ivan'),
            fake(win, 'Erin\\Desktop'): fake(win, 'Erin'),
            fake('d:/', 'users/', 'frank/x'): fake('d:/', 'users/', 'frank'),
            fake('"C:', '\\\\', 'Users', '\\\\', 'grace\\\\x"'): fake('C:', '\\\\', 'Users', '\\\\', 'grace'),
            fake('at ', HOME, 'heidi'): fake(HOME, 'heidi'),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.matches(text), [expected])

    def test_placeholders_and_variables_name_no_one(self):
        for text in (fake(HOME, '<name>/x'), fake(HOME, '{user}/x'), fake(HOME, '$USER/x'), fake(HOME, '${USER}/x'),
                     fake(HOME, '*/x'), fake(HOME, '.../x'), fake(HOME, 'user/x'), fake(HOME, 'USERNAME/x'),
                     fake(HOME, 'you/x'), fake(HOME, 'me/x'), fake(HOME, 'name/x'), fake(HOME, 'your-name/x'),
                     fake(HOME, 'example/x'), fake(USERS, 'Shared/x'), fake(USERS, 'yourname/x'),
                     fake('C:', '\\', 'Users', '\\', 'Public\\x'), fake('C:', '\\', 'Users', '\\', 'Default\\x'),
                     fake('C:', '\\', 'Users', '\\', '%USERNAME%\\x'), '$HOME/.config/alfred', '${HOME}/x', '~/Notes',
                     '%USERPROFILE%\\x', fake('under ', HOME, ' only'), HOME):
            with self.subTest(text=text):
                self.assertEqual(self.matches(text), [])

    def test_home_inside_another_path_or_address_is_not_a_home_folder(self):
        for text in (fake('https://example.invalid', HOME, 'page'), fake('/var', HOME, 'alice'),
                     fake('api', USERS, '12'), fake('/api/users/', '12'), fake('x', HOME, 'alice'),
                     fake('C:', '\\', 'Program Files\\x'), fake('AC:', '\\', 'Users', '\\', 'x')):
            with self.subTest(text=text):
                self.assertEqual(self.matches(text), [])


class Emails(unittest.TestCase):
    def matches(self, text):
        return [text[s:e] for k, s, e in hygiene.find(text) if k == 'email']

    def test_addresses_are_found(self):
        for value in (EMAIL, fake('a', AT, 'b.co'), fake('first.last+tag', AT, 'mail.example.org'),
                      fake('x_y-z', AT, 'sub-domain.example.co.uk'), fake('bot', AT, 'users.noreply.example.com')):
            with self.subTest(value=value):
                self.assertEqual(self.matches(f'mailto:{value}, then <{value}>.'), [value, value])

    def test_things_with_an_at_sign_that_are_not_addresses(self):
        for text in ('@property', 'import "@types/node"', fake('react', AT, '18.3.1'), fake('three', AT, '0.160.0/x'),
                     fake('user', AT, 'localhost'), fake('a', AT, 'b'), fake('x ', AT, ' y.com'), 'a @ b.com',
                     fake('name', AT, '-bad.com'), '[redacted:email]'):
            with self.subTest(text=text):
                self.assertEqual(self.matches(text), [])

    def test_an_address_inside_a_secret_is_reported_once_as_the_secret(self):
        cases = {
            fake('see https://alice', ':', 'Pw7x9q', AT, 'host.example.org/x'): ['url_password'],
            fake('write a', AT, 'AK', 'IA', 'Q3EXAMPLE7KEYID9', '.com'): ['aws_access_key_id'],
            fake('pass', 'word: "', HOME, 'alice/x9"'): ['password'],
            fake(EMAIL, ' https://bob:', 'Pw7x9q', AT, 'h.example.org ', EMAIL): ['email', 'url_password', 'email'],
        }
        for text, kinds in cases.items():
            with self.subTest(text=text[:12]):
                self.assertEqual([k for k, _, _ in hygiene.find(text)], kinds)


class Scanning(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)

    def test_each_kind_in_a_tracked_file_is_reported_with_file_line_kind_and_hash(self):
        for kind, (template, value) in SAMPLES.items():
            self.repo.add(f'samples/{kind}.txt', 'first line\n' + template.format(value) + '\n')
        self.repo.commit()
        code, out, err = self.repo.run()
        self.assertEqual(code, 1)
        lines = [l for l in out.splitlines() if l.startswith('samples/')]
        expected = sorted(f'samples/{kind}.txt:{3 if kind == "private_key" else 2}: {kind} {sha(value)[:12]}'
                          for kind, (_, value) in SAMPLES.items())
        self.assertEqual(lines, expected)
        self.assertIn(f'{len(SAMPLES)} findings: 0 allowed by reviewed exceptions, {len(SAMPLES)} not allowed; '
                      '0 stale exceptions', out)
        self.assertTrue(out.rstrip().endswith('public hygiene: failed'))
        self.assertEqual(err, '')

    def test_a_clean_repository_passes(self):
        self.repo.add('README.md', '# Plan\nAsk the accountant about the deposit. Data lives in ~/Notes.\n')
        self.repo.commit()
        code, out, err = self.repo.run()
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(out, 'scanned 1 tracked files (0 of them symbolic links); skipped 0 under third_party/, '
                              '0 binary, 0 submodules, 0 missing from the working tree\n'
                              '0 findings: 0 allowed by reviewed exceptions, 0 not allowed; 0 stale exceptions\n'
                              'public hygiene: ok\n')

    def test_line_numbers_count_lf_and_crlf_and_several_per_file(self):
        self.repo.add('a.txt', fake('one\r\ntwo ', EMAIL, '\r\n\r\nfour ', EMAIL, ' and ', HOME, 'alice/\n'))
        code, out, _ = self.repo.run()
        self.assertEqual([l for l in out.splitlines() if l.startswith('a.txt')],
                         [f'a.txt:2: email {sha(EMAIL)[:12]}', f'a.txt:4: email {sha(EMAIL)[:12]}',
                          f'a.txt:4: home_path {sha(fake(HOME, "alice"))[:12]}'])

    def test_binary_files_are_skipped_and_counted(self):
        self.repo.add('img.bin', b'\x89PNG\x00\x00' + EMAIL.encode())
        self.repo.add('latin.txt', ('caf\u00e9 ' + EMAIL).encode('latin-1'))
        self.repo.add('late-nul.txt', b'x' * 9000 + b'\x00 ' + EMAIL.encode())
        code, out, _ = self.repo.run()
        self.assertEqual(code, 1)
        self.assertIn('scanned 1 tracked files', out)
        self.assertIn('2 binary', out)
        self.assertEqual([l.split(':')[0] for l in out.splitlines() if ': email ' in l], ['late-nul.txt'])

    def test_third_party_is_skipped_only_at_the_top(self):
        self.repo.add('third_party/lib/README.md', EMAIL)
        self.repo.add('docs/third_party/notes.md', EMAIL)
        code, out, _ = self.repo.run()
        self.assertEqual(code, 1)
        self.assertIn('skipped 1 under third_party/', out)
        self.assertEqual([l.split(':')[0] for l in out.splitlines() if ': email ' in l], ['docs/third_party/notes.md'])

    def test_untracked_ignored_and_deleted_files_are_never_read(self):
        self.repo.add('.gitignore', 'ignored.txt\n')
        self.repo.add('gone.txt', 'clean\n')
        self.repo.commit()
        (self.repo.root / 'gone.txt').unlink()
        self.repo.write('untracked.txt', EMAIL)
        self.repo.write('ignored.txt', EMAIL)
        code, out, _ = self.repo.run()
        self.assertEqual(code, 0)
        self.assertIn('scanned 1 tracked files', out)
        self.assertIn('1 missing from the working tree', out)

    def test_a_tracked_symbolic_link_is_checked_by_its_target_text_never_followed(self):
        (Path(self.repo.tmp.name) / 'outside.txt').write_text(EMAIL, encoding='utf-8')
        os.symlink('../outside.txt', self.repo.root / 'link-out')
        os.symlink(fake(HOME, 'alice/notes'), self.repo.root / 'link-home')
        git(self.repo.root, 'add', 'link-out', 'link-home')
        code, out, _ = self.repo.run()
        self.assertIn('scanned 2 tracked files (2 of them symbolic links)', out)
        self.assertNotIn(': email ', out)
        self.assertEqual([l for l in out.splitlines() if l.startswith('link-')],
                         [f'link-home:1: home_path {sha(fake(HOME, "alice"))[:12]}'])
        self.assertEqual(code, 1)

    def test_a_submodule_is_skipped_and_counted(self):
        sub = Repo(self)
        sub.add('x.txt', EMAIL)
        sub.commit()
        head = git(sub.root, 'rev-parse', 'HEAD').strip()
        git(self.repo.root, 'update-index', '--add', '--cacheinfo', f'160000,{head},vendored')
        (self.repo.root / 'vendored').mkdir()
        (self.repo.root / 'vendored' / 'x.txt').write_text(EMAIL, encoding='utf-8')
        code, out, _ = self.repo.run()
        self.assertEqual(code, 0)
        self.assertIn('1 submodules', out)

    def test_a_subfolder_root_scans_the_whole_repository(self):
        self.repo.add('docs/a.md', EMAIL)
        self.repo.add('b.md', EMAIL)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = hygiene.main(['--root', str(self.repo.root / 'docs')])
        self.assertEqual(code, 1)
        self.assertEqual([l.split(':')[0] for l in out.getvalue().splitlines() if ': email ' in l], ['b.md', 'docs/a.md'])

    def test_not_a_git_repository_is_a_usage_error(self):
        empty = Path(self.repo.tmp.name) / 'plain'
        empty.mkdir()
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, GIT_CEILING_DIRECTORIES=self.repo.tmp.name), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = hygiene.main(['--root', str(empty)])
        self.assertEqual((code, out.getvalue()), (2, ''))
        self.assertIn('not inside a Git repository', err.getvalue())


class Allowlist(unittest.TestCase):
    def setUp(self):
        self.repo = Repo(self)
        self.repo.add('tests/t.py', fake('x = "', EMAIL, '"\ny = "', EMAIL, '"\n'))
        self.repo.add('docs/d.md', fake('Path ', HOME, 'alice/x\n'))

    def test_reviewed_entries_allow_every_occurrence_in_their_file(self):
        path = self.repo.allowlist([entry('tests/t.py', 'email', EMAIL), entry('docs/d.md', 'home_path', fake(HOME, 'alice'))])
        code, out, err = self.repo.run('--allowlist', str(path))
        self.assertEqual((code, err), (0, ''))
        self.assertIn('3 findings: 3 allowed by reviewed exceptions, 0 not allowed; 0 stale exceptions', out)
        self.assertNotIn('tests/t.py:', out)

    def test_an_entry_allows_only_its_own_file_kind_and_text(self):
        other = fake('bob', AT, 'example.invalid')
        path = self.repo.allowlist([entry('docs/d.md', 'email', EMAIL), entry('tests/t.py', 'email', other),
                                    entry('tests/t.py', 'home_path', EMAIL), entry('docs/d.md', 'home_path', fake(HOME, 'alice'))])
        code, out, _ = self.repo.run('--allowlist', str(path))
        self.assertEqual(code, 1)
        self.assertEqual([l for l in out.splitlines() if l.startswith('tests/')],
                         [f'tests/t.py:1: email {sha(EMAIL)[:12]}', f'tests/t.py:2: email {sha(EMAIL)[:12]}'])
        self.assertEqual([l for l in out.splitlines() if 'stale' in l and l.startswith('allowlist')],
                         [f'allowlist entry 1 is stale: docs/d.md email {sha(EMAIL)[:12]} matches nothing',
                          f'allowlist entry 2 is stale: tests/t.py email {sha(other)[:12]} matches nothing',
                          f'allowlist entry 3 is stale: tests/t.py home_path {sha(EMAIL)[:12]} matches nothing'])
        self.assertIn('3 findings: 1 allowed by reviewed exceptions, 2 not allowed; 3 stale exceptions', out)

    def test_a_stale_entry_fails_even_when_nothing_else_is_found(self):
        path = self.repo.allowlist([entry('tests/t.py', 'email', EMAIL), entry('docs/d.md', 'home_path', fake(HOME, 'alice')),
                                    entry('removed.py', 'email', EMAIL)])
        code, out, _ = self.repo.run('--allowlist', str(path))
        self.assertEqual(code, 1)
        self.assertIn(f'allowlist entry 3 is stale: removed.py email {sha(EMAIL)[:12]} matches nothing', out)
        self.assertTrue(out.rstrip().endswith('public hygiene: failed'))

    def test_the_default_allowlist_is_read_from_the_repository_and_may_be_absent(self):
        code, out, _ = self.repo.run()
        self.assertEqual(code, 1)
        self.assertIn('3 not allowed', out)
        self.repo.write('tools/public_hygiene_allowlist.json', json.dumps({'entries': [
            entry('tests/t.py', 'email', EMAIL), entry('docs/d.md', 'home_path', fake(HOME, 'alice'))]}))
        self.assertEqual(self.repo.run()[0], 0)

    def test_a_named_allowlist_that_does_not_exist_is_a_usage_error(self):
        code, out, err = self.repo.run('--allowlist', str(Path(self.repo.tmp.name) / 'missing.json'))
        self.assertEqual((code, out), (2, ''))
        self.assertIn('cannot read the allowlist', err)

    def test_malformed_allowlists_fail_with_clear_value_free_errors(self):
        secret = fake('gh', 'p_', A36)
        good = entry('tests/t.py', 'email', EMAIL)
        cases = {
            'not json': ('{"entries": [', 'the allowlist is not valid JSON (line 1, column 14)'),
            'a list': ('[]', 'the allowlist must be a JSON object with an "entries" list'),
            'no entries': ('{}', 'the allowlist must be a JSON object with an "entries" list'),
            'entries not a list': ('{"entries": {}}', 'the allowlist must be a JSON object with an "entries" list'),
            'unknown top key': (json.dumps({'entries': [], secret: 1}), 'the allowlist has an unknown top-level key'),
            'repeated key': ('{"entries": [], "entries": []}', 'the allowlist repeats a key inside one object'),
            'about not text': (json.dumps({'entries': [], 'about': 3}), 'the allowlist "about" must be text'),
            'entry not object': (json.dumps({'entries': [good, 'x']}), 'allowlist entry 2 must be an object'),
            'missing key': (json.dumps({'entries': [{k: v for k, v in good.items() if k != 'reason'}]}),
                            'allowlist entry 1 must have exactly the keys file, kind, sha256 and reason'),
            'extra key': (json.dumps({'entries': [dict(good, value=secret)]}),
                          'allowlist entry 1 must have exactly the keys file, kind, sha256 and reason'),
            'absolute file': (json.dumps({'entries': [dict(good, file='/' + secret)]}),
                              'allowlist entry 1: file must be a relative path inside the repository'),
            'dotted file': (json.dumps({'entries': [dict(good, file='a/../' + secret)]}),
                            'allowlist entry 1: file must be a relative path inside the repository'),
            'backslash file': (json.dumps({'entries': [dict(good, file='a\\b')]}),
                               'allowlist entry 1: file must be a relative path inside the repository'),
            'file not text': (json.dumps({'entries': [dict(good, file=3)]}),
                              'allowlist entry 1: file must be a relative path inside the repository'),
            'unknown kind': (json.dumps({'entries': [dict(good, kind=secret)]}), 'allowlist entry 1: kind is not a known kind'),
            'raw value as hash': (json.dumps({'entries': [dict(good, sha256=secret)]}),
                                  'allowlist entry 1: sha256 must be 64 lower-case hexadecimal characters'),
            'upper-case hash': (json.dumps({'entries': [dict(good, sha256=good['sha256'].upper())]}),
                                'allowlist entry 1: sha256 must be 64 lower-case hexadecimal characters'),
            'empty reason': (json.dumps({'entries': [dict(good, reason='   ')]}),
                             'allowlist entry 1: reason must be a sentence of at least 10 characters'),
            'short reason': (json.dumps({'entries': [dict(good, reason='ok')]}),
                             'allowlist entry 1: reason must be a sentence of at least 10 characters'),
            'duplicate': (json.dumps({'entries': [good, entry('docs/d.md', 'home_path', fake(HOME, 'alice')),
                                                  dict(good, reason='The same match again, reviewed twice.')]}),
                          'allowlist entry 3 repeats entry 1'),
        }
        for name, (raw, message) in cases.items():
            with self.subTest(case=name):
                path = self.repo.allowlist(None, raw=raw)
                code, out, err = self.repo.run('--allowlist', str(path))
                self.assertEqual((code, out), (2, ''))
                self.assertEqual(err, f'check_public_hygiene: {message}\n')
                self.assertNotIn(secret[:8], err)
                self.assertNotIn(EMAIL, err)

    def test_suggest_prints_entries_to_review_with_empty_reasons_that_cannot_be_pasted_unread(self):
        code, out, err = self.repo.run('--suggest')
        self.assertEqual(code, 1)
        suggested = json.loads(out)
        self.assertEqual(suggested, {'entries': [
            {'file': 'docs/d.md', 'kind': 'home_path', 'sha256': sha(fake(HOME, 'alice')), 'reason': ''},
            {'file': 'tests/t.py', 'kind': 'email', 'sha256': sha(EMAIL), 'reason': ''}]})
        self.assertIn('public hygiene: failed', err)
        path = self.repo.allowlist(None, raw=out)
        self.assertEqual(self.repo.run('--allowlist', str(path))[0], 2)


class NoValueIsEverPrinted(unittest.TestCase):
    def test_the_command_line_output_holds_no_matched_value(self):
        repo = Repo(self)
        for kind, (template, value) in SAMPLES.items():
            repo.add(f'samples/{kind}.txt', template.format(value) + '\n')
        repo.commit()
        stale = repo.allowlist([entry('samples/email.txt', 'email', fake('old', AT, 'example.invalid'))], name='stale.json')
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        for args in ([], ['--suggest'], ['--allowlist', str(stale)]):
            with self.subTest(args=args):
                done = subprocess.run([sys.executable, str(TOOL), '--root', str(repo.root), *args],
                                      capture_output=True, text=True, env=env, timeout=60)
                self.assertEqual(done.returncode, 1)
                shown = done.stdout + done.stderr
                self.assertIn('public hygiene: failed', shown)
                for kind, (_, value) in SAMPLES.items():
                    for piece in {value, value[:8], value[-8:], value.split('\n')[1] if '\n' in value else value}:
                        self.assertNotIn(piece, shown, kind)
                self.assertNotIn('alice', shown)
                self.assertNotIn('old' + AT, shown)


class BoundedCost(unittest.TestCase):
    """1 MB of hostile input for the home-path and email patterns must finish within a second."""

    MB = 1 << 20

    def test_each_hostile_megabyte_finishes_quickly(self):
        units = {'letters': 'a' * 512, 'dotted letters': 'a.' * 256, 'at signs': 'a@' * 256, 'domains': 'x@a.' * 128,
                 'hyphen labels': 'x@' + 'a-' * 200, 'home starts': HOME * 64, 'users starts': USERS + 'a' * 64,
                 'drive starts': 'C:\\Users\\' * 32, 'email floods': (EMAIL + ' ') * 16}
        for name, unit in units.items():
            text = (unit * (self.MB // len(unit) + 1))[:self.MB]
            with self.subTest(name=name):
                started = time.perf_counter()
                hygiene.find(text)
                elapsed = time.perf_counter() - started
                self.assertLess(elapsed, 1.0, f'{name}: {elapsed:.2f}s')


class TheCommittedAllowlist(unittest.TestCase):
    def test_it_is_well_formed(self):
        entries = hygiene.load_allowlist(ROOT / 'tools' / 'public_hygiene_allowlist.json')
        self.assertGreater(len(entries), 0)


if __name__ == '__main__':
    unittest.main()
