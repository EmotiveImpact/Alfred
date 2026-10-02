/**
 * Reviewed-memory review queue, statement history and the as-of report for the connected
 * console (MEM-007). Shapes mirror GET /desk/memory, GET /desk/memory/claims/{id}/history and
 * GET /desk/memory/as-of/{t}[/valid/{v}] (alfred/reviewed_memory.py, alfred/memory_history.py).
 * Display logic only: the server validates every decision, checks versions and rechecks access
 * and source support on every read. Nothing here grants authority or merges records.
 */
export type ReviewState='proposed'|'accepted'|'disputed'|'withdrawn'|'superseded'|'invalidated'|'forgotten';
export type HiddenReason='forgotten'|'support_changed'|'withheld';
export interface EntityRef{id:string;kind:string;name:string}
export interface MemoryEntity extends EntityRef{created:number}
export interface ClaimSource{note_id:string;path:string;title:string;start_line:number;end_line:number;quote:string}
export interface MemoryClaim{
  id:string;subject_id:string;predicate:string;object_id:string|null;value:string|null;valid_from:number|null;valid_until:number|null;
  state:ReviewState;version:number;created:number;reviewed:number|null;replaces_id:string|null;source:ClaimSource|null;
  valid_now:boolean;conflicts:string[];usable:boolean;withheld:boolean;memory_type:string|null;retention_until:number|null;
}
export interface MemoryView{entities:MemoryEntity[];claims:MemoryClaim[];counts:{proposed:number;usable:number;conflicted:number}}
export interface HistoryEntry{
  seq:number;state:ReviewState|'withheld'|'restored';at:number;time_known:boolean;by:'you'|'alfred'|'another_credential';
  origin:'recorded'|'observed'|'migrated'|'replayed';related_id:string|null;detail:string|null;valid_period:{from:number|null;until:number|null}|null;
}
export interface StatementSummary{
  claim_id:string;version:number;state:ReviewState;subject:EntityRef|null;predicate:string;value:string|null;object:EntityRef|null;
  value_hidden:HiddenReason|null;valid_from:number|null;valid_until:number|null;recorded:number;reviewed:number|null;replaces_id:string|null;
}
export interface StatementHistory{
  claim:StatementSummary&{usable:boolean;conflicts:string[];withheld:boolean};entries:HistoryEntry[];recorded_from_start:boolean;times_unknown:number;
  lineage:{replaces:StatementSummary[];replaced_by:StatementSummary[]};basis:string;values_in_history:false;
}
export interface AsOfItem extends StatementSummary{
  state_now:ReviewState;replaced_by:string|null;since:number|null;since_known:boolean;availability_then:'withheld_noticed'|null;
  conflicts_then?:string[];possible_conflicts_then?:string[];state_then?:ReviewState|null;
}
export interface AsOfReport{
  kind:'historical_report';basis:string;label:string;at:number;valid_at:number;requested_at:number;clamped_to_now:boolean;generated_at:number;
  held:AsOfItem[];accepted_outside_valid_period:AsOfItem[];uncertain:AsOfItem[];not_held:Record<string,number>;
  not_yet_recorded:number;without_history:number;current_answers:string;model_used:false;authority_granted:false;
}
export type Decision='accept'|'dispute'|'withdraw'|'supersede';

export const PREDICATE_LABEL:Record<string,string>={status:'status',scheduled_for:'scheduled for',decision:'decision',responsible_person:'responsible person',depends_on:'depends on'};
export function predicateLabel(predicate:string){return PREDICATE_LABEL[predicate]??predicate.replaceAll('_',' ');}
const STATE_LABEL:Record<string,string>={proposed:'Proposed',accepted:'Accepted',disputed:'Disputed',withdrawn:'Withdrawn',superseded:'Superseded',
  invalidated:'Invalidated',forgotten:'Forgotten',withheld:'Support unavailable or not permitted',restored:'Support readable again'};
export function stateLabel(state:string){return STATE_LABEL[state]??state;}
export const HIDDEN_LABEL:Record<HiddenReason,string>={forgotten:'Value removed: you forgot this statement',support_changed:'Value removed: its support changed',
  withheld:'Value withheld: its support is unavailable or not permitted now'};

