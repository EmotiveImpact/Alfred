import {useEffect,useState} from 'react';
import {CaretRight,Cpu} from '@phosphor-icons/react';
import {useConsole} from '../state/ConsoleProvider';
import {JOB_KINDS,eventLabel,kindLabel,readResult,reasonLabel,stateLabel,type JobKind,type JobView} from '../integration/jobs';
const time=(seconds:number)=>new Date(seconds*1000).toLocaleTimeString('en-GB');
function inputTitle(c:ReturnType<typeof useConsole>,job:JobView){
  const note=job.inputs.find(i=>i.type==='note');
  if(!note)return `${job.inputs.length} input${job.inputs.length===1?'':'s'}`;
  const record=c.state.snapshot.records.find(r=>r.id==='note:'+note.id);
  return record?`${record.title}, revision ${note.revision}`:'A note not currently visible to you';
}
/** Bounded jobs on this host: follow events, read results, cancel. Never a model, never a sandbox claim. */
export function JobsPanel(){
  const c=useConsole(),j=c.jobs,f=j.followed,owner=c.live.session?.role==='owner';
  const{show,hide}=j;
  useEffect(()=>{if(!c.connected)return;show();return hide;},[c.connected,show,hide]);
  if(!c.connected)return <p className="dialog-note">Bounded jobs run on a connected ALFRED host. This local preview has no worker and runs nothing.</p>;
  const readable=readResult(f?.result?.text);
  return <div className="jobs-panel">
    <div className="review-scope"><Cpu size={20}/><span>{j.backend?`Runs on this computer as a ${j.backend}.`:'Reading the job list…'} Results are counts or exact extracts, never model output.</span></div>
    {f&&<section className="ask-section job-follow" aria-label="Followed job">
      <h3>{f.job?`${kindLabel(f.job.kind)} · ${stateLabel(f.job.state)}`:'Reading the job…'}</h3>
      {f.job&&<p className="dialog-note">On {inputTitle(c,f.job)}. Submitted {time(f.job.created_at)}.{f.job.reason?` ${reasonLabel(f.job.reason)}`:''}</p>}
      <ol className="job-events" aria-label="Job events">{f.events.map(e=><li key={e.sequence}><span>{eventLabel(e)}</span><time>{time(e.at)}</time></li>)}</ol>
      {readable&&<div className="job-result" aria-label="Job result"><dl className="detail-list">{readable.lines.map(l=><div key={l.label}><dt>{l.label}</dt><dd>{l.value}</dd></div>)}</dl>
        {readable.selected.length>0&&<ol className="source-lines" aria-label="Extracted lines">{readable.selected.map((line,i)=><li key={i}>{line}</li>)}</ol>}
        <p className="dialog-note">{readable.basis} The stored bytes match their SHA-256; the content was not independently verified. Served from the {f.result?.served_from==='cache'?'local cache':'database record'}.</p></div>}
      {f.job?.result_removed&&<p className="dialog-note" role="status">Its result was removed with its source. The job record remains.</p>}
      {f.resultError&&<p className="dialog-note" role="status">{f.resultError}</p>}
      {owner&&f.job&&!f.job.finished&&f.job.state!=='cancel_requested'&&<button className="text-button" disabled={j.busy} onClick={()=>void j.cancel(f.id)}>Cancel this job</button>}
    </section>}
    <section className="ask-section"><h3>Recent jobs</h3>
      {j.jobs.length?<div className="record-list">{j.jobs.map(job=><button key={job.id} className={`record-row job-row ${f?.id===job.id?'active':''}`} aria-current={f?.id===job.id?'true':undefined} onClick={()=>j.follow(job.id)}>
        <span className="record-symbol"><Cpu size={17} weight="thin"/></span><span><strong>{kindLabel(job.kind)}</strong><small>{stateLabel(job.state)} · {inputTitle(c,job)} · {time(job.created_at)}</small></span><CaretRight size={16}/></button>)}</div>
      :<p className="quiet-empty">{j.loaded?(owner?'No jobs yet. Select a note and choose a bounded job in the inspector.':'No jobs you can see.'):'Reading…'}</p>}</section>
    {j.error&&<p className="sign-in-error" role="alert">{j.error}</p>}
  </div>;
}
/** Inspector control: run a first-party job on the exact revision being inspected. Owners only. */
export function RunJob({noteId,revision}:{noteId:string;revision:string}){
  const c=useConsole(),[kind,setKind]=useState<JobKind>('word_count'),[lines,setLines]=useState(5);
  const number=Number(revision),id=noteId.replace(/^note:/,'');
  if(!c.connected||c.live.session?.role!=='owner'||!Number.isInteger(number)||number<1)return null;
  const go=async()=>{if(await c.jobs.submit(kind,kind==='summarise_lines'?{max_lines:lines}:{},id,number))c.setModal('jobs');};
  return <section className="inspector-section run-job"><h3>Run a bounded job</h3><p className="dialog-note">Runs locally on revision {revision} of this note. If the note changes first, the job is refused rather than run on newer text.</p>
    <div className="inline-pair"><label>Job<select aria-label="Job kind" value={kind} onChange={e=>setKind(e.target.value as JobKind)}>{JOB_KINDS.map(k=><option key={k.id} value={k.id}>{k.label}</option>)}</select></label>
      {kind==='summarise_lines'&&<label>Lines<input aria-label="Number of lines" type="number" min={1} max={50} value={lines} onChange={e=>setLines(Math.min(50,Math.max(1,Math.trunc(Number(e.target.value))||1)))}/></label>}</div>
    <p className="dialog-note">{JOB_KINDS.find(k=>k.id===kind)?.note}</p>
    <button className="secondary-button" disabled={c.jobs.busy} onClick={()=>void go()}>Run on this revision</button>
    {c.jobs.error&&c.modal===null&&<p className="sign-in-error" role="alert">{c.jobs.error}</p>}</section>;
}
