"""Materialise an allowlisted first-party delta with pinned before/after hashes.

Temporary delivery transport only. No upstream imports or dependency execution.
Successful acceptance removes transport and commits normal reviewable source.
"""
from pathlib import Path
import hashlib,json,lzma
ROOT=Path(__file__).resolve().parents[1]
ALLOW=set('''AGENTS.md README.md SESSION_HANDOFF.md alfred/desk.py alfred/desk_http.py alfred/knowledge.py alfred/conversation.py tests/test_conversation.py web/index.html web/os.js web/conversation.js web/conversation.css tools/check_os_browser.py tools/check_conversation_browser.py tools/check_conversation_preview.py tools/build_conversation_preview.py tools/package_conversation.py docs/CONVERSATIONS.md docs/ROADMAP.md research/MODEL_TRIAL_V07.md docs/evidence/conversation-v07/model-first/OLLAMA-LICENSE.txt docs/evidence/conversation-v07/model-first/QWEN-LICENSE.txt docs/evidence/conversation-v07/model-first/origin.json docs/evidence/conversation-v07/model-first/receipt.json docs/evidence/conversation-v07/model-first/results.json docs/evidence/conversation-v07/model-first/runtime.json docs/evidence/conversation-v07/model-second/OLLAMA-LICENSE.txt docs/evidence/conversation-v07/model-second/QWEN-LICENSE.txt docs/evidence/conversation-v07/model-second/loaded-model.txt docs/evidence/conversation-v07/model-second/origin.json docs/evidence/conversation-v07/model-second/receipt.json docs/evidence/conversation-v07/model-second/results.json docs/evidence/conversation-v07/model-second/runtime.json'''.split())
FIXED='db77a2b2f95d95b9d207f89cf365614bd2da12023d81bc4115c21c2827f0e232'

def main():
    packed=b''.join((ROOT/f'.delivery/conversation-v07.{n:02}').read_bytes() for n in range(1,4))
    if hashlib.sha256(packed).hexdigest()!='977359f412b37b36d0e31a1564e9b5ea74561a4c6b2b7731745e322ebfb94b10':raise ValueError('Transport hash mismatch')
    decoder=lzma.LZMADecompressor(memlimit=128*1024*1024);raw=decoder.decompress(packed,max_length=500001)
    if len(raw)>500000 or not decoder.eof or decoder.unused_data:raise ValueError('Invalid transport')
    payload=json.loads(raw)
    if payload['schema']!=1 or payload['base_commit']!='97406ee25c3bc8cfc0c1a135abf43db4884e467f':raise ValueError('Unexpected predecessor')
    files=payload['files']
    if len(files)!=len(ALLOW) or {f['path'] for f in files}!=ALLOW:raise ValueError('Unexpected path set')
    ready=[]
    for item in files:
        target=ROOT/item['path']
        if target.is_symlink() or any(p.is_symlink() for p in target.parents if p!=ROOT.parent):raise ValueError('Symlink prohibited')
        prior=target.read_bytes() if target.exists() else None
        before=hashlib.sha256(prior).hexdigest() if prior is not None else None
        if before==item['sha256'] or (item['path']=='web/conversation.js' and before==FIXED):continue
        if before!=item['before']:raise ValueError('Predecessor mismatch: '+item['path'])
        if 'text' in item:value=item['text'].encode('utf-8')
        else:
            lines=prior.decode().splitlines(keepends=True);last=0
            for start,end,replacement in item['edits']:
                if type(start) is not int or type(end) is not int or not last<=start<=end<=len(lines) or not all(type(x) is str for x in replacement):raise ValueError('Invalid edit')
                last=end
            for start,end,replacement in reversed(item['edits']):lines[start:end]=replacement
            value=''.join(lines).encode()
        if hashlib.sha256(value).hexdigest()!=item['sha256']:raise ValueError('Result hash mismatch: '+item['path'])
        ready.append((target,value))
    for target,value in ready:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(value)
    # Reviewed correction from real browser acceptance: clearing server state must
    # also clear the displayed turns, including equal null/empty subsequent results.
    target=ROOT/'web/conversation.js';value=target.read_text()
    digest=hashlib.sha256(value.encode()).hexdigest()
    if digest!=FIXED:
        if digest!='53d0243ad8191e93441191274bdd357be0faced6afcbcee2ce80ac87a513c77e':raise ValueError('Unexpected UI predecessor')
        value=value.replace('state.id=select.value;state.data=null;state.last=0;state.epoch++;state.loading=false;load();','state.id=select.value;state.data=null;state.last=0;state.epoch++;state.loading=false;renderTurns();load();')
        old="const forget=button('Forget this conversation','text-button',()=>act(async()=>{if(!state.id||!confirm('Remove this conversation? Existing drafts and audit records are not undone.'))return;await api('/desk/conversations/'+state.id+'/forget',{});state.epoch++;state.loading=false;state.id=null;state.data=null;state.last=0;await load();}));forget.id='conversation-forget';"
        value=value.replace(old,"const forget=button('Forget this conversation','text-button',()=>act(forgetConversation));forget.id='conversation-forget';")
        value=value.replace('  async function newConversation(){',"""  async function forgetConversation(){
    const id=state.id;
    if(!id||!confirm('Remove this conversation? Existing drafts and audit records are not undone.'))return;
    const e=++state.epoch,g=ui.generation;state.loading=false;state.busy=true;controls();
    try{
      await api('/desk/conversations/'+id+'/forget',{});if(!alive(e,g))return;
      state.id=null;state.data=null;state.last=0;renderTurns();await load();
    }finally{if(alive(e,g)){state.busy=false;controls();}}
  }
  async function newConversation(){""")
        value=value.replace('state.id=result.id;state.data=result;state.last=0;await load();','state.id=result.id;state.data=result;state.last=0;renderTurns();await load();')
        if hashlib.sha256(value.encode()).hexdigest()!=FIXED:raise ValueError('Corrected UI hash mismatch')
        target.write_text(value)
    print('Materialised',len(ready),'verified first-party files and reviewed empty-thread correction; no upstream code executed.')
if __name__=='__main__':main()
