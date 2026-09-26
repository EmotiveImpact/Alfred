'use strict';
// No model calls, microphone access, third-party scripts or browser storage.
const $ = (id) => document.getElementById(id);
const ui = {csrf: null, state: null, view: 'presence', filter: 'all', connected: false, busy: false, generation: 0, before: null};
let toastTimer;
const names = {overview:'Your briefing', evidence:'The evidence, in view.', approvals:'You decide what happens.', activity:'Every step, accounted for.', sources:'Know where it comes from.', settings:'Always under your control.'};
const descriptions = {overview:'A sourced view of your sample production. You remain in control.', evidence:'Source-linked updates with revision, freshness and acknowledgement.', approvals:'Exact proposals. Explicit approval. Local drafts only, never sent.', activity:'The latest 100 recorded events in this workspace. No hidden actions.', sources:'A read-only connection to the configured local sample-project folder.', settings:'Pause processing, inspect the current boundary or switch workspace.'};
function node(tag, className='', value) { const e=document.createElement(tag); if(className) e.className=className; if(value!==undefined) e.textContent=String(value); return e; }
function button(label, className, action) { const b=node('button',className,label); b.type='button'; b.dataset.focusKey=label; b.addEventListener('click',action); return b; }
function showToast(message) { clearTimeout(toastTimer); $('toast').textContent=message; $('toast').hidden=false; toastTimer=setTimeout(()=>$('toast').hidden=true,6500); }
function pretty(s) { return String(s || '').replaceAll('_',' ').replaceAll('.',' '); }
function when(time) { if(!time) return 'Not yet checked'; return new Date(time*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
function absolute(time) { return new Date(time*1000).toLocaleString('en-GB'); }
function badge(label, warning=false, dim=false) { return node('span','badge'+(warning?' warn':'')+(dim?' dim':''),pretty(label)); }
function signedOut() { ui.generation++; ui.csrf=null; ui.state=null; ui.connected=false; ui.busy=false; $('workspace').hidden=true; $('sign-in').hidden=false; $('view-content').replaceChildren(); $('detail').close(); $('detail-body').replaceChildren(); $('access-key').value=''; }
function failedConnection() { ui.connected=false; $('offline').hidden=false; $('connection-status').textContent='Disconnected · cached view'; $('connection-dot').classList.add('off'); $('pause').disabled=true; if(ui.state) renderContent(); }
async function api(path, data) {
  const mutation=data!==undefined;
  const headers=mutation?{'Content-Type':'application/json','X-CSRF-Token':ui.csrf || ''}:{};
  const response=await fetch(path,{method:mutation?'POST':'GET',headers,credentials:'same-origin',body:mutation?JSON.stringify(data):undefined,signal:AbortSignal.timeout(10000)});
  const result=await response.json();
  if(!response.ok) {
    if(response.status===401 && path!=='/desk/login') signedOut();
    throw new Error(result.error || 'Request failed');
  }
  return result;
}
function errorText(error) { const known={evidence_not_current:'This source changed or is no longer current. Review its latest revision.', evidence_or_approval_expired:'This approval is no longer current. Create a new proposal from fresh evidence.', approval_mismatch:'The approval does not match the exact proposal.', unauthorised:'That access key is invalid, expired or revoked.', forbidden:'Your role does not permit this action.', invalid_text:'Use one paragraph of text, up to 4,096 characters.', control_character:'Use a single paragraph without control characters.', session_expired:'Your session expired. Sign in again.', login_rate_limited:'Too many attempts. Try again after one minute.'}; return known[error.message] || pretty(error.message); }
async function act(task) { try { await task(); } catch(e) { showToast(errorText(e)); } }
async function refresh() {
  if(ui.busy || !ui.csrf) return;
  ui.busy=true; const gen=ui.generation;
  try { const data=await api('/desk/state'+(ui.before?'?before='+ui.before:'')); if(gen!==ui.generation) return; ui.state=data; ui.connected=true; render(); }
  catch(error) { if(ui.csrf && gen===ui.generation) failedConnection(); }
  finally { if(gen===ui.generation) ui.busy=false; }
}
function selectView(view) { ui.view=view; ui.filter='all'; ui.before=null; refresh(); render(); }
function render() {
  const s=ui.state; if(!s) return;
  $('workspace').hidden=false; $('sign-in').hidden=true;
  $('scope-name').textContent=pretty(s.scope); $('role-name').textContent=pretty(s.role)+' · synthetic';
  $('offline').hidden=ui.connected; $('paused-banner').hidden=!s.paused;
  $('connection-status').textContent=s.paused?'Processing paused':(s.supervisor.error?'Worker needs attention':'Connected to local desk');
  $('connection-dot').classList.toggle('off',s.paused || Boolean(s.supervisor.error));
  $('pause').textContent=s.paused?'Resume processing':'Pause processing'; $('pause').disabled=s.role!=='owner' || !ui.connected || !s.supervisor.configured;
  $('current-date').textContent=new Date(s.now*1000).toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'});
  $('last-sync').textContent='Refreshed '+when(s.now);
  $('nav-count').textContent=s.actions.filter(a=>a.state==='proposed').length;
  document.querySelectorAll('[data-view]').forEach(b=> { if(b.dataset.view===ui.view) b.setAttribute('aria-current','page'); else b.removeAttribute('aria-current'); });
  $('section-eyebrow').textContent=ui.view==='overview'?'YOUR BRIEFING':ui.view.toUpperCase();
  if(ui.view==='overview') $('page-title').replaceChildren(document.createTextNode('Everything that matters.'),node('br'),node('span','','Nothing you don\'t need.'));
  else $('page-title').textContent=names[ui.view];
  $('page-description').textContent=descriptions[ui.view];
  renderContent();
}
function empty(title, description) { const e=node('div','empty'); e.append(node('strong','',title),node('span','',description)); return e; }
function sectionTop(title, caption) { const d=node('div','section-top'); d.append(node('h2','',title)); if(caption) d.append(node('small','',caption)); return d; }
function card(e, featured=false) {
  const c=node('article','evidence-card'+(featured?' featured':''));
  const top=node('div','card-top'); top.append(badge(e.status==='current'?'Current report':e.status,e.status!=='current'),node('span','card-time',when(e.observed_at)));
  c.append(top,node('h3','',e.title),node('p','',e.summary));
  const bottom=node('div','card-bottom');
  bottom.append(node('div','source-meta',(e.filename || e.source)+' · rev '+(e.revision || '?')+(e.acknowledged?' · acknowledged':'')),button('Inspect evidence ↗','text-button',()=>act(()=>openEvidence(e.seq))));
  bottom.querySelector('button').dataset.focusKey='evidence-'+e.seq; c.append(bottom); return c;
}
function overview(root) {
  const s=ui.state, current=s.events.filter(e=>e.status==='current');
  const stats=node('section','stats'); stats.setAttribute('aria-label','Workspace summary');
  [['Current updates shown',current.length,'From the latest 30 events'],['Awaiting approval',s.actions.filter(a=>a.state==='proposed').length,'In the latest 100 actions'],['Local drafts created',s.counts.drafts,'Stored here. Nothing sent.']].forEach(([label,note,caption])=>{const d=node('div','stat'); d.append(node('div','stat-label',label),node('div','stat-value',String(note).padStart(2,'0')),node('div','stat-caption',caption));stats.append(d);});
  root.append(stats);
  const layout=node('div','content-grid'),left=node('section'),stack=node('div','stack');
  left.append(sectionTop('Changes worth your attention','SOURCE-LINKED'));
  if(current.length) current.slice(0,3).forEach((e,i)=>stack.append(card(e,i===0))); else stack.append(empty('No current reports','Check source status or inspect expired and superseded evidence.'));
  left.append(stack,button('View all evidence →','text-button',()=>selectView('evidence')));
  const side=node('aside','side-panels'),one=node('section','panel');
  one.append(node('div','mini-icon','◇'),node('h3','','A clear next step'),node('p','','Inspect a current report, prepare a response, then review the exact draft before approving it.'),button('Review approvals →','primary full',()=>selectView('approvals')));
  const two=node('section','panel'); two.append(node('h3','','What Alfred can do here'));
  [['Read sample project files','ACTIVE'],['Create approved local drafts','ACTIVE'],['Send messages','NOT CONNECTED'],['Live reasoning / voice','OFF']].forEach(([a,b])=>{const row=node('div','capability');row.append(node('span','',a),node('strong',b==='ACTIVE'?'':'inactive',b));two.append(row);});
  two.append(node('div','divider'),node('p','accessible-note','Updates are selected by rules, not by an AI model. Every result stays linked to its source.'),button('View sources and health ↗','text-button',()=>selectView('sources')));
  side.append(one,two);layout.append(left,side);root.append(layout);
}
function evidencePage(root) {
  const filters=node('div','filters');
  [['all','All updates'],['current','Current'],['unread','Not acknowledged'],['history','History / unavailable']].forEach(([id,label])=>{const b=button(label,'',()=>{ui.filter=id;renderContent();});b.setAttribute('aria-pressed',String(ui.filter===id));filters.append(b);});
  root.append(filters,node('p','status-line',(ui.before?'Earlier page, up to 30 events.':'Latest 30 events.')+' Freshness is recalculated on each request.')); if(ui.before) root.append(button('Back to latest evidence','text-button',()=>{ui.before=null;refresh();}));
  const stack=node('div','stack');
  const events=ui.state.events.filter(e=>ui.filter==='all' || (ui.filter==='current'&&e.status==='current') || (ui.filter==='unread'&&!e.acknowledged) || (ui.filter==='history'&&e.status!=='current'));
  events.forEach(e=>stack.append(card(e)));
  if(!events.length) stack.append(empty('No matching updates','Choose another filter or check the configured source.'));
  root.append(stack);
  if(ui.state.next_cursor) root.append(button('Load older evidence','outline load-more',()=>act(async()=>{ui.before=ui.state.next_cursor;await refresh();})));
}
function actionsPage(root) {
  const actions=ui.state.actions;
  root.append(node('p','status-line','Latest 100 actions. Approval permits a local draft only. Alfred cannot send messages from this release.'));
  if(!actions.length) {root.append(empty('Nothing awaiting your decision','Open current evidence and prepare your first draft.'));return;}
  actions.forEach(a=>{
    const c=node('article','action-card'),top=node('div','card-top'); top.append(badge(a.state,a.state==='uncertain'||a.state==='blocked'),node('span','card-time',when(a.created_at)));
    c.append(top,node('h3','','Local response draft'),node('p','',a.parameters.text),node('div','mono','Action '+a.id));
    if(a.proof) c.append(node('p','accessible-note','Verified by local database read-back. Not sent.'),node('div','mono','Result SHA-256: '+a.proof.sha256));
    const buttons=node('div','actions');
    if(a.event_seq) buttons.append(button('Source evidence ↗','text-button',()=>act(()=>openEvidence(a.event_seq))));
    if(a.mine && ui.state.role==='owner') {
      if(a.state==='proposed') {const b=button('Review and approve','primary',()=>openApproval(a));b.disabled=!ui.connected||!a.evidence_current||a.expires_at<=ui.state.now;buttons.append(b);}
      if(['proposed','queued'].includes(a.state)) {const b=button('Cancel','outline',()=>act(async()=>{await api('/desk/actions/'+a.id+'/cancel',{});showToast('Cancelled before execution.');await refresh();}));b.disabled=!ui.connected;buttons.append(b);}
      if(a.state==='uncertain') {const b=button('Check stored result','outline',()=>act(async()=>{const result=await api('/desk/actions/'+a.id+'/reconcile',{});showToast(result.state==='verified'?'Existing local draft verified. Nothing resent.':'No result established. This action remains uncertain.');await refresh();}));b.disabled=!ui.connected;buttons.append(b);}
    }
    if(a.state==='proposed'&&!a.evidence_current) c.append(node('p','error','Source is no longer current. A fresh proposal is required.'));
    c.append(buttons);root.append(c);
  });
}
function sourcesPage(root) {
  const s=ui.state,h=s.supervisor,health=h.source;
  const panel=node('section','panel'); panel.append(node('h3','','Local project files'),node('p','','Only top-level JSON documents in the configured sample-project folder are read. The folder is never modified by the connector.'));
  [['Connection',health?pretty(health.status):'Not configured'],['Last scan',health?when(health.last_scan):'No scan'],['Processing',s.paused?'Paused':pretty(h.status)],['Interval',h.interval_seconds?h.interval_seconds+' seconds':'Not configured']].forEach(([a,b])=>{const r=node('div','list-row');r.append(node('span','',a),node('strong','',b));panel.append(r);});
  root.append(panel,node('div','divider'));
  if(health?.errors?.length) health.errors.forEach(e=>root.append(node('div','warning',(e.file?e.file+': ':'')+pretty(e.code))));
  if(h.error) root.append(node('div','warning','Worker: '+pretty(h.error)));
  s.documents.forEach(d=>{const r=node('div','list-row'),left=node('div');left.append(node('strong','',d.title),node('small','',d.filename+' · revision '+d.revision+' · checked '+when(d.checked)));r.append(left,badge(d.status,d.status!=='ready'));root.append(r);});
  if(!s.documents.length) root.append(empty('No documents imported','Check the configured project folder and source health above.'));
}
function activityPage(root) {
  const timeline=node('section','timeline');
  ui.state.audit.forEach(a=>{const e=node('div','timeline-item');e.append(node('strong','',pretty(a.kind)),node('small','',absolute(a.at)+' · '+a.actor),node('small','mono',a.subject));timeline.append(e);});root.append(timeline);
}
function settingsPage(root) {
  const grid=node('div','settings-grid');
  const control=node('section','panel');control.append(node('h3','','Processing control'),node('p','','Pause stops the local project scanner and prevents new draft execution. Existing records remain. Completed work is not undone.'));
  const p=button(ui.state.paused?'Resume processing':'Pause processing','primary',togglePause);p.disabled=ui.state.role!=='owner'||!ui.connected||!ui.state.supervisor.configured;control.append(p);
  const access=node('section','panel');access.append(node('h3','','Workspace access'),node('p','','Your current key grants '+ui.state.role+' access to '+ui.state.scope+'. Switch by signing out and using a key for another authorised workspace. Signing out hides your workspace; it does not stop the local process.'),button('Sign out / switch workspace','outline',logout));
  const privacy=node('section','panel');privacy.append(node('h3','','Collection boundary'),node('p','','Microphone, camera and location permissions are disabled. No live AI provider, external account or device is connected. Local stored data is not encrypted by this alpha. Use synthetic data only.'));
  const lifecycle=node('section','panel');lifecycle.append(node('h3','','Stopping and revoking access'),node('p','','Ctrl+C in the desk terminal stops processing. Events, approvals and local drafts survive restart. Browser sessions do not: sign in again. Credential revocation is available through the existing offline administration command.'),node('p','mono','python3 -m alfred.desk revoke --credential-id <credential-id>'));
  grid.append(control,access,privacy,lifecycle);root.append(grid);
}
function renderContent() {const root=$('view-content');const key=root.contains(document.activeElement)?document.activeElement.dataset.focusKey:null;root.replaceChildren();({overview,evidence:evidencePage,approvals:actionsPage,activity:activityPage,sources:sourcesPage,settings:settingsPage})[ui.view](root);if(key){const target=Array.from(root.querySelectorAll('button')).find(b=>b.dataset.focusKey===key);if(target)target.focus({preventScroll:true});}}
function setDialog(eyebrow) {$('detail-eyebrow').textContent=eyebrow;$('detail-body').replaceChildren();if(!$('detail').open)$('detail').showModal();return $('detail-body');}
async function openEvidence(seq) {
  if(!ui.connected) {showToast('Reconnect before inspecting current evidence.');return;}
  const gen=ui.generation; const e=await api('/desk/evidence/'+seq); if(gen!==ui.generation) return; const body=setDialog('SOURCE EVIDENCE');
  body.append(node('h2','dialog-title',e.title));body.querySelector('h2').id='detail-title';
  body.append(badge(e.status,e.status!=='current'),node('p','detail-summary',e.summary));
  const data=node('dl','data-grid');
  [['Source',e.filename||e.source],['Revision',e.revision||'Not available'],['Observed',absolute(e.observed_at)],['Expires',absolute(e.expires_at)],['Evidence basis',pretty(e.basis)+' · sample workspace'],['Routing reason',pretty(e.reason)]].forEach(([a,b])=>{const pair=node('div');pair.append(node('dt','',a),node('dd','',b));data.append(pair);});
  body.append(data,node('p','mono','Source SHA-256: '+(e.source_sha256||'Not recorded')),node('p','accessible-note','This is a report from a sample document, not independently verified real-world information.'));
  const actions=node('div','actions');
  if(!e.acknowledged) actions.append(button('Mark as acknowledged','outline',()=>act(async()=>{await api('/desk/evidence/'+seq+'/acknowledge',{});showToast('Your acknowledgement was recorded.');await openEvidence(seq);await refresh();})));
  else actions.append(node('span','accessible-note','Acknowledged by this signed-in user.'));
  if(ui.state.role==='owner'&&e.status==='current') actions.append(button('Prepare a response draft','primary',()=>compose(e)));
  body.append(actions);
}
function compose(e) {
  const body=setDialog('PREPARE A LOCAL DRAFT');body.append(node('h2','dialog-title','What should the response say?'));body.querySelector('h2').id='detail-title';
  body.append(node('p','accessible-note','Source: '+e.title+' · revision '+e.revision+'. This text is a template for you to edit, not generated by an AI model.'));
  const label=node('label','compose-label','Draft text');label.htmlFor='draft-text';
  const area=node('textarea');area.id='draft-text';area.maxLength=4096;area.value='Please review this update: '+e.summary;
  body.append(label,area,node('p','hint','One paragraph. Up to 4,096 characters. Nothing will be sent.'));
  const b=button('Review exact proposal →','primary',()=>act(async()=>{b.disabled=true;try{const proposal=await api('/desk/proposals',{event_seq:e.seq,text:area.value,request_id:'desk-'+crypto.randomUUID()});openApproval({...proposal,event_seq:e.seq});await refresh();}finally{b.disabled=false;}}));
  body.append(node('div','divider'),b);area.focus();
}
function openApproval(a) {
  const body=setDialog('YOUR APPROVAL IS REQUIRED');body.append(node('h2','dialog-title','Create this local draft?'));body.querySelector('h2').id='detail-title';
  body.append(node('p','detail-summary',a.parameters.text),node('div','divider'),node('p','accessible-note','This approves the exact text above, linked to its source evidence. Alfred will store it in the local database. It will not send a message or use an external account.'),node('p','mono','Approval fingerprint: '+a.fingerprint),node('p','accessible-note','Expires '+absolute(a.expires_at)+'. Changed or unavailable source evidence invalidates this proposal.'));
  const buttons=node('div','actions'),approve=button('Approve local draft','primary',()=>act(async()=>{approve.disabled=true;try{await api('/desk/actions/'+a.id+'/approve',{fingerprint:a.fingerprint});$('detail').close();selectView('approvals');showToast(ui.state.paused?'Approved and queued. Processing is paused.':'Approved. The local worker will create and verify the draft.');await refresh();}finally{approve.disabled=false;}}));
  approve.disabled=!ui.connected;buttons.append(approve,button('Not now','outline',()=>$('detail').close()));body.append(buttons);
}
async function togglePause() {await act(async()=>{await api('/desk/pause',{paused:!ui.state.paused});await refresh();showToast(ui.state.paused?'Processing paused. Stored work is unchanged.':'Processing resumed.');});}
async function logout() {await act(async()=>{await api('/desk/logout',{});signedOut();});}
$('login-form').addEventListener('submit',async(event)=>{event.preventDefault();$('login-error').textContent='';const key=$('access-key').value.trim();$('access-key').value='';try{const result=await api('/desk/login',{key});ui.csrf=result.csrf;ui.generation++;ui.view='presence';await refresh();}catch(error){$('login-error').textContent=errorText(error);}});
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>selectView(b.dataset.view)));
$('refresh').addEventListener('click',refresh);$('pause').addEventListener('click',togglePause);$('switch').addEventListener('click',logout);$('close-detail').addEventListener('click',()=>$('detail').close());
document.querySelector('.brand').addEventListener('click',event=>{event.preventDefault();selectView('presence');});
async function bootstrapDesk(){try{const session=await api('/desk/session');ui.csrf=session.csrf;await refresh();}catch(_){signedOut();}}
// All extension scripts must register before the first render. This also holds
// when the standalone file transport resolves before the HTML parser finishes.
if(document.readyState==='complete')queueMicrotask(bootstrapDesk);
else document.addEventListener('DOMContentLoaded',bootstrapDesk,{once:true});
setInterval(refresh,3000);
