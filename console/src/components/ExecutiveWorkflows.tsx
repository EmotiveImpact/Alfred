import {useCallback,useEffect,useState} from 'react';
import {ArrowLeft,ArrowUpRight,Info,Lightning,Plus,Trash} from '@phosphor-icons/react';
import {useConsole} from '../state/ConsoleProvider';
import {DeskError} from '../integration/deskClient';
import {dueLabel} from '../integration/toSnapshot';
import {type AttentionItem,type Brief,type ExecRecordView,type ExecutiveView,type OptionDraft,BRIEF_KINDS,KIND_LABEL,RULE_LABEL,
  citeLabel,fromDateInput,hiddenSummary,optionDrafts,optionsPayload,shortDate,toDateInput} from '../domain/executive';
import '../executive.css';

const ERRORS:Record<string,string>={executive_record_changed:'This record changed. The view has been refreshed; try again.',
  project_not_available:'That project is no longer available to you.',recommendation_not_current:'That recommendation has changed. The view has been refreshed.',
  invalid_text:'Give it a short title.',control_character:'Remove the unusual characters.',responsible_label_required:'Type a responsible label before linking a record.',
  responsible_not_available:'That record is not available to you.',responsible_not_a_person:'Link a person or organisation record.',
  invalid_responsible:'Type a short responsible label.',invalid_snooze:'Choose a day after today and within a year.',
  decision_reopen_required:'Reopen the decision before changing it.',decision_choice_required:'Choose one of the saved options to decide.',
  rationale_required:'Write a short rationale.',unknown_decision_option:'Choose one of the saved options.',
  invalid_decision_options:'A decision needs two to six options.',duplicate_option_label:'Each option needs a different name.',
  invalid_decision_option:'Give every option a short name.',invalid_option_points:'Up to four pros and four cons, each one short line.',
  milestone_not_open:'Progress can be recorded only on an open milestone.',decision_not_open:'This decision is no longer open.',
  decision_not_closed:'This decision is already open.',invalid_progress_note:'Write a short progress note.',
  executive_history_capacity:'This record has reached its history limit.',executive_record_not_found:'This record is no longer available to you.',
  brief_kind_not_supported:'Briefs are prepared for decisions, milestones and commitments.'};
export function executiveMessage(e:unknown){return e instanceof DeskError?ERRORS[e.code]??`ALFRED refused this (${e.code}).`:'ALFRED could not be reached.';}
const isAbort=(e:unknown)=>e instanceof DOMException&&e.name==='AbortError';
const plain=(id:string)=>id.replace(/^exec:/,'');

/** The authoritative executive view, re-read whenever the projection changes or after a change made here. */
export function useExecutiveView(){
  const c=useConsole(),{client,fail}=c.live,revision=c.state.snapshot.dataRevision;
  const[state,setState]=useState<{status:'loading'|'ready'|'error';view?:ExecutiveView;message?:string}>({status:'loading'});
  const[tick,setTick]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    client.get<ExecutiveView>('/desk/executive',controller.signal).then(view=>{if(!controller.signal.aborted)setState({status:'ready',view});}).catch(e=>{
      if(isAbort(e))return;setState(s=>({status:'error',view:s.view,message:executiveMessage(e)}));if(e instanceof DeskError&&e.kind==='signed_out')fail(e);
    });
    return()=>controller.abort();
  },[client,fail,revision,tick]);
  return {...state,refresh:useCallback(()=>setTick(t=>t+1),[])};
}

/** One server write with the record's exact version, then a fresh read of both views. */
function useWrite(onChanged:()=>void){
  const c=useConsole(),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const run=async(path:string,body:unknown,notice?:string)=>{
    setBusy(true);setError('');
    try{await c.live.client.post(path,body);if(notice)c.setNotice(notice);return true;}
    catch(e){setError(executiveMessage(e));if(e instanceof DeskError&&e.kind==='signed_out')c.live.fail(e);return false;}
    finally{setBusy(false);onChanged();void c.live.refresh();}
  };
  return {busy,error,run,setError};
}

