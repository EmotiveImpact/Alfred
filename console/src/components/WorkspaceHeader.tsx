import {useEffect,useState} from 'react';
import {ArrowsOut,MagnifyingGlass} from '@phosphor-icons/react';
import {SCOPES} from '../domain/model';
import {type ConnectionState} from '../integration/ConsoleReadPort';
import {useConsole} from '../state/ConsoleProvider';
function connectionLabel(c:ConnectionState){
  switch(c.kind){
  case 'ready':return{label:'Connected',title:`Records from your ALFRED server, confirmed ${new Date(c.observedAt).toLocaleTimeString('en-GB')}. Source mode; no model answers are generated here.`};
  case 'unavailable':return{label:'Unreachable',title:c.lastObservedAt?`Last confirmed ${new Date(c.lastObservedAt).toLocaleTimeString('en-GB')}. Shown records may be out of date.`:c.message};
  case 'signed_out':return{label:'Signed out',title:'Sign in with your local ALFRED access key.'};
  case 'denied':return{label:'Access refused',title:c.message};
  default:return{label:'Connecting',title:'Checking your ALFRED session.'};
  }
}
export function WorkspaceHeader(){
  const{state,switchScope,setModal,setQuery,dispatch,connected,live}=useConsole(),[clock,setClock]=useState(new Date());
  const status=connectionLabel(live.connection);
  useEffect(()=>{const id=setInterval(()=>setClock(new Date()),30000);return()=>clearInterval(id);},[]);
  return <header className="workspace-header"><div className="workspace-identity"><span className="header-wordmark">ALFRED</span><span className="header-divider"/><label className="sr-only" htmlFor="scope-select">Workspace</label>{connected?<select id="scope-select" value={state.scope} disabled={live.workspaces.length<2} onChange={e=>switchScope(e.target.value)}>{live.workspaces.length?live.workspaces.map(w=><option key={w.id} value={w.id}>{w.label}</option>):<option value="">No workspace</option>}</select>
      :<select id="scope-select" value={state.scope} onChange={e=>switchScope(e.target.value)}>{SCOPES.map(s=><option key={s} value={s}>{s==='operation'?'Operations':s[0].toUpperCase()+s.slice(1)}</option>)}</select>}</div>
    <div className="header-actions">{connected?<button className="demo-state connection-state" data-state={live.connection.kind} title={status.title} onClick={()=>setModal('settings')}><i/>{status.label}</button>:<button className="demo-state" title="Fictional local data. No model, account or microphone is connected." onClick={()=>setModal('settings')}><i/>Demo workspace</button>}<time dateTime={clock.toISOString()}>{new Intl.DateTimeFormat('en-GB',{weekday:'short',day:'2-digit',month:'short'}).format(clock)}<span>{new Intl.DateTimeFormat('en-GB',{hour:'2-digit',minute:'2-digit'}).format(clock)}</span></time><button className="icon-button" aria-label="Search workspace" onClick={()=>{setQuery('');setModal('search');}}><MagnifyingGlass size={18}/></button><button className="icon-button" aria-label={state.focus?'Exit focus mode':'Enter focus mode'} aria-pressed={state.focus} onClick={()=>dispatch({type:'focus'})}><ArrowsOut size={18}/></button></div>
  </header>;
}
