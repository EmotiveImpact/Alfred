import {describe,it,expect} from 'vitest';
import {describeSupport,type SupportReport} from '../src/integration/answerSupport';
const report=(over:Partial<SupportReport>={}):SupportReport=>({version:1,status:'all_words_found',words:{asked:['atlas'],found:['atlas'],not_found:[]},
  evidence:{excerpts:2,notes:1,retrieved_via:{keyword_match:2}},reviewed_statements:{used:0,withheld:{},ambiguous_names:[]},skipped_sources:{},
  context:{earlier_questions:0,selected_record:false},model:{used:false,claims:0,review:null,issues:[]},basis:'deterministic_term_coverage_not_truth_or_entailment',
  limits:'Counts and word matches only.',truth_verified:false,entailment_verified:false,...over});
describe('what supports an answer',()=>{
  it('stays quiet when every word is found and nothing was withheld, and never claims truth',()=>{
    const d=describeSupport(report());
    expect(d.tone).toBe('quiet');
    expect(d.headline).toBe('Every word you asked about appears in what is shown.');
    expect(d.facts).toEqual(['2 excerpts from 1 note','No model used']);
    expect(JSON.stringify(d)).not.toMatch(/true|correct|verified answer/i);
  });
  it('names the words that were not found',()=>{
    const d=describeSupport(report({status:'partly_covered',words:{asked:['atlas','budget'],found:['atlas'],not_found:['budget']}}));
    expect((d.headline)).toBe('Not found in what is shown: “budget”.');
    expect(d.tone).toBe('attention');
  });
  it('counts withheld statements and skipped sources without showing them',()=>{
    const d=describeSupport(report({reviewed_statements:{used:1,withheld:{conflicting:2,disputed:1},ambiguous_names:['Mina']},skipped_sources:{source_changed:1}}));
    expect(d.facts).toEqual(expect.arrayContaining(['1 reviewed statement used','2 conflicting reviewed statements withheld','1 disputed statement withheld',
      'Several records named “Mina”, kept separate','1 source changed while being read and skipped']));
    expect(d.tone).toBe('attention');
  });
  it('reports model review findings and an empty result plainly',()=>{
    expect(describeSupport(report({model:{used:true,claims:0,review:'withheld_for_review',issues:['number_not_in_cited_text']}})).facts)
      .toContain('Local model used; its review found a number not in the cited text');
    expect(describeSupport(report({status:'nothing_found',evidence:{excerpts:0,notes:0,retrieved_via:{}}})).headline).toBe('Nothing you may read matched this question.');
  });
});
