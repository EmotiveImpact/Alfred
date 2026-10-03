# Pilot platform recommendations — 3 October 2026

Stage: `PILOT-GROUNDWORK`. Requirements RUN-001/002/003, SYS-001/002/003,
UX-001/002 and the existing operational workstreams. This is a decision package,
not a second roadmap. [NEXT_STAGE](../docs/NEXT_STAGE.md) remains the active gate.

Recommend keeping the Python/SQLite Core and the connected React/Three/GLSL
console; evaluating Tauri as a client wrapper; keeping one durable job authority;
and prototyping file reads separately from execution. Do not choose a provider or
move private data from these results. Key custody and authority location are still
owner decisions. Desktop packaging does not establish always-on availability.

The [source receipt](pilot-primary-sources-2026-10-03.json) records current official
repository revisions, URLs, fetched-byte hashes and access limitations. Candidate
source was read as data, not installed, executed, imported or treated as agent
instructions. Published security/performance claims remain vendor claims.
Direct Tauri, Cloudflare and Hetzner websites returned egress HTTP 403; official
Tauri/Cloudflare source repositories supplied the docs. Hosting, GPU, boxd,
SpaceFS and pCloud prices/terms have not been independently refreshed here.
Research domain additions are saved in the environment draft; saving did not
change the running network policy. Historical claims below are labelled.

## Native client: evaluate a wrapper, preserve the application

| Choice | Evidence and fit | Cost/risk of the choice | Recommendation |
|---|---|---|---|
| Tauri 2 + Python sidecar | Official README supports arbitrary HTML/JS/CSS and OS WebViews; official sidecar docs explicitly describe Python/PyInstaller and architecture-specific binaries. Root README advertises MIT or Apache-2.0; MIT file fetched. | WebView2/WKWebView/WebKitGTK have different WebGL, media, accessibility and driver behaviour. Rust, binary bundling and per-platform lifecycle/signing become new build surfaces. | First packaging candidate, subject to target-device rendering and lifecycle acceptance. No Tauri dependency was added. |
| Electron + Python child service | Official process-model/security docs describe a browser main process and isolated renderers; root licence is MIT. Chromium is closest to the current browser test target. | Bundled browser/runtime increases update and distribution responsibility. Disable renderer Node integration, enable context isolation/sandbox, constrain navigation/CSP and validate every IPC sender. | Keep as a fallback if the actual console fails OS WebView acceptance. No Electron dependency was added. |
| Browser/PWA connected client | Existing same-origin browser-to-backend acceptance exercises the approved console. | No native service management, OS custody integration, installer or proven offline client. Laptop sleep still stops a laptop Core. | Retain for compatibility and as an enrolled-client option in a later remote stage. |

Suggested first packaging experiment: serve the existing built console from the
existing Python sidecar on a chosen loopback port, retain sign-in and exact
Host/Origin/CSRF checks, and load that origin in one WebView. Do not grant the
renderer a general shell, arbitrary filesystem access or Core credentials through
URLs/localStorage. The parent owns the sidecar process group and lifetime; the
client reports stopped/unreachable truthfully. A remote-Core client would use a
separate transport and enrolment contract, not quietly open this loopback server.

Tauri capability docs say overlapping capabilities combine permissions and do not
protect against malicious Rust, weak scopes, compromised development systems or
WebView vulnerabilities. Enable a named minimal capability set explicitly; do not
auto-enable every capability file or enable remote IPC for arbitrary content.
Updater docs require signed updates; signing key custody/revocation is a separate
operational decision. macOS signing docs describe Apple credentials, a Mac and
notarisation; no account was created or signing credential requested here.

No Rust compiler or WebKitGTK 4.1 development package was present in this builder.
Chromium/software rendering is available and tested; it cannot certify a Tauri
build or physical Mac/Windows rendering. After a dependency/target decision, the
next executable packaging step is an isolated branch with one existing console
window and the packaged Python sidecar, then measure cold start/RSS/package size,
GPU rendering, reduced motion, keyboard/screen-reader navigation, background and
sleep/resume, port contention, service crash, sign-out, upgrade and rollback on
the chosen real OS. Record the target, release signatures and results before
calling it an installed native application.

## Core location and trusted nodes

| Authority location | What stops when the laptop sleeps | Data/key implication | Practical choice |
|---|---|---|---|
| Primary laptop | Core, indexing, queues, local workers and browser connectivity | Smallest new trust surface, interactive unlock possible | Continue synthetic development here. It cannot meet always-on continuity. |
| Always-on home host | Laptop client/local worker stop; home Core and available home workers can continue | Home power/network, patching, physical access and unattended key custody become dependencies | Preferred first continuity experiment if a suitable owner-approved host exists. Availability and hardware suitability are unmeasured. |
| VPS Core | Laptop-local capabilities stop; provider-hosted Core/approved workers can continue | Core can decrypt allowed scopes; provider admin/memory/snapshot access and approved egress matter | Consider only after explicit region, budget, remote-auth and server-readable-data decisions. Do not infer confidentiality from a VPN or disk encryption. |

