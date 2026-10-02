import {describe,it,expect} from 'vitest';
import {refreshingDetail,type DetailState} from '../src/state/useConnection';
type Ready=Extract<DetailState,{status:'ready'}>;
const ready:Ready={status:'ready',id:'source:demo-source',detail:{} as Ready['detail']};
describe('record detail refresh',()=>{
  it('keeps the record shown while the same record is re-read, so open confirmations survive',()=>{
    expect(refreshingDetail(ready,'source:demo-source')).toBe(ready);
  });
  it('shows loading for a different record',()=>{
    expect(refreshingDetail(ready,'note:other')).toEqual({status:'loading',id:'note:other'});
  });
  it('shows loading when nothing usable is shown yet',()=>{
    expect(refreshingDetail({status:'idle'},'note:a')).toEqual({status:'loading',id:'note:a'});
    expect(refreshingDetail({status:'unavailable',id:'note:a',message:'gone'},'note:a')).toEqual({status:'loading',id:'note:a'});
    expect(refreshingDetail({status:'loading',id:'note:a'},'note:a')).toEqual({status:'loading',id:'note:a'});
  });
});
