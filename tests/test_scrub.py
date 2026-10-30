"""The secret scrubber (alfred/scrub.py, coordination/BACKLOG.md item A2).

Every credential below is invented and built at run time from pieces, so no
credential-shaped literal is committed to this public repository and GitHub's push
protection has nothing to flag. Nothing here touches the network or any real account.
These tests prove that each supported kind is found and blanked, that the look-alikes
ALFRED stores everywhere (digests, commit hashes, UUIDs, its own ids) are left alone, that
a finding never carries the secret, and that hostile input cannot make the scrubber slow.
"""
from __future__ import annotations
import hashlib
import time
import unittest
import uuid

from alfred.scrub import KINDS, Finding, find_secrets, scrub

A36 = 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8'  # 36 mixed letters and digits, no meaning
B64 = 'Zm9vYmFyYmF6cXV4' * 4                    # base64-looking filler


def fake(*parts):
    return ''.join(parts)


def pem(label='PRIVATE KEY', body=None):
    body = body or '\n'.join(['MII' + B64[:61]] * 3)
    dashes = '-' * 5
    return f'{dashes}BEGIN {label}{dashes}\n{body}\n{dashes}END {label}{dashes}'


# One invented value per kind, with the text it sits in. The secret is the part the
# scrubber must blank; the context around it must survive.
CASES = {
    'private_key': ('key file:\n{}\nend', pem()),
    'aws_access_key_id': ('aws_access_key_id = {}', fake('AK', 'IA', 'Q3EXAMPLE7KEYID9')),
    'aws_secret_access_key': ('aws_secret_access_key={}', fake('wJalr', 'XUtnF', 'EMI/K7MDENG/bPxRfi', 'CYEXAMPLEKEY')),
    'azure_storage_key': ('DefaultEndpointsProtocol=https;AccountKey={};EndpointSuffix=core', fake('a' * 40, 'B' * 40, '0123==')),
    'github_token': ('remote uses {} today', fake('gh', 'p_', A36)),
    'gitlab_token': ('token {} here', fake('gl', 'pat-', A36[:20])),
    'slack_token': ('bot {} set', fake('xo', 'xb-', '1234567890-0987654321-', A36[:24])),
    'slack_webhook': ('post to {} now', fake('https://hooks.', 'slack.com/services/', 'T0ABC1DEF/', 'B0GHI2JKL/', A36[:24])),
    'stripe_key': ('charge with {}', fake('sk', '_live_', A36[:24])),
    'google_api_key': ('maps {} ok', fake('AI', 'za', 'Sy', A36[:33])),
    'google_oauth': ('client secret {}', fake('GOC', 'SPX-', A36[:28])),
    'openai_key': ('use {} for it', fake('sk', '-proj-', A36, '_', A36)),
    'anthropic_key': ('claude key {} set', fake('sk', '-ant-', 'api03-', A36, A36)),
    'npm_token': ('publish with {}', fake('np', 'm_', A36)),
    'jwt': ('session {} expired', fake('ey', 'JhbGciOiJIUzI1NiJ9', '.', 'ey', 'JzdWIiOiIxMjM0NTY3ODkwIn0', '.', 'SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV')),
    'authorization_header': ('curl -H "Authorization: Bearer {}" https://example.invalid', fake('abc', '123DEF456ghi789')),
    'url_password': ('db at postgres://owner:{}@db.example.invalid:5432/alfred', fake('s3cr', 'etPass!')),
    'password': ('login password: {} for the shared drive', fake('Hunt', 'er-42')),
    'secret_assignment': ('client_secret = "{}"', fake('q8W', 'e7rT6', 'y5U4')),
}


