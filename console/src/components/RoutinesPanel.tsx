import {useCallback,useEffect,useState} from 'react';
import {Bell,BookOpenText,CaretRight,ClockCounterClockwise,Info,MoonStars,Pause,Play} from '@phosphor-icons/react';
import {useConsole,type ConsoleController} from '../state/ConsoleProvider';
import {DeskError} from '../integration/deskClient';
import {requestKey} from '../integration/jobs';
import {EVERY_HOURS,OFFSETS,RULE_LABEL,citeLabel,decisionLabel,formFromRoutine,formProblem,holdLabel,localMoment,nominationLine,notNominatedLine,offsetLabel,
  readLine,routineMessage,runSummary,scheduleLabel,settingsPayload,sourceLabel,
  type Cite,type NominationView,type ProceduresView,type RoutineForm,type RoutineKind,type RoutineSummary,type RoutineView,type RoutinesView,type RunView} from '../integration/routines';
import '../routines.css';

type Tab='routines'|'nominations'|'runs'|'procedures';
const isAbort=(e:unknown)=>e instanceof DOMException&&e.name==='AbortError';
// Which tab the next opening should show, set by the side panel. Read once, then cleared.
let requestedTab:Tab|null=null;
export function openRoutines(c:Pick<ConsoleController,'setModal'>,tab:Tab='routines'){requestedTab=tab;c.setModal('routines');}

/** Re-read on every confirmed projection refresh while open, and after every change made here. */
function useRoutineData<T>(path:string){
  const c=useConsole(),{client,fail}=c.live,observed=c.live.connection.kind==='ready'?c.live.connection.observedAt:'';
  const[state,setState]=useState<{data:T|null;error:string}>({data:null,error:''}),[tick,setTick]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    client.get<T>(path,controller.signal).then(data=>{if(!controller.signal.aborted)setState({data,error:''});}).catch(e=>{
      if(isAbort(e))return;setState(s=>({data:s.data,error:routineMessage(e)}));if(e instanceof DeskError&&e.kind==='signed_out')fail(e);
    });
    return()=>controller.abort();
  },[client,fail,path,observed,tick]);
  return {...state,refresh:useCallback(()=>setTick(t=>t+1),[])};
}

/** Routines: authored settings, nominations, run history and the procedure registry. */
export function RoutinesPanel(){
  const c=useConsole();
  if(!c.connected)return <div className="routines-panel"><div className="review-scope"><Info size={20}/><span>Routines need the connected ALFRED product. This local preview has no routines, schedules or nominations, and runs nothing.</span></div>
    <p className="dialog-note">When the console is served by your ALFRED host, you can enable a commitment review and a morning brief, set budgets, quiet hours and a pause, and accept or dismiss what they nominate.</p></div>;
  return <ConnectedRoutines/>;
}