export function PeopleSelect({value,onChange,label='Linked person'}:{value:string;onChange:(v:string)=>void;label?:string}){
  const{records}=useConsole();
  // Only records the server already returned as people. Picking one is the only way a link is made.
  const people=records.filter(r=>r.category==='people'&&(r.origin==='authored_note'||r.origin==='reviewed_entity'));
  const hidden=Boolean(value)&&!people.some(p=>p.id===value);
  return <label>{label}<select value={value} onChange={e=>onChange(e.target.value)}><option value="">None</option>
    {hidden&&<option value={value}>Linked record not available</option>}
    {people.map(p=><option key={p.id} value={p.id}>{p.title}{p.origin==='reviewed_entity'?' (reviewed)':''}</option>)}</select></label>;
}

function ResponsibleEditor({record,onChanged}:{record:ExecRecordView;onChanged:()=>void}){
  const[label,setLabel]=useState(record.responsible??''),[link,setLink]=useState(record.responsible_link??'');
  const w=useWrite(onChanged);
  useEffect(()=>{setLabel(record.responsible??'');setLink(record.responsible_link??'');},[record.version,record.responsible,record.responsible_link]);
  const save=()=>{
    // Clearing the label clears its link on the server; a link is sent only when it changes.
    const body:Record<string,unknown>={version:record.version,responsible:label.trim()||null};
    if(label.trim()&&link!==(record.responsible_link??''))body.responsible_link=link||null;
    void w.run(`/desk/executive/records/${record.id}`,body,'Responsible label saved. It is your text, not an account or a grant.');
  };
  return <div className="exec-block" role="group" aria-label="Responsible"><h4>Responsible</h4>
    <div className="inline-pair"><label>Responsible label<input className="inline-input" value={label} maxLength={80} placeholder="For example, Finance lead" onChange={e=>setLabel(e.target.value)}/></label><PeopleSelect value={link} onChange={setLink}/></div>
    {record.responsible_state==='unavailable'&&<p className="dialog-note exec-quiet">The linked record is not currently available to you. The label is kept.</p>}
    <p className="dialog-note exec-quiet">ALFRED never fills this from note text and never treats it as a person's account. A link exists only if you pick one.</p>
    {w.error&&<p className="sign-in-error" role="alert">{w.error}</p>}
    <div className="button-row"><button className="secondary-button" disabled={w.busy||(!label.trim()&&Boolean(link))} onClick={save}>Save responsible</button></div></div>;
}

function SnoozeEditor({record,onChanged}:{record:ExecRecordView;onChanged:()=>void}){
  const week=Math.floor(Date.now()/1000)+7*86400,[day,setDay]=useState(toDateInput(week)),w=useWrite(onChanged);
  if(!record.open)return null;
  return <div className="exec-block" role="group" aria-label="Reminder"><h4>Reminder</h4>
    {record.snoozed?<p className="dialog-note exec-quiet">Snoozed until {shortDate(record.snoozed_until)}. It stays listed under Snoozed until then.</p>
      :<p className="dialog-note exec-quiet">Shown in Attention when its rule applies. Snoozing hides it there, and from recommendations, until the day you choose.</p>}
    {w.error&&<p className="sign-in-error" role="alert">{w.error}</p>}
    <div className="exec-inline">{record.snoozed?<button className="secondary-button" disabled={w.busy} onClick={()=>void w.run(`/desk/executive/records/${record.id}`,{version:record.version,snoozed_until:null},'Snooze cleared.')}>Clear snooze</button>
      :<><label>Snooze until<input className="inline-input" type="date" value={day} onChange={e=>setDay(e.target.value)}/></label><button className="secondary-button" disabled={w.busy||!fromDateInput(day)} onClick={()=>void w.run(`/desk/executive/records/${record.id}`,{version:record.version,snoozed_until:fromDateInput(day)},'Snoozed. Nothing is sent anywhere.')}>Snooze</button></>}</div></div>;
}

