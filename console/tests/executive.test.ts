import {describe,it,expect} from 'vitest';
import {toSnapshot} from '../src/integration/toSnapshot';
import {type ConnectedProjection} from '../src/integration/ConsoleReadPort';
import {DeskClient} from '../src/integration/deskClient';
import {ALL,UNASSIGNED,citeLabel,filterByResponsible,fromDateInput,groupRecords,hiddenSummary,optionDrafts,optionsPayload,responsibleChoices,responsibleKey,toDateInput,
  type ExecRecordView,type ResponsibleGroup} from '../src/domain/executive';
const node=(id:string,over:Partial<ConnectedProjection['nodes'][number]>={})=>({id,label:id,type:'action' as const,workspaceId:'w1',evidence:[],...over});
const projection=():ConnectedProjection=>({kind:'authorised_projection',schemaVersion:1,workspaceId:'w1',dataRevision:'d1',grantRevision:'g1',observedAt:'2026-10-02T10:00:00Z',
  nodes:[node('exec:exec-a',{label:'Send the budget',kind:'commitment',category:'operations',origin:'executive_record',responsible:'Finance lead',due:100}),
    node('exec:exec-b',{label:'Choose the date',kind:'decision',category:'operations',origin:'executive_record'}),
    node('note:aaaaaaaaaaaaaaaaaaaaaaaa',{label:'Morgan',type:'person',kind:'person',category:'people',origin:'authored_note'})],
  edges:[{id:'execresp:exec-a',from:'exec:exec-a',to:'note:aaaaaaaaaaaaaaaaaaaaaaaa',layer:'executive_responsible',relation:'responsible',
    evidence:[{sourceId:'exec:exec-a',revision:'1',location:{kind:'record'},basis:'authored',availability:'current'}]}],
  executive:{priorities:[{id:'exec:exec-p',title:'Top',status:'open',open:true,due:null,overdue:false,rank:1,version:2,origin:'user_authored',responsible:'Ops'}],
    prioritiesStatus:'recorded',milestonesStatus:'not_recorded',insights:[],
    attention:[{recordId:'exec:exec-a',title:'Send the budget',kind:'commitment',rules:['due_soon'],reason:'Due within seven days',due:100,responsible:'Finance lead'},
      {recordId:'exec:exec-gone',title:'Not projected',kind:'commitment',rules:['overdue'],reason:'Past its due date',due:1,responsible:null}],
    attentionCount:2,snoozedCount:1,
    derivedInsights:[{rule:'top_priorities_deadline_clash',statement:'Two top priorities clash.',recordIds:['exec:exec-a','exec:exec-gone'],basis:'derived_from_your_records_not_accepted_fact'},
      {rule:'commitments_without_milestone',statement:'Only unprojected records.',recordIds:['exec:exec-gone'],basis:'derived_from_your_records_not_accepted_fact'}]}});
const record=(id:string,over:Partial<ExecRecordView>={}):ExecRecordView=>({id,kind:'commitment',title:id,detail:'',status:'open',open:true,project:null,due:null,overdue:false,rank:null,version:1,
  created:0,updated:0,project_state:null,project_name:null,responsible:null,responsible_link:null,responsible_state:null,responsible_name:null,snoozed_until:null,snoozed:false,...over});