function ConnectedRoutines(){
  const c=useConsole(),routines=useRoutineData<RoutinesView>('/desk/routines'),procedures=useRoutineData<ProceduresView>('/desk/routines/procedures');
  const[tab,setTab]=useState<Tab>(()=>{const t=requestedTab??'routines';requestedTab=null;return t;});
  const[busy,setBusy]=useState(false),[error,setError]=useState('');
  const view=routines.data;
  const refreshAll=routines.refresh;
  const write=async<T,>(path:string,body:unknown,notice?:string):Promise<T|null>=>{
    setBusy(true);setError('');
    try{const r=await c.live.client.post<T>(path,body);if(notice)c.setNotice(notice);return r;}
    catch(e){setError(routineMessage(e));if(e instanceof DeskError&&e.kind==='signed_out')c.live.fail(e);return null;}
    finally{setBusy(false);refreshAll();procedures.refresh();}
  };
  const open=(view?.nominations??[]).filter(n=>n.state==='open');
  const tabs:[Tab,string,number][]=[['routines','Routines',view?.routines.filter(r=>r.enabled).length??0],['nominations','Nominations',open.length],
    ['runs','Runs',view?.runs.length??0],['procedures','Procedures',procedures.data?.procedures.length??0]];
  return <div className="routines-panel">
    <div className="exec-tabs" role="tablist" aria-label="Routine views">
      {tabs.map(([id,label,count])=><button key={id} role="tab" id={`routine-tab-${id}`} aria-selected={tab===id} aria-controls={`routine-panel-${id}`} onClick={()=>setTab(id)}>{label}<span>{count}</span></button>)}
    </div>
    {!view&&!routines.error&&<p className="dialog-note" role="status">Reading your routines…</p>}
    {routines.error&&<p className="sign-in-error" role="alert">{routines.error}</p>}
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
    {view&&tab==='routines'&&<section role="tabpanel" id="routine-panel-routines" aria-labelledby="routine-tab-routines">
      <p className="dialog-note">A routine reads your records on a schedule you set and nominates; you decide. It runs only while this ALFRED host is running, under the key it was started with. Nothing is sent outside ALFRED.</p>
      {view.workspace_paused&&<p className="routine-alert" role="status"><Pause size={15}/>The workspace is paused, so every routine is skipped until you resume it.</p>}
      {view.available?view.routines.map(r=><RoutineCard key={`${r.kind}:${r.version}`} routine={r} busy={busy} write={write}/>)
        :<p className="quiet-empty">{view.reason==='owner_only'?'Routines are set by the workspace owner. This key cannot read or change them.':'Routines run under the access key this ALFRED host was started with. Sign in with that key to set them.'}</p>}
    </section>}
    {view&&tab==='nominations'&&<NominationList view={view} busy={busy} write={write}/>}
    {view&&tab==='runs'&&<RunList view={view}/>}
    {tab==='procedures'&&<ProcedureList data={procedures.data} error={procedures.error}/>}
  </div>;
}

type Write=<T>(path:string,body:unknown,notice?:string)=>Promise<T|null>;
const offsetOf=(view:RoutinesView,kind:RoutineKind)=>view.routines.find(r=>r.kind===kind)?.settings?.utc_offset_minutes??0;

