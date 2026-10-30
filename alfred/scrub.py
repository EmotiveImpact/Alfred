"""Find and blank credentials in text before ALFRED saves or sends it (integration plan
phase 5; coordination/BACKLOG.md item A2).

``find_secrets(text)`` returns findings, each a kind, a start and end offset into ``text``
and a fixed reason. A finding never holds the secret: its fields, ``repr`` and ``str`` show
only where it was and what kind it was. ``scrub(text)`` returns the text with each finding
replaced by ``[redacted:<kind>]``, and the findings, so a caller can record that something
was blanked without keeping what it was.

What it catches, one kind per pattern (docs/SECRET_SCRUBBING.md has the detail)
    private_key             PEM private key blocks, including ones inside JSON with
                            escaped newlines and ones cut off before their END line
    aws_access_key_id       AWS access key ids by their published prefixes
    aws_secret_access_key   a 40 character AWS secret key, only where it is labelled as one
    azure_storage_key       an Azure storage ``AccountKey=`` value
    github_token            GitHub personal, OAuth, app and fine-grained tokens
    gitlab_token            GitLab personal, deploy and runner tokens
    slack_token             Slack bot, user, app and refresh tokens
    slack_webhook           Slack incoming webhook addresses (the address is the secret)
    stripe_key              Stripe secret and restricted keys and webhook signing secrets
    google_api_key          Google API keys
    google_oauth            Google OAuth client secrets and access tokens
    openai_key              OpenAI API keys
    anthropic_key           Anthropic API keys
    npm_token               npm access tokens
    jwt                     JSON web tokens
    authorization_header    the credential in an ``Authorization`` header, or after
                            ``Bearer``
    url_password            the password in a URL's ``user:password@`` part
    password                a value labelled password, passwd, pwd or passphrase
    secret_assignment       a value labelled as a secret, key or token

Where findings overlap they become one, spanning them all, whose kind is the earliest of
theirs in the list above (the most specific): a GitHub token written as ``api_key = "..."``
is reported as ``github_token``, and a key file pasted as a JSON ``private_key`` value as
``private_key``.

What it leaves alone: prose, Markdown links, commit hashes, SHA-256 and other hex digests,
UUIDs, ALFRED's own ids, versions and dates, Stripe publishable keys, and code that names a
secret without holding one (``password = os.environ[...]``, ``login(token=token)``,
``api_key: ${API_KEY}``). Scrubbing is idempotent: a ``[redacted:...]`` marker is never a
finding.

Cost is linear in the input: every pattern is anchored on a literal or a bounded run of one
character class, and PEM blocks are matched by searching for their END line once rather
than with a lazy match that rescans. Standard library only; no model, no network.

This module is pure. Brain packets (alfred/brain.py) and harvested worker text
(alfred/learning.py) are scrubbed with it; the other call sites are listed in
docs/SECRET_SCRUBBING.md, "Where it will be called".
"""
from __future__ import annotations
from bisect import bisect_left
from dataclasses import dataclass
import re

KINDS = ('private_key', 'anthropic_key', 'openai_key', 'github_token', 'gitlab_token', 'slack_webhook',
         'slack_token', 'stripe_key', 'google_api_key', 'google_oauth', 'npm_token', 'aws_access_key_id',
         'aws_secret_access_key', 'azure_storage_key', 'jwt', 'url_password', 'authorization_header',
         'password', 'secret_assignment')
PRIORITY = {kind: rank for rank, kind in enumerate(KINDS)}
MARKER = '[redacted:'

REASONS = {
    'private_key': 'PEM private key block',
    'anthropic_key': 'Anthropic API key',
    'openai_key': 'OpenAI API key',
    'github_token': 'GitHub token',
    'gitlab_token': 'GitLab token',
    'slack_webhook': 'Slack webhook address',
    'slack_token': 'Slack token',
    'stripe_key': 'Stripe secret key',
    'google_api_key': 'Google API key',
    'google_oauth': 'Google OAuth secret or token',
    'npm_token': 'npm token',
    'aws_access_key_id': 'AWS access key id',
    'aws_secret_access_key': 'labelled AWS secret access key',
    'azure_storage_key': 'Azure storage account key',
    'jwt': 'JSON web token',
    'url_password': 'password in a URL',
    'authorization_header': 'authorisation header credential',
    'password': 'labelled password',
    'secret_assignment': 'labelled secret value',
}


@dataclass(frozen=True, slots=True)
class Finding:
    """Where a secret was and what kind it was. Never the secret itself."""
    kind: str
    start: int
    end: int
    reason: str


# Characters that may not sit directly before a match, so a token is not found inside a
# longer word. Checked in Python rather than with a look-behind, so that every pattern
# starts with a literal and the regular expression engine can skip ahead to it.
_WORD = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789')
_TOKEN = _WORD | {'_', '-'}
_E = r'(?![A-Za-z0-9_-])'

