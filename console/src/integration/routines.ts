/**
 * Shapes and wording for authored routines (alfred/routines.py, M10).
 * The server decides every run, budget, hold and authority check; this file only formats
 * what it returns and builds the exact settings body the person chose. Nothing here runs.
 */
import {DeskError} from './deskClient';
export type RoutineKind='commitment-review'|'morning-brief';
export type Schedule={every_hours:number}|{daily_at:string};
export interface RoutineSettings{schedule:Schedule;utc_offset_minutes:number;runs_per_day:number;nominations_per_run:number;
  quiet_hours:{start:string;end:string}|null;interrupt:'show_now'|'hold_for_brief';propose_drafts:boolean}
export interface RoutineView{kind:RoutineKind;name:string;description:string;rules:{id:string;rule:string}[];
  default:{schedule:Schedule;interrupt:'show_now'|'hold_for_brief'};configured:boolean;enabled:boolean;paused:boolean;version:number;
  settings:RoutineSettings|null;next_due:number|null;runs_today:number;quiet_now:boolean;authority_available:boolean}
/** What a citation points at, as the server says this person may read it now. */
export interface Resolved{state:'current'|'changed'|'unavailable';title?:string;record_kind?:string;status?:string;current_version?:number;
  due?:number|null;responsible?:string|null;subject?:{id:string;kind:string;name:string};predicate?:string;value?:string|null;
  source?:{note_id:string;path:string;title:string;revision:number;start_line:number;end_line:number};action_state?:string}
export interface Cite{kind:'record'|'statement'|'action';id:string;version:number;rule?:string;note?:string;revision?:number;lines?:number[];fingerprint?:string;resolved?:Resolved}
export interface RunOutcome{trigger:'manual'|'scheduled';missed_slots:number;budget:{runs_today:number;runs_per_day:number;nominations_per_run:number};
  skipped?:string;error?:string;read?:Record<string,number>;cited?:Cite[];cited_total?:number;due?:number;
  nominated?:{nomination:string;kind:'reminder'|'draft';rule:string;delivery:string;cite:Cite}[];not_nominated?:Record<string,number>;
  held?:{quiet_hours:number;next_brief:number};nothing_due?:boolean;surface_at?:number|null;
  sections?:{attention:Cite[];insights:{rule:string;records:Cite[]}[];approvals:Cite[]};released?:string[];still_held?:number;basis?:string}
export interface RunView{id:string;kind:RoutineKind;trigger:'manual'|'scheduled';started:number;finished:number;status:'completed'|'skipped'|'failed';
  skipped_reason:string|null;outcome:RunOutcome}
export type NominationCite={kind:'record'|'statement';id:string;version:number}&Resolved;
export interface NominationView{id:string;version:number;routine:RoutineKind;kind:'reminder'|'draft';rule:string;reason:string;due:number|null;
  delivery:'now'|'quiet_hours'|'next_brief';surface_at:number|null;released_by_brief:string|null;surfaced:boolean;held:'quiet_hours'|'next_brief'|null;
  state:'open'|'accepted'|'dismissed';created:number;decided:number|null;outcome:{follow_up?:string|null;action?:string}|null;cite:NominationCite}
export interface RoutinesView{available:boolean;reason:'owner_only'|'not_hosted'|null;scope:string;now:number;routines:RoutineView[];runs:RunView[];
  nominations:NominationView[];workspace_paused?:boolean;delivery:'in_app_only';limits:{runs_per_day:number;nominations_per_run:number;every_hours:number[]}}
export interface RoutineSummary{available:boolean;reason:string|null;nominations:NominationView[];held:number;
  latest_brief:{id:string;finished:number;read:Record<string,number>;released:number}|null}
export interface ProcedureView{id:string;version:number;review_state:string;usable:boolean;subject:{id:string;kind:string;name:string}|null;predicate:string;
  value:string|null;support_state:'current'|'changed'|'unavailable';reviewed:number|null;
  source:{note_id:string;path:string;title:string;revision:number;start_line:number;end_line:number;quote:string}|null;executable:false;basis:string}
export interface ProceduresView{procedures:ProcedureView[];authored_procedure_notes:{id:string;title:string;path:string;revision:number;basis:string}[];
  counts:{reviewed:number;usable:number;authored_notes:number};read_only:true;executable:false;statement:string}

/** The form the person edits. Converted to the exact server body only on save. */
export interface RoutineForm{enabled:boolean;every:number|'daily';dailyAt:string;offset:number;runsPerDay:number;nominationsPerRun:number;
  quiet:boolean;quietStart:string;quietEnd:string;interrupt:'show_now'|'hold_for_brief';proposeDrafts:boolean}

export const EVERY_HOURS=[1,2,4,8,12,24] as const;
export const OFFSETS=Array.from({length:(840+720)/15+1},(_,i)=>i*15-720);
const CLOCK=/^([01][0-9]|2[0-3]):([0-5][0-9])$/;
const pad=(n:number)=>String(n).padStart(2,'0');

