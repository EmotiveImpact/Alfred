import {useState} from 'react';
import {ArrowClockwise,LockKey,WarningCircle} from '@phosphor-icons/react';
import {useConsole} from '../state/ConsoleProvider';
function time(iso?:string){return iso?new Intl.DateTimeFormat('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(iso)):'';}
/** Sign in with an access key, or pair this device with a one-time code from one already signed in. */
function SignIn({message}:{message?:string}){
  const{live}=useConsole(),[mode,setMode]=useState<'key'|'pair'>('key'),[key,setKey]=useState(''),[code,setCode]=useState(''),[label,setLabel]=useState('');
  const[error,setError]=useState(''),[busy,setBusy]=useState(false),[paired,setPaired]=useState<{key:string;role:string;expiresAt:number}|null>(null),[kept,setKept]=useState(false);
  if(paired)return <div className="sign-in" role="group" aria-label="Device paired"><LockKey size={26} weight="thin"/><h2>This device is paired</h2>
    <p>Its own {paired.role} access key is below. It is shown once and never stored by this page. Keep it somewhere private, such as a password manager, to sign in again after this session ends. It expires {new Date(paired.expiresAt*1000).toLocaleDateString('en-GB')}.</p>
    <output className="paired-key hash" aria-label="This device's access key">{paired.key}</output>
    <label className="consent"><input type="checkbox" checked={kept} onChange={e=>setKept(e.target.checked)}/><span>I have stored this key privately.</span></label>
    <button className="primary-button" disabled={!kept} onClick={()=>{setPaired(null);void live.continueAfterPairing();}}>Continue to ALFRED</button></div>;
  if(mode==='pair')return <form className="sign-in" onSubmit={async e=>{e.preventDefault();if(busy)return;setBusy(true);const r=await live.pairDevice(code,label);setBusy(false);setCode('');if(typeof r==='string')setError(r);else{setError('');setPaired(r);}}}>
    <LockKey size={26} weight="thin"/><h2>Pair this device</h2>
    <p>On a device already signed in, open Data and permissions and create a pairing code. This device then gets its own key; no key is copied between devices.</p>
    <label className="sr-only" htmlFor="pairing-code">Pairing code</label>
    <input id="pairing-code" autoComplete="off" spellCheck={false} value={code} maxLength={40} onChange={e=>setCode(e.target.value.trim())} placeholder="One-time pairing code"/>
    <label className="sr-only" htmlFor="device-label">Device name</label>
    <input id="device-label" autoComplete="off" value={label} maxLength={60} onChange={e=>setLabel(e.target.value)} placeholder="Name this device, for example Studio laptop"/>
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
    <button className="primary-button" type="submit" disabled={busy||code.length<10||!label.trim()}>{busy?'Pairing…':'Pair this device'}</button>
    <button type="button" className="text-button" onClick={()=>{setMode('key');setError('');}}>Use an access key instead</button></form>;
  return <form className="sign-in" onSubmit={async e=>{e.preventDefault();if(!key.trim()||busy)return;setBusy(true);const message=await live.signIn(key);setBusy(false);setKey('');setError(message??'');}}>
    <LockKey size={26} weight="thin"/><h2>Sign in to ALFRED</h2>
    <p>{message??'Use the local access key from python3 -m alfred.desk access. It is sent once to this loopback server and never stored in the browser.'}</p>
    <label className="sr-only" htmlFor="access-key">Access key</label>
    <input id="access-key" type="password" autoComplete="off" spellCheck={false} value={key} maxLength={128} onChange={e=>setKey(e.target.value)} placeholder="Access key"/>
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
    <button className="primary-button" type="submit" disabled={busy||!key.trim()}>{busy?'Signing in…':'Sign in'}</button>
    <button type="button" className="text-button" onClick={()=>{setMode('pair');setError('');}}>Pair this device with a code</button></form>;
}
/** Truthful connected states over the stage. Never substitutes fixtures for missing data. */
export function ConnectionGate(){
  const{connected,live,records}=useConsole();
  if(!connected)return null;
  const c=live.connection;
  if(c.kind==='ready')return records.length?null:<div className="connection-gate quiet" role="status"><p>No permitted records in this workspace yet.</p><small>Select a source in ALFRED to index it. Nothing is invented to fill the view.</small></div>;
  if(c.kind==='checking'||c.kind==='loading')return <div className="connection-gate quiet" role="status"><p>Connecting to ALFRED…</p></div>;
  if(c.kind==='signed_out')return <div className="connection-gate"><SignIn message={c.message}/></div>;
  if(c.kind==='unavailable'&&records.length)return <div className="connection-banner" role="status"><WarningCircle size={16}/><span>{c.message} Showing records last confirmed at {time(c.lastObservedAt)}.</span><button onClick={live.retry}><ArrowClockwise size={14}/>Retry</button></div>;
  if(c.kind==='unavailable'||c.kind==='denied')return <div className="connection-gate" role="alert"><WarningCircle size={26} weight="thin"/><p>{c.message}</p><button className="secondary-button" onClick={live.retry}><ArrowClockwise size={16}/>Try again</button></div>;
  return null;
}