# (kind, pattern, characters that may not precede it, needs_random). The secret is group
# "v" when the pattern has one, else the whole match. needs_random drops a match with no
# digit or no letter (prose look-alikes such as a long hyphenated name after "sk-").
# Patterns in _CASED run on the text as written; those in _UNCASED on an ASCII-lowered
# copy of the same length, so their offsets are the same.
_CASED = (
    ('anthropic_key', r'sk-ant-[A-Za-z0-9_-]{20,}', _TOKEN, True),
    ('openai_key', r'sk-(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}', _TOKEN, True),
    ('github_token', r'gh[pousr]_[A-Za-z0-9]{36,}', _WORD, False),
    ('github_token', r'github_pat_[A-Za-z0-9_]{22,}', _WORD, False),
    ('gitlab_token', r'gl(?:pat|dt|rt|ptt|cbt)-[A-Za-z0-9_-]{20,}', _TOKEN, True),
    ('slack_webhook', r'https://hooks\.slack\.com/(?:services|workflows|triggers)/[A-Za-z0-9_/-]{20,}', frozenset(), False),
    ('slack_token', r'xox[abposre]-[A-Za-z0-9-]{10,}', _TOKEN, True),
    ('slack_token', r'xapp-\d-[A-Za-z0-9-]{10,}', _TOKEN, True),
    ('stripe_key', r'[sr]k_(?:live|test)_[A-Za-z0-9]{16,}', _WORD, False),
    ('stripe_key', r'whsec_[A-Za-z0-9]{24,}', _WORD, False),
    ('google_api_key', r'AIza[0-9A-Za-z_-]{35}' + _E, _TOKEN, False),
    ('google_oauth', r'GOCSPX-[A-Za-z0-9_-]{28,}', _TOKEN, False),
    ('google_oauth', r'ya29\.[0-9A-Za-z_-]{20,}', _TOKEN, False),
    ('npm_token', r'npm_[A-Za-z0-9]{36,}', _WORD, False),
    ('aws_access_key_id', r'A(?:KIA|SIA|BIA|CCA|GPA|IDA|IPA|NPA|NVA|ROA|PKA|SCA)[A-Z0-9]{16}(?![A-Za-z0-9])', _WORD, False),
    ('jwt', r'eyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*', _TOKEN, False),
    ('url_password', r'://[^\s/:@]{0,256}:(?P<v>[^\s/@]{1,256})@', frozenset(), False),
)
_UNCASED = (
    ('aws_secret_access_key', r'aws[_. -]?(?:secret[_. -]?(?:access[_. -]?)?key|sk)["\']?[ \t]{0,8}[:=][ \t]{0,8}["\']?'
                              r'(?P<v>[a-z0-9/+]{40})(?![a-z0-9/+=])', _WORD, False),
    ('azure_storage_key', r'accountkey[ \t]{0,4}=[ \t]{0,4}(?P<v>[a-z0-9+/]{80,}={0,2})', _WORD, False),
    ('authorization_header', r'authorization["\']?[ \t]{0,8}[:=][ \t]{0,8}["\']?(?:bearer|basic|token|digest|bot)[ \t]+'
                             r'(?P<v>[a-z0-9._~+/=-]{8,})', _WORD, False),
    ('authorization_header', r'bearer[ \t]+(?P<v>[a-z0-9._~+/-]{20,}=*)', _WORD, True),
)
_COMPILED = tuple((kind, re.compile(pattern), before, needs_random, cased)
                  for cased, table in ((True, _CASED), (False, _UNCASED))
                  for kind, pattern, before, needs_random in table)
_LOWER = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')
_SCHEME = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+.-')

_PEM_BEGIN = re.compile(r'-----BEGIN (?:[A-Z0-9]+ ){0,4}PRIVATE KEY(?: BLOCK)?-----')
_PEM_END = re.compile(r'-----END (?:[A-Z0-9]+ ){0,4}PRIVATE KEY(?: BLOCK)?-----')
# A cut-off block: the base64 lines (and RFC 1421 header lines) that follow the BEGIN line,
# separated by real or JSON-escaped newlines.
_PEM_BODY = re.compile(r'(?:(?:\r?\n|\\r?\\n)(?:[A-Za-z0-9+/=]+|[A-Za-z-]+: [^\r\n\\]*)(?=\r?\n|\\r?\\n|["\']|$))*')

_PASSWORD_LABELS = r'pass(?:word|wd|phrase)|pwd'
_LABEL = re.compile(
    r'(?P<label>' + _PASSWORD_LABELS + r'|client[_-]?secret|secret[_-]?key|private[_-]?key'
    r'|api[_-]?key|access[_-]?token|auth[_-]?token|secret|token)(?![A-Za-z0-9])(?P<lq>["\']?)'
    r'[ \t]{0,8}(?P<sep>[:=])[ \t]{0,8}'
    r'(?:"(?P<dq>[^"\r\n]{1,512})"|\'(?P<sq>[^\'\r\n]{1,512})\'|(?P<bare>[^\s"\'`,;()\[\]{}<>]+))')
