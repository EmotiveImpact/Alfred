/**
 * Shapes and wording for the agent drafts list (docs/AGENT_DRAFTS.md, docs/PROVENANCE_GATE.md).
 * ALFRED decides where each draft's contents came from, whether it may be approved, and
 * whether a typed address matches; this file only words what it returns and names the exact
 * route, fingerprint and addresses the person acted on. Approving saves a local draft only.
 */
import {DeskError} from './deskClient';
export type DraftState='waiting'|'stopped'|'suggested'|'approved'|'saved'|'cancelled'|'expired'|'changed'|'missing'|'blocked'|'uncertain';
export type Verdict='owner_only'|'uses_untrusted_text'|'steered_by_untrusted_text';
export type PlaceKind='email'|'url'|'domain'|'handle'|'phone';
export interface Place{kind:PlaceKind;value:string|null;source:'owner'|'excerpt'|'unsourced';refs:string[]}
export interface Excerpt{note:string|null;title:string|null;available:boolean}
export interface AgentDraft{id:string;job:string;position:number;created:number;capability:string;state:DraftState;
  disposition:'draft_only'|'pending_approval'|'refused';refusal:string|null;fingerprint:string;reason:string|null;text:string|null;
  original_text:string|null;sources_readable:boolean;verdict:Verdict|null;places:Place[];cited:string[];copied:string[];
  excerpts:Record<string,Excerpt>;action:{id:string;state:string;fingerprint:string;expires_at:number;current:boolean}|null;
  confirmed:{at:number;verdict:Verdict;places:{kind:PlaceKind;held:string|null;confirmed:string|null;replaced:boolean}[]}|null;
  can:{approve:boolean;confirm:boolean;dismiss:boolean}}
export interface DraftsView{available:boolean;reason:'owner_only'|null;mode:'off'|'watch'|'enforce';drafts:AgentDraft[];
  counts:{waiting:number;stopped:number;suggested:number;other:number;dismissed:number}|Record<string,never>}

/** "3 waiting · 1 stopped", leaving out what is zero. */
export function countsLine(view:DraftsView){
  const c=view.counts as Partial<Record<'waiting'|'stopped'|'suggested'|'other',number>>;
  const parts=[['waiting','waiting'],['stopped','stopped'],['suggested','suggested only'],['other','done or closed']] as const;
  const line=parts.filter(([k])=>(c[k]??0)>0).map(([k,w])=>`${c[k]} ${w}`).join(' · ');
  return line||'Nothing yet';
}

const KIND:Record<PlaceKind,string>={email:'email address',url:'web address',domain:'web address',handle:'handle',phone:'phone number'};
export function kindWord(kind:PlaceKind){return KIND[kind];}

/** The chip on each card: where the contents came from, in the owner's terms. */
export function originChip(d:AgentDraft){
  if(d.state==='stopped')return 'Stopped';
  if(d.confirmed)return 'Address you confirmed';
  if(d.verdict==='uses_untrusted_text')return 'Uses wording from a note';
  if(d.verdict==='steered_by_untrusted_text')return 'Address from a note';
  if(d.verdict==='owner_only')return 'From your own words';
  return 'Not labelled';
}
export function chipTone(d:AgentDraft){return d.state==='stopped'||d.verdict==='steered_by_untrusted_text'&&!d.confirmed?'warn':d.verdict==='owner_only'||d.confirmed?'on':'';}

const STATE:Record<DraftState,string>={waiting:'Waiting for your approval',stopped:'Stopped before approval',suggested:'Suggested only, not offered for approval',
  approved:'Approved, being saved',saved:'Saved as a local draft',cancelled:'Cancelled',expired:'Approval window closed',
  changed:'Its notes changed, so it cannot be approved',missing:'No longer available',blocked:'Blocked when saving',uncertain:'Saving not confirmed'};
export function stateLine(d:AgentDraft){return STATE[d.state]??d.state;}

/** The titles of notes behind some refs, joined, for example "“Inbox item”" or "a note you can no longer read". */
export function notesNamed(d:AgentDraft,refs:string[]){
  const titles=[...new Set(refs.map(r=>d.excerpts[r]?.title).filter((t):t is string=>Boolean(t)))];
  if(!titles.length)return refs.length?'a note you can no longer read':'no note';
  return titles.map(t=>`“${t}”`).join(', ');
}

/** The note an excerpt ref points to, if the person may still open it. */
export function openableNote(d:AgentDraft,refs:string[]){
  for(const r of refs){const e=d.excerpts[r];if(e?.available&&e.note)return {id:`note:${e.note}`,title:e.title??'the note'};}
  return null;
}

