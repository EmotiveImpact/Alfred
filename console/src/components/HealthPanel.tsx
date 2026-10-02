import {useCallback,useEffect,useState} from 'react';
import {useConsole} from '../state/ConsoleProvider';
import {DeskError} from '../integration/deskClient';
export interface HostHealth{checkedAt:string;paused:boolean;role:'owner'|'reader';
  host:{status:string;lastCycle:string|null;intervalSeconds:number|null;error:string|null};
  vault:{configured:boolean;status:string|null;lastScan:string|null;notes:number|null;issues:number};
  jobs:{configured:boolean;byState:Record<string,number>;backend:string|null};
  questions:{configured:boolean;waiting:number};
  model:{configured:boolean;name:string|null;allowed:boolean};
  lifecycle:{lastBackup:string|null;journalEntries:number}|null}
const time=(iso:string|null)=>iso?new Date(iso).toLocaleString('en-GB'):'never';
const HOST:Record<string,string>={paused:'Paused',idle:'Running, nothing to do',running:'Running',error:'Stopped by an error',starting:'Starting'};
/** What the local host is doing, read on request, with the owner's pause control. */
export function HealthPanel(){
  const c=useConsole(),[health,setHealth]=useState<HostHealth|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[confirm,setConfirm]=useState(false);
  const load=useCallback(async()=>{try{setHealth(await c.live.client.get<HostHealth>('/desk/console/health'));setError('');}catch(e){setError(e instanceof DeskError?`The host could not report its state (${e.code}).`:'ALFRED could not be reached.');}},[c.live.client]);
  useEffect(()=>{void load();},[load]);
  const setPaused=async(paused:boolean)=>{setBusy(true);try{await c.live.client.post('/desk/pause',{paused});setConfirm(false);c.setNotice(paused?'ALFRED is paused. Scanning, questions and drafts wait until you resume.':'ALFRED resumed.');await load();void c.live.refresh();}
    catch(e){setError(e instanceof DeskError?`ALFRED refused this (${e.code}).`:'ALFRED could not be reached.');}finally{setBusy(false);}};
  if(!health)return <p className="dialog-note" role="status">{error||'Reading the host state…'}</p>;
  const jobs=Object.entries(health.jobs.byState).map(([state,count])=>`${count} ${state.replaceAll('_',' ')}`).join(', ');
  return <section className="connection-list health-panel" aria-label="Host health"><h3>Host health</h3>
    <div><span>ALFRED host</span><b>{health.paused?'Paused':HOST[health.host.status]??health.host.status}{health.host.error?` · ${health.host.error}`:''}</b></div>
    <div><span>Last background cycle</span><b>{time(health.host.lastCycle)}</b></div>
    <div><span>Vault</span><b>{health.vault.configured?`${health.vault.status??'unknown'} · ${health.vault.notes??0} notes · scanned ${time(health.vault.lastScan)}${health.vault.issues?` · ${health.vault.issues} issues`:''}`:'Not configured'}</b></div>
    <div><span>Questions waiting</span><b>{health.questions.configured?health.questions.waiting:'Not configured'}</b></div>
    <div><span>Jobs</span><b>{health.jobs.configured?`${jobs||'none'} · ${health.jobs.backend}`:'No job worker on this host'}</b></div>
    {health.lifecycle&&<div><span>Last backup</span><b>{time(health.lifecycle.lastBackup)} · {health.lifecycle.journalEntries} journal entries</b></div>}
    <p className="dialog-note">Checked {time(health.checkedAt)}. This is the host's own report; it runs only while the foreground process is open and is not an installed service.</p>
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
    {health.role==='owner'&&(health.paused?<button className="secondary-button" disabled={busy} onClick={()=>void setPaused(false)}>Resume ALFRED</button>
      :confirm?<div className="forget-confirm" role="group" aria-label="Confirm pause"><p className="dialog-note">Pausing stops scanning, questions, routines and new draft execution. Records stay; completed work is not undone.</p>
        <div className="button-row"><button className="secondary-button" disabled={busy} onClick={()=>void setPaused(true)}>Pause now</button><button className="text-button" onClick={()=>setConfirm(false)}>Keep running</button></div></div>
      :<button className="text-button" onClick={()=>setConfirm(true)}>Pause ALFRED</button>)}
    <button className="text-button" onClick={()=>void load()}>Check again</button></section>;
}
