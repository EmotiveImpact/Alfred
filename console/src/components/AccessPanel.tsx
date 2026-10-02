import {useCallback,useEffect,useState} from 'react';
import {useConsole} from '../state/ConsoleProvider';
import {DeskError} from '../integration/deskClient';
interface SourceAccess{source:string;label:string;permitted:Record<string,boolean>;credential_expires:number}
interface IdentityView{person_id:string;device_id:string;role:'owner'|'reader';mode:'legacy_scope'|'explicit_grants';epoch:number;sources:SourceAccess[];grants:{source:string;capability:string;expires:number}[]}
const CAPS:{id:string;label:string;note:string}[]=[{id:'read',label:'Read',note:'See and search this source'},{id:'model',label:'Model',note:'Send excerpts to the local model'},{id:'inbox.write',label:'Inbox notes',note:'Create approved notes in ALFRED/Inbox'}];
const ERRORS:Record<string,string>={policy_changed:'Access changed elsewhere. The panel has been refreshed.',invitation_not_valid:'That code is not valid, has been used or has expired.',invalid_capability:'That capability cannot be shared by invitation.',source_not_available:'That source is no longer available.'};
function message(e:unknown){return e instanceof DeskError?ERRORS[e.code]??`ALFRED refused this (${e.code}).`:'ALFRED could not be reached.';}
const short=(id:string)=>id.replace(/^(person|device)-/,'').slice(0,8);
/** Owner-controlled source grants. Changing access rebuilds every view from the server. */
export function AccessPanel(){
  const c=useConsole(),[view,setView]=useState<IdentityView|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const[inviteSource,setInviteSource]=useState(''),[inviteCap,setInviteCap]=useState('read'),[code,setCode]=useState<{code:string;expires:number}|null>(null),[redeem,setRedeem]=useState('');
  const load=useCallback(async()=>{try{const v=await c.live.client.get<IdentityView>('/desk/identity');setView(v);setInviteSource(s=>s||v.sources[0]?.source||'');}catch(e){setError(message(e));}},[c.live.client]);
  useEffect(()=>{void load();},[load]);
  const run=async(path:string,body:object,after?:(r:unknown)=>void)=>{setBusy(true);setError('');try{c.expectAccessChange();const r=await c.live.client.post(path,body);after?.(r);await load();void c.live.refresh();}catch(e){setError(message(e));await load();}finally{setBusy(false);}};
  if(!view)return <p className="dialog-note" role="status">{error||'Reading your access…'}</p>;
  const owner=view.role==='owner';
  return <div className="access-panel">
    <dl className="detail-list"><div><dt>Person</dt><dd className="hash">{short(view.person_id)}</dd></div><div><dt>This device</dt><dd className="hash">{short(view.device_id)}</dd></div><div><dt>Role</dt><dd>{view.role}</dd></div><div><dt>Access mode</dt><dd>{view.mode==='explicit_grants'?'Explicit grants':'Whole workspace (legacy)'}</dd></div></dl>
    {view.mode==='legacy_scope'&&owner&&<div className="forget-confirm"><p className="dialog-note">Explicit grants make every source invisible, to you as well, until it is granted. Writing notes always needs its own grant.</p><button className="secondary-button" disabled={busy} onClick={()=>void run('/desk/identity/enable',{epoch:view.epoch})}>Use explicit grants</button></div>}
    <section className="ask-section"><h3>Sources</h3>{view.sources.length?view.sources.map(s=><div className="access-source" key={s.source}><strong>{s.label}</strong>
      <div className="access-caps">{CAPS.map(cap=>{const on=Boolean(s.permitted[cap.id]);const toggle=owner&&view.mode==='explicit_grants';
        return toggle?<button key={cap.id} role="switch" aria-checked={on} aria-label={`${cap.label} for ${s.label}`} title={cap.note} className={`access-chip ${on?'on':''}`} disabled={busy} onClick={()=>void run('/desk/identity/grants',{source:s.source,capability:cap.id,days:30,epoch:view.epoch,revoke:on})}>{cap.label}</button>
          :<span key={cap.id} className={`access-chip ${on?'on':''}`} title={cap.note}>{cap.label}</span>;})}</div></div>)
      :<p className="quiet-empty">{owner?'No sources are selected in this workspace.':'You hold no grants yet. Redeem a code from the workspace owner.'}</p>}</section>
    {owner&&view.sources.length>0&&<section className="ask-section"><h3>Invite another person</h3><p className="dialog-note">A one-time code, valid for fifteen minutes, that grants one capability on one source to whoever redeems it with their own key. Inbox writing cannot be shared.</p>
      <div className="inline-pair"><label>Source<select value={inviteSource} onChange={e=>setInviteSource(e.target.value)}>{view.sources.map(s=><option key={s.source} value={s.source}>{s.label}</option>)}</select></label><label>Capability<select value={inviteCap} onChange={e=>setInviteCap(e.target.value)}><option value="read">Read</option><option value="model">Model</option></select></label></div>
      <button className="secondary-button" disabled={busy||!inviteSource} onClick={()=>void run('/desk/identity/invitations',{source:inviteSource,capability:inviteCap,days:1,epoch:view.epoch},r=>{const v=r as {code:string;expires_at:number};setCode({code:v.code,expires:v.expires_at});})}>Create one-time code</button>
      {code&&<p className="invitation-code" aria-label="One-time code"><span className="hash">{code.code}</span><small>Expires {new Date(code.expires*1000).toLocaleTimeString('en-GB')}. Share it privately.</small></p>}</section>}
    <section className="ask-section"><h3>Redeem a code</h3><div className="follow-up"><label className="sr-only" htmlFor="redeem-code">One-time code</label><input id="redeem-code" value={redeem} maxLength={40} onChange={e=>setRedeem(e.target.value.trim())} placeholder="Paste a code from the workspace owner"/><button className="text-button" disabled={busy||redeem.length<10} onClick={()=>void run('/desk/identity/invitations/redeem',{code:redeem},()=>{setRedeem('');c.setNotice('Code redeemed. Your view now includes what it grants.');})}>Redeem</button></div></section>
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
  </div>;
}
