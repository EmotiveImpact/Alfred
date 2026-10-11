# LiveLens tools in ALFRED

ALFRED can use an owner-selected LiveLens API from its existing authenticated Desk
runtime. The optional provider is installed with `livelens-connect`, loaded by
`serve`, and available to an operator or agent caller through Desk HTTP or the
`livelens` command. An installed runtime reports `registeredInAlfred: true`.
The conversation model does not automatically select or invoke these tools.

Installation enables no polling, email, model calls or arbitrary LIVE account.
The demonstrated capture uses a locally generated fictional FFmpeg fixture. A
provider capture requires its own authorised LiveLens source and working provider
configuration. Existing ALFRED private-data gates, including application encryption
and key custody, still apply.

## Install

Use Python 3.11+, a running LiveLens API and a private token for the intended
workspace. No new ALFRED dependencies are needed. Give the API token only the
scopes needed by the tools you plan to use; LiveLens reads and `recordings:write`
are separate permissions. Keep secrets out of shell arguments, logs, Git and vaults.

Create a mode-0600 `livelens.token` file in a private unsynced directory outside Git
and vaults. Put the token in that file, optionally followed by one newline. Create
a mode-0600 connection JSON in the same private directory:

```json
{
  "schemaVersion": 1,
  "scope": "demo-production",
  "workspace": "your_livelens_workspace",
  "sourceCredential": "specialist-livelens",
  "baseUrl": "http://127.0.0.1:8787",
  "tokenFile": "/absolute/private/path/livelens.token",
  "sources": [{
    "id": "selected_source",
    "sessionIds": ["selected_session"],
    "recorderSourceId": "configured_recorder_source"
  }],
  "maxDurationSeconds": 60,
  "timeoutSeconds": 5
}
```

Use the actual ALFRED scope, LiveLens workspace, session and recorder source IDs.
`id` names the source in ALFRED tools; `recorderSourceId` must match a configured
LiveLens source. Omit `recorderSourceId` for reads only. Catalogue entries list
explicit accessible sessions; wildcards are refused. HTTPS is required except for
loopback HTTP; redirects are refused. Duration must be 2–3600 seconds and no larger
than the workspace's configured allowance. LiveLens independently enforces quotas
and recording bounds. Timeout is 0.05–10 seconds. One connection and one specialist
identity are supported per data directory, with up to 100 selected sources.

Stop ALFRED before installing. From the existing checkout:

```sh
python3 -m alfred.desk livelens-connect --data-dir "$ALFRED_DATA" \
  --livelens-config /absolute/private/path/livelens-connection.json
python3 -m alfred.desk livelens --data-dir "$ALFRED_DATA" --tool discover
python3 -m alfred.desk serve --data-dir "$ALFRED_DATA"
```

If using a custom vault, pass its existing `--vault /path/to/notes` option to
installation and tool commands too. Config, token, data directory and tool input
must stay outside that vault. Installation copies bounded config into the private
data directory, creates `specialist-livelens`, and grants this owner `read` and
`connector.read`. It enables explicit source policy for the scope: other note
sources may need their own grants after this switch. Legacy broad reads never
enable network access. No token is printed or placed in the database.

ALFRED rereads the private token file for each operation, so atomic replacement
takes effect without restart. Ownership, mode, symlink and placement are rechecked.
Grants and source identity expire. Renew deliberately, while the host is stopped:

```sh
python3 -m alfred.desk livelens-connect --data-dir "$ALFRED_DATA" \
  --livelens-config /absolute/private/path/livelens-connection.json \
  --renew-livelens-source
```

Renewal extends an unrevoked source identity for at most 30 days and refreshes the
owner's read grants, bounded by the owner's credential expiry. It never restores a
revoked/forgotten identity. It changes the policy epoch, invalidating pending
approvals. Rotate an expiring owner credential through the existing owner workflow.

Capture control is disabled by default. Explicitly enable it during installation:

```sh
python3 -m alfred.desk livelens-connect --data-dir "$ALFRED_DATA" \
  --livelens-config /absolute/private/path/livelens-connection.json \
  --allow-livelens-collection
```

This grants the owner `collection.control`. Every start and stop still needs exact
approval. Reinstalling without this flag revokes the owner's collection grant.
Reads use an already active grant without a new approval each time. Readers need
their own existing source invitations for `read` and `connector.read`; reader role
never permits capture. Installation never grants model access, and no route sends
evidence to a model.

## Use the ALFRED operator command

`livelens` loads the installed provider and the data directory's private owner
credential. `discover` returns tools and current permissions. This is an offline
operator caller; possession of the private data directory is authority. Remote
agents should use the authenticated HTTP transport below.

Put input in a private mode-0600 JSON file outside Git/vaults. A session read uses:

```json
{"operation":"sessions","parameters":{"sourceId":"selected_source"}}
```

```sh
python3 -m alfred.desk livelens --data-dir "$ALFRED_DATA" \
  --tool read --tool-input /absolute/private/path/read.json
```

Other reads: `search`, `evidence`, `context`, `report`, `job`. Results carry source
provenance, original clocks and integrity values plus a gateway receipt. Source
words remain untrusted data, with `instructionsAccepted:false` and
`memoryAccepted:false`. Output can contain evidence; keep it private.

A capture proposal uses:

