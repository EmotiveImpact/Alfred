import {useCallback,useEffect,useMemo,useState} from 'react';
import {ClockCounterClockwise,WarningCircle} from '@phosphor-icons/react';
import {useConsole} from '../state/ConsoleProvider';
import {DeskError} from '../integration/deskClient';
import {type AsOfItem,type AsOfReport,type Decision,type MemoryClaim,type MemoryView,DECIDED,REVIEW_ERRORS,acceptedSince,asOfPath,claimValue,dayEnd,
  entityLabel,formatTime,namesakeIds,notHeldSummary,predicateLabel,reviewBody,reviewQueue,supersedeCandidates,toDayInput,validPeriodLabel,
  validPeriodPayload,valueText} from '../domain/temporal';
import '../review.css';

const isAbort=(e:unknown)=>e instanceof DOMException&&e.name==='AbortError';
export function reviewMessage(e:unknown){return e instanceof DeskError?REVIEW_ERRORS[e.code]??`ALFRED refused this (${e.code}).`:'ALFRED could not be reached.';}

/** The person's own reviewed-memory ledger, re-read whenever the projection changes or after a decision here. */
export function useMemoryView(){
  const c=useConsole(),{client,fail}=c.live,revision=c.state.snapshot.dataRevision;
  const[state,setState]=useState<{status:'loading'|'ready'|'error';view?:MemoryView;message?:string}>({status:'loading'});
  const[tick,setTick]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    client.get<MemoryView>('/desk/memory',controller.signal).then(view=>{if(!controller.signal.aborted)setState({status:'ready',view});}).catch(e=>{
      if(isAbort(e))return;setState({status:'error',message:reviewMessage(e)});if(e instanceof DeskError&&e.kind==='signed_out')fail(e);
    });
    return()=>controller.abort();
  },[client,fail,revision,tick]);
  return {...state,refresh:useCallback(()=>setTick(t=>t+1),[])};
}

function ProposalCard({claim,view,owner,onDecided}:{claim:MemoryClaim;view:MemoryView;owner:boolean;onDecided:(refusal:string)=>void}){
  const c=useConsole();
  const entities=useMemo(()=>Object.fromEntries(view.entities.map(e=>[e.id,e])),[view.entities]),shared=useMemo(()=>namesakeIds(view.entities),[view.entities]);
  const[from,setFrom]=useState(toDayInput(claim.valid_from)),[until,setUntil]=useState(toDayInput(claim.valid_until));
  const[replacing,setReplacing]=useState(false),[replaces,setReplaces]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const candidates=supersedeCandidates(claim,view.claims),subject=entities[claim.subject_id];
  const proposed=claim.state==='proposed',blocked=claim.withheld||!claim.source;
  const decide=async(decision:Decision)=>{
    setError('');
    let period=null;
    if(proposed&&(decision==='accept'||decision==='supersede')){const p=validPeriodPayload(from,until);if('error' in p){setError(p.error);return;}period=p;}
    const prior=decision==='supersede'?view.claims.find(x=>x.id===replaces)??null:null;
    if(decision==='supersede'&&!prior){setError('Choose the statement this one replaces.');return;}
    setBusy(true);let refusal='';
    try{await c.live.client.post(`/desk/memory/claims/${encodeURIComponent(claim.id)}/review`,reviewBody(claim,decision,prior,period));c.setNotice(DECIDED[decision]);}
    catch(e){refusal=reviewMessage(e);if(e instanceof DeskError&&e.kind==='signed_out')c.live.fail(e);}
    // A refusal is shown by the queue: the refreshed statement may move or change version.
    finally{setBusy(false);onDecided(refusal);void c.live.refresh();}
  };
  const label=`${proposed?'Proposed':'Disputed'}: ${subject?.name??'record'} ${predicateLabel(claim.predicate)}`;
  return <article className="review-card" aria-label={label}>
    <header><span className={`review-state ${claim.state}`}>{proposed?'Proposed':'Disputed'}</span><strong>{entityLabel(subject,shared)}</strong></header>
    <p className="review-statement">{predicateLabel(claim.predicate)} · <b>{claimValue(claim,entities,shared)}</b></p>
    {subject&&shared.has(subject.id)&&<p className="review-note">Another record shares this name. They are kept separate; this decision applies to {subject.id} only.</p>}
    {claim.source?<><blockquote>{claim.source.quote}</blockquote><button className="text-button" onClick={()=>{c.selectRecord('note:'+claim.source!.note_id);c.setModal(null);}}>{claim.source.title}, {claim.source.start_line===claim.source.end_line?`line ${claim.source.start_line}`:`lines ${claim.source.start_line} to ${claim.source.end_line}`}</button></>
      :<p className="review-note">Its support is unavailable or not permitted now, so it cannot be decided until access returns.</p>}
    <p className="review-meta">Proposed {formatTime(claim.created)}{claim.memory_type?` · ${claim.memory_type}`:''}{claim.retention_until?` · forgotten after ${formatTime(claim.retention_until)}`:''} · {validPeriodLabel(claim.valid_from,claim.valid_until)}</p>
    {owner&&!blocked&&<>
      {proposed&&<fieldset className="valid-period"><legend>Valid period</legend>
        <label>Holds from<input type="date" value={from} onChange={e=>setFrom(e.target.value)}/></label>
        <label>Holds until<input type="date" value={until} onChange={e=>setUntil(e.target.value)}/></label>
        <small>Leave empty for no limit. A statement holds until the start of its “until” day. The period is fixed once you decide.</small></fieldset>}
      {replacing&&(candidates.length?<label className="replace-choice">Replaces<select value={replaces} onChange={e=>setReplaces(e.target.value)}><option value="">Choose the earlier statement…</option>
          {candidates.map(x=><option key={x.id} value={x.id}>{claimValue(x,entities,shared)} · {x.state} · {validPeriodLabel(x.valid_from,x.valid_until)}</option>)}</select></label>
        :<p className="review-note">There is no accepted, disputed or invalidated statement of this kind about this record to replace.</p>)}
      <div className="button-row review-actions">
        {replacing?<><button className="primary-button" disabled={busy||!replaces} onClick={()=>decide('supersede')}>Accept as replacement</button><button className="text-button" onClick={()=>{setReplacing(false);setReplaces('');}}>Cancel replacement</button></>
          :<><button className="primary-button" disabled={busy} onClick={()=>decide('accept')}>Accept</button>
            {!claim.replaces_id&&<button className="secondary-button" disabled={busy} onClick={()=>setReplacing(true)}>Replace an earlier statement…</button>}
            {proposed&&<button className="text-button" disabled={busy} onClick={()=>decide('dispute')}>Dispute</button>}
            <button className="text-button" disabled={busy} onClick={()=>decide('withdraw')}>Withdraw</button></>}
      </div></>}
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
  </article>;
}

