/** UI contract, not a backend API. Backend adapters must preserve server-side grants.
 * Decorative geometry is never included in these evidence-bearing records. */
export type Scope = 'personal' | 'work' | 'operation' | 'research' | 'systems';
export type Category = 'people' | 'projects' | 'knowledge' | 'sources' | 'operations' | 'resources';
export type RecordKind = 'person' | 'project' | 'note' | 'source' | 'action' | 'resource';
export interface Provenance { id: string; label: string; revision: string; basis: 'fixture' | 'authored' | 'reported' | 'observed'; excerpt: string; }
export interface KnowledgeRecord { id: string; title: string; kind: RecordKind; category: Category; scope: Scope; summary: string; detail: string; status: string; provenance: Provenance; }
export interface Relationship { id: string; from: string; to: string; relation: 'links_to' | 'supported_by' | 'depends_on'; provenanceId: string; basis: 'fixture' | 'authored'; }
export interface Priority { id: string; title: string; scope: Scope; timing: string; done: boolean; }
export interface Proposal { id: string; title: string; body: string; scope: Scope; status: 'pending' | 'reviewed' | 'declined'; effect: 'local_demo_only'; revision: number; }
export interface ConsoleSnapshot { schemaVersion: 1; mode: 'demo'; label: string; records: KnowledgeRecord[]; relationships: Relationship[]; priorities: Priority[]; proposals: Proposal[]; }
export interface DemoReceipt { id: string; proposalId: string; revision: number; outcome: 'reviewed' | 'declined'; at: string; effect: 'local_demo_only'; }
export interface ConsoleState { scope: Scope; focus: boolean; paused: boolean; reducedMotion: boolean; quality: 'balanced' | 'high'; selected: string | null; category: Category | null; snapshot: ConsoleSnapshot; receipts: DemoReceipt[]; }
export type ConsoleAction = {type:'scope';scope:Scope}|{type:'select';id:string|null}|{type:'category';category:Category|null}|{type:'focus'}|{type:'pause'}|{type:'quality';quality:'balanced'|'high'}|{type:'motion';value:boolean}|{type:'priority';id:string}|{type:'review';id:string;revision:number;outcome:'reviewed'|'declined';at:string}|{type:'reset';snapshot:ConsoleSnapshot};
export const SCOPES: Scope[] = ['personal','work','operation','research','systems'];
export const CATEGORIES: Category[] = ['people','projects','knowledge','sources','operations','resources'];
export const categoryCopy: Record<Category, {subtitle:string;description:string}> = {
 people:{subtitle:'Relationships · context',description:'People in the permitted workspace. Names never merge identities.'},
 projects:{subtitle:'Plans · execution',description:'Project records and their explicit source relationships.'},
 knowledge:{subtitle:'Memory · understanding',description:'Reviewed notes, with their source and revision kept visible.'},
 sources:{subtitle:'Evidence · provenance',description:'Source material behind the visible records. No private accounts connected.'},
 operations:{subtitle:'Decisions · control',description:'Proposed work, under your authority. This build performs no external actions.'},
 resources:{subtitle:'Tools · capability',description:'Available records about tools. Their presence does not grant access.'},
};
export function scopedRecords(snapshot:ConsoleSnapshot,scope:Scope,category:Category|null=null):KnowledgeRecord[]{return snapshot.records.filter(r=>r.scope===scope&&(!category||r.category===category));}
export function searchRecords(snapshot:ConsoleSnapshot,scope:Scope,query:string):KnowledgeRecord[]{
 const words=query.trim().toLocaleLowerCase('en-GB').split(/\s+/).filter(Boolean).slice(0,16);
 if(!words.length)return scopedRecords(snapshot,scope);
 return scopedRecords(snapshot,scope).filter(r=>words.every(w=>`${r.title} ${r.summary} ${r.category}`.toLowerCase().includes(w)));
}
export function visibleRelationships(snapshot:ConsoleSnapshot,scope:Scope):Relationship[]{const ids=new Set(scopedRecords(snapshot,scope).map(r=>r.id));return snapshot.relationships.filter(e=>ids.has(e.from)&&ids.has(e.to));}
export function initialState(snapshot:ConsoleSnapshot):ConsoleState{return{scope:'personal',focus:false,paused:false,reducedMotion:false,quality:'high',selected:null,category:null,snapshot,receipts:[]};}
export function reducer(state:ConsoleState,action:ConsoleAction):ConsoleState{
 switch(action.type){
 case 'scope':return{...state,scope:action.scope,selected:null,category:null};
 case 'select':return{...state,selected:action.id&&scopedRecords(state.snapshot,state.scope).some(r=>r.id===action.id)?action.id:null};
 case 'category':return{...state,category:action.category,selected:null};
 case 'focus':return{...state,focus:!state.focus};
 case 'pause':return{...state,paused:!state.paused};
 case 'quality':return{...state,quality:action.quality};
 case 'motion':return{...state,reducedMotion:action.value};
 case 'priority':return{...state,snapshot:{...state.snapshot,priorities:state.snapshot.priorities.map(p=>p.id===action.id&&p.scope===state.scope?{...p,done:!p.done}:p)}};
 case 'review':{const p=state.snapshot.proposals.find(p=>p.id===action.id&&p.scope===state.scope);if(!p||p.status!=='pending'||p.revision!==action.revision||p.effect!=='local_demo_only')return state;return{...state,snapshot:{...state.snapshot,proposals:state.snapshot.proposals.map(v=>v.id===p.id?{...v,status:action.outcome}:v)},receipts:[{id:`demo:${p.id}:${p.revision}`,proposalId:p.id,revision:p.revision,outcome:action.outcome,at:action.at,effect:'local_demo_only'},...state.receipts]};}
 case 'reset':return initialState(action.snapshot);
 }
}
/** Strict fixture ingress. No truth/authority claims are inferred from a valid schema. */
export function validateSnapshot(value:ConsoleSnapshot):ConsoleSnapshot{
 if(value.schemaVersion!==1||value.mode!=='demo')throw new Error('Unsupported console snapshot. No implicit live-mode conversion.');
 if(value.records.length>1000||value.relationships.length>4000)throw new Error('Snapshot exceeds this renderer contract.');
 const ids=new Set<string>();
 for(const r of value.records){if(ids.has(r.id)||!r.id||!SCOPES.includes(r.scope)||!CATEGORIES.includes(r.category)||!r.provenance.id||!r.provenance.revision)throw new Error('Invalid or duplicate record.');ids.add(r.id);}
 for(const e of value.relationships){const a=value.records.find(r=>r.id===e.from),b=value.records.find(r=>r.id===e.to);if(!a||!b||a.scope!==b.scope||!e.provenanceId)throw new Error('Broken or cross-scope relationship.');}
 return value;
}
