/**
 * Shapes and wording for daily learning (alfred/learning.py, H3).
 * The server gathers the evidence, applies the stated rules, checks every version and decides.
 * This file only formats what it returns and builds the exact bodies the person chose.
 * Nothing here learns, accepts, sends or runs anything.
 */
import {DeskError} from './deskClient';

export type LearningKind='preference'|'procedure'|'routing';
export interface LearningProposal{id:string;version:number;kind:LearningKind;category:string;category_label:string;key:string;rule:string;
  statement:string;evidence:string[];evidence_total:number;threshold:number;origin:string;run:string|null;supersedes:string|null;
  state:'suggested'|'accepted'|'dismissed';created:number;decided:number|null;decision:string|null;decision_label:string;record:string|null;
  trustable:boolean;record_state?:string;record_version?:number;accepted_by_rule?:{rule:string;version:number};undo_available?:boolean;
  executable:false;authority_granted:false}
export interface LearningRecord{id:string;version:number;kind:LearningKind;category:string;category_label:string;key:string;statement:string;
  state:'current'|'superseded'|'retired'|'undone';accepted:number;accepted_by:'you'|'your_rule';sent_to_brains:boolean}
export interface TrustRuleView{id:string;version:number;enabled:boolean;categories:string[];configured:boolean;
  trustable_categories:{id:string;label:string}[];never_trustable:string}
export interface DigestView{day:string;day_start:number;utc_offset_minutes:number;items:LearningProposal[];
  counts:{proposed:number;awaiting_review:number;accepted_by_your_rule:number};approvable:{id:string;version:number}[];
  recent_days:{day:string;proposed:number}[]}
export interface LearningView{proposals:LearningProposal[];records:LearningRecord[];counts:{awaiting_review:number;current_records:number};
  trust_rule:TrustRuleView;upstream:{briefs:{repository:string;comparison:string}[]}}

const KIND_LABEL:Record<LearningKind,string>={preference:'Preference',procedure:'Procedure draft',routing:'Routing note'};
const ORIGIN_LABEL:Record<string,string>={daily_learning:'from your records',harvest_artefact:'from a worker\'s result',harvest_staged:'staged by a worker'};

/** Kind, where it came from and how much evidence supports it, in one line. */
export function learningLine(p:LearningProposal){
  const evidence=`${p.evidence_total} piece${p.evidence_total===1?'':'s'} of evidence`;
  return [KIND_LABEL[p.kind]??p.kind,ORIGIN_LABEL[p.origin]??p.origin.replaceAll('_',' '),
    p.origin==='daily_learning'?`${evidence}, at least ${p.threshold} needed`:evidence,p.supersedes?'an update to one you accepted':null].filter(Boolean).join(' · ');
}
/** What happened to a learning. Rule acceptances say so, and say they can be undone. */
export function learningDecision(p:LearningProposal){
  if(p.state==='suggested')return p.decision==='returned_by_undo'?'Back for your review after you undid your rule':'Awaiting your review';
  if(p.decision==='accepted_by_your_rule')return p.undo_available?'Accepted by your rule · you can undo this':'Accepted by your rule';
  if(p.record_state&&p.record_state!=='current')return `${p.decision_label} · now ${p.record_state}`;
  return p.decision_label;
}
export function digestLine(d:DigestView){
  const c=d.counts;
  if(!c.proposed)return `Nothing proposed on ${d.day}`;
  return [`${c.proposed} proposed on ${d.day}`,`${c.awaiting_review} awaiting your review`,
    c.accepted_by_your_rule?`${c.accepted_by_your_rule} accepted by your rule`:null].filter(Boolean).join(' · ');
}
/** The exact set shown, ids with versions. The server refuses the whole set if any item changed. */
export function batchBody(d:DigestView){return {day:d.day,items:d.approvable.map(i=>({id:i.id,version:i.version}))};}
export function trustRuleBody(rule:TrustRuleView,enabled:boolean,categories:string[]){
  const allowed=new Set(rule.trustable_categories.map(c=>c.id));
  return {version:rule.version,enabled,categories:categories.filter(c=>allowed.has(c)).sort()};
}
export function trustRuleLine(rule:TrustRuleView){
  if(!rule.enabled)return 'Off. Every learning waits for your review.';
  const names=rule.trustable_categories.filter(c=>rule.categories.includes(c.id)).map(c=>c.label);
  return `On (version ${rule.version}) for: ${names.join('; ')}`;
}

const UPSTREAM_STATUS:Record<string,string>={no_owner_file:'No file of latest known versions yet, so nothing was compared',
  owner_file_invalid:'Your file of latest known versions could not be read',catalogue_unavailable:'The source library catalogue could not be read',
  catalogue_invalid:'The source library catalogue is not valid'};
/** The upstream comparison of one run. Nothing is ever fetched or installed. */
export function upstreamLine(u:{status:string;briefs_written?:number;licence_changed?:number;manifest_mismatch?:number}){
  if(u.status!=='compared')return `${UPSTREAM_STATUS[u.status]??u.status.replaceAll('_',' ')} · nothing fetched or installed`;
  const parts=[`${u.briefs_written??0} new update brief${u.briefs_written===1?'':'s'}`];
  if(u.licence_changed)parts.push(`${u.licence_changed} with a different licence reported`);
  if(u.manifest_mismatch)parts.push(`${u.manifest_mismatch} manifest${u.manifest_mismatch===1?'':'s'} not matching the catalogue`);
  return `${parts.join(' · ')} · nothing fetched or installed`;
}

const ERRORS:Record<string,string>={learning_changed:'This learning changed since you read it. Nothing was accepted. The list was refreshed.',
  learning_not_in_digest:'An item is not in that day\'s list any more. Nothing was accepted. The list was refreshed.',
  learning_closed:'This learning was already decided.',learning_not_found:'This learning is no longer available to you.',
  learning_capacity:'You have reached the limit of accepted learnings. Retire one first.',
  learning_not_trustable:'Only writing style and presentation preferences can be accepted by your rule.',
  category_not_trustable:'Only writing style and presentation preferences can be named in your rule.',
  trust_rule_changed:'Your rule changed elsewhere. The view was refreshed; check and save again.',
  learning_not_accepted_by_rule:'Only an acceptance made by your rule can be undone here.',
  invalid_learning_batch:'Nothing awaiting review in this list.',forbidden:'Only the workspace owner can do this.'};
export function learningMessage(e:unknown){return e instanceof DeskError?ERRORS[e.code]??`ALFRED refused this (${e.code}).`:'ALFRED could not be reached.';}
