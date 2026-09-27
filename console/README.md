# ALFRED operational console / refinement 02

A direct evolution of the existing React/TypeScript console, with the owner's slim-rail, true-black visual direction. It uses actual Three.js / React Three Fiber geometry and original GLSL, not an image of a dashboard.

Start with [component architecture](docs/COMPONENT_ARCHITECTURE.md), [precise build brief](docs/BUILD_BRIEF.md) and [next-builder prompt](docs/NEXT_BUILDER.md). The original v0.1 receipt remains historical; consult the new refinement receipt for current tested source and limitations.

## Run or preview

Open the delivered standalone `ALFRED-Console.html` in a browser with WebGL2. It contains the compiled application and licence notices and needs no network requests. Editable source remains in this directory.

```sh
cd console
npm ci
npm run dev
```

Use Node 22.12+ and npm 11.20.0 with the existing lock. Development and preview bind to loopback. The underlying package retains its initial private development version; this is visual/architectural revision 02.

```sh
npm run build
npm test
npx playwright install chromium
npm run test:browser
npm run standalone
```

## What changed

The small ALFRED logo now sits inside the narrow icon rail. Hover/focus/click expands labels over the workspace without resizing the canvas; Escape and pin are supported. The headline/slogan block is removed. Priorities, approvals, projects and a source-backed sample insight share one executive surface. The command bar remains persistent.

The monolithic screen is split into explicit state, navigation, stage, executive sections, command, inspector, dialogs and rendering pipeline components. Scene brightness has no time oscillation. A single stable composer owns rendering; scope, task and quality changes do not replace the WebGL canvas. The scene uses explicit layer order and bounded soft points. See the evidence for measured temporal and context-lifecycle checks.

Field mode combines decorative geometry and fixture records. Relationships mode removes decoration and shows only explicit records and links. Stable record IDs determine layout. Browse, search and inspection remain usable without WebGL.

## Actual capability boundary

All data is fictional. The known project names are context, not current status or live telemetry. Reviews and priorities modify this browser session only. No model, microphone, account, private vault or live backend approval is connected. No records or credentials are persisted to browser storage.

Commands such as `/brief`, `/tasks`, `/settings`, `/handoff` and scope names route locally; other text is literal scoped search. Unknown text is never executable code. The microphone control explains the disconnected state without requesting capture permission.

`src/integration/ConsoleReadPort.ts` is a proposed contract for the next builder, not an implemented HTTP client or a claim about existing routes. Preserve server-side authority and inspect actual Python interfaces before connecting it.

## Repository continuity

Base: merged main `03e946fc3fb6fe0b540abe5ff52204de6f0f99ed`. The older console PR #13 is already merged. New branch: `feat/alfred-console-refinement-2026-09-27`. Do not overwrite the brain's root handoff or the existing Python/web application. No main merge or deployment is implied by this revision.

There are no font binaries, remote textures or new runtime dependencies in this refinement. System sans-serif fonts and the existing icon library are retained. The sphere is an abstract procedural knowledge view, not an Earth map.

Physical-GPU performance, final on-device visual tuning, Firefox/Safari acceptance, full accessibility review, scalable large-graph layout and live brain/voice integration remain separate gates. Software-rendered Chromium evidence does not prove those properties.
