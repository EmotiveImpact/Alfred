"""Materialise this reviewed first-party delta, then leave normal source for review.

Only the explicit paths below are permitted. No upstream package is executed.
The temporary transport can be removed after acceptance; it is not a runtime.
"""
from pathlib import Path
import hashlib
import json
import lzma

ROOT = Path(__file__).resolve().parents[1]
ALLOW = set('''AGENTS.md README.md SESSION_HANDOFF.md alfred/desk_http.py alfred/knowledge.py alfred/pulse.py docs/PERSONAL_OS.md docs/ROADMAP.md tests/test_pulse.py tools/build_os_preview.py tools/check_desk_browser.py tools/check_grounded_browser.py tools/check_knowledge_browser.py tools/check_os_browser.py tools/check_os_preview.py tools/package_os.py web/app.js web/ask.js web/index.html web/knowledge.js web/os.css web/os.js'''.split())
EXPECTED = '1b5a7b56e6830d4962a137b7f2ed6f0919d440c6541e930daef59b41d47d6d71'

def main():
    packed = b''.join((ROOT / f'.delivery/os-v06.{n:02}').read_bytes() for n in range(1, 5))
    if hashlib.sha256(packed).hexdigest() != EXPECTED:
        raise ValueError('Transport hash mismatch')
    decoder = lzma.LZMADecompressor(memlimit=128 * 1024 * 1024)
    raw = decoder.decompress(packed, max_length=500001)
    if len(raw) > 500000 or not decoder.eof or decoder.unused_data:
        raise ValueError('Invalid or oversized transport')
    payload = json.loads(raw)
    if payload['schema'] != 1 or payload['base_commit'] != 'af10f961665962a42d2d78f00864edb9c267db26':
        raise ValueError('Unexpected predecessor')
    files = payload['files']
    if len(files) != len(ALLOW) or {f['path'] for f in files} != ALLOW:
        raise ValueError('Unexpected file set')
    ready = []
    for item in files:
        target = ROOT / item['path']
        if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != ROOT.parent):
            raise ValueError('Symlink not allowed')
        prior = target.read_bytes() if target.exists() else None
        before = hashlib.sha256(prior).hexdigest() if prior is not None else None
        if before == item['sha256']:
            continue
        if before != item['before']:
            raise ValueError('Predecessor differs: ' + item['path'])
        if 'text' in item:
            value = item['text'].encode('utf-8')
        else:
            lines = prior.decode('utf-8').splitlines(keepends=True)
            edits = item['edits']
            previous = 0
            for start, end, replacement in edits:
                if type(start) is not int or type(end) is not int or not previous <= start <= end <= len(lines) or not all(type(x) is str for x in replacement):
                    raise ValueError('Invalid edit')
                previous = end
            for start, end, replacement in reversed(edits):
                lines[start:end] = replacement
            value = ''.join(lines).encode('utf-8')
        if hashlib.sha256(value).hexdigest() != item['sha256']:
            raise ValueError('Result hash mismatch: ' + item['path'])
        ready.append((target, value))
    for target, value in ready:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    print(f'Verified and materialised {len(ready)} first-party files; no upstream code executed.')

if __name__ == '__main__':
    main()
