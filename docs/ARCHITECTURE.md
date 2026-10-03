# ALFRED architecture and current system boundaries

Updated 3 October 2026. Category: operational and executive intelligence. Main `75947b8dd59a3161c862d2533850a032994778e2` integrates the core and authenticated console through PR #18. This document reconciles present boundaries and separates them from [next-stage research](NEXT_STAGE.md). It does not adopt a provider, a native framework or a new runtime. [Earlier architecture](archive/pre-stage-2026-10-03/ARCHITECTURE.md) is retained verbatim.

## One intelligence, not one omnipotent model

The model proposes. ALFRED assembles authorised context. Independent policy authorises. Capabilities execute. Durable records distinguish intent, receipt, supported outcome and acknowledgement. Replaceable voice/reasoning/extraction/retrieval components do not inherit every account credential.

```text
Current local installation
  React/Three.js console + original web client
                     |
        same-origin session/CSRF boundary
                     |
       Python core + SQLite on local disk
        /          |          |         \
 sources/reviews  executive  actions    jobs
        |          |          |         |
 graph/context   routines   approvals  local first-party subprocess
                     |
          current host must remain running
```

## Implemented boundaries

The same loopback server serves `/console/` and its authenticated API. DeskClient reads permitted workspaces, graph projection and original record detail. Meaningful nodes come from existing source, reviewed-memory and executive services; decoration is not data. Authored, reviewed and executive relationship layers remain distinguishable. One workspace per credential is the current implementation, not the final multi-workspace/team model.

Selected-vault identity, bounded reviewed-memory context and capture/review/inbox writing are integrated. Only accepted/current/relevant authorised statements enter context. Retain original support, IDs, review/validity/source bindings and final checks. Saved context reconstructs current values rather than copying permission into a model. Namesakes do not silently merge.

The approved effects remain local: drafts, create-only ALFRED/Inbox notes and bounded report/review/executive/job records. The action ledger owns exact approval and dispatch reconciliation. The job coordinator is separate execution bookkeeping with one authority, leases/events and bounded first-party jobs. Worker output does not grant permission or prove semantic correctness. LocalSubprocessBackend is not an untrusted-code sandbox or second machine.

Pairing, grants, revocation and source-dependent lifecycle checks exist but are incomplete. The audit's approval-projection visibility concern remains to be reproduced. Application encryption and key custody are not implemented. Backup/restore and forget controls do not prove secure erasure of every copy. Export importers are not live accounts; read-aloud is not microphone input; the specialist contract has only a synthetic adapter.

## Storage and authority

Keep user-owned Markdown as a human authoring surface, separate from the action/memory database. Keep original sources and reviewed claims distinguishable. Use the existing authoritative records; any future graph/vector engine is a replaceable projection unless deliberately justified otherwise.

SQLite remains on one host's local disk at a time. File sync is not database/ledger/runtime sync. Keep credentials, databases, durable user files, rebuildable indexes, cache, backups and scratch distinct. A content-addressed cache and a filesystem mount do not enforce grants without ALFRED's policy layer.

PostgreSQL/pgvector remains a later concurrency/deployment option, not a mandatory rewrite. Do not deploy a fleet of services or a graph server to prove the first personal workflow. Measure the workload and failure model first.

## Proposed later topology: research, not an active deployment

```text
          optional always-on ALFRED coordinator
          approved home host OR approved cloud host
                  /          |          \
        desktop client   other client   enrolled workers
             |
       local node capabilities and local-only files

  optional object/file tier behind a bounded authorised cache
  optional isolated persistent/disposable execution backends
```

The later conversation favours continuity when a laptop sleeps. The authority host, data location, keys, remote authentication, provider/region and spend are still decisions. One active authority per job does not imply all personal data must move to a public-cloud server. Define local-only data and unavailable capabilities explicitly. No writable SQLite file sync or silent multi-master arrangement.

A Tauri/Rust shell retaining the React console and Python services is a proposal to compare with alternatives. Use native code only where justified by OS/security/performance needs; no wholesale rewrite. Test WebGL, sidecar lifecycle, IPC, key storage, signing and updates on actual targets before adoption. Desktop packaging and hosted operation are independent; neither supplies the other's safety controls.

Design a remote transport with an explicit threat model and revocation path; do not expose the current development listener by weakening checks. Separate local test prototypes from deployed remote clients. The user's devices, accounts, private information and microphone remain unavailable until specifically authorised.

## Candidate components

The earlier source catalogue and infrastructure report remain research. Graphiti/Cognee/Mem0/Basic Memory, Hermes/nanobot/QwenPaw, LiveKit/Pipecat, Jev, OpenSandbox, OpenFGA/OPA and Nango are not adopted by mention. OpenSandbox and NVIDIA OpenShell are distinct candidates. boxd/E2B/OpenShell, Space/SpaceFS, storage and mesh providers are evaluated behind replaceable interfaces, not made the job or memory authority.

Inspect exact pinned code/licences, editions, data egress and failure/deletion behaviour before adoption. The source library remains inert. Self-hosted is not automatically open source; a code licence does not clear a model, dataset or hosted service.

## Actions, routines and outcomes

Bind exact parameters, actor/workspace, expiry and source conditions to approval; recheck before dispatch. Do not replay uncertain irreversible effects blindly. Cancellation, rollback and snapshot restore are not undo of an external effect.

Pulse and authored routines use stated kinds, schedules/budgets and independent authority. Retrieved procedure text remains inert. Fixed-offset time handling, authoring across paired devices and other remaining workflow questions need explicit decisions/tests. No installed always-on service is established by routine scheduling code.

Voice shares context and permissions; capture, retention and upload are distinct decisions. Specialist products remain independent, with observation, report, simulation, analysis, result and acknowledgement separately labelled. No autonomous use-of-force control.

## Observability, testing and promotion

Inspect evidence age, source health, queues, retries, context size, resources and outcomes without retaining secrets or default raw transcripts. Preserve pause/revoke/export/forget. Measure correctness separately from responsiveness; the existing literal support report is not a semantic verifier.

Read [SECURITY_AND_DATA.md](SECURITY_AND_DATA.md), [AUDIT_2026-10-03.md](AUDIT_2026-10-03.md) and [NEXT_STAGE.md](NEXT_STAGE.md). The current task may build Track A and prepare opt-in synthetic Track B groundwork. Private pilot, hosted infrastructure, partner outreach and commercial/owned capacity require their gates; a green CI run never activates them automatically. The restricted live-model comparison remains unexecuted and must not be rerouted.
