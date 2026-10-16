import {useCallback,useEffect,useState} from 'react';
import {Brain,CheckSquare,Info,Pause,Play,Target} from '@phosphor-icons/react';
import {useConsole} from '../state/ConsoleProvider';
import {DeskError} from '../integration/deskClient';
import {localMoment,offsetLabel,scheduleLabel} from '../integration/routines';
import {acknowledgeNote,acknowledgeRequest,attentionLine,autonomyLine,brainEvidenceLine,canAcknowledge,canRunChecks,checkLabel,controlRequest,
  evidenceLabel,evidenceTone,goalMessage,runLine,stateLabel,taskLine,usageLines,verifyRequest,
  type BrainView,type HubResult,type HubState,type HubView,type Level,type MandateView,type Operation,type ResultsView,type Usage} from '../integration/goals';
import '../routines.css';
import '../goals.css';

const isAbort=(e:unknown)=>e instanceof DOMException&&e.name==='AbortError';
type Act=(level:Level,target:string|null,operation:Operation,version:number,notice:string)=>void;

/** Goals the agent hub works on: mandate, budget use and pause state, with pause, resume and stop. */
export function GoalsPanel(){
  const c=useConsole();
  if(!c.connected)return <div className="routines-panel"><div className="review-scope"><Info size={20}/><span>Goals need the connected ALFRED product. This local preview has no goals, mandates or brains, and runs nothing.</span></div></div>;
  return <ConnectedGoals/>;
}

function ConnectedGoals(){
  const c=useConsole(),{client,fail}=c.live,observed=c.live.connection.kind==='ready'?c.live.connection.observedAt:'';
  const[view,setView]=useState<HubView|null>(null),[error,setError]=useState(''),[actionError,setActionError]=useState(''),[busy,setBusy]=useState(false),[tick,setTick]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    client.get<HubView>('/desk/hub',controller.signal).then(data=>{if(!controller.signal.aborted){setView(data);setError('');}}).catch(e=>{
      if(isAbort(e))return;setError(goalMessage(e));if(e instanceof DeskError&&e.kind==='signed_out')fail(e);
    });
    return()=>controller.abort();
  },[client,fail,observed,tick]);
  const refresh=useCallback(()=>setTick(t=>t+1),[]);
  const act:Act=(level,target,operation,version,notice)=>{
    const {path,body}=controlRequest(level,target,operation,version);
    setBusy(true);setActionError('');
    client.post<HubView>(path,body).then(next=>{setView(next);c.setNotice(notice);})
      .catch(e=>{setActionError(goalMessage(e));if(e instanceof DeskError&&e.kind==='signed_out')fail(e);refresh();})
      .finally(()=>setBusy(false));
  };
  const acknowledge=(id:string)=>{
    setBusy(true);setActionError('');
    client.post(`/desk/hub/attention/${encodeURIComponent(id)}/acknowledge`,{}).catch(e=>setActionError(goalMessage(e))).finally(()=>{setBusy(false);refresh();});
  };
  if(error&&!view)return <div className="routines-panel"><p className="sign-in-error" role="alert">{error}</p></div>;
  if(!view)return <div className="routines-panel"><p className="dialog-note" role="status">Reading your goals…</p></div>;
  if(!view.available)return <div className="routines-panel"><p className="quiet-empty">{view.reason==='owner_only'?'Goals are set by the workspace owner. This key cannot read or change them.'
    :'Goals run under the access key this ALFRED host was started with. Sign in with that key to see them.'}</p>
    {view.reason!=='owner_only'&&<ResultsSection tick={tick} observed={observed}/>}</div>;
  const open=view.attention.filter(a=>a.state==='open');
  const titleOf=(target:string)=>view.goals.find(g=>`goal:${g.id}`===target)?.goal.title;
  return <div className="routines-panel goals-panel">
    <p className="dialog-note">A goal is yours; a mandate sets the limits brains work within. ALFRED admits, meters, pauses and stops every task. A brain cannot schedule itself, and nothing shown here grants authority.</p>
    {view.workspace_paused&&<p className="routine-alert" role="status"><Pause size={15}/>The workspace is paused, so no goal work is admitted and due heartbeats are skipped.</p>}
    {actionError&&<p className="sign-in-error" role="alert">{actionError}</p>}
    {open.length>0&&<section aria-label="Budget attention"><h3 className="routine-subhead">Needs your attention<span>{open.length}</span></h3>
      <ul className="routine-cites">{open.map(a=><li key={a.id}>{attentionLine(a,titleOf(a.target))} <button className="text-button" disabled={busy} onClick={()=>acknowledge(a.id)}>Acknowledge</button></li>)}</ul></section>}
    <section aria-label="Goals"><h3 className="routine-subhead">Goals<span>{view.goals.length}</span></h3>
      {view.goals.length?view.goals.map(m=><GoalCard key={m.id} m={m} busy={busy} act={act}/>)
        :<p className="quiet-empty">No goal has a mandate yet, so brains do no work for any goal.</p>}
      {view.unlinked_goals.length>0&&<p className="dialog-note">{view.unlinked_goals.length} active {view.unlinked_goals.length===1?'goal has':'goals have'} no mandate. Brains do no work for {view.unlinked_goals.length===1?'it':'them'}. Mandates are authored through ALFRED's hub routes; this view does not create them.</p>}
    </section>
    <section aria-label="All brains"><h3 className="routine-subhead">All brains</h3>
      {view.overall&&<article className="routine-card"><header><span className="record-symbol"><Brain size={18} weight="thin"/></span>
        <div><h3>Overall budget</h3><p>Every goal and brain counts against this. With no overall budget, no task is admitted.</p></div>
        <Chips label="Overall status" items={[stateLabel(view.overall.state,view.overall.reason)]} state={view.overall.state}/></header>
        <UsageLines usage={view.overall.usage} empty="No overall budget set, so nothing is admitted."/>
        <div className="button-row"><PauseButton state={view.overall.state} busy={busy} name="all brains"
          onClick={op=>act('overall',null,op,view.overall?.version??0,op==='pause'?'All goal work paused.':'Goal work resumed.')}/></div></article>}
      {view.brains.map(b=><BrainRow key={b.id} b={b} busy={busy} act={act}/>)}
    </section>
    <ResultsSection tick={tick} observed={observed}/>
  </div>;
}

