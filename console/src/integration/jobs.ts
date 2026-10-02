/**
 * Shapes and wording for the existing stage 0 job coordinator (alfred/jobs.py).
 * Results are parsed as data and rendered as text, never as markup.
 */
export type JobState='queued'|'leased'|'running'|'cancel_requested'|'succeeded'|'failed'|'cancelled'|'effect_unknown'|'reconciled';
export interface JobInput{type:'note'|'artefact';id?:string;source?:string;revision?:number;sha256?:string}
export interface JobView{id:string;kind:string;state:JobState;reason:string|null;attempt:number;max_attempts:number;created_at:number;updated_at:number;
  inputs:JobInput[];result:{sha256:string;size:number;media_type:string;basis:string}|null;last_sequence:number;finished:boolean;cancel_requested:boolean;needs_reconciliation:boolean;side_effect_free:boolean}
export interface JobEvent{sequence:number;kind:string;detail:Record<string,unknown>;at:number}
export interface JobEvents{job:string;state:JobState;finished:boolean;events:JobEvent[];next_cursor:number;more:boolean}
export interface JobArtefact{sha256:string;size:number;media_type:string;job_id:string;created_at:number;text?:string;served_from:string}
export type JobKind='word_count'|'summarise_lines';
/** Only the first-party kinds a person would choose. The test-only wait kind is not offered. */
export const JOB_KINDS:{id:JobKind;label:string;note:string}[]=[
  {id:'word_count',label:'Count words and lines',note:'A deterministic count, not an interpretation.'},
  {id:'summarise_lines',label:'Extract the first lines',note:'Extractive: the first non-empty lines. Not a model summary.'}];
const KIND_LABEL:Record<string,string>={word_count:'Word and line count',summarise_lines:'First lines (extractive)',wait:'Timed test job'};
export const kindLabel=(kind:string)=>KIND_LABEL[kind]??kind.replaceAll('_',' ');
const STATE_LABEL:Record<JobState,string>={queued:'Queued',leased:'Assigned to a worker',running:'Running',cancel_requested:'Cancellation requested',succeeded:'Finished',failed:'Failed',cancelled:'Cancelled',effect_unknown:'Outcome unknown · needs your check',reconciled:'Checked by you'};
export const stateLabel=(state:JobState)=>STATE_LABEL[state]??state;
const REASON:Record<string,string>={inputs_denied:'An input is no longer permitted or available.',inputs_changed:'The note changed after the job was submitted, so it was not run on the newer text.',authority_revoked:'The access key that submitted it was revoked.',cancelled_before_lease:'Cancelled before any worker started it.',attempts_exhausted:'Stopped after its permitted attempts.',process_failed:'The worker process ended with an error.',process_killed:'The worker process was stopped by a time or memory limit, or by cancellation.',artefact_hash_mismatch:'The result did not match its hash and was rejected.',lease_expired_requeued:'The worker stopped responding, so the job was queued again.',lease_expired_with_possible_effect:'The worker stopped responding after starting, so the outcome is unknown.',lease_expired_after_cancel_request:'The worker stopped responding after cancellation was requested.'};
export const reasonLabel=(reason:string|null)=>reason?REASON[reason]??reason.replaceAll('_',' '):'';
const EVENT_LABEL:Record<string,string>={submitted:'Submitted',leased:'Assigned to the local worker',started:'Started in a local subprocess',succeeded:'Finished and result stored',failed:'Failed',cancelled:'Cancelled',cancel_requested:'Cancellation requested',completed_after_cancel_request:'Completed before cancellation took effect',dispatch_denied:'Refused before running',lease_expired:'Worker stopped responding',lease_revoked:'Worker revoked',retry_scheduled:'Retry scheduled',result_rejected:'Result rejected: its hash did not match',reconciled:'Outcome recorded by you',effect_unknown:'Outcome unknown'};
export const eventLabel=(event:JobEvent)=>{
  const base=EVENT_LABEL[event.kind]??event.kind.replaceAll('_',' ');
  const reason=typeof event.detail.reason==='string'?reasonLabel(event.detail.reason):'';
  return reason?`${base}. ${reason}`:base;
};
/** Merge a page of events after a cursor without duplicates, in sequence order. */
export function mergeEvents(known:readonly JobEvent[],page:readonly JobEvent[]):JobEvent[]{
  const bySequence=new Map(known.map(e=>[e.sequence,e]));for(const e of page)bySequence.set(e.sequence,e);
  return [...bySequence.values()].sort((a,b)=>a.sequence-b.sequence);
}
export type ResultLine={label:string;value:string};
export interface ReadableResult{basis:string;lines:ResultLine[];selected:string[]}
const BASIS:Record<string,string>={deterministic_count_not_interpretation:'A deterministic count, not an interpretation.',extractive_first_lines_not_model_summary:'Exact first lines, not a model summary.'};
/** A plain reading of a result artefact. Unknown or malformed results are shown as unknown, never guessed. */
export function readResult(text:string|undefined):ReadableResult|null{
  if(!text)return null;let value:unknown;try{value=JSON.parse(text);}catch{return null;}
  if(!value||typeof value!=='object')return null;
  const r=value as {kind?:unknown;basis?:unknown;total?:Record<string,unknown>;inputs?:unknown};
  const basis=typeof r.basis==='string'?BASIS[r.basis]??r.basis:'Basis not stated.';
  const inputs=Array.isArray(r.inputs)?r.inputs as Record<string,unknown>[]:[];
  if(r.kind==='word_count'&&r.total){
    const n=(v:unknown)=>typeof v==='number'?v.toLocaleString('en-GB'):'unknown';
    return {basis,lines:[{label:'Words',value:n(r.total.words)},{label:'Lines',value:n(r.total.lines)},{label:'Bytes',value:n(r.total.bytes)}],selected:[]};
  }
  if(r.kind==='summarise_lines'){
    const selected=inputs.flatMap(i=>Array.isArray(i.selected)?i.selected.filter((s):s is string=>typeof s==='string'):[]);
    const total=inputs.reduce((sum,i)=>sum+(typeof i.lines==='number'?i.lines:0),0);
    return {basis,lines:[{label:'Lines in the note',value:total.toLocaleString('en-GB')},{label:'Lines extracted',value:String(selected.length)}],selected};
  }
  return {basis,lines:[{label:'Result',value:'A result of an unrecognised kind'}],selected:[]};
}
const ERRORS:Record<string,string>={input_revision_changed:'The note changed since you opened it. Reopen it and try again.',inputs_denied:'This note is not available to you for jobs.',job_capacity:'The job list is full.',jobs_not_configured:'This ALFRED host runs no job worker.',idempotency_key_collision:'That request conflicted with an earlier one. Try again.',not_found:'That job is not available.',artefact_not_available:'The result is no longer available: a source was deleted or your access changed.',cancellation_is_not_undo:'This job has already finished. Cancelling cannot undo it.'};
export const jobError=(code:string)=>ERRORS[code]??`ALFRED refused this (${code}).`;
export function requestKey(){const c=globalThis.crypto;return 'console-'+(c?.randomUUID?c.randomUUID():Math.random().toString(36).slice(2)+Date.now().toString(36)).replace(/[^A-Za-z0-9_.-]/g,'').slice(0,60);}
