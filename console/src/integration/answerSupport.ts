/** The server's per-answer support report (alfred/answer_support.py), in plain words. */
export interface SupportReport{
  version:number;status:'nothing_found'|'partly_covered'|'all_words_found';
  words:{asked:string[];found:string[];not_found:string[]};
  evidence:{excerpts:number;notes:number;retrieved_via:Record<string,number>};
  reviewed_statements:{used:number;withheld:Record<string,number>;ambiguous_names:string[]};
  skipped_sources:Record<string,number>;
  context:{earlier_questions:number;selected_record:boolean};
  model:{used:boolean;claims:number;review:string|null;issues:string[]};
  basis:string;limits:string;truth_verified:false;entailment_verified:false;
}
const WITHHELD:Record<string,[string,string]>={conflicting:['conflicting reviewed statement','conflicting reviewed statements'],
  disputed:['disputed statement','disputed statements'],not_currently_available:['statement whose support is unavailable','statements whose support is unavailable'],
  needs_fresh_review:['statement needing a fresh review','statements needing a fresh review'],outside_valid_period:['statement outside its valid period','statements outside their valid period'],
  awaiting_review:['statement awaiting your review','statements awaiting your review']};
const SKIPPED:Record<string,string>={source_changed:'changed while being read',source_unavailable:'was unavailable'};
const ISSUE:Record<string,string>={number_not_in_cited_text:'a number not in the cited text',requested_amount_not_evidenced:'an amount the sources do not give',
  broad_citation_review:'a broad citation',duplicate_citations_removed:'duplicate citations removed'};
const plural=(n:number,one:string,many:string)=>`${n} ${n===1?one:many}`;
const quoted=(words:string[])=>words.map(w=>`“${w}”`).join(', ');
/** A headline and short facts. Never says an answer is true or complete. */
export function describeSupport(r:SupportReport):{headline:string;tone:'quiet'|'attention';facts:string[]}{
  const headline=r.status==='nothing_found'?'Nothing you may read matched this question.'
    :r.status==='partly_covered'?`Not found in what is shown: ${quoted(r.words.not_found)}.`
    :'Every word you asked about appears in what is shown.';
  const facts=[plural(r.evidence.excerpts,'excerpt','excerpts')+(r.evidence.excerpts?` from ${plural(r.evidence.notes,'note','notes')}`:'')];
  if(r.reviewed_statements.used)facts.push(plural(r.reviewed_statements.used,'reviewed statement used','reviewed statements used'));
  for(const[reason,count] of Object.entries(r.reviewed_statements.withheld)){const[one,many]=WITHHELD[reason]??[reason.replaceAll('_',' '),reason.replaceAll('_',' ')];facts.push(`${plural(count,one,many)} withheld`);}
  if(r.reviewed_statements.ambiguous_names.length)facts.push(`Several records named ${quoted(r.reviewed_statements.ambiguous_names)}, kept separate`);
  for(const[reason,count] of Object.entries(r.skipped_sources))facts.push(`${plural(count,'source','sources')} ${SKIPPED[reason]??reason.replaceAll('_',' ')} and skipped`);
  if(r.context.earlier_questions)facts.push(`Follows ${plural(r.context.earlier_questions,'earlier question','earlier questions')}`);
  if(r.context.selected_record)facts.push('Narrowed by your selected record');
  facts.push(r.model.used?`Local model used${r.model.issues.length?`; its review found ${r.model.issues.map(i=>ISSUE[i]??i.replaceAll('_',' ')).join(', ')}`:''}`:'No model used');
  const attention=r.status!=='all_words_found'||Object.keys(r.reviewed_statements.withheld).length>0||Object.keys(r.skipped_sources).length>0||r.model.issues.length>0;
  return{headline,tone:attention?'attention':'quiet',facts};
}