function ReviewQueue(){
  const c=useConsole(),memory=useMemoryView(),owner=c.live.session?.role==='owner',[refusal,setRefusal]=useState('');
  const decided=useCallback((message:string)=>{setRefusal(message);memory.refresh();},[memory.refresh]);
  if(memory.status==='loading'&&!memory.view)return <p className="dialog-note" role="status">Reading your reviewed memory…</p>;
  if(!memory.view)return <p className="sign-in-error" role="alert">{memory.message}</p>;
  const view=memory.view,queue=reviewQueue(view.claims);
  return <div className="review-queue">
    <p className="dialog-note">Statements wait here until you decide. Accepting records your judgement; it is not a verified fact and grants no authority. Every decision is checked against the statement’s current version.</p>
    {!owner&&<p className="review-note">Only the owner who proposed a statement can review it.</p>}
    {refusal&&<p className="sign-in-error review-refusal" role="alert">{refusal}</p>}
    <section aria-label="Proposed statements"><h3>Proposed <span>{queue.proposed.length}</span></h3>
      {queue.proposed.length?queue.proposed.map(x=><ProposalCard key={`${x.id}:${x.version}`} claim={x} view={view} owner={owner} onDecided={decided}/>)
        :<p className="quiet-empty">Nothing is waiting. Statements you capture with “Remember this…” appear here until you decide.</p>}</section>
    {queue.disputed.length>0&&<section aria-label="Disputed statements"><h3>Disputed <span>{queue.disputed.length}</span></h3>
      <p className="review-note">A disputed statement is kept but not used. Accept it again, or withdraw it.</p>
      {queue.disputed.map(x=><ProposalCard key={`${x.id}:${x.version}`} claim={x} view={view} owner={owner} onDecided={decided}/>)}</section>}
  </div>;
}

function AsOfRow({item,shared,note}:{item:AsOfItem;shared:ReadonlySet<string>;note?:string}){
  const conflicts=item.conflicts_then?.length??0,possible=item.possible_conflicts_then?.length??0;
  return <div className={`asof-item ${item.value_hidden?'hidden-value':''}`}>
    <p><strong>{entityLabel(item.subject,shared)}</strong> {predicateLabel(item.predicate)} · {valueText(item,shared)}</p>
    <small>{[acceptedSince(item),validPeriodLabel(item.valid_from,item.valid_until),`now ${item.state_now}`].filter(Boolean).join(' · ')}</small>
    {note&&<small>{note}</small>}
    {conflicts>0&&<small className="asof-warning">Conflicted then with {conflicts} other accepted statement{conflicts>1?'s':''} under the single-value rule.</small>}
    {possible>0&&<small className="asof-warning">May have conflicted with {possible} statement{possible>1?'s':''} whose value is now removed or withheld.</small>}
    {item.availability_then&&<small className="asof-warning">ALFRED had noticed its support was unavailable or not permitted by then.</small>}
  </div>;
}

