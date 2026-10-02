# M01: selected-vault identity and compatible read pipeline

30 September 2026. Implementation review checkpoint, not a deployment receipt.

## Baseline and scope

Started on a clean branch from current main `8398c7437cb0ef1386d8dc4ff1f9e92fb2557ca2`, after checking issue #11, its consolidation update, current refs and open PRs. Rechecked main before publication. The backlog's earlier `03e946fc3fb6fe0b540abe5ff52204de6f0f99ed` remains recorded as the planning baseline. Console refinement #15 was the only concurrent open PR found. No console, source-library or production configuration files are changed here. The existing web interface only updates its no-issues caption to reflect supported anchor validation.

Implemented M01 as a bounded POSIX, read-only Markdown slice. Issue #11 stays open; M02-M12 remain planned. The backlog now distinguishes actual runtime implementation tracking from the historical planning-only revision. M01 implementation is subject to draft PR review and does not imply a main merge.

## Acceptance mapping

| M01 criterion | Evidence and observed result |
|---|---|
| Obsidian closed: selected files index without writes | `test_closed_app_read_never_writes_vault` indexes actual synthetic Markdown without an app/plugin process and checks unchanged bytes/mtime and absence of a sidecar. This is app-independent filesystem acceptance, not native editor-device acceptance. |
| Stable selected vault/source | Restart and root-folder rename retain the catalogue vault ID; root replacement after restart and changed selection configuration are unavailable. Distinct source grants retain distinct vault/note IDs. |
| Rename/revision compatibility | Proven filesystem move retains ID and advances revision, including swaps and reused old paths; same-path atomic saves retain ID. Explicitly adopted `alfred_id` supports an edited move/restore. Copying, unproved move continuity and confirmed delete/recreate without an ID remain distinct. Stale source references fail final revision checks. |
| Duplicate IDs | Duplicate adopted IDs reject the whole source snapshot atomically. Changing/removing an adopted ID and rebinding to another occupied note are rejected. Case-colliding paths are rejected. No automatic winning copy. |
| Aliases and supported anchors | Alias collisions remain ambiguous. Supported self/file/alias, heading/block and embed links validate target spans and hash/revision. Missing/duplicate/unsupported anchors cannot create a file-level edge. Code/comments/frontmatter are not anchor evidence. Encoded filenames/fragments are decoded separately. |
| Excluded folders and unsafe paths | Explicit descendant exclusions plus existing hidden/plugin/dependency exclusions; unsafe direct/scanned paths, symlinks, hardlinks and non-regular files are withheld; database-inside-vault is rejected. Existing symlink/hardlink tests remain in the retained core suite. |
| Partial saves and lost sources fail honestly | Incomplete metadata/fences/comments and changed/failed reads withhold affected content as unavailable. Mid-scan changes and whole-source failures withhold the complete source. Lost root does not mark notes deleted; last-complete time/snapshot remain distinct from latest check time. Mid-scan source revocation cannot expose content. |
| Rebuildable projection and compatibility | A v1 database migration preserves existing note IDs/revisions and is idempotent. Rebuilding removed note/link/anchor projections uses durable catalogue identity/history. Source loss still invalidates existing reviewed claims through the retained checks. |

Tests use temporary invented files, real SQLite and controlled race/error injections. UUID-like identifiers are generated once; acceptance checks continuity and rejection outcomes rather than fixed random values. Source metadata history contains path/hash/revision/status, not historical text bodies.

## Validation

- 51 M01 acceptance cases pass; named raw results are in [local-tests.txt](local-tests.txt).
- The complete first-party Python suite passes: 605 tests, including the 554 retained baseline tests.
- 12 backlog checker tests and the complete requirement/job/local-link consistency check pass.
- 21 source-library checker tests pass. Byte verification passes for 1,946 original source files, 363 extension files and 89,788 broad source-library files. These sets overlap; counts are not added as unique source.
- `git diff --check` passes.

The exact published commit/tree and unified GitHub CI results are recorded in the draft PR and Actions, avoiding a self-referential commit hash in this file. This local receipt does not claim GitHub browser results before those runs finish. Local Playwright package setup succeeded, but Chromium installation failed with invalid/truncated archives and HTTP 400 responses from its download endpoints. No local browser pass is claimed. The unchanged unified workflow exercises the real backend/web browser workflows and the preserved console on the combined PR source.

## Compatibility and limits

Read [the implemented contract](../../OBSIDIAN_INTEGRATION.md). Optional `alfred_id` adoption and folder exclusions are explicit CLI/API configuration, fixed for one selected source. Credential/person rotation and fine-grained grants are M02, not solved by the vault ID. Complete deletion, restored-backup tombstones, encryption and secure erasure remain M05 gates.

Supported anchors are plain-text ATX headings and trailing single-line block IDs; unsupported rich/setext/nested/footnote/multiline forms remain unresolved. No universal Obsidian parser or native app/device compatibility claim. Exact file paths take precedence over bare-name alias fallback.

A stable, valid intermediate editor save cannot be distinguished from an intended save by a read-only scanner. File/directory signature checks bound ordinary races but do not create a global filesystem/editor/sync transaction or cryptographic identity proof against a hostile local filesystem/inode reuse. Outputs remain indexed snapshots. Historical cached text may remain inaccessible after whole-source loss until later reconciliation; this is not a secure deletion receipt. Previously invalidated reviewed claims do not automatically become usable on reconnect.

No vault writes, third-party runtime adoption, model inference, private vault/account access, host installation, main merge or deployment. M03 reviewed-memory context injection and the real console/backend adapter remain separate work.
