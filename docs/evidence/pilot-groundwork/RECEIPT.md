# PILOT-GROUNDWORK delivery receipt

3 October 2026. Review branch: `feat/alfred-pilot-groundwork-2026-10-03`.
Code/research checkpoint: `b83acd62bd5260f541f5249fc65fac016dda02bc`.
The documentation/evidence commit follows it; resolve branch HEAD for that
commit. [SESSION_HANDOFF](../../../SESSION_HANDOFF.md) is the resumption point.

## Repository and delivery state

Main was re-fetched before publication:
`75947b8dd59a3161c862d2533850a032994778e2`, the already merged PR #18.
PR #19 remained **open/unmerged**, with handoff head
`3fe9d25c87058499887ce4b0d8c90ccecc6954e9`. Its changes were loaded by a
fast-forward into the review branch. All historical integration ancestors are
retained; PR #18 integration was not repeated. No reset or force-push occurred,
and the latest fetch found no newer main/handoff work.

| State | Actual result |
|---|---|
| Implementation | Track A bounded product changes; Track B recommendations and opt-in synthetic contracts committed. |
| Integration | Existing Python/SQLite, original web UI and authenticated same-origin console exercised together. No native shell, remote/isolated provider worker or cloud-file connection. |
| Local testing | Combined suites and 14 real browser workflows pass; exact revisions/hashes below. |
| Publication | Review branch pushed normally. [Compare with main](https://github.com/EmotiveImpact/Alfred/compare/main...feat/alfred-pilot-groundwork-2026-10-03). |
| Pull request | Draft creation failed: GitHub GraphQL returned `Forbidden`. Git push works; no new PR exists. This is API-access failure, not automatic approval-review rejection. |
| Hosted CI | Unified [run 37102086932](https://github.com/EmotiveImpact/Alfred/actions/runs/37102086932), revision `b83acd62b`: **Success, all four jobs passed**, 8m 41s. Public-summary readback in [hosted-ci.json](hosted-ci.json); authenticated logs were not read. Future documentation-head runs need their own check. |
| Owner acceptance / merge / deployment | No new owner acceptance inferred; stage branch unmerged; no deployment or installed service. |

The whole 33-requirement PRD remains scope. Prior implementation/decision
classifications are retained; 15 affected rows record an unmerged extension
and preserve their prior main delivery. No whole-product completion percentage
or later-stage activation is claimed.

## Track A

- [A1](A1.md): three negative HTTP reproductions confirmed approval text,
  destination, fingerprint and count disclosure across people/restricted reads.
  Common credential-private, source-readable visibility protects listings,
  details and audit, filtering before pagination. Positive owner reads and
  independent approval/dispatch authority remain.
- [A2](A2.md): normal provisioning requires explicit source grants. Existing
  legacy credentials/sources are captured once with bounded expiry; stopped-host
  migration can explicitly preserve recorded reads or deny. No implicit model,
  write or sync grants. Actual CLI tests cover both choices, idempotence and
  a running-host lock. Demonstration access is deliberately granted.
- [A3](A3.md): durable privacy/strict-policy/export intents replay at startup and
  older-backup restore; torn journals fail closed. Cancelled dependent drafts
  are redacted. Export publication rechecks authority/revisions; copy accounting
  survives backups taken before export and records uncertain/retained readable
  copies. Real SIGKILL tests distinguish one safe retry from unknown effects.
  The systemd example was syntax-checked, not installed.
- [A4](A4.md): measured lexical coverage/score floors reduce irrelevant context
  and weak links, with whole-read grant rechecks. Frozen precision rises
  24.34% → 54.22%, at mean recall 92.29% → 89.58% (one support lost).
  The separate small same-author held-out fixture retains 14/14 supports with
  precision 60.87%. These are source-selection results, not reasoning quality.
  The 15-check synthetic console loop covers select/ask/inspect, propose/accept/
  correct, recall, forget current/superseded values, reopen and older-backup
  restore. It also reproduced/fixed stale superseded-value inspector text.

Broad-browser failures were retained and resolved: a summarise operation word
wrongly raised relevance requirements for accumulated follow-ups; a vague
unfocused query now explicitly checks abstention with a named positive query
alongside it. Demo model grants are explicitly revoked before the UI grant
test. Default-deny/invitation acceptance uses a fresh ungranted person.
Read-aloud still asserts spoken text exactly equals displayed text. See
[retained initial results](failures/initial-results.json) and failure logs;
no failed run is relabelled a pass. Premium console rendering/design is unchanged.

## Track B

[Platform recommendations](../../../research/PILOT_PLATFORM_2026-10-03.md)
preserve Python/React and recommend Tauri as the first target-device packaging
evaluation, with Electron as a rendering fallback. One authoritative Core with
explicitly enrolled bounded worker identities is the proposed topology. The
package distinguishes laptop/home/VPS custody and availability, transport,
leases, persistent computers, isolation, file/catalogue/cache/backups and
commercial ownership/licensing choices. The
[custody proposal](../../KEY_CUSTODY_PILOT.md) is ready for an owner decision;
no crypto dependency was adopted.

Official sources are pinned/hashed in the
[primary-source receipt](../../../research/pilot-primary-sources-2026-10-03.json).
Current boxd docs explicitly preserve processes and logins across live forks;
clean images, credential stripping, fresh enrolment and fencing need separate
acceptance. Boxd idle RAM/disk billing/automatic top-ups, E2B tier/session limits,
pCloud terms/offline properties and Nebius's **effective 1 October** GPU rates
inform the recommendations. R2 list prices/current provider references are
separate from illustrative whole-stack workload/staff/tax/FX assumptions in the
[executable cost output](../../../research/pilot-costs-2026-10-03.json).
No quote, credit eligibility, spend approval or partnership is established.

The opt-in [file model](../../../prototypes/README.md) passes six local synthetic
contracts for authority on hits/fetches, pins/capacity, revision conflicts,
stale offline copies and deletion lineage. Four node tests exercise actual
SQLite contention, stale attempts, cancel/disconnect and worker-ID rejection on
one host. Neither establishes distributed security, VM isolation or provider
acceptance. Candidate source was read as data, not installed or executed;
archives remain byte-exact and inert.

## Exact local validation

[validation.json](validation.json) records Git-tree identity, script/artifact
hashes and per-browser revisions/commands. The full
[backend log](validation/backend-tests.txt) is retained.

| Check | Observed result | Revision / limit |
|---|---|---|
| Backend discovery | 1,157 passed, 131.789 s | `284bf87b0c915526745f98e2cb3c0744f123e044`; `alfred/`, `tests/`, `web/` trees identical at `b83acd62b`. |
| Console typecheck/build, standalone | Passed | `330201abe`; console tree identical at the code checkpoint. Existing bundle-size warning remains. |
| Console unit / Playwright | 143 in 13 files / 29 passed | Same unchanged console tree; logs retained. |
| Python browser acceptance | 14 workflows, 474 assertions passed | Twelve at `284bf87b0`; voice at `1cadb272b`; corrected connected fixture tested before `b83acd62b` with its exact committed SHA. Identical runtime/console. |
| Source preservation | 21 self-tests; all three verifiers passed; 11 ancestors retained | No upstream execution or new snapshot adoption. |
| Planning/register | 12 / 11 self-tests passed; final consistency reports in `validation/` | Internal consistency, not capability proof. |
| Current cost arithmetic | Four passed | Current calculator source; dated reference rates are not selected services. |
| Additional contracts | Six file, four node, two actual CLI tests; service syntax passed | File/node/CLI included in backend suite; no running service. |

Builder: Python 3.12.14; Node 24.19.0/npm 11.9.0 during console checks;
configured install npm 11.20.0; Playwright 1.57.0/Pillow 11.3.0;
Chromium 151.0.7922.173, software rendering. Hosted CI declares Node 22/npm
11.20.0. No physical-device, native, real sync-client, microphone/audio-hardware,
live-model or provider acceptance follows. Deliberate permission/server-loss
cases produce expected HTTP errors; final reports have zero uncaught page errors.

Use the existing unified workflow for reproducible commands. In this cloud
builder runtime must stay outside Git/sync/vault paths (prepared
`TMPDIR=/var/tmp/alfred-cloud`); browser output overrides preserve older evidence.
Do not execute the restricted real-model workflow for this stage.

## Resumption and remaining decisions

Next: refresh main/PR #19/review refs, preserve newer work and review the full
branch diff. With restored GitHub API access, create a **draft** main PR using
[PR_BODY.md](PR_BODY.md), attach it to the task and inspect exact-head unified CI.
Creating/reviewing a PR does not authorise merging.

Before later private/native/remote work, record target OS/Core location,
key custody/recovery/server-readable scopes, worker identity/transport/isolation,
file tier/region/offline expiry and a budget ceiling. Native toolchain/hardware
and remaining inaccessible primary sources are explicit limits. Storage is
unencrypted; external copies/media, shared-team privacy and production-scale
retrieval remain incomplete. No purchase, outreach, provisioning, public
deployment, private-data movement, real account/device connection, microphone
capture or main merge occurred. No work continues after this task ends.
