import {describe,it,expect} from 'vitest';
import {createDemoSnapshot} from '../src/domain/fixtures';
import {initialState,reducer,scopedRecords,searchRecords,visibleRelationships,validateSnapshot,SCOPES} from '../src/domain/model';
import {fibonacciPoint,makePointField,makeLattice,randomSeed} from '../src/scene/geometry';
describe('scope and evidence boundaries',()=>{
 it('makes valid, fresh fixtures',()=>{const a=createDemoSnapshot(),b=createDemoSnapshot();expect(a).toEqual(b);expect(a).not.toBe(b);expect(a.records.length).toBe(24);});
 for(const scope of SCOPES)it(`isolates ${scope} records and links`,()=>{const s=createDemoSnapshot();const r=scopedRecords(s,scope);expect(r.length).toBeGreaterThan(0);expect(r.every(v=>v.scope===scope)).toBe(true);const ids=r.map(v=>v.id);expect(visibleRelationships(s,scope).every(e=>ids.includes(e.from)&&ids.includes(e.to))).toBe(true);});
 it('never exposes work through personal search',()=>expect(searchRecords(createDemoSnapshot(),'personal','production')).toHaveLength(0));
 it('performs case-insensitive local search',()=>expect(searchRecords(createDemoSnapshot(),'personal','VELVET')[0].id).toBe('p-velvet'));
 it('does not interpret injected markup',()=>expect(searchRecords(createDemoSnapshot(),'personal','<script>')).toHaveLength(0));
 it('empty queries return only the chosen scope',()=>expect(searchRecords(createDemoSnapshot(),'work',' ')).toHaveLength(5));
 it('filters categories without inventing empty records',()=>expect(scopedRecords(createDemoSnapshot(),'systems','people')).toEqual([]));
 it('rejects duplicate ids',()=>{const s=createDemoSnapshot();s.records.push({...s.records[0]});expect(()=>validateSnapshot(s)).toThrow(/duplicate/);});
 it('rejects cross-scope graph edges',()=>{const s=createDemoSnapshot();s.relationships[0].to='w-studio';expect(()=>validateSnapshot(s)).toThrow(/cross-scope/);});
 it('rejects dangling links',()=>{const s=createDemoSnapshot();s.relationships[0].to='missing';expect(()=>validateSnapshot(s)).toThrow();});
 it('rejects unsupported live mode',()=>{const s=createDemoSnapshot();Object.assign(s,{mode:'live'});expect(()=>validateSnapshot(s)).toThrow(/implicit/);});
 it('requires provenance revisions',()=>{const s=createDemoSnapshot();s.records[0].provenance.revision='';expect(()=>validateSnapshot(s)).toThrow();});
});
describe('local UI transitions do not grant authority',()=>{
 it('switching scopes clears selection and category',()=>{let s=initialState(createDemoSnapshot());s=reducer(s,{type:'select',id:'p-velvet'});s=reducer(s,{type:'category',category:'projects'});s=reducer(s,{type:'scope',scope:'work'});expect(s.selected).toBeNull();expect(s.category).toBeNull();});
 it('cannot select an out-of-scope record',()=>expect(reducer(initialState(createDemoSnapshot()),{type:'select',id:'w-studio'}).selected).toBeNull());
 it('toggles a local priority',()=>{const s=reducer(initialState(createDemoSnapshot()),{type:'priority',id:'t1'});expect(s.snapshot.priorities[0].done).toBe(true);});
 it('does not mutate an out-of-scope priority',()=>{const s=initialState(createDemoSnapshot());expect(reducer(s,{type:'priority',id:'t4'}).snapshot.priorities).toEqual(s.snapshot.priorities);});
 it('records a demo-only reviewed receipt',()=>{const s=reducer(initialState(createDemoSnapshot()),{type:'review',id:'a1',revision:1,outcome:'reviewed',at:'2026-09-27T00:00:00Z'});expect(s.receipts[0].effect).toBe('local_demo_only');expect(s.snapshot.proposals[0].status).toBe('reviewed');});
 it('rejects stale proposal revisions',()=>{const s=initialState(createDemoSnapshot());expect(reducer(s,{type:'review',id:'a1',revision:2,outcome:'reviewed',at:'test'})).toBe(s);});
 it('reviews are idempotent and do not silently reverse',()=>{const a={type:'review',id:'a1',revision:1,outcome:'reviewed',at:'test'} as const;const s=reducer(initialState(createDemoSnapshot()),a);const t=reducer(s,{...a,outcome:'declined'});expect(t).toBe(s);expect(t.receipts).toHaveLength(1);});
 it('out-of-scope review is rejected',()=>{const s=reducer(initialState(createDemoSnapshot()),{type:'scope',scope:'work'});expect(reducer(s,{type:'review',id:'a1',revision:1,outcome:'reviewed',at:'test'})).toBe(s);});
 it('a decline has only a local effect',()=>expect(reducer(initialState(createDemoSnapshot()),{type:'review',id:'a2',revision:1,outcome:'declined',at:'test'}).receipts[0].effect).toBe('local_demo_only'));
 it('focus does not change snapshot',()=>{const s=initialState(createDemoSnapshot());expect(reducer(s,{type:'focus'}).snapshot).toBe(s.snapshot);});
 it('pause does not change data',()=>{const s=initialState(createDemoSnapshot());expect(reducer(s,{type:'pause'}).snapshot).toBe(s.snapshot);});
 it('reset clears all transient receipts',()=>{let s=reducer(initialState(createDemoSnapshot()),{type:'review',id:'a1',revision:1,outcome:'declined',at:'test'});s=reducer(s,{type:'reset',snapshot:createDemoSnapshot()});expect(s.receipts).toHaveLength(0);expect(s.snapshot.proposals[0].status).toBe('pending');});
});
describe('deterministic shader inputs',()=>{
 it('has reproducible random sequences',()=>{const a=randomSeed(3),b=randomSeed(3);for(let i=0;i<100;i++)expect(a()).toBe(b());});
 it('keeps Fibonacci points on a unit sphere',()=>{for(let i=0;i<100;i++)expect(Math.hypot(...fibonacciPoint(i,100))).toBeCloseTo(1,9);});
 it('produces finite fields with matching attribute counts',()=>{const f=makePointField(1000);expect(f.positions.length/3).toBe(f.strengths.length);expect(f.phases.length).toBe(f.warmth.length);expect([...f.positions].every(Number.isFinite)).toBe(true);});
 it('has deterministic point placement',()=>expect(makePointField(500)).toEqual(makePointField(500)));
 it('builds a bounded line lattice',()=>{const l=makeLattice();expect(l.positions.length%6).toBe(0);expect(l.positions.length/3).toBe(l.alpha.length);expect(l.nodes).toHaveLength(160);expect(l.positions.length).toBeLessThan(4000);});
});