/** Why a draft stopped, in plain words. */
export function stopReason(d:AgentDraft){
  if(d.refusal==='steered_by_untrusted_text'){
    const held=d.places.filter(p=>p.source!=='owner');
    const kinds=[...new Set(held.map(p=>kindWord(p.kind)))].join(' and ');
    const from=held.some(p=>p.source==='excerpt')?`came from ${notesNamed(d,held.flatMap(p=>p.refs))}, not from you`:'is not in anything you wrote';
    return `The ${kinds||'address'} in this draft ${from}. Text inside an email or note can be planted to trick an agent, so ALFRED stopped it.`;
  }
  if(d.refusal==='capability_not_allowed_for_brains')return 'The agent asked to do something agents may not do: only local drafts can be proposed. Nothing was done.';
  return d.refusal?`ALFRED refused this draft (${d.refusal.replaceAll('_',' ')}).`:'ALFRED refused this draft.';
}

/** One line per address the owner did not give: what it is, where it was found. */
export function placeLines(d:AgentDraft){
  return d.places.filter(p=>p.source!=='owner').map(p=>{
    const value=p.value??'withheld because its notes can no longer be read';
    const where=p.source==='excerpt'?`found in ${notesNamed(d,p.refs)}`:'found in nothing you or your notes wrote';
    return `${kindWord(p.kind)[0].toUpperCase()+kindWord(p.kind).slice(1)}: ${value} · ${where}`;
  });
}

/** What the draft used from notes, for a waiting or suggested draft. */
export function noteLine(d:AgentDraft){
  if(d.verdict!=='uses_untrusted_text'||d.confirmed)return null;
  const refs=[...new Set([...d.cited,...d.copied])];
  return `Some wording came from your note ${notesNamed(d,refs)}. Nothing in it sends anything anywhere.`;
}

/** What the person typed, and whether it replaced the address. */
export function confirmedLine(d:AgentDraft){
  if(!d.confirmed)return null;
  return d.confirmed.places.map(p=>p.replaced?`You replaced ${p.held??'the address'} with ${p.confirmed??'your own'}.`
    :`You confirmed ${p.confirmed??'the address'} yourself.`).join(' ');
}

/** The first line of the text, shortened, for the card. */
export function preview(text:string|null,limit=160){
  if(text===null)return 'Withheld: the notes this came from can no longer be read.';
  const first=text.split('\n').find(l=>l.trim())??'';
  return first.length>limit?first.slice(0,limit-1).trimEnd()+'…':first;
}

/* Requests. Each names the exact draft and what the person saw; the server checks both. */
export function confirmRequest(d:AgentDraft,typed:string[]){
  return {path:`/desk/hub/drafts/${encodeURIComponent(d.id)}/confirm`,body:{fingerprint:d.fingerprint,places:typed.map(t=>t.trim())}};
}
export function dismissRequest(d:AgentDraft){return {path:`/desk/hub/drafts/${encodeURIComponent(d.id)}/dismiss`,body:{}};}
export function approveRequest(d:AgentDraft){
  if(!d.action)throw new Error('nothing to approve');
  return {path:`/desk/actions/${encodeURIComponent(d.action.id)}/approve`,body:{fingerprint:d.action.fingerprint}};
}

const ERRORS:Record<string,string>={
  hub_not_configured:'This ALFRED host has no brains plugged in, so no agent has drafted anything.',
  invalid_places:'Type each address exactly, one per box, with nothing else around it.',
  address_hidden_in_text:'The address in this draft is disguised with hidden characters, so ALFRED cannot swap it safely. Ask again and name the address yourself.',
  address_not_confirmed:'That still leaves an address you did not give. Nothing was changed.',
  proposal_changed:'This draft changed since you opened it. The list has been refreshed.',
  proposal_dismissed:'This draft was dismissed.',
  not_held:'This draft is no longer waiting for an address. The list has been refreshed.',
  sources_changed:'The notes this draft came from changed or can no longer be read, so it cannot be offered for approval.',
  draft_in_progress:'This draft is approved and being saved. It can be dismissed once it is saved.',
  approval_mismatch:'The draft changed. Review the current version.',
  evidence_or_approval_expired:'Its notes changed or the approval window closed. Nothing was approved.',
  action_expired:'The approval window closed. Nothing was approved.',
  invalid_state:'This draft is no longer waiting for a decision.',
  not_found:'This draft is not yours, or no longer exists.',
  forbidden:'Only the workspace owner can act on agent drafts.',
};
export function draftsMessage(e:unknown){return e instanceof DeskError?ERRORS[e.code]??`ALFRED refused this (${e.code}).`:'ALFRED could not be reached.';}
