# CON-001 receipt: read-only connectors over export files (first slice)

2 October 2026. Worktree branch `worktree-agent-aa96290b947e1be84`, started from the
integration branch at `870751368`. Status: **partial**. Not merged, not deployed. No real
account, device, network call, model or private data was used.

**Tested commit:** `c669579df2ff62421bb2b48df72498a5179450fc` (clean tree; the only untracked
entry was a local `console/node_modules` link to the existing dependencies, used for the
console build). This receipt is committed after that revision and changes no code.

Design and limits: [connectors](../../CONNECTORS.md).

## What CON-001 asks, and what this slice provides

| Part of CON-001 | State | Evidence |
|---|---|---|
| Connector contract: read-only, least-access read scopes, a local file the owner selected, declared identity and freshness, no effect at the origin | Implemented on the branch | `tests/test_connectors.py` `ContractTests` |
| Calendar export reader (iCalendar, RFC 5545: VEVENT, VTODO) | Implemented on the branch | `tests/test_connector_formats.py` `CalendarTests` |
| Contacts export reader (vCard 4.0, tolerating 3.0) | Implemented on the branch | `tests/test_connector_formats.py` `ContactTests` |
| Imported records through the existing source and document pipeline (grants, retrieval, console projection, revision history, M05 invalidation) | Implemented on the branch | `ImportTests`, `AccessTests`, `ContactTests`, `ConsoleHTTPTests` in `tests/test_connectors.py` |
| Observable freshness | Status route and command only; not shown in the console | `test_freshness_is_observable_and_becomes_stale`, `test_status_route_needs_a_session_filters_readers_and_cannot_change_anything` |
| A consented read-only official account | **Not started.** Needs the owner's choice of account | none |
| One harmless approved write | **Not started** | none |

## Commands run on the tested commit

| Command | Result |
|---|---|
| `python3 -m unittest discover -s tests -v` | 920 tests, OK. 58 in `test_connector_formats`, 43 in `test_connectors`; the base `870751368` had 819. |
| The CI backend browser list (`tools/check_desk_browser.py`, `check_knowledge_browser.py`, `check_grounded_browser.py`, `check_os_browser.py`, `check_conversation_browser.py`, `check_memory_browser.py`, `check_memory_context_browser.py`) with `CHROMIUM_PATH=/opt/pw-browsers/chromium` and every output redirected outside the repository | All seven pass |
| `cd console && npm run build`, then `tools/check_console_connected_browser.py` | Build succeeds; 64 checks passed, no page errors |
| `python3 tools/check_memory_plan.py --self-test` and the report | OK, exit 0 |
| `python3 tools/check_requirement_register.py --self-test` and the report | OK, exit 0 |
| `python3 tools/test_source_library.py` | OK |

Not run: console unit tests and offline demo scenarios (no console source changed), the
archive `--verify` scripts (nothing under `third_party/` changed), and GitHub CI (nothing
was pushed).

## Acceptance evidence

- **Grants hide imported items.** A reader without a grant sees no item, record or instance;
  an invitation for `read` reveals exactly that source; revoking the owner's own `read` hides
  it again. Model purpose needs its own `model` grant. Another workspace sees and reaches
  nothing. Real HTTP: the console projection lists imported records to an authorised person
  only, and record inspection of a denied record is indistinguishable from an unknown one.
- **Re-imports create revisions.** A changed item keeps its identity and gains revision 2
  with both revisions in `knowledge_history`; unchanged items keep revision 1; the same
  instant written in UTC or a named zone keeps one identity.
- **Deletion invalidates.** An item missing from a later complete export becomes `missing`,
  its text is cleared, a reviewed statement citing it is invalidated and retrieval stops
  using it. Removing every current item is refused unless explicitly accepted.
- **Withheld is not deleted.** Duplicate identities (readable or not), absent items in an
  export containing an unidentifiable card, and a revoked instance key withhold reviews
  instead of invalidating them; a return under a new revision is not revived.
- **Stale exports are refused.** A lower `SEQUENCE`, `LAST-MODIFIED` or an older export file
  is refused with a receipt, and nothing else changes.
- **Least access.** Events-only instances do not read tasks; attendee names need their own
  scope and addresses are never kept; contact email and telephone each need a scope; photos,
  postal addresses, birthdays, keys and extensions are never read. Contacts never create,
  link or merge entities, including an existing namesake.
- **No effect at the origin.** The export's bytes, modification time and mode are unchanged
  after import; symbolic links, pipes, folders, wrong types, oversized files and a file that
  changes during the read are refused. Hostile text creates no link, action, entity or grant.
- **Offline administration.** The commands refuse while the host holds its lock; the key
  file is private (0600) and refused if shared; renewal keeps the previous key, and a backup
  restored from before a renewal still authenticates.
- **Parsing edge cases:** CRLF, LF and lone CR; folding with space or tab, including a fold
  inside a multi-byte character; escaping and unknown escapes; UTC, floating, all-day, IANA
  and unresolved zones (Windows names, `localtime`, prefixed IDs); clock-change gaps and
  overlaps; nominal and exact durations; recurrence kept as text and never expanded, even for
  an enormous `COUNT`; bounded exception dates; malformed structure; size, line, component,
  property, parameter and item limits; scheduling messages refused.

## Interaction found and handled

The knowledge view's map health counted every connector source as a source without
`MAP.md` and every imported item as outside the map, which would have kept the Pulse
memory-health routine in attention permanently. Map health now ignores connector sources
(`alfred/knowledge.py`, two lines), with a test.

## Not done

A live account connector of any provider and its token custody; device connectors; mail;
any write at an origin; background polling or HTTP-triggered import; a console view of
connector status and a console toggle for `connector.read`; a distinct basis label for
imported records in retrieval and the console (they still carry
`authored_note_not_verified_fact`, while their text states they are unchecked reports from
an export); recurrence expansion; `VTIMEZONE` interpretation; vCard 2.1 and encoded values;
contact suggestions for creating entities; application encryption and key custody (SYS-002).
Private data remains gated by M02 and M05.
