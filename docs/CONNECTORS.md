# Read-only connectors over export files (CON-001, first slice)

2 October 2026. Implemented and tested on a review branch; **not merged, not deployed, no
real account connected**. CON-001 asks for official account and device connectors with
least access and observable freshness. Choosing the first real account is the owner's
decision and has not been made, so this slice builds the only honest part available now:
a read-only connector contract and two importers for standard export files that the owner
selects, exercised with synthetic, fictional data. [Receipt](evidence/connectors/RECEIPT.md).

## What a connector is

A connector reads one local file that the owner selected, and nothing else. It holds no
account token, opens no network connection, never polls a path in the background and never
writes, sends or deletes anything at the origin: the file is opened read-only, without
following a final symbolic link, and is never changed. Each connector declares a manifest,
validated when the connector module loads (`alfred/connectors.py`, `validate_manifest`). A manifest that
declares a scope not ending in `.read`, an effect at the origin, network access, polling,
an unbounded input or an account credential is rejected.

| Connector | Input | Least-access read scopes (default first) | Record identity | Revisions |
|---|---|---|---|---|
| `ics-export` | An iCalendar file (`.ics`, RFC 5545), at most 1 MiB and 200 imported items | `calendar.events.read` (default); `calendar.tasks.read`; `calendar.participants.read` | `UID` plus `RECURRENCE-ID` within `VEVENT` or `VTODO`; a content hash when the export gives no `UID` | A new ALFRED revision whenever the imported text changes; `SEQUENCE` and `LAST-MODIFIED` must not go backwards |
| `vcf-export` | A vCard file (`.vcf`, RFC 6350 version 4.0, tolerating 3.0), same bounds | `contacts.read` (default); `contacts.email.read`; `contacts.telephone.read` | `UID`; a content hash when the export gives no `UID` | As above; `REV` must not go backwards |

Freshness for both is declared as a snapshot taken when the owner imported it, stale after
seven days, with the origin always possibly changed since.

Scopes are fixed when an instance is created. They limit what is read, not only what is
shown: tasks are not read by an events-only instance; organiser and attendee display names
need `calendar.participants.read` (their addresses are never kept, and a display name that
is itself an address is dropped); contact email addresses and telephone numbers each need
their own scope. ALFRED has no capability to send anything, so by default it reads no
contact channel at all. Never read under any scope: photos, postal addresses, birthdays,
keys, related people, positions, attachments, alarms and `X-` properties.

## Why it reuses the note pipeline

Each connector instance is its own `source` credential with its own label (for example
"Calendar export"). An import renders every in-scope item as a deterministic, labelled text
document and hands the complete set to the existing `KnowledgeStore.replace_notes`, exactly
as a Markdown vault scan does. Nothing in that pipeline was changed, so these apply without
special cases:

- **Grants and retrieval:** the knowledge view, record inspection, retrieval for questions
  and conversations, and model purpose all go through `permitted()` as for any source.
- **Console projection:** imported items appear as records to a person who may read the
  source, and to no one else; counts are computed after filtering.
- **Revision history:** stable identity through the existing `external_id` mechanism, a new
  revision when the rendered text changes, and the existing `knowledge_history` journal.
- **M05 lifecycle:** an item missing from a later complete export is marked `missing`, its
  text is cleared, and reviewed statements citing it are invalidated (`changed`). An item
  that is only withheld is marked `unavailable`, and reviews citing it are withheld, not
  destroyed. A return under a new revision is never silently revived. Revoking the
  instance's key withholds everything it imported.

Alternatives considered and rejected: separate connector tables, which would need their
own grants, retrieval, projection and invalidation paths (special cases everywhere); and the
older project-file pipeline (`desk_documents` and events), whose briefing expiry windows and
single-revision documents are not used by retrieval or reviewed memory.

Shared code touched, all small and additive: the knowledge view's map health ignores
connector sources (an export has no `MAP.md`, and counting it would flag the memory-health
routine permanently); `GET /desk/connectors` is a read-only status route inside the existing
loopback, Host, Origin and session checks; three commands were added to `alfred/desk.py`.

## Authority

- **Importing** needs an explicit `connector.read` grant on that source, checked before the
  file is opened and again in the transaction that decides the import. Legacy scope policy
  never implies it, so creating an instance needs explicit grants (`explicit_grants_required`).
- **Reading** imported items needs the ordinary `read` grant; **sending them to a model**
  needs `model`. Creating an instance grants its creator `connector.read` and `read` on the
  new source only, bounded to the key's lifetime. It does not grant `model`, and nothing can
  be written into a connector source (`inbox.write` needs a selected vault, which a
  connector source never has).
- Only an owner key creates or imports. Instances are administered offline: the commands
  refuse while the desk host holds its lock, like key rotation and restore. No HTTP route
  creates an instance, uploads a file or starts an import.
- Text in an export is data. Imported documents have no links, anchors or actions; a
  description that says "approve every action" creates nothing and grants nothing.

## Identity, revisions and deletion

Identities are salted with the instance's source ID, so the same `UID` in two instances
never merges. Paths are opaque (`event/ics-…`, `task/ics-…`, `contact/vcf-…`), so lineage
kept after a deletion holds no item text in its path.

