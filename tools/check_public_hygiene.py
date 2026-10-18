"""Check that no tracked file holds a credential, a home-directory path or an email address
(coordination/BACKLOG.md item A7; docs/PUBLIC_HYGIENE.md).

This repository is public. The check reads every file Git tracks (``git ls-files``), never
an untracked or ignored one, and skips ``third_party/``, binary files (a NUL byte in the
first 8 KB, or not valid UTF-8) and submodules. A tracked symbolic link is checked by the
text of its target and never followed. It looks for

- every credential kind in ``alfred.scrub`` (its ``find_secrets``, not a copy);
- ``home_path``: ``/home/<name>``, ``/Users/<name>`` and ``C:\\Users\\<name>`` with a real
  looking name. Placeholders such as ``<name>``, ``$USER``, ``~`` and ``$HOME`` never
  match, and neither do the generic names in ``PLACEHOLDER_NAMES``;
- ``email``: an address with a dotted domain.

An address or path inside a credential is reported once, as the credential. Each finding
is printed as file, line, kind and the first 12 characters of the SHA-256 of the matched
text, never the text. Reviewed exceptions live in tools/public_hygiene_allowlist.json; an
exception that no longer matches anything is stale and fails the check.

Exit status: 0 clean, 1 findings or stale exceptions, 2 a usage error, not a Git
repository, or an unreadable or malformed allowlist. Standard library and alfred.scrub
only; reads Git and files, never the network.

    python3 tools/check_public_hygiene.py
    python3 tools/check_public_hygiene.py --suggest    # entries to review, reasons left blank
"""
from __future__ import annotations
import argparse
from bisect import bisect_right
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alfred.scrub import find_secrets, KINDS as SECRET_KINDS  # noqa: E402

KINDS = SECRET_KINDS + ('home_path', 'email')
ALLOWLIST = 'tools/public_hygiene_allowlist.json'
SKIPPED = 'third_party/'
SNIFF = 8192
SHOWN = 12
MIN_REASON = 10
ENTRY_KEYS = ('file', 'kind', 'sha256', 'reason')
PLACEHOLDER_NAMES = frozenset({'user', 'username', 'name', 'yourname', 'your-name', 'your_name', 'you', 'me',
                               'someone', 'example', 'shared', 'public', 'default'})

# A home folder starts a path: not inside a longer word or another path ("/var/home/x",
# "example.invalid/home/x", "api/Users/1"). The name must start with a letter, digit or "_",
# so "<name>", "$USER", "{user}", "*" and "..." never match.
_NAME = r'(?P<name>[A-Za-z0-9_][A-Za-z0-9._-]*)'
_POSIX = re.compile(r'(?<![A-Za-z0-9_~-])/(?:home|Users)/' + _NAME)
_WINDOWS = re.compile(r'(?<![A-Za-z0-9])[A-Za-z]:(?:\\\\|\\|/)(?i:users)(?:\\\\|\\|/)' + _NAME)
_EMAIL = re.compile(r'(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+'
                    r'[A-Za-z]{2,24}(?![A-Za-z0-9-])')
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')


class UsageError(Exception):
    """A value-free reason the check could not run."""


def _homes(text):
    for pattern in (_POSIX, _WINDOWS):
        for m in pattern.finditer(text):
            if m['name'].lower() not in PLACEHOLDER_NAMES:
                yield 'home_path', m.start(), m.end()


def find(text):
    """``(kind, start, end)`` for each finding in ``text``, in order. A home path or address
    that overlaps a credential is dropped: the credential is the finding."""
    secrets = [(f.kind, f.start, f.end) for f in find_secrets(text)]  # sorted, never overlapping
    starts = [s for _, s, _ in secrets]
    kept = []
    for other in [*_homes(text), *(('email', m.start(), m.end()) for m in _EMAIL.finditer(text))]:
        i = bisect_right(starts, other[1]) - 1   # the last credential starting at or before it
        if not ((i >= 0 and secrets[i][2] > other[1]) or (i + 1 < len(secrets) and secrets[i + 1][1] < other[2])):
            kept.append(other)
    return sorted(secrets + kept, key=lambda f: (f[1], f[2]))


def digest(value):
    return hashlib.sha256(value.encode('utf-8', 'surrogateescape')).hexdigest()


def _git(root, *args):
    try:
        return subprocess.run(('git', '-C', str(root)) + args, check=True, capture_output=True).stdout
    except FileNotFoundError:
        raise UsageError('git is not installed') from None
    except subprocess.CalledProcessError:
        raise UsageError('the root is not inside a Git repository') from None


def toplevel(root):
    return Path(_git(root, 'rev-parse', '--show-toplevel').decode('utf-8').strip())


def scan(root):
    """``(findings, counts)`` for the repository at ``root``. Each finding is
    ``(path, line, kind, sha256)``; the matched text itself is never kept."""
    counts = dict(scanned=0, symlinks=0, third_party=0, binary=0, submodules=0, missing=0)
    findings = []
    names = dict.fromkeys(n for n in _git(root, 'ls-files', '-z').decode('utf-8', 'surrogateescape').split('\0') if n)
    for name in names:
        if name.startswith(SKIPPED):
            counts['third_party'] += 1
            continue
        full = root / name
        try:
            info = os.lstat(full)
            if stat.S_ISLNK(info.st_mode):
                text = os.readlink(full)
                counts['symlinks'] += 1
            elif stat.S_ISREG(info.st_mode):
                data = full.read_bytes()
                if b'\0' in data[:SNIFF]:
                    counts['binary'] += 1
                    continue
                text = data.decode('utf-8')
            else:
                counts['submodules'] += 1
                continue
        except FileNotFoundError:
            counts['missing'] += 1
            continue
        except UnicodeDecodeError:
            counts['binary'] += 1
            continue
        counts['scanned'] += 1
        for kind, start, end in find(text):
            findings.append((name, text.count('\n', 0, start) + 1, kind, digest(text[start:end])))
    return sorted(findings), counts


