import {type Category,type KnowledgeRecord,type Relationship} from './model';
export type GraphMode='field'|'relationships';
export type Position=[number,number,number];
const centres:Record<Category,Position>={people:[-.48,.68,.57],projects:[-.60,-.35,.70],sources:[.56,.50,.66],operations:[.61,-.49,.56],knowledge:[.02,.12,.98],resources:[-.03,-.73,.63]};
function hash(value:string){let h=2166136261;for(const char of value)h=Math.imul(h^char.charCodeAt(0),16777619);return h>>>0;}
/** Stable ID placement. Filtering, changing order or receiving unrelated records does not move a node. */
export function recordPosition(record:Pick<KnowledgeRecord,'id'|'category'>):Position {
  const seed=hash(record.id),c=centres[record.category];
  const raw:Position=[c[0]+((seed&255)/255-.5)*.44,c[1]+(((seed>>>8)&255)/255-.5)*.38,c[2]+(((seed>>>16)&255)/255-.5)*.26];
  const length=Math.hypot(...raw);return raw.map(n=>n/length*1.035) as Position;
}
export function linkedRecordIds(selected:string|null,edges:Relationship[]):Set<string> {
  if(!selected)return new Set();
  return new Set([selected,...edges.filter(e=>e.from===selected||e.to===selected).flatMap(e=>[e.from,e.to])]);
}
/** Fixture milestones only; never substitutes a percentage for real project telemetry. */
export const demoMilestones:Record<string,readonly boolean[]>={
  'p-velvet':[true,true,false,false], 'p-indigo':[true,false,false], 'p-loc8':[true,true,false],
  'w-studio':[true,false], 'o-plan':[false,false], 'r-graph':[true,false,false],
};
export function milestoneProgress(id:string){const tasks=demoMilestones[id]??[];return{completed:tasks.filter(Boolean).length,total:tasks.length};}
