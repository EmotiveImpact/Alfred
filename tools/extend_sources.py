"""Reuse the bounded source copier for three reviewed pins, never execute upstream."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import import_selected as copier
from import_sources import ROOT, blob_sha, safe_path

LOCK = ROOT / 'third_party/extension.lock.json'
RECEIPT = ROOT / 'third_party/EXTENSION_RECEIPT.json'
BASE = ROOT / 'third_party/extensions'


def verify_extension() -> None:
    lock = json.loads(LOCK.read_text())
    report = json.loads(RECEIPT.read_text())
    expected = {s['repository']: s for s in lock['sources']}
    if report['failures'] or set(expected) != {s['repository'] for s in report['sources']}:
        raise ValueError('Incomplete extension source set')
    if len(report['sources']) != len(expected):
        raise ValueError('Duplicate source receipt')
    total = 0
    for item in report['sources']:
        source = expected[item['repository']]
        if item['commit'] != source['commit']:
            raise ValueError('Commit differs from reviewed lock')
        dest = BASE / item['repository'].replace('/', '__')
        paths = [r['path'] for r in item['files']]
        if len(paths) != len(set(paths)):
            raise ValueError('Duplicate file record')
        actual = {p.relative_to(dest).as_posix() for p in dest.rglob('*') if p.is_file()}
        if actual != set(paths) or any(p.is_symlink() for p in dest.rglob('*')):
            raise ValueError('File set changed')
        if blob_sha((dest / source['licence_path']).read_bytes()) != source['licence_blob_sha1']:
            raise ValueError('Licence differs from reviewed pin')
        size = 0
        for record in item['files']:
            path = safe_path('root/' + record['path'])
            data = (dest / path).read_bytes()
            if len(data) != record['bytes'] or blob_sha(data) != record['git_blob_sha1'] or hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError('Byte mismatch: ' + str(path))
            size += len(data)
        if item['file_count'] != len(paths) or item['bytes'] != size:
            raise ValueError('Receipt totals differ')
        total += len(paths)
    print(f'Verified {total} extension source files across {len(expected)} pins; no upstream code executed.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        verify_extension()
        return
    lock = json.loads(LOCK.read_text())
    report = json.loads(RECEIPT.read_text()) if RECEIPT.exists() else {'sources': [], 'failures': []}
    report.setdefault('previous_failures', []).extend(report['failures'])
    report['failures'] = []
    done = {s['repository'] for s in report['sources']}
    copier.LIMIT = 32
    for source in lock['sources']:
        if source['repository'] in done:
            continue
        copier.PREFIXES[source['repository']] = tuple(source['prefixes'])
        dest = BASE / source['repository'].replace('/', '__')
        if dest.exists():
            raise ValueError('Refusing to overwrite snapshot')
        try:
            with tempfile.TemporaryDirectory(dir=ROOT / 'third_party') as tmp:
                stage = Path(tmp) / 'source'
                stage.mkdir()
                result = copier.snapshot(source, stage)
                dest.parent.mkdir(parents=True, exist_ok=True)
                stage.rename(dest)
            report['sources'].append(result)
            print(source['repository'], result['file_count'], 'files retained, NOT installed')
        except Exception as exc:
            report['failures'].append({'repository': source['repository'], 'error': str(exc)})
    RECEIPT.write_text(json.dumps(report, indent=2) + '\n')
    print('Current failures:', len(report['failures']))


if __name__ == '__main__':
    main()