describe('connected executive mapping',()=>{
  it('maps attention and derived insights only for projected records',()=>{
    const s=toSnapshot(projection(),'w1');
    expect(s.attention?.map(a=>a.recordId)).toEqual(['exec:exec-a']);
    expect((s.attentionCount??0)+(s.snoozedCount??0)).toBe(3);
    expect(s.derivedInsights).toEqual([{rule:'top_priorities_deadline_clash',statement:'Two top priorities clash.',recordIds:['exec:exec-a']}]);
  });
  it('keeps the responsible label as the person wrote it',()=>{
    const s=toSnapshot(projection(),'w1');
    expect(s.records.find(r=>r.id==='exec:exec-a')?.responsible).toBe('Finance lead');
    expect(s.priorities[0].responsible).toBe('Ops');
  });
  it('labels an explicitly picked responsible link as authored, not reviewed',()=>{
    const edge=toSnapshot(projection(),'w1').relationships.find(e=>e.layer==='executive_responsible');
    expect(edge).toMatchObject({from:'exec:exec-a',to:'note:aaaaaaaaaaaaaaaaaaaaaaaa',basis:'authored'});
  });
});
describe('responsible labels',()=>{
  const groups:ResponsibleGroup[]=[{label:'Morgan',link:'note:n1',link_state:'current',link_name:'Morgan',records:['n'],open:1,overdue:0},
    {label:'Morgan',link:'entity:m1',link_state:'current',link_name:'Morgan',records:['a'],open:1,overdue:0},
    {label:'Morgan',link:'entity:m2',link_state:'unavailable',link_name:null,records:['b'],open:1,overdue:0},
    {label:'Morgan',link:null,link_state:null,link_name:null,records:['c'],open:1,overdue:0}];
  it('never gives namesakes or different spellings the same key',()=>{
    const keys=[responsibleKey('Morgan','entity:m1'),responsibleKey('Morgan','entity:m2'),responsibleKey('Morgan',null),responsibleKey('morgan',null),responsibleKey(null,null)];
    expect(new Set(keys).size).toBe(5);
    expect(responsibleKey(null,null)).toBe(UNASSIGNED);
  });
  it('lists each label and link as its own filter choice',()=>{
    expect(responsibleChoices(groups,2).map(c=>c.label)).toEqual(['Everyone','Morgan · linked to Morgan','Morgan · linked to Morgan (reviewed)','Morgan · link unavailable','Morgan','No responsible label']);
    expect(responsibleChoices(groups,0).some(c=>c.key===UNASSIGNED)).toBe(false);
  });
  it('filters by the exact label and link',()=>{
    const rs=[record('a',{responsible:'Morgan',responsible_link:'entity:m1'}),record('b',{responsible:'Morgan',responsible_link:'entity:m2'}),record('c',{responsible:'Morgan'}),record('d')];
    expect(filterByResponsible(rs,responsibleKey('Morgan','entity:m1')).map(r=>r.id)).toEqual(['a']);
    expect(filterByResponsible(rs,UNASSIGNED).map(r=>r.id)).toEqual(['d']);
    expect(filterByResponsible(rs,ALL)).toHaveLength(4);
  });
  it('groups by kind in a fixed order and by responsible with the unassigned last',()=>{
    const rs=[record('m',{kind:'milestone'}),record('p',{kind:'priority',responsible:'Zed'}),record('d',{kind:'decision',responsible:'Ana'})];
    expect(groupRecords(rs,'kind').map(g=>[g.heading,g.items.map(r=>r.id)])).toEqual([['Priorities',['p']],['Commitments and follow-ups',[]],['Decisions',['d']],['Milestones',['m']],['Goals',[]]]);
    expect(groupRecords(rs,'responsible').map(g=>g.heading)).toEqual(['Ana','Zed','No responsible label']);
  });
});
describe('decision options',()=>{
  it('starts with two empty drafts and keeps authored order',()=>{
    expect(optionDrafts(undefined)).toHaveLength(2);
    expect(optionDrafts([{id:'o1',label:'B',notes:'',pros:['x'],cons:[]},{id:'o2',label:'A',notes:'n',pros:[],cons:['y','z']}]).map(d=>[d.label,d.pros,d.cons])).toEqual([['B','x',''],['A','','y\nz']]);
  });
  it('builds a payload without scores and mirrors the server limits',()=>{
    const ok=optionsPayload([{label:'  Hire  now ',notes:' Fast ',pros:'Quick\n\n start ',cons:''},{label:'Wait',notes:'',pros:'',cons:'Slow'}]);
    expect(ok).toEqual({options:[{label:'Hire now',notes:'Fast',pros:['Quick','start'],cons:[]},{label:'Wait',notes:'',pros:[],cons:['Slow']}]});
    expect(optionsPayload([{label:'Only',notes:'',pros:'',cons:''}])).toEqual({error:'A decision needs two to six options.'});
    expect(optionsPayload([{label:'Same',notes:'',pros:'',cons:''},{label:'same',notes:'',pros:'',cons:''}])).toEqual({error:'Each option needs a different name.'});
    expect(optionsPayload([{label:'',notes:'',pros:'',cons:''},{label:'B',notes:'',pros:'',cons:''}])).toEqual({error:'Give every option a name.'});
    expect(optionsPayload([{label:'A',notes:'',pros:'1\n2\n3\n4\n5',cons:''},{label:'B',notes:'',pros:'',cons:''}])).toEqual({error:'Up to four pros and four cons per option.'});
  });
});
describe('dates, citations and counts',()=>{
  it('round-trips a day through the stored 17:00 local time',()=>{
    const t=fromDateInput('2026-10-09');
    expect(t).not.toBeNull();expect(new Date(t!*1000).getHours()).toBe(17);expect(toDateInput(t)).toBe('2026-10-09');
    expect(fromDateInput('9 Oct')).toBeNull();expect(toDateInput(null)).toBe('');
  });
  it('names exactly what each item cites',()=>{
    expect(citeLabel({record:'exec-a',version:3})).toBe('Your record v3');
    expect(citeLabel({note:'n1',revision:2,lines:[7,7]})).toBe('Note revision 2, line 7');
    expect(citeLabel({claim:'c1',version:2,note:'n1',revision:4,lines:[7,8]})).toBe('Reviewed statement v2 · note revision 4, lines 7 to 8');
    expect(citeLabel(undefined)).toBe('');
  });
  it('summarises statements that are counted but never shown',()=>{
    expect(hiddenSummary({withheld:2,needing_fresh_review:1,awaiting_review:0})).toBe('2 withheld, 1 needing fresh review');
    expect(hiddenSummary({withheld:0})).toBe('');
  });
});
describe('record inspection transport',()=>{
  it('allows executive record identifiers and still refuses anything else',async()=>{
    const calls:string[]=[];
    const fetcher=(async(url:string)=>{calls.push(url);return new Response(JSON.stringify({id:'exec:exec-a',type:'exec'}),{status:200});}) as unknown as typeof fetch;
    const client=new DeskClient('',fetcher),signal=new AbortController().signal;
    await expect(client.inspectRecord('exec:exec-a',signal)).resolves.toMatchObject({type:'exec'});
    await expect(client.inspectRecord('exec:../x',signal)).rejects.toMatchObject({code:'record_not_available'});
    await expect(client.inspectRecord('claim:c1',signal)).rejects.toMatchObject({code:'record_not_available'});
    expect(calls).toEqual(['/desk/console/records/exec:exec-a']);
  });
});
