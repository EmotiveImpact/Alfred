# Plan reconciliation record, 2 October 2026

How the owner-supplied [reconciliation v1.1 and whole-product mandate](sources/2026-10-02/README.md)
were absorbed into the existing plan. The [PRD](PRD.md) stays the requirements authority,
the [roadmap](ROADMAP.md) the sequence and the [memory backlog](../plans/memory-backlog.json)
the bounded M programme. Delivery state lives in one place:
[the requirement register](../plans/requirement-register.json). Sources reviewed,
overlaps and missing material are in [the source-coverage register](../plans/source-coverage.json).

## Repository truth checked on 2 October

The reconciliation's table matched the live refs: main `8398c7437`, PR #15 `f7c41ce22`,
PR #16 `18dcfb39a`, PR #17 `07573dfdb`, with PR #17 containing PR #16. All three were then
combined on `claude/alfred-development-qpgxhg` ([receipt](evidence/integration-2026-10-02/RECEIPT.md)),
reviewed together in draft PR #18. No branch was reset, force-pushed or merged to main.

## Decision classes

| Class | Items |
|---|---|
| Accepted, already covered by an existing ID | Preserve the implemented console (UX-001); read-only real graph projection (MEM-003, MEM-009, MEM-012, MEM-016, SYS-001); selection, conversation and executive connection (INT-001, INT-002, ATT-001, ACT-001); reasoning as an explicit workstream (INT-001, INT-002). |
| Clarified, new ID | UX-002 project-centred focus and truthful connected states. |
| Accepted, new ID | ATT-002 executive records; RUN-002 distributed operation; RUN-003 isolated bounded jobs; SYS-003 expandable file access. |
| Proposal, new ID | OPS-002 common capability contract for specialist products. A contract is not an adapter. |
| Research candidates | boxd, Space/SpaceFS, pCloud (analogy), JuiceFS, SeaweedFS, rclone VFS, B2, R2, E2B, NVIDIA OpenShell, mesh options. See [the infrastructure research](../research/INFRASTRUCTURE_2026-10-02.md). None is installed or selected. |
| Provisional labels, not adopted | Home, Core, Drive and Forge; the "ALFRED Capability Protocol/Fabric" working name. |
| Not commitments | The generated connected-state image's thumbnails, counts, percentages, timestamps and online claims. |

## Decisions that need the owner

These change spend, vendors, data movement or architecture, so they are not made by the
build. Defaults hold until the owner decides. Detail and options are in section 7.3 of the
infrastructure research.

1. Where the authoritative database and job coordinator live (laptop, always-on home
   computer or VPS). Default: the primary laptop, synthetic data only.
2. Mesh control plane and node key expiry policy. Default: no mesh.
3. Object storage vendor, region and monthly ceiling. Default: no bucket.
4. Which scopes, if any, may leave the primary machine, and in what form. Default: none.
   This does not lift the M02/M05 private-data gates.
5. Paid compute (E2B Cloud, boxd, Modal) or self-host only, and whether forks may hold
   ALFRED material. Default: local subprocess only.
6. Whether to trial Space/SpaceFS. Default: not adopted.
7. VPS provider and jurisdiction. Default: none.
8. Confirm that "OpenShell" means NVIDIA OpenShell. Default: candidate only.
9. Key custody for application encryption before private data (SYS-002).
10. The first real account for a read-only connector test (CON-001).

## Dependency order used for building

The mandate's A to D order was kept. A and B (connected console, selection-aware
questions) are implemented on the branch and browser-tested. C (memory loop and access
lifecycle) and D (executive records) follow because D's records need the same provenance,
authority and invalidation rules that C completes. Infrastructure work runs alongside:
stage 0 of the research recommendation (a local job coordinator with durable job records,
leases, cancellation, retries and reconnectable events) needs no vendor decision, so it
can be built and tested now; stages 1 to 4 wait for the decisions above.

## What this record does not claim

It does not reconcile unsupplied chats, the version 1 amendment, or the generated image.
It gives no whole-product completion percentage. Implemented on a branch is not merged,
and merged is not deployed.