function OptionsEditor({record,onChanged}:{record:ExecRecordView;onChanged:()=>void}){
  const[drafts,setDrafts]=useState<OptionDraft[]>(()=>optionDrafts(record.options)),w=useWrite(onChanged);
  useEffect(()=>setDrafts(optionDrafts(record.options)),[record.version]);// eslint-disable-line react-hooks/exhaustive-deps
  const edit=(i:number,key:keyof OptionDraft,value:string)=>setDrafts(d=>d.map((x,j)=>j===i?{...x,[key]:value}:x));
  const save=()=>{const payload=optionsPayload(drafts);if('error' in payload){w.setError(payload.error);return;}
    void w.run(`/desk/executive/records/${record.id}/options`,{version:record.version,options:payload.options},'Options saved in the order you wrote them. Nothing scores them.');};
  return <div className="option-editor">{drafts.map((d,i)=><fieldset className="option-draft" key={i}><legend>Option {i+1}</legend>
      <label>Option {i+1} name<input className="inline-input" value={d.label} maxLength={120} onChange={e=>edit(i,'label',e.target.value)}/></label>
      <label>Option {i+1} notes<textarea className="inline-input" rows={2} maxLength={500} value={d.notes} onChange={e=>edit(i,'notes',e.target.value)}/></label>
      <div className="inline-pair"><label>Option {i+1} pros, one per line<textarea className="inline-input" rows={2} value={d.pros} onChange={e=>edit(i,'pros',e.target.value)}/></label>
        <label>Option {i+1} cons, one per line<textarea className="inline-input" rows={2} value={d.cons} onChange={e=>edit(i,'cons',e.target.value)}/></label></div>
      {drafts.length>2&&<button className="text-button" aria-label={`Remove option ${i+1}`} onClick={()=>setDrafts(x=>x.filter((_,j)=>j!==i))}><Trash size={12}/> Remove</button>}</fieldset>)}
    {w.error&&<p className="sign-in-error" role="alert">{w.error}</p>}
    <div className="button-row">{drafts.length<6&&<button className="text-button" onClick={()=>setDrafts(x=>[...x,{label:'',notes:'',pros:'',cons:''}])}><Plus size={12}/> Add option</button>}
      <button className="secondary-button" disabled={w.busy} onClick={save}>Save options</button></div></div>;
}

function OptionList({record}:{record:ExecRecordView}){
  const options=record.options??[];
  if(!options.length)return <p className="quiet-empty">No options recorded.</p>;
  return <ol className="option-list">{options.map(o=><li key={o.id} className={record.choice?.option===o.id?'chosen':''}><strong>{o.label}</strong>{record.choice?.option===o.id&&<span className="chosen-mark">Your choice</span>}
    {o.notes?<p>{o.notes}</p>:<p className="exec-quiet">No notes.</p>}
    {(o.pros.length>0||o.cons.length>0)&&<div className="pros-cons">{o.pros.map((x,i)=><span key={'p'+i} className="pro">+ {x}</span>)}{o.cons.map((x,i)=><span key={'c'+i} className="con">− {x}</span>)}</div>}</li>)}</ol>;
}