Exactly one writable SQLite authority per workspace/job. Replicate backups or
read-only projections, never a live database/WAL through a drive. An independent
Core replica needs fencing/leader election and disaster-recovery acceptance; it
is not implemented. Clients and workers may reconnect to the one authority; they
must not manufacture retries or execution rights from a cached job record.

Proposed remote contract, reusing `JobCoordinator` and `WorkerBackend`:

1. Explicitly enrol a device/worker with an OS-held private identity and bounded
   source/purpose/kind grants. No shared owner's bearer embedded in worker images.
2. An authenticated transport supplies device identity to policy; the existing
   loopback endpoints stay loopback. TLS identity, audience, replay protection,
   Origin rules, session revocation and transport resource limits need acceptance.
3. Core issues a job/attempt/worker-bound expiring lease, exact input revisions,
   limits, cancellation state and allowed result types. Workers receive allowed
   bytes, not a vault credential or unrestricted shared drive.
4. Heartbeat checks the current lease and policy. Cancellation is durable and
   cooperative, then a hard stop where the backend supports it. Connectivity loss
   is an observation, not proof of stopped execution.
5. Only the current attempt may publish a hash-checked result. A verified byte
   hash proves integrity, not factual correctness. Source revocation/deletion
   withdraws access to dependent results.
6. On reconnect, reconcile job IDs, attempts, leases, source revisions and effect
   receipts. Retry only work declared side-effect-free. Possible external effects
   become unknown for review; snapshot rollback cannot undo them.

The new [node contract tests](../tests/test_pilot_node_contract.py) exercise actual
concurrent transactions on one SQLite authority with two logical worker IDs:
one lease, stale attempt rejection, cancel/expiry reconciliation and refusal of
an original lease under a different/revoked worker ID. The [SIGKILL recovery
tests](../tests/test_pilot_recovery.py) kill a real child process and distinguish
safe retry from unknown effects. These do not implement worker-specific remote
credentials, prove a second machine, or demonstrate the laptop-off acceptance
scenario. The current local worker still uses the existing owner operator;
remote enrolment is a concrete remaining identity task.

Transport candidates: Tailscale's fetched client root is BSD-3-Clause; the hosted
control plane is a separate service. Headscale's fetched root is BSD-3-Clause,
with self-hosted control-plane operations borne by us. NetBird's current root
explicitly exempts `management/`, `signal/`, `relay/` and `combined/`: those are
AGPLv3, while other parts are BSD-3-Clause. This changes a self-hosted adoption
review and is not cleared by a process boundary. WireGuard remains a transport
option from the prior shortlist; its specific adoption source/terms have not
been refreshed. All require routing, enrolment/revocation and relay-egress
acceptance; none grants ALFRED source permissions or solves Core custody.

## Persistent agent computers and isolated workers

Persistent files, installed packages, running memory, snapshots and external
effects have distinct lifecycles. A persistent computer can preserve its disk
while a process crashes; a snapshot may restore disk/memory while external APIs
remain changed. A disposable worker can isolate one job yet lose disk on teardown.
The worker backend must declare these properties and an export/exit path.

| Candidate | Current evidence / known boundary | Later acceptance before adoption |
|---|---|---|
| Existing local subprocess | Real bounded job ledger/limits and byte results. It is neither VM isolation nor a security sandbox. | Retain only trusted synthetic work; no arbitrary imported code or private-data containment claim. |
| Owner-managed VPS/VM worker | Architecturally fits the existing backend contract. No provider, hypervisor or quota is selected. | Prove permitted nested virtualisation/KVM, image identity, network policy, workspace disposal, budgets, cancellation, host-crash recovery and backup/exit portability. A container alone is not a VM. |
| boxd | Prior 2 October research identified boxd.sh, persistent Linux KVM computers and proprietary/self-host licensing claims. Current site/terms were not refreshed. | Preserve as a persistent-computer candidate, not an adopted dependency. Confirm actual operator/product, licence, persistence/snapshot/fork semantics, credential stripping, quota, deletion, region, KVM and independent egress controls. |
| E2B | Current official SDK and separate infrastructure repositories fetched at pinned revisions, both with Apache-2.0 root licences. The infrastructure README describes Firecracker, memory/disk snapshots, live forks, object storage, PostgreSQL and Linux with KVM. These are published capabilities, not our runtime acceptance. Hosted service terms/prices are not established by source licensing. | Disposable/pause/resume budgets, actual KVM availability, snapshot credential sanitisation, persistent-volume semantics, network isolation, cancellation, unexpected billing, result reconciliation and portable data export. Snapshot restore can include memory; do not infer free idle capacity or safe credential forks from that. |
| NVIDIA OpenShell | Current official root is Apache-2.0. README claims kernel confinement, endpoint-bound credential injection, verified policy changes and telemetry controls. These are published claims, not our containment test. | Review actual kernel/runtime/deployment prerequisites, policy model and GPU access; disable optional telemetry for the approved pilot if appropriate. Test forbidden files/network, credential destinations, escape cases, host failure, cancellation and residual volumes. It is not interchangeable with a persistent boxd computer. |

