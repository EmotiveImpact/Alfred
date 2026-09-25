"""Copy pinned public source as inert research data. Never install or execute it."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MAX_DOWNLOAD = 64 * 1024 * 1024
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 48 * 1024 * 1024
TEXT = {'.py', '.ts', '.tsx', '.js', '.mjs', '.cjs', '.jsx', '.json', '.md', '.mdx',
        '.yaml', '.yml', '.toml', '.ini', '.cfg', '.txt', '.sh', '.rs', '.go', '.html',
        '.css', '.sql', '.proto', '.lock', '.example', '.in'}


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def safe_path(name: str) -> PurePosixPath:
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or '\0' in name:
        raise ValueError('Unsafe archive path')
    if len(p.parts) < 2 or any(part.lower() == '.git' for part in p.parts):
        raise ValueError('Unexpected archive path')
    return PurePosixPath(*p.parts[1:])


def select(path: PurePosixPath) -> bool:
    name = path.name.lower()
    # Preserve licence / copyright / notice files, including nested exceptions.
    legal = any(term in name for term in ('license', 'licence', 'notice', 'copying', 'copyright'))
    if legal:
        return True
    if any(part in {'node_modules', '.venv', '__pycache__', 'vendor', 'dist', 'build'} for part in path.parts):
        return False
    if name == '.env' or (name.startswith('.env.') and not name.endswith(('example', 'sample', 'template'))):
        return False
    if path.suffix.lower() in {'.pem', '.key', '.p12', '.pfx', '.sqlite', '.db'}:
        return False
    return path.suffix.lower() in TEXT or name in {'dockerfile', 'makefile', '.gitignore', '.gitattributes'}


def extract(archive: bytes, dest: Path, source: dict) -> dict:
    copied, excluded, seen = [], [], set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
        for member in tar:
            if member.isdir():
                continue
            path = safe_path(member.name)
            key = str(path)
            if key in seen:
                raise ValueError('Duplicate archive path')
            seen.add(key)
            reason = None
            if not member.isfile():
                reason = 'non-regular entry (links are never followed)'
            elif member.size > MAX_FILE:
                reason = 'file size cap'
            elif not select(path):
                reason = 'not source/text or sensitive-path exclusion'
            if reason:
                excluded.append({'path': key, 'reason': reason})
                continue
            stream = tar.extractfile(member)
            if stream is None:
                raise ValueError('Missing file stream')
            data = stream.read(MAX_FILE + 1)
            if len(data) != member.size:
                raise ValueError('File size mismatch')
            try:
                data.decode('utf-8')
            except UnicodeDecodeError:
                excluded.append({'path': key, 'reason': 'not UTF-8 text'})
                continue
            if b'\0' in data:
                excluded.append({'path': key, 'reason': 'binary content'})
                continue
            total += len(data)
            if total > MAX_TOTAL:
                raise ValueError('Source snapshot size cap exceeded')
            target = dest / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            # Copied scripts are data; do not preserve execute permission.
            target.chmod(0o644)
            copied.append({'path': key, 'bytes': len(data), 'git_blob_sha1': blob_sha(data),
                           'sha256': hashlib.sha256(data).hexdigest()})
    licence = dest / source['licence_path']
    if not licence.is_file() or blob_sha(licence.read_bytes()) != source['licence_blob_sha1']:
        raise ValueError('Pinned licence mismatch')
    for required in source.get('required_notices', []):
        if not (dest / required).is_file():
            raise ValueError('Required third-party notice missing: ' + required)
    return {'repository': source['repository'], 'commit': source['commit'],
            'licence': source['licence'], 'scope': 'source/text snapshot, NOT a complete fork',
            'runtime_enabled': False, 'archive_sha256': hashlib.sha256(archive).hexdigest(),
            'file_count': len(copied), 'bytes': total, 'files': copied, 'excluded': excluded}


def fetch(source: dict) -> bytes:
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', source['repository']):
        raise ValueError('Invalid repository')
    if not re.fullmatch(r'[0-9a-f]{40}', source['commit']):
        raise ValueError('Commit must be pinned')
    url = f"https://codeload.github.com/{source['repository']}/tar.gz/{source['commit']}"
    request = urllib.request.Request(url, headers={'User-Agent': 'ALFRED-source-research/0.1'})
    with urllib.request.urlopen(request, timeout=120) as response:
        if not response.url.startswith('https://codeload.github.com/'):
            raise ValueError('Unexpected archive host')
        data = response.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError('Download cap exceeded')
    return data


def verify() -> None:
    report = json.loads((ROOT / 'third_party/IMPORT_RECEIPT.json').read_text())
    if report['failures']:
        raise ValueError('One or more imports failed')
    count = 0
    for result in report['sources']:
        dest = ROOT / 'third_party/sources' / result['repository'].replace('/', '__')
        expected = {record['path'] for record in result['files']}
        actual = {p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file()}
        if expected != actual:
            raise ValueError('Snapshot file-set mismatch')
        for record in result['files']:
            path = dest / record['path']
            if path.is_symlink():
                raise ValueError('Unexpected symlink')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != record['sha256'] or blob_sha(data) != record['git_blob_sha1']:
                raise ValueError('Snapshot byte mismatch: ' + str(path))
            count += 1
    print(f'Verified {count} exact source files across {len(report["sources"])} pinned snapshots.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        verify()
        return
    lock = json.loads((ROOT / 'third_party/sources.lock.json').read_text())
    report = {'schema_version': 1, 'sources': [], 'failures': []}
    for source in lock['sources']:
        dest = ROOT / 'third_party/sources' / source['repository'].replace('/', '__')
        if dest.exists():
            raise ValueError('Refusing to overwrite an existing snapshot: ' + str(dest))
        try:
            archive = fetch(source)
            with tempfile.TemporaryDirectory(dir=ROOT / 'third_party') as tmp:
                staging = Path(tmp) / 'source'
                staging.mkdir()
                result = extract(archive, staging, source)
                dest.parent.mkdir(parents=True, exist_ok=True)
                staging.rename(dest)
            report['sources'].append(result)
            print(source['repository'], result['file_count'], 'source files copied; upstream NOT executed')
        except Exception as exc:
            report['failures'].append({'repository': source['repository'], 'error': str(exc)})
            print(source['repository'], 'IMPORT FAILED:', exc)
    (ROOT / 'third_party/IMPORT_RECEIPT.json').write_text(json.dumps(report, indent=2) + '\n')
    # Preserve successful imports and accurately report any incomplete sources.
    print('Import failures:', len(report['failures']))


if __name__ == '__main__':
    main()
