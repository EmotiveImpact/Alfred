/** Original ALFRED GLSL. Brightness has no time uniform or oscillation. */
export const pointVertex = `
attribute float aStrength; attribute float aWarmth;
uniform float uDpr;
varying float vAlpha; varying float vWarmth;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vec3 n = normalize(normalMatrix * normalize(position));
  vAlpha = mix(0.015, 0.62, smoothstep(-0.08, 0.82, n.z));
  vWarmth = aWarmth;
  gl_PointSize = clamp(aStrength * 12.0 * uDpr / -mv.z, 1.35 * uDpr, 8.0 * uDpr);
  gl_Position = projectionMatrix * mv;
}`;
export const pointFragment = `
varying float vAlpha; varying float vWarmth;
void main() {
  float r = length(gl_PointCoord - vec2(0.5)) * 2.0;
  float alpha = (1.0 - smoothstep(0.15, 1.0, r)) * vAlpha;
  vec3 colour = mix(vec3(0.61, 0.67, 0.70), vec3(0.94, 0.68, 0.32), vWarmth);
  gl_FragColor = vec4(colour, alpha);
}`;
export const edgeVertex = `
attribute float aAlpha; varying float vAlpha;
void main() {
  vec3 n = normalize(normalMatrix * normalize(position));
  vAlpha = aAlpha * mix(0.045, 0.85, smoothstep(-0.10, 0.8, n.z));
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;
export const edgeFragment = `
varying float vAlpha;
void main() { gl_FragColor = vec4(0.61, 0.61, 0.56, vAlpha); }
`;
export const shellVertex = `
varying vec3 vNormal; varying vec3 vEye;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vNormal = normalize(normalMatrix * normal); vEye = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}`;
export const shellFragment = `
varying vec3 vNormal; varying vec3 vEye;
void main() {
  vec3 n = normalize(vNormal);
  float rim = pow(1.0 - max(0.0, dot(n, normalize(vEye))), 5.8);
  float key = pow(max(0.0, dot(n, normalize(vec3(-0.35,0.85,0.3)))), 5.0);
  float edgeKey = 0.20 + 0.80 * max(0.0, dot(n, normalize(vec3(-0.25,0.9,0.1))));
  vec3 edge = mix(vec3(0.26,0.29,0.31),vec3(0.79,0.71,0.55),edgeKey);
  vec3 base = vec3(0.002,0.003,0.004) + vec3(0.016,0.018,0.019) * key;
  gl_FragColor = vec4(base + edge * rim * (0.11 + 0.40 * edgeKey), 1.0);
}`;
export const starVertex = `
attribute float aSize; attribute float aWarmth;
uniform float uDpr;
varying float vVisibility; varying float vWarmth;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vec3 n = normalize(normalMatrix * normalize(position));
  vVisibility = mix(0.06, 1.0, smoothstep(-0.05, 0.7, n.z)); vWarmth = aWarmth;
  gl_PointSize = aSize * uDpr / -mv.z;
  gl_Position = projectionMatrix * mv;
}`;
export const starFragment = `
varying float vVisibility; varying float vWarmth;
void main() {
  vec2 p = (gl_PointCoord - 0.5) * 2.0;
  float r = length(p);
  float core = exp(-r*r*170.0);
  float halo = exp(-r*r*12.0)*0.12;
  float rays = (exp(-abs(p.x)*95.0)*exp(-abs(p.y)*10.0) + exp(-abs(p.y)*95.0)*exp(-abs(p.x)*10.0))*0.12;
  vec3 c = mix(vec3(1.0,1.0,0.95),vec3(1.0,0.75,0.40),vWarmth);
  gl_FragColor = vec4(c*1.35, (core+halo+rays)*vVisibility);
}`;
