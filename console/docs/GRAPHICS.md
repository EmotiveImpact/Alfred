# ALFRED graphics implementation: refinement 02

This replaces the v0.1 graphics description, retained verbatim under `archive/GRAPHICS-v01.md`. That older version describes a time-varying brightness effect which is no longer used.

## Components and rendering ownership

`scene/KnowledgeSphere.tsx` owns the persistent canvas, camera controls, visibility/motion state and graphics-loss handling. `scene/layers.tsx` separates Shell, ParticleField, Lattice, OrbitLines, EvidenceLinks and RecordNodes. `scene/RenderPipeline.tsx` owns the single final render callback and the RenderPass -> UnrealBloomPass -> OutputPass chain. `scene/shaders.ts` contains the original point, edge, shell and star shaders.

The UI remains normal React DOM with CSS and SVG. Shaders supply the signature sphere and selection materials, not the text, forms, navigation labels or executive panel. This is a deliberate design boundary: the useful controls remain crisp and readable, while a small part of the screen carries the movement and light.

## Stable light, not flashing

The shaders have no time-driven brightness uniform or phase-driven pulse. Exposure is fixed at 1 with ACES tone mapping. Ambient animation is slow rotation, not a periodic light flare. The canvas is not keyed by quality, workspace or selection. Task and dialog changes preserve the renderer and stable record arrays.

The expanding rail overlays a fixed grid column, so opening its labels does not resize the canvas. The local clock is isolated in the header. The composer is created and disposed in a matching effect and one callback owns the final draw. Transparent additive layers have explicit render order and do not write depth. Soft point edges and multisampled targets reduce harsh subpixel changes.

Pause, operating-system reduced motion, hidden-document state and relationship-only mode use demand rendering. Ambient rendering also pauses while a modal is open. The provenance inspector appears immediately without an opacity transition. Context loss is visible, record browsing remains available, and the browser suite exercises restoration.

These measures address plausible causes of the reported flashing. A twelve-frame luminance sample and paused-pixel comparison are bounded regressions, not a certification that every physical monitor, browser, driver or GPU is flicker-free.

## Geometry and semantics

High quality starts with 44,000 decorative point candidates; balanced starts with 16,000. A deterministic procedural filter retains an organic subset. The decorative lattice uses 280 points and unique bounded nearest-neighbour segments. The background field, lattice and orbit lines are not memory records or evidence.

Actual fixture records use ID-based positions from `domain/projection.ts`. Display-name equality is not entity identity. Explicit relationship arcs come only from the current scope's relationship list. Their provenance is exposed in the inspector.

Field mode combines material decoration and real fixture records. Relationships mode removes the decorative shell, points, lattice and orbits. It shows only those records and supported fixture links. Few links should produce a sparse graph, not fabricated complexity.

There is no Earth texture, country map, remote image or video. The appearance is an abstract knowledge sphere, not geographical data or model hidden reasoning.

## Portrait framing correction

`scene/camera.ts` provides `cameraDistanceForViewport` and the shared 34-degree field of view. The desktop distance remains 4. Portrait views fit the sphere into the narrower dimension. The fitted control state is saved so switching to relationship mode does not restore the old close-up camera.

`styles.css` remains the main material/layout stylesheet. The final explicit portrait correction in `refinements.css`, imported after it, keeps the mobile canvas inside its actual workspace rather than extending it behind the rail and beyond the right edge. Five camera tests cover the desktop baseline, complete-sphere projection at three viewport shapes and safe handling of an unmeasured viewport.

The browser capture is still required: mathematical framing tests alone do not establish a usable phone layout.

## Remaining limits

The renderer is tuned for a bounded small fixture set, not arbitrary million-node graphs. The model's ingress ceilings are not performance guarantees. Stable IDs prevent reorder jitter but do not supply collision-free production clustering, complete label placement or large-graph level of detail.

Chromium with SwiftShader proves that the real shaders and interactions ran. It is not a physical-GPU frame-rate, thermal, battery or display-fidelity measurement. Safari, Firefox, target-device GPU checks and a complete accessibility audit remain separate gates.

Keep these distinctions in future delivery claims. Do not replace a failing hardware check with a generated image or a test that only confirms a canvas element exists.