class EveryKindIsCaught(unittest.TestCase):
    def test_the_kinds_are_the_documented_list(self):
        self.assertEqual(sorted(KINDS), sorted(CASES))

    def test_each_kind_is_found_blanked_and_its_context_kept(self):
        for kind, (template, secret) in CASES.items():
            with self.subTest(kind=kind):
                text = template.format(secret)
                findings = find_secrets(text)
                self.assertEqual([f.kind for f in findings], [kind])
                f = findings[0]
                self.assertEqual(text[f.start:f.end], secret)
                cleaned, again = scrub(text)
                self.assertEqual(again, findings)
                self.assertEqual(cleaned, template.format(f'[redacted:{kind}]'))
                self.assertNotIn(secret, cleaned)

    def test_every_private_key_label(self):
        for label in ('PRIVATE KEY', 'RSA PRIVATE KEY', 'EC PRIVATE KEY', 'DSA PRIVATE KEY',
                      'OPENSSH PRIVATE KEY', 'ENCRYPTED PRIVATE KEY', 'PGP PRIVATE KEY BLOCK'):
            with self.subTest(label=label):
                key = pem(label)
                self.assertEqual(scrub('a\n' + key + '\nb')[0], 'a\n[redacted:private_key]\nb')

    def test_a_private_key_inside_json_with_escaped_newlines(self):
        key = pem().replace('\n', '\\n')
        text = '{"type": "service_account", "private_key": "' + key + '\\n", "client_email": "x"}'
        cleaned, findings = scrub(text)
        self.assertEqual([f.kind for f in findings], ['private_key'])
        # The labelled value (key plus its trailing escaped newline) and the PEM block merge.
        self.assertIn('"private_key": "[redacted:private_key]", "client_email": "x"', cleaned)

    def test_a_truncated_private_key_is_still_blanked(self):
        text = pem().rsplit('\n', 1)[0] + '\n\nThe rest of the note.'
        cleaned, findings = scrub(text)
        self.assertEqual([f.kind for f in findings], ['private_key'])
        self.assertEqual(cleaned, '[redacted:private_key]\n\nThe rest of the note.')

    def test_token_variants(self):
        variants = {
            'github_token': [fake('gh', p, '_', A36) for p in 'pousr'] + [fake('github', '_pat_', '11ABCDEFG0', A36, A36[:23])],
            'slack_token': [fake('xo', 'x', p, '-', '1234567890-', A36[:20]) for p in 'abpr'],
            'stripe_key': [fake('sk', '_test_', A36[:24]), fake('rk', '_live_', A36[:24]), fake('wh', 'sec_', A36)],
            'openai_key': [fake('sk', '-', A36, A36[:12]), fake('sk', '-svcacct-', A36, A36)],
            'google_oauth': [fake('ya', '29.', A36, A36)],
            'authorization_header': [],
        }
        for kind, values in variants.items():
            for value in values:
                with self.subTest(kind=kind, value=value[:6]):
                    self.assertEqual(scrub(f'x {value} y')[0], f'x [redacted:{kind}] y')

    def test_authorization_header_forms(self):
        token = fake('dXNlcj', 'pwYXNzd29yZA==')
        for line in (f'Authorization: Basic {token}', f'authorization: bearer {token}',
                     f'"Authorization": "Bearer {token}"', f'Authorization: Token {token}',
                     f'headers = {{"Authorization": "Bearer {token}"}}'):
            with self.subTest(line=line):
                cleaned, findings = scrub(line)
                self.assertEqual([f.kind for f in findings], ['authorization_header'])
                self.assertNotIn(token, cleaned)
                self.assertIn('[redacted:authorization_header]', cleaned)

    def test_labelled_values(self):
        value = fake('Q7', 'x9-', 'Lm2p')
        lines = {
            'password': [f'password={value}', f'PASSWORD: {value}', f'"password": "{value}"', f"passwd = '{value}'",
                         f'pwd: {value}', f'passphrase: "correct horse {value}"', f'db_password={value}',
                         f'Password: letmein'],
            'secret_assignment': [f'api_key = "{value}"', f'API_KEY={value}', f'OPENAI_API_KEY="{value}"',
                                  f'apiKey: "{value}"', f'access_token: {value}', f'auth-token={value}',
                                  f'client_secret: {value}', f'secret_key = "{value}"', f'token: "{value}"',
                                  f'private_key = "{value}"'],
        }
        for kind, items in lines.items():
            for line in items:
                with self.subTest(line=line):
                    findings = find_secrets(line)
                    self.assertEqual([f.kind for f in findings], [kind])
                    secret = 'letmein' if line.endswith('letmein') else (f'correct horse {value}' if 'horse' in line else value)
                    self.assertEqual(line[findings[0].start:findings[0].end], secret)

    def test_url_passwords_in_several_schemes(self):
        secret = fake('p4', 'ss:w', 'ord')
        for url in (f'https://alice:{secret}@example.invalid/x', f'mysql://root:{secret}@localhost',
                    f'redis://:{secret}@cache.invalid:6379', f'amqp+ssl://u:{secret}@mq.invalid'):
            with self.subTest(url=url):
                cleaned, findings = scrub(f'see {url} today')
                self.assertEqual([f.kind for f in findings], ['url_password'])
                self.assertNotIn(secret, cleaned)
                self.assertIn(':[redacted:url_password]@', cleaned)


    def test_offsets_hold_with_non_ascii_text_and_at_the_edges(self):
        token = CASES['github_token'][1]
        for text in (token, f'İstanbul straße {token}', f'{token} ünd İ', f'Ünïcödé\r\n{pem().replace(chr(10), chr(13) + chr(10))}\r\n'):
            with self.subTest(text=text[:12]):
                findings = find_secrets(text)
                self.assertEqual(len(findings), 1)
                f = findings[0]
                self.assertIn(text[f.start:f.end], (token, pem().replace('\n', '\r\n')))
                self.assertNotIn(token, scrub(text)[0])
        upper = 'İ' * 3 + ' PASSWORD: ' + fake('Q7', 'x9-', 'Lm2p')
        f = find_secrets(upper)[0]
        self.assertEqual(upper[f.start:f.end], fake('Q7', 'x9-', 'Lm2p'))

    def test_a_token_inside_a_longer_word_is_not_a_token(self):
        for text in (fake('x', 'gh', 'p_', A36), fake('my', 'AK', 'IA', 'Q3EXAMPLE7KEYID9'), fake('ask', '-', A36),
                     fake('1', 'ey', 'JhbGciOi', '.', 'eyJzdWIiOi', '.', 'abc'), 'x://user:pass@host', '9a://u:p@h'):
            with self.subTest(text=text[:8]):
                self.assertEqual(find_secrets(text), ())


