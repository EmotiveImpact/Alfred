# Local core v0.2: developer guide

This is a loopback-only development service for synthetic data. It is not a production
web server, hosted assistant, live agent or operational system. The only effect it can
perform is creating a draft in its own SQLite database. No upstream packages are installed.

## Run the demonstrated path

From this repository's development branch with Python 3.10+:

```sh
python3 -m unittest discover -s tests -v
python3 -m alfred.run demo
```

The demo uses a temporary database, provisions synthetic source/owner credentials, accepts
an event, stores an exact action proposal and approval, reopens the database and creates
one local draft. It verifies the stored text with a fresh database read. It then removes
the temporary demonstration database. No bearer secret is printed by the demo.

## Run a persistent development API

Use a private user-owned directory outside the repository. Commands below are POSIX shell
examples. Provisioning emits a secret bearer once; do not paste it into chat, source files,
issues or screenshots. Avoid multi-user shared terminals. Database content is plaintext
within SQLite and needs appropriate OS/disk protection; use synthetic data only for now.

```sh
umask 077
DB="$HOME/.local/share/alfred/local.sqlite"
OWNER=$(python3 -m alfred.run --db "$DB" provision --scope demo --id owner-1 --role owner)
SOURCE=$(python3 -m alfred.run --db "$DB" provision --scope demo --id source-1 --role source)
export OWNER SOURCE
python3 -m alfred.run --db "$DB" serve --port 8765
```

Run the server in its terminal; use a separate authorised client process for API requests.
Provisioning is not exposed over HTTP. Reusing an existing credential ID fails rather
than silently rotating it. Default tokens expire after one day; `--ttl` is explicit.
All CLI-created workspaces are marked synthetic. A mature device-pairing/identity and
credential-rotation interface is still to be built.

To revoke a token without restarting the server:

```sh
python3 -m alfred.run --db "$DB" revoke --id owner-1
```

## HTTP contract

Only 127.0.0.1 is bound. Requests must use the actual localhost/127.0.0.1 Host and port.
Browser Origin requests are rejected pending a deliberate browser-session/CSRF design.
No CORS allowance, arbitrary remote host binding or public reverse proxy is configured.
The development server is single-threaded with bounded body size and socket timeout.
It does not offer production load handling, TLS or denial-of-service protection.

All data/action endpoints require `Authorization: Bearer <token>`. POST bodies must be
JSON objects, at most 16 KiB, with a single Content-Length; duplicate JSON keys, non-finite
numbers, unsupported fields and transfer encoding are rejected. Responses use no-store.
Request bodies and bearer values are not written to HTTP access logs.

| Endpoint | Role | Behaviour |
|---|---|---|
| GET /health | None | Minimal service/capability information, no workspace content |
| GET /v1/state | owner or reader | Last 100 events/actions/audit entries, counts and current staleness |
| POST /v1/events | source | Validate and persist one event, scope/source resolved from credential |
| POST /v1/actions | owner | Store a proposal; no execution |
| POST /v1/actions/{id}/approve | Same owner credential | Bind exact fingerprint and insert outbox entry atomically |
| POST /v1/actions/{id}/cancel | Same owner credential | Cancel before execution; never claim undo |
| POST /v1/worker/tick | owner | Process at most one approved local draft in this workspace |
| POST /v1/actions/{id}/reconcile | Same owner credential | Check an uncertain local draft outcome without resending |

No HTTP endpoint accepts caller-defined actor/scope, arbitrary shell commands, account
credentials, model output as policy, or a boolean claiming a result was verified.
A worker tick is explicit. The service does not independently wake or run a scheduler.

## Event example

Generate current integer timestamps in your client. Values below are placeholders, not
valid fresh data to paste unchanged. Authentication must use a source-role token.

```json
{
  "id": "revision-1",
  "subject": "production-1",
  "kind": "briefing.changed",
  "basis": "reported",
  "observed_at": 100,
  "expires_at": 700,
  "summary": "Synthetic timing revision received."
}
```

Source and workspace are server-derived. Supported kinds are briefing.changed,
status.changed and note. Evidence bases are reported, observed, derived and simulated.
Authenticated source identity does not prove the report is accurate. Replay checks retain
source time rather than replacing it with receipt time. Derived/simulated data cannot
silently take the observation route. Same-time reports are flagged for reconciliation;
full revision graphs and cross-source contradiction resolution remain future work.

## Action example

POST /v1/actions with an owner token and a real future expires_at:

```json
{
  "id": "draft-1",
  "capability": "message.draft",
  "parameters": {"text": "Please review the synthetic timing revision."},
  "expires_at": 700
}
```

The response includes a fingerprint bound to actor, workspace and exact parameters.
Submit `{"fingerprint":"<returned hash>"}` to the approve endpoint. Then an explicit
worker tick with `{}` creates a draft row. It does not contact email or messaging systems.

A successful result has proof type `local_sqlite_draft_readback` and `sent:false`.
The worker reads back actual stored content and checks its hash. This is stronger than
a fixture-supplied verification boolean, but it is only evidence about this local row.

## Failure and recovery semantics

Approval and outbox insertion share one SQLite transaction. Workers claim using a
transactional lease, and each effect rechecks credential expiry/revocation and action
expiry. Parallel worker calls cannot create duplicate local draft rows for one action.

After a crash, an expired executing lease becomes uncertain when a worker ticks. It is
not automatically resent. Reconciliation checks for the previously committed local draft;
if it exists and matches, the result can be verified. If it does not exist, uncertainty
remains pending deliberate resolution. Cancellation after execution cannot claim undo.

The tested at-most-one local draft effect is not a universal exactly-once guarantee.
External APIs will require their own idempotency and verification design. A future device
reporting a state would not by itself establish independent physical safety.

## Implemented protections and remaining gaps

Random 256-bit tokens are stored as hashes, not raw bearer strings. Role/scope lookup,
expiry and revocation are server-side. The database file is restricted to owner access on
POSIX and the CLI sets a restrictive umask. A trusted local OS administrator remains able
to read/change the database and provision credentials. This is not protection against a
compromised host or a multi-tenant hosting boundary.

Remaining: encryption/key storage, user/device identity distinct from token identity,
rotation and recovery, fine-grained per-capability policies, audit tamper evidence,
retention/deletion/export, full pagination, source correction/supersession, continuous
health monitoring, stronger HTTP deployment and authorised external integrations.

## Jev experiment boundary

`alfred/jev.py` builds and validates a fixed Choice interaction for potential relevance
classification. The builder requires explicit caller approval to prepare cloud-bound
context; there is no network transport, secret, API call or service-side egress policy
implemented by this helper. Results remain advisory and cannot grant capability access.
The pinned model identifier comes from official examples and has not been queried here.
