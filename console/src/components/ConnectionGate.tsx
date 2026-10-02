import {useState} from 'react';
import {ArrowClockwise,LockKey,WarningCircle} from '@phosphor-icons/react';
import {useConsole} from '../state/ConsoleProvider';
function time(iso?:string){return iso?new Intl.DateTimeFormat('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(iso)):'';}
/** Truthful connected states over the stage. Never substitutes fixtures for missing data. */
export function ConnectionGate(){
  const{connected,live,records}=useConsole(),[key,setKey]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  if(!connected)return null;
  const c=live.connection;
  if(c.kind==='ready')return records.length?null:<div className="connection-gate quiet" role="status"><p>No permitted records in this workspace yet.</p><small>Select a source in ALFRED to index it. Nothing is invented to fill the view.</small></div>;
  if(c.kind==='checking'||c.kind==='loading')return <div className="connection-gate quiet" role="status"><p>Connecting to ALFRED…</p></div>;
  if(c.kind==='signed_out')return <div className="connection-gate"><form className="sign-in" onSubmit={async e=>{e.preventDefault();if(!key.trim()||busy)return;setBusy(true);const message=await live.signIn(key);setBusy(false);setKey('');setError(message??'');}}>
    <LockKey size={26} weight="thin"/><h2>Sign in to ALFRED</h2>
    <p>{c.message??'Use the local access key from python3 -m alfred.desk access. It is sent once to this loopback server and never stored in the browser.'}</p>
    <label className="sr-only" htmlFor="access-key">Access key</label>
    <input id="access-key" type="password" autoComplete="off" spellCheck={false} value={key} maxLength={128} onChange={e=>setKey(e.target.value)} placeholder="Access key"/>
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
    <button className="primary-button" type="submit" disabled={busy||!key.trim()}>{busy?'Signing in…':'Sign in'}</button></form></div>;
  if(c.kind==='unavailable'&&records.length)return <div className="connection-banner" role="status"><WarningCircle size={16}/><span>{c.message} Showing records last confirmed at {time(c.lastObservedAt)}.</span><button onClick={live.retry}><ArrowClockwise size={14}/>Retry</button></div>;
  if(c.kind==='unavailable'||c.kind==='denied')return <div className="connection-gate" role="alert"><WarningCircle size={26} weight="thin"/><p>{c.message}</p><button className="secondary-button" onClick={live.retry}><ArrowClockwise size={16}/>Try again</button></div>;
  return null;
}
