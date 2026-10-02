# M02 receipt: identity, grants and their workflows

2 October 2026, branch `claude/alfred-development-qpgxhg`. Status: **in progress**. The
person/device model, strict grants and policy epochs came from PR #17; this increment adds
the workflows around them and fixes how losing access treats reviewed memory.

## M02 acceptance

| Acceptance | State | Evidence |
|---|---|---|
| Credential rotation and explicit person linking do not merge distinct users | Rotation and explicit pairing exist; distinct credentials stay distinct people. Rotation is now an offline command that stages the new key before the database commits and refuses while the host runs. Pairing has no command or interface yet. | `tests/test_memory_programme_wip.py`, `tests/test_identity_workflows.py` |
| Permission filtering happens before ranking, traversal and egress | Holds for the knowledge view, retrieval (keywords and FTS5), the console projection, record inspection, selection focus and job inputs. M06 measured zero leakage on 264 calls per ranking. | `tests/test_console_api.py`, `tests/test_console_focus.py`, `tests/test_jobs.py`, `docs/evidence/memory-m06/RECEIPT.md` |
| Mid-request revocation prevents disallowed persistence or display | Model generation, saved answers, projection assembly (409 on a grant change mid-build) and the browser view (cleared on revocation) are covered. | `tests/test_memory_programme_wip.py`, `tests/test_console_api.py`, connected browser checks |

## Added in this increment

- `GET /desk/identity` lists the caller's person, device, role, access mode and, per source,
  which capabilities are permitted. Readers only see sources they can read.
- Owners enable explicit grants and grant or revoke `read`, `model` and `inbox.write` per
  source over HTTP, bound to the policy epoch, with expiry clamped to the source key's
  lifetime.
- **Invitations:** an owner creates a single-use code (fifteen minutes) for one capability
  on one source. Another person redeems it with their own key and receives exactly that
  grant. No one can be granted by guessing an identifier; the inviter cannot redeem their
  own code; wrong-workspace, used, expired and unknown codes are indistinguishable. Inbox
  writing cannot be shared.
- The console's Security dialog shows this panel. A change made there keeps the panel open;
  other access changes still close every view that could show withdrawn material.
- Losing a grant now withholds reviews instead of destroying them (see the M05 receipt).

## Still missing

A pairing command or interface, key recovery for a lost device, grant administration for
more than one owner, and team or role policies beyond owner and reader. Private data stays
gated by M02 and M05.
