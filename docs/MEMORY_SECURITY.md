# Memory security, privacy and lifecycle gates

27 September 2026. Extends [SECURITY_AND_DATA.md](SECURITY_AND_DATA.md) and requirements MEM-009/010/013/014, SYS-001/002 in [PRD.md](PRD.md). These are required controls, not claims of completed encryption or independent security review.

## Before a private-data pilot

Resolve person/device identity and source grants outside all model output. Scope every candidate retrieval, traversal and derived summary before ranking or provider egress. Recheck access before persisting/displaying results. Keep secrets out of vaults, graphs and prompts. Source text can be hostile even when received from an authenticated source.

Do not make a shared graph summary, cache or vector index a route around access controls. A foreign entity count, title, path or embedding-derived snippet can leak information even if the final full document is hidden. Test zero-result, namesake, alias, neighbour and cached-answer paths.

Define application-storage encryption/key custody, host access, provider retention, backups and recovery. The current SQLite alpha is not application-encrypted. Local execution reduces some egress but does not establish device security, air-gapping or safe plugins. Obsidian Sync encryption does not protect decrypted local files or data deliberately sent to a model.

## Deletion model

Track independent events for source deletion, source unavailable, source access revoked, memory withdrawn, old value superseded and conversation expired. Invalidate dependent current statements, snippets, vectors, summaries, caches and queued work. Preserve only specifically authorised audit metadata, not a permanent copy of private source bodies.

A deletion receipt identifies the request, scope, dependency classes reconciled, failures and residual retention. Do not call it secure erasure if database pages, WAL, exports or backups may retain data. Backup expiry and cryptographic key lifecycle need their own documented decisions.

Restore under quarantine: reconcile tombstones, current grants and source availability before the restored node participates in retrieval. A restored old note or model summary cannot silently reintroduce forgotten data. File synchronisation is not enough to implement this protocol.

## Writes and plugins

Read, write, publish, sync and model upload are distinct grants. Initially permit only explicitly approved new ALFRED inbox notes. Bind exact destination/content/precondition; recheck at dispatch; reconcile file/database partial outcomes. Never grant an arbitrary local REST/CLI/MCP tool all vault operations merely because its API exists.

Obsidian plugins share substantial app privileges: https://obsidian.md/help/Extending+Obsidian/Plugin+security . Prefer a plugin-free filesystem read path initially. Any later plugin is reviewed first-party code with no automatic skill/plugin installation or hidden network egress. API licence rights are separate from application and service rights.

## Team and operational boundaries

Each client/operation has purpose-bound information, its own retention and role-limited sharing. Personal information is not a default team resource. A memory relationship such as 'member of team' is not an authorisation grant unless the independent identity/permission system establishes it.

Operational receipts, telemetry, reports, human acknowledgements, model analysis and simulation remain different evidence types. No autonomous use-of-force control, covert capture or assumption that missing data establishes safety.

## Supply-chain and experiment restrictions

Only five candidate commit/licence/package records were pinned in this research. No dependency inventory of a new runtime exists because nothing was installed. Root licences do not cover every model weight, plugin, data set or hosted edition. Do not conflate public code visibility with permission to copy.

The previously blocked live-model comparison remains unexecuted and must not be rerouted. New documentation, deterministic tests and licence review do not waive that restriction. Retain prior failure evidence and require an appropriately permitted, separately scoped evaluation for future model decisions.