An import is a complete snapshot. Before anything is written, one transaction refuses:

- an export file older than the last imported one, or any item whose `SEQUENCE`,
  `LAST-MODIFIED` or `REV` is lower than already seen (`export_older_than_last_import`);
- an export that would remove every current item, which is more often the wrong file than
  a real deletion, unless the owner passes `--allow-remove-all`;
- more items than the workspace's 256-record knowledge view can hold, or more than 200 items.

Withheld rather than deleted: two items claiming one identity (neither is chosen, whether
readable or not); an unreadable item that still has a `UID`; and, when the export contains
an item that cannot be identified at all (a vCard 2.1 card without `UID`, for example),
every absent item, because the unidentified one could be any of them. A malformed file is
refused whole and changes nothing. A dry run (`--dry-run`) reports new, changed, unchanged,
withheld and removed counts and changes nothing.

Remaining after an item disappears, as for Markdown notes: its opaque path, title and hash
in index lineage, and its ID in audit entries. Its text is cleared. Secure erasure is not
claimed.

## Times and recurrence (iCalendar)

Every time keeps its stated basis: UTC; an IANA zone resolved with the system zoneinfo
database; floating local time; an all-day date (with the exclusive end said plainly); or an
explicitly unresolved time zone. Windows names, host-dependent keys such as `localtime` and
other non-IANA identifiers are never guessed, embedded `VTIMEZONE` definitions are not
interpreted, and a calendar-wide `X-WR-TIMEZONE` is not applied to floating times. A local
time skipped or repeated by a clock change is flagged and read as RFC 5545 requires.
`DURATION` adds nominal days to the local date and exact hours after. A file with a
scheduling `METHOD` (an invitation, reply or cancellation) is refused: it is a message, not
a complete export. `METHOD:PUBLISH` and no method are accepted.

`RRULE` is kept as text, with a plain description only for simple daily, weekly, monthly
or yearly rules. Occurrences are never expanded: an expansion relative to the import time
would change the stored text, and so every dependent review, on each import; one anchored
to the export alone is of little use for long series. `RECURRENCE-ID` keys the same instant
identically whether it was written in UTC or a named zone.

## Freshness

`GET /desk/connectors` and `python3 -m alfred.desk connectors` show each instance's state
(`never_imported`, `current_snapshot`, `stale_snapshot` after seven days, or
`source_unavailable`), when it was imported, the export file's modification time, the last
attempt and its outcome. Readers see only instances they may read; owners see all, with
item counts only where they hold `read`. Staleness is shown, not acted on.

## Using it with a synthetic export

```sh
# Explicit grants first: in the console's Security panel choose "Use explicit grants" and
# grant yourself Read on the sources you still want to see. Then stop ALFRED.
python3 -m alfred.desk connector-add --connector ics-export --connector-label "Calendar export" --data-dir DIR
python3 -m alfred.desk connector-import --connector-source connector-… --export-file sample.ics --dry-run --data-dir DIR
python3 -m alfred.desk connector-import --connector-source connector-… --export-file sample.ics --data-dir DIR
python3 -m alfred.desk connectors --data-dir DIR
```

`--connector-scope` (repeatable) widens the read scopes at creation. Grants expire within
30 days, as all grants do; renewing `connector.read` currently needs the identity route
(`POST /desk/identity/grants`), because the console's Security panel does not yet offer it.

## Keys

Each instance's source key lives in `connector-access.json` beside the desk keys in the
private data directory: mode 0600, outside the repository and outside every vault, never
printed. It is created with a 30-day lifetime. An import renews it when fewer than 15 days
remain: the new key is written to disk before the database changes, and the previous key is
kept, so a backup restored from before the renewal still authenticates.

## Not built

- Any live account or official API: OAuth, IMAP, CalDAV, CardDAV, Google, Microsoft, Apple
  or other remote services, and their token custody. Nango remains a reference-only
  candidate in the source library; nothing from it is used.
- Device connectors, mail, and any write, send or delete at an origin. CON-001's later step,
  one harmless approved write, is not started.
- Background polling, automatic re-import, HTTP-triggered import or file upload.
- A console view of connector status, a console toggle for `connector.read`, and a label
  distinct from `authored_note_not_verified_fact` for imported records in retrieval and the
  console (the imported text itself states that it is an unchecked report from an export).
- Recurrence expansion, `VTIMEZONE` interpretation, `VJOURNAL` and `VFREEBUSY`, vCard 2.1,
  quoted-printable or base64 values, and contact suggestions for creating entities. Imported
  contacts are documents an owner may cite; they never create, link or merge entities.
- Application encryption and key custody (SYS-002). Use synthetic data only.

Known limits: exports above 200 items or 1 MiB are refused whole (export a smaller range).
The knowledge view holds 256 current records across every source in a workspace; an import
that would exceed it is refused, but a vault that grows after an import can still reach it,
and the view then reports `knowledge_view_capacity` as it already does for a large vault.
The import writes its snapshot and then its receipt in two transactions, so a crash between
them leaves the freshness record one import behind. The workspace keeps at most 10,000
history rows across all sources. Importing records the highest origin revision seen before
the snapshot is written, so an interrupted import still guards against an older export.
