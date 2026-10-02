# Local job coordinator (infrastructure stage 0)

Status, 2 October 2026: implemented on this branch as stage 0 of the staged architecture in [research/INFRASTRUCTURE_2026-10-02.md](../research/INFRASTRUCTURE_2026-10-02.md) (sections 5 and 7). Synthetic data only. Owner and reader HTTP routes and one host worker thread were wired on 2 October (see the end of this document). There is no console view yet, no remote worker, no VM isolation and no sandbox. Nothing is deployed and no background service is installed. It serves PRD rows RUN-002, RUN-003 and SYS-003 only at the single-host, local-subprocess level described here; the provider and mesh decisions in section 7.3 of the research remain open.

| File | Contents |
|---|---|
| `alfred/jobs.py` | `JobCoordinator`, `WorkerBackend`, `LocalSubprocessBackend`, `JobWorker`, `BoundedCache` |
| `alfred/job_kinds.py` | The allowlist of first-party job kinds and the child-process entry point |
| `tests/test_jobs.py` | Acceptance tests with synthetic notes, real SQLite and real subprocesses |

## Design in one paragraph

ALFRED's SQLite database is the only job authority. `JobCoordinator(store)` keeps durable job records beside the existing tables of a `LocalCore`-family store (normally `KnowledgeStore`), separate from the action outbox, whose only effect is still an approved local draft. Execution environments are replaceable backends behind `WorkerBackend`. A worker pulls a job with a time-limited lease, keeps it alive with heartbeats, and reports a result whose bytes the coordinator checks against the SHA-256 the worker states. Clients never talk to workers; they read the job record and its append-only event sequence, so a client can disconnect and later resume from its last cursor while the job carries on.

## Records

Schema version is held in `jobs_meta` (version 1), in the same style as `desk_meta` and `knowledge_meta`. A newer or unknown version is refused.

| Table | Purpose |
|---|---|
| `jobs` | One row per job: scope, actor (the submitting owner credential), kind, canonical parameters, bound inputs, idempotency key (unique per scope and actor) and request fingerprint, `side_effect_free`, state, reason, attempt and `max_attempts`, lease owner, lease token digest and expiry, start time, `cancel_requested`, created and updated times, result artefact hash. |
| `job_events` | Append-only. Per-job sequence numbers start at 1 and increase by exactly 1; SQLite triggers refuse a gap, an update or a delete. Each event has a kind, a small JSON detail and a time. |
| `workers` | Enrolment records per scope: ID, label, declared capabilities (job kinds), the enrolling owner credential, enrolment time and permanent revocation. |
| `artefacts` | Content-addressed results per scope: SHA-256, size, media type, producing job, time, lineage and the bytes. |

Artefact bytes are stored in SQLite in stage 0 (at most 1 MiB each and 256 MiB per scope), so they are covered by the same consistent backup as the job records (Online Backup API or `VACUUM INTO`) and need no second file lifecycle. In stage 2 the bytes would move to an object store keyed by the same hash, with SQLite keeping the metadata. Each artefact records its lineage: the note IDs, revisions and source hashes it was derived from, earlier artefacts it consumed, and the set of sources. Reading or reusing an artefact rechecks every source in that set. Identical bytes from a second job merge the source sets, which fails closed: a reader then needs every source of every producer. Propagating note deletion or tombstones into derived artefacts is not implemented; it belongs to the unfinished deletion and restore accounting (M05).

## States and transitions

```
                         owner cancel
   submit --> queued ----------------------------------------------> cancelled
               |  ^                                                      ^
  worker lease |  | lease expired, or retryable failure                  |
               |  | (side-effect free and attempts left)                 |
               v  |                                                      |
             leased --- worker start ---> running --- verified ---> succeeded
               |                            |          result
               | owner cancel               | owner cancel
               v                            v
             cancel_requested  <------------+
               |  worker stops the backend, or the lease expires (side-effect free)
               +-------------------------------------------------------> cancelled
               |  the job finished before it saw the request -----------> succeeded

   queued, at lease time: inputs no longer permitted or changed,
   or submitter revoked ---------------------------------------------> failed
   leased or running: non-retryable failure, or lease expiry with
   attempts exhausted (side-effect free) ----------------------------> failed

   leased, running or cancel_requested, job with possible effects:
   lease expiry, worker failure or stop ------> effect_unknown --owner finding--> reconciled
```

