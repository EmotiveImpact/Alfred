'use strict';
// Source-first question interface. Untrusted source/model text is always textContent.
// No browser persistence, ambient capture, tool execution or automatic model calls.
(() => {
  names.ask='Ask Alfred. See the evidence.';
  descriptions.ask='Bring a question to your knowledge. Follow every answer back to its source.';
  const nav=button('','',()=>selectView('ask'));nav.dataset.view='ask';nav.append(node('span','','◎'),document.createTextNode('Ask Alfred'));
  document.querySelector('[data-view=knowledge]').before(nav);
  const state={root:null,result:null,scope:null,question:'',mode:'sources',epoch:0,busy:false,checking:false,checked:0,valid:false,capability:null};
  const oldRender=renderContent,oldOut=signedOut;
  function reset(){state.epoch++;state.root=null;state.result=null;state.scope=null;state.question='';state.mode='sources';state.busy=false;state.valid=false;state.checking=false;state.capability=null;}
  signedOut=function(){reset();oldOut();};
  function active(epoch,generation){return state.epoch===epoch&&ui.generation===generation&&ui.csrf&&ui.view==='ask';}
  renderContent=function(){
    if(ui.view!=='ask'){if(state.root){state.epoch++;state.root=null;state.busy=false;}return oldRender();}
    if(state.scope!==ui.state?.scope){reset();state.scope=ui.state?.scope;}
    const root=$('view-content');
    if(state.root!==root||!root.querySelector('.ask-shell'))mount(root);
    const send=$('ask-submit');if(send)send.disabled=state.busy||!ui.connected;
    const download=$('ask-export');if(download)download.disabled=!ui.connected||!state.valid;
    if(state.result&&state.valid&&ui.connected&&Date.now()-state.checked>2500&&!state.checking)validate();
  };
  function mount(root){
    state.root=root;root.replaceChildren();
    const shell=node('section','ask-shell'),intro=node('div','ask-intro');
    intro.append(node('span','ask-orbit','◎'),node('div','', 'A question. A clear trail back to what you know.'));
    const form=node('form','ask-form');form.id='ask-form';
    const label=node('label','ask-label','What would you like to know?');label.htmlFor='ask-question';
    const field=node('input','ask-input');field.type='text';field.id='ask-question';field.maxLength=500;field.required=true;field.autocomplete='off';field.placeholder='What does the opening treatment say?';field.value=state.question;
    const controls=node('div','ask-controls'),mode=node('select','ask-mode');mode.id='ask-mode';mode.setAttribute('aria-label','Answer mode');
    for(const [value,title] of [['sources','Source excerpts · no model'],['local_model','Local model · explicitly opt in']]){const option=node('option','',title);option.value=value;if(value==='local_model')option.disabled=true;mode.append(option);}mode.value=state.mode;
    const send=node('button','primary','Find supporting sources ↗');send.type='submit';send.id='ask-submit';
    mode.addEventListener('change',()=>{state.mode=mode.value;send.textContent=state.mode==='sources'?'Find supporting sources ↗':'Ask configured local model ↗';});
    controls.append(mode,send);form.append(label,field,controls);
    form.addEventListener('submit',e=>{e.preventDefault();state.question=field.value;state.mode=mode.value;submit();});
    const examples=node('div','ask-examples');for(const q of ['Opening treatment','ALFRED permissions','Production decisions'])examples.append(button(q,'outline',()=>{field.value=q;state.question=q;submit();}));
    const status=node('p','ask-status','Source mode reads excerpts. It does not pretend a model is connected.');status.id='ask-status';status.setAttribute('role','status');
    const results=node('div','ask-results');results.id='ask-results';
    const boundary=node('div','ask-boundary');boundary.append(node('strong','','Your notes stay in charge.'),node('p','','The graph helps find connected material. Source files remain canonical. A model interpretation never becomes a permission, a verified fact or a completed action.'));
    shell.append(intro,form,examples,status,results,boundary);root.append(shell);draw();
    const epoch=state.epoch,generation=ui.generation;
    api('/desk/ask/status').then(value=>{if(!active(epoch,generation))return;state.capability=value;const allowed=value.local_model_configured&&value.model_allowed;mode.querySelector('option[value=local_model]').disabled=!allowed;if(!allowed){mode.value='sources';state.mode='sources';}if(!state.result)$('ask-status').textContent=allowed?'Local model configured: '+value.model+'. Only an explicit model request sends selected excerpts.':'Source mode active. No model is configured; excerpts and graph navigation work offline.';}).catch(e=>{if(active(epoch,generation))$('ask-status').textContent=errorText(e);});
  }
  async function submit(){
    if(state.busy||!ui.connected)return;
    const question=$('ask-question').value.trim();if(question.length<3){showToast('Enter a question or a few specific keywords.');return;}
    state.question=question;state.result=null;state.valid=false;state.busy=true;const epoch=++state.epoch,generation=ui.generation;
    $('ask-submit').disabled=true;$('ask-results').replaceChildren();$('ask-status').textContent=state.mode==='sources'?'Finding relevant notes and their explicit connections...':'Sending the selected source packet to the configured local model...';
    try{const result=await api('/desk/ask',{question,mode:state.mode});if(!active(epoch,generation))return;state.result=result;state.valid=true;state.checked=Date.now();draw();}
    catch(e){if(active(epoch,generation)){$('ask-status').textContent=errorText(e);state.result=null;draw();}}
    finally{if(active(epoch,generation)){state.busy=false;$('ask-submit').disabled=!ui.connected;}}
  }
  async function validate(){
    const result=state.result;if(!result||!result.packet.evidence.length)return;state.checking=true;state.checked=Date.now();
    const epoch=state.epoch,generation=ui.generation;
    try{const refs=result.packet.evidence.map(({note_id,sha256,revision})=>({note_id,sha256,revision}));const check=await api('/desk/ask/check',{references:refs});if(!active(epoch,generation)||state.result!==result)return;if(!check.current_index_match){state.valid=false;state.result={...result,claims:[],packet:{...result.packet,evidence:[]},export_markdown:''};if($('detail-eyebrow').textContent.startsWith('ASK /')){$('detail').close();$('detail-body').replaceChildren();}draw();}}
    catch(e){if(active(epoch,generation)){$('ask-status').textContent='Source validation unavailable. Do not treat this cached result as current.';const b=$('ask-export');if(b)b.disabled=true;}}
    finally{state.checking=false;}
  }
  function draw(){
    const root=$('ask-results');if(!root)return;root.replaceChildren();const r=state.result;
    if(!r){root.append(empty('Knowledge you can inspect','Ask about your notes. This release finds source passages and follows explicit links; a graph alone does not establish an answer.'));return;}
    if(!state.valid){$('ask-status').textContent='A source changed or became unavailable. Run the question again.';root.append(node('div','warning','Previous excerpts and interpretations have been cleared. The stored index no longer matches their citations.'));return;}
    const labels={sources_found:'Supporting excerpts, not an AI-generated answer.',no_sources:'No supporting notes found. Nothing has been invented.',model_interpretation:'Model interpretation. Citations checked; factual entailment is not verified.',model_abstained:'The local model could not establish an answer from these excerpts.',model_unavailable_or_invalid:'The local model failed or returned invalid citations. No generated answer is shown.'};
    $('ask-status').textContent=labels[r.status]||r.status;
    const top=node('div','ask-result-top');top.append(badge(r.model_used?'MODEL INTERPRETATION':'SOURCE MODE'),node('span','ask-result-count',r.packet.evidence.length+' sources · indexed snapshot'));
    if(r.packet.evidence.length){const b=button('Export evidence .md','outline',download);b.id='ask-export';b.disabled=!ui.connected;top.append(b);}root.append(top);
    if(r.claims.length){const generated=node('section','ask-generated');generated.append(node('h2','','An interpretation, with references'),node('p','accessible-note','Generated by '+r.model+'. Verify the cited passages before relying on this. No action was taken.'));r.claims.forEach(c=>{const row=node('article','ask-claim');row.append(node('p','',c.text));const refs=node('div','ask-citations');c.citations.forEach(cite=>{const src=r.packet.evidence.find(s=>s.source_id===cite.source_id);refs.append(button(cite.source_id+' · lines '+cite.start_line+' to '+cite.end_line,'outline',()=>openSource(src)));});row.append(refs);generated.append(row);});root.append(generated);}
    if(!r.packet.evidence.length){root.append(empty('The selected sources do not establish an answer','Use different keywords or connect an authorised note source. This is not evidence that the answer does not exist elsewhere.'));return;}
    const grid=node('div','ask-source-grid');r.packet.evidence.forEach(s=>{const card=node('article','ask-source-card'),head=node('div','ask-source-head');head.append(badge(s.source_id),node('span','',s.kind));card.append(head,node('h3','',s.title),node('p','ask-source-path',s.path+' · lines '+s.start_line+' to '+s.end_line),node('pre','ask-excerpt',s.excerpt),node('p','ask-provenance',(s.retrieved_via==='keyword_match'?'Keyword match':'Connected by an explicit note link')+' · revision '+s.revision),button(s.source_id+' · Open source','text-button',()=>openSource(s)));grid.append(card);});root.append(grid);
  }
  async function openSource(source){
    await act(async()=>{const epoch=state.epoch,generation=ui.generation;const note=await api('/desk/knowledge/notes/'+source.note_id);if(!active(epoch,generation))return;if(note.sha256!==source.sha256){await validate();showToast('The source changed. Run the question again.');return;}const body=setDialog('ASK / SOURCE EVIDENCE');const title=node('h2','dialog-title',note.title);title.id='detail-title';body.append(title,node('p','ask-source-path',note.path+' · revision '+note.revision),node('p','mono','SHA-256 '+note.sha256),node('pre','knowledge-source',note.body.split('\n').map((line,i)=>String(i+1).padStart(3,' ')+'  '+line).join('\n')));});
  }
  function download(){if(!state.result||!state.valid||!ui.connected)return;const url=URL.createObjectURL(new Blob([state.result.export_markdown],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='ALFRED-evidence-packet.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
})();