function RoutineCard({routine:r,busy,write}:{routine:RoutineView;busy:boolean;write:Write}){
  const c=useConsole(),owner=c.live.session?.role==='owner';
  const[form,setForm]=useState<RoutineForm>(()=>formFromRoutine(r));
  const set=(patch:Partial<RoutineForm>)=>setForm(f=>({...f,...patch}));
  const problem=formProblem(r.kind,form),offset=r.settings?.utc_offset_minutes??form.offset,brief=r.kind==='morning-brief';
  const save=()=>void write(`/desk/routines/${r.kind}/configure`,settingsPayload(r.kind,form,r.version),`${r.name} settings saved.`);
  const pause=()=>void write(`/desk/routines/${r.kind}/pause`,{version:r.version,paused:!r.paused},r.paused?`${r.name} resumed.`:`${r.name} paused. Due runs are recorded as skipped.`);
  const runNow=()=>void write(`/desk/routines/${r.kind}/run`,{request_id:requestKey()},`${r.name} ran. See its outcome under Runs.`);
  const status=[r.configured?(r.enabled?'On':'Off'):'Not set up',r.paused?'Paused':null,r.quiet_now?'Quiet hours now':null,r.configured&&!r.authority_available?'Authority unavailable':null].filter(Boolean) as string[];
  return <article className="routine-card" aria-labelledby={`routine-${r.kind}`}>
    <header><span className="record-symbol">{brief?<ClockCounterClockwise size={18} weight="thin"/>:<Bell size={18} weight="thin"/>}</span>
      <div><h3 id={`routine-${r.kind}`}>{r.name}</h3><p>{r.description}</p></div>
      <ul className="routine-chips" aria-label={`${r.name} status`}>{status.map(s=><li key={s} className={s==='On'?'on':s==='Paused'||s==='Authority unavailable'?'warn':''}>{s}</li>)}</ul></header>
    {r.configured&&r.settings&&<p className="routine-line">{scheduleLabel(r.settings.schedule)} · {offsetLabel(r.settings.utc_offset_minutes)} · {r.enabled&&r.next_due?`next ${localMoment(r.next_due,offset)}`:'no run scheduled'} · {r.runs_today} of {r.settings.runs_per_day} runs today</p>}
    <details className="routine-rules"><summary>Stated rules</summary><ul>{r.rules.map(rule=><li key={rule.id}>{rule.rule}</li>)}</ul></details>
    {owner?<form className="routine-form" aria-label={`${r.name} settings`} onSubmit={e=>{e.preventDefault();if(!problem)save();}}>
      <label className="routine-check"><input type="checkbox" checked={form.enabled} onChange={e=>set({enabled:e.target.checked})}/><span>Enabled</span></label>
      <div className="routine-grid">
        <label>Schedule<select value={String(form.every)} onChange={e=>set({every:e.target.value==='daily'?'daily':Number(e.target.value)})}>
          {EVERY_HOURS.map(h=><option key={h} value={h}>{scheduleLabel({every_hours:h})}</option>)}<option value="daily">Daily at a set time</option></select></label>
        {form.every==='daily'&&<label>Time of day<input type="time" value={form.dailyAt} onChange={e=>set({dailyAt:e.target.value})}/></label>}
        <label>Local time offset<select value={form.offset} onChange={e=>set({offset:Number(e.target.value)})}>{OFFSETS.map(o=><option key={o} value={o}>{offsetLabel(o)}</option>)}</select></label>
        <label>Runs per day<input type="number" min={1} max={24} value={form.runsPerDay} onChange={e=>set({runsPerDay:Math.trunc(Number(e.target.value))})}/></label>
        <label>{brief?'Held items surfaced per run':'Nominations per run'}<input type="number" min={1} max={10} value={form.nominationsPerRun} onChange={e=>set({nominationsPerRun:Math.trunc(Number(e.target.value))})}/></label>
      </div>
      <fieldset className="routine-quiet"><legend><MoonStars size={14}/>Quiet hours</legend>
        <label className="routine-check"><input type="checkbox" checked={form.quiet} onChange={e=>set({quiet:e.target.checked})}/><span>Hold nominations during quiet hours and show them afterwards</span></label>
        {form.quiet&&<div className="routine-grid"><label>Quiet from<input type="time" value={form.quietStart} onChange={e=>set({quietStart:e.target.value})}/></label>
          <label>Quiet until<input type="time" value={form.quietEnd} onChange={e=>set({quietEnd:e.target.value})}/></label></div>}
      </fieldset>
      {!brief&&<fieldset className="routine-interrupt"><legend>When something is nominated</legend>
        <label className="routine-check"><input type="radio" name={`interrupt-${r.kind}`} checked={form.interrupt==='show_now'} onChange={()=>set({interrupt:'show_now'})}/><span>Show it now</span></label>
        <label className="routine-check"><input type="radio" name={`interrupt-${r.kind}`} checked={form.interrupt==='hold_for_brief'} onChange={()=>set({interrupt:'hold_for_brief'})}/><span>Hold it for the next morning brief</span></label>
        <label className="routine-check"><input type="checkbox" checked={form.proposeDrafts} onChange={e=>set({proposeDrafts:e.target.checked})}/><span>Offer a local draft for overdue items with a responsible label</span></label>
      </fieldset>}
      {problem&&<p className="dialog-note" role="status">{problem}</p>}
      <div className="button-row"><button className="primary-button" type="submit" disabled={busy||Boolean(problem)}>Save settings</button>
        {r.configured&&<button type="button" className="secondary-button" aria-pressed={r.paused} disabled={busy} onClick={pause}>{r.paused?<Play size={14}/>:<Pause size={14}/>}{r.paused?'Resume routine':'Pause routine'}</button>}
        {r.configured&&<button type="button" className="text-button" disabled={busy} onClick={runNow}>Run now</button>}</div>
    </form>:<p className="dialog-note">Only the workspace owner can change routines.</p>}
  </article>;
}

