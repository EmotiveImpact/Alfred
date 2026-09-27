"""Complete exact inspected grants without re-downloading the oversized source.

Two recorded attempts found the complete pinned OpenClaw text exceeded 192 MiB
and 512 MiB. Keep its original focused snapshot and an honest size-limited
reference rather than repeatedly increasing bounds or claiming a complete copy.
All licence restrictions remain. No upstream application is executed.
"""
from pathlib import Path
import base64
import hashlib
import json
import tempfile
import build_source_library as library

REVIEWS = [
    ('openclaw/openclaw','8133be64d156a7a7f625ab69469b642930e29aec','LICENSE','ebaebf7c416761a32f932ad70ebe5d1d2e214f68','MIT',['THIRD_PARTY_NOTICES.md']),
    ('livekit/agents','57b3227a7842697e6ad45b1275369cf9700bf161','LICENSE','261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64','Apache-2.0',[]),
    ('asg017/sqlite-vec','04d28bd21773981e2d266bbf6aa4efbd011eb4f6','LICENSE-MIT','9c106bc48c760f7ed9f5b8255dea7adeef029cbe','MIT',['LICENSE-APACHE']),
    ('pgvector/pgvector','7db2345ed99bc77bf33cbdc8b12bd1973210dc81','LICENSE','fc5f177fa5d9c0d20a949f4b4faa028999977008','PostgreSQL',[]),
]

def main():
    report=library.verify(library.ROOT)
    rows=report['repositories']
    output=library.ROOT/library.LIBRARY
    total=report['summary']['retained_bytes']
    for repo,commit,path,sha,licence,notices in REVIEWS:
        row=next(r for r in rows if r['repository']==repo)
        if row['commit']!=commit:raise ValueError('Reviewed commit changed: '+repo)
        if row['status']=='copied':continue
        if repo in library.REFERENCE_ONLY:raise ValueError('Restricted source cannot be promoted')
        response=library.api('/repos/'+repo+'/contents/'+path+'?ref='+commit)
        raw=base64.b64decode(response['content'])
        if response['sha']!=sha or library.blob_sha(raw)!=sha:raise ValueError('Reviewed licence changed')
        row.update(licence=licence,licence_path=path,licence_blob=sha,
                   licence_sha256=hashlib.sha256(raw).hexdigest(),
                   licence_url='https://github.com/'+repo+'/blob/'+commit+'/'+path,
                   licence_review_basis='Exact manually inspected root grant; GitHub classification was NOASSERTION. Not blanket dependency/asset clearance.')
        if repo=='openclaw/openclaw':
            row.update(status='reference_only',source_copied=False,files=0,
                       historical_selection='third_party/sources/openclaw__openclaw',
                       reason='Broad source-text copy exceeded the 192 MiB and 512 MiB per-repository limits in runs 36290752368 and 36290874461. No partial broad snapshot was committed. The original pinned 146-file focused selection remains available; this is not a complete copy.')
            print(repo,'size-limited reference; historical focused source preserved',flush=True)
            continue
        slug=repo.replace('/','__');destination=output/'snapshots'/slug
        if destination.exists():raise ValueError('Will not overwrite a snapshot')
        with tempfile.TemporaryDirectory(prefix='.review-',dir=output) as temporary:
            scratch=Path(temporary);stage=scratch/'source';stage.mkdir()
            archive_hash=library.download(row,scratch/'archive.tar.gz')
            manifest=library.preserve_archive(scratch/'archive.tar.gz',stage,path,sha)
            if total+manifest['bytes']>library.MAX_LIBRARY:raise ValueError('Aggregate source-text limit')
            for notice in notices:
                if not (stage/notice).is_file():raise ValueError('Required notice missing: '+notice)
            stage.rename(destination)
        raw_manifest=(json.dumps(manifest,indent=2)+'\n').encode()
        (output/'manifests'/(slug+'.json')).write_bytes(raw_manifest)
        row.update(status='copied',source_copied=True,files=manifest['file_count'],bytes=manifest['bytes'],
                   excluded_files=len(manifest['excluded']),archive_sha256=archive_hash,
                   manifest_sha256=hashlib.sha256(raw_manifest).hexdigest(),
                   reason='Source redistribution grant inspected at exact pin; retained source and notices are unchanged.')
        total+=manifest['bytes']
        print(repo,manifest['file_count'],'source-text files copied, never executed',flush=True)
    library.write_index(library.ROOT,rows)
    library.verify(library.ROOT)

if __name__=='__main__':main()
