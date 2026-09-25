'use strict';
// Extends the existing Desk UI. All note text is untrusted and rendered as text.
// No CDN, embeddings, model call, vault modification or browser persistence.
(() => {
  names.knowledge='Your knowledge. Connected.';
  descriptions.knowledge='A local map of your notes, projects and decisions. Follow the source, not a guess.';
  const state={data:null,root:null,query:'',kind:'',selected:null,epoch:0,loading:false,last:0,mode:'graph',scope:null};
  const kinds=['map','project','person','decision','procedure','note'];
  const label={map:'Maps',project:'Projects',person:'People',decision:'Decisions',procedure:'Procedures',note:'Notes'};
  const originalRender=renderContent,originalOut=signedOut;
  let searchTimer;
  function valid(epoch,generation){return epoch===state.epoch&&generation===ui.generation&&ui.csrf&&ui.view==='knowledge';}
  function reset(){state.epoch++;state.data=null;state.root=null;state.scope=null;state.selected=null;state.query='';state.kind='';state.loading=false;state.last=0;clearTimeout(searchTimer);}
  signedOut=function(){reset();originalOut();};
  renderContent=function(){
    if(ui.view!=='knowledge'){if(state.root){state.epoch++;state.root=null;state.loading=false;}return originalRender();}
    const root=$('view-content');
    if(state.scope!==ui.state?.scope){reset();state.scope=ui.state?.scope;}
    if(state.root!==root||!root.querySelector('.knowledge-shell'))mount(root);
    if(Date.now()-state.last>2500&&!state.loading)load();
  };
  function mount(root){
    state.root=root;root.replaceChildren();
    const shell=node('div','knowledge-shell'),bar=node('div','knowledge-toolbar');
    const search=node('input','knowledge-search');search.type='search';search.placeholder='Search your knowledge...';search.id='knowledge-query';search.setAttribute('aria-label','Search notes');search.value=state.query;
    search.addEventListener('input',()=>{state.query=search.value;clearTimeout(searchTimer);searchTimer=setTimeout(()=>load(true),250);});
    const select=node('select','knowledge-kind');select.setAttribute('aria-label','Filter note kind');
    [['','All types'],...kinds.map(k=>[k,label[k]])].forEach(([value,title])=>{const opt=node('option','',title);opt.value=value;select.append(opt);});select.value=state.kind;
    select.addEventListener('change',()=>{state.kind=select.value;load(true);});
    const views=node('div','knowledge-toggles');
    for(const [mode,title] of [['graph','Map'],['list','Notes']]){const b=button(title,'outline',()=>{state.mode=mode;renderData();});b.dataset.mode=mode;views.append(b);}
    bar.append(search,select,views);
    const status=node('p','status-line');status.id='knowledge-status';status.setAttribute('role','status');
    const metrics=node('div','knowledge-metrics');metrics.id='knowledge-metrics';
    const grid=node('div','knowledge-grid'),main=node('section','knowledge-main'),canvas=node('div','knowledge-canvas'),inspector=node('aside','knowledge-inspector');
    canvas.id='knowledge-canvas';inspector.id='knowledge-inspector';inspector.setAttribute('aria-live','polite');
    const graphTop=node('div','knowledge-graph-top');graphTop.append(node('div','', 'KNOWLEDGE MAP'),node('small','','YOUR FILES · YOUR CONNECTIONS'));
    const legend=node('div','knowledge-legend');kinds.forEach(k=>{const e=node('span','legend-'+k,label[k]);legend.append(e);});
    main.append(graphTop,canvas,legend);
    grid.append(main,inspector);
    const health=node('section','knowledge-health');health.id='knowledge-health';
    shell.append(bar,status,metrics,grid,health,node('p','knowledge-disclaimer','Read-only index. A link records an authored reference, not a verified fact. No note content is sent to an AI provider.'));
    root.append(shell);renderData();
  }
  async function load(force=false){
    if(!ui.connected){$('knowledge-status').textContent='Disconnected. This is a cached knowledge view.';return;}
    if(state.loading&&!force)return;
    const epoch=++state.epoch,generation=ui.generation;state.loading=true;
    try{
      const data=await api('/desk/knowledge?q='+encodeURIComponent(state.query)+'&kind='+encodeURIComponent(state.kind));
      if(!valid(epoch,generation))return;
      state.data=data;state.last=Date.now();
      if(state.selected&&!data.nodes.some(n=>n.id===state.selected)){state.selected=null;$('knowledge-inspector').replaceChildren();}
      renderData();
    }catch(e){if(valid(epoch,generation)){$('knowledge-status').textContent=errorText(e);state.last=Date.now();}}
    finally{if(epoch===state.epoch)state.loading=false;}
  }
  function renderData(){
    const root=state.root;if(!root||!root.querySelector('.knowledge-shell'))return;
    root.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===state.mode)));
    const d=state.data;
    if(!d){$('knowledge-canvas').replaceChildren(empty('Opening your knowledge','Reading the local index. No model is involved.'));$('knowledge-inspector').replaceChildren(empty('Every connection has a source','Choose a note to inspect its original text, file hash and links.'));return;}
    const checks=d.sources.map(s=>s.checked);const recent=checks.length?Math.max(...checks):null;
    $('knowledge-status').textContent=(d.paused?'Indexing paused. ':ui.connected?'Local index connected. ':'Disconnected. Cached view. ')+d.counts.matches+' matching notes · checked '+(recent?when(recent):'not yet')+'.';
    const metrics=$('knowledge-metrics');metrics.replaceChildren();
    [['Notes in this workspace',d.counts.notes,'Canonical Markdown files'],['Source-linked connections',d.counts.links,'Explicit references only'],['Links to review',d.counts.issues,'Missing, ambiguous or blocked']].forEach(([title,value,caption])=>{const el=node('div','knowledge-metric');el.append(node('span','',title),node('strong','',String(value).padStart(2,'0')),node('small','',caption));metrics.append(el);});
    const canvas=$('knowledge-canvas');canvas.replaceChildren();
    if(!d.sources.length){canvas.append(empty('Connect a Markdown folder','Launch the desk with --vault /path/to/folder, or seed the supplied fictional vault. No private notes have been connected.'));}
    else if(!d.results.length){canvas.append(empty('No matching notes','Try another search or type. Unavailable and removed notes are not returned.'));}
    else if(state.mode==='list')drawList(canvas,d.results);
    else drawGraph(canvas,d);
    if(!state.selected||!$('knowledge-inspector').children.length)inspectIntro();
    renderHealth(d);
  }
  function drawList(root,notes){
    const list=node('div','knowledge-list');
    notes.forEach(n=>{const b=button('','knowledge-note-row',()=>inspect(n.id));b.append(node('span','note-kind kind-'+n.kind,n.kind),node('strong','',n.title),node('small','',n.path),node('p','',n.snippet));b.setAttribute('aria-label','Open note '+n.title);list.append(b);});root.append(list);
  }
  function svg(tag,attrs={},value){const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,String(v));if(value!==undefined)el.textContent=value;return el;}
  function drawGraph(root,data){
    const visible=data.results.slice(0,96),ids=new Set(visible.map(n=>n.id));
    const el=svg('svg',{viewBox:'0 0 860 530',class:'knowledge-svg',role:'group','aria-label':'Linked Markdown notes. Select a node to inspect its source.'});
    const centres={map:[410,265],project:[650,150],person:[635,390],decision:[235,380],procedure:[195,135],note:[440,465]};
    const positions={};
    kinds.forEach(k=>{const group=visible.filter(n=>n.kind===k),centre=centres[k];group.forEach((n,i)=>{const angle=2*Math.PI*i/Math.max(group.length,1)-Math.PI/2;const radius=group.length===1?0:Math.min(80,38+group.length*6);positions[n.id]=[centre[0]+Math.cos(angle)*radius,centre[1]+Math.sin(angle)*radius];});});
    const related=new Set([state.selected]);data.links.filter(l=>l.source===state.selected||l.target===state.selected).forEach(l=>{related.add(l.source);related.add(l.target);});
    for(const l of data.links){if(!ids.has(l.source)||!ids.has(l.target)||l.source===l.target)continue;const [x1,y1]=positions[l.source],[x2,y2]=positions[l.target];const active=state.selected&&(l.source===state.selected||l.target===state.selected);const line=svg('line',{x1,y1,x2,y2,class:'knowledge-edge'+(active?' active':'')});line.append(svg('title',{},l.relation+' · source line '+l.line));el.append(line);}
    for(const n of visible){const [x,y]=positions[n.id];const count=data.links.filter(l=>l.source===n.id||l.target===n.id).length;const g=svg('g',{class:'knowledge-node kind-'+n.kind+(n.id===state.selected?' selected':'')+(state.selected&&!related.has(n.id)?' muted':''),transform:'translate('+x+','+y+')',role:'button',tabindex:0,'aria-label':'Open note '+n.title});
      g.append(svg('circle',{r:Math.min(14,6+count)}),svg('text',{y:27,'text-anchor':'middle'},n.title.length>24?n.title.slice(0,22)+'…':n.title),svg('title',{},n.path));g.addEventListener('click',()=>inspect(n.id));g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();inspect(n.id);}});el.append(g);
    }
    root.append(el);if(data.results.length>96)root.append(node('p','status-line','Showing the first 96 matching notes in the map. Use search or Notes to inspect the rest.'));
  }
  function inspectIntro(){const panel=$('knowledge-inspector');panel.replaceChildren();panel.append(node('div','knowledge-orbit','⌬'),node('p','eyebrow','FOLLOW THE CONNECTION'),node('h3','','Not just stored. Understood in context.'),node('p','','Select any note to see what it links to, what links back, and the exact text behind the connection.'),node('div','knowledge-small-card','Files are the source. The graph is a rebuildable view. No inferred relationships are added.'));
  }
  async function inspect(id){
    state.selected=id;const generation=ui.generation;const selected=id;
    const panel=$('knowledge-inspector');panel.replaceChildren(node('p','status-line','Reading source...'));if(state.mode==='graph'){$('knowledge-canvas').replaceChildren();drawGraph($('knowledge-canvas'),state.data);}
    try{
      const n=await api('/desk/knowledge/notes/'+id);
      if(generation!==ui.generation||state.selected!==selected||ui.view!=='knowledge')return;
      panel.replaceChildren();panel.append(node('p','eyebrow',n.kind.toUpperCase()+' / LOCAL NOTE'),node('h3','',n.title),node('p','knowledge-path',n.path),node('small','', 'Revision '+n.revision+' · indexed '+when(n.indexed)));
      const details=node('details','knowledge-proof');details.append(node('summary','','Source identity'),node('p','mono','SHA-256: '+n.sha256),node('p','accessible-note','This hash identifies the indexed file bytes. It does not establish that the note is true.'));panel.append(details);
      const connections=node('div','knowledge-connections');connections.append(node('h4','','Connected notes'));
      const links=state.data.links.filter(l=>l.source===id||l.target===id);const seen=new Set();
      for(const link of links){const target=link.source===id?link.target:link.source;const key=target+':'+(link.source===id?'out':'in');if(seen.has(key))continue;seen.add(key);const peer=state.data.nodes.find(v=>v.id===target);if(!peer)continue;const b=button((link.source===id?'↗ ':'↙ ')+peer.title,'knowledge-connection',()=>inspect(target));b.append(node('small','',(link.source===id?'Referenced at line ':'Backlink, source line ')+link.line));connections.append(b);}
      if(!links.length)connections.append(node('p','accessible-note','No resolved links in this indexed revision.'));panel.append(connections);
      const full=button('Read source text','outline full',()=>openText(n));panel.append(full,node('p','knowledge-disclaimer','Authored note, not a verified observation.'));
    }catch(e){if(generation===ui.generation&&state.selected===id)panel.replaceChildren(node('p','error',errorText(e)));}
  }
  function openText(n){setDialog('KNOWLEDGE / SOURCE TEXT');const root=$('detail-body');root.replaceChildren();const heading=node('h2','',n.title);heading.id='detail-title';root.append(heading,node('p','knowledge-path',n.path+' · revision '+n.revision),node('p','mono','SHA-256 '+n.sha256));const pre=node('pre','knowledge-source');pre.textContent=n.body.split('\n').map((line,i)=>String(i+1).padStart(3,' ')+'  '+line).join('\n');root.append(pre,node('p','accessible-note','Showing the indexed snapshot. Edits happen in your original Markdown editor, not in this view.'));if(!$('detail').open)$('detail').showModal();}
  function renderHealth(d){
    const root=$('knowledge-health');root.replaceChildren();const header=sectionTop('Memory health','CHECKED FROM THE FILES');root.append(header);
    const health=d.map_health;const summary=node('div','knowledge-health-summary');
    summary.append(badge(d.counts.issues?'Needs review':'Links resolved',Boolean(d.counts.issues)),node('span','',health.outside_two_hops.length+' notes outside two hops of MAP.md'),node('span','',health.missing_map_sources.length+' sources without MAP.md'));root.append(summary);
    for(const source of d.sources){for(const e of source.errors||[])root.append(node('p','warning',(e.path?e.path+': ':'')+pretty(e.code)));}
    d.issues.slice(0,12).forEach(i=>{const row=node('div','knowledge-issue');row.append(badge(i.status,true),node('span','',i.target),button(i.path+' · line '+i.line,'text-button',()=>inspect(i.note)));root.append(row);});
    if(d.issues.length>12)root.append(node('p','status-line','First 12 issues shown. '+d.issues.length+' total in the index.'));
    if(!d.counts.issues)root.append(node('p','accessible-note','No unresolved file references in this snapshot. Heading and block anchors are not validated.'));
  }
})();
