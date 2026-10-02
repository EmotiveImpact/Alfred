# ALFRED console: exact component architecture

Revision 02, 27 September 2026. This describes the implemented presentation architecture, except where a connection is explicitly marked as proposed.

## Source and scope

Continue `EmotiveImpact/Alfred`, branch `feat/alfred-console-refinement-2026-09-27`. This increment starts from merged main `03e946fc3fb6fe0b540abe5ff52204de6f0f99ed`. The earlier console PR #13 is merged, not still awaiting integration. Its `console/` implementation is the starting source, not an HTML screenshot to reconstruct.

The React/TypeScript source produces both a normal Vite build and the self-contained `ALFRED-Console.html`. The HTML is a generated distribution, not the canonical editable source. The Python application, existing `web/` interface and governed-memory programme remain separate and unchanged by this presentation increment.

## Actual component tree

```text
App
└── ConsoleProvider                         state/ConsoleProvider.tsx
    └── ConsoleShell                        App.tsx
        ├── NavigationRail                  components/NavigationRail.tsx
        │   ├── small metallic ALFRED mark
        │   ├── icon navigation / labels
        │   └── hover, focus, click, pin controller
        ├── WorkspaceHeader                 components/WorkspaceHeader.tsx
        │   ├── workspace selector
        │   ├── explicit demonstration status
        │   ├── local clock
        │   └── search / focus controls
        ├── main.workspace
        │   ├── KnowledgeStage              components/KnowledgeStage.tsx
        │   │   ├── KnowledgeSphere         scene/KnowledgeSphere.tsx
        │   │   │   └── GraphScene
        │   │   │       ├── Shell            scene/layers.tsx
        │   │   │       ├── ParticleField
        │   │   │       ├── Lattice
        │   │   │       ├── OrbitLines
        │   │   │       ├── EvidenceLinks
        │   │   │       ├── RecordNodes
        │   │   │       └── RenderPipeline   scene/RenderPipeline.tsx
        │   │   ├── four accessible category callouts
        │   │   └── field / relationships / pause / reset / browse
        │   └── CommandBar                  components/CommandBar.tsx
        ├── ExecutivePanel                  components/ExecutivePanel.tsx
        │   ├── PrioritySection
        │   ├── ApprovalSection
        │   ├── ProjectsSection
        │   └── InsightSection
        ├── RecordInspector                 components/RecordInspector.tsx
        ├── ConsoleDialogs                  components/ConsoleDialogs.tsx
        │   └── Dialog                      components/Dialog.tsx
        └── transient status toast
```

## Ownership and update boundaries

| Module | Owns | Must not own |
|---|---|---|
| ConsoleProvider | Transient selected scope, record, graph mode, dialogs, demo task/review state, search/command input and status. | Authentication, live approvals, source truth, model execution, audio capture. |
| NavigationRail | Open/closed/pinned presentation state and accessible navigation commands. | Workspace grants, camera dimensions or graph data. |
| WorkspaceHeader | Local clock and scope selection controls. | Continuous graph updates. Its timer is local to this component. |
| KnowledgeStage | Graph presentation mode, accessible category entry points and renderer controls. | Data inference or permission decisions. |
| KnowledgeSphere | Canvas lifecycle, camera, motion policy, context loss and recovery. | Application-wide state or execution authority. |
| RenderPipeline | Exactly one post-processing render call, targets, bloom, output conversion and size/DPR updates. | Provider state changes on every animation frame. |
| ExecutivePanel | A compact projection of the current scope's priorities, proposals, sample milestones and source-backed example insight. | Invented live progress, budgets, health indicators or activity. |
| RecordInspector | Selected record, original source/revision, explicit neighbours and export. | Merging same-name entities or inventing missing links. |
| ConsoleDialogs | Bounded forms, local search, exact demo review confirmation, settings and integration explanations. | Turning input text into shell commands or silently requesting permissions. |

`domain/model.ts` and `domain/fixtures.ts` preserve the previous fixture schema and reducer. `domain/commands.ts` is the deterministic local command parser. `domain/projection.ts` supplies stable ID-based node placement, explicit neighbours and declared demo milestones. Visual code must not redefine a domain decision for convenience.

## Data flow now

```text
Fictional fixtures
  -> existing scoped selectors and reducer
  -> memoised records + explicit relationships
  -> DOM panels and renderer

User interaction
  -> typed UI intent
  -> local reducer / search / inspection
  -> local state + clearly labelled demonstration receipt
```