Fork contract: clone only approved durable file revisions and reproducible package
manifests. Strip service keys, OS identity stores, pairing/session material,
network memberships, pending effect intents and all job leases. Issue a new
identity through the Core only if separately authorised. Copying a whole live
machine snapshot with usable credentials violates this contract. Even a clean
fork needs budgets and independent isolation; the local lease test only proves
that a different worker ID cannot reuse another worker's lease.

## Cloud-backed files: separate the file tier

Keep Core database/secrets local to its authority; durable user files in a
revisioned file tier; indexes rebuildable; backups private and restorable;
worker scratch disposable. Object storage supplies objects, not safe shared
SQLite semantics or multi-client memory.

Space/SpaceFS and the pCloud second-drive experience remain relevant: browse a
catalogue, fetch on demand, pin explicitly for offline availability, and avoid
copying every file to every client. The earlier SpaceFS FUSE/S3 and pCloud
Drive/cache/Sync descriptions are historical; current licensing, account and
offline/deletion semantics were not refreshed. Do not imply a SpaceFS or pCloud
connection from this work.

Current open-source file options read at pinned revisions: JuiceFS Apache-2.0
README describes an object store **and a separate metadata engine**, including
Redis/MySQL/SQLite/TiKV; it is operationally more than a drive mount. rclone's MIT
root supplies transfer/mount tooling, not ALFRED identity or temporal semantics.
SeaweedFS Apache-2.0 README describes S3/POSIX and filer/volume components; adoption
would add a storage control plane and operational responsibility. Compare these
with a deliberately small object API plus existing `BoundedCache` before adding
a filesystem dependency. No new storage dependency is installed.

Proposed file contract: permission-filtered catalogue, opaque file identity,
immutable revision/digest/size, explicit read/write purposes and scope, bounded
fetch/range limits, compare-and-swap writes, explicit offline pins, freshness
labels, conflicting-copy review, deletion tombstones and lineage. A cached blob
is not authority; every return rechecks current policy. Remote offline operation
requires a deliberate revocation-delay/expiry policy, not indefinite cached
grants. A pin does not guarantee availability when a disk is missing/full.

The opt-in [synthetic file-tier model](../prototypes/pilot_file_tier.py) uses the
existing bounded cache, in-memory synthetic objects (maximum 4096 bytes each)
and an independent authority callback. Its six failure/positive tests cover
on-demand/pinned reads, revocation on a cache hit or during fetch, stale offline
copies, compare-and-swap conflicts, pinned capacity, and tombstones purging all
local revisions/pins. It opens no remote connection and mounts no filesystem.
Its catalogue is not durable, its authority callback is local, and it does not
prove encryption, distributed offline revocation, provider deletion or secure
erasure. Metadata digests/lineage remain, and copied files cannot be recalled.

## Workload economics and the provider shortlist

The executable [cost model](../tools/model_platform_costs.py) and
[dated output](pilot-costs-2026-10-03.json) separate active users, sessions, model calls and
input/output tokens, active/idle CPU/GPU hours, Core reservations, stored GB,
full retained backup copies, replicas, object requests, other-service egress,
monitoring, signing, tax/FX and operating staff. Reproduce it with:

```sh
python3 tools/model_platform_costs.py --output /tmp/alfred-costs.json
python3 -m unittest tests.test_platform_costs -v
```

Only Cloudflare R2 Standard list rates were refreshed from the official docs
source: USD 0.015/GB-month, 4.50/million Class A and 0.36/million Class B requests,
rounded up to billable units. Direct R2 egress is free; connected services and
source migrations can charge. Infrequent Access has a 30-day storage minimum
and retrieval charges, so it is not modelled as an automatically cheaper hot
drive. Base scenarios exclude the published free tier to expose paid unit
economics; the calculator can apply it explicitly per one account.

All model, VPS, CPU/GPU, staffing and monitoring rates below are **illustrative
assumptions**, not verified provider prices, approved budgets or capacity tests.
They use 15 sessions/user/month, three model calls/session, 3000 input/600 output
tokens/call, two one-minute CPU jobs/session, 2 GB/user plus two full backups,
no active GPU, tax zero and USD reporting. Headcount is one input, not the model.

