import {describe,it,expect} from 'vitest';
import {parseCommand} from '../src/domain/commands';
import {DeskError} from '../src/integration/deskClient';
import {amount,attentionLine,autonomyLine,controlRequest,goalMessage,stateLabel,taskLine,usageLines,type DimensionUse,type HubTask,type Usage} from '../src/integration/goals';

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
