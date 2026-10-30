import {describe,it,expect} from 'vitest';
import {type BinItem,BIN_ERRORS,binLabel,daysLeft,undoNotice} from '../src/domain/bin';

const DAY=86400;
const item=(over:Partial<BinItem>={}):BinItem=>({id:'bin-1',kind:'statement',subject:'claim-1',deleted:1000,expires:1000+30*DAY,
  label:{subject:'Atlas',predicate:'responsible_person',value:null,object:'Mina'},...over});

describe('the bin',()=>{
  it('names a statement by its record, kind and value or the record it points to',()=>{
    expect(binLabel(item())).toBe('Atlas · responsible person · Mina');
    expect(binLabel(item({label:{subject:'Atlas',predicate:'status',value:'awaiting review',object:null}}))).toBe('Atlas · status · awaiting review');
    expect(binLabel(item({label:{subject:null,predicate:null,value:null,object:null}}))).toBe('A record · statement');
  });
  it('names a record with how many statements come back with it',()=>{
    expect(binLabel(item({kind:'entity',subject:'mina',label:{name:'Mina',kind:'person',statements:1}}))).toBe('Mina and 1 statement');
    expect(binLabel(item({kind:'entity',subject:'atlas',label:{name:'Atlas',kind:'project',statements:3}}))).toBe('Atlas and 3 statements');
    expect(binLabel(item({kind:'entity',subject:'film',label:{name:null,kind:null,statements:0}}))).toBe('film');
  });
  it('counts whole days left to undo, rounding up and never below none',()=>{
    expect(daysLeft(item(),1000)).toBe(30);
    expect(daysLeft(item(),1000+29*DAY+1)).toBe(1);
    expect(daysLeft(item(),1000+30*DAY)).toBe(0);
    expect(daysLeft(item(),1000+40*DAY)).toBe(0);
  });
  it('says what came back and what an undo cannot put back',()=>{
    const r={kind:'statement' as const,subject:'claim-1',statements_restored:1,statements_not_restored:0,
      not_restored:['Saved answers and drafts the forget withdrew stay withdrawn; ask again for a fresh answer.']};
    expect(undoNotice(item(),r)).toBe('Put back Atlas · responsible person · Mina. Saved answers and drafts the forget withdrew stay withdrawn; ask again for a fresh answer.');
  });
  it('explains every refusal an undo can meet',()=>{
    for(const code of ['not_in_bin','undo_record_first','memory_entity_id_unavailable','memory_entity_capacity'])expect(BIN_ERRORS[code]).toBeTruthy();
  });
});
