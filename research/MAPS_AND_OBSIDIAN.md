# MAPS, Obsidian and ALFRED's knowledge architecture

Assessment: 26 September 2026. This is an original interpretation, not a copied prompt pack.

## Source inspected

Pav / Automation Orbit's MAPS guide:
https://github.com/pavrus117/ai-os-maps-guide/blob/066dc83a29bac80696872f3d4f8ce25f31cd439b/README.md

Reviewed README blob: `630ddc88fd525af7373c8f77989f9bfbc9815245`.
The repository lists a README and companion PDF. The README describes the PDF as the same
guide; this assessment reviewed the README, not a separate PDF analysis. No explicit
reuse licence was identified in those inspected materials. Its prompt cards and PDF
have therefore not been copied into ALFRED. General architectural ideas are discussed
with attribution and implemented through original ALFRED code.

## Is it useful?

Yes, as a practical personal-workflow design reference. The guide separates Memory,
Agent, Pulse and Screen. It emphasises navigable source files, checked references,
restricted unattended work and a dashboard that is a view over underlying records.
Those principles fit ALFRED's continuity goal. It is not a ready-made agent runtime,
proven multi-user security boundary or operational safety architecture.

The author's small workspace comparison is not an ALFRED benchmark. No cost, latency or
token-saving percentage from that example is adopted as a product claim. Subscription
and hosting statements are not treated as verified current commercial terms here.

## What we adopt, adapt and reject

| Idea | ALFRED treatment |
|---|---|
| A short root map with area signposts | Implement a MAP.md reference check and two-hop coverage diagnostic. The default fictional vault has a root map and three area maps. |
| Each fact has one canonical home | Keep the authored Markdown note canonical. The index and graph are rebuildable views, not a second editable copy. Conflicting authored claims can still exist and require review. |
| Broken references must be visible | Resolve explicit links, flag missing/ambiguous/blocked targets, and show the source line and hash. Never guess a link when several notes match. |
| Deterministic work before a model call | Build keyword retrieval and exact excerpts now. A future model receives a scoped source packet, not the entire filesystem. |
| Restricted unattended routines | Preserve ALFRED's explicit supervisor, pause, authorisation and result record. A routines registry and durable cross-device scheduling still need implementation. |
| Dashboard is not the source of truth | Keep notes in files; keep approvals and execution state in the existing ledger; show both through authenticated read APIs. |
| A graph for exploring files | Implement one useful graph and a searchable notes view, not six decorative graph modes. Every displayed edge identifies an explicit reference. |
| No dashboard authentication | Do not adopt. ALFRED has role-scoped data and action controls. Keep its existing same-origin sessions, host checks and CSRF protection. |
| Never delete anything | Do not make this a universal rule. Current indexing removes deleted note bodies and links from active retrieval; complete secure erasure and backup retention remain separate work. |
| Automatically push personal memory through Git | Do not implement. This repository is public. Private notes, client material, logs and credentials must never be synced into it. |

## Why Obsidian fits

Obsidian stores notes as ordinary Markdown files in a local vault and maintains a
separate metadata cache. That permits a file-based integration without turning ALFRED
into an Obsidian plugin or making Obsidian mandatory.
Primary documentation: https://obsidian.md/help/data-storage

Obsidian supports wikilinks and Markdown links. Its own graph displays notes and their
references. ALFRED supports a deliberately bounded subset of those file conventions,
not every Obsidian extension, embed, plugin or anchor feature.
Primary documentation: https://obsidian.md/help/links
Graph documentation: https://obsidian.md/help/plugins/graph

No Obsidian application, plugin, sync account or private vault was accessed or installed.
The demonstration uses 20 newly authored fictional Markdown notes. They can also be
opened in an ordinary editor. The configured folder is read-only to this connector;
`.obsidian` and other hidden directories are ignored.

## Keep three different representations distinct

**Authored knowledge:** notes, decisions, procedures and references someone wrote. A
note saying something happened is a claim, not automatic proof it happened.

**Reference graph, implemented in this increment:** file nodes labelled by declared kind
and explicit links/embeds with source line, hash and revision. This is a navigable
knowledge index. Its edges do not assert employment, ownership, causality or ground truth.

**Semantic world model, future:** people, places, devices, projects and claims with typed
relations, source evidence, time validity, conflicts and human corrections. Such a model
must be built and evaluated separately. Drawing lines between files does not complete it.

A future relation might say a source claims a person owns a task. It must carry the source,
time, scope and status, and must be retractable when the evidence changes. A model's
inference remains labelled as an inference. ENDSTATE scenarios remain simulations, not
new observations inserted into the personal knowledge graph.

## The intended composition

```text
Markdown files / optional Obsidian editor
                  |
Read-only, explicitly selected folder connector
                  |
Scoped, rebuildable note and reference index
                  |
Search + graph + source viewer + map-health checker
                  |
Bounded source packet with exact lines and hashes
                  |
Future contained reasoning adapter
                  |
ALFRED authority / approval / verified execution
```

The same architecture can later accept reviewed document/calendar sources. Permissions
belong outside the notes: a Markdown instruction cannot grant itself a tool, disclose a
workspace or change ALFRED's operational rules.
