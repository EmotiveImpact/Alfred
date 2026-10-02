import {describe,it,expect} from 'vitest';
import {type MemoryClaim,type HistoryEntry,acceptedSince,asOfPath,claimValue,dayEnd,dayStart,entityLabel,historyLine,namesakeIds,notHeldSummary,
  reviewBody,reviewQueue,supersedeCandidates,toDayInput,validPeriodLabel,validPeriodPayload,valueText} from '../src/domain/temporal';
import {parseCommand} from '../src/domain/commands';
import {detailValue} from '../src/components/StatementHistory';

const claim=(id:string,over:Partial<MemoryClaim>={}):MemoryClaim=>({id,subject_id:'atlas',predicate:'status',object_id:null,value:'planning',valid_from:null,valid_until:null,
  state:'proposed',version:1,created:100,reviewed:null,replaces_id:null,source:{note_id:'n1',path:'Atlas.md',title:'Atlas',start_line:2,end_line:2,quote:'Atlas is planning.'},
  valid_now:true,conflicts:[],usable:false,withheld:false,memory_type:null,retention_until:null,...over});
const entry=(over:Partial<HistoryEntry>):HistoryEntry=>({seq:1,state:'accepted',at:1_790_000_000,time_known:true,by:'you',origin:'recorded',related_id:null,detail:null,valid_period:null,...over});

describe('review queue',()=>{
  it('lists proposals and disputes oldest first and nothing else',()=>{
    const q=reviewQueue([claim('c3',{created:300}),claim('c1',{created:100}),claim('c2',{state:'disputed',created:50}),claim('c4',{state:'accepted'})]);
    expect(q.proposed.map(c=>c.id)).toEqual(['c1','c3']);expect(q.disputed.map(c=>c.id)).toEqual(['c2']);
  });
  it('offers to replace only the same record and kind of statement, never a namesake',()=>{
    const all=[claim('new'),claim('same',{state:'accepted',reviewed:5}),claim('older',{state:'invalidated',reviewed:2}),claim('namesake',{state:'accepted',subject_id:'atlas-two'}),
      claim('other-kind',{state:'accepted',predicate:'decision'}),claim('withdrawn',{state:'withdrawn'}),claim('pending')];
    expect(supersedeCandidates(all[0],all).map(c=>c.id)).toEqual(['same','older']);
    expect(supersedeCandidates(claim('x',{replaces_id:'same'}),all)).toEqual([]);
  });
  it('sends the exact version, and a valid period only when a proposal changes it',()=>{
    const c=claim('c1',{version:3});
    expect(reviewBody(c,'accept',null,{valid_from:null,valid_until:null})).toEqual({version:3,decision:'accept',replaces_id:null,replaces_version:null});
    expect(reviewBody(c,'accept',null,{valid_from:10,valid_until:null})).toEqual({version:3,decision:'accept',replaces_id:null,replaces_version:null,valid_from:10,valid_until:null});
    expect(reviewBody(c,'supersede',claim('p',{version:7,state:'accepted'}),null)).toEqual({version:3,decision:'supersede',replaces_id:'p',replaces_version:7});
    expect(reviewBody(c,'dispute',null,{valid_from:10,valid_until:null})).toEqual({version:3,decision:'dispute',replaces_id:null,replaces_version:null});
    expect(reviewBody(claim('d',{state:'disputed'}),'accept',null,{valid_from:10,valid_until:null})).not.toHaveProperty('valid_from');
  });
});

