// ALFRED original GLSL. No external textures or generated images in the sphere.
export const pointVertex=`
attribute float aStrength;attribute float aPhase;attribute float aWarmth;uniform float uTime;uniform float uDpr;varying float vAlpha;varying float vWarmth;
void main(){vec4 mv=modelViewMatrix*vec4(position,1.0);vec3 n=normalize(normalMatrix*normalize(position));float front=smoothstep(-0.15,0.9,n.z);vAlpha=(0.025+0.975*front)*(0.88+0.12*sin(uTime*0.55+aPhase));vWarmth=aWarmth;gl_PointSize=clamp(aStrength*13.0*uDpr/(-mv.z),0.65,15.0*uDpr);gl_Position=projectionMatrix*mv;}`;
export const pointFragment=`
varying float vAlpha;varying float vWarmth;
void main(){float r=length(gl_PointCoord-vec2(0.5))*2.0;if(r>1.0)discard;float core=exp(-r*r*11.0),halo=exp(-r*r*3.5)*0.18;vec3 colour=mix(vec3(0.77,0.81,0.82),vec3(1.0,0.74,0.40),vWarmth);gl_FragColor=vec4(colour*(1.12+core*.65),(core+halo)*vAlpha);}`;
export const edgeVertex=`
attribute float aAlpha;varying float vAlpha;
void main(){vec3 n=normalize(normalMatrix*normalize(position));vAlpha=aAlpha*(0.12+0.88*smoothstep(-0.25,0.85,n.z));gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`;
export const edgeFragment=`varying float vAlpha;void main(){gl_FragColor=vec4(0.78,0.76,0.67,vAlpha);}`;
export const shellVertex=`
varying vec3 vNormal;varying vec3 vEye;varying vec3 vPosition;
void main(){vec4 mv=modelViewMatrix*vec4(position,1.0);vNormal=normalize(normalMatrix*normal);vEye=normalize(-mv.xyz);vPosition=position;gl_Position=projectionMatrix*mv;}`;
export const shellFragment=`
varying vec3 vNormal;varying vec3 vEye;varying vec3 vPosition;
void main(){vec3 n=normalize(vNormal);float fresnel=pow(1.0-max(0.0,dot(n,normalize(vEye))),8.5);float light=0.28+0.72*max(0.0,dot(n,normalize(vec3(-0.25,0.8,0.5))));vec3 col=mix(vec3(0.13,0.14,0.15),vec3(0.70,0.69,0.64),light);gl_FragColor=vec4(col,fresnel*(0.08+light*0.14));}`;
export const starVertex=`uniform float uScale;uniform float uDpr;void main(){vec4 mv=modelViewMatrix*vec4(position,1.0);gl_PointSize=uScale*uDpr/(-mv.z);gl_Position=projectionMatrix*mv;}`;
export const starFragment=`
uniform float uSelected;
void main(){vec2 p=(gl_PointCoord-.5)*2.;float r=length(p);if(r>1.)discard;float halo=exp(-r*r*9.)*.14;float core=exp(-r*r*230.)*1.4;float crossLight=(exp(-abs(p.x)*110.)*exp(-abs(p.y)*9.)+exp(-abs(p.y)*110.)*exp(-abs(p.x)*9.))*.13;vec3 c=mix(vec3(1.,.77,.44),vec3(1.,.90,.70),uSelected);gl_FragColor=vec4(c*1.65,halo+core+crossLight);}`;
