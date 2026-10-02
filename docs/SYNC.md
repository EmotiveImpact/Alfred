# Four kinds of sync, kept apart (MEM-014)

Status, 2 October 2026. This document separates four things that are often all called
"sync". Only the parts marked implemented exist, and they are tested with synthetic files
and temporary folders. No sync client was installed, run or connected, no real vault was
read and nothing is deployed. Requirement text: MEM-014 and MEM-013 in [the PRD](PRD.md);
background: [infrastructure research, section 4.2](../research/INFRASTRUCTURE_2026-10-02.md).

| Kind | What moves | Who is the authority | What ALFRED does | State |
|---|---|---|---|---|
| Vault file sync | The person's Markdown files | The person's own tool: Syncthing, Dropbox, iCloud Drive, OneDrive, Nextcloud, Obsidian Sync or Git | Reads a selected folder, recognises conflict copies by name, never merges or resolves them, never runs a sync client | Conflict-copy recognition and the placement guard are implemented |
| Identity and grants | Credentials, person and device enrolment, source grants, invitations | The one local SQLite database | Offline provisioning, explicit pairing and offline rotation (M02); revocations are journalled (M05) | Never file-synced; no identity sync between devices exists |
| Ledger and job state | Reviewed statements, captures, executive records, actions and drafts, audit, jobs, job events and artefacts | The same database, a single authority | One host writes; `backup` makes a consistent copy and `restore` replays the lifecycle journal; see [JOBS.md](JOBS.md) | No replication and no second writer |
| Runtime or model sync | Model files, prompts, embeddings, caches, sessions, runtime state | None | Nothing | Not implemented |

A saved file is not proof that another device received it, and a vault that a sync tool
has updated is not a change ALFRED made. Each kind keeps its own authority.

## 1. Vault file sync

The person chooses how their vault is synced, if at all. ALFRED reads only the folder the
person selected ([M01 contract](OBSIDIAN_INTEGRATION.md)) and never writes into it except an
approved, create-only inbox note (M04). It does not run, configure or call any sync tool.
Obsidian's own guidance applies: use one sync method per device.

### Conflict copies

When a sync tool cannot reconcile edits made on two devices, it keeps both versions: one
under the original name and one under a conflict name. ALFRED recognises these exact name
forms, immediately before the `.md` extension (`alfred/sync_conflicts.py`):

| Tool | Name form | Example |
|---|---|---|
| Syncthing | `name.sync-conflict-YYYYMMDD-HHMMSS-XXXXXXX.md`, where `XXXXXXX` is the first seven characters (A to Z, 2 to 7) of the editing device's ID, or empty | `Atlas.sync-conflict-20261002-101500-ABCDEFG.md` |
| Dropbox | `name (Someone's conflicted copy YYYY-MM-DD).md`, optionally with ` (N)` after the date | `Atlas (Jo Example's conflicted copy 2026-10-02).md` |
| Nextcloud and ownCloud desktop clients | `name (conflicted copy YYYY-MM-DD hhmmss).md`, optionally with a user name before the date | `Atlas (conflicted copy 2026-10-02 101500).md` |
| Older ownCloud clients | `name_conflict-YYYYMMDD-HHMMSS.md` | `Atlas_conflict-20261002-101500.md` |

The date and time must be a real calendar date and clock time, so `Meeting 2.md`,
`Report (1).md` or `Conflicted copy policy.md` are ordinary notes. A copy of a copy is
traced back to the first original in the same folder. Recognition is by name only: ALFRED
never compares or merges contents, and it cannot tell a copy someone named by hand in the
same form from a sync tool's copy. The name forms follow each tool's documented behaviour;
they were tested with synthetic files created by name, not with the tools.

What happens to a recognised copy:

- It is never read or parsed as a note. It does not enter the index, search, retrieval,
  grounding packets, conversation context or the console graph as a note.
- It is recorded beside the scan (table `knowledge_conflicts`) with its path, the
  original's path, the original's catalogue ID when the original was indexed in the same
  scan, the tool, first and latest detection times, and a state: `linked`,
  `original_unavailable` (the original exists but could not be indexed) or `orphaned` (no
  original file).
- It is also a per-path source issue with code `sync_conflict_copy`, so the source shows
  `attention`, the existing knowledge issue view lists it, and a copy that an older scanner
  had indexed as a note becomes `unavailable` (withheld) rather than `missing`. Other
  problems are listed before these entries, because stored issue lists are bounded.
- `GET /desk/knowledge` returns `sync_conflicts` and `counts.sync_conflicts`, filtered by
  the same source permission as the notes. The console projection marks the original note
  `availability: attention` with a `syncConflict` object and lists every copy, including
  orphaned ones, in `syncConflicts`. No HTTP route was added. Reading the console code, its
  source inspector already lists the first source issues (code and path), which include these
  entries; nothing in the console displays the note-level `syncConflict` fields yet. This was
  not checked in a browser.
