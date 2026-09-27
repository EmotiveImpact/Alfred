/** Deterministic visual lattice. These points are decoration, not knowledge records. */
export function randomSeed(seed:number){let a=seed|0;return()=>{a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}
export type Point3=[number,number,number];
export function fibonacciPoint(i:number,total:number,radius=1):Point3{const y=1-2*(i+.5)/total,r=Math.sqrt(Math.max(0,1-y*y)),a=i*Math.PI*(3-Math.sqrt(5));return[Math.cos(a)*r*radius,y*radius,Math.sin(a)*r*radius];}
export function makePointField(count:number,seed=814):{positions:Float32Array;strengths:Float32Array;phases:Float32Array;warmth:Float32Array}{
 const rng=randomSeed(seed),p:number[]=[],s:number[]=[],ph:number[]=[],w:number[]=[];
 for(let i=0;i<count;i++){
  const v=fibonacciPoint(i,count);
  const jitter=Math.sqrt(4*Math.PI/count)*.85;
  let x=v[0]+(rng()-.5)*jitter,y=v[1]+(rng()-.5)*jitter,z=v[2]+(rng()-.5)*jitter;
  const length=Math.hypot(x,y,z);x/=length;y/=length;z/=length;
  const broad=Math.sin(x*3.7+y*1.8+Math.sin(z*3.2))*.65+Math.cos(y*4.6-z*2.6+x*1.2)*.45;
  const detail=Math.sin(x*17+z*6)*Math.cos(y*21-z*13)*.18+Math.sin(y*31+x*11)*.08;
  const cluster=broad+detail>.24;
  if(!cluster&&rng()>.025)continue;
  const radius=1+(rng()-.5)*.007;
  p.push(x*radius,y*radius,z*radius);
  s.push(cluster?.33+rng()*.52+(rng()>.998?1.65:0):.15+rng()*.18);
  ph.push(rng()*Math.PI*2);w.push(rng()>.94?.92:rng()*.16);
 }
 return{positions:new Float32Array(p),strengths:new Float32Array(s),phases:new Float32Array(ph),warmth:new Float32Array(w)};
}
export function makeLattice(count=160):{positions:Float32Array;nodes:Point3[];alpha:Float32Array}{
 const rng=randomSeed(45),nodes:Point3[]=[],p:number[]=[],alpha:number[]=[];
 for(let i=0;i<count;i++)nodes.push(fibonacciPoint(i,count,1.012));
 const seen=new Set<string>();
 for(let i=0;i<count;i++){
  const nearest=nodes.map((v,j)=>({j,d:Math.hypot(v[0]-nodes[i][0],v[1]-nodes[i][1],v[2]-nodes[i][2])})).filter(v=>v.j!==i).sort((a,b)=>a.d-b.d).slice(0,4);
  for(const {j,d} of nearest){const key=`${Math.min(i,j)}:${Math.max(i,j)}`;if(d>.48||seen.has(key))continue;seen.add(key);p.push(...nodes[i],...nodes[j]);const a=.07+rng()*.07;alpha.push(a,a);}
 }
 return{positions:new Float32Array(p),nodes,alpha:new Float32Array(alpha)};
}
export function makeOrbit(radius:number,tilt:number,segments=240):Float32Array{const p:number[]=[];for(let i=0;i<segments;i++){const a=i/segments*Math.PI*2,b=(i+1)/segments*Math.PI*2;for(const t of[a,b])p.push(radius*Math.cos(t),radius*Math.sin(t)*Math.sin(tilt),radius*Math.sin(t)*Math.cos(tilt));}return new Float32Array(p);}
