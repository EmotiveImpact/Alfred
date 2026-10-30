# Encryption step 2, part 4 receipt: jobs, the agent brain, goals, learning and the desk's observations

Built 30 October 2026 on part 3 (aded002ae), which waits for parts 1 and 2 (part 1 is PR #50);
part 4 goes up only after all three. Tested revision: fa555d38e (the commit carrying this receipt
changes only this file). Synthetic keys, an invented vault and invented work only, with the
rule-based SyntheticBrain. Nothing under `third_party/` was read, imported or executed, and no
model ran.

Requirements: SYS-002 (private storage), memory job M05. Plan: integration plan phase 1, step 2,
part 4 of 5. Nothing here lets a workspace in use be sealed; part 5 adds the `seal` command and
unlocking at start.

## What was built

- `alfred/sealing.py`: seventeen tables join the `TABLES` register, and two keyed ids join
  `KEYED_IDS`. Sealed: `events.body`, `desk_documents.filename` and `title`,
  `desk_links.filename` and `title`, `jobs.parameters`, `workers.label`, `artefacts.body`,
  `brain_results.outcome`, `brain_proposals.parameters`, `reason`, `cites`, `provenance` and
  `confirmation`, `brain_suggestions.statement` and `cites`, `verification_runs.report`,
  `hub_mandates.success_test`, `schedule` and `acceptance`, `hub_journal.detail`, and
  `learning_proposals` and `learning_records` `statement`, `detail` and `evidence`. Keyed
  fingerprints: `events.fingerprint`, `desk_documents.sha256`, `desk_links.sha256`,
  `desk_action_evidence.event_fingerprint`, `jobs.fingerprint`, `artefacts.sha256`,
  `brain_tasks.packet_sha256`, `brain_results.envelope_sha256`, `brain_proposals.fingerprint`,
  `verification_runs.report_sha256`, `verification_results.last_run_sha256` and
  `hub_mandates.request_hash`. Keyed ids: `events.subject` and `desk_documents.document_id`.
- `alfred/local.py`: `event_area`, `event_key` and `open_event`. An event's body is sealed whole
  once its sequence number is known, its fingerprint and subject are keyed, and the desk state
  opens it.
- `alfred/desk_store.py`: a document's id, file name, title and file hash are kept sealed or
  keyed; a file name is compared opened (`_at`), and a listed document's own id is read back
  from its event (`_document_view`). Evidence opens the event and its link.
- `alfred/jobs.py`: `job_area` and `artefact_body`. Parameters and worker labels are sealed; a
  job's fingerprint is keyed inside its transaction; a result is stored sealed (as Base64 text)
  under its keyed address, which `jobs.result_artefact`, later jobs' inputs, lineage and job
  events carry. A worker states and is checked against the plain SHA-256 in memory. The job
  cache keeps the sealed record under the keyed address and checks it by opening it
  (`BoundedCache.put(..., address=)`, `get(..., check=)`).
- `alfred/brain.py`: `brain_area` (the job's area) and `task_digest`. Outcomes, proposals,
  suggestions and confirmations are sealed; the packet hash, envelope hash, proposal
  fingerprint and the hash behind a confirmed action's id are keyed. Results, proposals,
  suggestions, drafts, place confirmation and `action_current` open what they read.
- `alfred/verification.py`: a run's report is sealed and its hash keyed; recorded job
  parameters are opened before counting declared checks; result bundles and packets are
  compared through `task_digest`.
- `alfred/hub_goals.py`: `goal_area`. A mandate's success test, schedule and checks are sealed,
  and an update keeps the stored sealed value of each unchanged one; the request hash is keyed;
  a journal entry's detail is sealed under the entry's number, taken before the append-only row
  is written. Every mandate reader, the scheduler and the result view open what they read.
- `alfred/learning.py`: `learning_area`. Statements, details and evidence are sealed on insert
  and acceptance; a harvested learning's key and signature are keyed; the hub journal, brain
  results and every view, packet statement and procedure listing are opened.
- `alfred/recovery.py` opens a mandate's schedule when reporting missed heartbeats;
  `alfred/lifecycle.py` seals the redaction marker when forgetting a source's events, documents
  and links; `alfred/deletion.py` opens them before checking they are redacted.

## Tests

- `tests/test_sealing_work.py` (10 tests), run first against part 3, where nine fail and the
  tenth (reading seals nothing) holds trivially:
  - the desk state, evidence, jobs, results (from the database and the cache), workers, brain
    results, proposals, suggestions, verification runs and acknowledgement, the hub view and
    journal, and learnings all read correctly from sealed values; a rescan of unchanged
    documents, a replayed mandate request and a repeated harvest are recognised;
  - the database, write-ahead log, shared memory and the job cache folder hold none of ten
    invented words (in three cases), nor the plain SHA-256 of any event, document file,
    document id, packet, result, bundle artefact, verification report or mandate request,
    whole or as 16, 24, 32, 40 and 64 character prefixes, and every cached object is a sealed
    record;
  - reading every view seals nothing;
  - a result whose database copy is damaged is served from the cache, and refused
    (`artefact_corrupt`, 500) once the cached copy is damaged too;
  - an event body, a job's parameters or a brain outcome moved to another row does not open;
  - destroying the area refuses every view (`area_destroyed`, 410);
  - with every source in a client area, notes are sealed there and everything in this part,
    with its keyed hashes and addresses, stays in the default area;
  - the register lists the part 4 tables with their fingerprint columns and keyed ids.
- `tests/test_sealing.py`: the register check creates the part 4 tables too.
- Tests that look into storage now read it opened (`tests/stored_helpers.py`), so each
  assertion holds in both modes: `test_brain_plug`, `test_deletion_accounting`, `test_desk`,
  `test_hub_goals`, `test_hub_integrate`, `test_jobs`, `test_provenance_gate`,
  `test_scrub_wiring` (a submitted packet's hash is now the keyed form the record keeps) and
  `test_verification`.
- A scripted plain scenario (two desk documents, one revised; a mandate created, replayed and
  updated; two brain tasks run by a worker with a cache, one proposing a draft; verification run
  and acknowledged; a scheduled task fired; a learning harvested and accepted; the daily
  learning run; every view; then the source forgotten), run with fixed random ids on part 3
  (aded002ae) and on part 4 one after the other, gave byte-identical output: the same views,
  the same rows in all 78 tables before forgetting and all 80 after, and the same cache files.
  Runs made at different times differ only in the inode numbers of the scenario's own folders.
- Whole suite, plain (`python -m unittest discover -s tests`): 1,971 tests, all passing.
- Whole suite, sealed (`python tests/sealed_suite.py`): 1,971 tests, all passing, with
  60,219 values sealed in the process.
- `tools/check_public_hygiene.py`, `tools/check_claims.py --base origin/main --branch
  claude/project-thread-9npowk`, `tools/check_requirement_register.py`,
  `tools/check_memory_plan.py`, `tools/check_adoptions.py` and `tools/egress_audit.py`: all
  pass.

## Not covered yet

- A workspace cannot be switched to sealed outside tests (part 5), which also keys the
  fingerprints a plain workspace already holds. A result's address is copied into jobs, later
  jobs' inputs, lineage, job events, the brain result's envelope hash and the cache's file
  names, so the conversion must key every copy together; job events, the hub journal and
  verification runs are append-only, so it must rewrite them once under that rule's control.
- Areas: everything in this part is in the default area, so a task's packet, result, report
  and the learnings harvested from it are not erased by destroying a client's area even when
  they quote that client's notes. Nothing crosses areas until part 5's folder rules put notes
  outside the default area; this is part of the owner's open choice about answers drawing on
  several areas (`docs/ENCRYPTION.md`).
- Still readable at rest, as metadata: job inputs and lineage (note ids, sources, revisions,
  keyed hashes), job event details (codes, sizes and keyed hashes), the count of values
  scrubbed from each packet, hub tasks, controls, heartbeats, meter readings and attention items
  (codes and numbers), learning keys and signatures that are ALFRED's codes, routine run
  outcomes (counts and ids), and the briefs about public upstream projects copied from the
  public catalogue.
- Identifiers a caller chooses (request, task, idempotency, worker and event ids) are not
  sealed; ALFRED's own ids are random or derived from keyed values.
- The browser check tools under `tools/` read a plain demo workspace's rows directly; they are
  not run sealed.
