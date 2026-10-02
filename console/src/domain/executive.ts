/**
 * Executive workflow view model for the connected console. Shapes mirror GET /desk/executive
 * and GET /desk/executive/records/{id}/brief (alfred/executive.py). Everything here is display
 * logic over what the server already authorised; nothing here grants, infers or stores anything.
 */
export type ExecKind='goal'|'priority'|'commitment'|'decision'|'milestone'|'follow_up';
export interface DecisionOption{id:string;label:string;notes:string;pros:string[];cons:string[]}
export interface DecisionChoice{option:string|null;label:string|null;rationale:string|null;decided_at:number|null}
export interface TrailEvent{event:'decided'|'reopened';option:string|null;label:string|null;rationale:string|null;at:number}
export interface ProgressEntry{kind:'note'|'status';note:string|null;status:string|null;at:number}
export interface ExecRecordView{
  id:string;kind:ExecKind;title:string;detail:string;status:string;open:boolean;project:string|null;due:number|null;overdue:boolean;
  rank:number|null;version:number;created:number;updated:number;project_state:'current'|'unavailable'|null;project_name:string|null;
  responsible:string|null;responsible_link:string|null;responsible_state:'current'|'unavailable'|null;responsible_name:string|null;
  snoozed_until:number|null;snoozed:boolean;options?:DecisionOption[];choice?:DecisionChoice|null;decision_history?:TrailEvent[];
  progress?:ProgressEntry[];last_progress_at?:number;
}
export interface Cite{record?:string;version?:number;note?:string;revision?:number;lines?:number[];claim?:string}
export interface AttentionItem{record:string;version:number;kind:ExecKind;title:string;rules:string[];reason:string;due:number|null;project:string|null;project_name:string|null;responsible:string|null;snoozed_until:number|null;cite:Cite}
export interface ResponsibleGroup{label:string;link:string|null;link_state:'current'|'unavailable'|null;link_name:string|null;records:string[];open:number;overdue:number}
export interface DerivedInsight{rule:string;statement:string;records:{id:string;version:number;title:string;kind:ExecKind}[];projects:{ref:string;name:string}[];basis:string;stored:false}
export interface ExecutiveView{
  records:ExecRecordView[];
  attention:{items:AttentionItem[];snoozed:AttentionItem[];rules:{id:string;rule:string}[];delivery:string};
  insights:{items:DerivedInsight[];rules:{id:string;rule:string}[];basis:string};
  responsible_groups:{groups:ResponsibleGroup[];unassigned_open:string[]};
}
export interface BriefNote{role:'project'|'responsible'|'cited_support';state:string;note_id:string;title?:string;path?:string;revision?:number;start_line:number|null;end_line:number|null;excerpt:string|null;truncated?:boolean;cite?:Cite}
export interface BriefStatement{claim_id:string;version:number;subject:{id:string;kind:string;name:string}|null;predicate:string;object:{id:string;kind:string;name:string}|null;value:string|null;why:'about_linked_record'|'supported_by_linked_note';support:{note_id:string;title:string;path:string;revision:number;start_line:number;end_line:number;quote:string};cite:Cite}
export interface Brief{
  kind:'assembled_brief';record:ExecRecordView;linked_notes:BriefNote[];statements:BriefStatement[];statements_not_shown:Record<string,number>;
  related:{id:string;version:number;kind:ExecKind;title:string;due:number|null;overdue:boolean;responsible:string|null;cite:Cite}[];
  progress:{project:string|null;done:number;total:number;recent:{record:string;title:string;kind:'note'|'status';note:string|null;status:string|null;at:number;cite:Cite}[]}|null;
  questions:{code:string;text:string;cite:Cite}[];assembled_at:number;label:string;model_used:false;stored:false;authority_granted:false;
}
export const KIND_LABEL:Record<ExecKind,string>={priority:'Priority',commitment:'Commitment',follow_up:'Follow-up',decision:'Decision',milestone:'Milestone',goal:'Goal'};
export const BRIEF_KINDS:readonly ExecKind[]=['decision','milestone','commitment'];
export const RULE_LABEL:Record<string,string>={overdue:'Overdue',decision_past_due:'Decision past due',due_soon:'Due soon',stale_milestone:'No recent progress'};
export const ALL='all',UNASSIGNED='unassigned';
/** One key per exact label and explicit link. Namesakes and spellings never share a key. */
export function responsibleKey(label:string|null,link:string|null){return label===null?UNASSIGNED:JSON.stringify([label,link??null]);}
/** A namesake note and reviewed entity read differently, as they do in every other picker. */
export function responsibleHeading(label:string,link:string|null,state:string|null,name:string|null){
  if(link===null)return label;
  return state==='current'?`${label} · linked to ${name}${link.startsWith('entity:')?' (reviewed)':''}`:`${label} · link unavailable`;
}
export function responsibleChoices(groups:ResponsibleGroup[],unassigned:number){
  const choices=[{key:ALL,label:'Everyone'}];
  for(const g of groups)choices.push({key:responsibleKey(g.label,g.link),label:responsibleHeading(g.label,g.link,g.link_state,g.link_name)});
  if(unassigned)choices.push({key:UNASSIGNED,label:'No responsible label'});
  return choices;
}
export function filterByResponsible(records:ExecRecordView[],key:string){return key===ALL?records:records.filter(r=>responsibleKey(r.responsible,r.responsible_link)===key);}
const KIND_GROUPS:[string,ExecKind[]][]=[['Priorities',['priority']],['Commitments and follow-ups',['commitment','follow_up']],['Decisions',['decision']],['Milestones',['milestone']],['Goals',['goal']]];
export function groupRecords(records:ExecRecordView[],by:'kind'|'responsible'):{heading:string;items:ExecRecordView[]}[]{
  if(by==='kind')return KIND_GROUPS.map(([heading,kinds])=>({heading,items:records.filter(r=>kinds.includes(r.kind))}));
  const groups=new Map<string,{heading:string;items:ExecRecordView[]}>();
  for(const r of records){
    const key=responsibleKey(r.responsible,r.responsible_link);
    const heading=r.responsible===null?'No responsible label':responsibleHeading(r.responsible,r.responsible_link,r.responsible_state,r.responsible_name);
    if(!groups.has(key))groups.set(key,{heading,items:[]});
    groups.get(key)!.items.push(r);
  }
  return [...groups.entries()].sort(([a,x],[b,y])=>a===UNASSIGNED?1:b===UNASSIGNED?-1:x.heading.localeCompare(y.heading,'en-GB')).map(([,g])=>g);
}
export interface OptionDraft{label:string;notes:string;pros:string;cons:string}
const lines=(value:string)=>value.split('\n').map(s=>s.replace(/\s+/g,' ').trim()).filter(Boolean);
export function optionDrafts(options:DecisionOption[]|undefined):OptionDraft[]{
  return options?.length?options.map(o=>({label:o.label,notes:o.notes,pros:o.pros.join('\n'),cons:o.cons.join('\n')})):[{label:'',notes:'',pros:'',cons:''},{label:'',notes:'',pros:'',cons:''}];
}
/** Early feedback mirroring the server rule. The server still validates and decides. */
export function optionsPayload(drafts:OptionDraft[]):{options:{label:string;notes:string;pros:string[];cons:string[]}[]}|{error:string}{
  const options=drafts.map(d=>({label:d.label.replace(/\s+/g,' ').trim(),notes:d.notes.trim(),pros:lines(d.pros),cons:lines(d.cons)}));
  if(options.length<2||options.length>6)return {error:'A decision needs two to six options.'};
  if(options.some(o=>!o.label))return {error:'Give every option a name.'};
  if(new Set(options.map(o=>o.label.toLocaleLowerCase('en-GB'))).size!==options.length)return {error:'Each option needs a different name.'};
  if(options.some(o=>o.pros.length>4||o.cons.length>4))return {error:'Up to four pros and four cons per option.'};
  return {options};
}
/** Due dates are entered as a day and stored as 17:00 local time on that day, as elsewhere in the console. */
export function fromDateInput(value:string){if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;const t=new Date(value+'T17:00:00').getTime();return Number.isFinite(t)?Math.floor(t/1000):null;}
export function toDateInput(seconds:number|null|undefined){if(seconds==null)return '';const d=new Date(seconds*1000);const pad=(n:number)=>String(n).padStart(2,'0');return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;}
export function shortDate(seconds:number|null|undefined){return seconds==null?'No date':new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short'}).format(new Date(seconds*1000));}
export function citeLabel(cite:Cite|undefined){
  if(!cite)return '';
  const lines=cite.lines?.length?(cite.lines[0]===cite.lines[1]?`line ${cite.lines[0]}`:`lines ${cite.lines[0]} to ${cite.lines[1]}`):'';
  if(cite.claim)return `Reviewed statement v${cite.version} · note revision ${cite.revision}${lines?', '+lines:''}`;
  if(cite.note)return `Note revision ${cite.revision}${lines?', '+lines:''}`;
  if(cite.record)return `Your record v${cite.version}`;
  return '';
}
export function hiddenSummary(counts:Record<string,number>){return Object.entries(counts).filter(([,n])=>n>0).map(([k,n])=>`${n} ${k.replaceAll('_',' ')}`).join(', ');}