function AsOfView(){
  const c=useConsole(),{client,fail}=c.live,revision=c.state.snapshot.dataRevision;
  const today=toDayInput(Math.floor(Date.now()/1000));
  const[day,setDay]=useState(today),[validDay,setValidDay]=useState(''),[query,setQuery]=useState<{at:number;valid:number|null}|null>(null);
  const[state,setState]=useState<{status:'idle'|'loading'|'ready'|'error';report?:AsOfReport;message?:string}>({status:'idle'});
  const[shared,setShared]=useState<ReadonlySet<string>>(new Set());
  useEffect(()=>{
    if(!query)return;
    const controller=new AbortController();setState(s=>({status:'loading',report:s.report}));
    // Re-read when access or data changes, so a value withheld now is hidden in the report too.
    Promise.all([client.get<AsOfReport>(asOfPath(query.at,query.valid),controller.signal),client.get<MemoryView>('/desk/memory',controller.signal)]).then(([report,view])=>{
      if(controller.signal.aborted)return;setShared(namesakeIds(view.entities));setState({status:'ready',report});
    }).catch(e=>{if(isAbort(e))return;setState({status:'error',message:reviewMessage(e)});if(e instanceof DeskError&&e.kind==='signed_out')fail(e);});
    return()=>controller.abort();
  },[client,fail,query,revision]);
  const show=(e:React.FormEvent)=>{
    e.preventDefault();const now=Math.floor(Date.now()/1000),at=dayEnd(day,now);
    if(at===null){setState({status:'error',message:'Choose a day.'});return;}
    const valid=validDay?dayEnd(validDay,Number.MAX_SAFE_INTEGER):null;setQuery({at,valid});
  };
  const report=state.report;
  return <div className="asof-view">
    <form className="asof-form" onSubmit={show}>
      <label>Held on<input type="date" value={day} max={today} onChange={e=>setDay(e.target.value)} required/></label>
      <label>Valid on <small>(optional)</small><input type="date" value={validDay} onChange={e=>setValidDay(e.target.value)}/></label>
      <button className="secondary-button" type="submit"><ClockCounterClockwise size={16}/>Show what I held</button>
    </form>
    {state.status==='idle'&&<p className="dialog-note">Choose a day to see which statements you had accepted then and which were valid then, from ALFRED’s own records.</p>}
    {state.status==='loading'&&!report&&<p className="dialog-note" role="status">Reading the recorded history…</p>}
    {state.status==='error'&&<p className="sign-in-error" role="alert">{state.message}</p>}
    {report&&<section className="asof-report" aria-label="Historical report">
      <div className="review-scope"><WarningCircle size={18}/><span>{report.label}</span></div>
      <p className="review-meta">Held on {formatTime(report.at)}{report.clamped_to_now?' (now)':''} · valid on {formatTime(report.valid_at)} · read {formatTime(report.generated_at)}</p>
      <h3>Accepted and valid then <span>{report.held.length}</span></h3>
      {report.held.length?report.held.map(x=><AsOfRow key={x.claim_id} item={x} shared={shared}/>):<p className="quiet-empty">No accepted statement was valid then.</p>}
      {report.accepted_outside_valid_period.length>0&&<><h3>Accepted then, outside their valid period <span>{report.accepted_outside_valid_period.length}</span></h3>
        {report.accepted_outside_valid_period.map(x=><AsOfRow key={x.claim_id} item={x} shared={shared}/>)}</>}
      {report.uncertain.length>0&&<><h3>ALFRED’s records cannot say <span>{report.uncertain.length}</span></h3>
        <p className="review-note">These statements predate recorded history. Their state changed at a time ALFRED cannot know, so they are not counted either way.</p>
        {report.uncertain.map(x=><AsOfRow key={x.claim_id} item={x} shared={shared} note={x.state_then?`Last known state before then: ${x.state_then}`:undefined}/>)}</>}
      {notHeldSummary(report)&&<p className="review-meta">Not held then: {notHeldSummary(report)}.</p>}
      <p className="dialog-note">{report.current_answers}</p>
    </section>}
  </div>;
}

/** Reviewed memory: the review queue and the as-of report. Connected mode only; the demonstration has no ledger. */
export function MemoryReview(){
  const c=useConsole(),[tab,setTab]=useState<'queue'|'asof'>(c.memoryTab);
  if(!c.connected)return <p className="dialog-note">Reviewed memory needs the connected ALFRED server. This demonstration has no review ledger.</p>;
  const tabs=[{id:'queue' as const,label:'Review queue'},{id:'asof' as const,label:'As of a date'}];
  return <div className="memory-review">
    <div className="exec-tabs" role="tablist" aria-label="Reviewed memory views">
      {tabs.map(t=><button key={t.id} role="tab" id={`memory-tab-${t.id}`} aria-selected={tab===t.id} aria-controls={`memory-panel-${t.id}`} onClick={()=>setTab(t.id)}>{t.label}</button>)}
    </div>
    <div role="tabpanel" id={`memory-panel-${tab}`} aria-labelledby={`memory-tab-${tab}`}>{tab==='queue'?<ReviewQueue/>:<AsOfView/>}</div>
  </div>;
}
