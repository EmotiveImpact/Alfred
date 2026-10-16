import {describe,it,expect} from 'vitest';
import {grantRequest,holds,others,type PeopleView} from '../src/integration/people';

const view:PeopleView={epoch:4,mode:'explicit_grants',shareable:['model','read'],people:[
  {person_id:'person-'+'a'.repeat(24),you:true,label:'You',roles:['owner'],devices:2,grants:[{source:'demo-source',capability:'read',expires:9}]},
  {person_id:'person-'+'b'.repeat(24),you:false,label:'Fictional producer',roles:['reader'],devices:1,grants:[{source:'demo-source',capability:'read',expires:9}]},
  {person_id:'person-'+'c'.repeat(24),you:false,label:'Unnamed person',roles:['reader'],devices:1,grants:[]},
]};

describe('people administration requests',()=>{
  it('lists everyone except the signed-in person',()=>{
    expect(others(view).map(p=>p.label)).toEqual(['Fictional producer','Unnamed person']);
  });
  it('turns a held grant off and a missing grant on, with the current epoch',()=>{
    const[producer,unnamed]=others(view);
    expect(holds(producer,'demo-source','read')).toBe(true);
    expect(grantRequest(producer,'demo-source','read',view.epoch)).toEqual({path:`/desk/identity/people/${producer.person_id}/grants`,
      body:{source:'demo-source',capability:'read',days:30,epoch:4,revoke:true}});
    expect(grantRequest(unnamed,'demo-source','model',view.epoch).body.revoke).toBe(false);
  });
  it('refuses a person identifier the server would not have sent',()=>{
    expect(()=>grantRequest({...view.people[1],person_id:'../owner'},'demo-source','read',4)).toThrow('invalid_person');
  });
});
