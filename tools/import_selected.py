"""Complete oversized imports with pinned, bounded, inert source selections."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import time
from urllib.parse import quote
import urllib.error
import urllib.request
from import_sources import ROOT, MAX_FILE, blob_sha, safe_path, select, verify

PREFIXES = {
    'NousResearch/hermes-agent': ('agent/', 'gateway/', 'tools/', 'cron/'),
    'openclaw/openclaw': ('src/security/', 'src/gateway/', 'src/agents/'),
}
LIMIT = 80
BINARY_SUFFIXES = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.pdf', '.woff', '.woff2', '.ttf', '.mp3', '.mp4'}


def get(url: str, cap: int) -> bytes:
    for attempt in range(4):
        time.sleep(0.3)
        request = urllib.request.Request(url, headers={'User-Agent': 'ALFRED-research/0.1'})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.url.split('/')[2] not in {'api.github.com', 'raw.githubusercontent.com'}:
                    raise ValueError('Unexpected host')
                data = response.read(cap + 1)
            if len(data) > cap:
                raise ValueError('Response size cap')
            return data
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 502, 503, 504} or attempt == 3:
                raise
            retry = exc.headers.get('Retry-After', '')
            delay = 5 * (2 ** attempt)
            if retry:
                try:
                    delay = max(delay, int(retry))
                except ValueError:
                    delay = max(delay, parsedate_to_datetime(retry).timestamp() - time.time())
            if delay > 120:
                raise ValueError('Server requests a longer retry delay; import remains incomplete') from exc
            time.sleep(delay)
    raise RuntimeError('Unreachable retry state')


def legal(path: str) -> bool:
    return any(x in PurePosixPath(path).name.lower() for x in ('license', 'licence', 'notice', 'copying', 'copyright'))


def snapshot(source: dict, dest: Path) -> dict:
    repo, commit = source['repository'], source['commit']
    data = json.loads(get(f'https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1', 24 * 1024 * 1024))
    if data.get('truncated'):
        raise ValueError('Refusing a truncated source tree')
    entries = [e for e in data['tree'] if e['type'] == 'blob']
    eligible = []
    for entry in entries:
        p = safe_path('root/' + entry['path'])
        if entry['mode'] not in {'100644', '100755'} or entry.get('size', MAX_FILE + 1) > MAX_FILE:
            continue
        if p.suffix.lower() in BINARY_SUFFIXES or not select(p):
            continue
        if legal(str(p)) or str(p) in {'README.md', 'SECURITY.md', 'pyproject.toml', 'package.json'}:
            eligible.append((0, entry))
        elif str(p).startswith(PREFIXES[repo]):
            priority = 1 if any(x in str(p).lower() for x in ('approval', 'policy', 'security', 'permission', 'auth', 'memory', 'session')) else 2
            eligible.append((priority, entry))
    eligible.sort(key=lambda item: (item[0], item[1]['path']))
    mandatory = [e for priority, e in eligible if priority == 0]
    optional = [e for priority, e in eligible if priority != 0][:LIMIT]
    chosen = mandatory + optional
    if sum(e.get('size', 0) for e in chosen) > 24 * 1024 * 1024:
        raise ValueError('Selected text budget exceeded')

    def copy(entry: dict) -> dict:
        path = entry['path']
        raw = get(f'https://raw.githubusercontent.com/{repo}/{commit}/{quote(path, safe="/")}', MAX_FILE)
        if blob_sha(raw) != entry['sha']:
            raise ValueError('Git blob mismatch: ' + path)
        raw.decode('utf-8')
        if b'\0' in raw:
            raise ValueError('Unexpected binary: ' + path)
        target = dest / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        target.chmod(0o644)
        return {'path': path, 'bytes': len(raw), 'git_blob_sha1': entry['sha'], 'sha256': hashlib.sha256(raw).hexdigest()}

    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(copy, chosen))
    if blob_sha((dest / source['licence_path']).read_bytes()) != source['licence_blob_sha1']:
        raise ValueError('Licence pin mismatch')
    for name in source.get('required_notices', []):
        if not (dest / name).is_file():
            raise ValueError('Required notice missing: ' + name)
    selected = {e['path'] for e in chosen}
    return {'repository': repo, 'commit': commit, 'licence': source['licence'],
            'scope': 'focused source selection, NOT a complete repository or runnable package',
            'selection': {'prefixes': PREFIXES[repo], 'optional_file_limit': LIMIT, 'eligible_text_legal_notices': True},
            'runtime_enabled': False, 'file_count': len(records), 'bytes': sum(r['bytes'] for r in records),
            'files': records, 'excluded': [{'path': e['path'], 'reason': 'outside bounded source selection or filtered path/type/size'} for e in entries if e['path'] not in selected]}


def main() -> None:
    path = ROOT / 'third_party/IMPORT_RECEIPT.json'
    report = json.loads(path.read_text())
    if not report['failures']:
        verify()
        return
    report.setdefault('previous_import_failures', []).extend(report['failures'])
    completed = {s['repository'] for s in report['sources']}
    failures = []
    lock = json.loads((ROOT / 'third_party/sources.lock.json').read_text())
    for source in lock['sources']:
        if source['repository'] in completed:
            continue
        dest = ROOT / 'third_party/sources' / source['repository'].replace('/', '__')
        if dest.exists():
            raise ValueError('Refusing to replace existing source')
        try:
            with tempfile.TemporaryDirectory(dir=ROOT / 'third_party') as tmp:
                staging = Path(tmp) / 'source'
                staging.mkdir()
                result = snapshot(source, staging)
                staging.rename(dest)
            report['sources'].append(result)
            print(result['repository'], result['file_count'], 'pinned files copied; NOT executed')
        except Exception as exc:
            failures.append({'repository': source['repository'], 'error': str(exc)})
            print(source['repository'], 'FAILED:', exc)
    report['failures'] = failures
    path.write_text(json.dumps(report, indent=2) + '\n')
    print('Current import failures:', len(failures))


if __name__ == '__main__':
    main()
