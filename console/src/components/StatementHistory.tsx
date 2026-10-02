import {useEffect,useState} from 'react';
import {useConsole} from '../state/ConsoleProvider';
import {DeskError} from '../integration/deskClient';
import {type StatementDetail} from '../integration/ConsoleReadPort';
import {type Decision,type StatementHistory,type StatementSummary,DECIDED,HIDDEN_LABEL,formatTime,historyLine,predicateLabel,validPeriodLabel,valueText} from '../domain/temporal';
import {reviewMessage} from './MemoryReview';
import '../review.css';

const seconds=(value:string|null|undefined)=>value?Math.floor(new Date(value).getTime()/1000):null;
/** The value of a neighbouring statement as the inspector may show it now. */
export function detailValue(s:Pick<StatementDetail,'state'|'withheld'|'value'|'object'>){
  if(s.state==='forgotten')return HIDDEN_LABEL.forgotten;
  if(s.state==='invalidated')return HIDDEN_LABEL.support_changed;
  if(s.withheld)return HIDDEN_LABEL.withheld;
  return s.value??s.object?.name??'No value';
}
function Lineage({title,items}:{title:string;items:StatementSummary[]}){
  if(!items.length)return null;
  return <div className="lineage"><h4>{title}</h4><ol>{items.map(x=><li key={x.claim_id}>{predicateLabel(x.predicate)} · {valueText(x)}<small>{x.state} · {validPeriodLabel(x.valid_from,x.valid_until)}{x.reviewed?` · reviewed ${formatTime(x.reviewed)}`:''}</small></li>)}</ol></div>;
}
function HistoryList({data}:{data:StatementHistory}){
  return <>
    <ol className="history-list" aria-label="Recorded history">{data.entries.map(e=>{const line=historyLine(e);return <li key={e.seq} data-state={e.state}><strong>{line.label}</strong><span>{line.when} · {line.who}</span>{line.notes&&<small>{line.notes}</small>}</li>;})}</ol>
    {!data.recorded_from_start&&<p className="review-note">This statement predates recorded history. Its earlier steps were reconstructed from older records; a time ALFRED cannot know is shown as “no later than”.</p>}
    <Lineage title="Replaces" items={data.lineage.replaces}/>
    <Lineage title="Replaced by" items={data.lineage.replaced_by}/>
    <p className="review-note">The history keeps identifiers, states and times, never a statement’s value.</p>
  </>;
}
/**
 * Valid period, recorded time, lineage, disputes and conflicts for one reviewed statement in the
 * inspector, with its recorded history on request. Decisions carry the statement's exact version.
 */
export function StatementTemporal({s,siblings}:{s:StatementDetail;siblings:readonly StatementDetail[]}){
  const c=useConsole(),owner=c.live.session?.role==='owner',revision=c.state.snapshot.dataRevision,{client,fail}=c.live;
  const[open,setOpen]=useState(false),[history,setHistory]=useState<{status:'idle'|'loading'|'ready'|'error';data?:StatementHistory;message?:string}>({status:'idle'});
  const[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{
    if(!open)return;
    const controller=new AbortController();setHistory(h=>({status:'loading',data:h.data}));
    client.get<StatementHistory>(`/desk/memory/claims/${encodeURIComponent(s.id)}/history`,controller.signal).then(data=>{if(!controller.signal.aborted)setHistory({status:'ready',data});}).catch(e=>{
      if(e instanceof DOMException&&e.name==='AbortError')return;setHistory({status:'error',message:reviewMessage(e)});if(e instanceof DeskError&&e.kind==='signed_out')fail(e);
    });
    return()=>controller.abort();
  },[client,fail,open,s.id,s.version,revision]);
  const decide=async(decision:Decision)=>{
    setBusy(true);setError('');
    try{await client.post(`/desk/memory/claims/${encodeURIComponent(s.id)}/review`,{version:s.version,decision,replaces_id:null,replaces_version:null});c.setNotice(DECIDED[decision]);}
    catch(e){setError(reviewMessage(e));if(e instanceof DeskError&&e.kind==='signed_out')fail(e);}
    finally{setBusy(false);void c.live.refresh();}
  };
  const from=seconds(s.validFrom),until=seconds(s.validUntil),recorded=seconds(s.recordedAt),reviewed=seconds(s.reviewedAt);
  const replaces=siblings.find(x=>x.id===s.replacesId),replacedBy=siblings.find(x=>x.id===s.replacedBy);
  return <div className="statement-temporal">
    <p>{validPeriodLabel(from,until)}{from!==null||until!==null?(s.validNow?' · valid now':' · not valid now'):''}</p>
    {recorded!==null&&<p>Recorded {formatTime(recorded)}{reviewed!==null?` · last reviewed ${formatTime(reviewed)}`:''}</p>}
    {s.replacesId&&<p>Replaces {replaces?`“${detailValue(replaces)}” (${replaces.state})`:'an earlier statement'}</p>}
    {s.replacedBy&&<p>Replaced by {replacedBy?`“${detailValue(replacedBy)}” (${replacedBy.state})`:'a later statement'}</p>}
    {s.state==='disputed'&&<p className="temporal-warning">You disputed this statement. It is kept but not used in answers.</p>}
    {s.conflicts.length>0&&<p className="temporal-warning">Conflicts with {s.conflicts.length} other accepted statement{s.conflicts.length>1?'s':''} for an overlapping period. Neither is used until you resolve it.</p>}
    <details className="statement-history" onToggle={e=>setOpen((e.currentTarget as HTMLDetailsElement).open)}><summary>History and lineage</summary>
      {history.status==='loading'&&!history.data&&<p className="review-note" role="status">Reading the recorded history…</p>}
      {history.status==='error'&&<p className="sign-in-error" role="alert">{history.message}</p>}
      {history.data&&<HistoryList data={history.data}/>}
    </details>
    {owner&&s.state==='accepted'&&<div className="temporal-actions"><button className="text-button" disabled={busy} onClick={()=>decide('dispute')}>Dispute</button><button className="text-button" disabled={busy} onClick={()=>decide('withdraw')}>Withdraw</button></div>}
    {owner&&(s.state==='proposed'||s.state==='disputed')&&<button className="text-button" onClick={()=>c.openMemory('queue')}>Decide in the review queue</button>}
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
  </div>;
}
