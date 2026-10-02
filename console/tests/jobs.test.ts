import {describe,it,expect} from 'vitest';
import {eventLabel,jobError,mergeEvents,readResult,reasonLabel,requestKey,stateLabel,JOB_KINDS,type JobEvent} from '../src/integration/jobs';
import {parseCommand} from '../src/domain/commands';
const ev=(sequence:number,kind='submitted',detail:Record<string,unknown>={}):JobEvent=>({sequence,kind,detail,at:1_000+sequence});
describe('bounded jobs in the console',()=>{
  it('merges event pages by sequence without duplicates or gaps being invented',()=>{
    const merged=mergeEvents([ev(1),ev(2,'leased')],[ev(2,'leased'),ev(4,'succeeded'),ev(3,'started')]);
    expect(merged.map(e=>e.sequence)).toEqual([1,2,3,4]);
    expect(mergeEvents([],[])).toEqual([]);
  });
  it('reads a word count as a count, not an interpretation',()=>{
    const r=readResult(JSON.stringify({kind:'word_count',basis:'deterministic_count_not_interpretation',inputs:[],total:{bytes:1200,lines:12,words:180}}));
    expect(r?.lines).toEqual([{label:'Words',value:'180'},{label:'Lines',value:'12'},{label:'Bytes',value:'1,200'}]);
    expect(r?.basis).toMatch(/not an interpretation/);
  });
  it('shows extracted lines exactly and labels them as not a model summary',()=>{
    const r=readResult(JSON.stringify({kind:'summarise_lines',basis:'extractive_first_lines_not_model_summary',inputs:[{lines:9,selected:['# Title','<script>x</script>']}]}));
    expect(r?.selected).toEqual(['# Title','<script>x</script>']);
    expect(r?.basis).toMatch(/not a model summary/);
  });
  it('never guesses at malformed or unknown results',()=>{
    expect(readResult('not json')).toBeNull();
    expect(readResult(undefined)).toBeNull();
    expect(readResult(JSON.stringify({kind:'other'}))?.lines[0].value).toMatch(/unrecognised/);
  });
  it('explains refusals and states in plain words',()=>{
    expect(reasonLabel('inputs_changed')).toMatch(/changed after the job was submitted/);
    expect(eventLabel(ev(2,'dispatch_denied',{reason:'inputs_denied'}))).toBe('Refused before running. An input is no longer permitted or available.');
    expect(stateLabel('effect_unknown')).toMatch(/needs your check/);
    expect(jobError('input_revision_changed')).toMatch(/Reopen it/);
    expect(jobError('something_new')).toBe('ALFRED refused this (something_new).');
  });
  it('offers only first-party kinds a person would choose, never the timed test kind',()=>{
    expect(JOB_KINDS.map(k=>k.id)).toEqual(['word_count','summarise_lines']);
  });
  it('creates request keys the server accepts as identifiers',()=>{
    const key=requestKey();expect(key).toMatch(/^console-[A-Za-z0-9_.-]{1,72}$/);expect(key.length).toBeLessThanOrEqual(80);expect(requestKey()).not.toBe(key);
  });
  it('opens the jobs panel from the command bar',()=>{
    expect(parseCommand('jobs',[])).toEqual({kind:'dialog',dialog:'jobs'});
    expect(parseCommand('/jobs',[])).toEqual({kind:'dialog',dialog:'jobs'});
  });
});