| Scenario | Assumed vendor cost/month | Explicit staff cost/month | Total/month |
|---|---:|---:|---:|
| 10 active synthetic pilot | $78.02 | $675.00 (15 h) | $753.02 |
| 100 active, two Core instances costed | $159.50 | $1,800.00 (40 h) | $1,959.50 |
| 1000 active, two Core instances costed | $494.66 | $7,200.00 (160 h) | $7,694.66 |

Two instances being costed does not establish active-active safety. At 100 active
users, a 720-hour idle GPU reservation adds $1,080 under the assumed rate, while
quadrupling output tokens adds $32.40. Ten full backups rather than two add $24.
The illustrative $1000 credit scenario reduces the first invoice to staff costs
but returns to $1,959.50 after credits. No credit eligibility is established;
discounts and quotes remain separate inputs. The tax/GBP sensitivity is an
explicit assumption, not live exchange-rate or tax advice. Model retry/context
growth, support incidents, compliance and capacity need measured pilot inputs.

| Role | Preserve these candidates | Recommendation now / information still needed |
|---|---|---|
| Hosting | OVHcloud, Scaleway, DigitalOcean, Hetzner | Shortlist CPU capacity/regions against the chosen authority/custody model. Fresh invoice-like prices, VAT/currency, backup/egress, nested-KVM rights, cancellation and support terms remain unverified; no ranking by old chat prices. |
| Edge/storage | Cloudflare, Backblaze | R2 is a cost/reference candidate, not a chosen drive. Refresh Backblaze object minimums/egress/regions and both providers' retention/deletion/exit behaviour. |
| GPU/ecosystem | NVIDIA, Nscale, Nebius | Research on-demand versus reservation only after measured model/worker demand. NVIDIA OpenShell source is reviewed; cloud GPU availability, programmes and all partner/credit claims remain unverified. |
| Execution | boxd, E2B, OpenShell; local/VPS workers | Decide persistent versus disposable properties before buying; require the job contract and containment acceptance above. |
| Transport | Tailscale, Headscale, NetBird, WireGuard | Choose after device/custody/remote-auth architecture. A private network is transport, not application policy or tenant isolation. |
| Colocation | Telehouse, Digital Realty | Preserve as later options; no current quote, rack/power/network minimum, relationship or SLA is established. |

Rent elastic compute first where workload is variable; reserve or dedicate only
when measured utilisation/latency and contractual exit costs justify idle
commitments. Colocation/owned hardware must account for amortisation, financing,
power, remote hands, spare capacity, transit, insurance, staffing and physical
failures. Compare a 36-month total-cost range and utilisation break-even against
rent before recommending ownership. Licensing/acquisition requires source/IP,
dependency/model/data rights, security/support obligations and integration/exit
diligence; prior valuation chat is not evidence of financeability or asset value.

Draft questions for a later authorised conversation: exact service/operator and
terms version; permitted KVM/GPU isolation; region/subprocessors/admin access;
idle/snapshot/storage/egress charges; metering and hard spend caps; cancellation
and unknown effects; retention/deletion including snapshots; export formats;
support/SLA and termination/portability; credits eligibility/expiry/post-credit
rates; self-host/licensing rights. No outreach or programme application occurred.

Cloud, Private and Sovereign remain proposed labels. Before commercial claims,
define who holds decrypting keys, which admins can access plaintext, jurisdiction,
tenant separation, audit/support obligations and exit terms, then test them.
Specialist products remain independent interfaces, not bundled deployments.

## Decisions and next executable steps

1. Review the [custody proposal](../docs/KEY_CUSTODY_PILOT.md): local interactive
   unlock versus unattended service-readable keys, and which scopes may leave
   the laptop. Architecture research is ready; crypto adoption/private-data use
   awaits the recorded choice and explicit approval.
2. Select target client OS and Core location for a later synthetic runtime stage.
   Then package the one console/sidecar; implement authenticated worker identity
   on the existing coordinator; test laptop-off/reconnect on real distinct nodes.
   No owner device or VPS is enrolled from this stage.
3. Apply the saved research network additions in environment settings if refreshed
   vendor terms/prices are wanted next. Retry the direct official pages, record
   dates/regions/rates, and replace the labelled assumptions in the cost JSON.
4. Promote the file model only after a durable catalogue/transport/expiry choice,
   independent policy implementation and provider/offline/conflict/deletion tests.
   Keep prototypes opt-in and out of the default server path.

None of these steps is an automatic activation of the private, hosted or
commercial stages. Implementation, synthetic acceptance, merge and deployment
are tracked separately in the stage receipt and requirement register.
