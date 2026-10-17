"""Check the work claims that keep Claude and Astra (Codex) out of each other's files.

Claims live in coordination/claims/<id>.md, one file per piece of work, as described in
coordination/README.md. Without --base this validates every claim in the working tree:
format, and no two live claims (active or review) sharing a path. With --base and --branch
it also checks a pull request's changed files:

- a codex/ branch may change only paths in a live Astra claim that already exists at the
  base, never a shared file, and of the claim files only its own existing ones;
- a claude/ branch may not change a path in a live Astra claim at the base or the head;
- any other branch (the owner's own) is not policed.

Standard library only; reads Git and files, never the network.

    python3 tools/check_claims.py
    python3 tools/check_claims.py --base origin/main --branch codex/question-set
"""
from __future__ import annotations
import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = 'coordination/claims/'
AGENTS = {'claude/': 'claude', 'codex/': 'codex'}
STATUSES = ('active', 'review', 'done', 'released')
LIVE = ('active', 'review')
REQUIRED = ('id', 'agent', 'status', 'task', 'claimed')
OPTIONAL = ('brief', 'depends')
# Claude keeps the files every piece of work shares, so Astra never claims or edits them.
SHARED = ('*AGENTS.md', '*CLAUDE.md', 'BUILD_START_HERE.md', 'BUGS_AND_FIXES.md', 'CHANGELOG.md',
          'CONSOLE_HANDOFF.md', 'README.md', 'SESSION_HANDOFF.md', '.github/', 'coordination/', 'plans/',
          'third_party/', 'tools/check_claims.py', 'tools/test_claims.py')


class ClaimError(ValueError):
    pass


def _glob(pattern):
    return any(ch in pattern for ch in '*?[')


def _prefix(pattern):
    return re.split(r'[*?\[]', pattern, maxsplit=1)[0]


def covers(pattern, path):
    """Whether a claim pattern (a file, a folder ending in /, or a glob) includes a file path."""
    if pattern.endswith('/'):
        return path.startswith(pattern)
    if _glob(pattern):
        return fnmatch.fnmatchcase(path, pattern)
    return path == pattern


def overlaps(a, b):
    """Whether two patterns can name the same file. Two globs are compared only by their
    literal text, so claims should prefer files and folders over wide globs."""
    if a == b:
        return True
    for x, y in ((a, b), (b, a)):
        if x.endswith('/') and y.startswith(x):
            return True
        if _glob(x) and not _glob(y) and fnmatch.fnmatchcase(y.rstrip('/'), x):
            return True
        if _glob(x) and y.endswith('/') and _prefix(x).startswith(y):
            return True
    return False


def _path(value):
    p = PurePosixPath(value.rstrip('/') or '/')
    if not value or value.startswith('/') or '\\' in value or any(part in ('', '.', '..') for part in p.parts):
        raise ClaimError('path must be relative inside the repository: ' + repr(value))
    return value


def parse_claim(text, name):
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---' or '---' not in [l.strip() for l in lines[1:]]:
        raise ClaimError(name + ': must start with a front matter block between --- lines')
    end = 1 + [l.strip() for l in lines[1:]].index('---')
    fields, paths, in_paths = {}, None, False
    for line in lines[1:end]:
        if not line.strip():
            continue
        if in_paths and line.startswith('  - '):
            paths.append(_path(line[4:].strip()))
            continue
        in_paths = False
        key, sep, value = line.partition(':')
        key, value = key.strip(), value.strip()
        if not sep or line.startswith(' '):
            raise ClaimError(name + ': unreadable line ' + repr(line))
        if key in fields or (key == 'paths' and paths is not None):
            raise ClaimError(name + ': duplicate key ' + key)
        if key == 'paths':
            if value:
                raise ClaimError(name + ': list paths on their own lines as "  - path"')
            paths, in_paths = [], True
        elif key in REQUIRED + OPTIONAL:
            fields[key] = value
        else:
            raise ClaimError(name + ': unknown key ' + key)
    missing = [k for k in REQUIRED if not fields.get(k)]
    if missing:
        raise ClaimError(name + ': missing ' + ', '.join(missing))
    if fields['agent'] not in AGENTS.values():
        raise ClaimError(name + ': agent must be claude or codex')
    if not fields['id'].startswith(fields['agent'] + '-') or not re.fullmatch(r'[a-z0-9-]+', fields['id']):
        raise ClaimError(name + ': id must be lower case and start with "' + fields['agent'] + '-"')
    if name != fields['id'] + '.md':
        raise ClaimError(name + ': file name must be ' + fields['id'] + '.md')
    if fields['status'] not in STATUSES:
        raise ClaimError(name + ': status must be one of ' + ', '.join(STATUSES))
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', fields['claimed']):
        raise ClaimError(name + ': claimed must be a date like 2026-10-17')
    if not paths:
        raise ClaimError(name + ': list at least one path')
    return dict(fields, paths=paths, notes='\n'.join(lines[end + 1:]).strip())


