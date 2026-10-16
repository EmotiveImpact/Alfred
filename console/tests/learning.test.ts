import {describe,it,expect} from 'vitest';
import {DeskError} from '../src/integration/deskClient';
import {batchBody,digestLine,learningDecision,learningLine,learningMessage,trustRuleBody,trustRuleLine,upstreamLine,
  type DigestView,type LearningProposal,type TrustRuleView} from '../src/integration/learning';
import {FIXED_DELIVERY,formFromRoutine,formProblem,runSummary,settingsPayload,type RoutineView,type RunView} from '../src/integration/routines';

const T=1_900_000_000;
const proposal=(over:Partial<LearningProposal>={}):LearningProposal=>({id:'lp-1',version:1,kind:'preference',category:'writing_length',
  category_label:'Writing style: how long your drafts are',key:'preference:draft_length',rule:'draft_edits',
  statement:'When you edit a draft before proposing it again, you usually make it shorter.',evidence:['audit:1','audit:2','audit:3'],evidence_total:3,threshold:3,
  origin:'daily_learning',run:'run-1',supersedes:null,state:'suggested',created:T,decided:null,decision:null,decision_label:'Awaiting your review',record:null,
  trustable:true,executable:false,authority_granted:false,...over});
const rule=(over:Partial<TrustRuleView>={}):TrustRuleView=>({id:'trusted-kinds',version:0,enabled:false,categories:[],configured:false,
  trustable_categories:[{id:'writing_length',label:'Writing style: how long your drafts are'},{id:'writing_structure',label:'Presentation: how many sentences your drafts are broken into'}],
  never_trustable:'People, money, commitments, procedures, routing and anything a worker supplied.',...over});
const digest=(over:Partial<DigestView>={}):DigestView=>({day:'2030-03-17',day_start:T-63_000,utc_offset_minutes:0,items:[proposal(),proposal({id:'lp-2',version:3})],
  counts:{proposed:2,awaiting_review:2,accepted_by_your_rule:0},approvable:[{id:'lp-1',version:1},{id:'lp-2',version:3}],recent_days:[],...over});

describe('learning wording',()=>{
  it('names the kind, origin and evidence against the threshold',()=>{
    expect(learningLine(proposal())).toBe('Preference · from your records · 3 pieces of evidence, at least 3 needed');
    expect(learningLine(proposal({kind:'procedure',origin:'harvest_staged',evidence_total:2,supersedes:null}))).toBe('Procedure draft · staged by a worker · 2 pieces of evidence');
    expect(learningLine(proposal({supersedes:'lrn-0123'}))).toMatch(/an update to one you accepted$/);
  });
  it('says when your rule accepted something and that it can be undone',()=>{
    expect(learningDecision(proposal())).toBe('Awaiting your review');
    expect(learningDecision(proposal({decision:'returned_by_undo'}))).toBe('Back for your review after you undid your rule');
    expect(learningDecision(proposal({state:'accepted',decision:'accepted_by_your_rule',decision_label:'Accepted by your rule',undo_available:true,record_state:'current'})))
      .toBe('Accepted by your rule · you can undo this');
    expect(learningDecision(proposal({state:'accepted',decision:'accepted_by_you',decision_label:'Accepted by you',record_state:'retired'}))).toBe('Accepted by you · now retired');
  });
  it('summarises the day',()=>{
    expect(digestLine(digest())).toBe('2 proposed on 2030-03-17 · 2 awaiting your review');
    expect(digestLine(digest({counts:{proposed:3,awaiting_review:1,accepted_by_your_rule:2}}))).toBe('3 proposed on 2030-03-17 · 1 awaiting your review · 2 accepted by your rule');
    expect(digestLine(digest({items:[],counts:{proposed:0,awaiting_review:0,accepted_by_your_rule:0}}))).toBe('Nothing proposed on 2030-03-17');
  });
  it('reports the upstream comparison and never claims a fetch',()=>{
    expect(upstreamLine({status:'no_owner_file'})).toMatch(/nothing was compared · nothing fetched or installed$/);
    expect(upstreamLine({status:'compared',briefs_written:2,licence_changed:1,manifest_mismatch:0}))
      .toBe('2 new update briefs · 1 with a different licence reported · nothing fetched or installed');
  });
  it('turns refusals into plain words',()=>{
    expect(learningMessage(new DeskError('conflict','learning_changed',409))).toMatch(/Nothing was accepted/);
    expect(learningMessage(new DeskError('denied','category_not_trustable',403))).toMatch(/writing style and presentation/);
    expect(learningMessage(new DeskError('rejected','something_new',400))).toBe('ALFRED refused this (something_new).');
  });
});

describe('learning bodies',()=>{
  it('approves exactly the listed set with versions',()=>{
    expect(batchBody(digest())).toEqual({day:'2030-03-17',items:[{id:'lp-1',version:1},{id:'lp-2',version:3}]});
  });
  it('names only categories the server offers as trustable',()=>{
    expect(trustRuleBody(rule(),true,['writing_structure','procedure','writing_length'])).toEqual({version:0,enabled:true,categories:['writing_length','writing_structure']});
    expect(trustRuleLine(rule())).toBe('Off. Every learning waits for your review.');
    expect(trustRuleLine(rule({enabled:true,version:2,categories:['writing_length']}))).toBe('On (version 2) for: Writing style: how long your drafts are');
  });
});

describe('daily learning routine',()=>{
  const routine:RoutineView={kind:'daily-learning',name:'Daily learning',description:'',rules:[],default:{schedule:{daily_at:'21:00'},interrupt:'show_now'},
    configured:false,enabled:false,paused:false,version:0,settings:null,next_due:null,runs_today:0,quiet_now:false,authority_available:true};
  it('has fixed delivery like the brief: no interrupt choice and no drafts',()=>{
    expect(FIXED_DELIVERY).toEqual(['morning-brief','daily-learning']);
    const f=formFromRoutine(routine,0);
    expect(f).toMatchObject({every:'daily',dailyAt:'21:00',runsPerDay:1});
    expect(formProblem('daily-learning',f)).toBeNull();
    expect(formProblem('daily-learning',{...f,proposeDrafts:true})).toMatch(/offers no drafts/);
    expect(settingsPayload('daily-learning',{...f,interrupt:'hold_for_brief',proposeDrafts:true},0)).toMatchObject({interrupt:'show_now',propose_drafts:false});
  });
  it('summarises a learning run',()=>{
    const base:RunView={id:'r1',kind:'daily-learning',trigger:'manual',started:T,finished:T,status:'completed',skipped_reason:null,
      outcome:{trigger:'manual',missed_slots:0,budget:{runs_today:1,runs_per_day:1,nominations_per_run:3}}};
    const proposed=[{proposal:'lp-1',kind:'preference',category:'writing_length',rule:'draft_edits',accepted_by_rule:{rule:'trusted-kinds',version:1,record:'lrn-1'}},
      {proposal:'lp-2',kind:'procedure',category:'procedure',rule:'procedures'}];
    expect(runSummary({...base,outcome:{...base.outcome,proposed:[],accepted_by_rule:0,upstream:{status:'no_owner_file'}}})).toBe('Learning run · 0 learnings for your review');
    expect(runSummary({...base,outcome:{...base.outcome,proposed,accepted_by_rule:1,upstream:{status:'compared',briefs_written:2}}}))
      .toBe('Learning run · 1 learning for your review · 1 accepted by your rule · 2 update briefs');
    expect(runSummary({...base,status:'skipped',skipped_reason:'paused'})).toBe('Skipped · This routine was paused.');
  });
});
