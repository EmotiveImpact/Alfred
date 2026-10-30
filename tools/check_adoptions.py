"""Check that code adapted from the research shelf or source library carries a true credit.

ALFRED may adapt code from the pinned snapshots in third_party/research-shelf/ and
third_party/library/ only with credit, as research/INTEGRATION_PLAN_2026-10-17.md sets out
under "How borrowing code works". This scans ALFRED's own source (alfred/, tools/, web/ and
console/src/, never third_party/ or tests/) for credit blocks: a comment or docstring line that
opens with the words "Adapted from:" and the owner/name of the upstream project, followed by
Path, Commit and Licence lines and the notice lines that licence needs. docs/ADOPTION_CHECK.md
shows the format. For every credit it checks, against the catalogues and per-repository
manifests read as JSON data:

- each required field is present and well formed (a full 40-character commit, a relative path);
- the project is in a catalogue, pinned at exactly that commit, and was copied, not only
  recorded as a reference;
- the catalogue records a licence that grants a right to copy (UNLICENSED, NOASSERTION and
  "not established" do not; UNLICENSED is not the Unlicense);
- the path is a file the manifest lists for that snapshot;
- the Licence line matches the catalogue, and the licence has a notice rule here: MIT needs a
  Copyright line, Apache-2.0 needs a Notice line and a Changes line;
- any Copyright or Notice text quotes whole lines of the upstream licence, NOTICE or adapted file.

A loose comment line that starts with those words but is not a complete credit fails, and so
does a file of at least MIN_COPY_BYTES bytes that is byte-identical to a snapshot file but has
no credit at all.

What a pass does not prove: a matching credit is not licence clearance, a compatibility review
or the owner's approval. It does not show that the full licence text ships with ALFRED, that
the code was rewritten to ALFRED's conventions, or that its network and storage behaviour was
reviewed. Rewritten code with no credit cannot be detected. The snapshot files themselves are
verified by tools/build_research_shelf.py --verify and tools/build_source_library.py --verify,
not here.

Standard library only. Reads files, never the network, and never imports or runs anything
under third_party/.

    python3 tools/check_adoptions.py
    python3 tools/check_adoptions.py --root path/to/checkout
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('alfred', 'tools', 'web', 'console/src')
COLLECTIONS = (('research shelf', 'third_party/research-shelf'), ('source library', 'third_party/library'))
SKIP_DIRS = frozenset({'.git', '__pycache__', 'node_modules', 'third_party'})
# Smaller files (empty modules, one-line stubs) match upstream by accident too often to mean a copy.
MIN_COPY_BYTES = 256

OPENING = 'Adapted from:'
REQUIRED = ('Path', 'Commit', 'Licence')
FIELDS = REQUIRED + ('Copyright', 'Notice', 'Changes')
QUOTED = ('Copyright', 'Notice')
NOTICE_RULES = {
    'MIT': (('Copyright', 'a Copyright line carrying the upstream copyright notice'),),
    'Apache-2.0': (('Notice', 'a Notice line carrying the upstream notice'),
                   ('Changes', 'a Changes line stating what was changed')),
}
NOT_CLEARED = ('NOASSERTION', 'NONE', 'not established')
NOTICE_FILES = ('NOTICE', 'NOTICE.md', 'NOTICE.txt')

HASH = re.compile(r'[0-9a-f]{40}')
PROJECT = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+')
MARKER = re.compile(r'adapted\s+from\b', re.IGNORECASE)
FIELD_LINE = re.compile(r'(' + '|'.join(FIELDS) + r'):(.*)')
KEY_LIKE = re.compile(r'([A-Z][A-Za-z]*(?: [A-Za-z]+){0,2}):(?:\s|$)')
OPENERS = ('<!--', '"""', "'''", '/*', '//', '#', '*')
CLOSERS = ('-->', '"""', "'''", '*/')


class Finding(NamedTuple):
    path: str
    line: int
    message: str

    def __str__(self):
        return f'{self.path}:{self.line}: {self.message}'


