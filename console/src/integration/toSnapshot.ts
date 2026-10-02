import {CATEGORIES,type Category,type ConsoleSnapshot,type Insight,type KnowledgeRecord,type Proposal,type RecordKind,type Relationship} from '../domain/model';
import {assertProjectionScope,type ConnectedProjection,type ProjectionNode} from './ConsoleReadPort';
const KIND:Record<ProjectionNode['type'],RecordKind>={person:'person',project:'project',note:'note',claim:'note',source:'source',action:'action',resource:'resource'};
const ORIGIN_LABEL={authored_note:'Authored note',reviewed_entity:'Reviewed memory entity',source:'Selected source'} as const;
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
    summary:node.summary??'',detail:node.summary??'',status:node.availability??'current',
    origin:node.origin,availability:node.availability,path:node.path,sha256:node.sha256,sourceId:node.sourceId,inboxWritable:node.inboxWritable,
    provenance:{id:node.evidence[0]?.sourceId??node.id,label:node.path??(node.origin?ORIGIN_LABEL[node.origin]:node.label),
      revision:node.revision??'',basis:node.origin==='reviewed_entity'?'human_review':node.origin==='source'?'source_status':'authored',excerpt:node.summary??''}}));
  const relationships:Relationship[]=projection.edges.map(edge=>({id:edge.id,from:edge.from,to:edge.to,relation:edge.relation,
    provenanceId:edge.evidence[0].sourceId,basis:edge.layer==='note_reference'?'authored':'human_review',layer:edge.layer}));
  const proposals:Proposal[]=(projection.approvals??[]).map(a=>({id:a.id,title:a.capability==='message.draft'?'Local message draft':a.capability==='vault.inbox_note'?`Inbox note · ${(a.path??'').split('/').pop()}`:a.capability,path:a.path??undefined,
    body:a.text??'',scope:w,status:proposalStatus(a.state),effect:'server_action',revision:1,serverState:a.state,fingerprint:a.fingerprint,
    capability:a.capability,evidenceCurrent:a.evidenceCurrent,mine:a.mine,createdAt:a.createdAt,expiresAt:a.expiresAt}));
  const names=new Map(records.map(r=>[r.id,r.title]));
  const insights:Insight[]=(projection.executive?.insights??[]).filter(i=>names.has(i.entityId)).map(i=>({id:i.claimId,recordId:i.entityId,
    title:names.get(i.entityId)!,summary:`${i.predicate.replaceAll('_',' ')}: ${i.value??names.get(i.objectId??'')??'linked record'}`,reviewedAt:i.reviewedAt,supportId:i.supportId}));
  return {schemaVersion:1,mode:'connected',label:'ALFRED workspace',records,relationships,priorities:[],proposals,workspaceId:w,
    dataRevision:projection.dataRevision,grantRevision:projection.grantRevision,observedAt:projection.observedAt,insights,
    model:projection.model?{configured:projection.model.configured,name:projection.model.name,allowed:projection.model.allowed}:{configured:false,name:null,allowed:false}};
}
