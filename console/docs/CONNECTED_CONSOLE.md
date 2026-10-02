# Connected console: real backend adapter

2 October 2026. Implements the read-only projection, selection-to-question and
server-approval connection that `COMPONENT_ARCHITECTURE.md` described as proposed.
The offline demonstration build is unchanged and still uses labelled fixtures.

## How to run it

```text
cd console && npm ci && npm run build      # produces console/dist
python3 -m alfred.desk init                # synthetic workspace, outside the repository
python3 -m alfred.desk access              # reveals the local owner key in a private terminal
python3 -m alfred.desk serve               # then open http://127.0.0.1:8765/console/
```

The Python server serves `console/dist` from its own loopback origin. The console
therefore inherits the existing HttpOnly session cookie, CSRF token, exact Host and
Origin checks and `default-src 'none'` content security policy without any change.
No cross-origin proxy, CORS header or relaxed loopback rule was added.

## Mode is decided by the serving origin, never by failure

`console/index.html` carries `<meta name="alfred-mode" content="demo"/>`. When the
ALFRED server serves the page it rewrites exactly that marker to `connected`. Vite
preview and the standalone file keep `demo`. A failed request in connected mode shows
an honest state (signed out, refused, unreachable); it never loads fixtures.

## Server contract

| Route | Returns |
|---|---|
| `GET /desk/console/workspaces` | The credential's single permitted workspace and current grant revision. |
| `GET /desk/console/projection` | Authorised projection: nodes, edges, server approvals, insights, model availability, data and grant revisions. |
| `GET /desk/console/records/{note|entity|source}:{id}` | Exact note lines, reviewed statements with original support, or source status. Unknown and denied records are both `404 record_not_available`. |
| `POST /desk/conversations/{id}/turns` | Existing queue, now with optional `focus`: the selected record. |

Implementation: `alfred/console_api.py`. The projection is built only from what
`KnowledgeStore.knowledge` and `ReviewedMemory.view` already return to this bearer,
so source grants filter records, counts, labels and links before anything is counted.
Authored note references (`note_reference`), reviewed relationships between
entities (`reviewed_claim`) and the excerpt a reviewed statement cites
(`review_support`) are separate edge layers. Proposed, disputed, conflicting or
invalidated statements produce no edge. Same-name entities remain separate nodes.

If the grant revision changes while the projection is assembled, the server returns
`409 projection_authority_changed` instead of possibly stale data; the console
retries once.

## Console behaviour

- `state/useConnection.ts` checks the session, signs in and out, reads the projection
  with an `AbortController`, polls every eight seconds while the tab is visible and
  replaces the projection wholesale.
- A grant or workspace change clears the selection, dialogs, search and any open answer.
  Revocation or sign-out clears every record. Network loss keeps the last confirmed
  view, labelled `Unreachable` with its confirmation time.
- The record inspector re-reads the selected record from the server whenever the
  projection changes. Changed support appears as "Source changed · review needed".
- Plain text in the command bar asks; `search …` searches; local commands open panels.
  The selected note or reviewed entity travels as `focus`. The server re-authorises
  it, labels it `user_selection_context_not_authority` and refuses an unavailable one.
- The Ask panel shows exact excerpts, retrieval reason, reviewed statements with
  their basis, same-name ambiguities and the model state. With no model configured
  it says so; nothing is generated. An open answer is withdrawn when a source changes.
- Proposing a draft from an answer is a separate step on the existing
  `/desk/conversations/{id}/draft` route. Approval and cancellation use the existing
  `/desk/actions/{id}/approve|cancel` routes with the exact fingerprint. Demo review
  receipts are never converted into server actions.

## Not provided by this increment

No priorities or milestones exist in the backend yet; the panel says so rather than
inventing them. There is one workspace per credential. No voice, account, device or
specialist-system connection. Software-rendered browser checks are not physical
device or GPU certification.

## Acceptance

- `tests/test_console_api.py` (16) and `tests/test_console_focus.py` (12): real HTTP
  and service checks, including other-workspace exclusion, strict-grant non-leakage,
  source change, revocation, same-name entities, static-path traversal and a race.
- `console/tests/connected.test.ts` (18): mapping, reducer selection rules, command
  routing and mode detection.
- `tools/check_console_connected_browser.py` (54 checks): real Chromium against the
  real server and a synthetic vault. Evidence: `docs/evidence/console-connected/`.
