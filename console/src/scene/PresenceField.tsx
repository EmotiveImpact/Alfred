import {useEffect,useMemo,useRef,useState} from 'react';
import {useFrame,useThree} from '@react-three/fiber';
import * as THREE from 'three';
import {markSamples,type PresenceActivity} from '../domain/presence';

const vertex=`
attribute float aLight;
attribute float aSeed;
attribute float aSpread;
attribute float aPhase;
uniform float uTime,uGather,uRadius,uDpr;
varying float vLight;
void main(){
  float a=aSeed*6.2831853+uTime*(.12+.045*aLight);
  float r=.2+sqrt(aSpread)*1.25;
  vec3 cloud=vec3(cos(a)*r*1.5,sin(a*2.+aPhase*.5)*r*.85,sin(a)*.13);
  float band=1.3+(aSpread-.5)*.75;
  vec3 ring=vec3(cos(a)*band,sin(a)*band*.42+sin(aPhase+uTime*.12)*.12,sin(a)*.12);
  float width=.6+aSpread*.5;
  vec3 eight=vec3(sin(a)*1.65*width,sin(a)*cos(a)*1.1*width,cos(a)*.1);
  float shape=.5+.5*sin(uTime*.055);
  vec3 loose=mix(mix(cloud,ring,shape),eight,.24+.2*sin(uTime*.041));
  vec3 p=mix(loose,position,uGather)*uRadius;
  vec4 view=modelViewMatrix*vec4(p,1.);
  gl_Position=projectionMatrix*view;
  gl_PointSize=(1.25+aLight*.85)*uDpr;
  vLight=aLight;
}`;
const fragment=`
uniform float uGather,uWarm;
varying float vLight;
void main(){
  float d=length(gl_PointCoord-.5);
  float alpha=(1.-smoothstep(.15,.5,d))*(.43+vLight*.34);
  vec3 cool=vec3(.52,.62,.78),ivory=vec3(.82,.85,.82),amber=vec3(.83,.67,.4);
  vec3 col=mix(mix(cool,ivory,uGather),amber,uWarm);
  gl_FragColor=vec4(col,alpha);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;
type Samples=ReturnType<typeof markSamples>;
/** Uses the existing Canvas and its single RenderPipeline. No independent draw loop. */
export function PresenceField({activity,moving,reduced,high}:{activity:PresenceActivity;moving:boolean;reduced:boolean;high:boolean}){
  const{camera,viewport,gl,invalidate}=useThree(),[samples,setSamples]=useState<Samples>([]),time=useRef(0),previousTarget=useRef(1);
  const material=useRef<THREE.ShaderMaterial>(null);
  const origin=useMemo(()=>new THREE.Vector3(),[]);
  const uniforms=useMemo(()=>({uTime:{value:0},uGather:{value:1},uRadius:{value:1},uDpr:{value:1},uWarm:{value:0}}),[]);
  useEffect(()=>{
    let disposed=false;const img=new Image();
    img.onload=()=>{if(disposed)return;const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
      const ctx=canvas.getContext('2d');if(!ctx)return;ctx.drawImage(img,0,0);setSamples(markSamples(ctx.getImageData(0,0,canvas.width,canvas.height).data,canvas.width,canvas.height));invalidate();};
    img.src='./alfred-mark.jpg';return()=>{disposed=true;img.onload=null;};
  },[invalidate]);
  const geometry=useMemo(()=>{
    const points=high?samples:samples.filter((_,i)=>i%2===0),positions=new Float32Array(points.length*3),light=new Float32Array(points.length),seed=new Float32Array(points.length),spread=new Float32Array(points.length),phase=new Float32Array(points.length);
    points.forEach((p,i)=>{const index=high?i:i*2;positions.set([p.x,p.y,0],i*3);light[i]=p.light;seed[i]=(index*.61803398875)%1;
      const random=Math.sin((index+1)*12.9898)*43758.5453;spread[i]=random-Math.floor(random);phase[i]=((index*.754877666)%1)*Math.PI*2;});
    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(positions,3));g.setAttribute('aLight',new THREE.BufferAttribute(light,1));g.setAttribute('aSeed',new THREE.BufferAttribute(seed,1));g.setAttribute('aSpread',new THREE.BufferAttribute(spread,1));g.setAttribute('aPhase',new THREE.BufferAttribute(phase,1));return g;
  },[samples,high]);
  useEffect(()=>()=>geometry.dispose(),[geometry]);
  const target=reduced||activity!=='present'?1:0;
  useEffect(()=>{
    const live=material.current?.uniforms;if(!live)return;
    if(reduced||(!moving&&previousTarget.current!==target))live.uGather.value=target;
    previousTarget.current=target;live.uWarm.value=activity==='review'?.8:0;invalidate();
  },[moving,target,activity,reduced,invalidate]);
  useEffect(()=>{gl.domElement.dataset.presenceParticles=String(geometry.getAttribute('position').count);return()=>{delete gl.domElement.dataset.presenceParticles;};},[geometry,gl]);
  useFrame((_,dt)=>{
    const live=material.current?.uniforms;if(!live)return;
    const bounds=viewport.getCurrentViewport(camera,origin);
    // The loose swarm is wider than the mark. Fit both into narrow viewports,
    // interpolating the fit with the actual gather to avoid a scale jump on focus.
    live.uRadius.value=Math.min(bounds.height*.23,bounds.width*(.21+.07*live.uGather.value));live.uDpr.value=gl.getPixelRatio();
    if(moving){time.current+=Math.min(dt,.05);live.uTime.value=time.current;live.uGather.value+=(target-live.uGather.value)*(1-Math.exp(-Math.min(dt,.5)*4));}
  });
  return <points geometry={geometry} frustumCulled={false} renderOrder={10}><shaderMaterial ref={material} vertexShader={vertex} fragmentShader={fragment} uniforms={uniforms} transparent depthWrite={false} depthTest={false}/></points>;
}