/** What ALFRED's checks established for each brain result. Read-mostly: run the declared
 *  checks again, or acknowledge the exact run shown, after a confirmation. */
function ResultsSection({tick,observed}:{tick:number;observed:string}){
  const c=useConsole(),{client,fail}=c.live;
  const[view,setView]=useState<ResultsView|null>(null),[error,setError]=useState(''),[actionError,setActionError]=useState('');
  const[busy,setBusy]=useState(false),[own,setOwn]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    client.get<ResultsView>('/desk/hub/results',controller.signal).then(data=>{if(!controller.signal.aborted){setView(data);setError('');}}).catch(e=>{
      if(isAbort(e))return;setError(goalMessage(e));if(e instanceof DeskError&&e.kind==='signed_out')fail(e);
    });
    return()=>controller.abort();
  },[client,fail,observed,tick,own]);
  /* Every action is followed by a fresh read, so the card shows what the server recorded. */
  const send=(path:string,body:unknown,notice:string)=>{
    setBusy(true);setActionError('');
    client.post(path,body).then(()=>c.setNotice(notice))
      .catch(e=>{setActionError(goalMessage(e));if(e instanceof DeskError&&e.kind==='signed_out')fail(e);})
      .finally(()=>{setBusy(false);setOwn(n=>n+1);});
  };
  if(!view)return error?<section aria-label="Results and checks"><p className="sign-in-error" role="alert">{error}</p></section>:null;
  if(!view.available)return null;
  const brains=Object.keys(view.by_brain).sort();
  return <section aria-label="Results and checks"><h3 className="routine-subhead">Results and checks<span>{view.results.length}</span></h3>
    <p className="dialog-note">What ALFRED's checks established for each brain result in the last {view.window_days} days. Verified means the declared checks passed or you acknowledged the result. A result with no declared checks is never counted as verified, and a brain's own confidence or “done” is never counted.</p>
    {(actionError||error)&&<p className="sign-in-error" role="alert">{actionError||error}</p>}
    {brains.length>0&&<ul className="routine-cites" aria-label="Results per brain">{brains.map(b=><li key={b}>{brainEvidenceLine(b,view.by_brain[b])}</li>)}</ul>}
    {view.results.length?view.results.map(r=><ResultCard key={r.job} r={r} busy={busy}
      onVerify={()=>send(verifyRequest(r.job,r.runs).path,verifyRequest(r.job,r.runs).body,'Checks ran. The result shows what they found.')}
      onAcknowledge={accept=>r.last_run&&send(acknowledgeRequest(r.job,r.last_run,accept).path,acknowledgeRequest(r.job,r.last_run,accept).body,
        accept?'Acknowledged over failed checks. Recorded as your decision.':'Acknowledged. Recorded as your decision.')}/>)
      :<p className="quiet-empty">No brain results yet.</p>}
  </section>;
}

