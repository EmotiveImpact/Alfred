# ALFRED / Obsidian console

A working React/TypeScript presentation build for the owner's approved black intelligence console. The knowledge sphere is actual Three.js geometry rendered through React Three Fiber and original GLSL, not a background image or video.

**This is a frontend design build with fictional fixtures. It is not the ALFRED brain.** No model, microphone, account, repository, device or backend is connected. Reviews change this browser session only. Reloading resets them. Project names in the fixture do not assert current project status.

## Open the preview

The delivered `ALFRED-Console.html` is a standalone offline build. Open it in a browser with WebGL2 enabled. It makes no network requests. The same application can also be run through Vite:

```sh
cd console
npm ci
npm run dev
```

Node 22.12 or later is required. Use npm 11.20.0 and the resolved lockfile; npm 10.9.8 failed dependency resolution during the initial build. Development and preview bind to loopback. Read `docs/BUILDER_HANDOFF.md` before connecting services.

```sh
npm run build
npm test
npx playwright install chromium
npm run test:browser
npm run standalone
```

The full repository's Python regression remains separate: `python3 -m unittest discover -s tests -v` from the repository root. Do not execute the quarantined third-party research archive.

## Use it

Switch Personal, Work, Operation, Research or Systems to change the fixture scope. Drag the sphere to rotate it. Select its visible bright record nodes or use the category labels / Browse control for keyboard-accessible inspection. The inspector shows exact fixture provenance and explicitly authored relationships.

Press Ctrl/Cmd+K to search. The command bar accepts local commands such as `/brief`, `/tasks`, `/settings`, `/handoff`, a scope name, or record search. It is not an AI chat pretending to answer arbitrary questions. Review an example draft only after reading its exact local effect. Use Controls to change graphics quality, pause motion, reduce motion, export local review receipts or reset the demonstration.

A missing WebGL2 context leaves record navigation working and shows an explicit graphics-unavailable state. OS reduced-motion preference takes precedence over the manual setting. The microphone button explains that nothing is listening; it never requests capture permission.

## Architectural boundary

`src/domain/model.ts` describes the **presentation fixture contract**, not an existing HTTP endpoint or security boundary. The existing Python and vanilla-JavaScript application is unchanged. The next builder must implement and test a deliberately scoped adapter, not point the UI at guessed endpoints or promote local demo receipts into real approvals.

This directory is additive to ALFRED v0.8 at `22e64567f69508928b164d55c578834abcb404e8`. Its visual brief supersedes the old provisional appearance only in this new presentation lane. Preserve the existing app while the brain work continues.

## Source map

- `src/scene`: deterministic field geometry, original GLSL materials, bloom, camera, explicit record nodes and evidence links.
- `src/domain`: fictional records, strict scope selectors, search, local review reducer and transient receipts.
- `src/components/Dialog.tsx`: native modal dialog with Escape handling and focus return.
- `src/App.tsx`: single operational workspace and functional controls.
- `src/styles.css`, `src/refinements.css`: material, layout and responsive treatment.
- `tests`, `e2e`: deterministic domain checks and real-browser rendering/interaction tests.
- `tools/standalone.mjs`: offline preview packer, including runtime dependency notices. It rejects unexpected chunk splitting rather than silently dropping assets.

No fonts or decorative image dependencies are included. System sans-serif fonts are used. The small original ALFRED mark is SVG. The sphere uses no downloaded textures.

## What is not established

No production performance guarantee, GPU-device certification, Safari/Firefox acceptance, exhaustive accessibility audit, production tenancy, real brain integration or exact pixel identity with the generated reference is claimed. CI rendering on software-backed Chromium is not a benchmark of the owner's Mac. Check the actual evidence receipt for completed tests and retained visual differences.