class Credited(NamedTuple):
    path: str
    line: int
    project: str
    upstream_path: str
    commit: str
    licence: str
    collection: str

    def __str__(self):
        return (f'{self.path}:{self.line}  {self.project} {self.upstream_path} at {self.commit[:12]} '
                f'({self.licence}, {self.collection})')


@dataclass(frozen=True)
class Snapshot:
    collection: str
    folder: Path
    repository: str
    commit: str
    licence: str
    licence_path: str | None
    copied: bool
    files: dict
    excluded: dict


@dataclass
class Credit:
    line: int
    project: str = ''
    fields: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)
    readable: bool = True


@dataclass
class Result:
    findings: list = field(default_factory=list)
    credits: list = field(default_factory=list)
    manifest_errors: list = field(default_factory=list)
    snapshots: list = field(default_factory=list)
    scanned: int = 0
    present: list = field(default_factory=list)
    missing: list = field(default_factory=list)


def safe_path(value):
    """Whether a manifest or credit path is relative and stays inside its snapshot."""
    return (isinstance(value, str) and bool(value) and not value.startswith('/') and '\\' not in value
            and '\0' not in value and all(part not in ('', '.', '..') for part in value.split('/')))


def blob_sha(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


# Reading the pinned catalogues and manifests (data only).

def _read_json(path, rel, missing):
    try:
        text = path.read_text(encoding='utf-8')
    except FileNotFoundError:
        return None, f'{rel}: {missing}'
    except (OSError, UnicodeDecodeError) as exc:
        return None, f'{rel}: unreadable ({exc.__class__.__name__})'
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f'{rel}: not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg})'


def _entry_problems(entry):
    problems = []
    if not isinstance(entry.get('repository'), str) or not PROJECT.fullmatch(entry['repository']):
        problems.append('repository must be owner/name')
    if not isinstance(entry.get('commit'), str) or not HASH.fullmatch(entry['commit']):
        problems.append('commit must be a 40-character lower-case hash')
    for key in ('status', 'licence'):
        if not isinstance(entry.get(key), str) or not entry[key].strip():
            problems.append(key + ' must be a non-empty string')
    if not isinstance(entry.get('source_copied'), bool):
        problems.append('source_copied must be true or false')
    if entry.get('licence_path') is not None and not safe_path(entry['licence_path']):
        problems.append('licence_path must be a relative path inside the snapshot')
    return problems


def _manifest(data, rel):
    if not isinstance(data, dict) or not isinstance(data.get('files'), list):
        return {}, {}, [f'{rel}: files must be a list']
    files, excluded, errors = {}, {}, []
    for i, item in enumerate(data['files']):
        if not isinstance(item, dict):
            errors.append(f'{rel}: files[{i}] must be an object')
            continue
        if not safe_path(item.get('path')):
            errors.append(f'{rel}: files[{i}].path must be a relative path inside the snapshot')
        elif not isinstance(item.get('git_blob_sha1'), str) or not HASH.fullmatch(item['git_blob_sha1']):
            errors.append(f'{rel}: files[{i}].git_blob_sha1 must be a 40-character lower-case hash')
        else:
            files[item['path']] = item['git_blob_sha1']
    left_out = data.get('excluded', [])
    if not isinstance(left_out, list):
        errors.append(f'{rel}: excluded must be a list')
    else:
        for i, item in enumerate(left_out):
            if not isinstance(item, dict) or not isinstance(item.get('path'), str) \
                    or not isinstance(item.get('reason'), str):
                errors.append(f'{rel}: excluded[{i}] must have a path and a reason')
            else:
                excluded[item['path']] = item['reason']
    return files, excluded, errors


def load_collection(root, label, rel):
    """Read one catalogue and the manifest of every copied snapshot in it."""
    catalogue = rel + '/CATALOGUE.json'
    data, error = _read_json(Path(root) / catalogue, catalogue, 'missing')
    if error:
        return [], [error]
    if not isinstance(data, dict) or not isinstance(data.get('repositories'), list):
        return [], [catalogue + ': repositories must be a list']
    snapshots, errors, seen = [], [], set()
    for i, entry in enumerate(data['repositories']):
        where = f'{catalogue}: repositories[{i}]'
        if not isinstance(entry, dict):
            errors.append(where + ' must be an object')
            continue
        problems = _entry_problems(entry)
        if problems:
            errors.extend(f'{where}.{p}' for p in problems)
            continue
        repo = entry['repository']
        if repo in seen:
            errors.append(f'{where} lists {repo} a second time')
            continue
        seen.add(repo)
        name = repo.replace('/', '__')
        copied = entry['status'] == 'copied' and entry['source_copied']
        files, excluded = {}, {}
        if copied:
            manifest = f'{rel}/manifests/{name}.json'
            data, error = _read_json(Path(root) / manifest, manifest,
                                     f'missing, but the catalogue lists {repo} as copied')
            if error:
                errors.append(error)
                continue
            files, excluded, problems = _manifest(data, manifest)
            if problems:
                errors.extend(problems)
                continue
        snapshots.append(Snapshot(label, Path(root) / rel / 'snapshots' / name, repo, entry['commit'],
                                  entry['licence'], entry.get('licence_path'), copied, files, excluded))
    return snapshots, errors


# Reading credit blocks from ALFRED's own files.

def _comment_text(line):
    """A line's indentation and its text without comment markers, as (indent, text)."""
    rest = line.rstrip()
    indent = len(rest) - len(rest.lstrip())
    rest = rest.lstrip()
    while True:
        opener = next((o for o in OPENERS if rest.startswith(o)), None)
        if opener is None:
            break
        rest = rest[len(opener):]
    indent += len(rest) - len(rest.lstrip())
    text = rest.strip()
    closer = next((c for c in CLOSERS if text.endswith(c)), None)
    if closer:
        text = text[:-len(closer)].rstrip()
    return indent, text


def read_credits(text):
    """Every credit block in a file. A block runs from its opening line to the first blank line
    or line that is neither a field, a deeper-indented continuation, nor field-shaped."""
    lines, credits, i = text.splitlines(), [], 0
    while i < len(lines):
        _, opening = _comment_text(lines[i])
        i += 1
        if not MARKER.match(opening):
            continue
        credit = Credit(line=i)
        credits.append(credit)
        if not opening.startswith(OPENING):
            credit.readable = False
            credit.problems.append((i, f'credit line must read "{OPENING} owner/name"; '
                                          'describe the source of an idea in other words'))
            continue
        credit.project = opening[len(OPENING):].strip()
        last = None
        while i < len(lines):
            indent, body = _comment_text(lines[i])
            if not body or MARKER.match(body):
                break
            match, key = FIELD_LINE.match(body), KEY_LIKE.match(body)
            if match:
                name, value = match.group(1), match.group(2).strip()
                if name in credit.fields:
                    credit.problems.append((i + 1, f'{name} appears twice in this credit'))
                    last = None
                else:
                    credit.fields[name] = [value, i + 1]
                    last = (name, indent)
            elif last and indent > last[1]:
                held = credit.fields[last[0]]
                held[0] = (held[0] + ' ' + body).strip()
            elif key:
                hint = ('ALFRED spells it Licence' if key.group(1) == 'License'
                        else 'end the credit with a blank line if this line is not part of it')
                credit.problems.append((i + 1, f'unknown credit field "{key.group(1)}"; {hint}'))
                last = None
            else:
                break
            i += 1
    return credits


# Checking one credit against the pinned snapshots.

def _normal(text):
    return ' '.join(text.split())


def _quotes_whole_lines(wanted, text):
    """Whether wanted equals one or more consecutive whole lines of text, ignoring comment
    markers and spacing, so a fragment such as a bare name or year is not a quote."""
    lines = [t for t in (_normal(_comment_text(line)[1]) for line in text.splitlines()) if t]
    for start in range(len(lines)):
        joined = ''
        for line in lines[start:]:
            joined = (joined + ' ' + line).strip()
            if joined == wanted:
                return True
            if len(joined) >= len(wanted):
                break
    return False


def _found_upstream(value, snap, path):
    """Whether quoted notice text is whole lines of the upstream adapted file, NOTICE file or licence."""
    names = [path] + list(NOTICE_FILES) + ([snap.licence_path] if snap.licence_path else [])
    base = snap.folder.resolve()
    wanted = _normal(value)
    for name in dict.fromkeys(names):
        if name not in snap.files:
            continue
        target = (snap.folder / name).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            continue
        if _quotes_whole_lines(wanted, target.read_bytes().decode('utf-8', errors='replace')):
            return True
    return False


def _grant_problem(licence):
    if licence.startswith('UNLICENSED'):
        return 'which grants no right to copy it (UNLICENSED is not the Unlicense)'
    if licence.strip() in NOT_CLEARED:
        return 'which is not cleared for adoption'
    return None


def check_credit(credit, index):
    """Problems with one credit as (line, message) pairs, and the matched snapshot if none."""
    problems = list(credit.problems)
    if not credit.readable:
        return problems, None
    value = {name: v for name, (v, _) in credit.fields.items()}
    line = {name: n for name, (_, n) in credit.fields.items()}
    if not credit.project:
        problems.append((credit.line, f'credit is missing the upstream project after "{OPENING}"'))
    elif not PROJECT.fullmatch(credit.project):
        problems.append((credit.line, f'"{credit.project}" is not an upstream project name; '
                                      'write owner/name as the catalogue does'))
    for name in REQUIRED:
        if not value.get(name):
            problems.append((credit.line, 'credit is missing ' + name))
    if value.get('Commit') and not HASH.fullmatch(value['Commit']):
        problems.append((line['Commit'], 'Commit must be the full 40-character lower-case hash, '
                                         f'not "{value["Commit"]}"'))
    if value.get('Path') and not safe_path(value['Path']):
        problems.append((line['Path'], 'Path must be a relative path inside the upstream project, '
                                       f'not "{value["Path"]}"'))
    if problems:
        return problems, None

    project, commit, path, licence = credit.project, value['Commit'], value['Path'], value['Licence']
    pinned = index.get(project)
    if not pinned:
        message = f'{project} is not pinned in the research shelf or the source library'
        spelt = sorted({s.repository for snaps in index.values() for s in snaps
                        if s.repository.lower() == project.lower()})
        if spelt:
            message += '; the catalogue spells it ' + spelt[0]
        return [(credit.line, message)], None
    snap = next((s for s in pinned if s.commit == commit), None)
    if snap is None:
        pins = '; '.join(f'the {s.collection} pins {s.commit}' for s in pinned)
        return [(line['Commit'], f'commit {commit} is not the pinned commit of {project} ({pins})')], None
    grant = _grant_problem(snap.licence)
    if grant:
        return [(line['Licence'], f'the {snap.collection} records the licence of {project} as '
                                  f'"{snap.licence}", {grant}')], None
    if not snap.copied:
        return [(credit.line, f'{project} is reference only in the {snap.collection}: no source was copied, '
                              'so there is nothing pinned to adapt from')], None

    if path in snap.excluded:
        problems.append((line['Path'], f'{path} was left out of the {snap.collection} snapshot of {project} '
                                       f'({snap.excluded[path]})'))
    elif path not in snap.files:
        problems.append((line['Path'], f'{path} is not in the {snap.collection} snapshot of {project}'))
    if licence != snap.licence:
        problems.append((line['Licence'], f'Licence "{licence}" does not match "{snap.licence}", which the '
                                          f'{snap.collection} records for {project}'))
        return problems, None
    rule = NOTICE_RULES.get(licence)
    if rule is None:
        problems.append((line['Licence'], f'this check has no notice rule for {licence} yet; the owner must '
                                          'agree one before code under it is adopted'))
        return problems, None
    for name, needed in rule:
        if not value.get(name):
            problems.append((credit.line, f'{licence} requires {needed}'))
    for name in QUOTED:
        if value.get(name) and not _found_upstream(value[name], snap, path):
            problems.append((line[name], f'{name} "{value[name]}" is not in the upstream licence, notice or '
                                         'adapted file at the pinned commit'))
    return problems, (None if problems else snap)


# Scanning ALFRED's source.

def _source_files(root, folder):
    for dirpath, dirnames, filenames in os.walk(Path(root) / folder):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if not path.is_symlink() and path.is_file():
                yield path.relative_to(root).as_posix(), path


def scan(root=ROOT, sources=SOURCES, collections=COLLECTIONS):
    root, result = Path(root), Result()
    for label, rel in collections:
        snapshots, errors = load_collection(root, label, rel)
        result.snapshots += snapshots
        result.manifest_errors += errors
    if result.manifest_errors:
        return result
    index, copies = {}, {}
    for snap in result.snapshots:
        index.setdefault(snap.repository, []).append(snap)
        for path, blob in sorted(snap.files.items()):
            copies.setdefault(blob, (snap, path))
    for folder in sources:
        (result.present if (root / folder).is_dir() else result.missing).append(folder)
    for folder in result.present:
        for rel, path in _source_files(root, folder):
            data = path.read_bytes()
            try:
                text = data.decode('utf-8')
            except UnicodeDecodeError:
                continue
            if '\0' in text:
                continue
            result.scanned += 1
            credits = read_credits(text)
            for credit in credits:
                problems, snap = check_credit(credit, index)
                result.findings += [Finding(rel, n, message) for n, message in problems]
                if snap:
                    result.credits.append(Credited(rel, credit.line, credit.project, credit.fields['Path'][0],
                                                   snap.commit, snap.licence, snap.collection))
            if not credits and len(data) >= MIN_COPY_BYTES and blob_sha(data) in copies:
                snap, upstream = copies[blob_sha(data)]
                result.findings.append(Finding(rel, 1, f'identical to {upstream} in the {snap.collection} snapshot '
                                                       f'of {snap.repository} but has no "Adapted from" credit'))
    result.findings.sort()
    result.credits.sort()
    return result


def _count(n, one, many):
    return f'{n} {one if n == 1 else many}'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--root', default=str(ROOT), help='repository checkout to check')
    args = parser.parse_args(argv)
    result = scan(args.root)
    if result.manifest_errors:
        for error in result.manifest_errors:
            print('error: ' + error, file=sys.stderr)
        print('adoption check could not run: ' + _count(len(result.manifest_errors), 'manifest error', 'manifest errors'))
        return 2
    if not result.present:
        print('error: none of ' + ', '.join(f + '/' for f in SOURCES) + ' exists under the root', file=sys.stderr)
        print('adoption check could not run')
        return 2
    copied = [s for s in result.snapshots if s.copied]
    per = ', '.join(f'{label} {sum(s.collection == label for s in copied)}' for label, _ in COLLECTIONS)
    reference = len(result.snapshots) - len(copied)
    print(f'Scanned {_count(result.scanned, "file", "files")} in ' + ', '.join(f + '/' for f in result.present)
          + f' against {_count(len(copied), "copied snapshot", "copied snapshots")} ({per}); '
          + _count(reference, 'reference-only entry cannot', 'reference-only entries cannot') + ' be adapted from.')
    for folder in result.missing:
        print(f'note: {folder}/ is not present, so it was not scanned')
    for credit in result.credits:
        print('ok  ' + str(credit))
    if result.findings:
        for finding in result.findings:
            print('error: ' + str(finding), file=sys.stderr)
        print(_count(len(result.findings), 'adoption error', 'adoption errors'))
        return 1
    if result.credits:
        print(_count(len(result.credits), 'credit matches', 'credits match') + ' the pinned manifests. '
              'A matching credit is not licence clearance or owner approval.')
    else:
        print('No adopted code yet: no file carries an "Adapted from" credit and none is a byte-identical copy '
              'of a snapshot file, so there is nothing to check.')
    print('adoptions ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
