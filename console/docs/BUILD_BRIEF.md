# ALFRED console: precise build brief

Revision 02, 27 September 2026. Owner-selected visual direction. This is an evolution of the existing console, not permission to create another generic dashboard.

## Objective

Produce one restrained, genuinely black operational workspace with a large interactive knowledge sphere, compact icon rail, one executive panel and a persistent command input. It should feel like carefully engineered equipment, not a marketing page, game HUD or stock dashboard wearing a dark theme.

The latest narrow-rail reference is the compositional target. Preserve the small metallic ALFRED emblem and wordmark at the top of the narrow rail. Do not move it into a large expanded branding panel. The rail stays collapsed at rest and reveals labels over the workspace on hover, keyboard focus or deliberate pinning.

## Fixed visual requirements

At the 1648 x 928 desktop reference viewport, reserve a 78 px left rail and a 444 px executive column, including its outer spacing. Use a 66 px header. The centre is a flexible graph workspace; the command bar is centred beneath it and occupies roughly three quarters of its width. These are implementation starting measurements, not a requirement to stretch the image on every display.

Use true black for the page and WebGL clear colour. Surfaces range from nearly black to restrained graphite. Main text is soft ivory; secondary text is a legible cool grey. Amber is reserved for the active navigation target, review emphasis and selected graph highlights. No wide neon borders, scratched textures, distressed type or backdrop photographs.

Use normal sans-serif letterforms. Headings may use restrained tracking, while body text remains readable and normally spaced. Do not add exotic science-fiction type, giant slogans or ornamental captions. The following copy must not return: "Clarity creates leverage", "Find signal", "Build understanding", "Sources before certainty", "Evidence before action". Do not display developer artefacts such as a visible "canvas" label.

## Rail interaction

The collapsed rail is useful, not merely a decorative strip. Each icon has an accessible name and a visible focus state. The expanded rail reveals labels without changing the grid column, camera, canvas dimensions or source state. Keep the rail hit area synchronised with its open state. Use a small label-reveal delay and restrained opacity/translation, not a width tween that leaves an invisible or stale overlay beside the GPU view. Preserve keyboard focus within the overlay. Escape dismisses the expansion. Pinning holds it open until explicitly unpinned. Touch users must have a click path.

Home is a quiet circular target rather than a large house badge. Search, Knowledge, Tasks, Research, Systems, Security and Settings remain visually consistent. Keep all items reachable on shorter displays.

## Graph interaction and material

Keep the existing React Three Fiber and original GLSL implementation. It must be a real interactive scene, not a screenshot, pre-rendered video or spinning CSS image. Default motion is slow rotation only. No luminance pulses, flashing lens flares, animated exposure or noise that changes every frame.

Use delicate explicit links, soft point cores and a controlled rim, with plenty of black visible through the composition. The sphere is not a map unless real geographic data is intentionally introduced. Do not claim decorative points are memory nodes. The record count must come from the actual scoped data.

People, Projects, Sources and Actions callouts open accessible record browsing. Hovering a real record exposes its name. Selecting it opens provenance and explicit neighbours. Provide a relationship-only mode, pause, reset and a list-based path that remains usable without WebGL. Stable record IDs control placement.

A quality change must not recreate the canvas. Test device-pixel-ratio changes, resize, scope changes, background tabs, reduced motion and context loss. Retain fixed exposure and a single render-loop owner. Any new shader effect must justify its information value and pass the same temporal stability checks.

## Executive panel

Use one coherent surface with fine internal separators, not four floating cards:

1. Top priorities: ordered local task rows with explicit completion state.
2. Approvals: exact proposal titles with Review and Decline. Both lead to a confirmation of the exact example effect in the demo; real authority belongs to the server later.
3. Active projects: project records with explicit fixture milestone counts. Never fabricate real-world completion percentages.
4. Recent insight: an inspectable source-backed sample, not invented live intelligence or market telemetry.

The desktop home composition should expose all four sections without hiding the final section below an unnecessary internal scroll at the reference size. Smaller screens may use deliberate scrolling; do not shrink text until it is unreadable.

## Command bar

Keep a slim, shallow-shaded input, restrained voice icon, separator and submit control. Local commands route to existing panels, while other input searches the permitted fixture scope. No arbitrary text becomes executable code. Voice remains visibly disconnected until an authorised adapter exists. Do not request microphone permission merely to animate an icon. Avoid a second permanent row of oversized function cards.

## Responsive and accessible behaviour

Retain normal DOM semantics for all operational controls. Native dialogs should trap focus, handle Escape and return focus. Record selection must have a keyboard-accessible equivalent. Respect the operating-system reduced-motion preference; manual settings may reduce motion further, not override it.

At 390 x 844, keep the command input reachable above the fold and the slim rail usable. Move the executive surface below the graph rather than squeeze it alongside. Avoid horizontal scrolling, clipped callouts and overlapping click targets. Tablet and normal laptop widths need their own captures, not a desktop image scaled down.

## Fidelity versus honesty

The reference contains illustrative dates, project percentages, large invented counts and online/security claims. Reproduce its composition and material quality, not its fictional assertions. Show a small truthful demo state; put detailed limitations in Controls, not a wall of explanatory copy on the home screen. Keep the user's actual programme names correctly spelled, particularly Velvet Accademy.

## Acceptance gates

Build and typecheck the actual source. Run the retained domain tests and additional command/projection/render-contract checks. Run real-browser tests over the production build, not only DOM snapshots or a health endpoint. Capture closed rail, expanded rail, source inspector, relationship mode, review, focus, laptop and mobile views.

Check actual sphere selection and camera drag; compare paused captures for stability; confirm that normal UI operations and quality changes preserve the context; exercise unavailable and lost/restored graphics; verify zero unintended network writes and no capture permission. Compare animated luminance samples for sudden black-frame or exposure jumps. These are bounded regression checks, not proof of universal physical-display flicker safety.

Inspect screenshots against the selected reference. Fix composition, clipping, material and interaction defects before declaring a handoff. Retain failures and the tested commit. Do not label a generated image as a running screenshot or imply a test verified hardware it did not use.

## Explicit non-goals for this increment

Do not rewrite the Python brain, replace the original web app, install a memory engine, connect accounts or microphones, merge main, deploy a public service, access a private vault or reroute the previously blocked model comparison. The next builder gets the source, exact brief, component map, working offline preview, tests and honest integration gates.
