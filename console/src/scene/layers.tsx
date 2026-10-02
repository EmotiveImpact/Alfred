import {useEffect,useMemo} from 'react';
import {useThree} from '@react-three/fiber';
import * as THREE from 'three';
import {makeLattice,makeOrbit,makePointField,fibonacciPoint} from './geometry';
import {recordPosition,linkedRecordIds} from '../domain/projection';
import {type KnowledgeRecord,type Relationship} from '../domain/model';
import * as S from './shaders';
function buffer(positions:Float32Array){return new THREE.BufferGeometry().setAttribute('position',new THREE.BufferAttribute(positions,3));}
export function Shell(){return <mesh renderOrder={0}><sphereGeometry args={[.997,96,72]}/><shaderMaterial vertexShader={S.shellVertex} fragmentShader={S.shellFragment} depthWrite depthTest/></mesh>;}
export function ParticleField({high}:{high:boolean}) {
  const dpr=useThree(s=>s.viewport.dpr);
  const geometry=useMemo(()=>{const f=makePointField(high?44000:16000);const g=buffer(f.positions);g.setAttribute('aStrength',new THREE.BufferAttribute(f.strengths,1));g.setAttribute('aWarmth',new THREE.BufferAttribute(f.warmth,1));return g;},[high]);
  const uniforms=useMemo(()=>({uDpr:{value:dpr}}),[dpr]);
  useEffect(()=>()=>geometry.dispose(),[geometry]);
  return <points geometry={geometry} renderOrder={10}><shaderMaterial uniforms={uniforms} vertexShader={S.pointVertex} fragmentShader={S.pointFragment} transparent depthWrite={false} depthTest={false} blending={THREE.AdditiveBlending}/></points>;
}
export function Lattice(){
  const data=useMemo(()=>makeLattice(280),[]);
  const geometry=useMemo(()=>{const g=buffer(data.positions);g.setAttribute('aAlpha',new THREE.BufferAttribute(data.alpha,1));return g;},[data]);
  const points=useMemo(()=>{
    const g=buffer(new Float32Array(data.nodes.flat()));g.setAttribute('aSize',new THREE.Float32BufferAttribute(data.nodes.map((_,i)=>i%11===0?53:18),1));g.setAttribute('aWarmth',new THREE.Float32BufferAttribute(data.nodes.map((_,i)=>i%7===0?.9:.05),1));return g;
  },[data]);
  const dpr=useThree(s=>s.viewport.dpr),uniforms=useMemo(()=>({uDpr:{value:dpr}}),[dpr]);
  useEffect(()=>()=>{geometry.dispose();points.dispose();},[geometry,points]);
  return <><lineSegments geometry={geometry} renderOrder={20}><shaderMaterial vertexShader={S.edgeVertex} fragmentShader={S.edgeFragment} transparent depthTest={false} depthWrite={false} blending={THREE.AdditiveBlending}/></lineSegments><points geometry={points} renderOrder={30}><shaderMaterial uniforms={uniforms} vertexShader={S.starVertex} fragmentShader={S.starFragment} transparent depthTest={false} depthWrite={false} blending={THREE.AdditiveBlending}/></points></>;
}
export function OrbitLines(){
  const orbits=useMemo(()=>[makeOrbit(1.18,.32),makeOrbit(1.26,.13),makeOrbit(1.13,.7)].map(buffer),[]);
  useEffect(()=>()=>orbits.forEach(g=>g.dispose()),[orbits]);
  const rotations: [number,number,number][]=[[.28,.2,-.35],[1.0,.25,.65],[.1,.3,-1.1]];
  return <>{orbits.map((g,i)=><lineSegments key={i} geometry={g} rotation={rotations[i]} renderOrder={5}><lineBasicMaterial color={i===1?'#b78f52':'#7d827f'} transparent opacity={i===1?.19:.12} depthWrite={false} depthTest={false} blending={THREE.AdditiveBlending}/></lineSegments>)}</>;
}
export function EvidenceLinks({records,relationships,selected}:{records:KnowledgeRecord[];relationships:Relationship[];selected:string|null}){
  const geometry=useMemo(()=>{
    const positions:number[]=[],alpha:number[]=[];const lookup=new Map(records.map(r=>[r.id,r]));
    for(const edge of relationships){const ar=lookup.get(edge.from),br=lookup.get(edge.to);if(!ar||!br)continue;
      const a=new THREE.Vector3(...recordPosition(ar)),b=new THREE.Vector3(...recordPosition(br));
      const strong=!selected||edge.from===selected||edge.to===selected;
      for(let i=0;i<32;i++)for(const t of[i/32,(i+1)/32]){const v=a.clone().lerp(b,t).normalize().multiplyScalar(1.044+Math.sin(Math.PI*t)*.025);positions.push(v.x,v.y,v.z);alpha.push(strong?(selected?.68:.26):.045);}
    }
    const g=buffer(new Float32Array(positions));g.setAttribute('aAlpha',new THREE.Float32BufferAttribute(alpha,1));return g;
  },[records,relationships,selected]);
  useEffect(()=>()=>geometry.dispose(),[geometry]);
  return <lineSegments geometry={geometry} renderOrder={40}><shaderMaterial vertexShader={S.edgeVertex} fragmentShader={S.edgeFragment} transparent depthWrite={false} depthTest={false} blending={THREE.AdditiveBlending}/></lineSegments>;
}
export function RecordNodes({records,relationships,selected,onSelect,onHover}:{records:KnowledgeRecord[];relationships:Relationship[];selected:string|null;onSelect:(id:string)=>void;onHover:(text:string|null)=>void}){
  const dpr=useThree(s=>s.viewport.dpr),gl=useThree(s=>s.gl);
  const geometry=useMemo(()=>{
    const linked=linkedRecordIds(selected,relationships),g=buffer(new Float32Array(records.flatMap(recordPosition)));
    g.setAttribute('aSize',new THREE.Float32BufferAttribute(records.map(r=>r.id===selected?155:!selected||linked.has(r.id)?110:55),1));
    g.setAttribute('aWarmth',new THREE.Float32BufferAttribute(records.map(r=>r.id===selected?1:.6),1));return g;
  },[records,relationships,selected]);
  const uniforms=useMemo(()=>({uDpr:{value:dpr}}),[dpr]);
  useEffect(()=>()=>geometry.dispose(),[geometry]);
  return <><points geometry={geometry} renderOrder={50}><shaderMaterial uniforms={uniforms} vertexShader={S.starVertex} fragmentShader={S.starFragment} transparent depthWrite={false} depthTest={false} blending={THREE.AdditiveBlending}/></points>{records.map(record=><mesh key={record.id} position={recordPosition(record)} onClick={e=>{e.stopPropagation();if(e.delta<5)onSelect(record.id);}} onPointerOver={e=>{e.stopPropagation();onHover(record.title);gl.domElement.style.cursor='pointer';}} onPointerOut={()=>{onHover(null);gl.domElement.style.cursor='grab';}}><sphereGeometry args={[.04,12,8]}/><meshBasicMaterial transparent opacity={0} depthWrite={false} depthTest={false}/></mesh>)}</>;
}
// Exported only for deterministic tests; no input record derives from this decoration.
export const decorativeSample=fibonacciPoint;