- The original note stays readable. A reviewed statement bound to its unchanged lines stays
  usable; if the original's content changed (for example the sync tool wrote the other
  device's version), the existing M01 and M05 rules invalidate the review as before.
- Catalogue identity stays with the original path. Syncthing renames the losing local file
  to the conflict name, so the old inode moves to the copy; before this change the scanner's
  inode continuity moved the original note's identity into the copy and gave the original
  path a new identity. With adopted `alfred_id` properties, a copy carrying the same ID
  previously made the whole source unavailable as a duplicate ID; it is now set aside.
- At most 64 copies are recorded per source. More produce `sync_conflict_capacity` at the
  head of the issue list, and the extra copies are still kept out of the index.
- The approved inbox writer refuses a filename that looks like a conflict copy, so ALFRED
  never creates a file its own scanner would set aside.

Resolving a conflict is the person's job, in their own editor: compare the two versions,
keep what is wanted in the original, then delete or rename the copy. The next complete scan
no longer finds the copy and removes the record. The audit log records
`knowledge.sync_conflict_detected` and `knowledge.sync_conflict_cleared` with a hashed
reference, never the path. A copy renamed to a new ordinary name becomes a new, distinct
note; it does not inherit the original's identity. A source that becomes unavailable hides
its last recorded conflicts along with its notes.

### Deliberately not recognised

| Case | Why |
|---|---|
| OneDrive | Appends a hyphen and the computer name (for example `Report-LAPTOP-7F3K2Q.md`), which cannot be told apart from ordinary hyphenated names without knowing the person's device names. |
| iCloud Drive | Numbered names such as `Meeting 2.md` look exactly like ordinary notes. |
| Obsidian Sync | Merges Markdown edits into the file itself by default, so there is no copy. Its optional conflict-file naming was not verified for this change. |
| Git | A conflicted merge leaves `<<<<<<<`, `=======` and `>>>>>>>` markers inside the file rather than a copy. Not detected; such a note is indexed as written. |
| Google Drive, Box, pCloud, Seafile, Resilio Sync, rclone bisync | Their conflict naming was not verified for this change. rclone bisync's default suffix does not end in `.md`, so those copies are not scanned at all. |
| Dropbox variants | Case-conflict and encoding-conflict renames, names in other languages, and a device name that contains parentheses. |

An unrecognised conflict copy is indexed as an ordinary, separate note with its own
identity. It is never merged with the original, but it is not flagged either.

## 2. Where ALFRED's live files may be kept

ALFRED's live files are the database (`desk.sqlite`), its write-ahead log and shared-memory
index (`-wal`, `-shm`), the lifecycle journal (`desk.sqlite.lifecycle.jsonl`), the access
keys (`desk-access.json`), the host lock and the job cache (`job-cache/`). They all live in
the data directory. SQLite documents that WAL needs every process on one host and that a
database separated from its WAL can lose committed transactions; sync tools copy these files
one at a time while they change.

`init`, `serve` and `restore` therefore refuse a data directory (`alfred/placement.py`):

- inside a configured vault (`--vault`), or inside any folder holding `.obsidian`
  (`data_directory_inside_vault`);
- inside a sync root recognised by an entry in the data directory or any ancestor
  (`data_directory_in_sync_folder`): Syncthing `.stfolder`, `.stignore` or `.stversions`;
  Dropbox `.dropbox` or `.dropbox.cache`; Nextcloud or ownCloud `.owncloudsync.log`,
  `.csync_journal.db`, `.sync_<hex>.db` or `._sync_<hex>.db`;
- under the macOS paths `Library/Mobile Documents` (iCloud Drive) or
  `Library/CloudStorage/<provider>` (OneDrive, Dropbox, Google Drive and Box on current
  macOS), also `data_directory_in_sync_folder`;
- inside a Git working tree, recognised by `.git` (`data_directory_in_git_working_tree`),
  because anything there can be committed and pushed.

Both the path as given and its real path after symlinks are checked, and a marker inside the
data directory (for example a synced `job-cache`) is caught too. The refusal happens before
anything is created, prints the reason and explains the consistent alternative: run
`backup` and copy the backup file and its manifest, which form a consistent snapshot that is
safe to sync, or use `export`. There is no override flag. `access`, `backup`, `export`,
`rotate` and `revoke` still run, so a person can make a consistent copy, move the data
directory to a local disk with ALFRED stopped, and revoke a credential in an emergency.
Backups are not encrypted, so a sync service can read them.

The check cannot see:

- iCloud Drive's Desktop and Documents syncing, OneDrive folder backup and similar features
  that sync ordinary paths such as `~/Documents`;
- sync clients that keep their state outside the folder, including OneDrive clients on
  Linux, Google Drive outside `Library/CloudStorage`, Box Drive, pCloud Drive, Resilio Sync,
  Seafile and Syncthing configured with a different marker name;
- network filesystems and FUSE mounts such as NFS, SMB, SSHFS, rclone mount, JuiceFS or
  SpaceFS, where SQLite says WAL does not work (a future check could read the mount table);
