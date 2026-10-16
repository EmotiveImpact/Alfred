/** Owner-authored capture policies (MEM-004, M04): read-only view types and plain labels.
 * Policies are authored over the guarded HTTP API; the console lists them with their counts.
 * Every proposal they make is an ordinary reviewed-memory proposal; nothing here accepts anything. */
import {DeskError} from './deskClient';

export type CaptureMatch={kind:'line_prefix';prefix:string}|{kind:'dated_line';keyword:string|null};
export interface CaptureCounts{proposed:number;open:number;accepted:number;dismissed:number;invalidated:number;forgotten:number;proposed_today:number;deferred_today:number}
export interface CapturePolicyView{id:string;version:number;enabled:boolean;name:string;context:'personal'|'company'|'client';match:CaptureMatch;
  sources:string[];path_prefix:string|null;daily_budget:number;proposes:{subject_id:string;predicate:string;memory_type:string;retention_days:number|null};
  subject_available:boolean;description:string;created:number;updated:number;counts:CaptureCounts}
export interface CaptureView{scope:string;policies:CapturePolicyView[];settings:{version:number;daily_budget:number};
  today:{day_start:number;proposed:number;deferred:{rule_budget:number;daily_budget:number}};last_run:{at:number;proposed:number}|null;
  model_used:false;auto_accept:false}

const CONTEXT:Record<string,string>={personal:'Personal',company:'Company',client:'Client'};
export function contextLabel(context:string){return CONTEXT[context]??context;}
export function ruleLabel(match:CaptureMatch){
  return match.kind==='line_prefix'?`Lines starting “${match.prefix}”`:`Open dated lines${match.keyword?` with “${match.keyword}”`:''}`;
}
export function countLine(c:CaptureCounts){return `${c.proposed} proposed · ${c.accepted} accepted · ${c.dismissed} dismissed · ${c.open} awaiting review`;}
export function todayLine(p:CapturePolicyView){
  const d=p.counts.deferred_today;
  return `Today ${p.counts.proposed_today} of ${p.daily_budget}${d?` · ${d} over budget, counted not proposed`:''}`;
}
const MESSAGES:Record<string,string>={forbidden:'Capture policies are set by the workspace owner. This key cannot read them.',
  capture_not_configured:'Capture policies need the connected ALFRED host.'};
/** A plain message for a refusal, from a DeskError or a bare code. */
export function captureMessage(e:unknown,code?:string){
  const key=code??(e instanceof DeskError?e.code:null);
  if(key===null)return 'ALFRED could not be reached.';
  return MESSAGES[key]??`ALFRED refused this (${key}).`;
}
