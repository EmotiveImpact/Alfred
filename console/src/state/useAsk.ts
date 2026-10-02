import {useCallback,useEffect,useRef,useState} from 'react';
import {DeskClient,DeskError} from '../integration/deskClient';
import {type SupportReport} from '../integration/answerSupport';
/** Shapes returned by the existing conversation service (alfred/conversation.py). */
export interface Evidence{source_id:string;note_id:string;title:string;path:string;kind:string;sha256:string;revision:number;start_line:number;end_line:number;excerpt:string;retrieved_via:string;basis:string}
export interface MemoryStatement{claim_id:string;subject:{id:string;kind:string;name:string};predicate:string;object:{id:string;kind:string;name:string}|null;value:string|null;support:{source_id:string;note_id:string;start_line:number;end_line:number};basis:string}
export interface ModelClaim{text:string;citations:{source_id:string;start_line:number;end_line:number}[]}
export interface TurnResult{status:string;mode:string;model_used:boolean;model:string|null;claims:ModelClaim[];support?:SupportReport;packet:{question:string;evidence:Evidence[];memory:MemoryStatement[];memory_ambiguities:{name:string;kind:string;entity_ids:string[]}[];focus:{record_id:string;label:string|null;available?:boolean}|null}}
export interface Turn{id:string;ordinal:number;question:string;mode:string;follow_up:number;state:string;focus:string|null;result:TurnResult|null}
interface SessionView{id:string;turns:Turn[]}
export type AskState=
  |{status:'idle'}
  |{status:'waiting';question:string;focusLabel:string|null}
  |{status:'done';question:string;focusLabel:string|null;turn:Turn;sessionId:string}
  |{status:'error';question:string;focusLabel:string|null;message:string};
// Withdrawn answers are final too: forgetting or removing a source never leaves a question waiting.
const FINAL=new Set(['completed','source_changed','focus_unavailable','failed','interrupted','memory_forgotten','source_forgotten']);
const ERRORS:Record<string,string>={local_model_not_configured:'No local model is configured. Ask in source mode.',model_workspace_not_authorised:'This access key may not send content to the local model.',conversation_processing_paused:'ALFRED is paused. Resume it to ask questions.',conversation_rate_limited:'Too many questions in the last minute. Try again shortly.',conversation_queue_full:'ALFRED is busy. Try again shortly.',conversation_busy:'The previous question is still being answered.',question_required:'Ask a slightly longer question.',question_too_complex:'Shorten the question.',invalid_focus:'The selected record cannot be used as context.'};
function requestId(){const c=globalThis.crypto;return 'console-'+(c?.randomUUID?c.randomUUID():Math.random().toString(36).slice(2)+Date.now().toString(36));}
const wait=(ms:number,signal:AbortSignal)=>new Promise<void>((resolve,reject)=>{const t=setTimeout(resolve,ms);signal.addEventListener('abort',()=>{clearTimeout(t);reject(new DOMException('aborted','AbortError'));},{once:true});});
/**
 * Asks through the existing bounded conversation queue. A selected record travels as
 * `focus`; the server re-authorises it and labels it as context, never as authority.
 */
export function useAsk(client:DeskClient,onSignedOut:(error:unknown)=>void){
  const[state,setState]=useState<AskState>({status:'idle'});
  const session=useRef<string|null>(null),controller=useRef<AbortController|null>(null);
  const reset=useCallback(()=>{controller.current?.abort();controller.current=null;session.current=null;setState({status:'idle'});},[]);
  useEffect(()=>()=>controller.current?.abort(),[]);
  const ensureSession=useCallback(async(signal:AbortSignal)=>{
    if(session.current){try{return await client.get<SessionView>('/desk/conversations/'+session.current,signal);}catch(e){if(!(e instanceof DeskError&&e.kind==='not_found'))throw e;session.current=null;}}
    const created=await client.post<SessionView>('/desk/conversations',{title:'Console questions'},signal);session.current=created.id;return created;
  },[client]);
  const ask=useCallback(async(question:string,options:{focus:string|null;focusLabel:string|null;mode:'sources'|'local_model';followUp:boolean})=>{
    controller.current?.abort();const c=new AbortController();controller.current=c;
    setState({status:'waiting',question,focusLabel:options.focusLabel});
    try{
      let view=await ensureSession(c.signal),submitted:{turn_id:string}|null=null;
      for(let attempt=0;attempt<2&&!submitted;attempt++){
        try{submitted=await client.post<{turn_id:string}>(`/desk/conversations/${view.id}/turns`,{question,mode:options.mode,follow_up:options.followUp,request_id:requestId(),after:view.turns.length,focus:options.focus},c.signal);}
        catch(e){if(attempt===0&&e instanceof DeskError&&(e.code==='conversation_changed'||e.code==='conversation_not_found')){if(e.code==='conversation_not_found')session.current=null;view=await ensureSession(c.signal);continue;}throw e;}
      }
      const deadline=Date.now()+95000;
      while(Date.now()<deadline){
        await wait(350,c.signal);
        const current=await client.get<SessionView>('/desk/conversations/'+view.id,c.signal),turn=current.turns.find(t=>t.id===submitted!.turn_id);
        if(!turn){setState({status:'error',question,focusLabel:options.focusLabel,message:'The question is no longer available.'});return;}
        if(FINAL.has(turn.state)){setState({status:'done',question,focusLabel:options.focusLabel,turn,sessionId:view.id});return;}
      }
      setState({status:'error',question,focusLabel:options.focusLabel,message:'No result within the time limit. Nothing was invented.'});
    }catch(e){
      if(e instanceof DOMException&&e.name==='AbortError')return;
      if(e instanceof DeskError&&e.kind==='signed_out'){onSignedOut(e);return;}
      setState({status:'error',question,focusLabel:options.focusLabel,message:e instanceof DeskError?ERRORS[e.code]??`ALFRED could not answer (${e.code}).`:'ALFRED could not be reached.'});
    }
  },[client,ensureSession,onSignedOut]);
  /** Re-read the saved turn; the server withdraws it if any source or review changed. */
  const recheck=useCallback(async()=>{
    if(state.status!=='done')return;
    try{const current=await client.get<SessionView>('/desk/conversations/'+state.sessionId),turn=current.turns.find(t=>t.id===state.turn.id);
      if(turn&&(turn.state!==state.turn.state||(turn.result===null)!==(state.turn.result===null)))setState({...state,turn});}
    catch(e){if(e instanceof DeskError&&e.kind==='signed_out')onSignedOut(e);}
  },[client,onSignedOut,state]);
  return{state,ask,reset,recheck};
}
