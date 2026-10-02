import {useMemo,useState} from 'react';
import {useConsole} from '../state/ConsoleProvider';
import {DeskError} from '../integration/deskClient';
import {type Evidence} from '../state/useAsk';
const ENTITY_KINDS=['project','person','organisation','decision','commitment','event','asset'] as const;
const PREDICATES:{id:string;label:string;object:boolean}[]=[{id:'status',label:'Status',object:false},{id:'scheduled_for',label:'Scheduled for',object:false},{id:'decision',label:'Decision',object:false},{id:'responsible_person',label:'Responsible person',object:true},{id:'depends_on',label:'Depends on',object:true}];
const TYPES=['semantic','episodic','preference','commitment','procedural'] as const;
const RETENTION:{label:string;days:number|null}[]=[{label:'Keep until I forget it',days:null},{label:'30 days',days:30},{label:'90 days',days:90},{label:'One year',days:365}];
interface Preview{scope:string;memory_type:string;retention_until:number|null;subject:string;predicate:string;value:string|null;object:string|null;source:{path:string;title:string;start_line:number;end_line:number;quote:string}|null}
function slug(name:string){return (name.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,40)||'record')+'-'+Math.random().toString(36).slice(2,8);}
const ERRORS:Record<string,string>={memory_source_changed:'The source changed. Ask again, then remember from the current text.',invalid_memory_source_range:'Choose at most eight lines inside the excerpt.',memory_object_kind:'That record cannot be the object of this statement.',inbox_write_not_granted:'Inbox notes need an explicit write grant for this source.',inbox_destination_exists:'A note with that name already exists. Choose another name.',invalid_inbox_filename:'Use a simple name ending in .md.'};
function message(e:unknown){return e instanceof DeskError?ERRORS[e.code]??`ALFRED refused this (${e.code}).`:'ALFRED could not be reached.';}
/**
 * "Remember this": an editable proposal from exact lines. Capturing never accepts it, and
 * accepting it never grants authority. An inbox note is a separate, approval-bound proposal.
 */