describe('valid time',()=>{
  it('reads whole days and mirrors the server rule',()=>{
    expect(validPeriodPayload('','')).toEqual({valid_from:null,valid_until:null});
    const ok=validPeriodPayload('2026-09-01','2026-10-01') as {valid_from:number;valid_until:number};
    expect(ok.valid_until-ok.valid_from).toBeGreaterThan(29*86400);
    expect(validPeriodPayload('2026-10-01','2026-10-01')).toHaveProperty('error');
    expect(validPeriodPayload('2026-10-02','2026-10-01')).toHaveProperty('error');
    expect(validPeriodPayload('soon','')).toHaveProperty('error');
    expect(toDayInput(dayStart('2026-09-15'))).toBe('2026-09-15');
  });
  it('takes the end of a chosen day, never a moment that has not happened',()=>{
    const start=dayStart('2026-09-15')!;
    expect(dayEnd('2026-09-15',start+10*86400)).toBe(start+86399);
    expect(dayEnd('2026-09-15',start+60)).toBe(start+60);
    expect(dayEnd('',1)).toBeNull();
    expect(asOfPath(5.7,null)).toBe('/desk/memory/as-of/5');expect(asOfPath(5,9)).toBe('/desk/memory/as-of/5/valid/9');
  });
  it('labels periods in plain words',()=>{
    expect(validPeriodLabel(null,null)).toBe('No valid period set');
    expect(validPeriodLabel(dayStart('2026-09-01'),null)).toMatch(/^Holds from 1 Sept? 2026$/);
    expect(validPeriodLabel(null,dayStart('2026-10-01'))).toBe('Holds until the start of 1 Oct 2026');
  });
});

describe('values and namesakes',()=>{
  const entities=[{id:'mina',kind:'person',name:'Mina'},{id:'mina-two',kind:'person',name:'mina'},{id:'atlas',kind:'project',name:'Atlas'},{id:'mina-org',kind:'organisation',name:'Mina'}];
  it('tells same-name records apart by kind and identifier and never merges them',()=>{
    const shared=namesakeIds(entities);
    expect([...shared].sort()).toEqual(['mina','mina-two']);
    expect(entityLabel(entities[0],shared)).toBe('Mina (person, record mina)');
    expect(entityLabel(entities[3],shared)).toBe('Mina (organisation)');
    expect(entityLabel(null,shared)).toBe('A record you forgot');
  });
  it('names a hidden value as hidden and never shows it',()=>{
    expect(valueText({value:null,object:null,value_hidden:'withheld'})).toMatch(/withheld/);
    expect(valueText({value:'secret',object:null,value_hidden:'forgotten'})).not.toContain('secret');
    const byId=Object.fromEntries(entities.map(e=>[e.id,e]));
    expect(claimValue(claim('c',{state:'invalidated',value:null}),byId,new Set())).toMatch(/support changed/);
    expect(claimValue(claim('c',{value:null,object_id:'mina',predicate:'responsible_person'}),byId,namesakeIds(entities))).toBe('Mina (person, record mina)');
    expect(detailValue({state:'accepted',withheld:true,value:null,object:null})).toMatch(/withheld/);
    expect(detailValue({state:'superseded',withheld:false,value:'planning',object:null})).toBe('planning');
  });
});

describe('recorded history wording',()=>{
  it('says who made each change and how ALFRED knows',()=>{
    expect(historyLine(entry({})).who).toBe('by you');
    const observed=historyLine(entry({state:'withheld',by:'alfred',origin:'observed',detail:'support_unavailable_or_not_permitted'}));
    expect([observed.label,observed.who]).toEqual(['Support unavailable or not permitted','by ALFRED']);expect(observed.notes).toContain('noticed by ALFRED');
    const migrated=historyLine(entry({time_known:false,origin:'migrated',detail:'state_found_at_migration'}));
    expect(migrated.when).toMatch(/^no later than .*exact time not known/);expect(migrated.notes).toContain('reconstructed from earlier records');
    expect(historyLine(entry({state:'forgotten',origin:'replayed'})).notes).toContain('replayed from the journal');
    expect(historyLine(entry({state:'proposed',valid_period:{from:null,until:null}})).notes).toBe('No valid period set');
  });
  it('summarises an as-of report without inventing states',()=>{
    expect(acceptedSince({since:null,since_known:true})).toBe('');
    expect(acceptedSince({since:1_790_000_000,since_known:false})).toMatch(/^Accepted no later than .*reconstructed/);
    expect(notHeldSummary({not_held:{proposed:1,disputed:0,superseded:2},not_yet_recorded:3,without_history:0})).toBe('1 proposed, 2 superseded, 3 recorded later');
  });
  it('opens reviewed memory from the command bar',()=>{
    expect(['memory','/memory','statements','Review memory'].map(t=>parseCommand(t,[]))).toEqual(Array(4).fill({kind:'dialog',dialog:'memory'}));
  });
});