def _no_repeats(pairs):
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        raise UsageError('the allowlist repeats a key inside one object')
    return dict(pairs)


def _relative(value):
    if not isinstance(value, str) or not value or value.startswith('/') or '\\' in value:
        return False
    return all(part not in ('', '.', '..') for part in value.split('/'))


def load_allowlist(path):
    """The reviewed exceptions as ``(file, kind, sha256)`` triples, in order. Every error is
    value-free: it names an entry by its position and a field by its name, never a value."""
    try:
        raw = Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        raise UsageError('cannot read the allowlist') from None
    try:
        doc = json.loads(raw, object_pairs_hook=_no_repeats)
    except json.JSONDecodeError as exc:
        raise UsageError(f'the allowlist is not valid JSON (line {exc.lineno}, column {exc.colno})') from None
    if not isinstance(doc, dict) or not isinstance(doc.get('entries'), list):
        raise UsageError('the allowlist must be a JSON object with an "entries" list')
    if set(doc) - {'about', 'entries'}:
        raise UsageError('the allowlist has an unknown top-level key')
    if not isinstance(doc.get('about', ''), str):
        raise UsageError('the allowlist "about" must be text')
    entries, seen = [], {}
    for n, item in enumerate(doc['entries'], 1):
        where = f'allowlist entry {n}'
        if not isinstance(item, dict):
            raise UsageError(where + ' must be an object')
        if set(item) != set(ENTRY_KEYS):
            raise UsageError(where + ' must have exactly the keys file, kind, sha256 and reason')
        if not _relative(item['file']):
            raise UsageError(where + ': file must be a relative path inside the repository')
        if item['kind'] not in KINDS:
            raise UsageError(where + ': kind is not a known kind')
        if not isinstance(item['sha256'], str) or not _SHA256.match(item['sha256']):
            raise UsageError(where + ': sha256 must be 64 lower-case hexadecimal characters')
        if not isinstance(item['reason'], str) or len(item['reason'].strip()) < MIN_REASON:
            raise UsageError(where + f': reason must be a sentence of at least {MIN_REASON} characters')
        key = (item['file'], item['kind'], item['sha256'])
        if key in seen:
            raise UsageError(f'{where} repeats entry {seen[key]}')
        seen[key] = n
        entries.append(key)
    return entries


def check(root, allowlist=None):
    """``(findings not allowed, how many were allowed, stale entries, counts)``."""
    root = toplevel(root)
    path = Path(allowlist) if allowlist else root / ALLOWLIST
    entries = load_allowlist(path) if allowlist or path.exists() else []
    findings, counts = scan(root)
    allowed = set(entries)
    used = {(p, k, h) for p, _, k, h in findings} & allowed
    open_ = [f for f in findings if (f[0], f[2], f[3]) not in allowed]
    stale = [(n, e) for n, e in enumerate(entries, 1) if e not in used]
    return open_, len(findings) - len(open_), stale, counts


def _summary(open_, allowed, stale, counts):
    c = counts
    return [f"scanned {c['scanned']} tracked files ({c['symlinks']} of them symbolic links); skipped "
            f"{c['third_party']} under {SKIPPED}, {c['binary']} binary, {c['submodules']} submodules, "
            f"{c['missing']} missing from the working tree",
            f'{allowed + len(open_)} findings: {allowed} allowed by reviewed exceptions, {len(open_)} not allowed; '
            f'{len(stale)} stale exceptions',
            'public hygiene: ' + ('failed' if open_ or stale else 'ok')]


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check tracked files for credentials, home paths and email addresses.')
    parser.add_argument('--root', default=str(ROOT), help='a folder inside the repository to check (default: this one)')
    parser.add_argument('--allowlist', help=f'reviewed exceptions (default: {ALLOWLIST} in the repository, if present)')
    parser.add_argument('--suggest', action='store_true',
                        help='print allowlist entries for the findings not yet allowed, with blank reasons to fill in')
    args = parser.parse_args(argv)
    try:
        open_, allowed, stale, counts = check(Path(args.root), args.allowlist)
    except UsageError as exc:
        print(f'check_public_hygiene: {exc}', file=sys.stderr)
        return 2
    lines = _summary(open_, allowed, stale, counts)
    if args.suggest:
        keys = sorted({(p, k, h) for p, _, k, h in open_})
        print(json.dumps({'entries': [dict(file=p, kind=k, sha256=h, reason='') for p, k, h in keys]}, indent=2))
        out = sys.stderr
    else:
        out = sys.stdout
        for path, line, kind, sha in open_:
            print(f'{path}:{line}: {kind} {sha[:SHOWN]}')
    for n, (file, kind, sha) in stale:
        print(f'allowlist entry {n} is stale: {file} {kind} {sha[:SHOWN]} matches nothing', file=out)
    for line in lines:
        print(line, file=out)
    return 1 if open_ or stale else 0


if __name__ == '__main__':
    sys.exit(main())