| From | To | Trigger |
|---|---|---|
| (new) | `queued` | `submit` by an owner, after input policy passes |
| `queued` | `leased` | `lease` by an enrolled worker whose capabilities include the kind; inputs and submitter authority are rechecked first |
| `queued` | `failed` | at lease time: `inputs_denied`, `inputs_changed`, `authority_revoked`, `inputs_too_large` |
| `queued` | `cancelled` | `cancel` (immediate, reason `cancelled_before_lease`) |
| `leased` | `running` | `start` by the lease holder |
| `leased`, `running` | `cancel_requested` | `cancel`; the worker learns of it from its next heartbeat |
| `leased`, `running`, `cancel_requested` | `succeeded` | `complete` with bytes matching the claimed SHA-256 (after a cancel request, an extra `completed_after_cancel_request` event is written) |
| `leased`, `running` | `queued` | lease expiry (`recover`, or the sweep inside `lease`), or `fail(retryable=True)`, only for side-effect-free jobs with attempts left |
| `leased`, `running` | `failed` | `fail`, or lease expiry with attempts exhausted (`attempts_exhausted`), side-effect-free jobs only |
| `cancel_requested` | `cancelled` | the worker stops and reports, or the lease expires, side-effect-free jobs only |
| any active state | `effect_unknown` | a job with possible effects whose lease expires, whose worker reports failure or which is stopped; never retried automatically |
| `effect_unknown` | `reconciled` | `reconcile` by an owner with a finding (`effect_happened`, `effect_did_not_happen`, `undetermined`); recorded as owner acknowledgement, not verification |

`succeeded`, `failed`, `cancelled` and `reconciled` are final. Cancellation is cooperative and is not undo: cancelling a finished job raises `cancellation_is_not_undo`, as in the action outbox. Revoking a worker ends its active leases at once and runs recovery on them.

All registered kinds are side-effect free today. A submitter may declare a pure kind as having possible effects (more conservative, and how the `effect_unknown` path is tested), but may never declare a kind with effects as side-effect free (`side_effect_claim_not_allowed`). For a job with possible effects `max_attempts` is recorded but never used.

## Calls

Every call authenticates a bearer with `store.authenticate` inside the transaction that reads or changes job state. Scope comes from the credential, never from the request.

| Call | Who | Notes |
|---|---|---|
| `submit(bearer, request)` | owner | `request` keys: `idempotency_key`, `kind`, `parameters`, `inputs`, `side_effect_free`, optional `max_attempts` (1 to 10, default 3). Same key and same request returns the existing job; a different request raises `idempotency_key_collision` (409). |
| `view(bearer, job)`, `jobs(bearer, limit=)` | owner, reader | Job record, including `last_sequence`, `finished` and `needs_reconciliation`. |
| `events(bearer, job, after_sequence, limit=)` | owner, reader | Events after a cursor, plus `next_cursor`, `more`, `state` and `finished`, for reconnecting clients. |
| `cancel(bearer, job)` | owner (any owner in the scope) | Queued: cancelled now. Leased or running: `cancel_requested`. |
| `reconcile(bearer, job, finding)` | owner | Only from `effect_unknown`. |
| `artefact(bearer, sha256)` | owner, reader | Rechecks lineage sources with `policy.permitted(..., 'read')` and verifies the SHA-256 on read. Through the cache when one is configured, falling back to the database copy. |
| `enrol_worker(bearer, id, label, capabilities)`, `revoke_worker(bearer, id)`, `workers(bearer)` | owner (enrol, revoke); owner, reader (list) | Capabilities must be registered kinds. Revocation is permanent; enrol a new ID instead. |
| `recover(bearer)` | owner | Explicit sweep of expired leases in the caller's scope. `lease` also sweeps first. |
| `lease(bearer, worker, ttl=)` | the owner credential that enrolled the worker | Returns `job`, `lease` token, `lease_until`, `attempt`, `kind`, `parameters`, `side_effect_free` and `inputs` (each `name`, `sha256`, `size`, `data` bytes), or `None`. |
| `start`, `heartbeat`, `complete`, `fail` | the same credential, with worker ID and lease token | `heartbeat` extends the lease and returns `cancel_requested`. `complete` refuses a hash mismatch (`artefact_hash_mismatch`, recorded as a `result_rejected` event first) and non-JSON bytes declared as JSON. |