A changed priority or open dialog does not replace the memoised record array. A clock tick does not pass through the provider. These are deliberate rendering boundaries, not merely style conventions.

There are five fixture scopes, selected in the header: Personal, Work, Operations, Research and Systems. The rail identifies activities, not permissions. Neither the selector nor a displayed record confers access.

## The knowledge sphere has two distinct meanings

**Field** combines an original decorative spherical material with genuine fixture record nodes and separately rendered explicit fixture links. Tiny background particles, lattice vertices and orbit lines are not entities, source counts or model reasoning. The organic distribution is procedural, not a geographical Earth map or density estimate.

**Relationships** removes the decorative shell, particles, lattice and orbits. Only current-scope records and explicit links remain. The inspector is the authoritative explanation of a link. A sparse view is correct when the dataset has few supported links; never pad it with fictitious knowledge.

Record positions come from stable record ID plus category, not input-array order. Reordering or filtering unrelated records does not randomly reposition an existing node. This is a bounded small-graph layout, not a claim of scalable collision-free layout for an arbitrary production graph. Large graphs need measured clustering, label placement and level of detail.

## Rendering and flashing mitigation

The implementation removes time-driven luminance from the GLSL. There is no `uTime` brightness pulse or phase-controlled flashing. The only ambient motion is slow rotation. Tone mapping and exposure remain fixed.

The WebGL canvas is not keyed by scope, quality or selected item. Hover expansion overlays the page and leaves the canvas rectangle unchanged. Quality updates its existing pixel ratio and scene detail instead of destroying the context. Ordinary task, dialog and selection changes retain the renderer.

The post-processing chain is:

```text
RenderPass -> restrained UnrealBloomPass -> OutputPass
```

One `useFrame` callback owns the final draw. The composer is allocated and disposed within a matching effect, avoiding use of an already-disposed memoised composer during development lifecycle checks. Explicit layer order is shell 0, orbit 5, field 10, lattice 20, stars 30, evidence 40 and records 50. Additive transparent layers do not write depth; view-dependent fading keeps distant geometry subdued. The opaque shell supplies material depth.

Soft point edges and bounded point sizes reduce unstable tiny highlights. Anti-aliased multisample render targets are used. Paused, reduced-motion, hidden-document and relationship-only views use demand rendering. Controls remain interactive. These changes address plausible sources of the reported flashing; only the measured evidence can establish what was reproduced on a given device.

The browser tests sample multiple actual rendered frames, compare paused pixel captures, check the renderer identity across UI/quality changes, and exercise context loss and restoration. Software-browser acceptance is not a physical-screen flicker certification or GPU-performance promise.

## DOM and shaders

Use shaders for the sphere and its selected-node material, not for text, buttons, forms or the executive panel. CSS supplies shallow graphite shading, fine borders and restrained state transitions. No full-screen animated light pass is needed to make the interface feel alive. Most of the console should be still while the graph responds to the user.

The small ALFRED mark is a scalable original SVG. Other interface icons use the existing Phosphor dependency. The stack and dependency lock are retained; no large UI framework is introduced for this refinement.

## Proposed connection to the brain

`integration/ConsoleReadPort.ts` is a typed handoff proposal, not an implemented client or a declaration that matching endpoints exist. It defines permissioned workspace discovery, abortable projection/inspection reads, evidence references, note-reference versus reviewed-claim edges and explicit connection states. Its scope guard checks structure, not authentication or truth.

The integration builder must inspect the actual Python routes and return shapes before implementing an adapter. Start with read-only source/claim projection. Use server-issued scope and grant revisions, cancel obsolete requests, and clear selected records on logout, revocation or scope change. Never retrieve all private data and rely on visual filtering alone.

Connect conversation/context through the existing bounded queue. Preserve the distinction between excerpts, interpretations and withheld answers. Connect action review only through the real exact-approval, dispatch and result ledger. The demo reducer and its local receipts must never be converted into live authority by casting a type or toggling a flag.

## Preserved memory programme

Main's governed-memory plan calls for selected-vault compatibility (M01), identity/grants (M02), reviewed-memory contextual retrieval (M03) and lifecycle controls (M05), among other jobs. These are independently specified implementation gates, not features delivered by this console. Obsidian remains optional authoring over user-owned Markdown; it is not the console's database or a prerequisite for rendering.

The intended eventual loop is source -> permitted evidence -> reviewed memory/context -> answer with provenance -> separately approved action -> durable result. The console makes that loop inspectable without replacing its authority.
