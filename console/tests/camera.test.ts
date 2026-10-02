import {describe,expect,it} from 'vitest';
import {PerspectiveCamera,Vector3} from 'three';
import {cameraDistanceForViewport,SPHERE_CAMERA_FOV} from '../src/scene/camera';

describe('camera framing without mobile cropping',()=>{
  it('retains the approved desktop camera distance',()=>{
    expect(cameraDistanceForViewport(1126,692)).toBe(4);
  });
  for(const [width,height] of [[337,621],[307,546],[954,540]]){
    it(`keeps the complete knowledge sphere in ${width}x${height}`,()=>{
      const camera=new PerspectiveCamera(SPHERE_CAMERA_FOV,width/height,.1,30);
      camera.position.z=cameraDistanceForViewport(width,height);camera.updateMatrixWorld();
      // Sample the full sphere, not just an equator lying at z=0.
      let maxX=0,maxY=0;
      for(let latitude=0;latitude<=36;latitude++)for(let longitude=0;longitude<72;longitude++){
        const phi=latitude*Math.PI/36,theta=longitude*Math.PI/36;
        const point=new Vector3(1.045*Math.sin(phi)*Math.cos(theta),1.045*Math.cos(phi),1.045*Math.sin(phi)*Math.sin(theta)).project(camera);
        maxX=Math.max(maxX,Math.abs(point.x));maxY=Math.max(maxY,Math.abs(point.y));
      }
      expect(maxX).toBeLessThan(.96);expect(maxY).toBeLessThan(.96);
    });
  }
  it('uses a safe initial distance for an unmeasured viewport',()=>{
    for(const pair of [[0,0],[0,600],[500,0],[-1,600],[NaN,300],[300,Infinity]]){
      expect(cameraDistanceForViewport(...pair as [number,number])).toBe(4);
    }
  });
});