- sync set up after `serve` started, because the check runs at `init`, `serve` and `restore`
  only;
- whole-disk or folder backup tools (Time Machine, restic, Borg). They are not two-way sync,
  but a file-level copy of a live database can be inconsistent; `backup` is the consistent
  route.

Windows is not a supported host.

## 3. Identity and grants

Credentials, person and device enrolment (`identity_devices`), source policy and grants
(`source_policy`, `source_grants`) and single-use invitations (`grant_invitations`) are rows
in the one database, so the placement guard keeps them out of synced folders as well. There is
no mechanism to copy identity between devices: another device gets its own credential by
offline provisioning and explicit pairing (M02). Credential and grant revocations are written
to the lifecycle journal first, so restoring an older backup cannot bring them back (M05).
Multi-host identity, remote enrolment, key expiry policy and device attestation are not
implemented.

## 4. Ledger and job state

Reviewed statements, captures, executive records, actions, drafts, the audit log, jobs, job
events and artefacts have one authority: the SQLite database on one host's local disk. The
job coordinator is single-host stage 0 ([JOBS.md](JOBS.md)). `backup` uses SQLite's online
backup API and writes a hashed manifest; `restore` is offline and replays the lifecycle
journal so forgotten values and revoked access stay gone. Replication (for example
Litestream), a second coordinator, remote workers, any multi-writer merge and encrypted
backups are not implemented.

## 5. Runtime or model sync

None exists. No model files, prompts, embeddings, caches, sessions or runtime state are
synced between devices. The job cache is local, bounded, rebuildable and never authoritative.

## 6. Backup and export are different

| | `backup` | `export` (MEM-013) |
|---|---|---|
| Purpose | Restore ALFRED after loss | A portable record a person can read, keep or take elsewhere |
| Contents | The whole database: every table and every person's records | Only what one credential may read now |
| Format | A SQLite file and a JSON manifest with its SHA-256 | Plain JSON, readable Markdown, a manifest and `SHA256SUMS` |
| Filtering | None | Forgotten, withheld and past-retention statements, keys, sessions and invitation codes are left out |
| Restorable | Yes, with `restore` (journal replayed) | No |
| Safe to copy into a synced folder | Yes, it is a consistent snapshot | Yes, it is a set of static files |
| Encrypted | No | No |
| Command | `python3 -m alfred.desk backup` | `python3 -m alfred.desk export --export-dir PATH [--role reader]` |

### Export contents and rules

`alfred/export.py` reads through the existing authorised views (`ReviewedMemory.view` and
`ExecutiveRecords.view`) for one owner or reader credential, and fails with
`export_authority_changed` if that credential's read authority changes while the export is
assembled. A source credential cannot export. The bundle holds:

- `statements.json` and `statements.md`: entities, including any that share a name (listed
  separately, never merged), and reviewed statements with review state (a proposed statement
  stays `proposed`), version, value, validity, review time, conflicts, cited note ID, hash,
  revision and line range, the cited text when it is currently permitted, and lineage
  (`replaces`, `replaced_by`); a link to a statement that was left out reads `not_exported`;
- `captures.json`: memory type, retention date (or none) and capture origin for each
  exported captured statement;
- `executive-records.json` and `executive-records.md`: goals, priorities, commitments,
  decisions, milestones and follow-ups with status, dates, project and cited-support state;
- `manifest.json`: format and version, export time, workspace, credential, role, counts,
  exclusions, the SHA-256 and size of every other file, and the statement that it is not a
  backup, not encrypted and grants no authority; `SHA256SUMS` for `sha256sum -c`; and a
  `README.md`.

Never included: access keys and credential digests, sessions, invitation codes, other
people's records, forgotten statements, statements whose support is withheld, captures whose
retention has ended (even before the supervisor's next retention pass), note bodies beyond the
cited lines, the knowledge index and note history, the audit log, lifecycle receipts, actions
and drafts, and jobs. Markdown shows note text inside code spans or fenced blocks, so it is
displayed literally and cannot act as HTML or links.

The destination must be a new folder or an existing empty one, outside every configured vault
and any folder holding `.obsidian`, and outside this repository; it may not be a symlink and
its parent must exist. The export is written to a private staging folder (0700, files 0600)
and renamed into place, so a failure leaves nothing behind and a destination that gains a file
meanwhile is not overwritten. A synced folder is an acceptable destination. Each export adds
an `export.written` audit entry naming its export ID.

## Not implemented

- Recognising OneDrive, iCloud Drive, Obsidian Sync, Google Drive or other conflict copies,
  Git conflict markers, or a copy whose tool is unknown.
- Comparing a copy with its original, or any merge, resolution or write-back by ALFRED.
- Detecting network filesystems, FUSE mounts or sync started after ALFRED started.
- A console interface that displays the conflict state; only the projection carries it.
- Identity, grant, ledger, job or runtime sync between devices; replication; encrypted backups
  or exports; redaction inside an export; exporting the knowledge index or receipts.
- Acceptance with real sync clients, real devices or a real vault edited by Obsidian.
