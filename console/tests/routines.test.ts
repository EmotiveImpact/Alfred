import {describe,it,expect} from 'vitest';
import {parseCommand} from '../src/domain/commands';
import {DeskError} from '../src/integration/deskClient';
import {OFFSETS,browserOffset,citeLabel,decisionLabel,formFromRoutine,formProblem,holdLabel,localClock,localMoment,nominationLine,offsetLabel,readLine,routineMessage,
  runSummary,scheduleLabel,settingsPayload,sourceLabel,type NominationView,type RoutineView,type RunView} from '../src/integration/routines';
const T=1_900_000_000; // 2030-03-17 17:46:40 UTC
const routine=(over:Partial<RoutineView>={}):RoutineView=>({kind:'commitment-review',name:'Commitment review',description:'',rules:[],
  default:{schedule:{every_hours:4},interrupt:'show_now'},configured:false,enabled:false,paused:false,version:0,settings:null,next_due:null,runs_today:0,
  quiet_now:false,authority_available:true,...over});
const run=(over:Partial<RunView>={}):RunView=>({id:'r1',kind:'commitment-review',trigger:'manual',started:T,finished:T,status:'completed',skipped_reason:null,
  outcome:{trigger:'manual',missed_slots:0,budget:{runs_today:1,runs_per_day:6,nominations_per_run:3}},...over});
const nomination=(over:Partial<NominationView>={}):NominationView=>({id:'nom-1',version:1,routine:'commitment-review',kind:'reminder',rule:'overdue',
  reason:'Your open commitment is past its due time.',due:T-3600,delivery:'now',surface_at:null,released_by_brief:null,surfaced:true,held:null,state:'open',
  created:T,decided:null,outcome:null,cite:{kind:'record',id:'exec-1',version:2,state:'current',title:'Book the grade'},...over});

describe('routine local time',()=>{
  it('labels fixed offsets and rounds this browser to quarter hours',()=>{
    expect([offsetLabel(0),offsetLabel(60),offsetLabel(-300),offsetLabel(345)]).toEqual(['UTC+00:00','UTC+01:00','UTC-05:00','UTC+05:45']);
    expect(browserOffset({getTimezoneOffset:()=>-67} as Date)).toBe(60);
    expect(OFFSETS[0]).toBe(-720);expect(OFFSETS.at(-1)).toBe(840);expect(OFFSETS.includes(345)).toBe(true);
  });
  it('formats moments in the routine offset, not the browser zone',()=>{
    expect(localClock(T,0)).toBe('17:46');expect(localClock(T,60)).toBe('18:46');
    expect(localMoment(T,-300)).toBe('17 Mar, 12:46');expect(localMoment(null,0)).toBe('No time');
  });
  it('names schedules plainly',()=>{
    expect([scheduleLabel({every_hours:1}),scheduleLabel({every_hours:4}),scheduleLabel({daily_at:'07:30'})]).toEqual(['Every hour','Every 4 hours','Daily at 07:30']);
  });
});

describe('routine settings form',()=>{
  it('starts from the routine defaults and this browser offset when not yet set up',()=>{
    const f=formFromRoutine(routine(),60);
    expect(f).toMatchObject({enabled:true,every:4,offset:60,runsPerDay:6,nominationsPerRun:3,quiet:false,interrupt:'show_now',proposeDrafts:false});
    expect(formFromRoutine(routine({kind:'morning-brief',default:{schedule:{daily_at:'07:30'},interrupt:'show_now'}}),0)).toMatchObject({every:'daily',dailyAt:'07:30',runsPerDay:1});
  });
  it('reads saved settings back exactly',()=>{
    const settings={schedule:{daily_at:'06:45'},utc_offset_minutes:-300,runs_per_day:2,nominations_per_run:5,quiet_hours:{start:'21:00',end:'06:00'},
      interrupt:'hold_for_brief' as const,propose_drafts:true};
    const f=formFromRoutine(routine({configured:true,enabled:false,version:3,settings}),60);
    expect(settingsPayload('commitment-review',f,3)).toEqual({version:3,enabled:false,...settings});
  });
  it('builds the exact server body, and the brief never holds or offers drafts',()=>{
    const f={...formFromRoutine(routine(),0),interrupt:'hold_for_brief' as const,proposeDrafts:true,quiet:false};
    expect(Object.keys(settingsPayload('commitment-review',f,0)).sort()).toEqual(['enabled','interrupt','nominations_per_run','propose_drafts','quiet_hours',
      'runs_per_day','schedule','utc_offset_minutes','version']);
    expect(settingsPayload('morning-brief',f,1)).toMatchObject({interrupt:'show_now',propose_drafts:false,quiet_hours:null,schedule:{every_hours:4}});
  });
  it('explains what must change before saving',()=>{
    const f=formFromRoutine(routine(),0);
    expect(formProblem('commitment-review',f)).toBeNull();
    expect(formProblem('commitment-review',{...f,quiet:true,quietStart:'22:00',quietEnd:'22:00'})).toMatch(/different start and end/);
    expect(formProblem('commitment-review',{...f,runsPerDay:30})).toMatch(/between 1 and 24/);
    expect(formProblem('commitment-review',{...f,nominationsPerRun:0})).toMatch(/between 1 and 10/);
    expect(formProblem('commitment-review',{...f,every:'daily',dailyAt:'7:30'})).toMatch(/time of day/);
    expect(formProblem('morning-brief',{...f,interrupt:'hold_for_brief'})).toMatch(/morning brief/);
  });
});

