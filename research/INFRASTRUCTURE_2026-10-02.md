# ALFRED infrastructure research: compute lifecycle, cloud-backed files and trusted nodes

Date checked: 2 October 2026. Prepared by a research helper in the 2 October build session using web search and page fetches, then reviewed before commit. Status: research evidence only. Nothing in this document has been installed, executed, purchased or adopted, and nothing here changes ALFRED's implemented status.

## 1. Scope and method

**Question.** The owner wants one coherent ALFRED across two trusted computers and, where appropriate, a VPS while mobile; launchable agent environments; cloud-backed files that need not all fit on the laptop (compared to pCloud's "second hard drive"); and remote work that stays inspectable when the local interface disconnects and reconnects. Researched as three distinct systems: (1) compute lifecycle, persistent agent computers versus disposable job sandboxes; (2) cloud-backed file access; (3) trusted nodes and coordination, including private mesh networking.

**Method.** Web search and fetching of official product pages, documentation, upstream GitHub repository and release pages. Nothing was cloned, installed, run, signed up for or bought. The earlier blocked live-model comparison was not touched.

**Labels.** VERIFIED: official docs, repository page, licence statement or published price list (URL in section 8). VENDOR CLAIM: product statement not independently tested (all performance and security claims). SECONDARY: third-party press or blogs, used only where no official source was reachable. ASSUMPTION: my inference.

**Limits of this check.**

- The GitHub REST API was not reachable from this session, so licences and versions come from rendered repository and release pages; most LICENCE files were not read byte for byte. Record the exact LICENCE file at the exact commit before any adoption.
- GitHub release pages omit the year for current-year releases; 2026 is inferred.
- The fetch tool returns model-generated summaries; re-read decision-critical text at source.
- Not verified: boxd's hypervisor; Hetzner prices (official page rendered placeholders); Daytona's LICENCE file text (fetches failed); Modal and Fly.io prices; any real performance, durability or security behaviour.

Self-hosted does not mean open source, and a permissive code licence does not cover a vendor's hosted service. Per AGENTS.md, ALFRED uses synthetic data until device pairing, source grants, application encryption and deletion/restore accounting are finished.

## 2. Candidate identity table

| Name | What it actually is | Licence | Hosting model | Role in ALFRED | Verification |
|---|---|---|---|---|---|
| boxd (boxd.sh) | Persistent Linux machines as a service ("full KVM virtual machines", "dedicated microVM"; VMM not named) with fork, snapshots, checkpoints, standby, hibernation. Operator Azin Tech Holding; hosted in the Netherlands per terms. | Proprietary (no source or licence published; self-host sold under an "annual license") | Hosted; self-host on "Custom" plan as "a single Rust binary" | Persistent agent computer | Features VERIFIED; self-host VENDOR CLAIM; "proprietary" ASSUMPTION |
| Space / SpaceFS (Space Computer, Inc.) | The owner's "spacedfs" (high confidence: owner supplied the URLs). Cloud filesystem mounted on macOS and Linux (FUSE 3; Windows "coming soon") plus an S3-compatible API ("s3sdk"): content-addressed shards, per-write versions, in-place edits, copy-on-write drive forks. | Proprietary (terms: "limited, revocable" licence, no reverse engineering; GitHub organisation has no public repositories) | Hosted; Enterprise "On-prem and private cloud deployment" on your own S3-compatible storage | File access and object storage | Docs and terms VERIFIED; Enterprise VENDOR CLAIM; private beta of about 100 users SECONDARY |
| pCloud Drive | Desktop virtual drive with local cache and separate two-way "Sync". | Proprietary | Hosted | Analogy only | VERIFIED |
| JuiceFS CE | POSIX filesystem: data chunks in object storage, metadata in Redis, MySQL, PostgreSQL, SQLite, TiKV, etcd and others. v1.4.1 (30 July 2026). | Apache-2.0 | Self-hosted client, own metadata engine and bucket | Shared POSIX layer | VERIFIED |
| SeaweedFS | Blob store with filer, S3 gateway, FUSE mount, WebDAV. v4.48 (28 September 2026). Separate Enterprise Edition. | Apache-2.0 (Enterprise licence not stated) | Self-hosted | Self-hosted storage | VERIFIED |
| rclone | Multi-backend copy/sync tool with VFS-based `rclone mount` and two-way `bisync`. v1.75.1 (4 September 2026). | MIT | Local client | Bounded cache over S3 storage | VERIFIED |
| Backblaze B2 | S3-compatible object storage; versioned by default; Object Lock. | Proprietary service | Hosted | Object storage | VERIFIED |
| Cloudflare R2 | S3-compatible object storage, free egress; no versioning or Object Lock. | Proprietary service | Hosted | Object storage | VERIFIED |
| E2B (e2b-dev/E2B SDKs, e2b-dev/infra) | Firecracker microVM sandboxes with memory-preserving pause/resume and one-to-many snapshots; infra has orchestrator, in-VM `envd`, REST API. | Apache-2.0 (both); E2B Cloud has its own terms | Hosted; self-host via "E2B Embed" (one KVM host, Docker Compose), GCP Terraform, Kubernetes; Enterprise BYOC | Resumable sandbox | VERIFIED |
| NVIDIA OpenShell | Policy-enforcing agent runtime: gateway, supervisor, sandbox; Docker, Podman, Kubernetes or MicroVM drivers; Landlock, seccomp, network namespace, egress proxy. v0.1.2 (28 September 2026). | Apache-2.0 | Self-hosted (local, remote over SSH, or behind reverse proxy) | Containment and policy layer | VERIFIED; identity confidence medium |
| Open-Shell-Menu | Unrelated Windows Start-menu replacement (Classic Shell fork). | MIT (SECONDARY) | Desktop app | None | SECONDARY; excluded |
| Tailscale | WireGuard mesh. Client, CLI and DERP open source; coordination server closed; Windows/macOS GUIs proprietary. v1.102.5 (29 September 2026). | BSD-3-Clause client; service proprietary | Hosted control plane | Private mesh | VERIFIED |
| Headscale | Independent self-hosted Tailscale control server, single tailnet. v0.29.4 (23 September 2026). | BSD-3-Clause | Self-hosted | Mesh control plane | VERIFIED |
| WireGuard | VPN protocol; cryptokey routing; no key distribution. | Kernel module GPL-2.0; others MIT, BSD, Apache-2.0 or GPL | Self-run | Transport primitive | VERIFIED |
| NetBird | WireGuard overlay with central policies. v0.80.0 (1 October 2026). | BSD-3-Clause except `management/`, `signal/`, `relay/` (AGPL-3.0) | Hosted or self-hosted | Private mesh | VERIFIED |
| Firecracker | KVM microVM monitor with memory and device-state snapshots. | Apache-2.0 | Self-run, Linux with KVM | Isolation primitive | VERIFIED |
| gVisor | User-space application kernel (`runsc` OCI runtime). | Apache-2.0 | Self-run | Isolation primitive | VERIFIED |
| Daytona | AI code sandbox runtime. Repository notice: since June 2026 core development is in a private codebase; the public repository is no longer maintained. | AGPL-3.0 for last open release v0.190.0 (SECONDARY) | Hosted; public code frozen | None | Notice VERIFIED |
| Modal Sandboxes | Hosted sandboxes (gVisor or VM runtime), filesystem snapshots, Volumes. | Proprietary service | Hosted only | Hosted burst compute | VERIFIED |
| Fly.io Machines | Hosted VMs; ephemeral rootfs, persistent volumes, Firecracker-snapshot suspend. | Proprietary service | Hosted | Compute / coordinator host | VERIFIED |
| Hetzner Cloud | VPS hosting (Germany, Finland, USA, Singapore). | Proprietary service | Hosted | Coordinator or worker host | Locations VERIFIED; prices SECONDARY |
| restic | Encrypted, deduplicating backup program. | BSD-2-Clause | Local client | Backup | VERIFIED |
| Litestream | Sidecar replicating SQLite incrementally to a file or S3-compatible storage; repository badge shows beta. | Apache-2.0 | Local sidecar | SQLite disaster recovery | VERIFIED |
| Syncthing | Continuous peer-to-peer file sync. | MPL-2.0 | Self-run | Anti-pattern for live SQLite | VERIFIED |

Release years marked 2026 above are inferred from GitHub's date display.

**OpenShell identification.** NVIDIA OpenShell is the only agent-sandbox project of that name found, is active, and matches "launchable agent environments". The other "Open-Shell" found is an unrelated Windows Start menu. Confidence is medium because the owner's source was not given; the owner should confirm. ALFRED's ARCHITECTURE.md names "OpenSandbox" as an earlier containment candidate; that is a different project, not re-researched here.

## 3. Compute lifecycle comparison

### 3.1 What "persistence" can mean

| Layer | Persistent agent computer (boxd style) | Resumable sandbox (E2B, Fly suspend) | Disposable job sandbox (Modal default, plain containers) |
|---|---|---|---|
| Files on root disk | Kept indefinitely | Kept while paused or snapshotted | Discarded at end unless snapshotted or written to a volume |
| Installed packages | Kept (they are files) | Kept with the disk image or snapshot | Rebuilt from image each time |
| Running processes and memory | Kept in standby; written to disk on hibernation | Kept if the pause includes memory | Lost |
| Open network connections | Kept across standby per vendor; clients may still need to reconnect | Dropped on pause or snapshot | Lost |
| Wall clock and timers | Frozen while suspended (boxd) | Frozen while paused (ASSUMPTION, by analogy) | Not applicable |
| Point-in-time rollback | Checkpoints (boxd: up to 10 per machine) | Snapshots | Image rebuild |

Consequence: no vendor's "persistent" guarantee makes an in-VM process a durable job record. boxd documents that "the idle timers watch network activity, not CPU", so a CPU-bound job without inbound traffic can be hibernated mid-work, and "Cron and systemd timers won't fire until the next inbound packet arrives". Fly.io discards suspend snapshots on deploy, migration or maintenance. Firecracker does not guarantee guest network connectivity after resume and closes open vsock connections. E2B drops connections during snapshotting. Durable job state belongs in ALFRED's coordinator.

### 3.2 Candidate capabilities

| Candidate | Isolation | Fork | Snapshot | Pause/resume | Hibernation | Lifetime limits | Host / resource needs |
|---|---|---|---|---|---|---|---|
| boxd (hosted) | KVM VM / "dedicated microVM" (VMM unnamed) | Memory and disk; speed claims inconsistent ("<10ms" docs, "under 200ms" homepage) | Named memory+disk snapshots, "replicated across a few workers", outlive source | Standby: "sub-millisecond" wake on first inbound packet | Default after 4 h network-idle; about 85 ms wake; bills disk only | Up to 10 checkpoints per machine (restore reboots into state); scheduled disk backups (default 7 day retention) | Default 2 vCPU, 8 GB RAM, 100 GB disk; self-host requirements unpublished |
| E2B Cloud | Firecracker microVM | One snapshot can create many sandboxes | Memory and filesystem, or filesystem-only (reboots on resume) | Pause about 4 s per GiB RAM, resume about 1 s; paused: no TTL, not billed | Pause is the equivalent | Continuous run 1 h (Hobby) or 24 h (Pro), reset by pause/resume; default idle timeout 5 min with `onTimeout: "kill"` | Hosted |
| E2B self-hosted | Firecracker, cgroups, network namespaces | As above | Pause ships memory/disk diff to object storage | Yes | Yes | Operator-defined | Linux with KVM (Embed) or GCP/Kubernetes |
| NVIDIA OpenShell | Container plus Landlock, seccomp, netns, policy proxy; optional MicroVM driver | Not documented | Not documented | Stop/start keeps "persistent workspace data"; detach leaves process running; reconnect "replays up to 1 MiB of recent output" | Not documented | Not documented | Linux, macOS (Apple Silicon), WSL 2 experimental; Docker 28+ or Podman 5.x; MicroVM needs KVM or Hypervisor.framework; version 0.1.x |
| Firecracker (primitive) | KVM microVM | Restoring one snapshot into several VMs is documented as insecure without mitigation | Guest memory and emulated hardware state; diff snapshots in developer preview | Via snapshot/restore | Via snapshot to disk | n/a | Linux with KVM; x86_64 and aarch64. |
| gVisor (primitive) | User-space kernel intercepting syscalls | n/a | Checkpoint/restore referenced in docs (not examined) | n/a | n/a | n/a | Linux 5.6+, x86_64 or ARM64. |
| Modal Sandboxes | gVisor or VM runtime | Via filesystem snapshots | Filesystem snapshots | Not documented on page read | No | Default 5 min, maximum 24 h | Hosted only. |
| Fly.io Machines | Firecracker snapshots for suspend | No | Suspend captures CPU registers, memory, open file handles | Resume "a few hundred ms"; plain stop loses memory | Suspend only for 2 GB memory or less, no swap; snapshot discarded on deploy, migration or maintenance | Not stated | Hosted; rootfs ephemeral, volumes persist. |

### 3.3 Security notes that affect design

- **Snapshot cloning duplicates secrets.** Firecracker warns that resuming one guest state more than once means "identifiers, random numbers and random number seeds, the guest OS entropy pool, as well as cryptographic tokens" may not be unique; VMGenID can trigger reseeding. ASSUMPTION: the same applies to any memory-preserving fork (boxd forks, E2B one-to-many snapshots). Inject short-lived, job-scoped credentials after start; never bake credentials into forkable images.
- **Forks copy data.** Forking a machine or drive holding ALFRED material duplicates it inside the vendor's estate: a data-movement decision.
- **Policy outside the agent.** OpenShell's out-of-process enforcement fits ALFRED's "models propose, independent policy decides" rule, but does not replace ALFRED's approval binding of exact action parameters.

## 4. File access comparison

### 4.1 Comparison

| System | On-demand reads | Cache bounds | Explicit offline availability | Revisions | Conflicts | Quotas / limits | Recovery |
|---|---|---|---|---|---|---|---|
| pCloud Drive (analogy) | Yes, "available on demand" | User-set cache size (minimum recommended 5120 MB); when full "the newer files overwrite the older ones" | Desktop: two-way Sync of chosen folders. Mobile: download only, offline edits not synced back | Not examined | Not documented | Plan quota | Not examined |
| Space / SpaceFS | Yes, byte-range streaming | Not documented; content-addressed shards (SHA-256, FastCDC) so a cached shard "can never be stale" | Not documented | Every mutation is a version; append-only history; restore creates a new head; retention not documented | Last writer wins without preconditions; `if_version` loser gets HTTP 412. Mount writes journal locally and "reach the API within seconds" | 5 GiB PUT, 5 TiB multipart, fork depth 8 | Rollback and forks; terms: history "not a substitute for an independent backup" |
| rclone VFS / mount | `full` mode caches only read ranges (sparse files); `off`/`minimal`/`writes` read remote directly | `--vfs-cache-max-size`/`--vfs-cache-min-free-space` are soft (checked every poll interval, default 1 min; "open files cannot be evicted"); `--vfs-cache-max-age` default 1 h | No VFS pinning (ASSUMPTION); use `copy`/`sync` or `bisync` ("advanced command") | From backend (B2 yes, R2 no) | No cross-machine locking; two instances sharing a cache "can potentially cause data corruption"; bisync writes `.conflict1` copies | Backend | Dirty files uploaded on next run with same flags; upload retries in `writes` mode |
| JuiceFS CE | Yes, POSIX, by chunk | `--cache-size` default 102400 MiB, soft ("may exceed configured value") | Not found | Not examined | Close-to-open; BSD and POSIX locks | Bucket and metadata engine | Needs metadata engine and bucket (objects are chunks, not files); `--writeback` can lose data permanently |
| SeaweedFS | Yes, FUSE/filer/WebDAV/S3 | Not examined | No | Not examined | Not examined | Operator | Operator; advanced recovery in Enterprise Edition |
| Backblaze B2 | Object API | n/a | n/a | Versioned by default; lifecycle rules | Object semantics | Account | Versions plus Object Lock (compliance mode "cannot be removed by any user") |
| Cloudflare R2 | Object API | n/a | n/a | None (`PutBucketVersioning` unimplemented) | Conditional `If-Match`/`If-None-Match` | Account | No Object Lock; rely on client snapshots (restic) |
| Syncthing | No, full copies | n/a | All local | Optional; "not a great backup application" | Loser renamed `.sync-conflict-...` and propagated | Local disk | Deletions propagate everywhere |

### 4.2 Why a live SQLite database and WAL must stay on a local disk

ALFRED's authoritative store is SQLite. The SQLite project's own documentation rules out placing a live database on a synced folder, FUSE mount or network filesystem:

- WAL mode: "All processes using a database must be on the same host computer; WAL does not work over a network filesystem", because the wal-index lives in shared memory that separate hosts cannot share (sqlite.org/wal.html).
- The WAL file "is part of the persistent state of the database"; "If a database file is separated from its WAL file, then transactions that were previously committed to the database might be lost, or the database file might become corrupted" (sqlite.org/wal.html).
- Background backup tools that copy a database mid-transaction can produce a copy with "some old and some new content" that is corrupt; copying a database without its journal is listed as likely to cause corruption; network filesystems, "NFS in particular", can have broken locks that corrupt databases under concurrent access (sqlite.org/howtocorrupt.html, sections 1.2, 1.4 and 2.1).
- "SQLite is designed for situations where the data and application coexist on the same machine"; if data is separated from the application by a network, use a client/server database, or keep WAL access on the database host and proxy requests to it (sqlite.org/useovernet.html).

Applied to the candidates (ASSUMPTION from the documented behaviour): Syncthing and pCloud Sync move the database, `-wal` and `-shm` files independently, so another device can receive a mismatched pair, and database conflict copies cannot be merged. rclone VFS uploads each file separately after a write-back delay with no cross-file atomicity. Space's mount publishes journalled writes "in the background", per key, with no documented cross-file transaction. JuiceFS supports POSIX locks, but WAL's shared-memory index still cannot span hosts.

Safe pattern: keep the authoritative database on one host's local disk; make consistent copies with the Online Backup API or `VACUUM INTO` (sqlite.org/backup.html); back those up (for example encrypted with restic) or replicate with Litestream (beta); test restore.

## 5. Coordination and node trust comparison

| Option | Enrolment | Node identity | Access policy | Control plane | Licence | Notes for ALFRED |
|---|---|---|---|---|---|---|
| Tailscale (hosted) | Login or auth keys | Per-device WireGuard keys; servers by tags | ACL policy; tags | Closed-source coordination server; DERP relays | Client BSD-3-Clause; service proprietary | Tagged devices have key expiry "disabled by default"; set expiry policy explicitly. |
| Headscale (self-hosted) | Pre-auth keys, web auth, OIDC | As Tailscale | ACLs, tags (not OIDC groups) | Self-hosted, single tailnet, embedded DERP | BSD-3-Clause | Needs a reachable host such as a VPS; project discourages reverse proxies and containers; independent of Tailscale Inc. (one maintainer employed there). |
| NetBird | Not examined in detail | WireGuard keys | Central access policies | Hosted, or self-hosted (Linux VM, 1+ CPU, 2 GB RAM, public domain, Docker) | Client BSD-3-Clause; control plane AGPL-3.0 | AGPL control plane must be recorded if self-hosted. |
| Plain WireGuard | Manual key exchange | Public key bound to allowed IPs | AllowedIPs only | None | Kernel GPL-2.0; others vary | Key distribution "out of scope"; fine for fixed hosts, poor for roaming laptops (ASSUMPTION). |
| boxd networks | Org API keys and device login | Machine names within an org | Tag-based networks: machines reach each other when they share a network | boxd | Proprietary | Can join a Tailscale network. Scope ends at boxd machines. |
| OpenShell gateway | `openshell gateway add`, browser login or mTLS | Gateway-registered sandboxes | Declarative YAML policies, egress proxy | Self-hosted (SQLite or Postgres state per search snippet only) | Apache-2.0 | Sandboxes only, not general devices. |
| E2B API | API key | Sandbox IDs | Per-sandbox | E2B Cloud or self-hosted API | Apache-2.0 code; hosted service proprietary | Controls sandboxes only. |

**What none of these provide.** A mesh gives authenticated transport. It does not place jobs, hold durable job records, cancel safely, retry only safe work, reconcile uncertain effects, or collect and verify results. Those are ALFRED responsibilities under ALFRED policy. Mesh membership is a network fact, not an authorisation.

**Coordinator requirements (ASSUMPTION, design proposal derived from the evidence).**

- Durable job record in ALFRED's SQLite: `queued`, `leased`, `running`, `cancel_requested`, `succeeded`, `failed`, `effect_unknown`, `reconciled`.
- Leases with heartbeat and expiry, so a hibernated or disconnected worker loses its lease rather than silently holding the job.
- Idempotency key per job; automatic retry only for side-effect-free jobs; anything with an external effect goes to `effect_unknown` for reconciliation.
- Cancellation: cooperative signal through the lease plus a hard stop through the backend.
- Worker identity: an ALFRED enrolment record (device ID, public key, owner approval, permitted scopes, revocation), checked against the mesh identity on every lease.
- Results: content-addressed artefacts (SHA-256) recorded with job, worker, input revision and policy decision. A worker's "done" is a claim; ALFRED verifies hashes and records acknowledgement separately.
- Reconnection: append-only `job_events` with sequence numbers; the console resumes from its last seen sequence (like OpenShell's output replay, but owned by ALFRED).

## 6. Cost and data-egress notes

All prices were read on 2 October 2026, exclude tax, and can change. Arithmetic examples are illustrative ASSUMPTIONS, not quotes.

| Service | Published price (as read) | Egress and caveats |
|---|---|---|
| Backblaze B2 (pay as you go) | USD 6.95 per TB-month; first 10 GB free; Class A, B and C API calls free; Class D USD 0.004 per 10,000 after 2,500 per day free; no minimum storage duration | Free egress up to 3x average monthly stored, then USD 0.01 per GB. |
| Cloudflare R2 Standard | USD 0.015 per GB-month; Class A USD 4.50 per million; Class B USD 0.36 per million; free tier 10 GB-month, 1 million Class A, 10 million Class B per month | Egress free. Infrequent Access: USD 0.01 per GB-month, 30 day minimum, USD 0.01 per GB retrieval. Usage rounded up to next billing unit. |
| boxd | EUR 0.049 per vCPU-hour while running; EUR 0.015 per GiB-hour of resident RAM; EUR 0.0001 per GiB-hour of written disk; EUR 30 starting credit; hibernated machines pay disk only | Custom plan for self-hosting, EU residency, SSO and audit logs, "annual license" (price not published). Egress price not stated. |
| E2B | Hobby USD 0 plus USD 100 credits (1 h sessions, 20 concurrent); Pro USD 150 per month plus usage (24 h sessions, 100 concurrent); CPU USD 0.000014 per vCPU-second; RAM USD 0.0000045 per GiB-second; storage free (10 or 20 GiB included); Enterprise USD 3,000 monthly minimum | Paused sandboxes not billed. Egress price not stated. |
| Space / SpaceFS | Individual USD 15 per month (USD 180 yearly); Teams USD 30 per member per month; Enterprise custom | Storage allowance and egress not captured. |
| Tailscale | Personal free (up to 6 users, unlimited user devices); Standard USD 8 per user-month; Premium USD 18 per user-month | Not examined. |
| Hetzner Cloud | Official page rendered no prices. SECONDARY sources report increases on 1 April 2026 and 15 June 2026 and replacement of CX22 by CX23, with small shared plans around EUR 5 to 6 per month by August 2026. | Must be checked in Hetzner's console before any decision. |

Illustrative arithmetic (ASSUMPTION):

- 500 GB of encrypted backups: B2 about USD 3.48 per month (0.5 TB x 6.95), with up to 1.5 TB of free monthly egress; R2 Standard about USD 7.35 per month ((500 minus 10 free) GB x 0.015) with free egress.
- One boxd machine running continuously for 30 days with 2 vCPU and 4 GiB resident RAM: about EUR 70.56 (vCPU) plus EUR 43.20 (RAM) = EUR 113.76 per month, plus disk. The same machine hibernated with 20 GiB written costs about EUR 1.44 per month.
- One E2B sandbox with 2 vCPU and 4 GiB running 8 hours a day for 30 days: about USD 24.19 (CPU) plus USD 15.55 (RAM) = USD 39.74 of usage; sessions over 1 hour need the USD 150 Pro plan.

Caveat: free egress does not settle data movement. Moving real personal, company or client material to any vendor is a separate owner decision and is currently blocked by the unfinished M02/M05 gates and application encryption.

## 7. Recommendation: reversible staged architecture

### 7.1 Principles

1. ALFRED's SQLite database is authoritative on exactly one host's local disk at a time. Everything else is a client, replica, cache, backup or worker.
2. The job coordinator lives inside ALFRED and owns durable job records, leases, events and results. Execution environments are replaceable backends behind one interface.
3. The mesh is transport. ALFRED enrolment and policy decide what a device may receive or do.
4. Files that are not the database are stored as content-addressed objects in S3-compatible storage behind a bounded local cache with an explicit pin list, so the laptop need not hold everything.
5. Every vendor is reachable only through an adapter, so it can be removed without data migration surprises. No proprietary service becomes the system of record.
6. Synthetic data only until the private-data release gates are met.

### 7.2 Stages

| Stage | What is built | Spend / vendor | Reversal |
|---|---|---|---|
| 0. Interfaces, no infrastructure | `jobs`, `job_events`, `workers`, `artefacts` tables; lease/heartbeat; idempotency keys; `effect_unknown` reconciliation; console event cursor for reconnect. `WorkerBackend` interface (`submit`, `status`, `events`, `cancel`, `collect`) with a **local-subprocess** backend on the same host, inside existing loopback, Host/Origin/CSRF boundaries. Consistent backups with the Online Backup API or `VACUUM INTO`, restore drill on synthetic data. | None | Delete tables; nothing external. |
| 1. Two trusted computers | Device enrolment records with owner approval and revocation. Second computer runs a pull-based worker that leases jobs over a private mesh and returns artefacts; it never opens the authoritative database file. Read-only backup copy may be held on the second machine. | Mesh choice (Tailscale Personal is free; Headscale needs a host) | Remove worker enrolment; leave mesh. |
| 2. Cloud-backed files | Content-addressed artefact store: objects keyed by SHA-256 in an S3-compatible bucket, client-side encrypted, with a local LRU cache that has a hard byte limit enforced by ALFRED and a separate pin list for explicit offline availability. Optionally `rclone mount` with `--vfs-cache-mode full` and `--vfs-cache-max-size` for human browsing of non-database folders only (understanding the limit is soft). Encrypted restic backups of database snapshots to the same or a second bucket. | Paid object storage account | Objects are plain encrypted blobs with a local manifest; copy out with rclone and close the account. |
| 3. VPS while mobile | Small VPS on the mesh as an always-on worker host and, optionally, a Headscale control plane. Workers buffer events locally and flush when the coordinator is reachable. | Paid VPS | Destroy VPS; workers return to Stage 1. |
| 4. Isolated execution backends | Add backends behind the same interface, evaluated with synthetic workloads: (a) NVIDIA OpenShell locally (Apache-2.0, early 0.1.x) for policy-enforced agent sandboxes; (b) self-hosted E2B Embed or direct Firecracker on a KVM host for microVMs; (c) hosted E2B Cloud for disposable bursts or boxd for persistent agent computers. Credentials injected per job, never baked into forkable images. | Possibly paid hosted plans | Disable backend; jobs fall back to local-subprocess. |

Space/SpaceFS is closest to the "second hard drive" experience and adds forks, versioned and conditional writes that suit agents. It is proprietary, early (private beta per press) and its terms disclaim liability for deleted content. It could be trialled in Stage 2 as an optional, non-authoritative view over synthetic or already-backed-up material, with ALFRED's manifests and backups remaining the record.

### 7.3 Decisions that need the owner

| # | Decision | Exact choice needed | Default until decided |
|---|---|---|---|
| 1 | Where the authoritative database and coordinator live | Choose one: (a) primary laptop (simplest, but remote work is only inspectable live when the laptop is online; workers buffer meanwhile), (b) an always-on home computer, or (c) a VPS (always inspectable from anywhere, but moves the entire ALFRED dataset to a provider and requires a hosting jurisdiction). | (a) primary laptop, synthetic data only. |
| 2 | Mesh control plane | Choose Tailscale hosted (free Personal plan; closed-source coordination server, which ASSUMPTION: sees device and network metadata), Headscale self-hosted (BSD-3-Clause, needs a public host), NetBird self-hosted (AGPL-3.0 control plane), or plain WireGuard (two fixed hosts only). Also choose a node key expiry policy, because Tailscale disables expiry for tagged devices by default. | No mesh; Stage 0 only. |
| 3 | Object storage vendor and region | Choose B2 (versioning on by default, Object Lock, 3x free egress) or R2 (free egress, no versioning or Object Lock), the bucket region, and a monthly spending ceiling. | No bucket. |
| 4 | Sensitive-data movement | State which scopes (personal, company, client), if any, may leave the primary machine, in what form (client-side encrypted only, or never), and to which named vendors. Currently blocked by M02/M05 and application encryption; this decision cannot unblock them. | Nothing real leaves the primary machine. |
| 5 | Compute vendor commitment | Whether to open paid accounts with E2B Cloud, boxd or Modal, or self-host only (OpenShell, E2B Embed, Firecracker). For hosted options: maximum monthly spend and whether forks/snapshots may contain any ALFRED material. | Local-subprocess only. |
| 6 | Space/SpaceFS trial | Whether to trial a proprietary early-stage file service, and with which data. | Not adopted. |
| 7 | VPS provider and jurisdiction | Provider, country, plan size and spending ceiling (prices must be read in the provider's console on the day). | No VPS. |
| 8 | Confirm "OpenShell" | Confirm NVIDIA OpenShell is the intended project. | Treat as a candidate only. |

### 7.4 Rejected options

| Option | Reason |
|---|---|
| Live SQLite database or WAL on Syncthing, pCloud, Space, an rclone mount or a JuiceFS mount | SQLite documentation: WAL does not work across hosts; separating database and WAL loses or corrupts data; network locks are unreliable. |
| Two writable ALFRED databases on two computers, merged by file sync | Produces conflicting copies with no safe merge; risks silently merging namesakes and breaking review lineage, supersession and revocation records. |
| Treating VM memory persistence (standby, hibernation, suspend, snapshots) as job durability | boxd hibernates on network idle and freezes clocks; Fly discards snapshots; Firecracker and E2B drop connections on snapshot or resume. |
| Any proprietary service (boxd, Space, E2B Cloud, Modal) as system of record | Proprietary, early-stage or both; Space and boxd terms place backup responsibility on the customer and disclaim liability. Use only behind adapters with ALFRED-owned records. |
| Daytona open-source code as a new dependency | Public repository no longer maintained since June 2026; development moved private. |
| JuiceFS or SeaweedFS in Stages 1 to 3 | Require operating a metadata engine or storage cluster; disproportionate for one owner. JuiceFS SQLite metadata is standalone-only. Reconsider only if a shared POSIX filesystem across many workers becomes a requirement. |
| Exposing ALFRED's development server publicly (including tunnelling services) | Conflicts with ALFRED's loopback, Host/Origin/CSRF boundary rules. |
| Baking credentials into forkable images or snapshots | Firecracker documents duplicated entropy and tokens on multiple restores. |
| Open-Shell-Menu | Unrelated Windows Start menu. |

## 8. URLs consulted

Compute lifecycle:

- https://boxd.sh/
- https://boxd.sh/pricing/
- https://boxd.sh/terms/
- https://docs.boxd.sh
- https://docs.boxd.sh/llms-full.txt
- https://docs.boxd.sh/guides/suspend-resume.md
- https://runtimewire.com/article/boxd-2m-pre-seed-cloud-computers-ai-coding-agents (search result only, not relied on)
- https://github.com/e2b-dev/E2B
- https://github.com/e2b-dev/infra
- https://docs.e2b.dev/sandbox/persistence.md
- https://docs.e2b.dev/faq/sandbox-lifetime.md
- https://docs.e2b.dev/sandbox/filesystem-only-snapshots.md
- https://docs.e2b.dev/sandbox/snapshots.md
- https://e2b.dev/pricing
- https://github.com/NVIDIA/OpenShell
- https://github.com/NVIDIA/OpenShell/releases/latest
- https://docs.nvidia.com/openshell/llms.txt
- https://docs.nvidia.com/openshell/about/architecture
- https://docs.nvidia.com/openshell/about/installation
- https://docs.nvidia.com/openshell/how-it-works/gateways/overview
- https://docs.nvidia.com/openshell/how-it-works/sandboxes/overview
- https://perspectives.nvidia.com/nvidia-openshell/sandbox-ai-agent-code-execution-no-containers/ (search result)
- https://github.com/zipa/Open-Shell-Menu and https://en.wikipedia.org/wiki/Classic_Shell (search results, for disambiguation)
- https://github.com/firecracker-microvm/firecracker
- https://raw.githubusercontent.com/firecracker-microvm/firecracker/main/docs/snapshotting/snapshot-support.md
- https://gvisor.dev/docs/
- https://github.com/google/gvisor
- https://github.com/daytonaio/daytona
- https://cdn.jsdelivr.net/gh/nightona-co/nightona@main/README.md (search result, SECONDARY for Daytona licence)
- https://modal.com/docs/guide/sandbox
- https://docs.fly.io/machines/overview
- https://docs.fly.io/reference/suspend-resume/

File access and storage:

- https://spacefs.com/
- https://spacefs.com/enterprise/
- https://spacefs.com/terms/
- https://docs.spacefs.com/
- https://docs.spacefs.com/llms.txt
- https://docs.spacefs.com/start/mount.md
- https://docs.spacefs.com/guides/concurrency.md
- https://docs.spacefs.com/guides/forks.md
- https://docs.spacefs.com/guides/history-and-rollback.md
- https://docs.spacefs.com/guides/placement.md
- https://docs.spacefs.com/how-it-works/architecture.md
- https://docs.spacefs.com/reference/limits.md
- https://github.com/Space-Computer-Inc
- https://pulse2.com/space-raises-2-4-million-pre-seed-to-build-ai-native-distributed-filesystem/ (search result, SECONDARY)
- https://help.pcloud.com/article/pcloud-drive-vs-pcloud-sync
- https://help.pcloud.com/article/offline-access
- https://pcloud.com/help/drive-help-center/what-is-cache-size (search result)
- https://github.com/juicedata/juicefs
- https://github.com/juicedata/juicefs/releases/latest
- https://juicefs.com/docs/community/guide/cache/
- https://juicefs.com/docs/community/databases_for_metadata/
- https://juicefs.com/docs/community/introduction/
- https://github.com/seaweedfs/seaweedfs
- https://github.com/seaweedfs/seaweedfs/releases/latest
- https://rclone.org/commands/rclone_mount/
- https://rclone.org/bisync/
- https://rclone.org/s3/
- https://github.com/rclone/rclone
- https://github.com/rclone/rclone/releases/latest
- https://www.backblaze.com/cloud-storage/pricing
- https://www.backblaze.com/docs/cloud-storage-object-lock
- https://www.backblaze.com/docs/cloud-storage-lifecycle-rules (search result)
- https://developers.cloudflare.com/r2/pricing/
- https://developers.cloudflare.com/r2/api/s3/api/
- https://docs.syncthing.net/users/faq.html
- https://docs.syncthing.net/users/syncing.html
- https://github.com/syncthing/syncthing
- https://restic.net/
- https://github.com/benbjohnson/litestream

SQLite:

- https://www.sqlite.org/useovernet.html
- https://www.sqlite.org/wal.html
- https://www.sqlite.org/howtocorrupt.html
- https://www.sqlite.org/backup.html

Mesh and hosting:

- https://github.com/tailscale/tailscale
- https://github.com/tailscale/tailscale/releases/latest
- https://tailscale.com/opensource
- https://tailscale.com/pricing
- https://tailscale.com/kb/1068/tags
- https://github.com/juanfont/headscale
- https://github.com/juanfont/headscale/releases/latest
- https://headscale.net/stable/about/features/
- https://github.com/netbirdio/netbird
- https://github.com/netbirdio/netbird/releases/latest
- https://www.wireguard.com/
- https://www.hetzner.com/cloud
- https://privatedevops.com/news/hetzner-june-2026-cloud-price-increase-what-to-do and https://kimmo.suominen.com/stuff/cpc-2026-08.txt (search results, SECONDARY for Hetzner prices)
