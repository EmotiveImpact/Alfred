import {useEffect,useRef,useState} from 'react';
import {DeskError} from '../integration/deskClient';
import {X,LinkSimple,CaretRight,DownloadSimple} from '@phosphor-icons/react';
import {useConsole,downloadJSON} from '../state/ConsoleProvider';
import {type RecordDetail,type StatementDetail} from '../integration/ConsoleReadPort';
import {type Relationship} from '../domain/model';
import {RunJob} from './JobsPanel';
import {ExecutiveInspectorActions} from './ExecutiveWorkflows';
import {SyncConflictNotice,SourceConflicts} from './SourceSafety';
const LAYER_LABEL:Record<string,string>={note_reference:'authored link',reviewed_claim:'reviewed relationship',review_support:'supported by reviewed excerpt',executive_link:'executive link',executive_support:'cited support',executive_responsible:'responsible (your link)',fixture:''};
const ORIGIN_BADGE:Record<string,string>={authored_note:'AUTHORED NOTE · NOT A VERIFIED FACT',reviewed_entity:'REVIEWED MEMORY · YOUR JUDGEMENT',source:'SELECTED SOURCE',executive_record:'EXECUTIVE RECORD · AUTHORED BY YOU'};
function frontmatterEnd(lines:string[]){if(lines[0]?.trim()!=='---')return 0;const end=lines.findIndex((l,i)=>i>0&&l.trim()==='---');return end<0?0:end+1;}
function statementLabel(s:StatementDetail){
  if(s.usable)return 'Accepted and current';
  if(s.state==='forgotten')return 'Forgotten · value removed';
  if(s.state==='invalidated')return 'Source changed · review needed';
  if(s.withheld)return 'Withheld · support unavailable or not permitted';
  if(s.conflicts.length)return 'Conflicting reviews · withheld';
  if(!s.validNow&&s.state==='accepted')return 'Outside its valid period';
  return s.state;
}
function ForgetControl({label,path,body,confirm}:{label:string;path:string;body:object;confirm:string}){
  const c=useConsole(),[asking,setAsking]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  if(c.live.session?.role!=='owner')return null;
  if(!asking)return <button className="text-button forget-button" onClick={()=>setAsking(true)}>{label}</button>;
  const run=async()=>{setBusy(true);setError('');try{
    const r=await c.live.client.post<{conversation_answers_withdrawn:number;pending_actions_cancelled:string[]}>(path,body);
    c.setNotice(`Forgotten. ${r.conversation_answers_withdrawn} saved answer(s) withdrawn, ${r.pending_actions_cancelled.length} pending draft(s) cancelled. Not secure erasure.`);setAsking(false);void c.live.refresh();
  }catch(e){setError(e instanceof DeskError&&e.code==='memory_review_changed'?'This statement changed. Reopen it and try again.':'It could not be forgotten.');}finally{setBusy(false);}};
  return <div className="forget-confirm" role="group" aria-label="Confirm forget"><p className="dialog-note">{confirm}</p>{error&&<p className="sign-in-error" role="alert">{error}</p>}<div className="button-row"><button className="secondary-button" disabled={busy} onClick={run}>Confirm forget</button><button className="text-button" onClick={()=>setAsking(false)}>Keep</button></div></div>;
}
/** Removes a whole source from ALFRED: its indexed text and everything derived from it. Never the person's files. */
function RemoveSource({source,label}:{source:string;label:string}){
  const c=useConsole(),[asking,setAsking]=useState(false),[consent,setConsent]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  if(c.live.session?.role!=='owner')return null;
  if(!asking)return <button className="text-button forget-button" onClick={()=>setAsking(true)}>Remove this source from ALFRED</button>;
  const run=async()=>{setBusy(true);setError('');try{
    // Removing a source changes access; this is the person's own change, so keep its receipt in view.
    c.expectAccessChange();
    const r=await c.live.client.post<{notes_removed:number;reviewed_statements_invalidated:number;conversation_answers_withdrawn:number;pending_actions_cancelled:string[];job_results_deleted:string[]}>(`/desk/sources/${encodeURIComponent(source)}/forget`,{confirm:source});
    c.setNotice(`Source removed: ${r.notes_removed} notes, ${r.reviewed_statements_invalidated} reviewed statement(s) invalidated, ${r.conversation_answers_withdrawn} answer(s) withdrawn, ${r.pending_actions_cancelled.length} draft(s) cancelled, ${r.job_results_deleted.length} job result(s) deleted. Your files were not touched.`);
    setAsking(false);c.dispatch({type:'select',id:null});void c.live.refresh();
  }catch(e){setError(e instanceof DeskError&&e.code==='source_not_available'?'This source is no longer available.':'It could not be removed.');}finally{setBusy(false);}};
  return <div className="forget-confirm" role="group" aria-label="Confirm source removal"><p className="dialog-note">Removes {label} from ALFRED: its indexed text, links and history, every answer and draft built on it, and job results derived from it. Reviewed statements that relied on it are invalidated. ALFRED stops reading it. Your own files are not touched, and this is not secure erasure.</p>
    <label className="consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>I want to remove this source and everything derived from it.</span></label>
    {error&&<p className="sign-in-error" role="alert">{error}</p>}<div className="button-row"><button className="secondary-button" disabled={busy||!consent} onClick={run}>Remove source</button><button className="text-button" onClick={()=>{setAsking(false);setConsent(false);}}>Keep</button></div></div>;
}
function ConnectedProvenance({detail}:{detail:RecordDetail}){
  const c=useConsole(),{selectRecord}=c;
  if(detail.type==='note'){
    const start=frontmatterEnd(detail.lines),shown=detail.lines.slice(start,start+14);
    return <><section className="inspector-section"><h3>Provenance</h3><dl className="detail-list"><div><dt>Path</dt><dd>{detail.path}</dd></div><div><dt>Revision</dt><dd>{detail.revision}</dd></div><div><dt>SHA-256</dt><dd className="hash">{detail.sha256.slice(0,16)}…</dd></div><div><dt>Basis</dt><dd>Authored text, not verified</dd></div></dl>
      <ol className="source-lines" start={start+1} aria-label="Exact source lines">{shown.map((line,i)=><li key={i}>{line||' '}</li>)}</ol>
      {detail.lines.length>start+14&&<p className="dialog-note">Showing lines {start+1} to {start+shown.length} of {detail.lines.length}{detail.truncated?' (inspection limit reached)':''}.</p>}</section><RunJob noteId={detail.id} revision={detail.revision}/></>;
  }
  if(detail.type==='exec'){
    const project=detail.project?c.state.snapshot.records.find(r=>r.id===detail.project):undefined;
    return <section className="inspector-section"><h3>Executive record</h3><dl className="detail-list"><div><dt>Kind</dt><dd>{detail.kind.replace('_','-')}</dd></div><div><dt>Status</dt><dd>{detail.status}</dd></div><div><dt>Due</dt><dd>{detail.due?`${new Date(detail.due).toLocaleDateString('en-GB')}${detail.overdue?' · overdue':''}`:'No date'}</dd></div>{detail.responsible&&<div><dt>Responsible</dt><dd>{detail.responsible}{detail.responsibleState==='unavailable'?' · link unavailable':''}</dd></div>}{detail.choice&&<div><dt>Decided</dt><dd>{detail.choice.label??'Yes'}</dd></div>}<div><dt>Basis</dt><dd>Your authored record</dd></div></dl>
      {detail.detail&&<p>{detail.detail}</p>}
      {project&&<button className="text-button" onClick={()=>selectRecord(project.id)}>Project: {project.title}</button>}
      {detail.support&&(detail.support.state==='current'?<><blockquote>{detail.support.quote}</blockquote><button className="text-button" onClick={()=>selectRecord('note:'+detail.support!.note_id)}>{detail.support.title}, {detail.support.start_line===detail.support.end_line?`line ${detail.support.start_line}`:`lines ${detail.support.start_line}–${detail.support.end_line}`}</button></>
        :<p className="dialog-note">The cited lines have {detail.support.state==='changed'?'changed since this record was written':'become unavailable'}. The record is kept; check it against the current source.</p>)}
      <ExecutiveInspectorActions id={detail.id} kind={detail.kind}/></section>;
  }
  if(detail.type==='source')return <section className="inspector-section"><h3>Source status</h3><dl className="detail-list"><div><dt>Status</dt><dd>{detail.status}</dd></div><div><dt>Checked</dt><dd>{new Date(detail.checkedAt).toLocaleString('en-GB')}</dd></div><div><dt>Notes</dt><dd>{detail.notes}</dd></div><div><dt>Issues</dt><dd>{detail.issues.length}</dd></div></dl>{detail.issues.slice(0,4).map((issue,i)=><p className="dialog-note" key={i}>{issue.code}{issue.path?` · ${issue.path}`:''}</p>)}<SourceConflicts sourceId={detail.id}/><RemoveSource source={detail.id.slice('source:'.length)} label={detail.label}/></section>;
  return <section className="inspector-section"><h3>Reviewed statements</h3>{detail.sameNameEntities.length>0&&<p className="dialog-note">{detail.sameNameEntities.length} other record{detail.sameNameEntities.length>1?'s share':' shares'} this name. They are kept separate.</p>}
    {detail.statements.length?detail.statements.map(s=><div className={`statement ${s.usable?'usable':'withheld'}`} key={s.id}><p><strong>{s.predicate.replaceAll('_',' ')}</strong> {s.value??s.object?.name??''}</p><small>{statementLabel(s)}</small>
      {s.support?<><blockquote>{s.support.quote}</blockquote><button className="text-button" onClick={()=>selectRecord(s.support!.noteId)}>{s.support.title}, {s.support.startLine===s.support.endLine?`line ${s.support.startLine}`:`lines ${s.support.startLine}–${s.support.endLine}`}</button></>:s.state!=='forgotten'&&<p className="dialog-note">Original support is not currently available.</p>}
      {s.state!=='forgotten'&&<ForgetControl label="Forget this statement" path={`/desk/memory/claims/${s.id}/forget`} body={{version:s.version}} confirm="Removes the reviewed value from ALFRED's current records, withdraws saved answers that used it and cancels undecided drafts. Audit entries, older backups and completed drafts remain."/>}</div>):<p>No statements recorded for this record.</p>}
    <ForgetControl label="Forget this record and its statements" path={`/desk/memory/entities/${detail.id.slice('entity:'.length)}/forget`} body={{}} confirm="Removes this record's name and every reviewed statement that mentions it from current records. A restore from an older backup replays this forget."/></section>;
}
function InspectorBody(){
  const{selected,relationships,records,dispatch,selectRecord,connected,detail,state}=useConsole(),heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{const previous=document.activeElement as HTMLElement|null;heading.current?.focus();return()=>{if(previous?.isConnected)previous.focus();};},[]);
  if(!selected)return null;
  const edges=relationships.filter(e=>e.from===selected.id||e.to===selected.id);
  const neighbour=(e:Relationship)=>records.find(r=>r.id===(e.from===selected.id?e.to:e.from));
  const exportRecord=()=>connected?downloadJSON({mode:'connected',workspace:state.snapshot.workspaceId,observedAt:state.snapshot.observedAt,record:selected,detail:detail.status==='ready'?detail.detail:null,relationships:edges},`ALFRED-${selected.id.replace(/[^A-Za-z0-9_-]/g,'-')}.json`):downloadJSON({mode:'demo',record:selected,relationships:edges},`ALFRED-${selected.id}-demo.json`);
  return <><header className="inspector-header"><span className="eyebrow">{selected.category} / inspect</span><button className="icon-button" aria-label="Close record inspector" onClick={()=>dispatch({type:'select',id:null})}><X size={20}/></button></header><div className="inspector-body">
    <span className="demo-badge">{connected?(selected.sourceKind==='connector_export'?'IMPORTED EXPORT · UNCHECKED REPORT':ORIGIN_BADGE[selected.origin??'']??'RECORD'):'DEMONSTRATION RECORD'}</span><h2 ref={heading} tabIndex={-1}>{selected.title}</h2><p className="inspector-summary">{selected.summary}</p>
    {connected?<>{detail.status==='loading'&&<p className="dialog-note" role="status">Reading the current record…</p>}{detail.status==='unavailable'&&<p className="dialog-note" role="status">{detail.message}</p>}<SyncConflictNotice record={selected}/>{detail.status==='ready'&&detail.id===selected.id&&<ConnectedProvenance detail={detail.detail}/>}</>
    :<><section className="inspector-section"><h3>Context</h3><p>{selected.detail}</p></section><section className="inspector-section"><h3>Provenance</h3><dl className="detail-list"><div><dt>Source</dt><dd>{selected.provenance.label}</dd></div><div><dt>Revision</dt><dd>{selected.provenance.revision}</dd></div><div><dt>Basis</dt><dd>{selected.provenance.basis}</dd></div><div><dt>Workspace</dt><dd>{selected.scope}</dd></div></dl><blockquote>{selected.provenance.excerpt}</blockquote></section></>}
    <section className="inspector-section"><h3>Explicit relationships</h3>{edges.length?edges.map(e=>{const other=neighbour(e);return <button className="linked-record" key={e.id} onClick={()=>other&&selectRecord(other.id)}><LinkSimple size={17}/><span><small>{connected?`${LAYER_LABEL[e.layer??'']} · ${e.relation.replaceAll('_',' ')}`:e.relation.replaceAll('_',' ')}</small>{other?.title}</span><CaretRight size={14}/></button>;}):<p>{connected?'No supported relationships for this record. Background particles are decorative, not relationships.':'No explicit links in this fixture. Background particles are decorative, not relationships.'}</p>}</section>
    <button className="secondary-button export-button" onClick={exportRecord}><DownloadSimple size={17}/>Export record</button></div></>;
}
export function RecordInspector(){const{selected}=useConsole();return selected?<aside className="inspector" aria-label="Record inspector"><InspectorBody/></aside>:null;}
