import {useCallback,useEffect,useState} from 'react';
import {Check,FileText,Info,NotePencil,ShieldWarning} from '@phosphor-icons/react';
import {useConsole} from '../state/ConsoleProvider';
import {DeskError} from '../integration/deskClient';
import {approveRequest,chipTone,confirmRequest,confirmedLine,countsLine,dismissRequest,draftsMessage,kindWord,noteLine,openableNote,
  originChip,placeLines,preview,stateLine,stopReason,type AgentDraft,type DraftsView} from '../integration/agentDrafts';
import '../routines.css';
import '../goals.css';
import '../agent-drafts.css';

const isAbort=(e:unknown)=>e instanceof DOMException&&e.name==='AbortError';
const when=(seconds:number)=>new Date(seconds*1000).toLocaleString('en-GB',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});
type Send=(request:{path:string;body:unknown},notice:string)=>void;

/** Every draft an agent proposed, where its contents came from, and what you may do with it. */
export function AgentDraftsPanel(){
  const c=useConsole();
  if(!c.connected)return <div className="routines-panel"><div className="review-scope"><Info size={20}/><span>Agent drafts need the connected ALFRED product. This local preview has no agents and drafts nothing.</span></div></div>;
  return <ConnectedDrafts/>;
}

function ConnectedDrafts(){
  const c=useConsole(),{client,fail}=c.live,observed=c.live.connection.kind==='ready'?c.live.connection.observedAt:'';
  const[view,setView]=useState<DraftsView|null>(null),[error,setError]=useState(''),[actionError,setActionError]=useState('');
  const[busy,setBusy]=useState(false),[tick,setTick]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    client.get<DraftsView>('/desk/hub/drafts',controller.signal).then(data=>{if(!controller.signal.aborted){setView(data);setError('');}}).catch(e=>{
      if(isAbort(e))return;setError(draftsMessage(e));if(e instanceof DeskError&&e.kind==='signed_out')fail(e);
    });
    return()=>controller.abort();
  },[client,fail,observed,tick]);
  /* Every action is followed by a fresh read, so each card shows what the server recorded. */
  const send:Send=useCallback(({path,body},notice)=>{
    setBusy(true);setActionError('');
    client.post(path,body).then(()=>c.setNotice(notice))
      .catch(e=>{setActionError(draftsMessage(e));if(e instanceof DeskError&&e.kind==='signed_out')fail(e);})
      .finally(()=>{setBusy(false);setTick(t=>t+1);});
  },[client,fail,c]);
  if(error&&!view)return <div className="routines-panel"><p className="sign-in-error" role="alert">{error}</p></div>;
  if(!view)return <div className="routines-panel"><p className="dialog-note" role="status">Reading agent drafts…</p></div>;
  if(!view.available)return <div className="routines-panel"><p className="quiet-empty">Agent drafts belong to the workspace owner. This key cannot read them.</p></div>;
  return <div className="routines-panel goals-panel drafts-panel">
    <p className="dialog-note">Every draft an agent wrote for you, and where its contents came from. Approving saves a local draft only; nothing is ever sent from here.{view.mode==='watch'?' Address checks are set to watch: drafts with an address from a note are labelled but still offered for approval.':view.mode==='off'?' Address checks are off, so drafts are not labelled.':''}</p>
    {actionError&&<p className="sign-in-error" role="alert">{actionError}</p>}
    <h3 className="routine-subhead">Drafts<span aria-label="Draft counts">{countsLine(view)}</span></h3>
    {view.drafts.length?view.drafts.map(d=><DraftCard key={d.id} d={d} busy={busy} send={send}/>)
      :<p className="quiet-empty">No agent has drafted anything yet.</p>}
    {'dismissed' in view.counts&&view.counts.dismissed>0&&<p className="dialog-note">{view.counts.dismissed} dismissed {view.counts.dismissed===1?'draft is':'drafts are'} kept in ALFRED's records and not shown here.</p>}
  </div>;
}