describe('routine outcomes',()=>{
  it('says why a run was skipped',()=>{
    expect(runSummary(run({status:'skipped',skipped_reason:'paused'}))).toBe('Skipped · This routine was paused.');
    expect(runSummary(run({status:'skipped',skipped_reason:'workspace_paused'}))).toBe('Skipped · The workspace was paused.');
    expect(runSummary(run({status:'skipped',skipped_reason:'budget_exhausted'}))).toMatch(/run budget/);
    expect(runSummary(run({status:'skipped',skipped_reason:'authority_lost'}))).toMatch(/^Skipped · Authority lost/);
    expect(runSummary(run({status:'failed',outcome:{...run().outcome,error:'routine_failed'}}))).toMatch(/nothing from this run was kept/);
  });
  it('summarises nominations, holds and items not nominated',()=>{
    expect(runSummary(run({outcome:{...run().outcome,nothing_due:true,nominated:[]}}))).toBe('Completed · nothing due');
    const cite={kind:'record' as const,id:'exec-1',version:1};
    expect(runSummary(run({outcome:{...run().outcome,nothing_due:false,nominated:[{nomination:'n',kind:'reminder',rule:'overdue',delivery:'quiet_hours',cite}],
      held:{quiet_hours:1,next_brief:0},not_nominated:{already_nominated:2,nomination_budget:0,snoozed:1}}}))).toBe('Completed · 1 nomination · 1 held · 2 already nominated · 1 snoozed by you');
    expect(runSummary(run({kind:'morning-brief',outcome:{...run().outcome,read:{attention_items:3,insights:1,pending_approvals:0},released:['a']}})))
      .toBe('Brief assembled · 3 attention items · 1 insight · 0 pending approvals · 1 held released');
    expect(readLine({executive_records:4,commitment_statements:0,undated_statements:1})).toBe('4 open commitments and follow-ups · 1 undated statement');
  });
});

describe('nominations',()=>{
  it('never shows a title or value for something no longer readable',()=>{
    expect(citeLabel({...nomination().cite})).toBe('Book the grade · version 2');
    expect(citeLabel({kind:'statement',version:2,state:'unavailable'})).toBe('No longer available to you');
    expect(citeLabel({kind:'record',version:1,state:'changed',title:'Book the grade',current_version:2})).toBe('Book the grade · version 1 · changed since (now version 2)');
    expect(citeLabel({kind:'statement',version:2,state:'current',subject:{id:'a',kind:'project',name:'Atlas'},predicate:'scheduled_for',value:'2030-03-17'}))
      .toBe('Atlas: scheduled for 2030-03-17 · version 2');
    expect(sourceLabel({state:'current',source:{note_id:'n',path:'Atlas.md',title:'Atlas',revision:3,start_line:7,end_line:7}})).toBe('Atlas.md, line 7, revision 3');
    expect(sourceLabel({state:'unavailable'})).toBeNull();
  });
  it('names the kind, rule and due time without repeating a draft offer',()=>{
    expect(nominationLine(nomination(),0)).toBe('Reminder · Overdue · 17 Mar, 16:46');
    expect(nominationLine(nomination({kind:'draft',rule:'draft_offer'}),0)).toBe('Draft offer · 17 Mar, 16:46');
  });
  it('labels holds and decisions',()=>{
    expect(holdLabel(nomination({held:'next_brief',surfaced:false}),0)).toBe('Held for the next morning brief');
    expect(holdLabel(nomination({held:'quiet_hours',surfaced:false,surface_at:T}),60)).toBe('Held for quiet hours until 17 Mar, 18:46');
    expect(holdLabel(nomination(),0)).toBeNull();
    expect([decisionLabel(nomination({state:'dismissed'})),decisionLabel(nomination({state:'accepted',outcome:{action:'routine-nom-1'}})),
      decisionLabel(nomination({state:'accepted',outcome:{follow_up:'exec-2'}})),decisionLabel(nomination({state:'accepted',outcome:{follow_up:null}}))])
      .toEqual(['Dismissed','Accepted · draft proposed for your approval','Accepted · follow-up added','Accepted']);
  });
  it('turns server refusals into plain words',()=>{
    expect(routineMessage(new DeskError('conflict','nomination_source_changed',409))).toMatch(/can only be dismissed/);
    expect(routineMessage(new DeskError('denied','routine_owner_not_hosted',403))).toMatch(/key this ALFRED host was started with/);
    expect(routineMessage(new DeskError('rejected','something_new',400))).toBe('ALFRED refused this (something_new).');
    expect(routineMessage(new Error('x'))).toBe('ALFRED could not be reached.');
  });
});

describe('routines command',()=>{
  it('opens the routines panel from the command bar, never anything else',()=>{
    expect(parseCommand('routines')).toEqual({kind:'dialog',dialog:'routines'});
    expect(parseCommand('/routines')).toEqual({kind:'dialog',dialog:'routines'});
    expect(parseCommand('run routines now')).toEqual({kind:'search',query:'run routines now'});
  });
});
