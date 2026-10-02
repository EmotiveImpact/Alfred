import {useEffect,useState} from 'react';
import {ArrowsOut,MagnifyingGlass} from '@phosphor-icons/react';
import {SCOPES,type Scope} from '../domain/model';
import {useConsole} from '../state/ConsoleProvider';
export function WorkspaceHeader(){
  const{state,switchScope,setModal,setQuery,dispatch}=useConsole(),[clock,setClock]=useState(new Date());
  useEffect(()=>{const id=setInterval(()=>setClock(new Date()),30000);return()=>clearInterval(id);},[]);
  return <header className="workspace-header"><div className="workspace-identity"><span className="header-wordmark">ALFRED</span><span className="header-divider"/><label className="sr-only" htmlFor="scope-select">Workspace</label><select id="scope-select" value={state.scope} onChange={e=>switchScope(e.target.value as Scope)}>{SCOPES.map(s=><option key={s} value={s}>{s==='operation'?'Operations':s[0].toUpperCase()+s.slice(1)}</option>)}</select></div>
    <div className="header-actions"><button className="demo-state" title="Fictional local data. No model, account or microphone is connected." onClick={()=>setModal('settings')}><i/>Demo workspace</button><time dateTime={clock.toISOString()}>{new Intl.DateTimeFormat('en-GB',{weekday:'short',day:'2-digit',month:'short'}).format(clock)}<span>{new Intl.DateTimeFormat('en-GB',{hour:'2-digit',minute:'2-digit'}).format(clock)}</span></time><button className="icon-button" aria-label="Search workspace" onClick={()=>{setQuery('');setModal('search');}}><MagnifyingGlass size={18}/></button><button className="icon-button" aria-label={state.focus?'Exit focus mode':'Enter focus mode'} aria-pressed={state.focus} onClick={()=>dispatch({type:'focus'})}><ArrowsOut size={18}/></button></div>
  </header>;
}
