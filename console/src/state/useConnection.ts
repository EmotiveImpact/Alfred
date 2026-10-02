import {useCallback,useEffect,useMemo,useRef,useState,type Dispatch} from 'react';
import {type ConsoleAction} from '../domain/model';
import {type ConsoleMode} from '../integration/mode';
import {DeskClient,DeskError,type SessionInfo} from '../integration/deskClient';
import {type ConnectionState,type PermittedWorkspace,type RecordDetail} from '../integration/ConsoleReadPort';
import {emptyConnectedSnapshot,toSnapshot} from '../integration/toSnapshot';
export const REFRESH_INTERVAL_MS=8000;
export type DetailState={status:'idle'}|{status:'loading';id:string}|{status:'ready';id:string;detail:RecordDetail}|{status:'unavailable';id:string;message:string};
function isAbort(error:unknown){return error instanceof DOMException&&error.name==='AbortError';}
/**
 * Owns the authenticated read path. Every response replaces the projection wholesale; a
 * grant or workspace change clears selection; sign-out and revocation clear all records.
 * Network loss keeps the last confirmed projection but labels it with its confirmation time.
 */
export function useConnection(mode:ConsoleMode,dispatch:Dispatch<ConsoleAction>,notify:(message:string)=>void,onAuthorityLost:(kind:'cleared'|'changed')=>boolean){
  const client=useMemo(()=>new DeskClient(),[]);
  const[connection,setConnection]=useState<ConnectionState>(mode==='demo'?{kind:'demo'}:{kind:'checking'});
  const[session,setSession]=useState<SessionInfo|null>(null);
  const[workspaces,setWorkspaces]=useState<readonly PermittedWorkspace[]>([]);
  const sessionRef=useRef<SessionInfo|null>(null),last=useRef<{data?:string;grant?:string;observedAt?:string}>({});
  const inflight=useRef<AbortController|null>(null),retried=useRef(false);
  const clear=useCallback((next:ConnectionState)=>{
    inflight.current?.abort();inflight.current=null;sessionRef.current=null;last.current={};client.forget();
    setSession(null);setWorkspaces([]);dispatch({type:'projection',snapshot:emptyConnectedSnapshot()});onAuthorityLost('cleared');setConnection(next);
  },[client,dispatch,onAuthorityLost]);
  const fail=useCallback((error:unknown)=>{
    if(isAbort(error))return;
    if(error instanceof DeskError&&error.kind==='signed_out'){clear({kind:'signed_out',message:'Your session ended or this access key was revoked. Records were cleared.'});return;}
    if(error instanceof DeskError&&error.kind==='denied'){clear({kind:'denied',message:'This browser request was refused by the ALFRED server.'});return;}
    if(error instanceof DeskError&&error.kind==='unavailable'){setConnection({kind:'unavailable',message:'ALFRED is not reachable.',lastObservedAt:last.current.observedAt});return;}
    if(error instanceof DeskError){setConnection({kind:'unavailable',message:`The server could not build this view (${error.code}).`,lastObservedAt:last.current.observedAt});return;}
    clear({kind:'unavailable',message:'The server returned a projection this console cannot verify. Nothing is shown.'});
  },[clear]);
  const refresh=useCallback(async()=>{
    const current=sessionRef.current;if(!current)return;
    inflight.current?.abort();const controller=new AbortController();inflight.current=controller;
    try{
      const projection=await client.readProjection(controller.signal);
      if(controller.signal.aborted||sessionRef.current!==current)return;
      const snapshot=toSnapshot(projection,current.scope),previous=last.current;
      if(previous.grant&&previous.grant!==snapshot.grantRevision&&!onAuthorityLost('changed'))notify('Access changed. The view was rebuilt from current permissions.');
      if(previous.data!==snapshot.dataRevision||previous.grant!==snapshot.grantRevision)dispatch({type:'projection',snapshot});
      last.current={data:snapshot.dataRevision,grant:snapshot.grantRevision,observedAt:snapshot.observedAt};retried.current=false;
      setConnection({kind:'ready',workspaceId:snapshot.workspaceId!,observedAt:snapshot.observedAt!});
    }catch(error){
      if(error instanceof DeskError&&error.kind==='conflict'&&!retried.current){retried.current=true;setTimeout(()=>void refresh(),250);return;}
      fail(error);
    }finally{if(inflight.current===controller)inflight.current=null;}
  },[client,dispatch,fail,notify,onAuthorityLost]);
  const start=useCallback(async()=>{
    try{
      const info=await client.session();sessionRef.current=info;setSession(info);setConnection({kind:'loading',workspaceId:info.scope});
      const controller=new AbortController();setWorkspaces(await client.permittedWorkspaces(controller.signal));
      await refresh();
    }catch(error){
      if(error instanceof DeskError&&error.kind==='signed_out'){clear({kind:'signed_out'});return;}
      fail(error);
    }
  },[client,clear,fail,refresh]);
  useEffect(()=>{if(mode==='connected')void start();return()=>inflight.current?.abort();},[mode,start]);
  useEffect(()=>{
    if(mode!=='connected'||!session)return;
    const tick=()=>{if(!document.hidden)void refresh();};
    const id=setInterval(tick,REFRESH_INTERVAL_MS);document.addEventListener('visibilitychange',tick);
    return()=>{clearInterval(id);document.removeEventListener('visibilitychange',tick);};
  },[mode,session,refresh]);
  const signIn=useCallback(async(key:string)=>{
    try{await client.login(key.trim());await start();return null;}
    catch(error){
      if(error instanceof DeskError&&error.code==='login_rate_limited')return 'Too many attempts. Wait a minute and try again.';
      if(error instanceof DeskError&&error.kind==='unavailable')return 'ALFRED is not reachable.';
      return 'That access key was not accepted.';
    }
  },[client,start]);
  const signOut=useCallback(async()=>{try{await client.logout();}catch{/* the local view is cleared regardless */}clear({kind:'signed_out',message:'Signed out. Records were cleared from this view.'});},[client,clear]);
  const retry=useCallback(()=>{if(sessionRef.current)void refresh();else void start();},[refresh,start]);
  return {client,connection,session,workspaces,refresh,retry,signIn,signOut,fail};
}
/** Abortable inspection of one permitted record, re-read whenever the projection changes. */
export function useRecordDetail(client:DeskClient,enabled:boolean,id:string|null,dataRevision:string|undefined,onError:(error:unknown)=>void):DetailState{
  const[state,setState]=useState<DetailState>({status:'idle'});
  useEffect(()=>{
    if(!enabled||!id){setState({status:'idle'});return;}
    const controller=new AbortController();setState({status:'loading',id});
    client.inspectRecord(id,controller.signal).then(detail=>{if(!controller.signal.aborted)setState({status:'ready',id,detail});}).catch(error=>{
      if(isAbort(error))return;
      if(error instanceof DeskError&&error.kind==='not_found'){setState({status:'unavailable',id,message:'This record is no longer available to you.'});return;}
      setState({status:'unavailable',id,message:'The record could not be inspected right now.'});onError(error);
    });
    return()=>controller.abort();
  },[client,enabled,id,dataRevision,onError]);
  return state;
}