```json
{
  "operation": "start_recording",
  "parameters": {
    "sourceId": "selected_source", "sessionId": "selected_session",
    "jobId": "operator_selected_unique_job", "maxDurationSeconds": 60,
    "segmentSeconds": 5
  },
  "reason": "Operator-authorised bounded capture"
}
```

```sh
python3 -m alfred.desk livelens --data-dir "$ALFRED_DATA" \
  --tool propose --tool-input /absolute/private/path/capture.json
```

Review the returned operation, exact parameters, reason and expiry. Put the returned
`fingerprint` in a separate private JSON file, `{"fingerprint":"returned hash"}`.
Approve and dispatch the returned action ID explicitly:

```sh
python3 -m alfred.desk livelens --data-dir "$ALFRED_DATA" \
  --tool approve --action-id livelens_RETURNED_ID \
  --tool-input /absolute/private/path/approval.json
python3 -m alfred.desk livelens --data-dir "$ALFRED_DATA" \
  --tool dispatch --action-id livelens_RETURNED_ID \
  --tool-input /absolute/private/path/approval.json
```

Approval expires after ten minutes. It binds actor, person, credential generation,
scope, source-policy epoch, connection config, exact parameters and reason. Changes
invalidate pending approvals. Credentials, grants and pause state are checked
immediately before the write. A later revocation cannot undo a request already
accepted by LiveLens.

An ALFRED action marked `completed` means accepted/reconciled request, not completed
recording. Read `job` with the same source/job IDs to inspect recorder state,
segments and hashes. Stopping is a separate `stop_recording` proposal with
`{sourceId,jobId}` and the same approval sequence.

After timeout/crash, an action stays `uncertain`/`dispatching`. Reconcile the
original stable job ID rather than create another capture:

```sh
python3 -m alfred.desk livelens --data-dir "$ALFRED_DATA" \
  --tool reconcile --action-id livelens_RETURNED_ID
```

Reconciliation reads the job and validates source, session and original duration/
segment parameters. It never repeats the write. Missing/conflicting jobs remain
unresolved. `--tool actions [--action-id ID]` shows actor-private history.

## Operator/agent HTTP transport

Use existing `POST /desk/login` with `{key}` on the ALFRED origin; retain the
HttpOnly session cookie and returned CSRF token. Mutations require exact `Origin`,
JSON content type and `X-CSRF-Token`. Host, fetch metadata, loopback and credential
checks remain. Never put credentials in tool descriptions or source input.

| Route | Input / result |
|---|---|
| `GET /desk/livelens` | Discovery/current permissions; unconfigured host reports `configured:false` |
| `POST /desk/livelens/read` | `{operation,parameters}`; untrusted source receipt |
| `GET /desk/livelens/actions` | Actor-private history, at most 100 |
| `POST /desk/livelens/actions` | `{operation,parameters,reason}`; proposal/fingerprint |
| `GET /desk/livelens/actions/:id` | One actor-private proposal/outcome |
| `POST /desk/livelens/actions/:id/approve` | `{fingerprint}` |
| `POST /desk/livelens/actions/:id/dispatch` | `{fingerprint}`; accepted/uncertain receipt |
| `POST /desk/livelens/actions/:id/reconcile` | `{}`; read-only reconciliation |

Manifests and source text cannot authorise actions. This does not enable the older
`SpecialistBridge` simulation actions or ingest evidence as memory. ALFRED stores
only bounded action/job metadata and audit identifiers; media and raw read results
remain LiveLens-owned. The ledger permits at most 1000 historical actions per scope.
Source forgetting deletes its ledger, revokes access and replays on restore. It
does not stop/delete accepted LiveLens captures; use LiveLens's explicit stop and
retention controls. SQLite free pages/backups retain their existing unencrypted
limitations.

## Verify and disconnect

The real acceptance script starts both applications on disposable loopback
listeners, discovers tools through an authenticated session, reads granted sources,
checks denials, installs/uses the ordinary CLI and approves a bounded fictional
capture. It independently hashes and strictly decodes retained segments. It needs
Node 22.12+, FFmpeg and the actual LiveLens checkout:

```sh
python3 tools/check_livelens_http.py --livelens-root /path/to/tiktok-community-manager \
  --runtime-root /private/unsynced/test-directory \
  --output /private/unsynced/alfred-livelens-http-receipt.json
```

To disconnect, stop ALFRED, revoke the source/collection grant using existing
identity controls and remove its private `livelens-config.json`. Restarting then
reports unconfigured. Already accepted jobs remain bounded by LiveLens; inspect/
stop them explicitly there. Retire/delete the private API token separately. Nothing
installs a background service automatically.

## First-party provenance

The client/gateway derive from EmotiveImpact/tiktok-community-manager commit
`92a19a26e358a70fe5e06ec31b96cbad16e83e13`, paths
`integrations/alfred/livelens_client.py` and `livelens_gateway.py`. Source SHA-256:
`13059d90e4974ab1bd5508e2a3f7b31cc94c2212296c0226c9898e4e4171f75b` and
`cb75ab1500a987ad5baa573f7d7c0eca9adfe7e23d61498f60cea6d6514d1dab`.
Only module descriptions changed here; the policy/ledger wrapper is original code.
No ALFRED `third_party/` code is imported/executed, no new dependency is installed,
and no additional licence grant is asserted.