/** Same-name records are told apart by kind and identifier, never merged. */
export function namesakeIds(entities:readonly EntityRef[]){
  const groups=new Map<string,string[]>();
  for(const e of entities){const key=`${e.kind}\u0000${e.name.toLocaleLowerCase('en-GB')}`;groups.set(key,[...(groups.get(key)??[]),e.id]);}
  return new Set([...groups.values()].filter(ids=>ids.length>1).flat());
}
export function entityLabel(entity:EntityRef|null|undefined,shared:ReadonlySet<string>){
  if(!entity)return 'A record you forgot';
  return shared.has(entity.id)?`${entity.name} (${entity.kind}, record ${entity.id})`:`${entity.name} (${entity.kind})`;
}
/** The statement's value as the person may see it now. A hidden value is named as hidden, never guessed. */
export function valueText(item:{value:string|null;object?:EntityRef|null;value_hidden?:HiddenReason|null},shared:ReadonlySet<string>=new Set()){
  if(item.value_hidden)return HIDDEN_LABEL[item.value_hidden];
  if(item.value!==null)return item.value;
  if(item.object)return entityLabel(item.object,shared);
  return 'No value';
}
export function claimHidden(c:Pick<MemoryClaim,'state'|'withheld'>):HiddenReason|null{
  if(c.state==='forgotten')return 'forgotten';
  if(c.state==='invalidated')return 'support_changed';
  return c.withheld?'withheld':null;
}
export function claimValue(c:MemoryClaim,entities:Record<string,EntityRef>,shared:ReadonlySet<string>){
  return valueText({value:c.value,object:c.object_id?entities[c.object_id]??null:null,value_hidden:claimHidden(c)},shared);
}

/** Oldest first, so nothing waits behind newer captures. */
export function reviewQueue(claims:readonly MemoryClaim[]){
  const order=(a:MemoryClaim,b:MemoryClaim)=>a.created-b.created||a.id.localeCompare(b.id);
  return {proposed:claims.filter(c=>c.state==='proposed').sort(order),disputed:claims.filter(c=>c.state==='disputed').sort(order)};
}
/** What a decision may replace: the same record (by identifier, never by name) and the same kind of statement. */
export function supersedeCandidates(claim:MemoryClaim,claims:readonly MemoryClaim[]){
  if(claim.replaces_id)return [];
  return claims.filter(c=>c.id!==claim.id&&c.subject_id===claim.subject_id&&c.predicate===claim.predicate&&['accepted','disputed','invalidated'].includes(c.state))
    .sort((a,b)=>(b.reviewed??0)-(a.reviewed??0)||a.id.localeCompare(b.id));
}

const pad=(n:number)=>String(n).padStart(2,'0');
/** A chosen day starts at local midnight. */
export function dayStart(value:string){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
  const t=new Date(value+'T00:00:00').getTime();return Number.isFinite(t)?Math.floor(t/1000):null;
}
/** "As of" a day means the end of that day, or now if the day has not ended. */
export function dayEnd(value:string,nowSeconds:number){
  const start=dayStart(value);if(start===null)return null;
  const [y,m,d]=value.split('-').map(Number),next=Math.floor(new Date(y,m-1,d+1).getTime()/1000);
  return Math.min(next-1,nowSeconds);
}
export function toDayInput(seconds:number|null|undefined){if(seconds==null)return '';const d=new Date(seconds*1000);return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;}
/** Mirrors the server rule: "until" is the start of that day and must come after "from". The server still decides. */
export function validPeriodPayload(from:string,until:string):{valid_from:number|null;valid_until:number|null}|{error:string}{
  const start=from?dayStart(from):null,end=until?dayStart(until):null;
  if((from&&start===null)||(until&&end===null))return {error:'Choose whole days.'};
  if(end!==null&&end<=(start??0))return {error:'“Holds until” must be a later day than “Holds from”.'};
  return {valid_from:start,valid_until:end};
}
export function formatDay(seconds:number){return new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric'}).format(new Date(seconds*1000));}
export function formatTime(seconds:number){return new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(seconds*1000));}
export function validPeriodLabel(from:number|null,until:number|null){
  if(from===null&&until===null)return 'No valid period set';
  if(until===null)return `Holds from ${formatDay(from!)}`;
  if(from===null)return `Holds until the start of ${formatDay(until)}`;
  return `Holds from ${formatDay(from)} until the start of ${formatDay(until)}`;
}

