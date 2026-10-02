/**
 * Integration proposal for the brain builder. No HTTP client or live adapter is
 * implemented here. These names are NOT claims about existing server endpoints.
 * Demo state must never be cast into ConnectedProjection or treated as authority.
 */
export type Availability='current'|'stale'|'unavailable'|'withdrawn';
export interface EvidenceReference {
  sourceId:string;
  revision:string;
  location:{kind:'lines';start:number;end:number}|{kind:'page';page:number;block?:string};
  basis:'authored'|'observed'|'reported'|'human_review'|'model_proposed';
  availability:Availability;
}
export interface ProjectionNode {
  id:string;
  label:string;
  type:'person'|'project'|'note'|'claim'|'source'|'action'|'resource';
  workspaceId:string;
  evidence:EvidenceReference[];
  reviewState?:'proposed'|'accepted'|'disputed'|'superseded'|'withdrawn';
}
export interface ProjectionEdge {
  id:string;from:string;to:string;
  layer:'note_reference'|'reviewed_claim';
  relation:string;
  evidence:EvidenceReference[];
}
export interface ConnectedProjection {
  kind:'authorised_projection';schemaVersion:1;
  workspaceId:string;dataRevision:string;grantRevision:string;observedAt:string;
  nodes:ProjectionNode[];edges:ProjectionEdge[];
}
export type ConnectionState =
  |{kind:'disconnected'}
  |{kind:'loading';workspaceId:string;requestId:string}
  |{kind:'ready';projection:ConnectedProjection}
  |{kind:'denied'|'revoked';workspaceId:string}
  |{kind:'unavailable';workspaceId:string;message:string};
export interface ConsoleReadPort {
  permittedWorkspaces(signal:AbortSignal):Promise<readonly {id:string;label:string}[]>;
  readProjection(workspaceId:string,signal:AbortSignal):Promise<ConnectedProjection>;
  inspectRecord(workspaceId:string,id:string,signal:AbortSignal):Promise<ProjectionNode>;
}
/** Structural projection guard. Not authentication, not entailment verification. */
export function assertProjectionScope(projection:ConnectedProjection,workspaceId:string):void {
  if(projection.kind!=='authorised_projection'||projection.schemaVersion!==1||projection.workspaceId!==workspaceId||!projection.grantRevision||!projection.dataRevision)throw new Error('Invalid projection envelope');
  const ids=new Set<string>();
  for(const node of projection.nodes){if(!node.id||ids.has(node.id)||node.workspaceId!==workspaceId)throw new Error('Duplicate or out-of-scope node');ids.add(node.id);}
  for(const edge of projection.edges){if(!ids.has(edge.from)||!ids.has(edge.to)||!edge.evidence.length)throw new Error('Broken or unsupported edge');}
}