function DraftCard({d,busy,send}:{d:AgentDraft;busy:boolean;send:Send}){
  const c=useConsole();
  const[open,setOpen]=useState<'none'|'approve'|'confirm'|'dismiss'>('none'),[full,setFull]=useState(false);
  const title=preview(d.text,90),stopped=d.state==='stopped';
  const source=openableNote(d,stopped?d.places.filter(p=>p.source!=='owner').flatMap(p=>p.refs):[...d.cited,...d.copied]);
  const note=noteLine(d),confirmed=confirmedLine(d);
  return <article className="routine-card draft-card" aria-label={`Draft: ${title}`}>
    <header><span className="record-symbol">{stopped?<ShieldWarning size={18} weight="thin"/>:<NotePencil size={18} weight="thin"/>}</span>
      <div><h3>{title}</h3><p>{d.reason!==null?`The agent's own note: ${d.reason}`:'The agent’s note is withheld.'} · {when(d.created)}</p></div>
      <ul className="routine-chips" aria-label={`Where this draft came from: ${title}`}><li className={chipTone(d)}>{originChip(d)}</li></ul></header>
    <p className="routine-line">{stateLine(d)}{d.capability!=='message.draft'?` · asked for ${d.capability}`:''}</p>
    {stopped&&<><p className="draft-why">{stopReason(d)}</p>
      {placeLines(d).length>0&&<ul className="result-checks draft-places" aria-label="Addresses you did not give">{placeLines(d).map(l=><li key={l} className="failed">{l}</li>)}</ul>}
      <p className="routine-line">Stopped {when(d.created)}. Nothing was approved, saved or sent.</p></>}
    {note&&<p className="routine-line">{note}</p>}
    {confirmed&&<p className="routine-line">{confirmed}</p>}
    {d.original_text!==null&&full&&<p className="routine-line">The agent wrote: {d.original_text}</p>}
    {full&&<blockquote className="draft-text" aria-label="Full draft text">{d.text??'Withheld: the notes this came from can no longer be read.'}</blockquote>}
    <div className="button-row">
      <button type="button" className="secondary-button" aria-expanded={full} onClick={()=>setFull(f=>!f)}>{full?'Hide full text':'Read in full'}</button>
      {d.can.approve&&open!=='approve'&&<button type="button" className="primary-button" disabled={busy} onClick={()=>setOpen('approve')}>Approve<Check size={15}/></button>}
      {source&&<button type="button" className="secondary-button" onClick={()=>{c.selectRecord(source.id);c.setModal(null);}}><FileText size={14}/>See the note it came from</button>}
      {d.can.confirm&&open!=='confirm'&&<button type="button" className="secondary-button" disabled={busy} onClick={()=>setOpen('confirm')}>Try again with an address I confirm</button>}
      {d.can.dismiss&&open!=='dismiss'&&<button type="button" className="text-button" disabled={busy} onClick={()=>d.action?.state==='proposed'?setOpen('dismiss'):send(dismissRequest(d),'Draft dismissed. Its record is kept.')}>Dismiss</button>}
    </div>
    {open==='approve'&&<ApproveConfirm d={d} busy={busy} onCancel={()=>setOpen('none')} onApprove={()=>{setOpen('none');send(approveRequest(d),'Approved. ALFRED saves it as a local draft. Nothing is sent.');}}/>}
    {open==='confirm'&&<AddressForm d={d} busy={busy} onCancel={()=>setOpen('none')} onSubmit={typed=>{setOpen('none');
      send(confirmRequest(d,typed),'Address confirmed. The draft now waits for you to approve its exact text.');}}/>}
    {open==='dismiss'&&<div className="forget-confirm" role="group" aria-label={`Confirm dismiss: ${title}`}><p className="dialog-note">Dismissing also cancels its approval, so it can no longer be saved. Its record is kept.</p>
      <div className="button-row"><button type="button" className="secondary-button" disabled={busy} onClick={()=>{setOpen('none');send(dismissRequest(d),'Draft dismissed and its approval cancelled.');}}>Dismiss draft</button>
        <button type="button" className="text-button" onClick={()=>setOpen('none')}>Keep it</button></div></div>}
  </article>;
}

function ApproveConfirm({d,busy,onApprove,onCancel}:{d:AgentDraft;busy:boolean;onApprove:()=>void;onCancel:()=>void}){
  const[consent,setConsent]=useState(false);
  return <div className="forget-confirm" role="group" aria-label="Approve this exact text">
    <blockquote className="draft-text">{d.text}</blockquote>
    <label className="consent"><input type="checkbox" checked={consent} onChange={e=>setConsent(e.target.checked)}/><span>I approve this exact text and nothing else. ALFRED saves it as a local draft; nothing is sent.</span></label>
    <div className="button-row"><button type="button" className="primary-button" disabled={!consent||busy} onClick={onApprove}>Approve exact text<Check size={15}/></button>
      <button type="button" className="text-button" onClick={onCancel}>Cancel</button></div></div>;
}

/** One box per address the owner did not give, in the order ALFRED found them. */
function AddressForm({d,busy,onSubmit,onCancel}:{d:AgentDraft;busy:boolean;onSubmit:(typed:string[])=>void;onCancel:()=>void}){
  const held=d.places.filter(p=>p.source!=='owner');
  const[typed,setTyped]=useState<string[]>(()=>held.map(()=>''));
  return <form className="forget-confirm draft-confirm" aria-label="Confirm the address yourself" onSubmit={e=>{e.preventDefault();onSubmit(typed);}}>
    <p className="dialog-note">Type the address yourself, from somewhere you trust: your contacts, a call, or a letter. Do not copy it from the email that held it. If you type the same address, you confirm it; if you type a different one, ALFRED puts yours in the draft instead. Either way you still approve the exact text before anything is saved.</p>
    {held.map((p,i)=><label key={`${p.kind}-${i}`} className="draft-field"><span>{held.length>1?`${kindWord(p.kind)} ${i+1}`:kindWord(p.kind)} (the draft has {p.value??'an address withheld'})</span>
      <input value={typed[i]} maxLength={320} autoComplete="off" spellCheck={false} onChange={e=>setTyped(t=>t.map((v,j)=>j===i?e.target.value:v))}/></label>)}
    <div className="button-row"><button type="submit" className="secondary-button" disabled={busy||typed.some(t=>!t.trim())}>Use {held.length>1?'these addresses':'this address'}</button>
      <button type="button" className="text-button" onClick={onCancel}>Cancel</button></div></form>;
}