A revoked worker gets `worker_revoked`; a revoked or expired owner credential gets `unauthorised`; another owner presenting someone else's worker gets `worker_operator_mismatch`; an expired, replaced or wrong lease token gets `stale_lease`. Other workspaces get `not_found` for jobs and workers and `artefact_not_available` for artefacts.

## Declared inputs and policy

A job declares input references, never paths: `{'note': <24 hex note ID>}` (optionally with an expected `revision`) or `{'artefact': <sha256>}`, at most 16 and 4 MiB in total.

- At submission each note must be ready, from an active source in the caller's scope, and permitted by `policy.permitted(db, principal, source, now, capability)`; the capability comes from the kind's registry entry and is `read` for every current kind. Each note is bound to its current revision and source file hash. A missing, hidden or unpermitted note raises the same `inputs_denied` (403), so the error does not reveal whether a note exists.
- At lease time the same checks run again for the submitting owner, plus the submitter's credential must still be a valid owner. A note that is no longer permitted fails the job with `inputs_denied`; a note whose revision or source hash changed fails it with `inputs_changed` rather than silently running on new content.
- The worker receives only the bytes of those declared, permitted inputs, labelled `input-0`, `input-1` and so on, never note paths, database paths, vault paths or credentials.

## Worker backends

`WorkerBackend` has four calls: `submit(handle, kind, parameters, inputs)`, `status(handle)` (`running` or `finished`), `cancel(handle)` (hard stop) and `collect(handle, timeout)` (returns `BackendResult`: `ok`, `output`, `reason`, `exit_code`, `diagnostics`). A backend has no job authority: leases, retries, cancellation records, input policy and result verification stay in the coordinator.

`LocalSubprocessBackend` is a **local subprocess**. It is not VM isolation, not a remote worker and not a sandbox: the child shares the host, the user account and the kernel with ALFRED. What it does:

- Always runs `alfred/job_kinds.py` with the current interpreter in isolated mode (`-I -S -B`). There is no shell and no arbitrary command; the kind must be in the allowlist, and the coordinator and the child both validate parameters.
- Gives the child an empty environment, a fresh empty private working directory, its own session and process group, and only the declared input bytes on standard input.
- Enforces a wall-clock limit (kills the process group, reason `wall_clock_limit`) and an output size limit (reason `output_too_large`). The child also sets POSIX CPU, address-space, file-size and core limits on itself.
- Installs a Python audit hook in the child before running the kind that refuses file opens, sockets, subprocesses and similar events. Python documents audit hooks as unsuitable for sandboxing; this is a tripwire for mistakes in first-party kinds, not a security boundary. Nothing here prevents a modified kind from using the network.

Current kinds: `word_count` (bytes, lines and words), `summarise_lines` (extractive: the first non-empty lines; not a model summary) and `wait` (sleeps, then hashes its inputs; used to exercise limits, cancellation and reconnection).

`JobWorker` is the pull loop: lease, start, submit to the backend, heartbeat while it runs (stopping the backend when the heartbeat reports a cancel request), then `complete` with the output's SHA-256 or `fail` with the backend's reason. If a heartbeat fails because the lease or authority was lost, the worker stops the process and reports nothing. `run(stop)` loops until stopped or until the worker loses its authority (`stopped_reason`). It runs in an ALFRED-owned process, never inside the job's process.

**Disconnection.** The submitting client holds no connection to the job. The test `test_client_disconnects_and_a_new_client_resumes_from_its_cursor` runs a separate client process that submits a job, reads events until the job has started, records its cursor and exits; the worker loop finishes the job in a real subprocess; a new client over the same database then reads exactly the remaining events from that cursor and the full contiguous sequence.

