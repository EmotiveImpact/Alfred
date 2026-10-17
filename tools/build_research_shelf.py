"""Add reviewed research repositories to an inert shelf; never install or execute them.

The 27 September library (third_party/library) is immutable, so repositories studied
later go on this separate shelf. Each entry is pinned to a full commit and to the exact
licence file bytes a person inspected. Files are read straight from Git objects with
`git ls-tree` and `git cat-file`, so no upstream .gitattributes filter, hook, script or
build step runs. The same exclusion rules as the library apply (binaries, models,
datasets, secrets-shaped content, symlinks, submodules, oversized files).

Usage:
  python3 tools/build_research_shelf.py           # add request entries not yet shelved
  python3 tools/build_research_shelf.py --verify  # offline byte check, used by CI
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SHELF = Path('third_party/research-shelf')
REQUEST = Path('third_party/research-shelf-request.json')
MAX_SHELF = 400 * 1024 * 1024

_spec = importlib.util.spec_from_file_location('source_library', Path(__file__).with_name('build_source_library.py'))
lib = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(lib)

COMMIT = re.compile(r'[a-f0-9]{40}')
REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+')


def slug(repository: str) -> str:
    return repository.replace('/', '__')


def check_entry(entry: dict) -> None:
    if not REPO.fullmatch(entry.get('repository', '')): raise ValueError('Invalid repository')
    if not COMMIT.fullmatch(entry.get('commit', '')): raise ValueError('Unpinned commit: ' + entry.get('repository', ''))
    if entry.get('licence') not in lib.ALLOWED: raise ValueError('Licence outside the redistribution allowlist')
    if not COMMIT.fullmatch(entry.get('licence_blob', '')): raise ValueError('Licence blob not pinned')
    lib.safe_path(entry['licence_path'])
    for prefix in entry.get('include_prefixes', []): lib.safe_path(prefix)


def git(repo: Path, *args: str, binary: bool = False):
    out = subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True,
                         env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'}).stdout
    return out if binary else out.decode()


def fetch(entry: dict, workdir: Path) -> Path:
    repo = workdir / 'repo.git'
    subprocess.run(['git', 'init', '-q', '--bare', str(repo)], check=True)
    git(repo, 'fetch', '-q', '--depth', '1', '--no-tags', 'https://github.com/' + entry['repository'], entry['commit'])
    if git(repo, 'rev-parse', 'FETCH_HEAD').strip() != entry['commit']: raise ValueError('Fetched commit differs from pin')
    return repo


def tree_to_tar(repo: Path, entry: dict, target: Path) -> list[dict]:
    """Write the pinned tree as a tar of raw Git blobs, honouring include_prefixes.

    Returns oversized files, which are recorded as omissions without being read."""
    oversized = []
    prefixes = entry.get('include_prefixes') or []
    keep = lambda p: not prefixes or p == entry['licence_path'] or any(p == x or p.startswith(x.rstrip('/') + '/') for x in prefixes)
    listing = git(repo, 'ls-tree', '-r', '-z', '--full-tree', '-l', entry['commit'], binary=True).split(b'\0')
    root = slug(entry['repository'])
    with tarfile.open(target, 'w:gz') as tf:
        for line in filter(None, listing):
            meta, path = line.split(b'\t', 1)
            mode, kind, sha, size = meta.split()
            path = path.decode('utf-8', 'surrogateescape')
            if not keep(path): continue
            info = tarfile.TarInfo(root + '/' + path)
            if mode == b'120000' or kind == b'commit':
                info.type = tarfile.SYMTYPE; info.linkname = 'not-followed'; tf.addfile(info); continue
            info.size = int(size)
            if info.size > lib.MAX_FILE:
                oversized.append({'path': lib.safe_path(path), 'reason': 'per-file source-text bound', 'bytes': info.size}); continue
            raw = git(repo, 'cat-file', 'blob', sha.decode(), binary=True)
            if lib.blob_sha(raw) != sha.decode(): raise ValueError('Git object does not match its id')
            tf.addfile(info, io.BytesIO(raw))
    return oversized


def write_index(root: Path, request: dict, rows: list[dict]) -> dict:
    out = root / SHELF; out.mkdir(parents=True, exist_ok=True)
    report = {'schema_version': 1, 'date': request['requested_on'], 'purpose': 'Inert research shelf for repositories studied after the 27 September library',
              'product': 'ALFRED: operational and executive intelligence', 'upstream_executed': False, 'models_downloaded': False,
              'repositories': rows,
              'summary': {'requested': len(rows), 'copied': len(rows),
                          'retained_files': sum(r['files'] for r in rows), 'retained_bytes': sum(r['bytes'] for r in rows)}}
    (out / 'CATALOGUE.json').write_text(json.dumps(report, indent=2) + '\n')
    lines = ['# ALFRED research shelf', '',
             'Outside projects studied for ALFRED\'s memory and brain design, kept as **inert reference text**.',
             'Nothing here is installed, imported, executed or followed as instructions. Upstream AGENTS, CLAUDE,',
             'prompts, skills, scripts and workflows are untrusted research data.', '',
             f"**{len(rows)} pinned snapshots, {report['summary']['retained_files']:,} source-text files.**", '',
             '| Repository | Commit | Licence | Files | Why it is here | Details |', '|---|---|---|---:|---|---|']
    for r in rows:
        s = slug(r['repository'])
        lines.append(f"| [{r['repository']}]({r['source_url']}) | `{r['commit'][:12]}` | {r['licence']} | {r['files']} | "
                     f"{r['why'].replace('|', '/')} | [source](snapshots/{s}) · [manifest](manifests/{s}.json) |")
    lines += ['', '## What a snapshot is', '',
              'The UTF-8 source, test, document and configuration text at one pinned commit. It is not a Git clone,',
              'has no history, and leaves out binaries, model weights, datasets, secrets-shaped content, symlinks,',
              'submodules and oversized files. Each manifest lists every file kept (with Git and SHA-256 hashes) and',
              'every file left out, with the reason. `include_prefixes` in the request marks a focused selection.', '',
              '## Licences and adoption', '',
              'Each licence file was read by a person at the pinned commit and its Git blob is recorded. The original',
              'licence and notice files stay inside each snapshot. A root licence is not clearance for nested',
              'dependencies, models, datasets, trademarks or hosted services. Reading this code is not adoption:',
              'bringing any of it into ALFRED needs the exact source path, licence, changes, containment, data-egress',
              'review and the owner\'s approval, as AGENTS.md requires.', '',
              'Hermes (NousResearch/hermes-agent), Letta and Graphiti are already in `third_party/library/`.',
              'Papers without released code are listed in `research/INTEGRATION_PLAN_2026-10-17.md`, not copied.', '',
              'Verify offline: `python3 tools/build_research_shelf.py --verify`.', '']
    (out / 'README.md').write_text('\n'.join(lines))
    return report


def verify(root: Path) -> dict:
    out = root / SHELF
    report = json.loads((out / 'CATALOGUE.json').read_text())
    request = json.loads((root / REQUEST).read_text())
    if report.get('upstream_executed') is not False or report.get('models_downloaded') is not False:
        raise ValueError('Invalid execution status')
    wanted = {(e['repository'], e['commit']) for e in request['repositories']}
    rows = report['repositories']
    if {(r['repository'], r['commit']) for r in rows} != wanted or len(rows) != len(wanted):
        raise ValueError('Shelf does not match the request exactly')
    total = size = 0
    for row in rows:
        check_entry(row)
        s = slug(row['repository']); path = out / 'snapshots' / s
        raw = (out / 'manifests' / (s + '.json')).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row['manifest_sha256']: raise ValueError('Manifest differs: ' + s)
        files = json.loads(raw)['files']
        actual = set()
        for p in path.rglob('*'):
            if p.is_symlink(): raise ValueError('Symlink in stored source')
            if p.is_file(): actual.add(p.relative_to(path).as_posix())
        if actual != {f['path'] for f in files}: raise ValueError('Snapshot file set differs: ' + s)
        sub = 0
        for item in files:
            data = (path / lib.safe_path(item['path'])).read_bytes()
            if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256'] or lib.blob_sha(data) != item['git_blob_sha1']:
                raise ValueError('Snapshot bytes differ: ' + s + '/' + item['path'])
            sub += len(data)
        if lib.blob_sha((path / row['licence_path']).read_bytes()) != row['licence_blob']: raise ValueError('Licence changed: ' + s)
        if len(files) != row['files'] or sub != row['bytes']: raise ValueError('Snapshot totals differ: ' + s)
        total += len(files); size += sub
    snapshots = out / 'snapshots'
    if {p.name for p in snapshots.iterdir()} != {slug(r['repository']) for r in rows}: raise ValueError('Uncatalogued snapshot directory')
    if total != report['summary']['retained_files'] or size != report['summary']['retained_bytes']: raise ValueError('Catalogue totals differ')
    print(json.dumps({'verified_source_files': total, 'verified_source_bytes': size, 'snapshots': len(rows), 'upstream_executed': False}))
    return report


def build(root: Path) -> None:
    request = json.loads((root / REQUEST).read_text())
    entries = request['repositories']
    if len({e['repository'].casefold() for e in entries}) != len(entries): raise ValueError('Duplicate requested repository')
    for e in entries: check_entry(e)
    out = root / SHELF
    existing = json.loads((out / 'CATALOGUE.json').read_text())['repositories'] if (out / 'CATALOGUE.json').exists() else []
    done = {(r['repository'], r['commit']) for r in existing}
    rows = list(existing); total = sum(r['bytes'] for r in rows)
    for entry in entries:
        if (entry['repository'], entry['commit']) in done: continue
        s = slug(entry['repository']); destination = out / 'snapshots' / s
        if destination.exists(): raise ValueError('Refusing to overwrite existing snapshot: ' + s)
        out.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.stage-', dir=out) as tmp:
            work = Path(tmp); stage = work / 'source'; stage.mkdir()
            oversized = tree_to_tar(fetch(entry, work), entry, work / 'source.tar.gz')
            manifest = lib.preserve_archive(work / 'source.tar.gz', stage, entry['licence_path'], entry['licence_blob'])
            manifest['excluded'] = sorted(manifest['excluded'] + oversized, key=lambda x: x['path'])
            if total + manifest['bytes'] > MAX_SHELF: raise ValueError('Aggregate shelf bound exceeded')
            destination.parent.mkdir(parents=True, exist_ok=True)
            stage.rename(destination)
        raw = (json.dumps(manifest, indent=2) + '\n').encode()
        (out / 'manifests').mkdir(exist_ok=True); (out / 'manifests' / (s + '.json')).write_bytes(raw)
        total += manifest['bytes']
        rows.append({'repository': entry['repository'], 'commit': entry['commit'],
                     'source_url': 'https://github.com/' + entry['repository'] + '/tree/' + entry['commit'],
                     'status': 'copied', 'source_copied': True, 'runtime_installed': False,
                     'licence': entry['licence'], 'licence_path': entry['licence_path'], 'licence_blob': entry['licence_blob'],
                     'licence_review_basis': entry['licence_review_basis'], 'why': entry['why'],
                     'include_prefixes': entry.get('include_prefixes', []),
                     'files': manifest['file_count'], 'bytes': manifest['bytes'], 'excluded_files': len(manifest['excluded']),
                     'manifest_sha256': hashlib.sha256(raw).hexdigest()})
        print(entry['repository'], manifest['file_count'], 'files', manifest['bytes'], 'bytes', flush=True)
        write_index(root, request, rows)
    order = {(e['repository'], e['commit']): i for i, e in enumerate(entries)}
    write_index(root, request, sorted(rows, key=lambda r: order[(r['repository'], r['commit'])]))
    verify(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    verify(ROOT) if args.verify else build(ROOT)


if __name__ == '__main__':
    main()
