"""Complete four exact, manually inspected redistribution grants.

GitHub reported NOASSERTION for these root files. Their actual licence text was
read, not assumed. This does not relax the UNLICENSED/non-commercial exclusions.
No upstream code is installed or executed. Existing snapshots stay immutable.
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
        slug=repo.replace('/','__');destination=output/'snapshots'/slug
        if destination.exists():raise ValueError('Will not overwrite a snapshot')
        with tempfile.TemporaryDirectory(prefix='.review-',dir=output) as temporary:
            scratch=Path(temporary);stage=scratch/'source';stage.mkdir()
            archive_hash=library.download(row,scratch/'archive.tar.gz')
            # The first attempt established that the pinned OpenClaw source text
            # exceeds the initial 192 MiB budget. Increase only this named source
            # to a bounded 512 MiB, retaining all path, licence, secret, asset and
            # per-file checks. This is source preservation, not code execution.
            previous_limit=library.MAX_SOURCE
            if repo=='openclaw/openclaw':library.MAX_SOURCE=512*1024*1024
            try:
                manifest=library.preserve_archive(scratch/'archive.tar.gz',stage,path,sha)
            finally:
                library.MAX_SOURCE=previous_limit
            if total+manifest['bytes']>1536*1024*1024:raise ValueError('Aggregate source-text limit')
            for notice in notices:
                if not (stage/notice).is_file():raise ValueError('Required notice missing: '+notice)
            stage.rename(destination)
        raw_manifest=(json.dumps(manifest,indent=2)+'\n').encode()
        (output/'manifests'/(slug+'.json')).write_bytes(raw_manifest)
        row.update(status='copied',source_copied=True,files=manifest['file_count'],bytes=manifest['bytes'],
                   excluded_files=len(manifest['excluded']),archive_sha256=archive_hash,
                   manifest_sha256=hashlib.sha256(raw_manifest).hexdigest(),licence=licence,
                   licence_path=path,licence_blob=sha,licence_sha256=hashlib.sha256(raw).hexdigest(),
                   licence_url='https://github.com/'+repo+'/blob/'+commit+'/'+path,
                   licence_review_basis='Exact manually inspected root grant; automated GitHub classification was NOASSERTION. Not blanket dependency/asset clearance.',
                   reason='Source redistribution grant inspected at exact pin; all retained files/notices remain unchanged.')
        total+=manifest['bytes']
        print(repo,manifest['file_count'],'source-text files copied, never executed',flush=True)
    library.write_index(library.ROOT,rows)
    library.verify(library.ROOT)

if __name__=='__main__':main()
