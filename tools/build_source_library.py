"""Preserve licensed public source as inert reference data; never install or execute it.

Archive scope is all eligible UTF-8 source/test/document/configuration files at a pinned
commit, not Git history, binaries, model weights, datasets or a runnable installation.
A licence allowlist is a redistribution screen, NOT a complete dependency/legal audit.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = Path('third_party/library')
REQUEST = Path('third_party/library-request.json')
ALLOWED = {'MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'ISC', 'Unlicense',
           'MPL-2.0', 'GPL-2.0', 'GPL-3.0', 'AGPL-3.0', 'LGPL-2.1', 'LGPL-3.0',
           'GPL-2.0-only', 'GPL-2.0-or-later', 'GPL-3.0-only', 'GPL-3.0-or-later',
           'AGPL-3.0-only', 'AGPL-3.0-or-later', 'PostgreSQL'}
# Existing documented restrictions are not erased by automated licence detection.
REFERENCE_ONLY = {
    'obsidianmd/obsidian-headless': 'Package declares UNLICENSED; no redistribution grant established. Official external-client reference only.',
    'isair/jarvis': 'Previously documented commercial-use restriction; explicit permission/terms review needed before copying for this product.',
    'ethanplusai/jarvis': 'Previously documented custom non-commercial terms; explicit permission/terms review needed before copying for this product.'}
MAX_DOWNLOAD = 256 * 1024 * 1024
MAX_FILE = 3 * 1024 * 1024
MAX_SOURCE = 192 * 1024 * 1024
MAX_LIBRARY = 900 * 1024 * 1024
MAX_MEMBERS = 150000
BINARY_SUFFIXES = {'.png','.jpg','.jpeg','.gif','.webp','.ico','.pdf','.zip','.gz','.xz','.zst',
 '.woff','.woff2','.ttf','.otf','.mp3','.wav','.mp4','.mov','.webm','.onnx','.gguf','.safetensors',
 '.pt','.pth','.bin','.dll','.so','.dylib','.exe','.sqlite','.sqlite3','.db','.parquet','.arrow'}
DATA_DIRS = {'node_modules','.git','.venv','venv','__pycache__','datasets','dataset','data','model_weights'}
PRIVATE_CONTENT = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}')

class QuotaStopped(RuntimeError):
    pass

class HostOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, host: str): self.host = host
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urllib.parse.urlsplit(newurl)
        if parts.scheme != 'https' or parts.netloc != self.host:
            raise ValueError('Cross-host redirect refused')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def safe_path(value: str) -> str:
    if not isinstance(value, str) or not value or value.startswith('/') or '\\' in value:
        raise ValueError('Unsafe path')
    if any(ord(c) < 32 or ord(c) == 127 for c in value): raise ValueError('Control character in path')
    parts = value.split('/')
    if any(p in ('', '.', '..') or ':' in p for p in parts): raise ValueError('Unsafe path component')
    return str(PurePosixPath(value))


def api(path: str) -> object:
    if not path.startswith('/repos/') or not re.fullmatch(r'[A-Za-z0-9_./?=&%+~-]+', path):
        raise ValueError('Only repository API reads are allowed')
    headers = {'User-Agent':'ALFRED-source-reference-audit', 'Accept':'application/vnd.github+json'}
    token = os.environ.get('GH_TOKEN')
    if token: headers['Authorization'] = 'Bearer '+token
    req = urllib.request.Request('https://api.github.com'+path, headers=headers)
    opener = urllib.request.build_opener(HostOnlyRedirect('api.github.com'))
    try:
        with opener.open(req, timeout=45) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000: raise ValueError('Oversized metadata response')
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        if exc.code == 429 or (exc.code == 403 and exc.headers.get('X-RateLimit-Remaining') == '0'):
            raise QuotaStopped('GitHub API quota reached; no alternate credentials or rerouting') from None
        raise


def root_pins(root: Path) -> dict:
    result = {}
    for name in ('third_party/sources.lock.json','third_party/extension.lock.json'):
        for row in json.loads((root/name).read_text())['sources']:
            result[row['repository'].casefold()] = row
    for row in json.loads((root/'research/memory-sources.json').read_text())['pinned_reviews']:
        result.setdefault(row['repository'].casefold(), row)
    return result


def audit(requested: str, pins: dict) -> dict:
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', requested):
        raise ValueError('Invalid repository')
    repo = api('/repos/'+requested)
    if repo.get('private'): raise ValueError('Only public upstream repositories are permitted')
    canonical = repo['full_name']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', canonical): raise ValueError('Invalid canonical name')
    pin = pins.get(requested.casefold(), pins.get(canonical.casefold(), {}))
    commit = pin.get('commit')
    if not commit:
        ref = urllib.parse.quote(repo['default_branch'], safe='')
        commit = api('/repos/'+canonical+'/commits/'+ref)['sha']
    if not re.fullmatch(r'[a-f0-9]{40}', commit): raise ValueError('Unpinned commit')
    row = {'requested_repository':requested,'repository':canonical,'commit':commit,
           'upstream_url':'https://github.com/'+canonical,'source_url':'https://github.com/'+canonical+'/tree/'+commit,
           'status':'reference_only','source_copied':False,'runtime_installed':False,'files':0}
    try:
        lic = api('/repos/'+canonical+'/license?ref='+commit)
        raw = base64.b64decode(lic['content'], validate=False)
        if blob_sha(raw) != lic['sha']: raise ValueError('Licence bytes do not match Git blob')
        raw.decode('utf-8')
        row.update({'licence':lic['license']['spdx_id'],'licence_path':safe_path(lic['path']),
                    'licence_blob':lic['sha'],'licence_sha256':hashlib.sha256(raw).hexdigest(),
                    'licence_url':'https://github.com/'+canonical+'/blob/'+commit+'/'+lic['path']})
    except urllib.error.HTTPError as exc:
        if exc.code != 404: raise
        row.update({'licence':'not established','reason':'No recognised root licence returned at the pinned revision; source not copied.'})
    restriction = REFERENCE_ONLY.get(requested.casefold()) or REFERENCE_ONLY.get(canonical.casefold())
    if restriction:
        row['reason'] = restriction
        if requested.casefold() == 'obsidianmd/obsidian-headless': row['licence'] = 'UNLICENSED (package declaration)'
    elif row.get('licence') in ALLOWED:
        row['status'] = 'eligible'
        row['reason'] = 'Root licence permits source redistribution subject to its terms; preserve notices. Not a full dependency/asset audit or adoption approval.'
    else:
        row.setdefault('reason','Licence requires specific review outside the redistribution allowlist; source not copied.')
    return row


def excluded(path: str, member: tarfile.TarInfo, raw: bytes | None = None) -> str | None:
    parts = PurePosixPath(path).parts
    name = parts[-1].lower()
    if not member.isfile(): return 'non-regular file (including symlink/submodule/special file)'
    if any(part.lower() in DATA_DIRS for part in parts): return 'dependency/environment/dataset directory'
    if name in {'.gitattributes','.lfsconfig'}: return 'upstream Git content-conversion configuration retained only as a reference'
    if name.startswith('.env') or name in {'id_rsa','id_ed25519','credentials.json','secrets.json'} or name.endswith(('.pem','.key','.p12','.pfx')):
        return 'credential/configuration-sensitive path'
    if PurePosixPath(name).suffix in BINARY_SUFFIXES: return 'binary/media/model/database/archive asset'
    if member.size > MAX_FILE: return 'per-file source-text bound'
    if raw is not None:
        if b'\0' in raw: return 'binary bytes'
        try: raw.decode('utf-8')
        except UnicodeDecodeError: return 'not UTF-8 text'
        if PRIVATE_CONTENT.search(raw): return 'private-key or token-shaped content'
        if raw.startswith(b'version https://git-lfs.github.com/spec/v1'): return 'Git LFS pointer, external asset not fetched'
    return None


def download(row: dict, destination: Path) -> str:
    url = 'https://codeload.github.com/'+row['repository']+'/tar.gz/'+row['commit']
    opener = urllib.request.build_opener(HostOnlyRedirect('codeload.github.com'))
    digest = hashlib.sha256(); total = 0; start = time.monotonic()
    with opener.open(urllib.request.Request(url,headers={'User-Agent':'ALFRED-source-reference-audit'}),timeout=60) as response, destination.open('xb') as out:
        while block := response.read(1024*1024):
            total += len(block)
            if total > MAX_DOWNLOAD or time.monotonic()-start > 240: raise ValueError('Bounded source download exceeded')
            digest.update(block); out.write(block)
    return digest.hexdigest()


def preserve_archive(archive: Path, stage: Path, licence_path: str, licence_blob: str) -> dict:
    files, omissions, seen = [], [], set(); size = 0; root_name = None; member_count = 0
    with tarfile.open(archive, mode='r|gz') as source:
        for member in source:
            member_count += 1
            if member_count > MAX_MEMBERS: raise ValueError('Too many archive members')
            full = safe_path(member.name.rstrip('/'))
            parts = full.split('/')
            if root_name is None: root_name = parts[0]
            if parts[0] != root_name: raise ValueError('Multiple archive roots')
            if len(parts) == 1: continue
            path = safe_path('/'.join(parts[1:]))
            if member.isdir(): continue
            if path in seen: raise ValueError('Duplicate archive file')
            seen.add(path)
            reason = excluded(path, member)
            raw = None
            if reason is None:
                stream = source.extractfile(member)
                if stream is None: raise ValueError('Unreadable source member')
                raw = stream.read(MAX_FILE+1)
                if len(raw) != member.size: raise ValueError('Source member length differs')
                reason = excluded(path, member, raw)
            if reason:
                omissions.append({'path':path,'reason':reason,'bytes':member.size}); continue
            size += len(raw)
            if size > MAX_SOURCE: raise ValueError('Per-repository source-text bound exceeded')
            target = stage/path
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw)
            files.append({'path':path,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'git_blob_sha1':blob_sha(raw)})
    licence = stage/safe_path(licence_path)
    if not licence.is_file() or blob_sha(licence.read_bytes()) != licence_blob:
        raise ValueError('Pinned root licence missing or changed in archive')
    return {'files':sorted(files,key=lambda x:x['path']),'excluded':sorted(omissions,key=lambda x:x['path']),
            'file_count':len(files),'bytes':size,'archive_members':member_count}


def write_index(root: Path, rows: list[dict]) -> dict:
    output = root/LIBRARY; output.mkdir(parents=True,exist_ok=True)
    counts = {status:sum(r['status']==status for r in rows) for status in ('copied','reference_only','error')}
    report = {'schema_version':1,'date':'2026-09-27','purpose':'Inert build-reference source library',
              'product':'ALFRED: operational and executive intelligence',
              'input_commit':os.environ.get('GITHUB_SHA'),'workflow_run':os.environ.get('GITHUB_RUN_ID'),
              'scope':'All eligible source/test/docs/config text, not complete forks or Git history. Every omission is recorded.',
              'upstream_executed':False,'models_downloaded':False,'repositories':rows,
              'summary':{'requested':len(rows),**counts,'retained_files':sum(r.get('files',0) for r in rows),
                         'retained_bytes':sum(r.get('bytes',0) for r in rows)}}
    (output/'CATALOGUE.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=['# ALFRED upstream source library','', '**Operational and executive intelligence.**','',
           'This catalogue covers every repository requested in the two research landscapes and the agent additions.',
           'Source is inert reference material, not an enabled dependency. Existing historical snapshots are preserved separately.',
           'No upstream scripts, skills, tests, workflows, packages or models are executed by this importer.','',
           f"**{counts['copied']} source snapshots; {counts['reference_only']} reference-only; {counts['error']} errors.**",
           f"**{report['summary']['retained_files']:,} eligible source-text files copied.**",'',
           '| Repository | Availability | Licence observed | Files | Details |','|---|---|---|---:|---|']
    for row in rows:
        slug=row['repository'].replace('/','__')
        detail=f"[Source](snapshots/{slug}) · [manifest](manifests/{slug}.json)" if row['status']=='copied' else row.get('reason','').replace('|','/')
        lines.append(f"| [{row['repository']}]({row['source_url']}) | {row['status']} | {row.get('licence','not established')} | {row.get('files',0)} | {detail} |")
    lines += ['', '## Meaning of a source snapshot','',
              'This is broad source-text preservation without the old per-prefix selection cap. It is **not** a complete Git fork.',
              'Binary/media/model assets, datasets/dependency environments, secrets-like paths/content, symlinks, Git LFS assets,',
              'unsafe paths, Git content-conversion files and oversized files are excluded. Per-repository manifests enumerate omissions.',
              'Use the pinned upstream URL for the original tree and external build requirements. Do not install from this reference folder.', '',
              '## Permission and adoption','',
              'UNLICENSED is not the permissive Unlicense. Public visibility and viewing/forking rights do not grant unrestricted',
              'redistribution or incorporation into ALFRED. Obsidian Headless stays an official-client reference until an applicable grant is established.',
              'GPL/AGPL and other copied licences retain their terms; this collection does not relicense them or establish compatibility with a commercial release.',
              'A root-licence screen is not a full audit of nested code, assets, data, dependencies or hosted-service rights. Review the relevant path before adoption.', '',
              'Run `python3 tools/build_source_library.py --verify` to check this snapshot set without a network connection.',
              'Historical selections: `third_party/sources/` and `third_party/extensions/`; do not silently modify those receipts.','']
    (output/'README.md').write_text('\n'.join(lines))
    return report


def verify(root: Path) -> dict:
    output=root/LIBRARY
    report=json.loads((output/'CATALOGUE.json').read_text())
    request=json.loads((root/REQUEST).read_text())
    if report.get('upstream_executed') is not False or report.get('models_downloaded') is not False:
        raise ValueError('Invalid execution status')
    rows=report['repositories']
    if {r['requested_repository'] for r in rows} != set(request['repositories']) or len(rows)!=len(request['repositories']):
        raise ValueError('Catalogue does not cover exact requested repository set')
    total=0; byte_count=0; expected_dirs=set()
    for row in rows:
        if not re.fullmatch(r'[a-f0-9]{40}',row.get('commit','')): raise ValueError('Missing immutable pin')
        if row['status']!='copied':
            if row['source_copied'] or row.get('files')!=0: raise ValueError('False copy claim')
            continue
        if row['licence'] not in ALLOWED or row['repository'].casefold() in REFERENCE_ONLY:
            raise ValueError('Copy permission gate bypassed')
        slug=row['repository'].replace('/','__'); expected_dirs.add(slug)
        path=output/'snapshots'/slug
        manifest_file=output/'manifests'/(slug+'.json')
        if hashlib.sha256(manifest_file.read_bytes()).hexdigest()!=row['manifest_sha256']:
            raise ValueError('Manifest differs')
        manifest=json.loads(manifest_file.read_text())
        files=manifest['files']; known={f['path'] for f in files}
        if len(known)!=len(files): raise ValueError('Repeated manifest path')
        actual=set()
        for p in path.rglob('*'):
            if p.is_symlink(): raise ValueError('Symlink in stored source')
            if p.is_file(): actual.add(p.relative_to(path).as_posix())
        if actual!=known: raise ValueError('Snapshot file set differs: '+slug)
        subtotal=0
        for item in files:
            data=(path/safe_path(item['path'])).read_bytes()
            if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256'] or blob_sha(data)!=item['git_blob_sha1']:
                raise ValueError('Snapshot bytes differ: '+slug+'/'+item['path'])
            subtotal+=len(data)
        if blob_sha((path/row['licence_path']).read_bytes())!=row['licence_blob']: raise ValueError('Licence changed')
        if len(files)!=row['files'] or subtotal!=row['bytes']: raise ValueError('Snapshot totals differ')
        total+=len(files); byte_count+=subtotal
    snapshots=output/'snapshots'
    if snapshots.exists() and {p.name for p in snapshots.iterdir()}!=expected_dirs:
        raise ValueError('Uncatalogued snapshot directory')
    if total!=report['summary']['retained_files'] or byte_count!=report['summary']['retained_bytes']:
        raise ValueError('Catalogue totals differ')
    print(json.dumps({'verified_source_files':total,'verified_source_bytes':byte_count,'snapshots':len(expected_dirs),
                      'catalogued_repositories':len(rows),'upstream_executed':False}))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.verify: verify(ROOT); return
    request=json.loads((ROOT/REQUEST).read_text()); repos=request['repositories']
    if len(repos)!=len(set(r.casefold() for r in repos)): raise ValueError('Duplicate requested repository')
    output=ROOT/LIBRARY
    if (output/'CATALOGUE.json').exists():
        verify(ROOT); print('Existing immutable library verified; no network refresh.'); return
    pins=root_pins(ROOT); rows=[]; total=0; quota=False
    output.mkdir(parents=True,exist_ok=True)
    for requested in repos:
        row=None
        try:
            if quota: raise QuotaStopped('Earlier API quota stop')
            row=audit(requested,pins)
            if row['status']=='eligible':
                slug=row['repository'].replace('/','__'); destination=output/'snapshots'/slug
                if destination.exists(): raise ValueError('Refusing to overwrite existing snapshot')
                with tempfile.TemporaryDirectory(prefix='.stage-',dir=output) as tmp:
                    scratch=Path(tmp); stage=scratch/'source'; stage.mkdir()
                    row['archive_sha256']=download(row,scratch/'source.tar.gz')
                    manifest=preserve_archive(scratch/'source.tar.gz',stage,row['licence_path'],row['licence_blob'])
                    if total+manifest['bytes']>MAX_LIBRARY: raise ValueError('Aggregate source-text bound exceeded')
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    stage.rename(destination)
                raw=(json.dumps(manifest,indent=2)+'\n').encode()
                (output/'manifests').mkdir(exist_ok=True)
                (output/'manifests'/(slug+'.json')).write_bytes(raw)
                total+=manifest['bytes']
                row.update(status='copied',source_copied=True,files=manifest['file_count'],bytes=manifest['bytes'],
                           excluded_files=len(manifest['excluded']),manifest_sha256=hashlib.sha256(raw).hexdigest())
        except Exception as exc:
            if isinstance(exc,QuotaStopped): quota=True
            row=row or {'requested_repository':requested,'repository':requested,'commit':pins.get(requested.casefold(),{}).get('commit',''),
                        'source_url':'https://github.com/'+requested,'source_copied':False,'runtime_installed':False,'files':0}
            row.update(status='error',reason=type(exc).__name__+': '+str(exc)[:240])
        rows.append(row); write_index(ROOT,rows)
        print(requested,row['status'],row.get('files',0),row.get('licence','unresolved'),flush=True)
    report=write_index(ROOT,rows)
    if report['summary']['error']: raise SystemExit('Some sources unresolved; inspect the catalogue, do not claim a complete copy.')
    verify(ROOT)
    print(json.dumps(report['summary']))

if __name__=='__main__': main()
