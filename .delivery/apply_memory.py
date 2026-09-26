"""Apply a bounded first-party supersession-lineage correction before acceptance.

Normal source is retained in the resulting delivery commit; this temporary helper
is removed after the complete existing code and browser suite passes.
"""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[1]
TESTS='''    def test_later_review_preserves_supersession_lineage(self):
        a=self.propose();self.review(a);b=self.propose(object_id='sam')
        self.review(b,'supersede',replaces_id=a,replaces_version=self.get(a)['version'])
        for decision in ('dispute','accept','withdraw'):
            self.review(b,decision)
            self.assertEqual(self.get(b)['replaces_id'],a)
    def test_second_supersession_cannot_overwrite_lineage(self):
        a=self.propose();self.review(a);b=self.propose(object_id='sam')
        self.review(b,'supersede',replaces_id=a,replaces_version=self.get(a)['version'])
        c=self.propose();self.review(c)
        self.assertFault('memory_replacement_already_recorded',lambda:self.review(b,'supersede',replaces_id=c,replaces_version=self.get(c)['version']))
        self.assertEqual(self.get(b)['replaces_id'],a);self.assertEqual(self.get(c)['state'],'accepted')
    def test_source_invalidation_keeps_supersession_lineage(self):
        a=self.propose();self.review(a);b=self.propose(object_id='sam')
        self.review(b,'supersede',replaces_id=a,replaces_version=self.get(a)['version'])
        self.file.write_text('# Atlas\\nThe source has changed.\\n');self.scan.scan()
        self.assertEqual(self.get(b)['state'],'invalidated');self.assertEqual(self.get(b)['replaces_id'],a)
'''
EDITS=[
 ('alfred/reviewed_memory.py','1e39c3e95a02e2bfceec27a7ef90d84c2d532fffa0b2b665b6b112552d5ee73c','53d7cf5d4fcf861a9e2f01509b26ade9afc84070d05279ce9845b00ff8bfc1de',[
  ('            replacement=None\n',"            replacement=c['replaces_id']\n"),
  ("            if body['decision']=='supersede':\n","            if body['decision']=='supersede':\n                if c['replaces_id'] is not None:raise Fault('memory_replacement_already_recorded',409)\n")]),
 ('web/reviewed-memory.js','f634d8d92f87e29708a17e9abb94746edb73c7cb3dc420330c12483320586adb','8c29da90bb6ce4229dcc707144c392b56f26dadb72e31dcbec883e61ffe82cb9',[
  ('if(alternatives.length){','if(alternatives.length&&!c.replaces_id){')]),
 ('tests/test_reviewed_memory.py','431ed5bd59968105b8938ccdb27abe767f6c176372e65cfc9862883767a4f7e8','3247742964df2d4a451d8c540795dc39001b63e1ea9aa2409df66c574d203521',[
  ('    def test_supersession_does_not_cross_subject(self):\n',TESTS+'    def test_supersession_does_not_cross_subject(self):\n')])]
ready=[]
for name,before,after,edits in EDITS:
    p=ROOT/name
    if p.is_symlink() or any(x.is_symlink() for x in p.parents):raise ValueError('Unexpected symlink')
    raw=p.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if digest==after:continue
    if digest!=before:raise ValueError('Unexpected predecessor: '+name)
    value=raw.decode()
    for old,new in edits:
        if value.count(old)!=1:raise ValueError('Ambiguous edit: '+name)
        value=value.replace(old,new)
    raw=value.encode()
    if hashlib.sha256(raw).hexdigest()!=after:raise ValueError('Unexpected result: '+name)
    ready.append((p,raw))
for p,raw in ready:p.write_bytes(raw)
print('Preserved supersession lineage in',len(ready),'verified first-party files; no model or upstream execution.')
