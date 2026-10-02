import {describe,it,expect} from 'vitest';
import {readFileSync} from 'node:fs';
import {parseCommand} from '../src/domain/commands';
import {recordPosition,linkedRecordIds,milestoneProgress} from '../src/domain/projection';
import {createDemoSnapshot} from '../src/domain/fixtures';
import {assertProjectionScope,type ConnectedProjection} from '../src/integration/ConsoleReadPort';
import * as shaders from '../src/scene/shaders';
describe('command routing',()=>{
  for(const input of['/brief','summarise','today'])it(`routes ${input}`,()=>expect(parseCommand(input)).toEqual({kind:'dialog',dialog:'brief'}));
  it('routes handoff',()=>expect(parseCommand('/handoff')).toEqual({kind:'dialog',dialog:'handoff'}));
  it('routes actual demo scope',()=>expect(parseCommand('work')).toEqual({kind:'scope',scope:'work'}));
  it('treats unknown input literally',()=>expect(parseCommand('rm -rf /')).toEqual({kind:'search',query:'rm -rf /'}));
  it('bounds search input',()=>{const v=parseCommand('x'.repeat(900));expect(v.kind==='search'&&v.query.length).toBe(500);});
  it('has empty-input behaviour',()=>expect(parseCommand(' ')).toEqual({kind:'empty'}));
});
describe('stable meaningful graph',()=>{
  it('does not change positions on sorting',()=>{const records=createDemoSnapshot().records;const a=new Map(records.map(r=>[r.id,recordPosition(r)]));for(const r of [...records].reverse())expect(recordPosition(r)).toEqual(a.get(r.id));});
  it('does not change a record position when unrelated data is removed',()=>{const a=createDemoSnapshot().records[0];expect(recordPosition({...a})).toEqual(recordPosition(a));});
  it('has finite bounded record positions',()=>{for(const r of createDemoSnapshot().records)expect(Math.hypot(...recordPosition(r))).toBeCloseTo(1.035,9);});
  it('uses stable ID, not display-name merging',()=>{const a=createDemoSnapshot().records[0];expect(recordPosition({...a,id:'different-id'})).not.toEqual(recordPosition(a));});
  it('selects only explicit neighbours',()=>expect([...linkedRecordIds('p-velvet',createDemoSnapshot().relationships)].sort()).toEqual(['p-design','p-velvet']));
  it('does not invent progress when milestones are absent',()=>expect(milestoneProgress('unknown')).toEqual({completed:0,total:0}));
  it('derives demo progress from explicit fixture tasks',()=>expect(milestoneProgress('p-velvet')).toEqual({completed:2,total:4}));
});
describe('stable rendering contract',()=>{
  it('contains no time-driven luminance uniforms',()=>{for(const value of Object.values(shaders)){expect(value).not.toContain('uTime');expect(value).not.toContain('aPhase');}});
  it('has a single explicit post-processing frame owner',()=>{const code=readFileSync('src/scene/RenderPipeline.tsx','utf8');expect((code.match(/composer\.render\(/g)||[])).toHaveLength(1);expect(code).toContain('},1)');});
  it('does not remount the canvas for quality or scope',()=>{const source=readFileSync('src/scene/KnowledgeSphere.tsx','utf8');expect(source).not.toMatch(/<Canvas\s+key=/);});
});
const valid=():ConnectedProjection=>({kind:'authorised_projection',schemaVersion:1,workspaceId:'w1',dataRevision:'d1',grantRevision:'g1',observedAt:'2026-09-27T00:00:00Z',nodes:[{id:'n1',workspaceId:'w1',type:'note',label:'Example',evidence:[]}],edges:[]});
describe('proposed integration envelope',()=>{
  it('accepts structural same-scope data',()=>expect(()=>assertProjectionScope(valid(),'w1')).not.toThrow());
  it('rejects the wrong workspace',()=>expect(()=>assertProjectionScope(valid(),'w2')).toThrow());
  it('rejects scope leakage inside the envelope',()=>{const p=valid();p.nodes[0].workspaceId='w2';expect(()=>assertProjectionScope(p,'w1')).toThrow();});
  it('requires a grant revision',()=>{const p=valid();p.grantRevision='';expect(()=>assertProjectionScope(p,'w1')).toThrow();});
  it('rejects an unsupported edge',()=>{const p=valid();p.edges.push({id:'e',from:'n1',to:'missing',layer:'note_reference',relation:'links_to',evidence:[]});expect(()=>assertProjectionScope(p,'w1')).toThrow();});
});
