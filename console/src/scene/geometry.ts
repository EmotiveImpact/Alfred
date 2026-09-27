/** Deterministic visual lattice. These points are decoration, not knowledge records. */
export function randomSeed(seed:number){let a=seed|0;return()=>{a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}
export type Point3=[number,number,number];
export function fibonacciPoint(i:number,total:number,radius=1):Point3{const y=1-2*(i+.5)/total,r=Math.sqrt(Math.max(0,1-y*y)),a=i*Math.PI*(3-Math.sqrt(5));return[Math.cos(a)*r*radius,y*radius,Math.sin(a)*r*radius];}
export function makePointField(count:number,seed=814):{positions:Float32Array;strengths:Float32Array;phases:Float32Array;warmth:Float32Array}{
 const rng=randomSeed(seed),p:number[]=[],s:number[]=[],ph:number[]=[],w:number[]=[];
 for(let i=0;i<count;i++){const v=fibonacciPoint(i,count),[x,y,z]=v;const f=Math.sin(x*13+y*5+Math.sin(z*9))*Math.cos(z*11-y*8)+Math.sin(y*19+z*6)*.6+Math.cos(x*22-z*16)*.3;if(f<-.05&&rng()>.10)continue;const radius=1+(rng()-.5)*.013;p.push(x*radius,y*radius,z*radius);s.push(.36+rng()*.55+(rng()>.991?1.8:0));ph.push(rng()*Math.PI*2);w.push(rng()>.65?.85:.2);}
 return{positions:new Float32Array(p),strengths:new Float32Array(s),phases:new Float32Array(ph),warmth:new Float32Array(w)};
}
export function makeLattice(count=160):{positions:Float32Array;nodes:Point3[];alpha:Float32Array}{
 const rng=randomSeed(45),nodes:Point3[]=[],p:number[]=[],alpha:number[]=[];for(let i=0;i<count;i++)nodes.push(fibonacciPoint(i,count,1.012));
 for(let i=0;i<count;i++){const pairs=nodes.map((v,j)=>({j,d:Math.hypot(v[0]-nodes[i][0],v[1]-nodes[i][1],v[2]-nodes[i][2])})).filter(v=>v.j>i).sort((a,b)=>a.d-b.d).slice(0,3);for(const{j,d}of pairs){if(d>.76)continue;p.push(...nodes[i],...nodes[j]);const a=.15+rng()*.22;alpha.push(a,a);}if(i%7===0){const j=(i+47)%count;p.push(...nodes[i],...nodes[j]);alpha.push(.08,.08);}}
 return{positions:new Float32Array(p),nodes,alpha:new Float32Array(alpha)};
}
export function makeOrbit(radius:number,tilt:number,segments=240):Float32Array{const p:number[]=[];for(let i=0;i<segments;i++){const a=i/segments*Math.PI*2,b=(i+1)/segments*Math.PI*2;for(const t of[a,b])p.push(radius*Math.cos(t),radius*Math.sin(t)*Math.sin(tilt),radius*Math.sin(t)*Math.cos(tilt));}return new Float32Array(p);}
