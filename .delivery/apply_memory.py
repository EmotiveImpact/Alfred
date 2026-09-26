"""Materialise an exact reviewed first-party application delta.

Only the allowlisted application, test, UI and documentation files may change.
This does not contain or execute a model comparison, downloads or upstream code.
"""
from pathlib import Path
import hashlib
import json
import lzma

ROOT = Path(__file__).resolve().parents[1]
ALLOW = set('''AGENTS.md README.md SESSION_HANDOFF.md alfred/conversation.py alfred/desk_http.py alfred/evidence_review.py alfred/grounded.py alfred/pulse.py alfred/reviewed_memory.py docs/EVIDENCE_REVIEW.md docs/REVIEWED_MEMORY.md docs/ROADMAP.md tests/test_evidence_pipeline.py tests/test_evidence_review.py tests/test_memory_http.py tests/test_pulse_history.py tests/test_reviewed_memory.py tools/build_memory_preview.py tools/check_conversation_browser.py tools/check_memory_browser.py tools/check_memory_preview.py tools/package_memory.py web/ask.js web/conversation.js web/index.html web/os.js web/reviewed-memory.css web/reviewed-memory.js'''.split())
EXPECTED = '02de3d7d110c621f36594abf03b8670d474a15f2e2afcc37b9702388605872d2'

def main():
    packed = b''.join((ROOT / f'.delivery/memory-v08.{i:02}').read_bytes() for i in range(1, 5))
    if hashlib.sha256(packed).hexdigest() != EXPECTED:
        raise ValueError('Transfer hash mismatch')
    decoder = lzma.LZMADecompressor(memlimit=128 * 1024 * 1024)
    raw = decoder.decompress(packed, max_length=300001)
    if len(raw) > 300000 or not decoder.eof or decoder.unused_data:
        raise ValueError('Invalid or oversized transfer')
    payload = json.loads(raw)
    if payload['schema'] != 1 or payload['base_commit'] != 'e0a0ef973d20d3f60606423ab2035d9f9df9e68f':
        raise ValueError('Unexpected base')
    files = payload['files']
    if len(files) != len(ALLOW) or {f['path'] for f in files} != ALLOW:
        raise ValueError('Unexpected file set')
    ready = []
    for item in files:
        target = ROOT / item['path']
        if target.is_symlink() or any(p.is_symlink() for p in target.parents):
            raise ValueError('Symlink not permitted')
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
            previous = 0
            for start, end, replacement in item['edits']:
                if type(start) is not int or type(end) is not int or not previous <= start <= end <= len(lines) or not all(type(x) is str for x in replacement):
                    raise ValueError('Invalid edit')
                previous = end
            for start, end, replacement in reversed(item['edits']):
                lines[start:end] = replacement
            value = ''.join(lines).encode('utf-8')
        if hashlib.sha256(value).hexdigest() != item['sha256']:
            raise ValueError('Result hash differs: ' + item['path'])
        ready.append((target, value))
    for target, value in ready:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value)
    print(f'Materialised {len(ready)} exact first-party files; no upstream or model execution.')

if __name__ == '__main__':
    main()
