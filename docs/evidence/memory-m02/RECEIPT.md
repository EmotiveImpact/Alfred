# M02 receipt: identity, grants and their workflows

2 October 2026, branch `claude/alfred-development-qpgxhg`. Status: **in progress**. The
person/device model, strict grants and policy epochs came from PR #17; this increment adds
the workflows around them and fixes how losing access treats reviewed memory.

## M02 acceptance

| Acceptance | State | Evidence |
|---|---|---|
| Credential rotation and explicit person linking do not merge distinct users | Rotation and explicit pairing exist; distinct credentials stay distinct people. Rotation is now an offline command that stages the new key before the database commits and refuses while the host runs. Pairing now works from the console with a single-use code offered by the person themselves, so no one is linked by guessing an identifier. | `tests/test_memory_programme_wip.py`, `tests/test_identity_workflows.py` |
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

## Device pairing (added later on 2 October)

- A signed-in person creates a single-use pairing code (ten minutes) from the Security
  panel, choosing the new device's role: the same as theirs, or reader. A reader can only
  pair reader devices.
- The new device redeems the code from the sign-in screen with a name. The server creates
  that device's **own** credential for the **same person**, with an expiry no later than
  the offering key's, and returns the key once; the console shows it once and asks the
  person to confirm they have kept it before continuing. No key is copied between devices.
- Grants belong to the person, so they apply to the new device; device review histories
  stay separate, as before.
- Redemption is the only unauthenticated identity route. It shares the sign-in failure
  budget (20 refusals a minute), and unknown, used, expired and orphaned codes (the offering
  key revoked or moved to another person) are indistinguishable.
- A person sees only their own active devices and can revoke any of them except the one
  in use. Revocation is journalled first (M05), so restoring an older backup cannot bring
  the device back, and its sessions end at the next request.

**Recovering from a lost device.** If another device of the same person still works,
revoke the lost one from its Security panel. If the only owner device is lost, stop ALFRED
on the host and run `python3 -m alfred.desk rotate --role owner` there: the old owner key
stops working and a new one is printed once.

Evidence: `tests/test_identity_workflows.py` (`PairingTests`, which also reruns the earlier
identity tests) and the pairing section of `tools/check_console_connected_browser.py`
(a second browser context pairs as a reader device, reads with the person's grants, and is
signed out when the owner revokes it). Screenshots:
[pairing](../console-connected/connected-pairing.png),
[device list](../console-connected/connected-devices.png).

## Still missing

Grant administration for more than one owner, team or role policies beyond owner and
reader (OPS-001), shared review histories across one person's devices, and making strict
grants the default for new workspaces. Private data stays gated by M02 and M05.
