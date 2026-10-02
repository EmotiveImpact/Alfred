import {useMemo,useState} from 'react';
import {Check} from '@phosphor-icons/react';
import {useConsole} from '../state/ConsoleProvider';
import {DeskError} from '../integration/deskClient';
import {dueLabel} from '../integration/toSnapshot';
import {type KnowledgeRecord} from '../domain/model';
const KINDS=[{id:'priority',label:'Priority'},{id:'commitment',label:'Commitment'},{id:'follow_up',label:'Follow-up'},{id:'decision',label:'Decision'},{id:'milestone',label:'Milestone'},{id:'goal',label:'Goal'}] as const;
const DONE:Record<string,string>={priority:'done',commitment:'done',follow_up:'done',milestone:'done',goal:'achieved',decision:'decided'};
const OPEN:Record<string,string>={priority:'open',commitment:'open',follow_up:'open',milestone:'open',goal:'active',decision:'proposed'};
const GROUPS:[string,string[]][]=[['Priorities',['priority']],['Commitments and follow-ups',['commitment','follow_up']],['Decisions',['decision']],['Milestones',['milestone']],['Goals',['goal']]];
const ERRORS:Record<string,string>={executive_record_changed:'This record changed. The view has been refreshed; try again.',project_not_available:'That project is no longer available to you.',recommendation_not_current:'That recommendation has changed. The view has been refreshed.',invalid_text:'Give it a short title.',control_character:'Remove the unusual characters.'};
function message(e:unknown){return e instanceof DeskError?ERRORS[e.code]??`ALFRED refused this (${e.code}).`:'ALFRED could not be reached.';}
const plain=(id:string)=>id.replace(/^exec:/,'');
/** Server-side status change with the record's exact version. */
export function useExecutiveActions(){
  const c=useConsole();
  const toggle=async(record:{id:string;version:number;kind:string;done:boolean})=>{
    try{await c.live.client.post(`/desk/executive/records/${plain(record.id)}`,{version:record.version,status:record.done?OPEN[record.kind]:DONE[record.kind]});}
    catch(e){c.setNotice(message(e));}finally{void c.live.refresh();}
  };
  const accept=async(fromRecord:string,fromVersion:number)=>{
    try{await c.live.client.post('/desk/executive/recommendations/accept',{request_id:'accept-'+Math.random().toString(36).slice(2,12),from_record:fromRecord,from_version:fromVersion});c.setNotice('Added to your priorities. It is now yours, not an inference.');}
    catch(e){c.setNotice(message(e));}finally{void c.live.refresh();}
  };
  return{toggle,accept};
}
function versionOf(r:KnowledgeRecord){const v=Number(r.provenance.revision);return Number.isFinite(v)?v:1;}
function isDone(r:KnowledgeRecord){return ['done','achieved','decided'].includes(r.status);}
export function ExecutiveRecordsPanel(){
  const c=useConsole(),{toggle}=useExecutiveActions();
  const records=useMemo(()=>c.state.snapshot.records.filter(r=>r.origin==='executive_record'),[c.state.snapshot.records]);
  const projects=useMemo(()=>c.state.snapshot.records.filter(r=>r.category==='projects'),[c.state.snapshot.records]);
  const[kind,setKind]=useState<typeof KINDS[number]['id']>('priority'),[title,setTitle]=useState(''),[project,setProject]=useState(''),[due,setDue]=useState(''),[rank,setRank]=useState('');
  const[busy,setBusy]=useState(false),[error,setError]=useState('');
  const owner=c.live.session?.role==='owner';
  const create=async()=>{setBusy(true);setError('');try{
    await c.live.client.post('/desk/executive/records',{request_id:'record-'+Math.random().toString(36).slice(2,12),kind,title:title.trim(),detail:'',
      project:project||null,due:due?Math.floor(new Date(due+'T17:00:00').getTime()/1000):null,rank:kind==='priority'&&rank?Number(rank):null,support:null});
    setTitle('');setDue('');setRank('');c.setNotice('Recorded. It appears in the panel and the graph.');void c.live.refresh();
  }catch(e){setError(message(e));}finally{setBusy(false);}};
  return <div className="executive-records">
    <p className="dialog-note">Records you write yourself. ALFRED does not infer obligations; due-soon commitments appear only as labelled recommendations.</p>
    {GROUPS.map(([label,kinds])=>{const items=records.filter(r=>kinds.includes(r.execKind??''));return <section className="ask-section" key={label}><h3>{label}</h3>
      {items.length?items.map(r=><button role="checkbox" aria-checked={isDone(r)} key={r.id} disabled={!owner} className={`task-row ${isDone(r)?'done':''}`} onClick={()=>void toggle({id:r.id,version:versionOf(r),kind:r.execKind!,done:isDone(r)})}><span className="check-ring">{isDone(r)&&<Check size={13}/>}</span><span>{r.title}</span><small>{r.summary}</small></button>)
        :<p className="quiet-empty">None recorded.</p>}</section>;})}
    {owner&&<div className="remember-form" aria-label="New executive record"><h4>Add a record</h4>
      <div className="inline-pair"><label>Kind<select value={kind} onChange={e=>setKind(e.target.value as typeof kind)}>{KINDS.map(k=><option key={k.id} value={k.id}>{k.label}</option>)}</select></label><label>Project<select value={project} onChange={e=>setProject(e.target.value)}><option value="">None</option>{projects.map(p=><option key={p.id} value={p.id}>{p.title}{p.origin==='reviewed_entity'?' (reviewed)':''}</option>)}</select></label></div>
      <label>Title<input className="inline-input" value={title} maxLength={160} onChange={e=>setTitle(e.target.value)}/></label>
      <div className="inline-pair"><label>Due<input className="inline-input" type="date" value={due} onChange={e=>setDue(e.target.value)}/></label>{kind==='priority'&&<label>Rank<input className="inline-input" type="number" min={1} max={1000} value={rank} onChange={e=>setRank(e.target.value)}/></label>}</div>
      {error&&<p className="sign-in-error" role="alert">{error}</p>}
      <div className="button-row"><button className="secondary-button" disabled={busy||!title.trim()} onClick={create}>Add record</button></div></div>}
  </div>;
}
export {dueLabel};