function NominationRow({n,offset,busy,write}:{n:NominationView;offset:number;busy:boolean;write:Write}){
  const c=useConsole(),owner=c.live.session?.role==='owner',current=n.cite.state==='current',hold=holdLabel(n,offset);
  const decide=async(path:'accept'|'dismiss',body:unknown,notice:string)=>{
    const result=await write<{action?:{id:string}}>(`/desk/routines/nominations/${encodeURIComponent(n.id)}/${path}`,body,notice);
    if(result?.action){
      // The draft is now a proposal in the ledger. Its exact text still needs its own approval.
      await c.live.refresh();c.openReview(result.action.id);
    }
  };
  const source=sourceLabel(n.cite);
  return <li className={`nomination-row ${n.state!=='open'?'decided':''}`} aria-label={`${n.kind==='draft'?'Draft offer':'Reminder'}: ${current||n.cite.state==='changed'?citeLabel(n.cite):'unavailable item'}`}>
    <div className="nomination-head"><span className={`attention-mark rule-${n.rule==='overdue'?'overdue':'due_soon'}`} aria-hidden="true"/>
      <strong>{citeLabel(n.cite)}</strong><small>{nominationLine(n,offset)}</small></div>
    <p className="nomination-reason">{n.reason}</p>
    {source&&<p className="nomination-source">Cited lines: {source}</p>}
    {hold&&<p className="nomination-hold"><MoonStars size={13}/>{hold}</p>}
    {n.state!=='open'?<p className="nomination-decided">{decisionLabel(n)}{n.decided?` · ${localMoment(n.decided,offset)}`:''}</p>
      :owner&&<>{!current&&<p className="dialog-note">The cited commitment changed or is no longer available, so this can only be dismissed.</p>}
        {n.kind==='draft'&&current&&<p className="dialog-note">Accepting proposes a local draft in the approval ledger. You approve its exact text separately; nothing is sent.</p>}
        <div className="button-row">
          {n.kind==='reminder'&&<><button className="secondary-button" disabled={busy||!current} onClick={()=>void decide('accept',{version:n.version,create_follow_up:false},'Reminder accepted. Nothing else was created.')}>Accept</button>
            <button className="secondary-button" disabled={busy||!current} onClick={()=>void decide('accept',{version:n.version,create_follow_up:true},'Reminder accepted and a follow-up added to your records.')}>Accept and add follow-up</button></>}
          {n.kind==='draft'&&<button className="secondary-button" disabled={busy||!current} onClick={()=>void decide('accept',{version:n.version,create_follow_up:false},'Draft proposed for your approval. Nothing is sent.')}>Propose draft for approval</button>}
          <button className="text-button" disabled={busy} onClick={()=>void decide('dismiss',{version:n.version},'Nomination dismissed.')}>Dismiss</button></div></>}
  </li>;
}

function NominationList({view,busy,write}:{view:RoutinesView;busy:boolean;write:Write}){
  const offset=offsetOf(view,'commitment-review'),open=view.nominations.filter(n=>n.state==='open');
  const shown=open.filter(n=>n.surfaced),held=open.filter(n=>!n.surfaced),decided=view.nominations.filter(n=>n.state!=='open');
  const brief=view.routines.find(r=>r.kind==='morning-brief');
  return <section role="tabpanel" id="routine-panel-nominations" aria-labelledby="routine-tab-nominations">
    <p className="dialog-note">A nomination is a suggestion with a stated reason and the exact version it cites. Nothing becomes a task, a draft or a message unless you accept it, and nothing is delivered outside ALFRED.</p>
    <h3 className="routine-subhead">Shown<span>{shown.length}</span></h3>
    {shown.length?<ul className="nomination-list" aria-label="Shown nominations">{shown.map(n=><NominationRow key={n.id} n={n} offset={offset} busy={busy} write={write}/>)}</ul>:<p className="quiet-empty">Nothing nominated right now.</p>}
    <h3 className="routine-subhead">Held<span>{held.length}</span></h3>
    {held.length?<><ul className="nomination-list" aria-label="Held nominations">{held.map(n=><NominationRow key={n.id} n={n} offset={offset} busy={busy} write={write}/>)}</ul>
      {held.some(n=>n.held==='next_brief')&&!brief?.enabled&&<p className="routine-alert" role="status"><Info size={15}/>The morning brief is off, so items held for it wait here until you accept or dismiss them.</p>}</>
      :<p className="quiet-empty">Nothing is held.</p>}
    <h3 className="routine-subhead">Recently decided<span>{decided.length}</span></h3>
    {decided.length?<ul className="nomination-list" aria-label="Decided nominations">{decided.map(n=><NominationRow key={n.id} n={n} offset={offset} busy={busy} write={write}/>)}</ul>:<p className="quiet-empty">No decisions yet.</p>}
  </section>;
}

