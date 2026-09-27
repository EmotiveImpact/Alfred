"""Package first-party application, documentation and actual acceptance receipts.

Quarantined upstream source is preserved in GitHub, not executed or repackaged here.
"""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]

def main():
    out=ROOT/'docs/previews/conversation-v07';out.mkdir(parents=True,exist_ok=True)
    names=['README.md','AGENTS.md','SESSION_HANDOFF.md']
    for folder,suffixes in [('alfred',{'.py'}),('web',{'.html','.js','.css'}),('tests',{'.py'}),('tools',{'.py'}),('docs',{'.md'}),('research',{'.md'})]:
        names += [p.relative_to(ROOT).as_posix() for p in (ROOT/folder).glob('*') if p.is_file() and p.suffix in suffixes]
    names += [p.relative_to(ROOT).as_posix() for p in (ROOT/'docs/evidence/conversation-v07').rglob('*') if p.is_file()]
    names += ['docs/previews/conversation-v07/ALFRED-OS-v07.html','docs/previews/conversation-v07/manifest.json']
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sorted(set(names))}
    target=out/'ALFRED-OS-v07-Developer-Package.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name in hashes:z.write(ROOT/name,name)
        z.writestr('PACKAGE_SHA256.json',json.dumps(hashes,indent=2)+'\n')
        z.writestr('PACKAGE_README.txt','ALFRED OS v0.7. Read README.md, docs/CONVERSATIONS.md and SESSION_HANDOFF.md.\nFirst-party local development application only. No native OS installation. Small synthetic real-model trial is documented, not general validation.\nUpstream quarantine is excluded: full source verifiers require the GitHub branch.\n')
    (out/'package-manifest.json').write_text(json.dumps({'file':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'files':len(hashes),'excludes':'upstream quarantine and runtime data'},indent=2)+'\n')
    print('Packaged',len(hashes),'first-party source/document/evidence files')
if __name__=='__main__':main()
