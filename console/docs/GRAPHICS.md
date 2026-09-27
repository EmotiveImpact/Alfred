# Graphics implementation

React Three Fiber mounts an actual Three.js WebGL2 scene inside an otherwise normal DOM workspace. The camera is perspective; drag rotates the view through OrbitControls with pan/zoom disabled. The scene uses no remote textures, Earth map image, baked video or generated screenshot.

## Original GLSL materials

`src/scene/shaders.ts` contains point, edge, shell and star materials. Points have per-point strength, phase and warmth, view-normal depth fading, radial cores and faint halos. Time changes decorative luminance, never record status. Edges have view-dependent alpha; typed relationship geometry is separate from the decorative lattice. The shell has a restrained Fresnel-like illuminated edge. Record nodes have compact high-energy centres and faint glints.

Three's EffectComposer runs RenderPass, UnrealBloomPass and OutputPass. ACES tone mapping and restrained bloom provide the finish. Pure black is shared by the canvas and DOM to avoid a visible rectangular seam. No perpetual CSS blur substitutes for real geometry.

## Bounds and controls

The refined high field begins with 40,000 candidate positions and retains a deterministic organic subset. Balanced begins with 14,000. These are decorative candidates, not entity counts. The lattice is 160 nodes. Record nodes and explicit fixture arcs are separate geometries.

Pixel ratio is capped by profile. Animation uses delta clamping, and paused/reduced-motion/hidden views switch to demand rendering. Controls remain interactive. Geometry and composer resources are disposed on replacement and unmount.

The current geometry layout is for a small fixture set. The contract rejects more than 1,000 records or 4,000 relationships, but that is an ingress ceiling, not a guarantee that every combination is an appropriate real-time workload. Do not load a large production graph without measured level-of-detail and layout work.

## Important limitations

The point field is procedural rather than geographic. Its clusters do not represent countries or knowledge density. The reference's tiny star/particle placement is not reproduced pixel-for-pixel. Colour and shading can vary by renderer and display.

The field is intentionally calm rather than audio-reactive because no audio source is connected. A future audio adapter must provide a measured amplitude envelope with explicit permission; do not animate a fake listening state.

Software rendering in CI must be distinguished from physical-GPU performance. Retain the actual renderer string and test environment in the delivery evidence. Test WebGL context loss/restoration and large-scope changes as part of hardening before production.
