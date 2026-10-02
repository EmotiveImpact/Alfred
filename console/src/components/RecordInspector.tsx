import {useEffect,useRef} from 'react';
import {X,LinkSimple,CaretRight,DownloadSimple} from '@phosphor-icons/react';
import {useConsole,downloadJSON} from '../state/ConsoleProvider';
import {type RecordDetail} from '../integration/ConsoleReadPort';
import {type Relationship} from '../domain/model';
const LAYER_LABEL:Record<string,string>={note_reference:'authored link',reviewed_claim:'reviewed relationship',review_support:'supported by reviewed excerpt',fixture:''};
const ORIGIN_BADGE:Record<string,string>={authored_note:'AUTHORED NOTE · NOT A VERIFIED FACT',reviewed_entity:'REVIEWED MEMORY · YOUR JUDGEMENT',source:'SELECTED SOURCE'};
function frontmatterEnd(lines:string[]){if(lines[0]?.trim()!=='---')return 0;const end=lines.findIndex((l,i)=>i>0&&l.trim()==='---');return end<0?0:end+1;}
function ConnectedProvenance({detail}:{detail:RecordDetail}){
  const{selectRecord}=useConsole();
  if(detail.type==='note'){
    const start=frontmatterEnd(detail.lines),shown=detail.lines.slice(start,start+14);
    return <section className="inspector-section"><h3>Provenance</h3><dl className="detail-list"><div><dt>Path</dt><dd>{detail.path}</dd></div><div><dt>Revision</dt><dd>{detail.revision}</dd></div><div><dt>SHA-256</dt><dd className="hash">{detail.sha256.slice(0,16)}…</dd></div><div><dt>Basis</dt><dd>Authored text, not verified</dd></div></dl>
      <ol className="source-lines" start={start+1} aria-label="Exact source lines">{shown.map((line,i)=><li key={i}>{line||' '}</li>)}</ol>
      {detail.lines.length>start+14&&<p className="dialog-note">Showing lines {start+1} to {start+shown.length} of {detail.lines.length}{detail.truncated?' (inspection limit reached)':''}.</p>}</section>;
  }
  if(detail.type==='source')return <section className="inspector-section"><h3>Source status</h3><dl className="detail-list"><div><dt>Status</dt><dd>{detail.status}</dd></div><div><dt>Checked</dt><dd>{new Date(detail.checkedAt).toLocaleString('en-GB')}</dd></div><div><dt>Notes</dt><dd>{detail.notes}</dd></div><div><dt>Issues</dt><dd>{detail.issues.length}</dd></div></dl>{detail.issues.slice(0,4).map((issue,i)=><p className="dialog-note" key={i}>{issue.code}{issue.path?` · ${issue.path}`:''}</p>)}</section>;
  return <section className="inspector-section"><h3>Reviewed statements</h3>{detail.sameNameEntities.length>0&&<p className="dialog-note">{detail.sameNameEntities.length} other record{detail.sameNameEntities.length>1?'s share':' shares'} this name. They are kept separate.</p>}
    {detail.statements.length?detail.statements.map(s=><div className={`statement ${s.usable?'usable':'withheld'}`} key={s.id}><p><strong>{s.predicate.replaceAll('_',' ')}</strong> {s.value??s.object?.name??''}</p><small>{s.usable?'Accepted and current':s.state==='invalidated'?'Source changed · review needed':s.conflicts.length?'Conflicting reviews · withheld':s.state}</small>
      {s.support?<><blockquote>{s.support.quote}</blockquote><button className="text-button" onClick={()=>selectRecord(s.support!.noteId)}>{s.support.title}, {s.support.startLine===s.support.endLine?`line ${s.support.startLine}`:`lines ${s.support.startLine}–${s.support.endLine}`}</button></>:<p className="dialog-note">Original support is not currently available.</p>}</div>):<p>No statements recorded for this record.</p>}</section>;
}
function InspectorBody(){
  const{selected,relationships,records,dispatch,selectRecord,connected,detail,state}=useConsole(),heading=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{const previous=document.activeElement as HTMLElement|null;heading.current?.focus();return()=>{if(previous?.isConnected)previous.focus();};},[]);
  if(!selected)return null;
  const edges=relationships.filter(e=>e.from===selected.id||e.to===selected.id);
  const neighbour=(e:Relationship)=>records.find(r=>r.id===(e.from===selected.id?e.to:e.from));
  const exportRecord=()=>connected?downloadJSON({mode:'connected',workspace:state.snapshot.workspaceId,observedAt:state.snapshot.observedAt,record:selected,detail:detail.status==='ready'?detail.detail:null,relationships:edges},`ALFRED-${selected.id.replace(/[^A-Za-z0-9_-]/g,'-')}.json`):downloadJSON({mode:'demo',record:selected,relationships:edges},`ALFRED-${selected.id}-demo.json`);
  return <><header className="inspector-header"><span className="eyebrow">{selected.category} / inspect</span><button className="icon-button" aria-label="Close record inspector" onClick={()=>dispatch({type:'select',id:null})}><X size={20}/></button></header><div className="inspector-body">
    <span className="demo-badge">{connected?ORIGIN_BADGE[selected.origin??'']??'RECORD':'DEMONSTRATION RECORD'}</span><h2 ref={heading} tabIndex={-1}>{selected.title}</h2><p className="inspector-summary">{selected.summary}</p>
    {connected?<>{detail.status==='loading'&&<p className="dialog-note" role="status">Reading the current record…</p>}{detail.status==='unavailable'&&<p className="dialog-note" role="status">{detail.message}</p>}{detail.status==='ready'&&detail.id===selected.id&&<ConnectedProvenance detail={detail.detail}/>}</>
    :<><section className="inspector-section"><h3>Context</h3><p>{selected.detail}</p></section><section className="inspector-section"><h3>Provenance</h3><dl className="detail-list"><div><dt>Source</dt><dd>{selected.provenance.label}</dd></div><div><dt>Revision</dt><dd>{selected.provenance.revision}</dd></div><div><dt>Basis</dt><dd>{selected.provenance.basis}</dd></div><div><dt>Workspace</dt><dd>{selected.scope}</dd></div></dl><blockquote>{selected.provenance.excerpt}</blockquote></section></>}
    <section className="inspector-section"><h3>Explicit relationships</h3>{edges.length?edges.map(e=>{const other=neighbour(e);return <button className="linked-record" key={e.id} onClick={()=>other&&selectRecord(other.id)}><LinkSimple size={17}/><span><small>{connected?`${LAYER_LABEL[e.layer??'']} · ${e.relation.replaceAll('_',' ')}`:e.relation.replaceAll('_',' ')}</small>{other?.title}</span><CaretRight size={14}/></button>;}):<p>{connected?'No supported relationships for this record. Background particles are decorative, not relationships.':'No explicit links in this fixture. Background particles are decorative, not relationships.'}</p>}</section>
    <button className="secondary-button export-button" onClick={exportRecord}><DownloadSimple size={17}/>Export record</button></div></>;
}
export function RecordInspector(){const{selected}=useConsole();return selected?<aside className="inspector" aria-label="Record inspector"><InspectorBody/></aside>:null;}
