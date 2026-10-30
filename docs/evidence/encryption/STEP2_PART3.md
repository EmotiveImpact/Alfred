# Encryption step 2, part 3 receipt: conversations, executive records, drafts and actions

Built 30 October 2026 on part 2 (b88d2e2db), which waits for part 1 (PR #50) to merge; part 3
goes up only after both. Tested revision: 2caf2bdce (the commit carrying this receipt changes
only this file). Synthetic keys and invented records only. Nothing under `third_party/` was
read, imported or executed, and no model ran.

Requirements: SYS-002 (private storage), memory job M05. Plan: integration plan phase 1, step 2,
part 3 of 5. Nothing here lets a workspace in use be sealed; part 5 adds the `seal` command and
unlocking at start.

## What was built

- `alfred/sealing.py`: ten tables join the `TABLES` register. Sealed: `conversations.title`,
  `conversation_turns.question` and `result`, `conversation_action_sources.references_json`,
  `executive_records.title`, `detail`, `responsible`, `options` and `rationale`,
  `executive_progress.note`, `executive_decisions.option_label` and `rationale`,
  `actions.parameters` and `proof`, `drafts.body` and `draft_sources.binding`. Keyed
  fingerprints: `conversation_turns.request_hash`, `executive_records.request_hash`,
  `actions.fingerprint`, `drafts.digest` and `voice_playbacks.text_sha256`.
- `alfred/local.py`: `action_area`, `seal_action`, `open_action`, `action_fingerprint` and
  `draft_digest` are the one place an action's parameters, proof, approval fingerprint and
  draft digest are sealed or keyed. Proposing, approving, dispatching, the local draft and its
  readback use them; `action_view` opens the row it is given.
- `alfred/conversation.py`: `conversation_area` (the default area). A conversation's title,
  each question, each kept answer and a draft's source binding are sealed when written and
  opened when read; the request hash is keyed, so a replayed question is still recognised.
- `alfred/executive.py`: `record_area` (the default area). Record text and both trails are
  sealed; an update keeps the stored sealed value of every field whose text is unchanged.
- `alfred/drafts.py`: bindings are opened through one helper and sealed again when a draft
  outlives its conversation, since a sealed value is bound to the row it was sealed for;
  withdrawing a draft seals its replacement text; re-proposing seals the new action.
- `alfred/voice.py`: the hash of an answer read aloud is keyed in its answer's area.
- Writers of actions updated: inbox notes, vault appends, desk evidence drafts, routine draft
  offers and knowledge's outbox proofs.
- Readers updated: `routines` (record titles and responsible labels), `hub_goals` (goal titles),
  `brain` (an earlier proposal's parameters), `learning` (a draft's text for sentence counts),
  `verification` (the effect readback, which now compares the keyed digest), `lifecycle` and
  `deletion` (answers, bindings and inbox parameters when forgetting and counting).

## Tests

- `tests/test_sealing_records.py` (10 tests), each run first against part 2 and failing there:
  - conversations, answers, drafts, the draft archive, the action ledger, executive records
    and both trails still read correctly from sealed values; a draft kept after its
    conversation was forgotten still knows its sources; replaying a question, a record request
    and an action is recognised and a changed record request is refused;
  - the database, write-ahead log, shared memory and lifecycle journal hold none of ten invented
    words (in three cases), the question, the answer or the draft, nor the plain SHA-256 of any
    question request, record request, action binding, draft, inbox note or spoken text, whole
    or as 16, 24, 32, 40 and 64 character prefixes;
  - reading every view seals nothing, and an update that leaves text unchanged seals nothing
    while a changed detail seals only that field;
  - a conversation value, an action's parameters or a trail entry moved to another row does not
    open;
  - destroying the area refuses conversations, records and drafts (`area_destroyed`, 410);
  - with every source in a client area, notes are sealed there and everything in this part,
    with its keyed hashes, stays in the default area;
  - the register lists the ten tables, and a lost sealing record is refused when only an
    executive record is sealed.
- `tests/test_sealing.py`: the register check creates the part 3 tables too.
- Tests that look into storage now read it opened (`tests/stored_helpers.py`) or write it the
  way ALFRED does, so each assertion holds in both modes: `test_agent_drafts`,
  `test_brain_plug`, `test_drafts_archive`, `test_evidence_pipeline`, `test_executive_workflows`
  (a version-one record written sealed), `test_local` and `test_verification` (a tampered draft
  sealed like a real one, so the mismatch is still what is refused) and `test_memory_m03`.
- A scripted plain scenario (two conversations with both answer modes, drafts approved,
  forgotten and re-proposed, a direct action, an inbox note carried out, a decision decided,
  reopened and edited, a milestone with progress, a read-aloud record, then every view and an
  export), run with fixed random ids on part 2 (b88d2e2db) and on part 3, gave the same views,
  export and rows in all 54 tables, apart from the inode numbers of the scenario's own
  temporary vault folder and the wall-clock `elapsed_ms` of each answer.
- Whole suite, plain (`python -m unittest discover -s tests`): 1,961 tests, all passing.
- Whole suite, sealed (`python tests/sealed_suite.py`): 1,961 tests, all passing, with
  54,756 values sealed in the process.
- `tools/check_public_hygiene.py`, `tools/check_claims.py --base origin/main --branch
  claude/project-thread-9npowk`, `tools/check_requirement_register.py`,
  `tools/check_memory_plan.py`, `tools/check_adoptions.py` and `tools/egress_audit.py`: all
  pass.

## Not covered yet

- A workspace cannot be switched to sealed outside tests (part 5), which also keys the
  fingerprints a plain workspace already holds.
- Learning, the agent brain's own records, goals and jobs keep their text until part 4.
- The desk's own observations (each event's subject, summary and fingerprint, and the file
  names, titles and hashes of the documents and links the desk lists, with the event
  fingerprint a desk evidence draft keeps) are not in any of the five parts yet.
- Areas: answers, drafts and actions are in the default area even when an answer cites a
  client's notes, so destroying that client's area does not erase them. Nothing crosses areas
  until part 5's folder rules put notes outside the default area; this is part of the owner's
  open choice about answers drawing on several areas (`docs/ENCRYPTION.md`).
- Conversation, question and action request ids are not sealed; the console makes random ids.
- A sealed value is bound to its row but not to its version, so an earlier answer, record text
  or draft text of the same row could be put back by someone able to write the database
  (stated in `docs/ENCRYPTION.md`).
- The browser check tools under `tools/` read a plain demo workspace's rows directly; they are
  not run sealed.