function ResultCard({r,busy,onVerify,onAcknowledge}:{r:HubResult;busy:boolean;onVerify:()=>void;onAcknowledge:(acceptFailures:boolean)=>void}){
  const[confirm,setConfirm]=useState(false);
  const goal=r.work?`Goal: ${r.work.goal_title??'no longer available'}`:'No goal';
  const failed=r.checks==='failed_checks';
  return <article className="routine-card result-card" aria-label={`Result ${r.job}`}>
    <header><span className="record-symbol"><CheckSquare size={18} weight="thin"/></span>
      <div><h3>{r.work?r.work.work:'Brain task'} · {r.brain}</h3><p>{goal} · {r.scope_class} scope · {r.job}</p></div>
      <ul className="routine-chips" aria-label={`Result ${r.job} verification`}><li className={evidenceTone(r.evidence)}>{evidenceLabel(r)}</li></ul></header>
    <p className="routine-line">{runLine(r)}</p>
    {r.last_run&&r.last_run.checks.length>0&&<ul className="result-checks">{r.last_run.checks.map(k=><li key={k.id} className={k.status}>{k.id} {k.kind.replaceAll('_',' ')}: {k.status==='unverifiable'?'could not run':k.status}</li>)}</ul>}
    {(canRunChecks(r)||canAcknowledge(r))&&<div className="button-row">
      {canRunChecks(r)&&<button type="button" className="secondary-button" disabled={busy} onClick={onVerify}>Run checks</button>}
      {canAcknowledge(r)&&!confirm&&<button type="button" className="text-button" disabled={busy} aria-label={`Acknowledge result ${r.job}`} onClick={()=>setConfirm(true)}>Acknowledge…</button>}</div>}
    {confirm&&<div className="forget-confirm" role="group" aria-label={`Confirm acknowledge result ${r.job}`}><p className="dialog-note">{acknowledgeNote(r)}</p>
      <div className="button-row"><button type="button" className="secondary-button" disabled={busy} onClick={()=>{setConfirm(false);onAcknowledge(failed);}}>
        {failed?'Accept with failed checks':`Acknowledge run ${r.last_run?.position??''}`}</button>
        <button type="button" className="text-button" onClick={()=>setConfirm(false)}>Cancel</button></div></div>}
  </article>;
}

/** The first chip is the state; the rest are cautions unless marked plain. */
function Chips({label,items,state,plain=[]}:{label:string;items:string[];state:HubState;plain?:string[]}){
  return <ul className="routine-chips" aria-label={label}>{items.map((s,i)=><li key={s} className={i===0?(state==='active'?'on':'warn'):plain.includes(s)?'':'warn'}>{s}</li>)}</ul>;
}

function UsageLines({usage,empty}:{usage:Usage;empty:string}){
  const lines=[...usageLines(usage,'daily'),...usageLines(usage,'total')];
  return lines.length?<ul className="goal-usage">{lines.map(l=><li key={l} className={/limit reached/.test(l)?'spent':/warning/.test(l)?'warn':''}>{l}</li>)}</ul>
    :<p className="routine-line">{empty}</p>;
}

function PauseButton({state,busy,name,onClick}:{state:HubState;busy:boolean;name:string;onClick:(op:Operation)=>void}){
  if(state==='stopped')return null;
  const paused=state==='paused';
  return <button type="button" className="secondary-button" aria-pressed={paused} aria-label={`${paused?'Resume':'Pause'} ${name}`} disabled={busy}
    onClick={()=>onClick(paused?'resume':'pause')}>{paused?<Play size={14}/>:<Pause size={14}/>}{paused?'Resume':'Pause'}</button>;
}

