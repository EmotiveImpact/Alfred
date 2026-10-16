/**
 * Shapes and wording for goals the agent hub works on (alfred/hub_goals.py, AGENT_HUB.md H2).
 * The server decides every mandate check, budget, pause and stop; this file only formats what
 * it returns and names the exact control route and version the person acted on. Nothing here
 * admits, schedules or runs work, and nothing it shows is a grant of authority.
 */
import {DeskError} from './deskClient';
export type HubState='active'|'paused'|'stopped';
export type Dimension='tokens'|'money_pence'|'wall_seconds'|'tasks';
export type Limits=Record<Dimension,number|null>;
export interface HubBudget{daily:Limits;total:Limits;warn_percent:number;utc_offset_minutes:number}
export interface DimensionUse{used:number;in_flight:number;limit:number|null;spent:boolean;warning:boolean}
export interface PeriodUse{since:number;dimensions:Record<Dimension,DimensionUse>}
export type Usage={daily:PeriodUse;total:PeriodUse}|null;
export interface HubTask{job:string;work:string;brain:string;autonomy:number;trigger:'operator'|'heartbeat';created:number;job_state:string|null;
  job_reason:string|null;result:string|null;accounted:number|null;usage:{tokens:number;money_pence:number;wall_seconds:number;basis:string}|null}
export interface Heartbeat{slot:string;at:number;status:'submitted'|'skipped'|'refused';reason:string|null;missed:number;job:string|null}
/** An acceptance check as ALFRED declared it (AGENT_HUB.md H4). Parameters vary by kind. */
export interface AcceptanceCheck{id:string;kind:string;artefact?:string;sections?:string[];fields?:string[];targets?:string[];[k:string]:unknown}
export interface MandateView{id:string;version:number;state:HubState;state_reason:string|null;
  goal:{id:string;title:string|null;status:string|null;available:boolean};scope_class:string;deadline:number;expired:boolean;success_test:string;
  autonomy:Record<string,{level:number;name:string}>;brains:string[];assigned_brain:string;tools:string[];budget:HubBudget;usage:Usage;
  schedule:{when:{every_hours:number}|{daily_at:string};utc_offset_minutes:number}|null;next_due:number|null;missed_total:number;
  tasks:HubTask[];heartbeats:Heartbeat[];acceptance?:AcceptanceCheck[]}
export interface BrainView{id:string;registered:boolean;label:string|null;locality:string|null;state:HubState;reason:string|null;control_version:number;
  budget:HubBudget|null;usage:Usage}
export interface AttentionItem{id:string;target:string;period:'daily'|'total';since:number;dimension:Dimension;level:'warning'|'hard_stop';
  used:number;limit:number;at:number;state:'open'|'acknowledged'}
export interface HubView{available:boolean;reason:'owner_only'|'not_hosted'|null;now:number;workspace_paused?:boolean;goals:MandateView[];
  unlinked_goals:{id:string;title:string;version:number}[];brains:BrainView[];
  overall:{state:HubState;reason:string|null;version:number;budget:HubBudget|null;usage:Usage}|null;attention:AttentionItem[]}

const UNIT:Record<Dimension,string>={tokens:'tokens',money_pence:'',wall_seconds:'',tasks:'tasks'};
const NAME:Record<Dimension,string>={tokens:'tokens',money_pence:'money',wall_seconds:'wall time',tasks:'tasks'};
const PERIOD={daily:'today',total:'in total'} as const;

/** One amount in its own unit: pence as pounds, seconds as minutes once there are enough. */
export function amount(dimension:Dimension,value:number){
  if(dimension==='money_pence')return `£${(value/100).toFixed(2)}`;
  if(dimension==='wall_seconds')return value>=120?`${Math.round(value/60)} min`:`${value} s`;
  return `${value.toLocaleString('en-GB')} ${UNIT[dimension]}`;
}

/** Each limited dimension in one period, for example "12 of 30 tokens today (30 in flight)". */
export function usageLines(usage:Usage,period:'daily'|'total'):string[]{
  if(!usage)return [];
  const dims=usage[period].dimensions;
  return (Object.keys(dims) as Dimension[]).filter(d=>dims[d].limit!==null).map(d=>{
    const u=dims[d],flight=u.in_flight>0?` (${amount(d,u.in_flight)} in flight)`:'';
    const mark=u.spent?' · limit reached':u.warning?' · warning':'';
    return `${amount(d,u.used)} of ${amount(d,u.limit as number)} ${PERIOD[period]}${flight}${mark}`;
  });
}

/** Why something is paused or stopped, in plain words. */
export function stateLabel(state:HubState,reason:string|null){
  if(state==='active')return 'Running';
  if(state==='stopped')return 'Stopped';
  if(!reason||reason==='operator')return 'Paused by you';
  const m=/^budget_(daily|total)_(tokens|money_pence|wall_seconds|tasks)$/.exec(reason);
  if(m)return `Paused: ${m[1]==='daily'?'daily':'total'} ${NAME[m[2] as Dimension]} budget reached`;
  return `Paused (${reason})`;
}