function CiteList({items,label}:{items:Cite[];label:string}){
  if(!items.length)return null;
  return <><h4 className="run-cite-head">{label}</h4><ul className="routine-cites" aria-label={label}>{items.map((x,i)=><li key={`${x.id}:${i}`} className={x.resolved?.state!=='current'?'gone':''}>
    {x.resolved?citeLabel({...x.resolved,kind:x.kind,version:x.version}):`${x.kind} ${x.id} · version ${x.version}`}{x.rule?` · ${RULE_LABEL[x.rule]??x.rule}`:''}</li>)}</ul></>;
}

function RunDetail({run,offset}:{run:RunView;offset:number}){
  const o=run.outcome,skipped=notNominatedLine(o.not_nominated);
  return <div className="run-detail">
    <dl className="detail-list">
      <div><dt>Trigger</dt><dd>{run.trigger==='manual'?'Run now, by you':'Schedule'}</dd></div>
      <div><dt>Ran</dt><dd>{localMoment(run.started,offset)} ({offsetLabel(offset)})</dd></div>
      <div><dt>Budget</dt><dd>{o.budget.runs_today} of {o.budget.runs_per_day} runs today · up to {o.budget.nominations_per_run} per run</dd></div>
      {run.status==='skipped'&&<div><dt>Skipped</dt><dd>{runSummary(run).replace(/^Skipped · /,'')}</dd></div>}
      {o.missed_slots>0&&<div><dt>Missed</dt><dd>{o.missed_slots} earlier slot{o.missed_slots===1?'':'s'} while ALFRED was not running; not run afterwards</dd></div>}
      {o.read&&<div><dt>Read</dt><dd>{readLine(o.read)}</dd></div>}
      {o.nominated&&<div><dt>Nominated</dt><dd>{o.nominated.length||'None'}{o.held&&(o.held.quiet_hours+o.held.next_brief)?` · ${o.held.quiet_hours} held for quiet hours · ${o.held.next_brief} held for the brief`:''}</dd></div>}
      {skipped&&<div><dt>Not nominated</dt><dd>{skipped}</dd></div>}
      {o.released&&<div><dt>Surfaced</dt><dd>{o.released.length} held nomination{o.released.length===1?'':'s'}{o.still_held?` · ${o.still_held} still held`:''}</dd></div>}
      {o.error&&<div><dt>Error</dt><dd>{o.error}</dd></div>}
    </dl>
    {o.sections?<>
      <CiteList items={o.sections.attention} label="Attention items in this brief"/>
      {o.sections.insights.map((i,k)=><CiteList key={k} items={i.records.map(r=>({...r,rule:i.rule}))} label={`Records behind the insight: ${RULE_LABEL[i.rule]??i.rule}`}/>)}
      <CiteList items={o.sections.approvals} label="Proposals awaiting your approval"/></>
      :<CiteList items={o.cited??[]} label="Everything read and cited, nominated or not"/>}
    {o.cited_total!=null&&o.cited&&o.cited_total>o.cited.length&&<p className="dialog-note">{o.cited_total-o.cited.length} further citations were counted but not stored.</p>}
    <p className="dialog-note">{run.kind==='morning-brief'?'Assembled from your current records by the stated rules. Not advice and not model output.':'Computed by the stated rules over your records and accepted statements. No model was used.'} Titles show as they read for you now.</p>
  </div>;
}

function RunList({view}:{view:RoutinesView}){
  const[open,setOpen]=useState<string|null>(null);
  return <section role="tabpanel" id="routine-panel-runs" aria-labelledby="routine-tab-runs">
    <p className="dialog-note">Every due slot leaves one record: what ran and what it read, or why it was skipped. Records are historical, not current state.</p>
    {view.runs.length?<ol className="run-list" aria-label="Routine runs">{view.runs.map(run=>{const offset=offsetOf(view,run.kind),name=view.routines.find(r=>r.kind===run.kind)?.name??run.kind;
      return <li key={run.id} className={`run-row status-${run.status}`}>
        <button aria-expanded={open===run.id} onClick={()=>setOpen(open===run.id?null:run.id)}><span><strong>{name} · {localMoment(run.started,offset)}</strong><small>{runSummary(run)}</small></span><CaretRight size={14}/></button>
        {open===run.id&&<RunDetail run={run} offset={offset}/>}</li>;})}</ol>
      :<p className="quiet-empty">No runs yet. Enable a routine or choose Run now.</p>}
  </section>;
}

