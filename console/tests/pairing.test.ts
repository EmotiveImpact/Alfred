import {describe,it,expect} from 'vitest';
import {DeskClient,DeskError} from '../src/integration/deskClient';
type Call={url:string;init:RequestInit};
function fake(responses:{status:number;body:unknown}[]){
  const calls:Call[]=[];
  const fetcher=(async(url:string,init:RequestInit)=>{calls.push({url,init});const r=responses.shift()!;return new Response(JSON.stringify(r.body),{status:r.status,headers:{'Content-Type':'application/json'}});}) as unknown as typeof fetch;
  return{calls,fetcher};
}
describe('device pairing client',()=>{
  it('redeems a code, keeps the new CSRF token in memory and returns the key once',async()=>{
    const{calls,fetcher}=fake([{status:200,body:{csrf:'csrf-new',key:'k'.repeat(43),device_id:'device-'+'a'.repeat(24),role:'reader',expires_at:1}},{status:200,body:{ok:true}}]);
    const client=new DeskClient('',fetcher);
    const paired=await client.pair('c'.repeat(24),'Fictional tablet');
    expect(paired.role).toBe('reader');
    expect(JSON.parse(String(calls[0].init.body))).toEqual({code:'c'.repeat(24),label:'Fictional tablet'});
    await client.post('/desk/identity',{});
    expect((calls[1].init.headers as Record<string,string>)['X-CSRF-Token']).toBe('csrf-new');
  });
  it('reports an invalid code as not found without detail',async()=>{
    const{fetcher}=fake([{status:404,body:{error:'pairing_not_valid'}}]);
    await expect(new DeskClient('',fetcher).pair('x'.repeat(24),'Phone')).rejects.toMatchObject({kind:'not_found',code:'pairing_not_valid'});
    expect(DeskError).toBeDefined();
  });
});