def validate(claims):
    errors, live = [], [c for c in claims if c['status'] in LIVE]
    for c in live:
        if c['agent'] == 'codex':
            for p in c['paths']:
                for s in SHARED:
                    if overlaps(p, s):
                        errors.append(f"{c['id']}: {p} touches shared file {s}, which Claude keeps")
    for i, a in enumerate(live):
        for b in live[i + 1:]:
            for pa in a['paths']:
                for pb in b['paths']:
                    if overlaps(pa, pb):
                        errors.append(f"{a['id']} and {b['id']} overlap on {pa} and {pb}")
    return errors


def _load(items):
    claims, errors = [], []
    for name, text in items:
        try:
            claims.append(parse_claim(text, name))
        except ClaimError as exc:
            errors.append(str(exc))
    return claims, errors


def claims_in(root):
    folder = Path(root) / CLAIMS
    return _load((p.name, p.read_text(encoding='utf-8')) for p in sorted(folder.glob('*.md'))) if folder.is_dir() else ([], [])


def _git(root, *args):
    return subprocess.run(('git',) + args, cwd=root, check=True, capture_output=True, text=True).stdout


def claims_at(root, rev):
    names = [n for n in _git(root, 'ls-tree', '--name-only', rev, CLAIMS).split() if n.endswith('.md')]
    claims, errors = _load((PurePosixPath(n).name, _git(root, 'show', f'{rev}:{n}')) for n in names)
    if errors:
        raise ClaimError('claims at the base are invalid: ' + '; '.join(errors))
    return claims


def changed_files(root, base):
    return sorted(set(_git(root, 'diff', '--name-only', '--no-renames', f'{base}...HEAD').split()))


def agent_for(branch):
    return next((agent for prefix, agent in AGENTS.items() if branch.startswith(prefix)), None)


def _live(claims, agent):
    return [c for c in claims if c['agent'] == agent and c['status'] in LIVE]


def check_changes(changed, branch, base, head):
    agent, errors = agent_for(branch), []
    astra_base, astra_any = _live(base, 'codex'), _live(base, 'codex') + _live(head, 'codex')
    own_files = {c['id'] + '.md' for c in base if c['agent'] == 'codex'}
    for p in changed:
        if agent == 'codex':
            if p.startswith(CLAIMS):
                if PurePosixPath(p).name not in own_files or PurePosixPath(p).parent.as_posix() + '/' != CLAIMS:
                    errors.append(f'{p}: Astra may only update its own existing claim files')
            elif any(covers(s, p) for s in SHARED):
                errors.append(f'{p}: shared file kept by Claude; describe the change in the PR instead')
            elif not any(covers(pat, p) for c in astra_base for pat in c['paths']):
                errors.append(f'{p}: not in any live Astra claim on the base branch')
        elif agent == 'claude' and not p.startswith(CLAIMS):
            owner = next((c['id'] for c in astra_any for pat in c['paths'] if covers(pat, p)), None)
            if owner:
                errors.append(f'{p}: claimed by Astra in {owner}')
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--root', default=str(ROOT))
    parser.add_argument('--base', help='base revision of a pull request')
    parser.add_argument('--branch', default='', help='head branch name of the pull request')
    args = parser.parse_args(argv)
    head, errors = claims_in(args.root)
    errors += validate(head)
    if args.base:
        try:
            base = claims_at(args.root, args.base)
        except ClaimError as exc:
            base, errors = [], errors + [str(exc)]
        changed = changed_files(args.root, args.base)
        errors += check_changes(changed, args.branch, base, head)
        who = agent_for(args.branch) or 'not an agent branch, so not policed'
        print(f'{len(changed)} changed files on {args.branch or "this branch"} ({who})')
    for c in head:
        if c['status'] in LIVE:
            print(f"{c['status']:>7}  {c['agent']:<6} {c['id']}: {c['task']}")
    for e in errors:
        print('error: ' + e, file=sys.stderr)
    print('claims ok' if not errors else f'{len(errors)} claim errors')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
