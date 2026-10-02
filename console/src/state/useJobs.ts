import {useCallback,useEffect,useRef,useState} from 'react';
import {DeskClient,DeskError} from '../integration/deskClient';
import {type JobArtefact,type JobEvent,type JobEvents,type JobKind,type JobView,jobError,mergeEvents,requestKey} from '../integration/jobs';
export interface FollowedJob{id:string;job:JobView|null;events:JobEvent[];cursor:number;result:JobArtefact|null;resultError:string}
const wait=(ms:number,signal:AbortSignal)=>new Promise<void>((resolve,reject)=>{const t=setTimeout(resolve,ms);signal.addEventListener('abort',()=>{clearTimeout(t);reject(new DOMException('aborted','AbortError'));},{once:true});});
const aborted=(e:unknown)=>e instanceof DOMException&&e.name==='AbortError';
/**
 * Follows jobs on the existing coordinator. The event cursor is kept in memory, so leaving
 * the panel and coming back resumes after the last event this page saw: nothing is replayed
 * or skipped. Polling runs only while the panel is open. Nothing is written to storage.
 */
export function useJobs(client:DeskClient,onSignedOut:(error:unknown)=>void){
  const[jobs,setJobs]=useState<JobView[]>([]),[backend,setBackend]=useState(''),[loaded,setLoaded]=useState(false);
  const[followed,setFollowed]=useState<FollowedJob|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const current=useRef<FollowedJob|null>(null),loop=useRef<AbortController|null>(null),open=useRef(false);
  const publish=(next:FollowedJob|null)=>{current.current=next;setFollowed(next);};
  const report=useCallback((e:unknown)=>{
    if(aborted(e))return;
    if(e instanceof DeskError&&e.kind==='signed_out'){onSignedOut(e);return;}
    setError(e instanceof DeskError?jobError(e.code):'ALFRED could not be reached.');
  },[onSignedOut]);
  const refresh=useCallback(async(signal?:AbortSignal)=>{
    try{const r=await client.get<{jobs:JobView[];backend:string}>('/desk/jobs',signal);setJobs(r.jobs);setBackend(r.backend);setLoaded(true);}catch(e){report(e);}
  },[client,report]);
  const run=useCallback(async(id:string,signal:AbortSignal)=>{
    let state:FollowedJob=current.current?.id===id?current.current:{id,job:null,events:[],cursor:0,result:null,resultError:''};
    for(;;){
      const page=await client.get<JobEvents>(`/desk/jobs/${encodeURIComponent(id)}/events?after=${state.cursor}`,signal);
      const job=await client.get<JobView>('/desk/jobs/'+encodeURIComponent(id),signal);
      state={...state,job,events:mergeEvents(state.events,page.events),cursor:page.next_cursor};publish(state);
      if(page.more)continue;
      if(page.finished)break;
      await wait(900,signal);
    }
    if(state.job?.result&&!state.result){
      // The server rechecks the result's lineage and the reader's access on every read.
      try{state={...state,result:await client.get<JobArtefact>('/desk/jobs/artefacts/'+state.job.result.sha256,signal),resultError:''};}
      catch(e){if(aborted(e)||(e instanceof DeskError&&e.kind==='signed_out'))throw e;state={...state,resultError:e instanceof DeskError?jobError(e.code):'ALFRED could not be reached.'};}
      publish(state);
    }
    void refresh(signal);
  },[client,refresh]);
  const follow=useCallback((id:string)=>{
    loop.current?.abort();const c=new AbortController();loop.current=c;setError('');
    if(current.current?.id!==id)publish({id,job:null,events:[],cursor:0,result:null,resultError:''});
    void run(id,c.signal).catch(report);
  },[run,report]);
  const show=useCallback(()=>{
    open.current=true;void refresh();
    const f=current.current;if(f&&(!f.job?.finished||(f.job.result&&!f.result&&!f.resultError)))follow(f.id);
  },[refresh,follow]);
  const hide=useCallback(()=>{open.current=false;loop.current?.abort();loop.current=null;},[]);
  const submit=useCallback(async(kind:JobKind,parameters:Record<string,number>,note:string,revision:number)=>{
    setBusy(true);setError('');
    try{
      const job=await client.post<JobView>('/desk/jobs',{idempotency_key:requestKey(),kind,parameters,inputs:[{note,revision}],side_effect_free:true});
      publish({id:job.id,job,events:[],cursor:0,result:null,resultError:''});return true;
    }catch(e){report(e);return false;}finally{setBusy(false);}
  },[client,report]);
  const cancel=useCallback(async(id:string)=>{
    setBusy(true);setError('');
    try{await client.post<JobView>(`/desk/jobs/${encodeURIComponent(id)}/cancel`,{});if(open.current)follow(id);}catch(e){report(e);}finally{setBusy(false);}
  },[client,follow,report]);
  // Lost or changed authority: forget everything this page learned about jobs.
  const reset=useCallback(()=>{loop.current?.abort();loop.current=null;publish(null);setJobs([]);setBackend('');setLoaded(false);setError('');},[]);
  useEffect(()=>()=>loop.current?.abort(),[]);
  return{jobs,backend,loaded,followed,busy,error,show,hide,follow,submit,cancel,reset};
}
export type JobsController=ReturnType<typeof useJobs>;