## Bounded cache

`BoundedCache(root, limit_bytes)` holds content-addressed files under a private directory (mode 0700, files 0600, index `index.sqlite3`) that must be outside this repository; keep it outside vaults and synced folders too. It is never the authoritative copy.

- Hard limit on stored content bytes, enforced by the cache under its own index lock: before a write it evicts least-recently-used unpinned entries, never pinned ones. An item larger than the limit is refused (`cache_item_too_large`); an item that cannot fit beside pinned entries is refused (`cache_full_of_pinned_entries`).
- Explicit pin list (`pin`, `unpin`, `pins`, `put(..., pin=True)`) for offline availability. Pins survive restarts; a pinned item that is missing is reported in `usage()['pinned_missing']`, not fetched.
- Every `get` verifies the SHA-256. A corrupt entry is removed, counted and reported (`cache_entry_corrupt`).
- Opening the cache reconciles crash leftovers: partial writes, index rows with missing files and orphan files. Reopening with a lower limit evicts unpinned entries, and refuses to start if pinned entries alone exceed it.
- `usage()` reports the limit, used and free bytes, entries, pinned entries and bytes, missing pins and corrupt removals. The index file and filesystem block overhead are outside the counted limit.

When a coordinator is given a cache, completed results are mirrored into it and `artefact()` reads through it; a corrupt cached copy falls back to the database copy and is re-cached. In stage 0 this is a demonstration of the interface stage 2 needs; the database copy is local anyway. Downloaded inputs would use the same cache once a remote store exists.

## What is and is not proven

Proven by `tests/test_jobs.py` (53 tests) with synthetic notes, real SQLite and real subprocesses on Linux:

- idempotent submission and collision, per-actor keys, allowlisted kinds and parameters, owner-only submission;
- input binding to revisions; denial at submission under strict grants; denial at lease time after a grant is revoked, a source credential is revoked or the submitter is revoked; `inputs_changed` after a note is revised; the lease carries only the declared bytes;
- worker capabilities; worker revocation stopping lease, heartbeat and completion and requeueing its job; revoked owner credential refused; only the enrolling owner can operate a worker; stale lease tokens refused;
- result hash mismatch rejected and recorded, non-JSON refused, artefacts feeding later jobs, lineage rechecked on read and reuse;
- cancellation of queued, leased and running jobs (the running process is killed through the backend), finished jobs not undone, results after a cancel request recorded honestly;
- lease expiry requeueing side-effect-free jobs with bounded attempts, `effect_unknown` without retry for jobs with possible effects, owner reconciliation, retryable failures;
- a new coordinator over the same database file reading identical state and events and finishing recovered work;
- wall-clock and output limits, the child's own validation errors, an empty child environment and command line without database path or bearer (Linux `/proc`), and the audit-hook tripwire refusing a socket, a file write and a subprocess;
- client disconnection and reconnection from a cursor while a real subprocess finishes the job;
- cache hard limit, LRU eviction, pin protection, oversized refusal, corruption detection, restart persistence, crash reconciliation, private permissions and refusal inside the repository, and coordinator fallback from a corrupt cached copy;
- scope isolation: another workspace cannot view, cancel, read events, lease, read or reuse results; readers can view but not cancel, revoke or recover.

Not proven or not built:

- Containment. A local subprocess is not a sandbox; there is no namespace, seccomp, VM or network isolation. The CPU and memory limits are set but not tested.
- Remote workers, multiple hosts, a mesh, object storage or any vendor service.
- The browser interface and the console. The HTTP routes are loopback-only, behind the existing session, CSRF and Host/Origin checks.
- Survival of a job when the host process itself dies. The child is in its own session and may run on until it finishes or hits its CPU limit, but its result is then lost; the job's lease expires and recovery applies. Recovery is tested by advancing the coordinator clock and by restarting the coordinator, not by killing the host process.
- Real external effects. No registered kind has one; the `effect_unknown` path is exercised with a conservative declaration.
- Power-loss durability beyond SQLite's own guarantees, throughput, fairness between scopes, or Windows support (the backend assumes POSIX).
- Any reasoning quality. These kinds are deterministic text utilities; no model runs.

