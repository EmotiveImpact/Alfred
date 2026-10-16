import {DeskError} from './deskClient';
/** Kept drafts on the connected server (`/desk/drafts`). The server decides every status. */
export type DraftFilter='current'|'lapsed'|'archived'|'all';
export interface DraftView{
  id:string;capability:string;status:string;ledger_state:string;archived:boolean;version:number;text:string|null;path:string|null;
  created_at:number;approval_expires_at:number;approval_lapsed:boolean;withdrawn:string|null;reproposed_from:string|null;reproposed_as:string[];origin:string|null;
}
export interface DraftListing{drafts:DraftView[];matched:number;limit:number;archived_filter:string;approval_window_seconds:number}
export const DRAFT_FILTERS:[DraftFilter,string][]=[['current','Current'],['lapsed','Lapsed'],['archived','Archived'],['all','All']];
/** The listing path for a filter and optional text. Only fields the server accepts. */
export function draftsPath(filter:DraftFilter,text=''):string{
  const q=new URLSearchParams();
  if(filter==='lapsed')q.set('status','lapsed');
  if(filter==='archived')q.set('archived','only');
  if(filter==='all')q.set('archived','include');
  const t=text.trim().slice(0,200);if(t)q.set('q',t);
  const s=q.toString();return s?'/desk/drafts?'+s:'/desk/drafts';
}
const LABEL:Record<string,string>={awaiting_approval:'Awaiting approval',lapsed:'Approval lapsed · kept',archived:'Archived · kept',
  withdrawn:'Withdrawn · its source was forgotten',queued:'Approved · queued',executing:'Running',uncertain:'Outcome being checked',
  verified:'Saved locally · not sent',cancelled:'Declined · kept',blocked:'Blocked',failed:'Not written'};
export function draftStatusLabel(status:string){return LABEL[status]??status;}
/** Re-propose makes a fresh approval; never offered while one is open or for a withdrawn draft. */
export function canRepropose(d:DraftView){return !['awaiting_approval','queued','executing','uncertain','withdrawn'].includes(d.status);}
export function canArchive(d:DraftView){return !d.archived&&!['queued','executing','uncertain'].includes(d.status);}
const ERRORS:Record<string,string>={draft_changed:'This draft changed. The list has been refreshed.',evidence_not_current:'Its sources changed or are no longer available, so it cannot be proposed again.',
  draft_withdrawn:'This draft was withdrawn when its source was forgotten.',draft_has_no_source_binding:'This draft has no source to recheck, so it cannot be proposed again.',
  draft_in_progress:'Work on this draft has started.',draft_still_awaiting_approval:'This draft is still awaiting your approval.'};
export function draftMessage(e:unknown){return e instanceof DeskError?ERRORS[e.code]??`The server refused this (${e.code}).`:'ALFRED could not be reached.';}
