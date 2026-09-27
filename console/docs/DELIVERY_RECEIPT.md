# ALFRED Obsidian console / delivery receipt

Date: 27 September 2026. Frontend design build v0.1.0. Draft PR #13 in EmotiveImpact/Alfred.

## Exact code and verification

- UI branch: `feat/alfred-obsidian-console-2026-09-27`.
- Tested application commit: `50853d5150130d4fe5aff730278cb86713eedfee`.
- Tested tree: `842d6e38ead484ec1e856d38d636f45fa726a71d`.
- Brain foundation: `22e64567f69508928b164d55c578834abcb404e8`, branch `feat/alfred-reviewed-memory-2026-09-26`.
- GitHub Actions run: `36284767255`.
- Console job: `108523305466`, success.
- Existing Python core job: `108523305313`, success.
- Artifact: `10919579923`, `obsidian-console-preview`.

This receipt is a documentation-only addition after the tested application commit. It does not change the application, shaders, tests, dependency lock or workflow. Main remains unmerged; there is no hosted deployment. The Python core, existing web application and brain handoff were not modified.

## Completed checks

The TypeScript check and production Vite build passed. All **33 deterministic unit tests** passed. All **23 real-browser scenarios** passed, with zero failed, skipped or flaky scenarios in the retained JSON report. The unchanged first-party Python regression also passed in its independent job.

Browser checks cover the actual WebGL2 scene, all five scopes, scoped keyboard search, category filters, source inspection, exact local-review confirmation, priority reset, command routing, script-shaped search input, the disconnected microphone state, quality controls, focus, OS reduced motion, graphics-unavailable navigation, four responsive widths and the self-contained offline preview with no network requests. Additional checks select a real mesh node, prove paused render stability and resumed change, drag the actual camera, check graph-label bounds, verify a settled opaque inspector, and keep the mobile command rail above navigation. A short recording is captured from the running application.

The final dependency audit reported **zero known vulnerabilities** across 177 resolved dependencies, using the committed lock and npm 11.20.0. This is an audit result at the time of the build, not a security guarantee. Production JavaScript was 1,358.94 kB uncompressed / 381.18 kB gzip; CSS was 38.61 kB / 8.90 kB gzip. Source maps are development evidence, not required by the standalone preview.

Renderer: `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)`. The browser tests ran on software-backed Chromium. They prove real rendering and interaction, not the frame rate, battery cost or visual identity of a particular physical GPU.

## Visual inspection and refinement

Actual application screenshots were inspected against the owner-approved 1648 x 928 console reference. The build retains the left navigation, large central sphere, compact operational column, bottom command rail, true-black field, graphite surfaces, ivory text and restrained amber.

The initial render had a visible canvas-background seam, a heavy lattice and an overly thick sphere edge. Those were refined. The second browser run correctly found the header intercepting the People control; the control was repositioned rather than force-clicked in the test. The mobile command rail was moved clear of fixed navigation. The final inspector screenshot waits for its real transition to settle. The refined point field has deterministic spatial jitter rather than obvious uniform rows.

This is not a pixel-identical reproduction of a generated image. The field is procedural, not an Earth texture. Fine illumination and typography remain subject to physical-device review. Invented project percentages, fake online states and the reference's office photograph were deliberately not reproduced. Fixture counts and disconnected states are explicit.

## Handoff assets

The CI artifact contains the source, offline `ALFRED-Console.html`, screenshots, raw browser results, build/unit logs, dependency audit and a 12.96-second actual interaction recording. The user-facing builder pack retains the source, exact approved reference, those evidence files, runtime licence notices and a next-builder prompt. It excludes node_modules, toolchain archives and font files. CI artifacts expire after seven days; the user-facing pack preserves their useful contents, while committed source and tests make regeneration possible.

Standalone HTML SHA-256: `48629fcc13e3985c9c4a34354472d78d2edf3b17e2d41596bc74453538bc4183`.

Desktop screenshot SHA-256: `8b0a227eec3238331e156b6a46ec27c020fa515bbc829efc9ea39c03f3d2ea70`.

Approved reference SHA-256: `6bace22b338a9897a182ffb82cd4ad04719ae60435f33b78e7aa13c715acdb94`.

## Boundaries and next builder

The console uses fictional fixtures. No model, microphone, external account, device, repository operation or live approval is connected. Search and commands run only local presentation logic. Review receipts are transient demonstrations, not server authority. Decorative vertices and lines are not knowledge records or evidence.

Read `CONSOLE_HANDOFF.md`, `console/AGENTS.md`, `console/README.md`, `console/docs/BUILDER_HANDOFF.md`, `console/docs/GRAPHICS.md` and the existing root brain handoff. Refresh real remote refs before integrating. Preserve the chosen interface and connect the brain through an explicitly authenticated and scoped adapter, without relaxing loopback/Origin policy or changing note/claim/approval semantics.

Open gates: real brain integration; exact server-authorised action lifecycle; live voice; physical-GPU measurements; Safari/Firefox verification; comprehensive accessibility review; context-loss recovery hardening; and scalable layout for large permitted graphs. This delivery does not claim those gates are complete.
