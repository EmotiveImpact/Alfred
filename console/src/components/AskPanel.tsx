import {useState} from 'react';
import {AnswerSupport} from './AnswerSupport';
import {ArrowRight,Crosshair,FileText,WarningCircle} from '@phosphor-icons/react';
import {useConsole} from '../state/ConsoleProvider';
import {DeskError} from '../integration/deskClient';
import {type Evidence,type Turn} from '../state/useAsk';
import {RememberForm} from './RememberForm';
const VIA:Record<string,string>={selected_record:'Selected record',keyword_match:'Matched your words',explicit_link_from_match:'Linked from a match',reviewed_statement_support:'Supports a reviewed statement'};
const STATE_MESSAGE:Record<string,string>={source_changed:'A source changed after this answer. It was withdrawn rather than shown stale.',focus_unavailable:'The selected record is no longer available, so nothing was retrieved for it.',failed:'ALFRED could not complete this question. Nothing was invented.',interrupted:'ALFRED restarted before answering. Ask again.',memory_forgotten:'A reviewed statement this answer used was forgotten, so the answer was withdrawn.',source_forgotten:'A source this answer used was removed from ALFRED, so the answer was withdrawn.'};
function lines(e:Evidence){return e.start_line===e.end_line?`line ${e.start_line}`:`lines ${e.start_line}–${e.end_line}`;}
function DraftProposal({turn,sessionId}:{turn:Turn;sessionId:string}){
  const c=useConsole(),[text,setText]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  if(c.live.session?.role!=='owner'||!turn.result?.packet.evidence.length)return null;
  const propose=async()=>{setBusy(true);setError('');try{
    await c.live.client.post(`/desk/conversations/${sessionId}/draft`,{turn_id:turn.id,text:text.trim(),request_id:'draft-'+turn.id});
    c.setNotice('Draft proposed. Review the exact text in Approvals. Nothing is sent.');setText('');void c.live.refresh();
  }catch(e){setError(e instanceof DeskError&&e.code==='evidence_not_current'?'The evidence changed. Ask again before proposing.':e instanceof DeskError&&e.code==='action_id_collision'?'A different draft was already proposed from this answer.':'The draft could not be proposed.');}finally{setBusy(false);}};
  return <details className="draft-proposal"><summary>Propose a local draft from this answer</summary><p className="dialog-note">Proposing is separate from asking. The draft is bound to these exact sources and still needs your approval. It is never sent.</p>
    <label className="sr-only" htmlFor="draft-text">Draft text</label><textarea id="draft-text" value={text} maxLength={4000} rows={3} onChange={e=>setText(e.target.value)} placeholder="Write the exact draft text"/>
    {error&&<p className="sign-in-error" role="alert">{error}</p>}<button className="secondary-button" disabled={busy||!text.trim()} onClick={propose}>Propose draft</button></details>;
}
export function AskPanel(){
  const c=useConsole(),a=c.ask.state,[follow,setFollow]=useState(''),[remembering,setRemembering]=useState<string|null>(null),model=c.state.snapshot.model;
  if(a.status==='idle')return <p className="dialog-note">Type a question in the command bar. Use “search …” to search records instead.</p>;
  const turn=a.status==='done'?a.turn:null,result=turn?.result??null,packet=result?.packet;
  return <div className="ask-panel">
    <p className="ask-question">{a.question}</p>
    <div className="ask-context">{a.focusLabel?<span className="focus-chip"><Crosshair size={13}/>Context: {a.focusLabel}<small>selection narrows retrieval, grants no access</small></span>:<span className="focus-chip quiet">No record selected · whole permitted workspace</span>}
      <span className="mode-chip">{c.askMode==='local_model'?`Local model · ${model?.name}`:model?.configured?'Source mode · model not used':'Source mode · no model configured'}</span></div>
    {a.status==='waiting'&&<p className="dialog-note" role="status">Retrieving permitted sources…</p>}
    {a.status==='error'&&<div className="review-scope" role="alert"><WarningCircle size={18}/><span>{a.message}</span></div>}
    {turn&&!result&&<div className="review-scope" role="alert"><WarningCircle size={18}/><span>{STATE_MESSAGE[turn.state]??`This question ended as ${turn.state}.`}</span></div>}
    {packet&&<>
      {packet.focus&&packet.focus.available===false&&<p className="dialog-note">The selected record has since been withdrawn.</p>}
      <AnswerSupport report={result!.support}/>
      {result!.claims.length>0&&<section className="ask-section"><h3>Model interpretation</h3><p className="dialog-note">Citations are checked against the supplied lines. That checks reference integrity, not truth.</p>{result!.claims.map((claim,i)=><div className="statement" key={i}><p>{claim.text}</p><small>{claim.citations.map(ci=>`${ci.source_id} ${ci.start_line}–${ci.end_line}`).join(' · ')}</small></div>)}</section>}
      {result!.status==='model_abstained'&&<p className="dialog-note">The model abstained. The sources below are shown unchanged.</p>}
      {packet.memory.length>0&&<section className="ask-section"><h3>Your reviewed statements</h3>{packet.memory.map(m=><div className="statement usable" key={m.claim_id}><p><strong>{m.subject.name}</strong> {m.predicate.replaceAll('_',' ')} {m.value??m.object?.name}</p><small>Your judgement, supported by {m.support.source_id} · not a verified fact</small></div>)}</section>}
      {packet.memory_ambiguities.length>0&&<div className="review-scope"><WarningCircle size={18}/><span>{packet.memory_ambiguities.map(x=>`${x.entity_ids.length} separate “${x.name}” records`).join('; ')}. Say which one you mean; they are never merged.</span></div>}
      <section className="ask-section"><h3>{packet.evidence.length?'Source excerpts':'No permitted source matched'}</h3>
        {packet.evidence.length?<p className="dialog-note">Exact excerpts from authored notes, not a generated answer and not verified facts.</p>:<p className="dialog-note">ALFRED does not invent an answer when nothing permitted supports one.</p>}
        {packet.evidence.map(e=><div className="evidence" key={e.source_id}><header><span className="source-id">{e.source_id}</span><button className="text-button" onClick={()=>{c.selectRecord('note:'+e.note_id);c.setModal(null);}}><FileText size={14}/>{e.title}</button><small>{e.path} · {lines(e)} · {VIA[e.retrieved_via]??e.retrieved_via}</small></header><blockquote>{e.excerpt}</blockquote>
          {turn&&c.live.session?.role==='owner'&&(remembering===e.source_id?<RememberForm evidence={e} turnId={turn.id} onClose={()=>setRemembering(null)}/>:<button className="text-button remember-button" onClick={()=>setRemembering(e.source_id)}>Remember this…</button>)}</div>)}
      </section>
      {turn&&c.ask.sessionId&&<DraftProposal turn={turn} sessionId={c.ask.sessionId}/>}
    </>}
    {a.status!=='waiting'&&<form className="follow-up" onSubmit={e=>{e.preventDefault();if(follow.trim().length<3)return;c.askQuestion(follow.trim(),true);setFollow('');}}><label className="sr-only" htmlFor="follow-up">Follow-up question</label><input id="follow-up" value={follow} maxLength={500} onChange={e=>setFollow(e.target.value)} placeholder="Ask a follow-up"/><button className="send-inline" aria-label="Ask follow-up" type="submit"><ArrowRight size={16}/></button></form>}
    {model?.configured&&model.allowed&&<label className="consent"><input type="checkbox" checked={c.askMode==='local_model'} onChange={e=>c.setAskMode(e.target.checked?'local_model':'sources')}/><span>Use the local model for the next question. Permitted excerpts are sent to {model.name} on this computer; tools stay off.</span></label>}
  </div>;
}
