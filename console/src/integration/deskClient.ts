import {type ConnectedProjection,type ConsoleReadPort,type PermittedWorkspace,type RecordDetail} from './ConsoleReadPort';
/**
 * Same-origin client for the loopback ALFRED server. The HttpOnly session cookie is never
 * readable here; the CSRF token lives in memory only and is never written to storage.
 */
export type DeskErrorKind='signed_out'|'denied'|'not_found'|'conflict'|'unavailable'|'rejected';
export class DeskError extends Error {
  constructor(readonly kind:DeskErrorKind,readonly code:string,readonly status:number){super(code);}
}
export function errorKind(status:number):DeskErrorKind{
  if(status===401)return 'signed_out';
  if(status===403)return 'denied';
  if(status===404)return 'not_found';
  if(status===409)return 'conflict';
  if(status===0||status>=500)return 'unavailable';
  return 'rejected';
}
export interface SessionInfo{csrf:string;scope:string;role:'owner'|'reader';expires_at:number}
export class DeskClient implements ConsoleReadPort {
  private csrf='';
  constructor(private readonly base='',private readonly fetcher:typeof fetch=(...a)=>fetch(...a)){}
  private async call<T>(path:string,init:{method?:'GET'|'POST';body?:unknown;signal?:AbortSignal}={}):Promise<T>{
    const method=init.method??'GET';let response:Response;
    try{
      response=await this.fetcher(this.base+path,{method,credentials:'same-origin',cache:'no-store',signal:init.signal,
        headers:method==='POST'?{'Content-Type':'application/json','X-CSRF-Token':this.csrf}:undefined,
        body:method==='POST'?JSON.stringify(init.body??{}):undefined});
    }catch(error){
      if(error instanceof DOMException&&error.name==='AbortError')throw error;
      throw new DeskError('unavailable','network_unavailable',0);
    }
    let value:unknown=null;
    try{value=await response.json();}catch{value=null;}
    if(!response.ok){const code=typeof value==='object'&&value&&'error' in value?String((value as {error:unknown}).error):'http_'+response.status;throw new DeskError(errorKind(response.status),code,response.status);}
    return value as T;
  }
  async session(signal?:AbortSignal){const s=await this.call<SessionInfo>('/desk/session',{signal});this.csrf=s.csrf;return s;}
  async login(key:string){const r=await this.call<{csrf:string}>('/desk/login',{method:'POST',body:{key}});this.csrf=r.csrf;}
  /** Redeems a one-time pairing code. The new device's own key is returned once, for the person to keep. */
  async pair(code:string,label:string){const r=await this.call<{csrf:string;key:string;device_id:string;role:'owner'|'reader';expires_at:number}>('/desk/identity/pairing/redeem',{method:'POST',body:{code,label}});this.csrf=r.csrf;return r;}
  async logout(){try{await this.call('/desk/logout',{method:'POST',body:{}});}finally{this.csrf='';}}
  forget(){this.csrf='';}
  async permittedWorkspaces(signal:AbortSignal):Promise<readonly PermittedWorkspace[]>{return (await this.call<{workspaces:PermittedWorkspace[]}>('/desk/console/workspaces',{signal})).workspaces;}
  readProjection(signal:AbortSignal){return this.call<ConnectedProjection>('/desk/console/projection',{signal});}
  inspectRecord(id:string,signal:AbortSignal){
    if(!/^(note|entity|source):[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/.test(id))return Promise.reject(new DeskError('not_found','record_not_available',404));
    return this.call<RecordDetail>('/desk/console/records/'+id,{signal});
  }
  post<T>(path:string,body:unknown,signal?:AbortSignal){return this.call<T>(path,{method:'POST',body,signal});}
  get<T>(path:string,signal?:AbortSignal){return this.call<T>(path,{signal});}
}
