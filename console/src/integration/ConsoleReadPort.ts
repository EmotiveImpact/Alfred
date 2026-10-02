/**
 * Contract for the implemented read-only server projection, GET /desk/console/projection
 * (alfred/console_api.py). The server filters by the session's credential and source grants
 * before it builds records, counts or links. Demo state must never be cast into this shape.
 */
export type Availability='current'|'attention'|'stale'|'unavailable'|'withdrawn';
export interface EvidenceReference {
  sourceId:string;
  revision:string;
  sha256?:string;
  location:{kind:'lines';start:number;end:number}|{kind:'page';page:number;block?:string}|{kind:'record'};
  basis:'authored'|'observed'|'reported'|'human_review'|'model_proposed';
  availability:Availability;
  claimId?:string;
  claimVersion?:number;
}
export type NodeOrigin='authored_note'|'reviewed_entity'|'source'|'executive_record';
export type NodeCategory='people'|'projects'|'knowledge'|'sources'|'operations'|'resources';
export interface ProjectionNode {
  id:string;
  label:string;
  type:'person'|'project'|'note'|'claim'|'source'|'action'|'resource';
  kind?:string;
  category?:NodeCategory;
  origin?:NodeOrigin;
  workspaceId:string;
  availability?:Availability;
  summary?:string;
  path?:string;
  revision?:string;
  sha256?:string;
  sourceId?:string;
  updatedAt?:string;
  evidence:EvidenceReference[];
  reviewState?:'proposed'|'accepted'|'disputed'|'superseded'|'withdrawn';
  statements?:{usable:number;proposed:number;disputed:number;conflicted:number;unavailable:number};
  inboxWritable?:boolean;
  status?:string;
  due?:number|null;
  supportState?:string|null;
}
export interface ProjectionEdge {
  id:string;from:string;to:string;
  layer:'note_reference'|'reviewed_claim'|'review_support'|'executive_link'|'executive_support';
  relation:string;
  evidence:EvidenceReference[];
}
export interface ServerApproval {
  id:string;capability:string;state:string;text:string|null;path?:string|null;fingerprint:string;
  createdAt:string;expiresAt:string;evidenceCurrent:boolean;mine:boolean;effect:string;
}
export interface ServerPriority {id:string;title:string;status:string;open:boolean;due:number|null;overdue:boolean;rank:number|null;version:number;origin:string}
export interface ServerRecommendation {fromRecord:string;fromVersion:number;title:string;due:number|null;reason:string;basis:string}
export interface ServerInsight {
  entityId:string;claimId:string;predicate:string;value:string|null;objectId:string|null;
  reviewedAt:string;supportId:string;basis:string;
}
export interface ConnectedProjection {
  kind:'authorised_projection';schemaVersion:1;
  workspaceId:string;dataRevision:string;grantRevision:string;observedAt:string;
  nodes:ProjectionNode[];edges:ProjectionEdge[];
  approvals?:ServerApproval[];
  executive?:{priorities:ServerPriority[];prioritiesStatus:string;recommendations?:ServerRecommendation[];milestones?:{project:string;done:number;total:number}[];insights:ServerInsight[];milestonesStatus:string};
  model?:{configured:boolean;name:string|null;allowed:boolean;tools_enabled:boolean};
  counts?:Record<string,number>;
  paused?:boolean;
  authorityGranted?:false;
}
export interface PermittedWorkspace {id:string;label:string;role:'owner'|'reader';synthetic:boolean}
export interface NoteDetail {id:string;type:'note';label:string;kind:string;path:string;revision:string;sha256:string;indexedAt:string;lines:string[];truncated:boolean;basis:string}
export interface StatementDetail {
  id:string;version:number;state:string;usable:boolean;predicate:string;value:string|null;
  subject:{id:string;kind:string;name:string}|null;object:{id:string;kind:string;name:string}|null;
  validFrom:string|null;validUntil:string|null;validNow:boolean;conflicts:string[];reviewedAt:string|null;withheld?:boolean;
  support:{noteId:string;path:string;title:string;revision:string;sha256:string;startLine:number;endLine:number;quote:string}|null;
}
export interface EntityDetail {id:string;type:'entity';label:string;kind:string;createdAt:string;statements:StatementDetail[];sameNameEntities:string[];basis:string}
export interface SourceDetail {id:string;type:'source';label:string;status:string;checkedAt:string;lastCompleteScan:string|null;snapshot:string;issues:{code:string;path?:string}[];notes:number}
export interface ExecDetail {id:string;type:'exec';label:string;kind:string;status:string;detail:string;due:string|null;overdue:boolean;project:string|null;version:number;support:{state:string;note_id:string;path?:string;title?:string;start_line:number;end_line:number;quote:string|null}|null;basis:string}
export type RecordDetail=NoteDetail|EntityDetail|SourceDetail|ExecDetail;
export type ConnectionState =
  |{kind:'demo'}
  |{kind:'checking'}
  |{kind:'signed_out';message?:string}
  |{kind:'loading';workspaceId?:string}
  |{kind:'ready';workspaceId:string;observedAt:string}
  |{kind:'denied';message:string}
  |{kind:'unavailable';message:string;lastObservedAt?:string};
export interface ConsoleReadPort {
  permittedWorkspaces(signal:AbortSignal):Promise<readonly PermittedWorkspace[]>;
  readProjection(signal:AbortSignal):Promise<ConnectedProjection>;
  inspectRecord(id:string,signal:AbortSignal):Promise<RecordDetail>;
}
/** Structural projection guard. Not authentication, not entailment verification. */
export function assertProjectionScope(projection:ConnectedProjection,workspaceId:string):void {
  if(projection.kind!=='authorised_projection'||projection.schemaVersion!==1||projection.workspaceId!==workspaceId||!projection.grantRevision||!projection.dataRevision)throw new Error('Invalid projection envelope');
  const ids=new Set<string>();
  for(const node of projection.nodes){if(!node.id||ids.has(node.id)||node.workspaceId!==workspaceId)throw new Error('Duplicate or out-of-scope node');ids.add(node.id);}
  for(const edge of projection.edges){if(!ids.has(edge.from)||!ids.has(edge.to)||!edge.evidence.length)throw new Error('Broken or unsupported edge');}
}
