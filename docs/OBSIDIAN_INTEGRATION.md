# Obsidian integration specification

27 September 2026. Target specification, not a newly connected vault. Requirements MEM-001/002/011/014 in [PRD.md](PRD.md). The existing bounded Markdown scanner is a starting point, not complete Obsidian compatibility.

## Decision

Support Obsidian without requiring it. A vault is a local folder of Markdown and attachments, not ALFRED's database. The user can keep editing notes without ALFRED; ALFRED can read selected notes when Obsidian is closed. The first connector remains local filesystem read-only with explicit folders and exclusions.

Keep ALFRED's SQLite files, credentials, audit journal, embedding indexes and private runtime configuration outside the vault. Do not put the vault in this public repository. Do not synchronise a live SQLite database/WAL as ordinary note files.

## Integration options

| Option | Role | Decision / boundary |
|---|---|---|
| Selected filesystem folder | Read Markdown and supported attachments without requiring app/plugin. | Default first implementation. Permissioned allowlist, bounded file sizes, source health and reconciliation. |
| Official Obsidian plugin API | Optional in-app capture, backlink/metadata operations and explicit selection. | Later thin first-party plugin, not an agent runtime with unrestricted tools. MIT API definitions do not licence Obsidian's app source. |
| Official `obsidian` CLI | Operates the running desktop app. | Optional allowlisted convenience adapter. Not a headless server; no generic shell/CLI passthrough or eval commands. |
| Community Local REST API | Optional vault operations through a plugin. | Interoperability reference only initially. Extra credential, local network and plugin privilege surface requires review. |
| Official `ob` Headless Sync | Syncs selected remote vault files without the desktop app. | Optional independently configured host/mirror after privacy and sync tests. Not ALFRED runtime replication. |

Official CLI requires the Obsidian app to be running: https://obsidian.md/cli . The Headless Sync client is open beta, needs an active Sync subscription and warns against using desktop Sync and Headless Sync simultaneously on the same device: https://obsidian.md/help/sync/headless . Back up before testing. Use one sync method per device, not a combination of competing sync writers.

The inspected official headless package declares UNLICENSED, so this public repository is not a blanket grant to vendor/fork it: https://github.com/obsidianmd/obsidian-headless . Treat it as an optional separately installed service client under applicable terms. No installation or subscription purchase occurs in this work.

## Read compatibility acceptance

| Area | Current v0.8 | Required next behaviour |
|---|---|---|
| Markdown text, title, kind, tags, aliases | Bounded subset. | Preserve exact source bytes and deterministic parsing; document unsupported metadata. |
| Wikilinks and relative links | File-level resolution, ambiguity visible. | Regression fixtures for escaped names, encoded paths, alias collisions and same-name notes. |
| Heading/block anchors and embeds | Fragment does not establish validated span. | Validate supported anchors, preserve position provenance, flag unsupported anchors; never silently cite an unrelated passage. |
| Rename/move | Path-based identity is insufficient for continuity. | Sidecar catalogue or explicitly adopted stable ID; require proof/review before rebinding. Do not modify all existing frontmatter automatically. |
| Concurrent saves and sync conflicts | No complete Obsidian sync contract. | Debounce incomplete writes, reconcile a full scan, retain distinct conflicts and avoid duplicate ingestion. |
| `.obsidian`, scripts and plugin configuration | Excluded. | Continue excluding by default. Never load plugins or interpret their files as instructions. |
| Attachments | Not a complete multi-format ingestion system. | Explicit allowlist and parser adapters; preserve page/block provenance. No execution of embedded code or macros. |
| Multiple vaults | Scope must remain explicit. | No global name-based linking across vaults/workspaces; separate grants and identities. |

Use a catalogue-controlled document ID mapping first. Optional frontmatter IDs require explicit adoption and duplicate-ID detection; content or filename equality alone is not proof that two notes represent the same object. A copied ID must not steal an earlier note's history.

## Capture experience

The user can eventually select text or issue 'remember this'. ALFRED previews proposed text, source, memory type, destination, scope and retention. Explicit user assertions are a legitimate basis, labelled as such, not forged source-document facts. Model distillation can shorten a note but must keep a route to its permitted input and never invent consent.

Begin with new files in `ALFRED/Inbox`, optional daily capture notes and a reviewed projects/preferences index. Existing folder arrangements remain valid; do not impose a migration. Map notes provide navigation, not permission. Keep personal and company captures in their correct vaults.

## Safe write-back acceptance

Write access is separate from read access. Review binds an operation ID, permitted vault/path, expected source version or expected absence, exact proposed content/diff, expiry and actor. Restrict the initial capability to new inbox notes. Re-read content before dispatch and after completion. Report 'note created and read back', not 'all devices have synchronised'.

Preserve content outside the approved edit. Never overwrite Obsidian settings, plugins, human-authored notes or a conflict copy under a broad 'organise my memory' instruction. Reject symlinks, traversal, unexpected file replacement and unsupported encoding. A remote sync conflict or a concurrently edited file requires review.

For an optional plugin, use the official Vault API's `process` pattern for local read-modify-write; asynchronous work must compare the original content before applying a change. This protects the plugin operation, not every independent external writer. Official guidance: https://docs.obsidian.md/Plugins/Vault . The standalone connector needs its own journal, hash precondition and reconciliation contract.

## Sync and offline

An always-on ALFRED node may later use a separately configured pull-only mirror. Read-only ALFRED processing should not alter that mirror. A future write queue must have one deliberate publication route rather than racing against mirror-remote resets. Headless Sync's E2EE option protects synchronisation; it does not encrypt the opened local vault, ALFRED's caches or information sent to a model.

Track last complete scan, local revision, sync health and remote confirmation separately. A saved file is not proof that another device received it. A lost connection must not be called a deleted vault. Deleted source tombstones and current grants must be reconciled after reconnect/backup restore.

## Privacy and distribution

Obsidian is free for personal and commercial use under its current application terms; that is not permission to copy its proprietary application code: https://obsidian.md/license . API type definitions are a separate repository: https://github.com/obsidianmd/obsidian-api .

Community plugins inherit substantial application privileges, including filesystem and network access; a general fine-grained permission system is not a substitute for reviewing installed plugins: https://obsidian.md/help/Extending+Obsidian/Plugin+security . Avoid making community-plugin installation mandatory for initial ALFRED use.

No private vault is accessed in this planning delivery. Actual setup must select a test vault first, establish exclusions and egress policy, and then pass read/write/conflict/deletion tests before sensitive use.

## What counts as integrated

A native Obsidian integration is not established by the name of a console branch. Acceptance needs an actual test vault edited by Obsidian and by another editor; correct index updates with the app closed; working reviewed-memory retrieval; exact-diff write approval; conflict handling; pause/revocation; and export/forget evidence. Native mobile/background behaviour requires its own device tests.
