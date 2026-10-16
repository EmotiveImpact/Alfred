import {useCallback,useEffect,useState} from 'react';
import {useConsole} from '../state/ConsoleProvider';
import {DeskError} from '../integration/deskClient';
import {requestKey} from '../integration/jobs';
import {DRAFT_FILTERS,canArchive,canRepropose,draftMessage,draftStatusLabel,draftsPath,type DraftFilter,type DraftListing,type DraftView} from '../integration/drafts';

/** Find kept drafts again: current, lapsed, archived or all. Read only while open. */
export function DraftsFinder(){
  const c=useConsole(),{client,fail}=c.live;
  const[open,setOpen]=useState(false),[filter,setFilter]=useState<DraftFilter>('current'),[text,setText]=useState('');
  const[listing,setListing]=useState<DraftListing|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[tick,setTick]=useState(0);
  const refresh=useCallback(()=>setTick(t=>t+1),[]);
  useEffect(()=>{
    if(!open)return;const controller=new AbortController();
    client.get<DraftListing>(draftsPath(filter,text),controller.signal).then(r=>{if(!controller.signal.aborted){setListing(r);setError('');}}).catch(e=>{
      if(e instanceof DOMException&&e.name==='AbortError')return;setError(draftMessage(e));if(e instanceof DeskError&&e.kind==='signed_out')fail(e);});
    return()=>controller.abort();
  },[client,fail,open,filter,text,tick]);
  const act=async(d:DraftView,command:'archive'|'unarchive'|'repropose')=>{
    setBusy(true);setError('');
    try{
      await client.post(`/desk/drafts/${encodeURIComponent(d.id)}/${command}`,command==='repropose'?{version:d.version,request_id:requestKey()}:{version:d.version});
      c.setNotice(command==='repropose'?'Proposed again with a fresh approval. Review the exact text in Approvals. Nothing is sent.':command==='archive'?'Draft archived. It is kept and can be found under Archived.':'Draft restored from the archive.');
      void c.live.refresh();
    }catch(e){setError(draftMessage(e));if(e instanceof DeskError&&e.kind==='signed_out')fail(e);}
    finally{setBusy(false);refresh();}
  };
  return <details className="draft-proposal drafts-finder" onToggle={e=>setOpen((e.target as HTMLDetailsElement).open)}>
    <summary>Find drafts, including lapsed and archived</summary>
    <p className="dialog-note">Drafts are kept. An approval window can lapse; the draft stays here and can be proposed again with a fresh approval after its sources are rechecked.</p>
    <div className="drafts-controls">
      <label><span>Show</span><select aria-label="Draft filter" value={filter} onChange={e=>setFilter(e.target.value as DraftFilter)}>{DRAFT_FILTERS.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label>
      <input aria-label="Search drafts" placeholder="Search draft text" value={text} maxLength={200} onChange={e=>setText(e.target.value)}/>
    </div>
    {error&&<p className="sign-in-error" role="alert">{error}</p>}
    {open&&!listing&&!error&&<p className="dialog-note" role="status">Reading your drafts…</p>}
    {listing&&(listing.drafts.length?<ul className="drafts-list" aria-label="Drafts">{listing.drafts.map(d=><li key={d.id} className="drafts-row">
      <span><strong>{d.text??(d.withdrawn?'Text removed':'No text')}</strong><small>{draftStatusLabel(d.status)} · {new Date(d.created_at*1000).toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'})}{d.path?` · ${d.path}`:''}</small></span>
      <span className="approval-actions">
        {canRepropose(d)&&<button className="review-button" disabled={busy} aria-label={`Propose again ${d.id}`} onClick={()=>void act(d,'repropose')}>Propose again</button>}
        {canArchive(d)&&<button className="decline-button" disabled={busy} aria-label={`Archive ${d.id}`} onClick={()=>void act(d,'archive')}>Archive</button>}
        {d.archived&&<button className="decline-button" disabled={busy} aria-label={`Unarchive ${d.id}`} onClick={()=>void act(d,'unarchive')}>Unarchive</button>}
      </span></li>)}</ul>:<p className="quiet-empty">No drafts match.</p>)}
    {listing&&listing.matched>listing.drafts.length&&<p className="dialog-note">Showing {listing.drafts.length} of {listing.matched}. Narrow the search to see others.</p>}
  </details>;
}
