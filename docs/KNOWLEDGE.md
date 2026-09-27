# Knowledge Desk v0.4 development guide

This increment extends the existing Desk UI; it does not replace or flatten the earlier
personal/work/authorised operational architecture. No live AI is connected.

## Run the actual local application

Python 3.10+ on a POSIX development machine with the required directory-descriptor and
no-follow filesystem flags. GitHub acceptance uses Linux Python 3.12.3. Windows and a
native mobile application have not been validated. No runtime packages or API keys are
required for this development application.

Use a new private data directory, not a folder inside the public source repository:

```sh
python3 -m alfred.desk init --data-dir ~/.local/share/alfred/desk-v04-demo
python3 -m alfred.desk access --data-dir ~/.local/share/alfred/desk-v04-demo
python3 -m alfred.desk serve --data-dir ~/.local/share/alfred/desk-v04-demo
```

The access command intentionally displays the private local sign-in key in your terminal.
Do not paste it into chat, commit it or expose it in a screenshot. Open
`http://127.0.0.1:8765` locally and sign in. The generated workspace contains three
fictional project reports and a 20-note fictional Markdown vault.

Existing data is not overwritten. An older Desk directory without a vault still runs,
but Knowledge reports no source. To point the connector at an explicitly chosen test
folder, use `--vault /absolute/path/to/test-vault` with the serve command. Use synthetic
notes for this alpha until its encryption, retention, pairing and threat model have been
reviewed. No actual private Obsidian vault has been connected by this work.

## What runs automatically

While the explicitly launched Desk process is alive, its supervisor checks the configured
project folder and optional Markdown vault on its interval, and processes previously
approved local drafts. Closing the browser does not stop that process. Pause stops new
scans and effects; Ctrl+C stops the process. No operating-system daemon, cloud host,
cross-device synchronisation or scheduled ChatGPT task has been installed.

## Knowledge interface

Use Knowledge in the sidebar. Search uses case-insensitive keyword matching, not semantic
embeddings. Filter by declared note type and switch between Map and Notes. Select a note
to see its path, revision, file hash, outgoing references and backlinks. Read source text
shows a numbered indexed snapshot without executing Markdown/HTML.

Source packet collects up to five matching notes and bounded excerpts with line numbers,
revision and hashes. It does not generate an answer or send content to a model. Changed
or unavailable sources are skipped when assembling a packet rather than silently cited
against mismatched bytes.

Memory health reports unresolved/ambiguous/blocked links, missing root MAP.md files and
notes outside two directed reference hops of a source's root. The fictional Research
inbox deliberately links to one absent note to demonstrate the warning. This is not a
real missing user document.

## Supported Markdown subset

- UTF-8 Markdown and a UTF-8 BOM, with source hashes computed from original bytes.
- Flat title, type/kind, tags and aliases frontmatter; simple inline or multiline lists.
- Ordinary `[[note]]`, `[[folder/note|label]]`, file embeds and relative Markdown links.
- Case-insensitive exact file lookup, then unambiguous wikilink basename/alias lookup.
- Reference source line, source revision and exact file-byte hash retained.

Code fences, inline code, indented code, comments and frontmatter are not treated as
link evidence. This parser is not a complete CommonMark/YAML/Obsidian implementation.
Heading and block fragments resolve to their file only; anchor existence is not checked.
Attachments are not imported or opened. External URLs are not fetched. Script/file
schemes and paths escaping the selected source are blocked. Links are resolved inside
one source, never guessed across another vault or workspace.

## Bounds and file safety

Per scan: at most 256 valid notes, 64 KiB per note, 4 MiB total note bytes, 128 references
per note, 8,192 total references, directory depth six and 4,096 enumerated entries.
Graph rendering is capped at the first 96 matching nodes; the list/search can inspect
the remaining indexed notes. The combined workspace graph also has a 256-note view cap.
Failures are explicit rather than an unbounded filesystem crawl.

The connector opens directories and notes without following symlinks, rejects hard-linked
notes, ignores hidden configuration/plugin directories, pins root identity and checks
file metadata before and after reads. It never writes the original notes or runs their
instructions. These measures are not a complete sandbox against a compromised local OS.

## Storage and deletion

Markdown files are canonical. New knowledge tables are a rebuildable index in the existing
SQLite development database. Updates replace the indexed note body/references and advance
a hash-based local revision. Unchanged content retains its revision. A rename does not
guess identity: old paths become unavailable, new paths are indexed and stale references
are flagged.

After a successful scan, deleted or unreadable notes are excluded from current retrieval;
their indexed bodies/tags/aliases and old references are removed from the active tables.
Some tombstone metadata, including path/title/hash/revision, remains. SQLite pages, WAL,
backups and old already-delivered content are NOT securely erased by that operation.
This is not a complete right-to-erasure implementation or an encrypted vault.

Credential expiry/revocation and source unavailability are rechecked when serving notes.
The index can still lag an external edit until the next successful scan. Display indexing
time and do not treat filesystem modification time as proof of factual validity.

## API and checker

Authenticated read routes:

```text
GET /desk/knowledge?q=<keywords>&kind=<optional-kind>
GET /desk/knowledge/notes/<opaque-note-id>
GET /desk/knowledge/context?q=<keywords>
```

No browser-supplied filesystem root, note-write/delete endpoint or permission-granting
Markdown field exists. All routes inherit the Desk's existing loopback Host/Origin,
session and role boundaries. Graph responses are scoped on the server.

```sh
python3 -m alfred.knowledge_check --data-dir ~/.local/share/alfred/desk-v04-demo
```

The checker examines the most recent indexed snapshot. Exit 0 means no recorded map/link
issues; 1 means issues or unavailable sources; 2 means access/configuration failure.
The supplied fictional vault intentionally returns 1 until its demonstration missing
link is removed or resolved. The checker is not installed as a nightly routine.

## Verification and preview

Run `python3 -m unittest discover -s tests -v`. Browser tests additionally require the
pinned test-only Playwright environment used in `.github/workflows/knowledge-v04.yml`.
They exercise the real browser/server/database/files, not a mocked backend.

Successful acceptance writes tests, source hashes, browser reports and screenshots under
`docs/evidence/knowledge-v04/`. Check the actual run, not merely this workflow's existence.

`docs/previews/ALFRED-Desk-v04.html` packages the actual frontend with a clearly labelled,
read-only fictional in-file transport. It is useful for viewing the UI without a running
server. It is NOT a hosted backend and cannot create drafts, edit files or connect accounts.
The compressed text companion and manifest support exact-byte transfer and verification.
