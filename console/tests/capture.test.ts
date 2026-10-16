import {describe,it,expect} from 'vitest';
import {DeskError} from '../src/integration/deskClient';
import {captureMessage,contextLabel,countLine,ruleLabel,todayLine,type CapturePolicyView} from '../src/integration/capture';

const policy=(over:Partial<CapturePolicyView>={}):CapturePolicyView=>({id:'decisions',version:2,enabled:true,name:'Meeting decisions',context:'company',
  match:{kind:'line_prefix',prefix:'Decision:'},sources:['source'],path_prefix:'Meetings/',daily_budget:5,
  proposes:{subject_id:'atlas',predicate:'decision',memory_type:'semantic',retention_days:null},subject_available:true,description:'',created:1,updated:2,
  counts:{proposed:4,open:1,accepted:2,dismissed:1,invalidated:0,forgotten:0,proposed_today:3,deferred_today:0},...over});

describe('capture policy labels',()=>{
  it('names each rule kind plainly',()=>{
    expect(ruleLabel({kind:'line_prefix',prefix:'Decision:'})).toBe('Lines starting “Decision:”');
    expect(ruleLabel({kind:'dated_line',keyword:null})).toBe('Open dated lines');
    expect(ruleLabel({kind:'dated_line',keyword:'owe'})).toBe('Open dated lines with “owe”');
    expect([contextLabel('personal'),contextLabel('client')]).toEqual(['Personal','Client']);
  });
  it('shows proposed, accepted and dismissed counts per policy',()=>{
    expect(countLine(policy().counts)).toBe('4 proposed · 2 accepted · 1 dismissed · 1 awaiting review');
  });
  it('states the daily budget and counts excess without proposing it',()=>{
    expect(todayLine(policy())).toBe('Today 3 of 5');
    expect(todayLine(policy({counts:{...policy().counts,proposed_today:5,deferred_today:2}}))).toBe('Today 5 of 5 · 2 over budget, counted not proposed');
  });
  it('explains refusals',()=>{
    expect(captureMessage(new DeskError('denied','forbidden',403))).toContain('workspace owner');
    expect(captureMessage(null,'forbidden')).toContain('workspace owner');
    expect(captureMessage(new Error('x'))).toBe('ALFRED could not be reached.');
    expect(captureMessage(new DeskError('conflict','capture_policy_changed',409))).toBe('ALFRED refused this (capture_policy_changed).');
  });
});