export function autonomyLine(autonomy:MandateView['autonomy']){
  return Object.entries(autonomy).map(([work,a])=>`${work}: ${a.name.replaceAll('_',' ')} (${a.level})`).join(' · ');
}

/** ``goal`` is the goal's title when the caller can still read it. */
export function attentionLine(a:AttentionItem,goal?:string|null){
  const target=a.target==='overall'?'All brains':a.target.startsWith('brain:')?`Brain ${a.target.slice(6)}`:goal?`Goal ${goal}`:'Goal';
  const what=a.level==='hard_stop'?'limit reached, paused':'warning';
  return `${target} · ${NAME[a.dimension]} ${PERIOD[a.period]} · ${amount(a.dimension,a.used)} of ${amount(a.dimension,a.limit)} · ${what}`;
}

export function taskLine(t:HubTask){
  const state=t.job_state?t.job_state.replaceAll('_',' '):'unknown';
  const used=t.usage?` · ${amount('tokens',t.usage.tokens)}${t.usage.basis==='metered'?'':` (${t.usage.basis.replaceAll('_',' ')})`}`:'';
  return `${t.trigger==='heartbeat'?'Heartbeat':'Operator'} · ${t.work} · ${t.brain} · ${state}${used}`;
}

export type Level='goal'|'brain'|'overall';
export type Operation='pause'|'resume'|'stop';
/** The exact route and the version the person saw. A changed version is refused by the server. */
export function controlRequest(level:Level,target:string|null,operation:Operation,version:number){
  const path=level==='goal'?`/desk/hub/mandates/${encodeURIComponent(target??'')}/${operation}`
    :level==='brain'?`/desk/hub/brains/${encodeURIComponent(target??'')}/${operation}`:`/desk/hub/overall/${operation}`;
  return {path,body:{version}};
}

/* Results and checks (AGENT_HUB.md H4). ALFRED runs the checks and decides each class; this
   file only words them. A brain's own confidence or "done" is never one of the inputs. */
export type EvidenceClass='verified'|'failed_checks'|'unverifiable'|'no_checks'|'not_returned';
export interface CheckStatus{id:string;kind:string;status:'passed'|'failed'|'unverifiable'}
export interface ResultRun{position:number;outcome:'returned'|'checked'|'failed_checks';sha256:string;
  counts:{passed:number;failed:number;unverifiable:number};checks:CheckStatus[]}
export interface HubResult{job:string;brain:string;task_id:string;scope_class:string;contract:'accepted'|'refused'|'stopped';contract_reason:string|null;
  declared:number;checks:string;state:string;evidence:EvidenceClass;runs:number;acknowledged_over:string|null;ingested_at:number;updated_at:number|null;
  work:{mandate:string;goal:string;goal_title:string|null;work:string;trigger:string}|null;last_run:ResultRun|null}
export type EvidenceCounts=Record<EvidenceClass,number>&{results:number};
export interface ResultsView{available:boolean;reason:'owner_only'|null;results:HubResult[];by_brain:Record<string,EvidenceCounts>;window_days:number}

const CLASS_ORDER:EvidenceClass[]=['verified','failed_checks','unverifiable','no_checks','not_returned'];
const CLASS_WORDS:Record<EvidenceClass,string>={verified:'verified',failed_checks:'failed checks',unverifiable:'not verified',
  no_checks:'no checks declared',not_returned:'not returned'};

/** The chip for one result. Acknowledged and checked are told apart; neither comes from the brain. */
export function evidenceLabel(r:HubResult){
  if(r.evidence==='verified')return r.state!=='acknowledged'?'Verified by checks':r.acknowledged_over==='failed_checks'?'Acknowledged over failed checks':'Acknowledged by you';
  if(r.evidence==='failed_checks')return r.contract==='refused'?'Failed checks (refused)':'Failed checks';
  if(r.evidence==='unverifiable')return r.runs===0?'Not verified: checks not run':'Not verified: checks could not run';
  if(r.evidence==='no_checks')return 'No checks declared';
  return 'Not returned';
}
/** Chip tone: amber for verified, warning for failed checks, plain otherwise. */
export function evidenceTone(e:EvidenceClass){return e==='verified'?'on':e==='failed_checks'?'warn':'';}

/** Per brain, for example "synthetic: 2 verified · 1 failed checks · 0 not verified · 3 no checks declared". */
export function brainEvidenceLine(brain:string,c:EvidenceCounts){
  return `${brain}: ${CLASS_ORDER.filter(k=>k!=='not_returned'||c[k]>0).map(k=>`${c[k]} ${CLASS_WORDS[k]}`).join(' · ')}`;
}