function DecisionEditor({record,owner,onChanged}:{record:ExecRecordView;owner:boolean;onChanged:()=>void}){
  const[choice,setChoice]=useState(''),[rationale,setRationale]=useState(''),w=useWrite(onChanged);
  const options=record.options??[],proposed=record.status==='proposed';
  const decide=()=>void w.run(`/desk/executive/records/${record.id}/decide`,{version:record.version,option:options.length?choice:null,rationale:rationale.trim()},'Decision recorded with your rationale.');
  return <div className="exec-block" role="group" aria-label="Decision"><h4>Options</h4>
    <p className="dialog-note exec-quiet">Options you write, in your order. ALFRED does not score, rank or choose between them.</p>
    {proposed&&owner?<OptionsEditor record={record} onChanged={onChanged}/>:<OptionList record={record}/>}
    {proposed&&owner&&<div className="decide-form" role="group" aria-label="Record a decision"><h4>Decide</h4>
      {options.length?<div className="option-choices" role="radiogroup" aria-label="Chosen option">{options.map(o=><label key={o.id} className="option-choice"><input type="radio" name={`choice-${record.id}`} checked={choice===o.id} onChange={()=>setChoice(o.id)}/>{o.label}</label>)}</div>
        :<p className="dialog-note exec-quiet">No saved options. You can still record the decision with its rationale.</p>}
      <label>Rationale<textarea className="inline-input" rows={2} maxLength={1200} value={rationale} onChange={e=>setRationale(e.target.value)}/></label>
      {w.error&&<p className="sign-in-error" role="alert">{w.error}</p>}
      <div className="button-row"><button className="secondary-button" disabled={w.busy||!rationale.trim()||(options.length>0&&!choice)} onClick={decide}>Record decision</button></div></div>}
    {!proposed&&<div className="decision-outcome"><p><span className="eyebrow">{record.status==='decided'?'Decided':'Superseded'}</span>
      <strong>{record.choice?.label??(record.status==='decided'?'Marked decided':'No option recorded')}</strong>{record.choice?.decided_at?<small> · {shortDate(record.choice.decided_at)}</small>:null}</p>
      {record.choice?.rationale&&<blockquote>{record.choice.rationale}</blockquote>}
      {w.error&&<p className="sign-in-error" role="alert">{w.error}</p>}
      {owner&&<button className="secondary-button" disabled={w.busy} onClick={()=>void w.run(`/desk/executive/records/${record.id}/reopen`,{version:record.version},'Decision reopened. The earlier choice stays in its history.')}>Reopen decision</button>}</div>}
    {(record.decision_history?.length??0)>0&&<ol className="exec-trail" aria-label="Decision history">{record.decision_history!.map((h,i)=><li key={i}>{h.event==='decided'?`Decided${h.label?`: ${h.label}`:''}`:`Reopened${h.label?` (was ${h.label})`:''}`}<small>{shortDate(h.at)}</small></li>)}</ol>}</div>;
}

function ProgressEditor({record,owner,onChanged}:{record:ExecRecordView;owner:boolean;onChanged:()=>void}){
  const[note,setNote]=useState(''),w=useWrite(onChanged);
  const record_=async()=>{if(await w.run(`/desk/executive/records/${record.id}/progress`,{version:record.version,note:note.trim()},'Progress recorded.'))setNote('');};
  return <div className="exec-block" role="group" aria-label="Progress"><h4>Progress</h4>
    {record.progress?.length?<ol className="exec-trail" aria-label="Recorded progress">{record.progress.map((e,i)=><li key={i}>{e.kind==='note'?e.note:`Marked ${e.status}`}<small>{shortDate(e.at)}</small></li>)}</ol>:<p className="quiet-empty">No progress recorded yet.</p>}
    {owner&&record.status==='open'&&<><div className="exec-inline"><label>Progress note<input className="inline-input" value={note} maxLength={400} onChange={e=>setNote(e.target.value)}/></label>
      <button className="secondary-button" disabled={w.busy||!note.trim()} onClick={()=>void record_()}>Record progress</button></div>
      {w.error&&<p className="sign-in-error" role="alert">{w.error}</p>}</>}</div>;
}

export function RecordEditor({record,owner,onChanged,onBrief}:{record:ExecRecordView;owner:boolean;onChanged:()=>void;onBrief:(id:string)=>void}){
  return <div className="record-editor">
    {record.detail&&<p className="exec-detail">{record.detail}</p>}
    {owner?<ResponsibleEditor record={record} onChanged={onChanged}/>:record.responsible&&<p className="dialog-note">Responsible: {record.responsible}</p>}
    {record.kind==='decision'&&<DecisionEditor record={record} owner={owner} onChanged={onChanged}/>}
    {record.kind==='milestone'&&<ProgressEditor record={record} owner={owner} onChanged={onChanged}/>}
    {owner&&<SnoozeEditor record={record} onChanged={onChanged}/>}
    {BRIEF_KINDS.includes(record.kind)&&<div className="button-row"><button className="secondary-button" onClick={()=>onBrief(record.id)}>Prepare brief</button></div>}
  </div>;
}

function Questions({brief}:{brief:Brief}){
  return brief.questions.length?<ul className="brief-questions">{brief.questions.map((q,i)=><li key={i}>{q.text}</li>)}</ul>:<p className="quiet-empty">No open questions by the stated checks.</p>;
}

