import {CATEGORIES,type Category,type ConsoleSnapshot,type Insight,type KnowledgeRecord,type Proposal,type RecordKind,type Relationship} from '../domain/model';
import {assertProjectionScope,type ConnectedProjection,type ProjectionNode} from './ConsoleReadPort';
const KIND:Record<ProjectionNode['type'],RecordKind>={person:'person',project:'project',note:'note',claim:'note',source:'source',action:'action',resource:'resource'};
const ORIGIN_LABEL={authored_note:'Authored note',reviewed_entity:'Reviewed memory entity',source:'Selected source',executive_record:'Executive record'} as const;
export function dueLabel(due:number|null|undefined,overdue=false){if(due==null)return 'No date';const day=new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short'}).format(new Date(due*1000));return overdue?`Overdue · ${day}`:`Due ${day}`;}
function category(node:ProjectionNode):Category{return node.category&&(CATEGORIES as string[]).includes(node.category)?node.category:'knowledge';}
function proposalStatus(state:string):Proposal['status']{
  if(state==='proposed')return 'pending';
  if(state==='queued'||state==='executing'||state==='uncertain')return 'in_progress';
  if(state==='verified')return 'completed';
  return 'closed';
}
/** An empty connected snapshot. It is never populated from fixtures. */
export function emptyConnectedSnapshot(workspaceId=''):ConsoleSnapshot{
  return {schemaVersion:1,mode:'connected',label:'ALFRED workspace',records:[],relationships:[],priorities:[],proposals:[],workspaceId,insights:[]};
}
/** Map the server projection into the console's view model after the structural guard. */
export function toSnapshot(projection:ConnectedProjection,expectedWorkspace:string):ConsoleSnapshot{
  assertProjectionScope(projection,expectedWorkspace);
  const w=projection.workspaceId;
  const records:KnowledgeRecord[]=projection.nodes.map(node=>({
    id:node.id,title:node.label,kind:KIND[node.type]??'note',category:category(node),scope:w,
    summary:node.summary??'',detail:node.summary??'',status:node.status??node.availability??'current',execKind:node.origin==='executive_record'?node.kind:undefined,due:node.due,
    origin:node.origin,availability:node.availability,path:node.path,sha256:node.sha256,sourceId:node.sourceId,inboxWritable:node.inboxWritable,
    provenance:{id:node.evidence[0]?.sourceId??node.id,label:node.path??(node.origin?ORIGIN_LABEL[node.origin]:node.label),
      revision:node.revision??'',basis:node.origin==='reviewed_entity'?'human_review':node.origin==='source'?'source_status':'authored',excerpt:node.summary??''}}));
  const ex=projection.executive;
  const relationships:Relationship[]=projection.edges.map(edge=>({id:edge.id,from:edge.from,to:edge.to,relation:edge.relation,
    provenanceId:edge.evidence[0].sourceId,basis:edge.layer==='note_reference'||edge.layer==='executive_link'?'authored':'human_review',layer:edge.layer}));
  const proposals:Proposal[]=(projection.approvals??[]).map(a=>({id:a.id,title:a.capability==='message.draft'?'Local message draft':a.capability==='vault.inbox_note'?`Inbox note · ${(a.path??'').split('/').pop()}`:a.capability,path:a.path??undefined,
    body:a.text??'',scope:w,status:proposalStatus(a.state),effect:'server_action',revision:1,serverState:a.state,fingerprint:a.fingerprint,
    capability:a.capability,evidenceCurrent:a.evidenceCurrent,mine:a.mine,createdAt:a.createdAt,expiresAt:a.expiresAt}));
  const names=new Map(records.map(r=>[r.id,r.title]));
  const insights:Insight[]=(projection.executive?.insights??[]).filter(i=>names.has(i.entityId)).map(i=>({id:i.claimId,recordId:i.entityId,
    title:names.get(i.entityId)!,summary:`${i.predicate.replaceAll('_',' ')}: ${i.value??names.get(i.objectId??'')??'linked record'}`,reviewedAt:i.reviewedAt,supportId:i.supportId}));
  const priorities=(ex?.priorities??[]).map(p=>({id:p.id,title:p.title,scope:w,timing:p.open?dueLabel(p.due,p.overdue):p.status==='done'?'Done':p.status,done:p.status==='done',version:p.version,overdue:p.overdue,origin:p.origin}));
  const recommendations=(ex?.recommendations??[]).map(r=>({fromRecord:r.fromRecord,fromVersion:r.fromVersion,title:r.title,reason:r.reason,due:r.due}));
  const milestones=Object.fromEntries((ex?.milestones??[]).map(m=>[m.project,{done:m.done,total:m.total}]));
  return {schemaVersion:1,mode:'connected',label:'ALFRED workspace',records,relationships,priorities,proposals,workspaceId:w,recommendations,milestones,
    dataRevision:projection.dataRevision,grantRevision:projection.grantRevision,observedAt:projection.observedAt,insights,
    model:projection.model?{configured:projection.model.configured,name:projection.model.name,allowed:projection.model.allowed}:{configured:false,name:null,allowed:false}};
}