export function offsetLabel(minutes:number){const sign=minutes<0?'-':'+',m=Math.abs(minutes);return `UTC${sign}${pad(Math.floor(m/60))}:${pad(m%60)}`;}
/** This browser's offset, rounded to the server's 15-minute steps. A suggestion the person can change. */
export function browserOffset(date=new Date()){const v=Math.round(-date.getTimezoneOffset()/15)*15;return Math.min(840,Math.max(-720,v));}
const shifted=(seconds:number,offset:number)=>new Date((seconds+offset*60)*1000);
export function localClock(seconds:number,offset:number){const d=shifted(seconds,offset);return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;}
export function localMoment(seconds:number|null|undefined,offset:number){
  if(seconds==null)return 'No time';
  return new Intl.DateTimeFormat('en-GB',{timeZone:'UTC',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',hour12:false}).format(shifted(seconds,offset));
}
export function scheduleLabel(schedule:Schedule){
  if('daily_at' in schedule)return `Daily at ${schedule.daily_at}`;
  return schedule.every_hours===1?'Every hour':schedule.every_hours===24?'Every 24 hours, from local midnight':`Every ${schedule.every_hours} hours`;
}

export function formFromRoutine(r:RoutineView,offset=browserOffset()):RoutineForm{
  const s=r.settings,schedule=s?.schedule??r.default.schedule;
  return {enabled:s?r.enabled:true,every:'daily_at' in schedule?'daily':schedule.every_hours,dailyAt:'daily_at' in schedule?schedule.daily_at:'07:30',
    offset:s?.utc_offset_minutes??offset,runsPerDay:s?.runs_per_day??(r.kind==='morning-brief'?1:6),nominationsPerRun:s?.nominations_per_run??3,
    quiet:Boolean(s?.quiet_hours),quietStart:s?.quiet_hours?.start??'22:00',quietEnd:s?.quiet_hours?.end??'07:00',
    interrupt:s?.interrupt??r.default.interrupt,proposeDrafts:s?.propose_drafts??false};
}
/** Plain reasons a form cannot be saved yet. The server validates again regardless. */
export function formProblem(kind:RoutineKind,f:RoutineForm):string|null{
  if(f.every==='daily'&&!CLOCK.test(f.dailyAt))return 'Choose a time of day, such as 07:30.';
  if(!Number.isInteger(f.runsPerDay)||f.runsPerDay<1||f.runsPerDay>24)return 'Runs per day must be between 1 and 24.';
  if(!Number.isInteger(f.nominationsPerRun)||f.nominationsPerRun<1||f.nominationsPerRun>10)return 'Nominations per run must be between 1 and 10.';
  if(f.quiet&&(!CLOCK.test(f.quietStart)||!CLOCK.test(f.quietEnd)))return 'Quiet hours need a start and an end time.';
  if(f.quiet&&f.quietStart===f.quietEnd)return 'Quiet hours need different start and end times.';
  if(kind==='morning-brief'&&(f.interrupt!=='show_now'||f.proposeDrafts))return 'The morning brief shows what it surfaces and offers no drafts.';
  return null;
}
export function settingsPayload(kind:RoutineKind,f:RoutineForm,version:number){
  return {version,enabled:f.enabled,schedule:f.every==='daily'?{daily_at:f.dailyAt}:{every_hours:f.every},utc_offset_minutes:f.offset,
    runs_per_day:f.runsPerDay,nominations_per_run:f.nominationsPerRun,quiet_hours:f.quiet?{start:f.quietStart,end:f.quietEnd}:null,
    interrupt:kind==='morning-brief'?'show_now':f.interrupt,propose_drafts:kind==='morning-brief'?false:f.proposeDrafts};
}

export const SKIP_LABEL:Record<string,string>={authority_lost:'Authority lost: the access key this host runs under is no longer valid for this routine.',
  workspace_paused:'The workspace was paused.',paused:'This routine was paused.',budget_exhausted:'Today\'s run budget was already used.'};
export const RULE_LABEL:Record<string,string>={overdue:'Overdue',due_within_a_day:'Due within a day',draft_offer:'Draft offer',
  decision_past_due:'Decision past due',due_soon:'Due soon',stale_milestone:'No recent progress',
  responsible_overdue_across_projects:'Overdue across projects',top_priorities_deadline_clash:'Priority deadlines clash',
  commitments_without_milestone:'Commitments without milestone progress'};
const READ_LABEL:Record<string,[string,string]>={executive_records:['open commitment or follow-up','open commitments and follow-ups'],
  commitment_statements:['commitment statement','commitment statements'],undated_statements:['undated statement','undated statements'],
  statements_not_usable:['statement not usable now','statements not usable now'],attention_items:['attention item','attention items'],
  snoozed_items:['snoozed item','snoozed items'],insights:['insight','insights'],pending_approvals:['pending approval','pending approvals'],
  held_nominations:['held nomination','held nominations']};
const SKIPPED_ITEM:Record<string,string>={already_nominated:'already nominated',nomination_budget:'over the nomination budget',
  nomination_capacity:'over the open nomination limit',snoozed:'snoozed by you'};
const plural=(n:number,word:string)=>`${n} ${word}${n===1?'':'s'}`;
export function readLine(read:Record<string,number>|undefined){
  if(!read)return '';
  return Object.entries(read).filter(([,v])=>v>0).map(([k,v])=>`${v} ${READ_LABEL[k]?.[v===1?0:1]??k.replaceAll('_',' ')}`).join(' · ')||'Nothing to read';
}
export function notNominatedLine(counts:Record<string,number>|undefined){
  return Object.entries(counts??{}).filter(([,v])=>v>0).map(([k,v])=>`${v} ${SKIPPED_ITEM[k]??k.replaceAll('_',' ')}`).join(' · ');
}
/** One line per run: what happened, or why it was skipped. */
export function runSummary(run:RunView){
  const o=run.outcome;
  if(run.status==='skipped')return `Skipped · ${SKIP_LABEL[run.skipped_reason??'']??run.skipped_reason}`;
  if(run.status==='failed')return `Failed (${o.error??'unknown'}) · nothing from this run was kept`;
  if(run.kind==='morning-brief'){
    const r=o.read??{},parts=[plural(r.attention_items??0,'attention item'),plural(r.insights??0,'insight'),plural(r.pending_approvals??0,'pending approval')];
    if(o.released?.length)parts.push(`${o.released.length} held released`);
    return `Brief assembled · ${parts.join(' · ')}`;
  }
  if(o.nothing_due)return 'Completed · nothing due';
  const n=o.nominated?.length??0,held=(o.held?.quiet_hours??0)+(o.held?.next_brief??0);
  return `Completed · ${plural(n,'nomination')}${held?` · ${held} held`:''}${notNominatedLine(o.not_nominated)?` · ${notNominatedLine(o.not_nominated)}`:''}`;
}
/** Kind, rule and due time in one line. A draft offer's rule is its kind, so it is not repeated. */
export function nominationLine(n:NominationView,offset:number){
  const parts=[n.kind==='draft'?'Draft offer':'Reminder'];
  if(n.rule!=='draft_offer')parts.push(RULE_LABEL[n.rule]??n.rule);
  if(n.due!=null)parts.push(localMoment(n.due,offset));
  return parts.join(' · ');
}
export function holdLabel(n:NominationView,offset:number){
  if(n.held==='next_brief')return 'Held for the next morning brief';
  if(n.held==='quiet_hours')return `Held for quiet hours until ${n.surface_at!=null?localMoment(n.surface_at,offset):'they end'}`;
  return null;
}
/** A citation as text. Unavailable items never show a title or value. */
export function citeLabel(c:Resolved&{kind:string;version:number}){
  if(c.state==='unavailable')return 'No longer available to you';
  let label:string;
  if(c.kind==='record')label=`${c.title} · version ${c.version}`;
  else if(c.kind==='statement')label=`${c.subject?.name}: ${(c.predicate??'').replaceAll('_',' ')} ${c.value??''} · version ${c.version}`;
  else label=`Proposal · ${c.action_state??'unknown'}`;
  return c.state==='changed'?`${label} · changed since (now version ${c.current_version})`:label;
}
export function sourceLabel(c:Resolved){
  if(!c.source)return null;
  const s=c.source,lines=s.start_line===s.end_line?`line ${s.start_line}`:`lines ${s.start_line} to ${s.end_line}`;
  return `${s.path}, ${lines}, revision ${s.revision}`;
}
export function decisionLabel(n:NominationView){
  if(n.state==='dismissed')return 'Dismissed';
  if(n.state!=='accepted')return 'Open';
  if(n.outcome?.action)return 'Accepted · draft proposed for your approval';
  if(n.outcome?.follow_up)return 'Accepted · follow-up added';
  return 'Accepted';
}
const ERRORS:Record<string,string>={routine_changed:'These settings changed elsewhere. The view was refreshed; check and save again.',
  routine_owner_not_hosted:'Routines run under the key this ALFRED host was started with. This key cannot change them.',
  forbidden:'Only the workspace owner can do this.',routine_not_configured:'Save this routine\'s settings first.',
  routine_rate_limited:'Too many runs in a short time. Wait a minute.',nomination_changed:'This nomination changed. The view was refreshed.',
  nomination_closed:'This nomination was already decided.',nomination_source_changed:'The cited commitment changed or is no longer available. It can only be dismissed.',
  nomination_not_found:'This nomination is no longer available to you.',follow_up_only_for_reminders:'Only reminders can add a follow-up.',
  invalid_quiet_hours:'Quiet hours need different start and end times.',invalid_routine_schedule:'Choose a schedule from the list.',
  invalid_run_budget:'Runs per day must be between 1 and 24.',invalid_nomination_budget:'Nominations per run must be between 1 and 10.',
  interrupt_not_applicable:'The morning brief shows what it surfaces.',drafts_not_applicable:'The morning brief offers no drafts.',
  executive_capacity:'Your executive records are full.',action_capacity:'The approval ledger is full.'};
export function routineMessage(e:unknown){return e instanceof DeskError?ERRORS[e.code]??`ALFRED refused this (${e.code}).`:'ALFRED could not be reached.';}
