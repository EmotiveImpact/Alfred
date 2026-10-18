import {describe,it,expect} from 'vitest';
import {parseCommand} from '../src/domain/commands';
import {DeskError} from '../src/integration/deskClient';
import {acknowledgeNote,acknowledgeRequest,amount,attentionLine,autonomyLine,brainEvidenceLine,canAcknowledge,canRunChecks,checkLabel,controlRequest,
  evidenceLabel,evidenceTone,goalMessage,runLine,stateLabel,taskLine,usageLines,verifyRequest,type DimensionUse,type HubResult,type HubTask,type Usage}
  from '../src/integration/goals';

const use=(over:Partial<DimensionUse>={}):DimensionUse=>({used:0,in_flight:0,limit:null,spent:false,warning:false,...over});
const usage=(daily:Partial<Record<'tokens'|'money_pence'|'wall_seconds'|'tasks',Partial<DimensionUse>>>,total={}):Usage=>({
  daily:{since:0,dimensions:{tokens:use(daily.tokens),money_pence:use(daily.money_pence),wall_seconds:use(daily.wall_seconds),tasks:use(daily.tasks)}},
  total:{since:0,dimensions:{tokens:use((total as typeof daily).tokens),money_pence:use(),wall_seconds:use(),tasks:use((total as typeof daily).tasks)}}});

describe('goal budget wording',()=>{
  it('formats each dimension in its own unit',()=>{
    expect([amount('tokens',1200),amount('money_pence',250),amount('wall_seconds',45),amount('wall_seconds',600),amount('tasks',3)])
      .toEqual(['1,200 tokens','£2.50','45 s','10 min','3 tasks']);
  });
  it('lists only limited dimensions, with work in flight, warnings and spent limits',()=>{
    const u=usage({tokens:{used:24,in_flight:30,limit:60,warning:true},tasks:{used:2,limit:2,spent:true}},{tasks:{used:2,limit:50}});
    expect(usageLines(u,'daily')).toEqual(['24 tokens of 60 tokens today (30 tokens in flight) · warning','2 tasks of 2 tasks today · limit reached']);
    expect(usageLines(u,'total')).toEqual(['2 tasks of 50 tasks in total']);
    expect(usageLines(null,'daily')).toEqual([]);
  });
  it('says why something is paused, and never calls a stop a pause',()=>{
    expect(stateLabel('active',null)).toBe('Running');
    expect(stateLabel('paused','operator')).toBe('Paused by you');
    expect(stateLabel('paused','budget_daily_tokens')).toBe('Paused: daily tokens budget reached');
    expect(stateLabel('paused','budget_total_money_pence')).toBe('Paused: total money budget reached');
    expect(stateLabel('stopped','operator')).toBe('Stopped');
    expect(stateLabel('paused','something_else')).toBe('Paused (something_else)');
  });
  it('names autonomy per kind of work, attention items and tasks plainly',()=>{
    expect(autonomyLine({drafting:{level:2,name:'act_with_approval'},research:{level:1,name:'suggest'}}))
      .toBe('drafting: act with approval (2) · research: suggest (1)');
    const warning={id:'a',target:'goal:mandate-1',period:'daily' as const,since:0,dimension:'tokens' as const,level:'warning' as const,used:24,limit:60,at:0,state:'open' as const};
    expect(attentionLine(warning,'Deliver the review')).toBe('Goal Deliver the review · tokens today · 24 tokens of 60 tokens · warning');
    expect(attentionLine(warning)).toBe('Goal · tokens today · 24 tokens of 60 tokens · warning');
    expect(attentionLine({id:'b',target:'brain:synthetic',period:'total',since:0,dimension:'tasks',level:'hard_stop',used:1,limit:1,at:0,state:'open'}))
      .toBe('Brain synthetic · tasks in total · 1 tasks of 1 tasks · limit reached, paused');
    const task:HubTask={job:'job-1',work:'research',brain:'synthetic',autonomy:1,trigger:'heartbeat',created:0,job_state:'succeeded',job_reason:null,
      result:'accepted',accounted:1,usage:{tokens:12,money_pence:0,wall_seconds:1,basis:'metered'}};
    expect(taskLine(task)).toBe('Heartbeat · research · synthetic · succeeded · 12 tokens');
    expect(taskLine({...task,trigger:'operator',usage:{...task.usage!,tokens:30,basis:'unknown_charged_at_ceiling'}}))
      .toBe('Operator · research · synthetic · succeeded · 30 tokens (unknown charged at ceiling)');
  });
});

describe('goal controls',()=>{
  it('send the exact route and the version the person saw, nothing else',()=>{
    expect(controlRequest('goal','mandate-0123456789abcdef01234567','pause',3))
      .toEqual({path:'/desk/hub/mandates/mandate-0123456789abcdef01234567/pause',body:{version:3}});
    expect(controlRequest('brain','synthetic','stop',0)).toEqual({path:'/desk/hub/brains/synthetic/stop',body:{version:0}});
    expect(controlRequest('overall',null,'resume',2)).toEqual({path:'/desk/hub/overall/resume',body:{version:2}});
  });
  it('turn server refusals into plain words',()=>{
    expect(goalMessage(new DeskError('conflict','budget_still_spent',409))).toMatch(/still spent/);
    expect(goalMessage(new DeskError('conflict','hub_not_configured',409))).toMatch(/no brains plugged in/);
    expect(goalMessage(new DeskError('denied','hub_owner_not_hosted',403))).toMatch(/key this ALFRED host was started with/);
    expect(goalMessage(new DeskError('rejected','something_new',400))).toBe('ALFRED refused this (something_new).');
    expect(goalMessage(new Error('x'))).toBe('ALFRED could not be reached.');
  });
  it('open from the command bar, never anything else',()=>{
    expect(parseCommand('goals')).toEqual({kind:'dialog',dialog:'goals'});
    expect(parseCommand('/goals')).toEqual({kind:'dialog',dialog:'goals'});
    expect(parseCommand('stop all goals')).toEqual({kind:'search',query:'stop all goals'});
  });
});