export function RememberForm({evidence,turnId,onClose}:{evidence:Evidence;turnId:string;onClose:()=>void}){
  const c=useConsole(),entities=useMemo(()=>c.state.snapshot.records.filter(r=>r.origin==='reviewed_entity'),[c.state.snapshot.records]);
  const note=c.state.snapshot.records.find(r=>r.id==='note:'+evidence.note_id),source=c.state.snapshot.records.find(r=>r.id===note?.sourceId);
  const[subject,setSubject]=useState(entities[0]?.id.replace(/^entity:/,'')??'new'),[newName,setNewName]=useState(''),[newKind,setNewKind]=useState<typeof ENTITY_KINDS[number]>('project');
  const[predicate,setPredicate]=useState('status'),[value,setValue]=useState(''),[object,setObject]=useState('');
  const[start,setStart]=useState(evidence.start_line),[end,setEnd]=useState(Math.min(evidence.end_line,evidence.start_line+7));
  const[type,setType]=useState<typeof TYPES[number]>('semantic'),[retention,setRetention]=useState(0);
  const[busy,setBusy]=useState(false),[error,setError]=useState(''),[made,setMade]=useState<{id:string;preview:Preview}|null>(null),[decided,setDecided]=useState('');
  const[filename,setFilename]=useState(''),[content,setContent]=useState('');
  const isObject=PREDICATES.find(p=>p.id===predicate)!.object;
  const capture=async()=>{setBusy(true);setError('');try{
    let subjectId=subject;
    if(subject==='new'){if(!newName.trim()){setError('Name the new record.');return;}subjectId=slug(newName);await c.live.client.post('/desk/memory/entities',{id:subjectId,kind:newKind,name:newName.trim()});}
    const r=await c.live.client.post<{id:string;preview:Preview}>('/desk/memory/capture',{request_id:'capture-'+Math.random().toString(36).slice(2,12),subject_id:subjectId,predicate,
      object_id:isObject?object.replace(/^entity:/,''):null,value:isObject?null:value.trim(),valid_from:null,valid_until:null,
      evidence:{note_id:evidence.note_id,sha256:evidence.sha256,revision:evidence.revision,start_line:start,end_line:end},
      memory_type:type,retention_days:RETENTION[retention].days,captured_from:{turn_id:turnId,note_id:evidence.note_id}});
    setMade(r);setFilename(`${r.preview.subject.replace(/[^A-Za-z0-9 _.-]/g,'').trim().slice(0,60)||'Note'}.md`);
    setContent(`# ${r.preview.subject}\n\n${r.preview.predicate.replaceAll('_',' ')}: ${r.preview.value??r.preview.object??''}\n\nSource: ${evidence.path}, lines ${start} to ${end}.\n`);
  }catch(e){setError(message(e));}finally{setBusy(false);}};
  const review=async(decision:'accept'|'withdraw')=>{if(!made)return;setBusy(true);setError('');try{
    await c.live.client.post(`/desk/memory/claims/${made.id}/review`,{version:1,decision,replaces_id:null,replaces_version:null});
    setDecided(decision==='accept'?'Accepted as your reviewed statement. It is a judgement, not a verified fact.':'Withdrawn. Nothing was remembered.');void c.live.refresh();
  }catch(e){setError(message(e));}finally{setBusy(false);}};
  const proposeNote=async()=>{if(!source?.sourceId&&!note?.sourceId)return;setBusy(true);setError('');try{
    await c.live.client.post('/desk/inbox/proposals',{request_id:'inbox-'+Math.random().toString(36).slice(2,12),source:(note?.sourceId??'').replace(/^source:/,''),filename,content});
    c.setNotice('Inbox note proposed. Approve the exact file in Approvals. Nothing has been written yet.');void c.live.refresh();
  }catch(e){setError(message(e));}finally{setBusy(false);}};
  if(made)return <div className="remember-form" aria-label="Remember this preview">
    <h4>Preview before it becomes memory</h4>
    <dl className="detail-list"><div><dt>Workspace</dt><dd>{made.preview.scope}</dd></div><div><dt>Statement</dt><dd>{made.preview.subject} · {made.preview.predicate.replaceAll('_',' ')} · {made.preview.value??made.preview.object}</dd></div><div><dt>Memory type</dt><dd>{made.preview.memory_type}</dd></div><div><dt>Retention</dt><dd>{made.preview.retention_until?`Forgotten after ${new Date(made.preview.retention_until*1000).toLocaleDateString('en-GB')}`:'Kept until you forget it'}</dd></div><div><dt>Source</dt><dd>{made.preview.source?`${made.preview.source.path}, lines ${made.preview.source.start_line} to ${made.preview.source.end_line}`:'Unavailable'}</dd></div></dl>
    {made.preview.source&&<blockquote>{made.preview.source.quote}</blockquote>}
    {decided?<p className="dialog-note" role="status">{decided}</p>:<div className="button-row"><button className="primary-button" disabled={busy} onClick={()=>review('accept')}>Accept as my reviewed statement</button><button className="text-button" disabled={busy} onClick={()=>review('withdraw')}>Withdraw</button></div>}
    {source?.inboxWritable?<details className="draft-proposal"><summary>Also propose an inbox note</summary><p className="dialog-note">Creates ALFRED/Inbox/{filename||'…'} only after you approve the exact file. Never overwrites.</p>
      <label className="sr-only" htmlFor="inbox-name">Inbox note name</label><input id="inbox-name" className="inline-input" value={filename} maxLength={83} onChange={e=>setFilename(e.target.value)}/>
      <label className="sr-only" htmlFor="inbox-content">Inbox note text</label><textarea id="inbox-content" rows={5} value={content} maxLength={16000} onChange={e=>setContent(e.target.value)}/>
      <button className="secondary-button" disabled={busy||!filename.endsWith('.md')||!content.trim()} onClick={proposeNote}>Propose inbox note</button></details>
      :<p className="dialog-note">Inbox notes for this source need an explicit write grant.</p>}
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
  </div>;
  return <div className="remember-form" aria-label="Remember this">
    <h4>Remember from {evidence.title}</h4>
    <label>Record<select value={subject} onChange={e=>setSubject(e.target.value)}>{entities.map(r=><option key={r.id} value={r.id.replace(/^entity:/,'')}>{r.title} ({r.kind})</option>)}<option value="new">New record…</option></select></label>
    {subject==='new'&&<div className="inline-pair"><label>Name<input className="inline-input" value={newName} maxLength={120} onChange={e=>setNewName(e.target.value)}/></label><label>Kind<select value={newKind} onChange={e=>setNewKind(e.target.value as typeof ENTITY_KINDS[number])}>{ENTITY_KINDS.map(k=><option key={k}>{k}</option>)}</select></label></div>}
    <label>Statement<select value={predicate} onChange={e=>setPredicate(e.target.value)}>{PREDICATES.map(p=><option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
    {isObject?<label>Linked record<select value={object} onChange={e=>setObject(e.target.value)}><option value="">Choose…</option>{entities.map(r=><option key={r.id} value={r.id}>{r.title} ({r.kind})</option>)}</select></label>
      :<label>Value<input className="inline-input" value={value} maxLength={400} onChange={e=>setValue(e.target.value)} placeholder="As written in the source"/></label>}
    <div className="inline-pair"><label>From line<input className="inline-input" type="number" min={evidence.start_line} max={evidence.end_line} value={start} onChange={e=>setStart(Number(e.target.value))}/></label><label>To line<input className="inline-input" type="number" min={start} max={Math.min(evidence.end_line,start+7)} value={end} onChange={e=>setEnd(Number(e.target.value))}/></label></div>
    <div className="inline-pair"><label>Memory type<select value={type} onChange={e=>setType(e.target.value as typeof TYPES[number])}>{TYPES.map(t=><option key={t}>{t}</option>)}</select></label><label>Retention<select value={retention} onChange={e=>setRetention(Number(e.target.value))}>{RETENTION.map((r,i)=><option key={r.label} value={i}>{r.label}</option>)}</select></label></div>
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
    <div className="button-row"><button className="secondary-button" disabled={busy||(isObject?!object:!value.trim())} onClick={capture}>Preview proposal</button><button className="text-button" onClick={onClose}>Cancel</button></div>
  </div>;
}