/** An assembled brief: computed on request from what this person may read now, re-assembled when records change. */
export function BriefPanel({id,onBack}:{id:string;onBack:()=>void}){
  const c=useConsole(),{client,fail}=c.live,revision=c.state.snapshot.dataRevision;
  const[state,setState]=useState<{status:'loading'}|{status:'ready';brief:Brief}|{status:'error';message:string}>({status:'loading'});
  useEffect(()=>{
    const controller=new AbortController();
    client.get<Brief>(`/desk/executive/records/${encodeURIComponent(id)}/brief`,controller.signal).then(brief=>{if(!controller.signal.aborted)setState({status:'ready',brief});}).catch(e=>{
      if(isAbort(e))return;setState({status:'error',message:executiveMessage(e)});if(e instanceof DeskError&&e.kind==='signed_out')fail(e);
    });
    return()=>controller.abort();
  },[client,fail,id,revision]);
  const openNote=(noteId:string)=>{c.selectRecord('note:'+noteId);c.setModal(null);};
  const openRecord=(recordId:string)=>{c.selectRecord('exec:'+recordId);c.setModal(null);};
  return <div className="brief-view" aria-label="Assembled brief">
    <button className="text-button brief-back" onClick={onBack}><ArrowLeft size={12}/> Back to records</button>
    {state.status==='loading'&&<p className="dialog-note" role="status">Assembling from your current records and permitted sources…</p>}
    {state.status==='error'&&<p className="sign-in-error" role="alert">{state.message}</p>}
    {state.status==='ready'&&(()=>{const b=state.brief,r=b.record;return <>
      <div className="review-scope"><Info size={20}/><span>{b.label}</span></div>
      <p className="dialog-note exec-quiet">Assembled at {new Date(b.assembled_at*1000).toLocaleTimeString('en-GB')} and not stored. It is assembled again when your records or sources change, so anything you can no longer read drops out.</p>
      <h3 className="proposal-title">{r.title}</h3>
      <dl className="detail-list"><div><dt>Kind</dt><dd>{KIND_LABEL[r.kind]}</dd></div><div><dt>Status</dt><dd>{r.status}</dd></div><div><dt>Due</dt><dd>{dueLabel(r.due,r.overdue)}</dd></div>
        <div><dt>Responsible</dt><dd>{r.responsible??'Not recorded'}{r.responsible_state==='current'&&r.responsible_name?` · ${r.responsible_name}`:''}</dd></div>
        <div><dt>Project</dt><dd>{r.project===null?'None':r.project_state==='current'?r.project_name:'Not available to you'}</dd></div></dl>
      {r.kind==='decision'&&<section className="ask-section"><h3>Options</h3><OptionList record={r}/>{r.choice?.rationale&&<p className="dialog-note">Rationale: {r.choice.rationale}</p>}</section>}
      <section className="ask-section"><h3>Linked notes</h3>{b.linked_notes.length?b.linked_notes.map((n,i)=>n.state==='current'?<div className="evidence" key={i}>
          <header><span className="source-id">{n.role==='project'?'PROJECT NOTE':n.role==='responsible'?'RESPONSIBLE PERSON NOTE':'CITED LINES'}</span><button className="text-button" onClick={()=>openNote(n.note_id)}>{n.title}</button><small>{n.path} · {citeLabel(n.cite)}</small></header>
          {n.excerpt?<blockquote>{n.excerpt}{n.truncated?'…':''}</blockquote>:<p className="exec-quiet">No prose line to quote.</p>}</div>
        :<p className="dialog-note" key={i}>The cited lines {n.state==='changed'?'have changed since the record was written':'are not currently available to you'}.</p>):<p className="quiet-empty">No linked note is available.</p>}</section>
      <section className="ask-section"><h3>Reviewed statements</h3>{b.statements.length?b.statements.map(s=><div className="statement usable" key={s.claim_id}>
          <p><strong>{s.subject?.name??'Record'}</strong> {s.predicate.replaceAll('_',' ')} {s.value??s.object?.name??''}</p>
          <small>{s.why==='about_linked_record'?'About a linked record':'Supported by a linked note'} · your reviewed statement, not a verified fact</small>
          <blockquote>{s.support.quote}</blockquote><button className="text-button" onClick={()=>openNote(s.support.note_id)}>{s.support.title}, {citeLabel(s.cite)}</button></div>)
        :<p className="quiet-empty">No accepted, current reviewed statement about the linked records.</p>}
        {hiddenSummary(b.statements_not_shown)&&<p className="dialog-note exec-quiet">Not shown: {hiddenSummary(b.statements_not_shown)}.</p>}</section>
      <section className="ask-section"><h3>Related commitments and follow-ups</h3>{b.related.length?<div className="brief-related">{b.related.map(x=><button className="record-row" key={x.id} onClick={()=>openRecord(x.id)}><span><strong>{x.title}</strong><small>{KIND_LABEL[x.kind]} · {dueLabel(x.due,x.overdue)}{x.responsible?` · ${x.responsible}`:''} · {citeLabel(x.cite)}</small></span><ArrowUpRight size={14}/></button>)}</div>
        :<p className="quiet-empty">None open in the same project.</p>}</section>
      <section className="ask-section"><h3>Milestone progress</h3>{b.progress?<><p className="dialog-note exec-quiet">{b.progress.done} of {b.progress.total} recorded milestones done. Counted from your milestones only.</p>
          {b.progress.recent.length?<ol className="exec-trail">{b.progress.recent.map((e,i)=><li key={i}>{e.title}: {e.kind==='note'?e.note:`marked ${e.status}`}<small>{shortDate(e.at)}</small></li>)}</ol>:null}</>
        :<p className="quiet-empty">No milestones recorded for this project.</p>}</section>
      <section className="ask-section"><h3>Open questions</h3><Questions brief={b}/></section>
    </>;})()}
  </div>;
}

