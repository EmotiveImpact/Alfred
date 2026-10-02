# M04 receipt: explicit capture and approved inbox writes

2 October 2026, branch `claude/alfred-development-qpgxhg`. Status: **implemented on the
integration branch** against synthetic vaults. Not merged, not deployed. Private use is still
gated by M02 and M05.

## Acceptance

| M04 acceptance | Evidence |
|---|---|
| Remember-this previews editable scope, memory type, source and retention | `ReviewedMemory.capture` returns a preview (workspace, statement, memory type, retention date, exact source lines and quote) and leaves the statement `proposed` and unusable. The console form edits record, statement, value, lines, type and retention before capture; acceptance is a separate click. [Screenshot](connected-remember.png). |
| Exact path, content and precondition approval is separate from reading or recalling | `alfred/inbox.py` proposes a `vault.inbox_note` action bound by fingerprint to source, vault ID, exact path under `ALFRED/Inbox/`, exact text and its hash, and a create-only precondition. It needs an explicit `inbox.write` grant; the legacy scope policy and a read grant alone never allow it. Approval uses the existing route and fingerprint. |
| Concurrent changes, restart and duplicate requests never silently overwrite human notes | Writes go to a hidden temporary file, then `link()` creates the destination atomically and fails if anything exists. A human file created after approval fails the action (`destination_exists`) and is left byte-identical. A crash after writing leaves the action uncertain; reconcile reads the bytes back and verifies the hash. Same request ID and content is idempotent; changed content collides. |

Also tested: revoking the write grant after approval blocks dispatch; a symlinked `ALFRED`
folder is never followed; a replaced vault root is refused; a paused workspace writes nothing;
unsafe names are rejected; readers cannot propose; retention chosen at capture forgets the
statement through the M05 journal with a receipt.

## Commands and results

- `python3 -m unittest tests.test_memory_capture_inbox`: 18 tests pass.
- Full suite: 731 tests pass at this commit.
- `tools/check_console_connected_browser.py`: 54 checks pass, including ask, remember, preview,
  accept, propose an inbox note, approve the exact file, the file appearing in the vault only
  after approval, and the new note being indexed and read back.

## Limits

One destination folder, create-only. No edits to existing notes, no deletions in the vault, no
sync. Memory types are recorded and shown; type-specific policies (for example, commitments
feeding attention) are M10. Under strict grants only the owner's own person holds grants;
another person sees nothing until a grant workflow for them exists (M02).