class LookAlikesAreLeftAlone(unittest.TestCase):
    def assertClean(self, text):
        self.assertEqual(find_secrets(text), ())
        self.assertEqual(scrub(text), (text, ()))

    def test_ordinary_prose_and_markdown(self):
        self.assertClean('# Plan\nThe harbour survey is due on Thursday. Ask the accountant about the deposit.\n'
                         'See [the guide](https://example.invalid/guide?page=2#top) and <https://user@example.invalid/x>.\n'
                         'Version 1.4.2 shipped on 2026-10-17 at 09:30; the token budget is 500 per day.\n'
                         'Keep your password in the keychain. The secret: plan ahead. Token: see below.\n')

    def test_hashes_ids_and_uuids(self):
        self.assertClean(' '.join([hashlib.sha256(b'x').hexdigest(), hashlib.sha1(b'x').hexdigest(),
                                   hashlib.md5(b'x').hexdigest(), str(uuid.UUID(int=12345)), uuid.UUID(int=99).hex,
                                   'job-' + 'ab12' * 6, 'mandate-' + 'cd34' * 6, 'chat-' + 'ef56' * 6,
                                   'person-' + '0a1b' * 6, 'export-20261017T093000Z-1a2b3c4d', 'lrn-' + '9f' * 12]))

    def test_code_that_names_secrets_without_holding_one(self):
        self.assertClean('\n'.join([
            "token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)",
            "password = os.environ['ALFRED_PASSWORD']",
            "api_key = get_key(name)",
            "login(password=password, token=token)",
            "{'password': password, 'secret': self.secret}",
            "max_tokens=500",
            "TOKEN_COUNT = 12",
            "password: ${DB_PASSWORD}",
            "api_key: <your key here>",
            "secret: '***'",
            "password = None",
            "token = ''",
            "client_secret: [redacted:secret_assignment]",
        ]))

    def test_public_and_short_lookalikes(self):
        self.assertClean(' '.join([fake('pk', '_live_', A36[:24]), 'sk-learn', 'sk-integration-test-environment-name',
                                   'AKIA', 'ghp_short', 'eyJhbGciOiJIUzI1NiJ9', 'Bearer of bad news',
                                   'Authorization: Bearer', 'https://example.invalid:8080/path', 'http://a:b']))


class FindingsNeverCarryTheSecret(unittest.TestCase):
    def test_repr_str_and_fields_hold_no_secret(self):
        for kind, (template, secret) in CASES.items():
            with self.subTest(kind=kind):
                text = template.format(secret)
                for f in find_secrets(text):
                    self.assertIsInstance(f, Finding)
                    for shown in (repr(f), str(f), f.reason, f.kind):
                        self.assertNotIn(secret, shown)
                        self.assertNotIn(secret[:8], shown)
                    self.assertEqual(set(vars(f)) if hasattr(f, '__dict__') else set(f.__slots__),
                                     {'kind', 'start', 'end', 'reason'})

    def test_findings_are_immutable(self):
        f = find_secrets(CASES['github_token'][1])[0]
        with self.assertRaises(AttributeError):
            f.start = 0


