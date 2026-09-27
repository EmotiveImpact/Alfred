import {useEffect,useRef} from 'react';
import {useFrame,useThree} from '@react-three/fiber';
import * as THREE from 'three';
import {EffectComposer} from 'three/addons/postprocessing/EffectComposer.js';
import {RenderPass} from 'three/addons/postprocessing/RenderPass.js';
import {UnrealBloomPass} from 'three/addons/postprocessing/UnrealBloomPass.js';
import {OutputPass} from 'three/addons/postprocessing/OutputPass.js';
type Pipeline={composer:EffectComposer;bloom:UnrealBloomPass};
/** One render owner. Effects allocate and dispose together, including React StrictMode remounts. */
export function RenderPipeline({high}:{high:boolean}){
  const{gl,scene,camera,size,invalidate,setDpr}=useThree();
  const pipeline=useRef<Pipeline|null>(null),frame=useRef(0);
  useEffect(()=>{
    const target=new THREE.WebGLRenderTarget(1,1,{type:THREE.HalfFloatType,samples:4});
    const composer=new EffectComposer(gl,target),bloom=new UnrealBloomPass(new THREE.Vector2(1,1),.24,.36,1.02);
    composer.addPass(new RenderPass(scene,camera));composer.addPass(bloom);composer.addPass(new OutputPass());
    pipeline.current={composer,bloom};invalidate();
    return()=>{pipeline.current=null;composer.passes.forEach(pass=>pass.dispose());composer.dispose();};
  },[gl,scene,camera,invalidate]);
  useEffect(()=>{
    const p=pipeline.current;if(!p)return;
    const dpr=Math.min(window.devicePixelRatio||1,high?1.75:1.15);
    setDpr(dpr);p.composer.setPixelRatio(dpr);p.bloom.strength=high?.24:.18;p.composer.setSize(size.width,size.height);invalidate();
  },[gl,scene,camera,high,size.width,size.height,invalidate,setDpr]);
  useFrame((_,dt)=>{
    if(!pipeline.current)return;pipeline.current.composer.render(dt);frame.current++;
    // Inert diagnostics for browser tests, never a model or system-health claim.
    gl.domElement.dataset.renderFrame=String(frame.current);
  },1);
  return null;
}