function ProcedureList({data,error}:{data:ProceduresView|null;error:string}){
  return <section role="tabpanel" id="routine-panel-procedures" aria-labelledby="routine-tab-procedures">
    <div className="review-scope"><BookOpenText size={20}/><span>{data?.statement??'Procedures are kept to be read. Nothing here runs, approves, schedules or grants anything.'}</span></div>
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
    {!data&&!error&&<p className="dialog-note" role="status">Reading procedures…</p>}
    {data&&<>
      <h3 className="routine-subhead">Reviewed procedures<span>{data.procedures.length}</span></h3>
      {data.procedures.length?<ul className="procedure-list" aria-label="Reviewed procedures">{data.procedures.map(p=><li key={p.id}>
        <div className="nomination-head"><strong>{p.subject?.name??'Unavailable record'} · {p.predicate.replaceAll('_',' ')}</strong>
          <small>{p.review_state==='accepted'&&p.usable?'Accepted · current':p.review_state.replaceAll('_',' ')} · version {p.version}</small></div>
        {p.value!=null?<p className="procedure-value">{p.value}</p>:<p className="dialog-note">{p.support_state==='changed'?'Its cited lines changed, so it needs a fresh review. Its value is not shown.':'Its source is not readable for you now. Its value is withheld.'}</p>}
        {p.source&&<><p className="nomination-source">{p.source.path}, {p.source.start_line===p.source.end_line?`line ${p.source.start_line}`:`lines ${p.source.start_line} to ${p.source.end_line}`}, revision {p.source.revision}</p>
          <blockquote className="procedure-quote">{p.source.quote}</blockquote></>}
        <p className="procedure-basis">Reviewed description · never run · grants nothing</p></li>)}</ul>
        :<p className="quiet-empty">No reviewed procedures. Capture a statement as procedural memory to list it here.</p>}
      <h3 className="routine-subhead">Authored procedure notes<span>{data.authored_procedure_notes.length}</span></h3>
      {data.authored_procedure_notes.length?<ul className="procedure-notes">{data.authored_procedure_notes.map(n=><li key={n.id}><strong>{n.title}</strong><small>{n.path} · revision {n.revision} · authored, not reviewed</small></li>)}</ul>
        :<p className="quiet-empty">No notes of type procedure in your permitted sources.</p>}
    </>}
  </section>;
}

/** Executive panel: nominations that are shown now, and the latest brief. Held items never appear here. */
export function RoutineNominationsSection(){
  const c=useConsole();
  return c.connected&&c.live.session?<RoutineSummarySection/>:null;
}
function RoutineSummarySection(){
  const c=useConsole(),summary=useRoutineData<RoutineSummary>('/desk/routines/nominations').data;
  if(!summary?.available||(!summary.nominations.length&&!summary.latest_brief))return null;
  const brief=summary.latest_brief;
  return <section className="executive-section routine-section"><header className="executive-section-heading"><h3>Routines</h3>
      <button onClick={()=>openRoutines(c,summary.nominations.length?'nominations':'runs')}>Open<CaretRight size={12}/></button></header>
    {summary.nominations.slice(0,3).map(n=><button className="attention-row" key={n.id} onClick={()=>openRoutines(c,'nominations')}>
      <span className={`attention-mark rule-${n.rule==='overdue'?'overdue':'due_soon'}`} aria-hidden="true"/>
      <span><strong>{n.cite.state==='unavailable'?'No longer available to you':n.cite.kind==='record'?n.cite.title:`${n.cite.subject?.name}: ${n.cite.value}`}</strong>
        <small>{n.kind==='draft'?'Draft offer':'Reminder'} · {RULE_LABEL[n.rule]??n.rule} · your decision</small></span></button>)}
    {brief&&<button className="attention-row" onClick={()=>openRoutines(c,'runs')}><span className="attention-mark rule-brief" aria-hidden="true"/>
      <span><strong>Morning brief</strong><small>{brief.read.attention_items??0} attention · {brief.read.pending_approvals??0} approvals · {brief.released} surfaced</small></span></button>}
    {summary.held>0&&<p className="quiet-empty">{summary.held} held for later.</p>}
  </section>;
}