_IS_PASSWORD = re.compile(r'(?:' + _PASSWORD_LABELS + r')\Z')
_PLACEHOLDER_WORDS = frozenset({'none', 'null', 'nil', 'true', 'false', 'undefined', 'empty', 'unset', 'hidden',
                                'redacted', 'required', 'optional', 'secret', 'password', 'token', 'example'})
_PLACEHOLDER = re.compile(r'(?:\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|%\(?[A-Za-z_]*\)?s|\{\{.*\}\}|<.*>|([*xX.#_-])\1*)\Z')
_IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
_DOTTED = re.compile(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\Z')
_DIGIT = re.compile(r'[0-9]')
_LETTER = re.compile(r'[A-Za-z]')


def _random_looking(value):
    return bool(_DIGIT.search(value) and _LETTER.search(value))


def _private_keys(text):
    found = [m.span() for m in _PEM_END.finditer(text)]
    ends = [start for start, _ in found]
    covered = 0
    for begin in _PEM_BEGIN.finditer(text):
        if begin.start() < covered:
            continue
        i = bisect_left(ends, begin.end())
        stop = found[i][1] if i < len(found) else _PEM_BODY.match(text, begin.end()).end()
        covered = stop
        yield 'private_key', begin.start(), stop


def _url_has_scheme(text, at):
    """Whether ``://`` at ``at`` follows a URL scheme: a letter, then 1 to 20 scheme characters,
    not itself preceded by one."""
    start = at
    while start > 0 and at - start <= 21 and text[start - 1] in _SCHEME:
        start -= 1
    return 2 <= at - start <= 21 and text[start].isascii() and text[start].isalpha() \
        and (start == 0 or text[start - 1] not in _SCHEME)


def _tokens(text, lowered):
    for kind, pattern, before, needs_random, cased in _COMPILED:
        for m in pattern.finditer(text if cased else lowered):
            if m.start() and text[m.start() - 1] in before:
                continue
            if kind == 'url_password' and not _url_has_scheme(text, m.start()):
                continue
            start, end = m.span('v' if 'v' in pattern.groupindex else 0)
            value = text[start:end]
            if value.startswith(MARKER) or (needs_random and not _random_looking(value)):
                continue
            yield kind, start, end


def _labelled(text, lowered):
    for m in _LABEL.finditer(lowered):
        if m.start() and text[m.start() - 1] in _WORD:
            continue
        label, group = m['label'], next(g for g in ('dq', 'sq', 'bare') if m[g] is not None)
        start, end = m.span(group)
        if _keep_value(text, label, m['lq'], m['sep'], text[start:end], group == 'bare', end):
            yield ('password' if _IS_PASSWORD.match(label) else 'secret_assignment'), start, end


def _keep_value(text, label, label_quoted, sep, value, bare, end):
    """Whether a labelled value is a secret rather than a placeholder or a piece of code."""
    lowered = value.strip().lower()
    if len(value.strip()) < 4 or value.startswith(MARKER) or lowered == label.lower():
        return False
    if lowered in _PLACEHOLDER_WORDS or _PLACEHOLDER.match(value.strip()):
        return False
    if not bare:
        return True
    following = text[end:end + 1]
    if following in ('(', '[') or _DOTTED.match(value):
        return False                       # a call, a subscript or an attribute: code
    if label_quoted:
        return _random_looking(value)       # {'password': password} names a variable
    if sep == '=' and _IDENTIFIER.match(value) and not _DIGIT.search(value):
        return False                       # password=password, token=new_token
    if _IS_PASSWORD.match(label):
        return True
    return _random_looking(value)           # "Token: see below" is prose


def _merge(raw):
    merged = []
    for kind, start, end in sorted(raw, key=lambda f: (f[1], -f[2], PRIORITY[f[0]])):
        if merged and start < merged[-1][2]:
            first = merged[-1]
            specific = min(first[0], kind, key=PRIORITY.__getitem__)
            merged[-1] = (specific, first[1], max(first[2], end))
        else:
            merged.append((kind, start, end))
    return tuple(Finding(kind, start, end, REASONS[kind]) for kind, start, end in merged)


def find_secrets(text):
    """The secrets in ``text``, in order, overlapping ones merged. Never holds a secret."""
    if not isinstance(text, str):
        raise TypeError('find_secrets needs str, not ' + type(text).__name__)
    if not text:
        return ()
    lowered = text.translate(_LOWER)  # ASCII only, so every offset is unchanged
    return _merge([*_private_keys(text), *_tokens(text, lowered), *_labelled(text, lowered)])


def scrub(text):
    """``(cleaned, findings)``: ``text`` with each secret replaced by ``[redacted:<kind>]``."""
    findings = find_secrets(text)
    parts, cursor = [], 0
    for f in findings:
        parts += [text[cursor:f.start], f'{MARKER}{f.kind}]']
        cursor = f.end
    parts.append(text[cursor:])
    return ''.join(parts), findings
