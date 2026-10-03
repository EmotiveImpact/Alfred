import {describe,it,expect} from 'vitest';
import {presenceActivity,markSamples,PRESENCE_LABEL} from '../src/domain/presence';
const idle={connected:true,ready:true,typing:false,waiting:false,speaking:false,reviewing:false};
describe('truthful presentation state',()=>{
  it('uses observable typing, retrieval and playback rather than a canned timeline',()=>{
    expect(presenceActivity(idle)).toBe('present');
    expect(presenceActivity({...idle,typing:true})).toBe('typing');
    expect(presenceActivity({...idle,typing:true,waiting:true})).toBe('retrieving');
    expect(presenceActivity({...idle,waiting:true,speaking:true})).toBe('speaking');
    expect(presenceActivity({...idle,reviewing:true})).toBe('review');
    expect(PRESENCE_LABEL.retrieving).toBe('Retrieving sources');
  });
  it('lost connection overrides stale activity',()=>{
    expect(presenceActivity({...idle,ready:false,waiting:true,speaking:true})).toBe('unavailable');
    expect(presenceActivity({...idle,connected:false,ready:false})).toBe('present');
  });
});
describe('supplied silhouette sampling',()=>{
  it('keeps visible source pixels and excludes black/transparent space',()=>{
    const pixels=new Uint8ClampedArray(7*7*4);
    pixels.set([255,255,255,255],0);pixels.set([128,128,128,255],(6*7+6)*4);
    pixels.set([255,255,255,0],(3*7+3)*4);
    const points=markSamples(pixels,7,7);
    expect(points).toHaveLength(2);expect(points[0]).toEqual({x:-1,y:1,light:1});
    expect(points[1].x).toBe(1);expect(points[1].y).toBe(-1);
  });
  it('bounds work and preserves a deterministic selection across the silhouette',()=>{
    const pixels=new Uint8ClampedArray(100*100*4).fill(255);
    const a=markSamples(pixels,100,100,24);
    expect(a).toHaveLength(24);expect(a).toEqual(markSamples(pixels,100,100,24));
    expect(a[0].y).toBe(1);expect(a.at(-1)!.y).toBeLessThan(-.8);
    expect(markSamples(new Uint8ClampedArray(49*4),7,7)).toEqual([]);
  });
});
