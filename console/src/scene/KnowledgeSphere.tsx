import {Component,memo,useCallback,useEffect,useRef,useState,type ReactNode} from 'react';
import {Canvas,useFrame,useThree} from '@react-three/fiber';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {type KnowledgeRecord,type Relationship} from '../domain/model';
import {type GraphMode} from '../domain/projection';
import {Shell,ParticleField,Lattice,OrbitLines,EvidenceLinks,RecordNodes} from './layers';
import {RenderPipeline} from './RenderPipeline';
import {cameraDistanceForViewport,SPHERE_CAMERA_FOV} from './camera';
import {PresenceField} from './PresenceField';
import {type PresenceActivity} from '../domain/presence';
export interface SphereProps{records:KnowledgeRecord[];relationships:Relationship[];selected:string|null;onSelect:(id:string)=>void;paused:boolean;reducedMotion:boolean;quality:'high'|'balanced';onStatus:(status:string)=>void;mode:GraphMode;resetEpoch:number;presentation?:'globe'|'consciousness';activity?:PresenceActivity;}
class SceneBoundary extends Component<{children:ReactNode;fallback:ReactNode;onError:()=>void},{failed:boolean}>{
  state={failed:false};static getDerivedStateFromError(){return{failed:true};}
  componentDidCatch(){this.props.onError();}
  render(){return this.state.failed?this.props.fallback:this.props.children;}
}
function GraphScene(props:SphereProps&{moving:boolean;onHover:(text:string|null)=>void}){
  const{gl,camera,invalidate,size}=useThree(),group=useRef<THREE.Group>(null),controls=useRef<OrbitControls|null>(null),savedCamera=useRef<THREE.Vector3|null>(null);
  useEffect(()=>{
    const c=new OrbitControls(camera,gl.domElement);c.enablePan=false;c.enableZoom=false;c.enableDamping=!props.reducedMotion;c.dampingFactor=.1;c.rotateSpeed=.32;c.minPolarAngle=.6;c.maxPolarAngle=2.4;
    const change=()=>invalidate();c.addEventListener('change',change);controls.current=c;gl.domElement.style.cursor='grab';
    return()=>{c.removeEventListener('change',change);c.dispose();};
  },[camera,gl,invalidate,props.reducedMotion]);
  const presence=props.presentation==='consciousness';
  useEffect(()=>{
    const c=controls.current;if(c){c.enabled=!presence;c.enableDamping=!presence&&!props.reducedMotion;}
    if(presence){if(!savedCamera.current)savedCamera.current=camera.position.clone();c?.reset();camera.position.set(0,0,cameraDistanceForViewport(size.width,size.height));camera.lookAt(0,0,0);}
    else{if(savedCamera.current){camera.position.copy(savedCamera.current);camera.lookAt(0,0,0);savedCamera.current=null;}c?.update();}
    gl.domElement.style.cursor=presence?'default':'grab';invalidate();
  },[presence,gl,camera,invalidate,props.reducedMotion]);// viewport/reset framing is handled below
  useEffect(()=>{
    const distance=cameraDistanceForViewport(size.width,size.height);
    camera.position.set(0,0,distance);camera.lookAt(0,0,0);camera.updateProjectionMatrix();controls.current?.update();controls.current?.saveState();
    if(savedCamera.current)savedCamera.current.set(0,0,distance);
    if(group.current)group.current.rotation.set(0,0,0);invalidate();
  },[camera,size.width,size.height,props.resetEpoch,invalidate]);
  useEffect(()=>{if(props.mode==='relationships'&&group.current){group.current.rotation.set(0,0,0);controls.current?.reset();invalidate();}},[props.mode,invalidate]);
  useFrame((_,dt)=>{if(group.current&&props.moving&&!presence)group.current.rotation.y+=Math.min(dt,.04)*.018;if(!presence)controls.current?.update();});
  return <><group ref={group} visible={!presence}>
    {props.mode==='field'&&<><Shell/><ParticleField high={props.quality==='high'}/><Lattice/></>}
    <EvidenceLinks records={props.records} relationships={props.relationships} selected={props.selected}/>
    {!presence&&<RecordNodes records={props.records} relationships={props.relationships} selected={props.selected} onSelect={props.onSelect} onHover={props.onHover}/>}
  </group>{!presence&&props.mode==='field'&&<OrbitLines/>}{presence&&<PresenceField activity={props.activity??'present'} moving={props.moving} reduced={props.reducedMotion} high={props.quality==='high'}/>}<RenderPipeline high={props.quality==='high'}/></>;
}
function KnowledgeSphereImpl(props:SphereProps){
  const[hidden,setHidden]=useState(document.hidden),[hover,setHover]=useState<string|null>(null),[lost,setLost]=useState(false),[failed,setFailed]=useState(false),[attempt,setAttempt]=useState(0);
  const glRef=useRef<THREE.WebGLRenderer|null>(null),cleanup=useRef<()=>void>(()=>{});
  const[available]=useState(()=>{try{const c=document.createElement('canvas');return !!c.getContext('webgl2');}catch{return false;}});
  useEffect(()=>{if(!available)props.onStatus('Graphics unavailable');},[available,props.onStatus]);
  useEffect(()=>{const handler=()=>setHidden(document.hidden);document.addEventListener('visibilitychange',handler);return()=>{document.removeEventListener('visibilitychange',handler);cleanup.current();};},[]);
  const onError=useCallback(()=>{setFailed(true);props.onStatus('Graphics unavailable');},[props.onStatus]);
  const onCreated=useCallback(({gl,invalidate}:{gl:THREE.WebGLRenderer;invalidate:()=>void})=>{
    cleanup.current();glRef.current=gl;gl.setClearColor(0x000000,1);gl.toneMapping=THREE.ACESFilmicToneMapping;gl.toneMappingExposure=1;
    gl.domElement.dataset.contextId=String(Date.now());
    const lostEvent=(e:Event)=>{e.preventDefault();setLost(true);props.onStatus('Graphics context lost');};
    const restored=()=>{setLost(false);props.onStatus('WebGL2 renderer');invalidate();};
    gl.domElement.addEventListener('webglcontextlost',lostEvent);gl.domElement.addEventListener('webglcontextrestored',restored);
    cleanup.current=()=>{gl.domElement.removeEventListener('webglcontextlost',lostEvent);gl.domElement.removeEventListener('webglcontextrestored',restored);};
    props.onStatus('WebGL2 renderer');
  },[props.onStatus]);
  const fallback=<div className="graphics-fallback" role="status"><h3>Graphics unavailable.</h3><p>Browse your records below.<br/>The workspace remains usable.</p>{failed&&<button onClick={()=>{setFailed(false);setAttempt(n=>n+1);}}>Retry graphics</button>}</div>;
  const moving=!props.paused&&!props.reducedMotion&&!hidden&&!lost&&(props.presentation==='consciousness'||props.mode==='field');
  return <div className="sphere-canvas" aria-label={props.presentation==='consciousness'?'Decorative ALFRED presence':'Three-dimensional knowledge view'}>
    {!available?fallback:<SceneBoundary key={attempt} fallback={fallback} onError={onError}><Canvas camera={{position:[0,0,4],fov:SPHERE_CAMERA_FOV,near:.1,far:30}} dpr={1} frameloop={moving?'always':'demand'} gl={{antialias:true,alpha:false,powerPreference:'high-performance'}} onCreated={onCreated} fallback={fallback}><GraphScene {...props} moving={moving} onHover={setHover}/></Canvas></SceneBoundary>}
    {hover&&!lost&&props.presentation!=='consciousness'&&<div className="node-tooltip" role="status">{hover}</div>}
    {lost&&<div className="graphics-status" role="status">Graphics paused. Waiting for context recovery. Record browsing remains available.</div>}
  </div>;
}
export const KnowledgeSphere=memo(KnowledgeSphereImpl);
