# Strict grants by default: receipt (plan item 1.2; SYS-001, MEM-009, M02)

Branch `feat/strict-grants-2026-10-16`, started from `main` at `75947b8dd59a3161c862d2533850a032994778e2`.
Tested revision: `492bf617a` (the implementation commit). This receipt is added in the following commit and changes no code.

Synthetic data only. Nothing under `third_party/` was imported, installed or executed. Loopback, Host/Origin and CSRF checks are unchanged.

## What was missing before this work

Identity already had persons and devices, single-use invitations, device pairing, offline rotation and owner grants (M02). Against plan item 1.2 the gaps were:

- New workspaces started in the whole-workspace (legacy) mode: every owner and reader key read every source until the owner pressed "Use explicit grants".
- An owner could grant only their own person. Another person could be granted only by redeeming an invitation, there was no list of people, and no way to switch a source off for someone else.
- A new person needed an offline `provision` command; there was no enrolment over HTTP.
- The review ledger was keyed by device credential, so a paired device showed an empty review history (`device_reviews_shared: false`).

## What was built

- **Strict by default** (`alfred/policy.py`). A workspace with no policy record is strict. A one-time upgrade (`identity_meta`) records every workspace that existed before this version as legacy, explicitly, so an existing private database does not silently lose or change access. Workspaces created afterwards, including new ones in an upgraded database, are strict. New credentials, owner keys included, receive no grants.
- **Demo init** (`alfred/desk.py`) grants its owner `read` and `model` on `demo-source` through the ordinary owner grant path (epoch-checked and audited). The demo reader key holds nothing.
- **Enrolment over HTTP.** `POST /desk/identity/enrolments {label, epoch}` (owner only) returns a single-use, 15-minute code. The new device redeems it on the existing pre-session route `POST /desk/identity/pairing/redeem`, which shares the sign-in failure budget and the indistinguishable `pairing_not_valid` refusal. It receives its own reader key as a new person with no grants. More than one owner person per workspace is still not supported.
- **People and per-source grants over HTTP.** `GET /desk/identity/people` (owner only) lists every person holding an active key, labelled by the owner's enrolment label (never by device names), with roles, device count and current grants. `POST /desk/identity/people/<person>/grants {source, capability, days, epoch, revoke}` grants or revokes one capability on one source. Another person may hold `read` and `model` only; vault writing and imports stay with the owner. A person ID that holds no active key in this workspace is `404 person_not_available`.
- **Version-checked and journalled.** Every change checks and bumps the workspace policy epoch (`409 policy_changed` on a stale view). Every grant, revocation, enrolment offer and enrolment is in the audit log; every revocation is written to the lifecycle journal first, so a restore cannot bring it back (tested).
- **Review history per person** (`alfred/reviewed_memory.py`, `memory_history.py`, `lifecycle.py` and the readers in `routines.py`, `executive.py`, `export.py`, `conversation.py`). Entities, statements, statement history and lifecycle receipts are keyed by the person, so every device of one person shows the same history. Each review still records the device credential that made it; history shows `you`, `you_on_another_device`, `alfred` or `another_credential`. Rows written per credential migrate once, idempotently; journal replay into an older backup matches either key; the audit-based history migration searches every device credential of the person. Offline explicit pairing (`pair`) refuses to fold a person who already has a review history, as it already refused one with grants.
- **Console** (`console/src/components/AccessPanel.tsx`, `console/src/integration/people.ts`). For an owner the access panel adds a People section: each other person with Read and Model switches per source, and an enrolment code. The server decides every change.
- `desk_http` now refuses a reader's grant or invitation request with `403 forbidden` before looking at sources.

## Tests

| Check | Result |
|---|---|
| `python3 -m unittest discover -s tests` | 1,124 tests, OK (186.6 s) |
| `tests/test_policy_strict.py` (new) | 11 tests, OK |
| `cd console && npm ci && npm run build && npm test` | build OK; 14 files, 146 tests passed (3 new in `tests/people.test.ts`) |
| `tools/check_console_connected_browser.py` | 104 checks passed, no page errors ([report](browser/browser-report.json), [people panel](browser/connected-people.png)) |
| `check_executive_browser`, `check_temporal_review_browser`, `check_routines_browser` | 45, 50, 52 passed |
| `check_desk_browser`, `check_knowledge_browser`, `check_os_browser`, `check_conversation_browser`, `check_memory_browser`, `check_memory_context_browser`, `check_voice_browser`, `check_sync_conflict_browser` | all passed (33, 25, os, conversation, memory, M03, 12, 5) |
| `check_grounded_browser` | all 23 checks passed; the script then stopped at its optional WebP thumbnail step because Pillow is not installed in `/tmp/alfred-browser` (environment, not this change) |

Acceptance from the plan, where it is tested:

- A new reader sees nothing until granted: `DefaultPolicyTests.test_a_new_reader_sees_nothing_until_granted_and_the_owner_grant_is_not_shared`, `StrictHTTPTests.test_enrol_list_grant_and_revoke_a_person_over_http`, and the browser check (a newly enrolled person sees `0 records`, then records after the owner's switch, then `0 records` again).
- Losing a grant withholds mid-request: `StrictHTTPTests.test_losing_a_grant_withholds_mid_request` (the model grant is revoked while the model is working, and the read grant after retrieval; both end in `sources_changed_during_question`).
- Pairing a device shows the same review history: `StrictHTTPTests.test_pairing_a_device_shows_the_same_review_history`.

Fixtures that relied on implicit whole-workspace reads now grant explicitly through `tests/grant_helpers.py`, which calls the real owner-only, epoch-checked `IdentityPolicy.grant`. No fixture marks a workspace legacy, except the two tests of the legacy upgrade path, which reproduce a pre-upgrade database. Tests that used `enable` to mean "strict with nothing granted" now revoke explicitly. `tools/evaluate_retrieval.py` keeps its positive control by granting both sources explicitly and then revoking the restricted one; its tests pass unchanged.

## Limits

- One owner person per workspace. Enrolment creates readers only; multi-owner identity is gate 4.
- Person labels are owner-chosen text, not verified identity. Nothing links people by name.
- Grants still last at most 30 days and never outlive the source key. Expired demo keys need a new `init` or offline rotation.
- Legacy workspaces keep whole-workspace reads until their owner enables grants; that switch is still one-way and explicit.
- Two devices explicitly paired offline before this version, each with a statement of the same request ID, keep the colliding row under its credential (it is not shown). No such pairing exists in any fixture.
- No encryption, deletion accounting or restore reporting was added here (items 1.1 and 1.3).
- The console change was checked at the default desktop size in the connected browser check, not on a physical device.