describe('results and checks',()=>{
  const run={position:2,outcome:'failed_checks' as const,sha256:'a'.repeat(64),counts:{passed:1,failed:1,unverifiable:0},
    checks:[{id:'C1',kind:'artefact_sections',status:'passed' as const},{id:'C2',kind:'claims_cited',status:'failed' as const}]};
  const result=(over:Partial<HubResult>={}):HubResult=>({job:'job-0123456789abcdef01234567',brain:'synthetic',task_id:'goal-1',scope_class:'company',
    contract:'accepted',contract_reason:null,declared:2,checks:'failed_checks',state:'failed_checks',evidence:'failed_checks',runs:2,
    acknowledged_over:null,ingested_at:0,updated_at:0,work:{mandate:'mandate-1',goal:'goal-1',goal_title:'Crew brief',work:'research',trigger:'operator'},
    last_run:run,...over});
  it('name each class from ALFRED\'s record, and never call a result without checks verified',()=>{
    expect(evidenceLabel(result())).toBe('Failed checks');
    expect(evidenceLabel(result({contract:'refused'}))).toBe('Failed checks (refused)');
    expect(evidenceLabel(result({evidence:'verified',state:'checked',checks:'checked'}))).toBe('Verified by checks');
    expect(evidenceLabel(result({evidence:'verified',state:'acknowledged',acknowledged_over:'returned'}))).toBe('Acknowledged by you');
    expect(evidenceLabel(result({evidence:'verified',state:'acknowledged',acknowledged_over:'failed_checks'}))).toBe('Acknowledged over failed checks');
    expect(evidenceLabel(result({evidence:'unverifiable',runs:0,last_run:null}))).toBe('Not verified: checks not run');
    expect(evidenceLabel(result({evidence:'unverifiable',runs:1}))).toBe('Not verified: checks could not run');
    // Acknowledged, but nothing was declared: still not verified.
    expect(evidenceLabel(result({evidence:'no_checks',declared:0,state:'acknowledged'}))).toBe('No checks declared');
    expect(evidenceLabel(result({evidence:'not_returned',contract:'stopped'}))).toBe('Not returned');
    expect([evidenceTone('verified'),evidenceTone('failed_checks'),evidenceTone('no_checks')]).toEqual(['on','warn','']);
    expect(brainEvidenceLine('synthetic',{results:6,verified:2,failed_checks:1,unverifiable:0,no_checks:3,not_returned:0}))
      .toBe('synthetic: 2 verified · 1 failed checks · 0 not verified · 3 no checks declared');
  });
  it('word declared checks and the last run without the reasons',()=>{
    expect(checkLabel({id:'C1',kind:'artefact_sections',artefact:'notes.md',sections:['Synthetic brain notes']}))
      .toBe('C1 notes.md has “Synthetic brain notes”');
    expect(checkLabel({id:'C2',kind:'claims_cited'})).toBe('C2 every claim cites a sent excerpt');
    expect(checkLabel({id:'C3',kind:'future_kind'})).toBe('C3 future kind');
    expect(runLine(result())).toBe('Run 2: 1 passed · 1 failed · 0 could not run');
    // Who started the run, as ALFRED recorded it; it changes nothing about how the run counts.
    expect(runLine(result({last_run:{...run,position:1,initiated:'automatic'}})))
      .toBe('Run 1 (automatic, when the result arrived): 1 passed · 1 failed · 0 could not run');
    expect(runLine(result({last_run:{...run,initiated:'owner'}}))).toBe('Run 2 (by you): 1 passed · 1 failed · 0 could not run');
    expect(runLine(result({declared:0,evidence:'no_checks'}))).toMatch(/never counted as verified/);
    expect(runLine(result({last_run:null,runs:0}))).toBe('2 checks declared, not run yet.');
  });
  it('offer checks and acknowledgement only where ALFRED would accept them',()=>{
    expect([canRunChecks(result()),canRunChecks(result({declared:0})),canRunChecks(result({contract:'refused'}))]).toEqual([true,false,false]);
    expect([canAcknowledge(result()),canAcknowledge(result({last_run:null})),canAcknowledge(result({state:'acknowledged'})),
      canAcknowledge(result({contract:'stopped'}))]).toEqual([true,false,false,false]);
  });
  it('send the runs seen and the exact run acknowledged, explicitly over failed checks',()=>{
    expect(verifyRequest('job-0123456789abcdef01234567',2)).toEqual({path:'/desk/hub/results/job-0123456789abcdef01234567/verify',body:{runs:2}});
    expect(acknowledgeRequest('job-0123456789abcdef01234567',run,true))
      .toEqual({path:'/desk/hub/results/job-0123456789abcdef01234567/acknowledge',body:{run_sha256:'a'.repeat(64),accept_failures:true}});
    expect(acknowledgeNote(result())).toMatch(/^Run 2 failed C2\. Accepting it over failed checks/);
    expect(acknowledgeNote(result({declared:0,checks:'returned'}))).toMatch(/stays unverified for routing/);
    expect(goalMessage(new DeskError('conflict','acknowledgement_mismatch',409))).toMatch(/checked again/);
    expect(goalMessage(new DeskError('conflict','failed_checks_need_explicit_acceptance',409))).toMatch(/explicitly/);
  });
});
