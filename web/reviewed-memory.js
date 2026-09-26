'use strict';
// Explicitly reviewed memory, not automatic extraction or execution authority.
(() => {
  const state={epoch:0,last:0,loading:false,data:null,signature:null,inspected:null};
  names['reviewed-memory']='What you choose to remember.';
  descriptions['reviewed-memory']='People, projects and decisions, connected to the evidence you reviewed.';
  const priorRender=renderContent,priorOut=signedOut;
  function reset(){state.epoch++;state.last=0;state.loading=false;state.data=null;state.signature=null;state.inspected=null;}
  signedOut=function(){reset();priorOut();};
  renderContent=function(){
    if(ui.view!=='reviewed-memory')return priorRender();
    const root=$('view-content');
    if(!root.querySelector('.reviewed-memory')){reset();root.replaceChildren();const shell=node('section','reviewed-memory');
      const tools=node('div','memory-toolbar');tools.append(button('New entity','outline',()=>act(entityDialog)),button('Propose a statement','primary',()=>act(proposalDialog)),button('Export reviewed memory','text-button',()=>act(exportMemory)));
      tools.querySelectorAll('button').forEach((b,i)=>b.id=['memory-new-entity','memory-propose','memory-export'][i]);
      const status=node('p','status-line','Reading your reviewed memory…');status.id='memory-status';status.setAttribute('role','status');
      const body=node('div');body.id='memory-records';shell.append(tools,status,body,node('p','memory-limit','Private to this access key. Acceptance records your judgement, not verified truth. Notes remain unchanged.'));root.append(shell);
    }
    root.querySelectorAll('.memory-toolbar button').forEach(b=>b.disabled=!ui.connected||Boolean(window.ALFRED_PREVIEW)||(b.id!=='memory-export'&&ui.state.role!=='owner'));
    if(ui.connected&&!state.loading&&Date.now()-state.last>2000)load();
  };
  function alive(e,g){return e===state.epoch&&g===ui.generation&&ui.csrf&&ui.view==='reviewed-memory';}
  async function load(){state.loading=true;const e=state.epoch,g=ui.generation;
    try{const data=await api('/desk/memory');if(!alive(e,g))return;state.data=data;state.last=Date.now();
      const signature=JSON.stringify(data);if(signature!==state.signature){state.signature=signature;draw(data);}
    }catch(error){if(alive(e,g))$('memory-status').textContent=errorText(error);}finally{if(alive(e,g))state.loading=false;}
  }
  function name(id){return state.data?.entities.find(x=>x.id===id)?.name||id;}
  function draw(data){const root=$('memory-records');root.replaceChildren();
    if(state.inspected&&$('detail').open){const current=data.claims.find(c=>c.id===state.inspected.id);if(!current||!current.source||current.version!==state.inspected.version){$('detail').close();$('detail-body').replaceChildren();state.inspected=null;showToast('That statement or its evidence changed. Open the current record again.');}}
    $('memory-status').textContent=data.counts.usable+' current reviewed statements · '+data.counts.proposed+' awaiting review'+(data.counts.conflicted?' · '+data.counts.conflicted+' conflicting records':'');
    const entities=node('div','memory-entities');for(const entity of data.entities){const item=node('div','memory-entity');item.append(node('strong','',entity.name),node('small','',pretty(entity.kind)+' · '+entity.id));entities.append(item);}root.append(entities);
    if(!data.claims.length)root.append(empty('Build memory deliberately','Create an entity, then propose a statement with the exact source lines. A note link alone is not a fact.'));
    for(const c of data.claims){const row=node('article','memory-claim');row.dataset.claimId=c.id;
      row.append(node('div','memory-claim-state',pretty(c.state)+(c.conflicts.length?' / conflict to resolve':'')+(!c.valid_now?' / outside validity period':'')));
      const heading=node('h2','',name(c.subject_id)+' · '+pretty(c.predicate));row.append(heading,node('p','memory-value',c.value|| (c.object_id?name(c.object_id):'Statement removed because its evidence is no longer current.')));
      if(c.source){const s=c.source;row.append(node('blockquote','memory-quote',s.quote));const source=button(s.path+' · lines '+s.start_line+'–'+s.end_line,'text-button',()=>inspect(c));source.dataset.sourceId=s.note_id;row.append(source);}
      row.append(node('small','',c.usable?'Available in the reviewed graph. No action permission is implied.':c.conflicts.length?'Competing accepted statements are excluded from the current graph.':'Not a current accepted statement.'));
      if(ui.state.role==='owner'&&['proposed','accepted','disputed'].includes(c.state)){
        const actions=node('div','memory-actions');
        for(const [op,label] of [['accept','Accept statement'],['dispute','Dispute'],['withdraw','Withdraw']]){const b=button(label,'outline',()=>act(()=>reviewDialog(c,op)));b.dataset.review=op;b.disabled=!ui.connected||Boolean(window.ALFRED_PREVIEW);actions.append(b);}
        const alternatives=data.claims.filter(x=>x.id!==c.id&&x.subject_id===c.subject_id&&x.predicate===c.predicate&&['accepted','disputed','invalidated'].includes(x.state));
        if(alternatives.length){const b=button('Replace an earlier statement','text-button',()=>reviewDialog(c,'supersede',alternatives));b.dataset.review='supersede';b.disabled=!ui.connected||Boolean(window.ALFRED_PREVIEW);actions.append(b);}row.append(actions);
      }root.append(row);
    }
    const graph=node('details','memory-graph');graph.append(node('summary','','Reviewed connections ('+data.graph.edges.length+')'));
    for(const edge of data.graph.edges)graph.append(node('p','',name(edge.source)+' → '+pretty(edge.predicate)+' → '+name(edge.target)));
    if(!data.graph.edges.length)graph.append(node('p','','Accepted, current, unconflicted entity relationships appear here. The original note graph is unchanged.'));root.append(graph);
  }
  function field(form,labelText,id,type='text'){const label=node('label','',labelText);const input=node('input');input.id=id;input.type=type;label.htmlFor=id;form.append(label,input);return input;}
  function select(form,labelText,id,options){const label=node('label','',labelText),input=node('select');label.htmlFor=id;input.id=id;for(const [v,t]of options){const o=node('option','',t);o.value=v;input.append(o);}form.append(label,input);return input;}
  function dialog(title){state.inspected=null;const body=setDialog('REVIEWED MEMORY');const h=node('h2','dialog-title',title);h.id='detail-title';body.append(h);return body;}
  async function entityDialog(){const body=dialog('Give this entity its own identity.'),form=node('form','memory-form');
    const input=field(form,'Name','memory-entity-name');input.required=true;input.maxLength=120;
    const kind=select(form,'Kind','memory-entity-kind',['person','organisation','project','asset','decision','commitment','event'].map(x=>[x,pretty(x)]));
    const submit=node('button','primary','Create entity');submit.type='submit';form.append(node('p','hint','Identical names remain separate entities. Names never grant access.'),submit);body.append(form);
    form.addEventListener('submit',e=>{e.preventDefault();act(async()=>{submit.disabled=true;try{await api('/desk/memory/entities',{id:'entity-'+crypto.randomUUID(),name:input.value,kind:kind.value});$('detail').close();await load();}finally{submit.disabled=false;}});});input.focus();
  }
  async function proposalDialog(){
    if(!state.data?.entities.length){showToast('Create an entity first.');return;}
    const e=state.epoch,g=ui.generation;const graph=await api('/desk/knowledge');if(!alive(e,g))return;
    if(!graph.nodes.length){showToast('Connect an indexed Markdown source first.');return;}
    const body=dialog('Propose a source-backed statement.'),form=node('form','memory-form');let note=null;let serial=0;
    const entities=state.data.entities;
    const subject=select(form,'About','memory-subject',entities.map(x=>[x.id,x.name+' · '+x.id]));
    const predicate=select(form,'Relationship','memory-predicate',['responsible_person','depends_on','status','scheduled_for','decision'].map(x=>[x,pretty(x)]));
    const object=select(form,'Related entity','memory-object',entities.map(x=>[x.id,x.name+' · '+x.id]));
    const value=field(form,'Statement value','memory-value');value.maxLength=400;
    function relation(){const related=['responsible_person','depends_on'].includes(predicate.value);object.disabled=!related;value.disabled=related;value.required=!related;}
    predicate.addEventListener('change',relation);relation();
    const source=select(form,'Evidence note','memory-note',graph.nodes.map(x=>[x.id,x.path]));
    const first=field(form,'First supporting line','memory-first','number'),last=field(form,'Last supporting line','memory-last','number');first.value='1';last.value='1';first.min=last.min='1';first.required=last.required=true;
    const preview=node('pre','memory-note-text','Loading source…');preview.id='memory-note-text';form.append(preview);
    const submit=node('button','primary','Save proposal for review');submit.type='submit';submit.disabled=true;form.append(node('p','hint','Nothing is accepted automatically. Select at most eight exact supporting lines. This form creates no device or account permissions.'),submit);body.append(form);
    async function read(){const ticket=++serial;note=null;submit.disabled=true;try{const n=await api('/desk/knowledge/notes/'+source.value);if(ticket!==serial||!form.isConnected)return;note=n;preview.textContent=n.body.split(/\r?\n/).map((l,i)=>(i+1)+'  '+l).join('\n');submit.disabled=false;}catch(error){if(form.isConnected)preview.textContent=errorText(error);}}
    source.addEventListener('change',read);await read();
    const request='memory-'+crypto.randomUUID();form.addEventListener('submit',ev=>{ev.preventDefault();act(async()=>{if(!note)return;submit.disabled=true;try{await api('/desk/memory/proposals',{request_id:request,subject_id:subject.value,predicate:predicate.value,object_id:object.disabled?null:object.value,value:value.disabled?null:value.value,valid_from:null,valid_until:null,evidence:{note_id:note.id,sha256:note.sha256,revision:note.revision,start_line:Number(first.value),end_line:Number(last.value)}});$('detail').close();await load();}finally{submit.disabled=false;}});});
  }
  function inspect(c){const body=dialog('The evidence behind this statement.');state.inspected={id:c.id,version:c.version};body.append(node('p','detail-summary',c.source.path),node('pre','memory-note-text',c.source.quote),node('p','hint','Source SHA-256: '+c.source.sha256),node('p','hint','Review: '+c.state+' · version '+c.version+' · reviewer '+(c.reviewer||'not reviewed')));}
  function reviewDialog(c,decision,alternatives=[]){const body=dialog(decision==='supersede'?'Replace a previous statement?':pretty(decision)+' this statement?');state.inspected={id:c.id,version:c.version};body.append(node('p','detail-summary',name(c.subject_id)+' · '+pretty(c.predicate)+' · '+(c.value||name(c.object_id))),node('blockquote','memory-quote',c.source?.quote||''));
    body.append(node('p','hint','Review records your judgement. It does not independently verify the claim or grant permission. Competing accepted values remain a visible conflict.'));
    const choices=alternatives.length?select(body,'Earlier statement to replace','memory-replaces',alternatives.map(x=>[x.id,(x.value||name(x.object_id)||'Invalidated')+' · '+x.id])):null;
    const b=button('Confirm '+decision,'primary',()=>act(async()=>{b.disabled=true;try{const prior=choices?alternatives.find(x=>x.id===choices.value):null;await api('/desk/memory/claims/'+c.id+'/review',{version:c.version,decision,replaces_id:prior?.id||null,replaces_version:prior?.version||null});$('detail').close();await load();}finally{b.disabled=false;}}));b.id='memory-review-confirm';body.append(b);
  }
  async function exportMemory(){const data=await api('/desk/memory/export');const blob=new Blob([JSON.stringify({schema:1,...data},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='ALFRED-reviewed-memory.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  // A separate, deliberate lifecycle operation, not another execution capability.
  const pulseRender=renderContent;
  renderContent=function(){pulseRender();if(ui.view!=='pulse'||!$('routine-history')||$('pulse-history-manage'))return;const b=button('Manage retained reports','text-button',()=>act(async()=>{const plan=await api('/desk/pulse/history');const body=dialog('Retain receipts, remove older reports.');body.append(node('p','detail-summary',plan.eligible+' report summaries can be removed.'),node('p','hint','The latest 64 records, the rolling 24 hours and active runs are kept. Compact retry receipts remain. This does not change schedules or securely erase database backups.'));
    const confirm=button('Remove '+plan.eligible+' older reports','primary',()=>act(async()=>{await api('/desk/pulse/history',{fingerprint:plan.fingerprint});$('detail').close();showToast('Older report summaries removed. Retry receipts retained.');selectView('pulse');}));confirm.id='pulse-history-confirm';confirm.disabled=!plan.can_prune;body.append(confirm);}));b.id='pulse-history-manage';b.disabled=ui.state.role!=='owner'||!ui.connected||Boolean(window.ALFRED_PREVIEW);$('view-content').append(b);};
})();
