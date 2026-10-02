import {useConsole} from '../state/ConsoleProvider';
import {type KnowledgeRecord} from '../domain/model';
/** Sync conflict copies (MEM-014) and read-only export connectors (CON-001), as the server reports them. */
const TOOL:Record<string,string>={syncthing:'Syncthing',dropbox:'Dropbox',nextcloud_owncloud:'Nextcloud or ownCloud',owncloud_legacy:'ownCloud (older client)'};
export const toolLabel=(tool:string)=>TOOL[tool]??tool.replaceAll('_',' ');
const CONFLICT_STATE:Record<string,string>={linked:'beside its original',orphaned:'its original no longer exists',original_unavailable:'its original is not currently available'};
const when=(iso:string)=>new Date(iso).toLocaleString('en-GB');
/** A sync tool kept another version beside this note. ALFRED never merges or chooses between them. */
export function SyncConflictNotice({record}:{record:KnowledgeRecord}){
  const copies=record.syncConflict?.copies??[];
  if(!copies.length)return null;
  return <section className="inspector-section sync-conflict" aria-label="Sync conflict"><h3>Sync conflict</h3>
    <p className="dialog-note">A sync tool kept {copies.length===1?'another version':`${copies.length} other versions`} of this note beside it. ALFRED reads only this note, never merges the versions and never chooses between them. Open both in your editor, keep the right text, then delete the copy.</p>
    <ul className="conflict-copies">{copies.map(c=><li key={c.path}><span className="hash">{c.path}</span><small>{toolLabel(c.tool)} · found {when(c.detectedAt)}</small></li>)}</ul></section>;
}
/** Every conflict copy recorded for one source, including copies whose original is missing. */
export function SourceConflicts({sourceId}:{sourceId:string}){
  const{state,selectRecord}=useConsole();
  const items=(state.snapshot.syncConflicts??[]).filter(c=>c.sourceId===sourceId);
  if(!items.length)return null;
  return <section className="inspector-section" aria-label="Sync conflict copies"><h3>Sync conflict copies</h3>
    <p className="dialog-note">Kept out of the index, search and answers until you resolve them in your editor.</p>
    <ul className="conflict-copies">{items.map(c=><li key={c.path}><span className="hash">{c.path}</span><small>{toolLabel(c.tool)} · {CONFLICT_STATE[c.state]??c.state}</small>
      {c.originalId&&<button className="text-button" onClick={()=>selectRecord(c.originalId!)}>Open the original</button>}</li>)}</ul></section>;
}
export interface ConnectorView{source:string;label:string;connector:string;title:string;scopes:string[];credential_active:boolean;key_expires:number|null;
  freshness:{state:string;imported_at:number|null;age_seconds:number|null;stale_after_seconds:number};items:number|null;
  last_attempt:{at:number;outcome:string;code:string|null}|null;permitted:Record<string,boolean>}
const FRESHNESS:Record<string,string>={current_snapshot:'Current snapshot',stale_snapshot:'Stale: import a newer export',never_imported:'Nothing imported yet',source_unavailable:'Source unavailable'};
export const freshnessLabel=(state:string)=>FRESHNESS[state]??state.replaceAll('_',' ');
const day=(seconds:number|null)=>seconds?new Date(seconds*1000).toLocaleDateString('en-GB'):'never';
/** Read-only export connectors: what each reads, how fresh its snapshot is, and how to refresh it. */
export function ConnectorList({connectors}:{connectors:ConnectorView[]}){
  if(!connectors.length)return null;
  return <section className="ask-section connector-list" aria-label="Export connectors"><h3>Export connectors</h3>
    <p className="dialog-note">Each reads only an export file you choose, never an account. Nothing is written back. Import a newer file with <code>python3 -m alfred.desk connector-import</code> while ALFRED is stopped.</p>
    {connectors.map(c=><div className="access-source connector-row" key={c.source}><span><strong>{c.label}</strong><small>{c.title}</small></span>
      <span className={`connector-state ${c.freshness.state}`}>{freshnessLabel(c.freshness.state)}</span>
      <small className="connector-meta">{c.items==null?'Items hidden without a read grant':`${c.items} item${c.items===1?'':'s'}`} · imported {day(c.freshness.imported_at)} · scopes {c.scopes.join(', ')}{c.last_attempt&&c.last_attempt.outcome!=='imported'?` · last attempt refused (${c.last_attempt.code})`:''}</small></div>)}</section>;
}