function SnoozeInline({item,onChanged}:{item:AttentionItem;onChanged:()=>void}){
  const[open,setOpen]=useState(false),[day,setDay]=useState(toDateInput(Math.floor(Date.now()/1000)+7*86400)),w=useWrite(onChanged);
  const snooze=async()=>{if(await w.run(`/desk/executive/records/${item.record}`,{version:item.version,snoozed_until:fromDateInput(day)},'Snoozed. Nothing is sent anywhere.'))setOpen(false);};
  if(!open)return <button className="text-button" aria-label={`Snooze ${item.title}`} onClick={()=>setOpen(true)}>Snooze</button>;
  return <span className="exec-inline snooze-inline"><label>Snooze until<input className="inline-input" type="date" value={day} onChange={e=>setDay(e.target.value)}/></label>
    <button className="secondary-button" disabled={w.busy||!fromDateInput(day)} onClick={()=>void snooze()}>Confirm snooze</button>
    {w.error&&<span className="sign-in-error" role="alert">{w.error}</span>}</span>;
}

export function AttentionList({view,owner,onChanged,onOpen}:{view:ExecutiveView;owner:boolean;onChanged:()=>void;onOpen:(id:string)=>void}){
  const{items,snoozed,rules}=view.attention,w=useWrite(onChanged);
  const row=(item:AttentionItem,isSnoozed:boolean)=><div className="attention-item" key={item.record}>
    <span className={`attention-mark rule-${isSnoozed?'snoozed':item.rules[0]}`} aria-hidden="true"/>
    <span className="attention-copy"><strong>{item.title}</strong><small>{isSnoozed?`Snoozed until ${shortDate(item.snoozed_until)}`:item.rules.map(x=>RULE_LABEL[x]??x).join(' · ')} · {KIND_LABEL[item.kind]}{item.due!=null?` · ${shortDate(item.due)}`:''}{item.responsible?` · ${item.responsible}`:''}{item.project_name?` · ${item.project_name}`:''}</small></span>
    <span className="attention-actions">{owner&&(isSnoozed?<button className="text-button" disabled={w.busy} onClick={()=>void w.run(`/desk/executive/records/${item.record}`,{version:item.version,snoozed_until:null},'Snooze cleared.')}>Clear snooze</button>:<SnoozeInline item={item} onChanged={onChanged}/>)}
      <button className="text-button" aria-label={`Open ${item.title}`} onClick={()=>onOpen(item.record)}>Open</button></span></div>;
  return <div className="attention-list">
    <p className="dialog-note">Computed now from your records by the stated rules below. Shown in this console only: nothing is pushed, e-mailed or sent to a device.</p>
    {items.length?items.map(i=>row(i,false)):<p className="quiet-empty">Nothing is due, overdue or stale by these rules.</p>}
    {snoozed.length>0&&<section className="ask-section"><h3>Snoozed</h3>{snoozed.map(i=>row(i,true))}</section>}
    {w.error&&<p className="sign-in-error" role="alert">{w.error}</p>}
    <details className="exec-rules"><summary>Rules</summary><ul>{rules.map(r=><li key={r.id}><strong>{RULE_LABEL[r.id]??r.id}.</strong> {r.rule}</li>)}</ul></details></div>;
}