/** The exact body for one version-checked decision. A valid period is sent only when a proposal's period changes. */
export function reviewBody(claim:MemoryClaim,decision:Decision,replaces:MemoryClaim|null,period:{valid_from:number|null;valid_until:number|null}|null){
  const body:Record<string,unknown>={version:claim.version,decision,replaces_id:decision==='supersede'&&replaces?replaces.id:null,
    replaces_version:decision==='supersede'&&replaces?replaces.version:null};
  if(period&&claim.state==='proposed'&&(decision==='accept'||decision==='supersede')&&(period.valid_from!==claim.valid_from||period.valid_until!==claim.valid_until))
    Object.assign(body,period);
  return body;
}
export const REVIEW_ERRORS:Record<string,string>={memory_review_changed:'This statement changed since you opened it. The queue has been refreshed; check it and decide again.',
  memory_replacement_changed:'The statement you chose to replace has changed. Choose it again.',memory_replacement_mismatch:'Only a statement about the same record and of the same kind can be replaced.',
  memory_replacement_already_recorded:'This statement already replaces another one.',memory_source_changed:'Its source changed or is not available to you now, so it cannot be decided.',
  memory_review_closed:'This statement is no longer awaiting a decision.',invalid_memory_validity:'“Holds until” must be a later day than “Holds from”.',
  memory_validity_fixed:'The valid period is fixed once a statement has been decided.',memory_history_capacity:'This statement has reached its history limit.',
  memory_claim_not_found:'This statement is no longer available to you.',invalid_timestamp:'Choose a valid day.',forbidden:'Only the owner who proposed a statement can review it.'};
export const DECIDED:Record<Decision,string>={accept:'Accepted as your reviewed statement. It is a judgement, not a verified fact.',
  supersede:'Accepted as the replacement. The earlier statement is kept as superseded.',dispute:'Disputed. It is kept but not used in answers.',
  withdraw:'Withdrawn. It is kept in the history but not used.'};

const DETAIL:Record<string,string>={support_changed:'its supporting lines changed',source_removed:'its source was removed from ALFRED',
  claim_forgotten:'forgotten',entity_forgotten:'its record was forgotten',captured:'captured with “Remember this”',supersede:'as a replacement',
  from_audit_log:'from the audit log',from_statement_record:'from the statement record',last_review_time_from_statement_record:'last review time from the statement record',
  state_found_at_migration:'state found when history began',support_unavailable_or_not_permitted:'',support_readable_again:''};
const ORIGIN:Record<HistoryEntry['origin'],string>={recorded:'',observed:'noticed by ALFRED when it next looked',migrated:'reconstructed from earlier records',replayed:'replayed from the journal on restore'};
export function historyLine(e:HistoryEntry){
  const who=e.by==='you'?'by you':e.by==='alfred'?'by ALFRED':'by another credential';
  const when=e.time_known?formatTime(e.at):`no later than ${formatTime(e.at)} (exact time not known)`;
  const notes=[e.detail?DETAIL[e.detail]??e.detail.replaceAll('_',' '):'',ORIGIN[e.origin],
    e.valid_period?validPeriodLabel(e.valid_period.from,e.valid_period.until):''].filter(Boolean);
  return {label:stateLabel(e.state),when,who,notes:notes.join(' · ')};
}
export function acceptedSince(item:Pick<AsOfItem,'since'|'since_known'>){
  if(item.since===null)return '';
  return item.since_known?`Accepted ${formatTime(item.since)}`:`Accepted no later than ${formatTime(item.since)} (reconstructed)`;
}
export function notHeldSummary(report:Pick<AsOfReport,'not_held'|'not_yet_recorded'|'without_history'>){
  const parts=Object.entries(report.not_held).filter(([,n])=>n>0).map(([state,n])=>`${n} ${state}`);
  if(report.not_yet_recorded)parts.push(`${report.not_yet_recorded} recorded later`);
  if(report.without_history)parts.push(`${report.without_history} without recorded history`);
  return parts.join(', ');
}
export function asOfPath(at:number,valid:number|null){return `/desk/memory/as-of/${Math.max(0,Math.floor(at))}`+(valid===null?'':`/valid/${Math.max(0,Math.floor(valid))}`);}