/** Pause or resume, and a stop that asks first: a stop is final. */
function Controls({state,name,busy,onControl}:{state:HubState;name:string;busy:boolean;onControl:(op:Operation)=>void}){
  const[confirm,setConfirm]=useState(false);
  if(state==='stopped')return null;
  return <><div className="button-row"><PauseButton state={state} busy={busy} name={name} onClick={onControl}/>
    {!confirm&&<button type="button" className="text-button" aria-label={`Stop ${name}`} disabled={busy} onClick={()=>setConfirm(true)}>Stop</button>}</div>
    {confirm&&<div className="forget-confirm" role="group" aria-label={`Confirm stop ${name}`}><p className="dialog-note">Stopping is final. Queued and running tasks are cancelled through the job coordinator, nothing new is admitted, and restoring an older backup keeps it stopped. Completed work is not undone.</p>
      <div className="button-row"><button type="button" className="secondary-button" disabled={busy} onClick={()=>{setConfirm(false);onControl('stop');}}>Stop for good</button>
        <button type="button" className="text-button" onClick={()=>setConfirm(false)}>Keep it</button></div></div>}</>;
}

function GoalCard({m,busy,act}:{m:MandateView;busy:boolean;act:Act}){
  const title=m.goal.title??'Goal no longer available',offset=m.budget.utc_offset_minutes;
  const chips=[stateLabel(m.state,m.state_reason),m.expired?'Past deadline':null,m.goal.status&&m.goal.status!=='active'?`Goal ${m.goal.status}`:null].filter(Boolean) as string[];
  return <article className="routine-card" aria-labelledby={`goal-${m.id}`}>
    <header><span className="record-symbol"><Target size={18} weight="thin"/></span>
      <div><h3 id={`goal-${m.id}`}>{title}</h3><p>Success test (yours, not evaluated by ALFRED): {m.success_test}</p></div>
      <Chips label={`${title} status`} items={chips} state={m.state}/></header>
    <p className="routine-line">{m.scope_class} scope · assigned to {m.assigned_brain} · deadline {localMoment(m.deadline,offset)} ({offsetLabel(offset)})</p>
    <p className="routine-line">Autonomy: {autonomyLine(m.autonomy)}</p>
    <p className="routine-line">Allowed brains: {m.brains.join(', ')} · Tools: {m.tools.length?m.tools.join(', '):'none'}</p>
    <p className="routine-line">{m.acceptance&&m.acceptance.length?`Acceptance checks (yours, run by ALFRED on every task): ${m.acceptance.map(checkLabel).join(' · ')}`
      :'No acceptance checks on this goal: its results are not counted as verified unless a task declares checks.'}</p>
    {m.schedule&&<p className="routine-line">Heartbeat {scheduleLabel(m.schedule.when).toLowerCase()} · {m.next_due?`next ${localMoment(m.next_due,m.schedule.utc_offset_minutes)}`:'none scheduled'} · {m.missed_total} missed {m.missed_total===1?'slot':'slots'} counted, not replayed</p>}
    <UsageLines usage={m.usage} empty="No limit on this goal. Brain and overall budgets still apply."/>
    {m.tasks.length>0&&<details className="routine-rules"><summary>Recent tasks</summary><ul>{m.tasks.slice(0,5).map(t=><li key={t.job}>{taskLine(t)}</li>)}</ul></details>}
    <Controls state={m.state} name={title} busy={busy} onControl={op=>act('goal',m.id,op,m.version,
      op==='pause'?`${title} paused. Its queued and running tasks were cancelled.`:op==='resume'?`${title} resumed.`:`${title} stopped.`)}/>
  </article>;
}

function BrainRow({b,busy,act}:{b:BrainView;busy:boolean;act:Act}){
  const name=b.label?`${b.label} (${b.id})`:b.id;
  const chips=[stateLabel(b.state,b.reason),b.registered?(b.locality==='cloud'?'Cloud':'Local'):'Not plugged in'];
  return <article className="routine-card" aria-label={`Brain ${b.id}`}>
    <header><span className="record-symbol"><Brain size={18} weight="thin"/></span><div><h3>{name}</h3></div>
      <Chips label={`Brain ${b.id} status`} items={chips} state={b.state} plain={['Local','Cloud']}/></header>
    <UsageLines usage={b.usage} empty="No budget for this brain. The overall budget still applies."/>
    <Controls state={b.state} name={`brain ${b.id}`} busy={busy} onControl={op=>act('brain',b.id,op,b.control_version,
      op==='pause'?`Brain ${b.id} paused.`:op==='resume'?`Brain ${b.id} resumed.`:`Brain ${b.id} stopped.`)}/>
  </article>;
}
