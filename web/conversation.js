'use strict';
// Saved conversations use server-scoped storage; no localStorage or model tools.
(() => {
  const state={id:null,data:null,list:[],capability:null,root:null,epoch:0,loading:false,busy:false,last:0};
  const priorRender=renderContent,priorOut=signedOut;
  const alive=(e,g)=>e===state.epoch&&g===ui.generation&&ui.csrf&&ui.view==='conversation';
  function reset(){state.epoch++;state.id=null;state.data=null;state.list=[];state.capability=null;state.root=null;state.loading=false;state.busy=false;state.last=0;}
  signedOut=function(){reset();priorOut();};
  renderContent=function(){
    if(ui.view!=='conversation'){if(state.root){state.epoch++;state.root=null;state.loading=false;}return priorRender();}
    if(!state.root||!$('view-content').querySelector('.conversation-shell'))mount();
    if(ui.connected&&!state.loading&&Date.now()-state.last>900)load();
    controls();
  };
  function mount(){
    state.root=$('view-content');state.root.replaceChildren();
    const shell=node('section','conversation-shell'),top=node('div','conversation-toolbar');
    const select=node('select','conversation-select');select.id='conversation-select';select.setAttribute('aria-label','Saved conversation');select.addEventListener('change',()=>{state.id=select.value;state.data=null;state.last=0;state.epoch++;state.loading=false;renderTurns();load();});
    const fresh=button('New conversation','outline',()=>act(newConversation));fresh.id='conversation-new';
    const forget=button('Forget this conversation','text-button',()=>act(forgetConversation));forget.id='conversation-forget';
    top.append(select,fresh,forget);
    const status=node('p','status-line','Opening your conversations…');status.id='conversation-status';status.setAttribute('role','status');
    const turns=node('div','conversation-turns');turns.id='conversation-turns';turns.setAttribute('aria-live','polite');
    const form=node('form','conversation-form');form.id='conversation-form';
    const input=node('input','ask-input');input.id='conversation-question';input.maxLength=500;input.minLength=3;input.required=true;input.placeholder='Pick up a thought, ask a follow-up, make a plan…';input.autocomplete='off';input.setAttribute('aria-label','Message Alfred');
    const row=node('div','conversation-options'),label=node('label','conversation-follow'),check=node('input');check.type='checkbox';check.id='conversation-follow';check.checked=true;label.append(check,document.createTextNode('Continue this context'));
    const mode=node('select','ask-mode');mode.id='conversation-mode';mode.setAttribute('aria-label','Conversation answer mode');for(const [value,title]of [['sources','Source passages'],['local_model','Local model']]){const o=node('option','',title);o.value=value;mode.append(o);}
    const send=node('button','primary','Send ↗');send.type='submit';send.id='conversation-send';row.append(label,mode,send);form.append(input,row);
    form.addEventListener('submit',event=>{event.preventDefault();act(sendTurn);});
    shell.append(top,status,turns,form,node('p','conversation-retention','Saved locally for up to 24 hours, private to this access key. You can forget a thread. Nothing is sent or executed by a reply.'));
    state.root.append(shell);renderTurns();
  }
  async function forgetConversation(){
    const id=state.id;
    if(!id||!confirm('Remove this conversation? Existing drafts and audit records are not undone.'))return;
    const e=++state.epoch,g=ui.generation;state.loading=false;state.busy=true;controls();
    try{
      await api('/desk/conversations/'+id+'/forget',{});if(!alive(e,g))return;
      state.id=null;state.data=null;state.last=0;renderTurns();await load();
    }finally{if(alive(e,g)){state.busy=false;controls();}}
  }
  async function newConversation(){
    state.epoch++;state.loading=false;
    const e=state.epoch,g=ui.generation;const result=await api('/desk/conversations',{title:'New conversation'});if(!alive(e,g))return;
    state.id=result.id;state.data=result;state.last=0;renderTurns();await load();$('conversation-question').focus();
  }
  async function load(){
    if(state.loading)return;state.loading=true;const e=state.epoch,g=ui.generation;
    try{
      const list=await api('/desk/conversations');if(!alive(e,g))return;state.list=list.sessions;state.capability=list;
      if(!state.id||!state.list.some(s=>s.id===state.id))state.id=state.list[0]?.id||null;
      const data=state.id?await api('/desk/conversations/'+state.id):null;if(!alive(e,g))return;
      const changed=JSON.stringify(data)!==JSON.stringify(state.data);state.data=data;state.last=Date.now();
      const select=$('conversation-select');select.replaceChildren();if(!state.list.length)select.append(node('option','','No saved conversations'));
      state.list.forEach(s=>{const o=node('option','',s.title);o.value=s.id;select.append(o);});if(state.id)select.value=state.id;
      const model=$('conversation-mode').querySelector('[value=local_model]');model.disabled=!(list.model_configured&&list.model_allowed);
      if(model.disabled)$('conversation-mode').value='sources';
      if(changed)renderTurns();controls();
    }catch(error){if(alive(e,g)){$('conversation-status').textContent=errorText(error);state.last=Date.now();}}
    finally{if(alive(e,g))state.loading=false;}
  }
  function controls(){
    if(!state.root||!$('conversation-send'))return;
    const pending=state.data?.turns.some(t=>['queued','running'].includes(t.state));
    $('conversation-send').disabled=Boolean(window.ALFRED_PREVIEW)||!ui.connected||state.busy||pending||ui.state?.paused;
    $('conversation-new').disabled=Boolean(window.ALFRED_PREVIEW)||!ui.connected||state.busy;
    $('conversation-forget').disabled=Boolean(window.ALFRED_PREVIEW)||!ui.connected||!state.id;
    if(state.capability)$('conversation-status').textContent=window.ALFRED_PREVIEW?'Example conversation · read-only preview. Run the local build to start or save a conversation.':pending?'Alfred is working on this turn. You can continue using the rest of your workspace.':
      state.capability.model_configured?'Local model available: '+state.capability.model+'. Select Local model to send the relevant source excerpts.':'Source mode is available. No model is connected to this host.';
  }
  async function sendTurn(){
    if(state.busy)return;state.busy=true;controls();const question=$('conversation-question').value.trim(),mode=$('conversation-mode').value,follow=$('conversation-follow').checked;
    const e=state.epoch,g=ui.generation;
    try{
      if(!state.id){const created=await api('/desk/conversations',{title:question.slice(0,70)});if(!alive(e,g))return;state.id=created.id;state.data=created;}
      await api('/desk/conversations/'+state.id+'/turns',{question,mode,follow_up:follow,after:state.data?.turns.length||0,request_id:'ui-'+crypto.randomUUID()});
      if(!alive(e,g))return;$('conversation-question').value='';state.last=0;await load();
    }finally{if(alive(e,g)){state.busy=false;controls();}}
  }
  function renderTurns(){
    const root=$('conversation-turns');if(!root)return;root.replaceChildren();
    // Close a source modal if its turn has become unavailable.
    if($('detail-eyebrow').textContent.startsWith('CONVERSATION')&&state.data?.turns.some(t=>t.state==='source_changed')){$('detail').close();$('detail-body').replaceChildren();}
    if(!state.data?.turns.length){root.append(empty('A conversation, not a fresh start each time','Ask about your authorised notes. Follow-up questions can carry the topic forward without treating earlier model answers as facts.'));return;}
    for(const turn of state.data.turns){
      const article=node('article','conversation-turn');article.dataset.turn=turn.id;
      const q=node('div','conversation-user');q.append(node('small','','YOU'),node('p','',turn.question));article.append(q);
      const answer=node('div','conversation-answer');answer.append(node('small','',turn.result?.model_used?'ALFRED / LOCAL MODEL':'ALFRED / SOURCE MODE'));
      if(turn.result){const r=turn.result;
        if(r.claims.length){r.claims.forEach(c=>{answer.append(node('p','conversation-claim',c.text));const refs=node('div','ask-citations');c.citations.forEach(cite=>{const source=r.packet.evidence.find(s=>s.source_id===cite.source_id);refs.append(button(cite.source_id+' · '+source.title,'text-button',()=>act(()=>openSource(source))));});answer.append(refs);});answer.append(node('p','accessible-note','Model interpretation, not a verified fact. Check the sources.'));}
        else answer.append(node('p','accessible-note',r.status==='model_needs_review'?'The proposed reply did not pass the evidence checks. It has been withheld; inspect the sources below.':r.status==='no_sources'?'No supporting sources found.':r.status==='model_abstained'?'The local model could not establish an answer from the supplied sources.':'These are source passages, not an AI-generated answer.'));
        for(const source of r.packet.evidence){const details=node('details','conversation-source');const title=node('summary','',source.source_id+' · '+source.title+' · lines '+source.start_line+'–'+source.end_line);details.append(title,node('pre','ask-excerpt',source.excerpt),button('Inspect source','text-button',()=>act(()=>openSource(source))));answer.append(details);}
        if(r.packet.evidence.length&&state.data.role==='owner'){const b=button('Prepare a local draft','outline',()=>composeTurn(turn));b.disabled=!ui.connected;answer.append(b);}
      }else{const labels={queued:'Queued on this host.',running:'Reading the selected context…',source_changed:'A source changed or is no longer available. Ask again for a fresh answer.',interrupted:'The host stopped before this turn completed. It was not automatically retried.',failed:'This turn could not be completed. No unchecked answer or action was recorded.'};answer.append(node('p','accessible-note',labels[turn.state]||turn.state));}
      article.append(answer);root.append(article);
    }
  }
  async function openSource(source){const e=state.epoch,g=ui.generation;const note=await api('/desk/knowledge/notes/'+source.note_id);if(!alive(e,g))return;if(note.sha256!==source.sha256){await load();throw new Error('Source changed. Ask again.');}const root=setDialog('CONVERSATION / SOURCE');const h=node('h2','dialog-title',note.title);h.id='detail-title';root.append(h,node('p','mono','SHA-256 '+note.sha256),node('pre','knowledge-source',note.body.split('\n').map((l,i)=>(i+1)+'  '+l).join('\n')));}
  function composeTurn(turn){
    const root=setDialog('CONVERSATION / PROPOSE A DRAFT'),title=node('h2','dialog-title','Review the wording first.');title.id='detail-title';
    const input=node('textarea');input.id='conversation-draft-text';input.maxLength=4096;input.setAttribute('aria-label','Local draft text');input.value=turn.result.claims.map(c=>c.text).join(' ');
    const b=button('Review exact draft','primary',()=>act(async()=>{b.disabled=true;try{const a=await api('/desk/conversations/'+state.id+'/draft',{turn_id:turn.id,text:input.value,request_id:'chat-draft-'+crypto.randomUUID()});openApproval(a);}finally{b.disabled=false;}}));
    root.append(title,node('p','accessible-note','This creates a proposal tied to these note revisions. A separate approval is required. Nothing will be sent.'),input,b);
  }
  setInterval(()=>{if(ui.view==='conversation'&&ui.csrf&&ui.connected&&!state.loading)load();},1200);
})();
