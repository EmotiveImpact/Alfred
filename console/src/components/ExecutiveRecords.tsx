import {useEffect,useMemo,useState} from 'react';
import {CaretDown,Check} from '@phosphor-icons/react';
import {useConsole} from '../state/ConsoleProvider';
import {dueLabel} from '../integration/toSnapshot';
import {type ExecRecordView,ALL,filterByResponsible,fromDateInput,groupRecords,responsibleChoices,shortDate} from '../domain/executive';
import {AttentionList,BriefPanel,InsightList,PeopleSelect,RecordEditor,executiveMessage,useExecutiveView} from './ExecutiveWorkflows';
const KINDS=[{id:'priority',label:'Priority'},{id:'commitment',label:'Commitment'},{id:'follow_up',label:'Follow-up'},{id:'decision',label:'Decision'},{id:'milestone',label:'Milestone'},{id:'goal',label:'Goal'}] as const;
const DONE:Record<string,string>={priority:'done',commitment:'done',follow_up:'done',milestone:'done',goal:'achieved',decision:'decided'};
const OPEN:Record<string,string>={priority:'open',commitment:'open',follow_up:'open',milestone:'open',goal:'active',decision:'proposed'};
const plain=(id:string)=>id.replace(/^exec:/,'');
/** Server-side status change with the record's exact version. */
export function useExecutiveActions(){
  const c=useConsole();
  const toggle=async(record:{id:string;version:number;kind:string;done:boolean})=>{
    try{await c.live.client.post(`/desk/executive/records/${plain(record.id)}`,{version:record.version,status:record.done?OPEN[record.kind]:DONE[record.kind]});}
    catch(e){c.setNotice(executiveMessage(e));}finally{void c.live.refresh();}
  };
  const accept=async(fromRecord:string,fromVersion:number)=>{
    try{await c.live.client.post('/desk/executive/recommendations/accept',{request_id:'accept-'+Math.random().toString(36).slice(2,12),from_record:fromRecord,from_version:fromVersion});c.setNotice('Added to your priorities. It is now yours, not an inference.');}
    catch(e){c.setNotice(executiveMessage(e));}finally{void c.live.refresh();}
  };
  return{toggle,accept};
}
function isDone(status:string){return ['done','achieved','decided'].includes(status);}
function summary(r:ExecRecordView){
  const parts=[r.open?dueLabel(r.due,r.overdue):r.status.replace('_',' ')];
  if(r.kind==='decision'&&r.options?.length)parts.push(`${r.options.length} options`);
  if(r.responsible)parts.push(r.responsible);
  if(r.snoozed)parts.push(`snoozed until ${shortDate(r.snoozed_until)}`);
  return parts.join(' · ');
}
function RecordRow({record,owner,expanded,onExpand,onChanged,onBrief}:{record:ExecRecordView;owner:boolean;expanded:boolean;onExpand:()=>void;onChanged:()=>void;onBrief:(id:string)=>void}){
  const{toggle}=useExecutiveActions(),done=isDone(record.status);
  // A decision with options is decided by choosing one, never by ticking a box.
  const choosing=record.kind==='decision'&&(Boolean(record.options?.length)||record.choice?.option!=null);
  return <div className={`exec-row ${expanded?'expanded':''}`}>
    <div className="exec-row-line"><button role="checkbox" aria-checked={done} disabled={!owner} className={`task-row ${done?'done':''}`}
        onClick={()=>{if(choosing){onExpand();return;}void toggle({id:record.id,version:record.version,kind:record.kind,done}).then(onChanged);}}>
        <span className="check-ring">{done&&<Check size={13}/>}</span><span>{record.title}</span><small>{summary(record)}</small></button>
      <button className="exec-more" aria-expanded={expanded} aria-label={`Details for ${record.title}`} onClick={onExpand}><CaretDown size={14}/></button></div>
    {expanded&&<RecordEditor record={record} owner={owner} onChanged={onChanged} onBrief={onBrief}/>}
  </div>;
}
function AddRecord({onChanged}:{onChanged:()=>void}){
  const c=useConsole();
  const projects=useMemo(()=>c.state.snapshot.records.filter(r=>r.category==='projects'),[c.state.snapshot.records]);
  const[kind,setKind]=useState<typeof KINDS[number]['id']>('priority'),[title,setTitle]=useState(''),[project,setProject]=useState(''),[due,setDue]=useState(''),[rank,setRank]=useState('');
  const[responsible,setResponsible]=useState(''),[link,setLink]=useState('');
  const[busy,setBusy]=useState(false),[error,setError]=useState('');
  const create=async()=>{setBusy(true);setError('');try{
    const label=responsible.trim();
    await c.live.client.post('/desk/executive/records',{request_id:'record-'+Math.random().toString(36).slice(2,12),kind,title:title.trim(),detail:'',
      project:project||null,due:due?fromDateInput(due):null,rank:kind==='priority'&&rank?Number(rank):null,support:null,
      ...(label?{responsible:label,responsible_link:link||null}:{})});
    setTitle('');setDue('');setRank('');setResponsible('');setLink('');c.setNotice('Recorded. It appears in the panel and the graph.');onChanged();void c.live.refresh();
  }catch(e){setError(executiveMessage(e));}finally{setBusy(false);}};
  return <div className="remember-form" aria-label="New executive record"><h4>Add a record</h4>
    <div className="inline-pair"><label>Kind<select value={kind} onChange={e=>setKind(e.target.value as typeof kind)}>{KINDS.map(k=><option key={k.id} value={k.id}>{k.label}</option>)}</select></label><label>Project<select value={project} onChange={e=>setProject(e.target.value)}><option value="">None</option>{projects.map(p=><option key={p.id} value={p.id}>{p.title}{p.origin==='reviewed_entity'?' (reviewed)':''}</option>)}</select></label></div>
    <label>Title<input className="inline-input" value={title} maxLength={160} onChange={e=>setTitle(e.target.value)}/></label>
    <div className="inline-pair"><label>Due<input className="inline-input" type="date" value={due} onChange={e=>setDue(e.target.value)}/></label>{kind==='priority'&&<label>Rank<input className="inline-input" type="number" min={1} max={1000} value={rank} onChange={e=>setRank(e.target.value)}/></label>}</div>
    <div className="inline-pair"><label>Responsible<input className="inline-input" value={responsible} maxLength={80} placeholder="Optional, for example Finance lead" onChange={e=>setResponsible(e.target.value)}/></label><PeopleSelect value={link} onChange={setLink}/></div>
    {link&&!responsible.trim()&&<p className="dialog-note exec-quiet">Type a responsible label to keep the linked person.</p>}
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
    <div className="button-row"><button className="secondary-button" disabled={busy||!title.trim()} onClick={create}>Add record</button></div></div>;
}
type Tab='records'|'attention'|'insights';
export function ExecutiveRecordsPanel(){
  const c=useConsole(),exec=useExecutiveView(),owner=c.live.session?.role==='owner';
  // A target set by the side panel or the inspector is read once when the dialog opens.
  const[target]=useState(()=>c.executiveTarget);
  const setTarget=c.setExecutiveTarget;
  useEffect(()=>{setTarget(null);},[setTarget]);
  const[tab,setTab]=useState<Tab>(target?.view==='attention'||target?.view==='insights'?target.view:'records');
  const[expanded,setExpanded]=useState<string|null>(target?.view==='details'?target.id:null);
  const[brief,setBrief]=useState<string|null>(target?.view==='brief'?target.id:null);
  const[filter,setFilter]=useState(ALL),[by,setBy]=useState<'kind'|'responsible'>('kind');
  const changed=exec.refresh;
  const view=exec.view;
  useEffect(()=>{if(!expanded||!view)return;document.getElementById('exec-'+expanded)?.scrollIntoView({block:'nearest'});},[expanded,view]);
  if(brief)return <div className="executive-records"><BriefPanel id={brief} onBack={()=>setBrief(null)}/></div>;
  const records=view?.records??[];
  const choices=view?responsibleChoices(view.responsible_groups.groups,view.responsible_groups.unassigned_open.length):[];
  const shown=filterByResponsible(records,choices.some(x=>x.key===filter)?filter:ALL);
  const open=(id:string)=>{setTab('records');setExpanded(id);setFilter(ALL);};
  return <div className="executive-records">
    <div className="exec-tabs" role="tablist" aria-label="Executive views">
      {([['records','Records',records.length],['attention','Attention',view?.attention.items.length??0],['insights','Insights',view?.insights.items.length??0]] as [Tab,string,number][]).map(([id,label,count])=>
        <button key={id} role="tab" id={`exec-tab-${id}`} aria-selected={tab===id} aria-controls={`exec-panel-${id}`} onClick={()=>setTab(id)}>{label}<span>{count}</span></button>)}
    </div>
    {exec.status==='loading'&&!view&&<p className="dialog-note" role="status">Reading your records…</p>}
    {exec.status==='error'&&<p className="sign-in-error" role="alert">{exec.message}</p>}
    {view&&tab==='records'&&<div role="tabpanel" id="exec-panel-records" aria-labelledby="exec-tab-records">
      <p className="dialog-note">Records you write yourself. ALFRED does not infer obligations or owners; due-soon commitments appear only as labelled recommendations and attention items.</p>
      <div className="exec-toolbar"><label>Responsible<select aria-label="Filter by responsible" value={filter} onChange={e=>setFilter(e.target.value)}>{choices.map(x=><option key={x.key} value={x.key}>{x.label}</option>)}</select></label>
        <label>Group by<select aria-label="Group records by" value={by} onChange={e=>setBy(e.target.value as 'kind'|'responsible')}><option value="kind">Kind</option><option value="responsible">Responsible</option></select></label></div>
      {groupRecords(shown,by).map(g=><section className="ask-section" key={g.heading}><h3>{g.heading}</h3>
        {g.items.length?g.items.map(r=><div id={'exec-'+r.id} key={r.id}><RecordRow record={r} owner={owner} expanded={expanded===r.id} onExpand={()=>setExpanded(x=>x===r.id?null:r.id)} onChanged={changed} onBrief={setBrief}/></div>)
          :<p className="quiet-empty">None recorded.</p>}</section>)}
      {owner&&<AddRecord onChanged={changed}/>}
    </div>}
    {view&&tab==='attention'&&<div role="tabpanel" id="exec-panel-attention" aria-labelledby="exec-tab-attention"><AttentionList view={view} owner={owner} onChanged={changed} onOpen={open}/></div>}
    {view&&tab==='insights'&&<div role="tabpanel" id="exec-panel-insights" aria-labelledby="exec-tab-insights"><InsightList view={view}/></div>}
  </div>;
}
export {dueLabel};