const CHECK_WORDS:Record<string,(c:AcceptanceCheck)=>string>={
  claims_cited:()=>'every claim cites a sent excerpt',
  numbers_cited:()=>'every number appears in the cited text',
  artefact_sections:c=>`${c.artefact} has ${(c.sections??[]).map(s=>`“${s}”`).join(', ')}`,
  artefact_fields:c=>`${c.artefact} has ${(c.fields??[]).join(', ')}`,
  artefact_schema:c=>`${c.artefact} matches the declared schema`,
  artefact_pattern:c=>`${c.artefact} matches the declared pattern`,
  no_out_of_scope_content:()=>'nothing from notes outside the task',
  effect_readback:()=>'every proposed effect reads back as proposed',
};
export function checkLabel(c:AcceptanceCheck){return `${c.id} ${(CHECK_WORDS[c.kind]??(()=>c.kind.replaceAll('_',' ')))(c)}`;}

/** What the last run found, without reasons (they may quote what the brain returned). */
export function runLine(r:HubResult){
  if(r.contract==='stopped')return 'The job stopped without a result, so nothing was checked.';
  if(r.declared===0)return 'No acceptance checks were declared for this task, so it is never counted as verified.';
  if(!r.last_run)return `${r.declared} ${r.declared===1?'check':'checks'} declared, not run yet.`;
  const n=r.last_run.counts;
  return `Run ${r.last_run.position}: ${n.passed} passed · ${n.failed} failed · ${n.unverifiable} could not run`;
}

export function canRunChecks(r:HubResult){return r.contract==='accepted'&&r.declared>0;}
export function canAcknowledge(r:HubResult){return r.contract==='accepted'&&r.last_run!==null&&r.state!=='acknowledged';}

/** The run the person saw, and whether they accept it over failed checks. Nothing else is sent. */
export function verifyRequest(job:string,runs:number){return {path:`/desk/hub/results/${encodeURIComponent(job)}/verify`,body:{runs}};}
export function acknowledgeRequest(job:string,run:ResultRun,acceptFailures:boolean){
  return {path:`/desk/hub/results/${encodeURIComponent(job)}/acknowledge`,body:{run_sha256:run.sha256,accept_failures:acceptFailures}};
}
/** What acknowledging means for this result, said before the person confirms. */
export function acknowledgeNote(r:HubResult){
  const run=r.last_run?`run ${r.last_run.position}`:'this run';
  if(r.declared===0)return `You accept ${run} as it stands. No checks were declared, so this result stays unverified for routing even after you acknowledge it.`;
  if(r.checks==='failed_checks'){
    const failed=(r.last_run?.checks??[]).filter(c=>c.status==='failed').map(c=>c.id);
    return `${run[0].toUpperCase()+run.slice(1)} failed ${failed.length?failed.join(', '):'a check'}. Accepting it over failed checks is recorded as your decision, bound to ${run}. It grants no authority: proposed effects still need their own approval.`;
  }
  return `You accept ${run} as it stands. It grants no authority: proposed effects still need their own approval. A later run that fails a check you did not accept ends this acknowledgement.`;
}

const ERRORS:Record<string,string>={
  hub_not_configured:'This ALFRED host has no brains plugged in, so there are no goals for brains to work on.',
  verification_changed:'Checks ran again since you opened this. The view has been refreshed; check it and try again.',
  acknowledgement_mismatch:'This result was checked again since you opened it. The view has been refreshed; acknowledge the run you now see.',
  failed_checks_need_explicit_acceptance:'This run failed checks. Accept it explicitly over the failed checks, or leave it.',
  not_verified_yet:'Run the checks before acknowledging this result.',
  nothing_to_acknowledge:'A refused or stopped result has nothing to acknowledge.',
  not_found:'This result is not yours, or no longer exists.',
  hub_owner_not_hosted:'Goals are run under the access key this ALFRED host was started with. Sign in with that key to change them.',
  forbidden:'Only the workspace owner can change goals.',
  budget_still_spent:'The budget that paused this is still spent. Raise the limit or wait for a new day before resuming.',
  mandate_changed:'This goal changed since you opened it. The view has been refreshed; check it and try again.',
  control_changed:'This changed since you opened it. The view has been refreshed; check it and try again.',
  goal_stopped:'This goal was stopped. A stop is final; a new mandate is needed to work on the goal again.',
  brain_stopped:'This brain was stopped. A stop is final for this brain.',
  goal_not_paused:'This goal is not paused.',goal_not_running:'This goal is not running.',already_paused:'Already paused.',not_paused:'Not paused.',
};
export function goalMessage(e:unknown){return e instanceof DeskError?ERRORS[e.code]??`ALFRED refused this (${e.code}).`:'ALFRED could not be reached.';}
