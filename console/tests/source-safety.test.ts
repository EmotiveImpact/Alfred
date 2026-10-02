import {describe,it,expect} from 'vitest';
import {toSnapshot} from '../src/integration/toSnapshot';
import {type ConnectedProjection} from '../src/integration/ConsoleReadPort';
import {freshnessLabel,toolLabel} from '../src/components/SourceSafety';
const note=(id:string,extra:object={})=>({id,label:'Atlas',type:'note' as const,kind:'note',category:'knowledge' as const,origin:'authored_note' as const,workspaceId:'w1',evidence:[],...extra});
const projection=(over:Partial<ConnectedProjection>={}):ConnectedProjection=>({kind:'authorised_projection',schemaVersion:1,workspaceId:'w1',dataRevision:'d1',grantRevision:'g1',observedAt:'2026-10-02T10:00:00Z',
  nodes:[note('note:aaaaaaaaaaaaaaaaaaaaaaaa',{availability:'attention',sourceKind:'vault',syncConflict:{state:'unresolved',copies:[{path:'Atlas.sync-conflict-20261002-101500-ABCDEFG.md',tool:'syncthing',detectedAt:'2026-10-02T10:15:00Z'}]}}),
    note('note:bbbbbbbbbbbbbbbbbbbbbbbb',{sourceKind:'connector_export'})],edges:[],
  syncConflicts:[{path:'Atlas.sync-conflict-20261002-101500-ABCDEFG.md',originalId:'note:aaaaaaaaaaaaaaaaaaaaaaaa',originalPath:'Atlas.md',state:'linked',tool:'syncthing',sourceId:'source:s1',detectedAt:'2026-10-02T10:15:00Z',basis:'sync_conflict_copy_not_indexed'},
    {path:'Gone (conflicted copy 2026-10-02 101500).md',originalId:'note:cccccccccccccccccccccccc',originalPath:'Gone.md',state:'orphaned',tool:'nextcloud_owncloud',sourceId:'source:s1',detectedAt:'2026-10-02T10:15:00Z',basis:'sync_conflict_copy_not_indexed'}],
  ...over});
describe('sync conflicts and export connectors in the console',()=>{
  it('keeps a conflict on its note and never turns the copy into a record',()=>{
    const s=toSnapshot(projection(),'w1');
    expect(s.records).toHaveLength(2);
    expect(s.records[0].syncConflict?.copies[0].tool).toBe('syncthing');
    expect(s.records[0].availability).toBe('attention');
  });
  it('links a copy to its original only when that original is in this projection',()=>{
    const s=toSnapshot(projection(),'w1');
    expect(s.syncConflicts?.map(c=>c.originalId)).toEqual(['note:aaaaaaaaaaaaaaaaaaaaaaaa',null]);
  });
  it('marks imported export items so they are not labelled as authored notes',()=>{
    const s=toSnapshot(projection(),'w1');
    expect(s.records.map(r=>r.sourceKind)).toEqual(['vault','connector_export']);
  });
  it('names tools and freshness plainly, never guessing',()=>{
    expect(toolLabel('nextcloud_owncloud')).toBe('Nextcloud or ownCloud');
    expect(toolLabel('some_tool')).toBe('some tool');
    expect(freshnessLabel('stale_snapshot')).toMatch(/newer export/);
  });
});
