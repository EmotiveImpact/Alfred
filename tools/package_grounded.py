"""Package only original code/docs and synthetic visual evidence; no credentials."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/previews/grounded-v05'

def main():
    target=OUT/'ALFRED-Desk-v05-Developer-Package.zip'
    paths=[]
    for folder in ('alfred','web','tests','tools','research'):
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix in {'.py','.js','.css','.html','.md','.json'})
    paths.extend((ROOT/'docs').glob('*.md'))
    paths.extend(ROOT/n for n in ('README.md','AGENTS.md','SESSION_HANDOFF.md'))
    paths.extend(p for p in (ROOT/'docs/evidence/grounded-v05').rglob('*') if p.is_file() and not p.name.endswith('.b64'))
    paths.append(OUT/'ALFRED-Desk-v05.html')
    paths=sorted(set(paths))
    manifest={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for p in paths:archive.write(p,p.relative_to(ROOT))
        archive.writestr('PACKAGE_README.txt','ALFRED Desk v0.5 developer package. Original application code and synthetic evidence only.\nNot a hosted or installed assistant. Read docs/GROUNDED_DESK.md and README.md.\nThe eight quarantined upstream snapshots are NOT included; use the GitHub branch for their licences, source archives and verification. No upstream runtime is required for the default Desk.\nRun python3 -m unittest discover -s tests -v, then python3 -m alfred.desk init, access, serve using a new private data directory.\nNo model, microphone or external account is activated by the package.\n')
        archive.writestr('PACKAGE_SHA256.json',json.dumps(manifest,indent=2)+'\n')
    (OUT/'package-manifest.json').write_text(json.dumps({'file':target.name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'original_files':len(paths),'upstream_archives_included':False,'runtime_credentials_included':False},indent=2)+'\n')
    print('Packaged',len(paths),'original code/document/evidence files; no upstream runtimes or credentials.')

if __name__=='__main__':main()