## How remote workers would plug in later (RUN-002, RUN-003)

The coordinator does not change shape. Remote execution arrives as either a new `WorkerBackend` used by a local `JobWorker`, or a `JobWorker` running on another enrolled machine that calls the same lease, start, heartbeat, complete and fail operations over an authenticated transport. Either way ALFRED's database remains the only job authority and a worker's report remains a claim checked against hashes.

What has to be added, and which owner decisions in research section 7.3 gate it:

1. **Where the coordinator lives** (decision 1). Until decided it stays on the primary laptop with synthetic data; remote workers would buffer events while it is unreachable.
2. **Worker identity over a mesh** (decision 2, plus decision 8 for OpenShell). Stage 0 workers act under the enrolling owner's bearer. A remote worker needs its own credential or device key, an enrolment record carrying device ID, public key, permitted scopes and owner approval, and a check of the mesh identity on every lease. Mesh membership is transport, not authorisation.
3. **Input delivery and results across machines** (decisions 3 and 4). Inputs would be sent as job-scoped bytes or short-lived, single-job object URLs, never database files. Results would be uploaded to an object store keyed by SHA-256, client-side encrypted, and fetched through `BoundedCache`. Which scopes may leave the primary machine is a separate decision and is blocked by M02, M05 and application encryption.
4. **Isolated execution** (decision 5). OpenShell, self-hosted E2B or Firecracker would each be a `WorkerBackend` evaluated with synthetic workloads. Credentials are injected per job after start and never baked into forkable images. Persistent agent computers stay workers, never the system of record.
5. **Always-on worker host** (decision 7). A VPS would run a pull worker; destroying it returns jobs to local recovery.

Effect-bearing kinds additionally need ALFRED's existing approval binding of exact parameters and source conditions (ACT-001) before they could be registered.

## Notes for wiring HTTP routes

- Expose owner and reader calls only: `submit`, `view`, `jobs`, `events` (cursor in the query), `cancel`, `reconcile`, `artefact`, `workers`, `enrol_worker`, `revoke_worker`, `recover`. Keep the worker-side calls (`lease`, `start`, `heartbeat`, `complete`, `fail`) in process in stage 0; they carry raw bytes and lease tokens and have no remote caller yet.
- Keep loopback, Host, Origin and CSRF checks. `parse_json` limits bodies to 16 KiB, which fits `submit`.
- Serve artefact bytes with their stored media type, `X-Content-Type-Options: nosniff` and as an attachment or JSON-encoded value; never render them as HTML.
- Map `Fault.status` directly. Do not reveal lease tokens in any view; they are only returned to the leasing worker.
- Start one `JobWorker` thread per host process with `LocalSubprocessBackend` (like the existing `Supervisor`), stop it on shutdown, and enrol its worker ID with the owner credential the host already holds. Starting a worker is not deploying or installing a service.

## Wired on 2 October 2026

`alfred/desk_http.py` exposes the owner and reader calls under `/desk/jobs` behind the
existing session, CSRF and Host/Origin checks: list and submit (`/desk/jobs`), view
(`/desk/jobs/{id}`), events from a cursor (`/desk/jobs/{id}/events?after=N`), cancel,
reconcile, recover, workers (list, enrol, revoke) and results
(`/desk/jobs/artefacts/{sha256}`, returned as a JSON value, never as a page). Worker
calls (lease, start, heartbeat, complete, fail) stay in-process.

`python3 -m alfred.desk serve` starts one `JobWorker` thread with the local-subprocess
backend for the enrolled worker `local-host`, and a `BoundedCache` of 256 MiB under
the private data directory. Stopping the desk stops the worker; queued work stays
queued and leases expire and are recovered on the next start.

Results now follow M05: a result derived from a note that has since been deleted,
directly or through another result, can no longer be read or used as an input.
Identical results produced from different notes merge their full lineage, so deleting
either note blocks the shared result.

Evidence: `tests/test_jobs.py` (54) and `tests/test_jobs_http.py` (4), including a client
that signs out while its job runs and a new session that resumes from its event cursor.