export function InsightList({view}:{view:ExecutiveView}){
  const c=useConsole(),{items,rules}=view.insights;
  const name=Object.fromEntries(rules.map(r=>[r.id,r.id.replaceAll('_',' ')]));
  return <div className="insight-list">
    <p className="dialog-note">Derived from your own records by the fixed rules below. These are not accepted facts and are not stored. Each one links to the records it was computed from.</p>
    {items.length?items.map((i,n)=><div className="derived-insight" key={n}><span className="eyebrow">Derived · {name[i.rule]??i.rule}</span><p>{i.statement}</p>
      <div className="exec-links">{i.records.map(r=><button className="text-button" key={r.id} onClick={()=>{c.selectRecord('exec:'+r.id);c.setModal(null);}}>{r.title}</button>)}</div></div>)
      :<p className="quiet-empty">No insight follows from your records by these rules.</p>}
    <details className="exec-rules"><summary>Rules</summary><ul>{rules.map(r=><li key={r.id}>{r.rule}</li>)}</ul></details></div>;
}

/** Side-panel summary from the projection; the full list lives in the executive dialog. */
export function AttentionSection(){
  const c=useConsole();
  if(!c.connected)return null;
  const items=c.state.snapshot.attention??[],count=c.state.snapshot.attentionCount??0,snoozed=c.state.snapshot.snoozedCount??0;
  return <section className="executive-section attention-section"><header className="executive-section-heading"><h3>Attention</h3>
      {count>3||snoozed?<button onClick={()=>c.openExecutive('attention')}>View all</button>:<span>{count}</span>}</header>
    {items.length?items.slice(0,3).map(a=><button className="attention-row" key={a.recordId} onClick={()=>c.openExecutive('details',plain(a.recordId))}>
      <span className={`attention-mark rule-${a.rules[0]}`} aria-hidden="true"/><span><strong>{a.title}</strong><small>{RULE_LABEL[a.rules[0]]??a.reason}{a.due!=null?` · ${shortDate(a.due)}`:''}{a.responsible?` · ${a.responsible}`:''}</small></span></button>)
      :<p className="quiet-empty">Nothing due, overdue or stale by the stated rules.{snoozed?` ${snoozed} snoozed.`:''}</p>}
  </section>;
}

export function DerivedInsightRow(){
  const c=useConsole(),insight=c.state.snapshot.derivedInsights?.[0];
  if(!c.connected||!insight)return null;
  return <button className="derived-row" onClick={()=>c.openExecutive('insights')}><span className="record-symbol"><Lightning size={20} weight="thin"/></span><span><strong>{insight.statement}</strong><em>Derived from your records · not an accepted fact</em></span><ArrowUpRight size={15}/></button>;
}

export function ExecutiveInspectorActions({id,kind}:{id:string;kind:string}){
  const c=useConsole(),record=plain(id);
  return <div className="button-row exec-inspector-actions">{(BRIEF_KINDS as readonly string[]).includes(kind)&&<button className="secondary-button" onClick={()=>c.openExecutive('brief',record)}>Prepare brief</button>}
    <button className="text-button" onClick={()=>c.openExecutive('details',record)}>Open in next steps</button></div>;
}
