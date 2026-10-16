import {describe,it,expect} from 'vitest';
import {DeskError} from '../src/integration/deskClient';
import {canArchive,canRepropose,draftMessage,draftStatusLabel,draftsPath,type DraftView} from '../src/integration/drafts';
import {toSnapshot} from '../src/integration/toSnapshot';
import {type ConnectedProjection,type ServerApproval} from '../src/integration/ConsoleReadPort';
const draft=(over:Partial<DraftView>={}):DraftView=>({id:'d1',capability:'message.draft',status:'lapsed',ledger_state:'proposed',archived:false,version:1,
  text:'Sample draft',path:null,created_at:1_900_000_000,approval_expires_at:1_900_000_900,approval_lapsed:true,withdrawn:null,reproposed_from:null,reproposed_as:[],origin:'evidence',...over});
const approval=(over:Partial<ServerApproval>):ServerApproval=>({id:'a',capability:'message.draft',state:'proposed',text:'x',fingerprint:'0'.repeat(64),createdAt:'',expiresAt:'',
  evidenceCurrent:true,mine:true,effect:'local_draft_only_not_sent',...over});
const projection=(approvals:ServerApproval[]):ConnectedProjection=>({kind:'authorised_projection',schemaVersion:1,workspaceId:'w1',dataRevision:'d',grantRevision:'g',
  observedAt:'2030-03-17T00:00:00Z',nodes:[],edges:[],approvals});

describe('kept drafts',()=>{
  it('builds only the query fields the server accepts',()=>{
    expect(draftsPath('current')).toBe('/desk/drafts');
    expect(draftsPath('lapsed')).toBe('/desk/drafts?status=lapsed');
    expect(draftsPath('archived',' budget ')).toBe('/desk/drafts?archived=only&q=budget');
    expect(draftsPath('all')).toBe('/desk/drafts?archived=include');
    expect(draftsPath('current','x'.repeat(300)).length).toBeLessThan(230);
  });
  it('offers re-propose and archive only where the server would allow them',()=>{
    expect(canRepropose(draft())).toBe(true);
    expect(canRepropose(draft({status:'awaiting_approval'}))).toBe(false);
    expect(canRepropose(draft({status:'withdrawn'}))).toBe(false);
    expect(canArchive(draft({archived:true,status:'archived'}))).toBe(false);
    expect(canArchive(draft({status:'queued'}))).toBe(false);
  });
  it('labels status plainly and explains refusals',()=>{
    expect(draftStatusLabel('lapsed')).toBe('Approval lapsed · kept');
    expect(draftStatusLabel('withdrawn')).toContain('forgotten');
    expect(draftMessage(new DeskError('conflict','evidence_not_current',409))).toContain('sources changed');
    expect(draftMessage(new DeskError('conflict','other',409))).toContain('other');
  });
  it('does not show a lapsed or archived draft as waiting for approval',()=>{
    const s=toSnapshot(projection([approval({id:'a1'}),approval({id:'a2',draftStatus:'lapsed'}),approval({id:'a3',draftStatus:'archived'}),approval({id:'a4',draftStatus:'awaiting_approval'})]),'w1');
    expect(s.proposals.map(p=>[p.id,p.status])).toEqual([['a1','pending'],['a2','closed'],['a3','closed'],['a4','pending']]);
  });
});
