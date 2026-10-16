# Drafts are kept: lapse, archive, find and propose again

Branch `feat/drafts-archive-2026-10-16`, started from `main` at `75947b8dd`. Tested revision:
the working tree committed as the branch head (see the commit that adds this receipt). Synthetic
data only. Nothing is sent; the only effects remain local drafts and create-only inbox notes.

## Owner decision

16 October 2026, verbatim: "i dont like the idea of drafts going after 15mins... they should exist
or be archived and i should be able to find them again". This answers decision 0.3's "re-offering
expired drafts" question: drafts are kept and can be re-offered by the owner.

## What was built

- `alfred/drafts.py` (new). A draft (`message.draft` or `vault.inbox_note`) is never deleted or
  hidden. Its approval window still lapses after 15 minutes and an old approval still cannot
  dispatch. The draft keeps a visible status: `awaiting_approval`, `lapsed`, `archived`,
  `withdrawn`, or its ledger state (`queued`, `verified`, `cancelled`, and so on).
- Search over the owner's own drafts by text, status, date (`since`/`until`, epoch seconds or
  `YYYY-MM-DD`) and archive filter (`exclude` by default, `include`, `only`). Actor-private and
  owner only, like the existing action ledger.
- Reopen returns the full draft and whether re-proposing would pass right now, worked out by
  running the real re-propose inside a rolled-back savepoint.
- Archive and unarchive, version-checked (`draft_changed` on a stale version) and written to the
  audit log (`draft.archived`, `draft.unarchived`). Archiving a draft still awaiting approval
  closes its window at once; unarchiving never reopens it.
- Re-propose makes a new action with its own id and a fresh fingerprint over the current exact
  parameters (optionally edited text for `message.draft`). It re-binds the original source
  condition (desk evidence event, conversation sources and reviewed statement versions, routine
  commitment version, or the inbox grant and vault preconditions) and calls the store's own
  `evidence_valid` in the same transaction. If anything changed it fails with
  `evidence_not_current` and leaves nothing behind. Audited as `action.reproposed_from_draft`.
- Conversation drafts outlive the conversation's 24-hour retention: before a conversation row is
  removed (retention or forgetting the conversation) its value-free source binding is copied to
  `draft_sources`. A re-proposed conversation draft is checked by `reproposal_current` (same
  checks as `knowledge_action_current`, without the conversation itself).
- Forgetting is not bypassed. `forget_source_db` and `withdraw_dependants` (claim and entity
  forget, and restore replay) now also find drafts through the kept bindings, cancel undecided
  ones, replace their text with "Removed when its source was forgotten.", mark them `withdrawn`
  and refuse to re-propose them. Receipts gain `drafts_withdrawn`. Executing, uncertain and
  verified drafts are left as before (completed drafts are not undone).
- HTTP: `GET /desk/drafts`, `GET /desk/drafts/<id>`, `POST /desk/drafts/<id>/archive`,
  `/unarchive`, `/repropose`, inside the existing guarded handler (loopback Host, Origin, session
  cookie, CSRF on every POST).
- Console projection approvals carry `draftStatus`. The console no longer shows a lapsed,
  archived or withdrawn draft as waiting for approval, and the Approvals section has a "Find
  drafts, including lapsed and archived" panel (filter Current, Lapsed, Archived, All; text
  search; Propose again, Archive, Unarchive). Owner sessions only.

Shared modules touched, small and additive: `alfred/conversation.py` (two hooks),
`alfred/knowledge.py` (one extra condition), `alfred/lifecycle.py` (withdrawal hooks),
`alfred/desk_http.py` (one route), `alfred/console_api.py` (one field).

## Tests

- `tests/test_drafts_archive.py`: 20 tests (desk evidence, conversation, routine and HTTP).
- `python3 -m unittest discover -s tests`: 1,133 tests, OK (264 s).
- `cd console && npm ci && npm run build && npm test`: build clean, 147 unit tests pass
  (adds `console/tests/drafts.test.ts`).
- `tools/check_console_connected_browser.py` (Chromium 141, swiftshader): 103 checks passed, no
  page errors. New checks: a lapsed draft leaves Approvals, is found under Lapsed, is proposed
  again as a new action with a fresh approval, and an archived draft is listed under Archived.
- `tools/check_conversation_browser.py` and `tools/check_desk_browser.py` (33 checks): pass,
  no uncaught errors. Screenshots went to a scratch folder, not into this repository.

## Limits

- Drafts are kept until the source is forgotten; there is no owner "delete draft" action yet,
  and no automatic archiving. The 5000-actions-per-scope capacity still applies.
- A desk evidence draft cannot be re-proposed after its evidence event expires or is
  superseded; it stays listed and `reopen` says why.
- The value-free conversation binding (note ids, revisions, hashes, statement versions) is now
  kept beyond the conversation's 24-hour retention, for as long as the draft exists.
- Withdrawal replaces the text in current records only. It is not secure erasure: WAL, free
  pages and older backups keep earlier bytes until checkpoint, vacuum or rotation, as stated in
  the lifecycle receipts.
- The original web interface (`web/`) still lists actions from `desk_state` without the new
  status; only the console has the finder.
- The browser check simulates the fifteen minutes passing by moving the action's `expires`
  column in the test database.