class StableOutput(unittest.TestCase):
    def test_several_secrets_in_one_text_are_found_in_order(self):
        gh, aws, jwt = CASES['github_token'][1], CASES['aws_access_key_id'][1], CASES['jwt'][1]
        text = f'first {gh}, then {aws}; last {jwt}.'
        cleaned, findings = scrub(text)
        self.assertEqual([f.kind for f in findings], ['github_token', 'aws_access_key_id', 'jwt'])
        self.assertEqual(cleaned, 'first [redacted:github_token], then [redacted:aws_access_key_id]; last [redacted:jwt].')
        self.assertEqual([f.start for f in findings], sorted(f.start for f in findings))

    def test_overlapping_matches_merge_into_one_finding(self):
        token = CASES['github_token'][1]
        # The labelled assignment and the GitHub pattern both match; one redaction results.
        for text in (f'api_key = "{token}"', f'Authorization: Bearer {token}', f'password: {token}'):
            with self.subTest(text=text):
                cleaned, findings = scrub(text)
                self.assertEqual(len(findings), 1)
                self.assertEqual(cleaned.count('[redacted:'), 1)
                self.assertNotIn(token, cleaned)
                self.assertEqual(findings[0].kind, 'github_token')  # the specific kind wins

    def test_a_secret_url_inside_a_labelled_value_merges(self):
        url = CASES['slack_webhook'][1]
        cleaned, findings = scrub(f'secret: "{url}"')
        self.assertEqual((cleaned.count('[redacted:'), len(findings)), (1, 1))

    def test_scrubbing_twice_changes_nothing_more(self):
        text = '\n'.join(t.format(s) for t, s in CASES.values())
        once, _ = scrub(text)
        self.assertEqual(scrub(once), (once, ()))
        for _, secret in CASES.values():
            self.assertNotIn(secret, once)

    def test_same_input_same_output(self):
        text = '\n'.join(t.format(s) for t, s in CASES.values())
        self.assertEqual(scrub(text), scrub(text))

    def test_empty_and_wrong_types(self):
        self.assertEqual(scrub(''), ('', ()))
        for value in (None, b'bytes', 12, ['a']):
            with self.subTest(value=value), self.assertRaises(TypeError):
                scrub(value)
            with self.assertRaises(TypeError):
                find_secrets(value)


class BoundedCost(unittest.TestCase):
    """1 MB of hostile input per pattern family must finish within a second each."""

    MB = 1 << 20
    ADVERSARIAL = {
        'pem headers without an end': '-----BEGIN PRIVATE KEY-----\nMIIabc\n',
        'pem ends without a begin': '-----END PRIVATE KEY-----\n',
        'scheme then colons': 'a://' + ':' * 50,
        'user and colon without at': 'https://user:pass',
        'labels without values': 'password=api_key:token=',
        'label then long value': 'password=' + 'x' * 300 + ' ',
        'jwt starts': 'eyJ' + 'a' * 40 + '.',
        'bearer runs': 'Authorization: Bearer Bearer ',
        'prefix floods': 'ghp_sk-ant-xoxb-AKIAAIzaGOCSPX-npm_glpat-sk_live_',
        'base64 run': 'Zm9v' * 64,
        'letters': 'a' * 512,
        'mixed punctuation': '=:"\'@/ ',
    }

    def test_each_hostile_megabyte_finishes_quickly(self):
        for name, unit in self.ADVERSARIAL.items():
            text = (unit * (self.MB // len(unit) + 1))[:self.MB]
            with self.subTest(name=name):
                started = time.perf_counter()
                cleaned, _ = scrub(text)
                elapsed = time.perf_counter() - started
                self.assertLess(elapsed, 1.0, f'{name}: {elapsed:.2f}s')
                self.assertIsInstance(cleaned, str)

    def test_a_megabyte_of_real_secrets_finishes_quickly(self):
        block = '\n'.join(t.format(s) for t, s in CASES.values()) + '\n'
        text = (block * (self.MB // len(block) + 1))[:self.MB]
        started = time.perf_counter()
        cleaned, findings = scrub(text)
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertGreater(len(findings), 1000)
        for kind, (_, secret) in CASES.items():
            self.assertNotIn(secret, cleaned, kind)


if __name__ == '__main__':
    unittest.main()
