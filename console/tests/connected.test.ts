import {describe,it,expect} from 'vitest';
import {toSnapshot,emptyConnectedSnapshot} from '../src/integration/toSnapshot';
import {type ConnectedProjection} from '../src/integration/ConsoleReadPort';
import {initialState,reducer} from '../src/domain/model';
import {parseCommand} from '../src/domain/commands';
import {errorKind} from '../src/integration/deskClient';
import {consoleMode} from '../src/integration/mode';
const projection=(over:Partial<ConnectedProjection>={}):ConnectedProjection=>({kind:'authorised_projection',schemaVersion:1,workspaceId:'w1',dataRevision:'d1',grantRevision:'g1',observedAt:'2026-10-02T10:00:00Z',
  nodes:[{id:'note:aaaaaaaaaaaaaaaaaaaaaaaa',label:'Atlas',type:'project',kind:'project',category:'projects',origin:'authored_note',workspaceId:'w1',summary:'Plan',path:'Atlas.md',revision:'2',sha256:'f'.repeat(64),evidence:[{sourceId:'note:aaaaaaaaaaaaaaaaaaaaaaaa',revision:'2',location:{kind:'lines',start:1,end:3},basis:'authored',availability:'current'}]},
    {id:'entity:atlas',label:'Atlas',type:'project',kind:'project',category:'projects',origin:'reviewed_entity',workspaceId:'w1',evidence:[]}],
  edges:[{id:'support:1',from:'entity:atlas',to:'note:aaaaaaaaaaaaaaaaaaaaaaaa',layer:'review_support',relation:'supported_by',evidence:[{sourceId:'note:aaaaaaaaaaaaaaaaaaaaaaaa',revision:'2',location:{kind:'lines',start:2,end:2},basis:'human_review',availability:'current'}]}],
  approvals:[{id:'a1',capability:'message.draft',state:'proposed',text:'Exact text',fingerprint:'0'.repeat(64),createdAt:'',expiresAt:'',evidenceCurrent:true,mine:true,effect:'local_draft_only_not_sent'},
    {id:'a2',capability:'message.draft',state:'verified',text:'Done',fingerprint:'1'.repeat(64),createdAt:'',expiresAt:'',evidenceCurrent:true,mine:true,effect:'local_draft_only_not_sent'}],
  executive:{priorities:[],prioritiesStatus:'not_recorded',milestonesStatus:'not_recorded',insights:[{entityId:'entity:atlas',claimId:'c1',predicate:'status',value:'planning',objectId:null,reviewedAt:'',supportId:'note:aaaaaaaaaaaaaaaaaaaaaaaa',basis:'x'}]},
  ...over});
describe('connected projection mapping',()=>{
  it('maps server nodes without inventing records',()=>{const s=toSnapshot(projection(),'w1');expect(s.mode).toBe('connected');expect(s.records.map(r=>r.id)).toEqual(['note:aaaaaaaaaaaaaaaaaaaaaaaa','entity:atlas']);expect(s.priorities).toEqual([]);});
  it('keeps same-name records distinct',()=>{const s=toSnapshot(projection(),'w1');expect(s.records.filter(r=>r.title==='Atlas')).toHaveLength(2);});
  it('labels edge layers by basis',()=>{const s=toSnapshot(projection(),'w1');expect(s.relationships[0]).toMatchObject({layer:'review_support',basis:'human_review'});});
  it('maps server action states and never local demo effects',()=>{const s=toSnapshot(projection(),'w1');expect(s.proposals.map(p=>[p.status,p.effect])).toEqual([['pending','server_action'],['completed','server_action']]);});
  it('derives insights only from projected records',()=>{expect(toSnapshot(projection(),'w1').insights?.[0].summary).toBe('status: planning');const p=projection();p.executive!.insights[0].entityId='entity:missing';expect(toSnapshot(p,'w1').insights).toEqual([]);});
  it('rejects a projection for another workspace',()=>expect(()=>toSnapshot(projection(),'w2')).toThrow());
  it('rejects out-of-scope nodes',()=>{const p=projection();p.nodes[1].workspaceId='w2';expect(()=>toSnapshot(p,'w1')).toThrow();});
  it('starts connected mode empty, never with fixtures',()=>{const s=emptyConnectedSnapshot();expect(s.records).toEqual([]);expect(s.mode).toBe('connected');});
});
describe('connected reducer',()=>{
  const ready=()=>reducer(initialState(emptyConnectedSnapshot()),{type:'projection',snapshot:toSnapshot(projection(),'w1')});
  it('adopts the server workspace as scope',()=>expect(ready().scope).toBe('w1'));
  it('keeps a selection that is still permitted',()=>{const s=reducer(ready(),{type:'select',id:'entity:atlas'});expect(reducer(s,{type:'projection',snapshot:toSnapshot(projection({dataRevision:'d2'}),'w1')}).selected).toBe('entity:atlas');});
  it('clears a selection whose record disappeared',()=>{const s=reducer(ready(),{type:'select',id:'entity:atlas'});const p=projection({dataRevision:'d2'});p.nodes=p.nodes.slice(0,1);p.edges=[];p.executive!.insights=[];expect(reducer(s,{type:'projection',snapshot:toSnapshot(p,'w1')}).selected).toBeNull();});
  it('clears selection when the grant revision changes',()=>{const s=reducer(ready(),{type:'select',id:'entity:atlas'});expect(reducer(s,{type:'projection',snapshot:toSnapshot(projection({grantRevision:'g2'}),'w1')}).selected).toBeNull();});
  it('cannot select an unknown record',()=>expect(reducer(ready(),{type:'select',id:'note:other'}).selected).toBeNull());
  it('ignores demo review actions on server proposals',()=>{const s=ready();expect(reducer(s,{type:'review',id:'a1',revision:1,outcome:'reviewed',at:'x'})).toBe(s);});
});
describe('connected command and transport rules',()=>{
  it('does not treat fixture scope names as commands when connected',()=>expect(parseCommand('work',[])).toEqual({kind:'search',query:'work'}));
  it('still routes scope commands in the demo',()=>expect(parseCommand('work')).toEqual({kind:'scope',scope:'work'}));
  it('maps HTTP status to honest states',()=>expect([401,403,404,409,500,0,400].map(errorKind)).toEqual(['signed_out','denied','not_found','conflict','unavailable','unavailable','rejected']));
  it('defaults to the demonstration unless the server marks the page',()=>{
    const doc=(content:string|null)=>({querySelector:()=>content===null?null:{getAttribute:()=>content}}) as unknown as Document;
    expect([consoleMode(doc(null)),consoleMode(doc('demo')),consoleMode(doc('Connected')),consoleMode(doc('connected'))]).toEqual(['demo','demo','demo','connected']);
  });
});
