# M03: reviewed-memory context bridge

1 October 2026. Draft implementation checkpoint, not a merge or deployment receipt.

## Starting point

Continued M01 draft PR #16 from its tested head `87a2b06041083e02bf1f2c2cb0a55c3963fa102a`. Main remained `8398c7437cb0ef1386d8dc4ff1f9e92fb2557ca2`; no competing memory PR or review changes were found. Console refinement #15 remained separate. The consolidated backend, console and inert source library are preserved. Historical planning/research branches were not used as the implementation base.

## Implemented contract

Questions and conversations now select only relevant, accepted, currently valid, actor-private reviewed statements whose exact indexed support is still available and whose structural conflicts are unresolved neither by recency nor model judgement. Proposed, disputed, withdrawn, superseded, invalidated, expired and future statements are withheld from the reviewed-memory packet. Authored notes remain independent, labelled evidence; withholding a judgement does not erase otherwise-authorised source text.

Selection is deterministic over the persisted IDs and metadata. Up to four statements and 1,600 characters of subject/object names, predicates and values enter context. Their exact original support is allocated first within the existing five-source/6,000-excerpt-character budget, never as an extra evidence budget. Identical supporting slices share a source entry; different spans retain inclusive absolute line numbers. Each statement retains entity IDs, review version/state/time, recorded and valid times, supersession lineage, source hash/revision/span/quote hash and an explicit judgement basis. Review grants no action authority.

Namesakes retain separate entity IDs. Relevant duplicate names are qualified in the packet/UI, and model use is withheld pending clarification. No automatic entity resolver or new entity-disambiguation UI is claimed. Overlapping competing accepted single-valued relationships remain withheld; a late report cannot automatically replace ownership. Explicit, version-bound supersession retains the older record and replacement lineage.

Review/source/temporal/conflict and namesake checks apply immediately before optional model egress and final response return, in the transaction persisting/displaying a conversation, and in separate draft proposal/approval/dispatch decisions. Changed review versions, newly accepted conflicts, expired validity, unavailable/revised sources and newly relevant namesakes invalidate the binding. Saved turns keep source/review bindings rather than duplicating statement values or supporting passages; current values are reconstructed only after checks. User questions and any generated interpretation still follow the existing bounded conversation retention contract.

Historical source-only conversations and plain-list action source bindings remain compatible. The extended `/desk/ask/check` contract optionally accepts memory bindings and namesake qualifications; old source-only callers still work. The existing web Ask/conversation surfaces label accepted memory separately and clear stale results. The React/Three.js fixture console is unchanged.

## Acceptance mapping

| M03 criterion | Deterministic evidence |
|---|---|
| Relevant accepted statements with exact support and review basis | `test_accepted_identity_finds_exact_original_support_without_name_in_note`, `test_review_metadata_and_validity_are_retained`, `test_optional_model_receives_review_basis_and_exact_evidence`, and real HTTP acceptance verify identity-led discovery, exact original lines/hash/revision, review and valid/recorded times, separate judgement/source labels and tool-free request construction. |
| Disputed, expired, invalidated and conflicting statements withheld or qualified | Proposed/disputed/withdrawn/future/expired/source-change/source-loss/revocation cases; pre-egress, mid-response, saved-view and draft proposal/approval/dispatch races. Reacceptance requires a new review version. Authored note evidence is not represented as an accepted memory. |
| Namesakes, late records and changed ownership preserve identities/history | Distinct same-named people/projects, clarification abstention, late historical and overlapping records, and explicit ownership supersession verify separate IDs, retained old records and replacement lineage. |
| Bounded compatible read pipeline | Shared and distinct support spans, mixed memory/keyword five-source limits, deterministic restart, source-only historical turn/action compatibility and unchanged vault bytes. |

## Validation

- 58 M03 cases pass in [local-tests.txt](local-tests.txt), using real temporary Markdown/SQLite, a fixed clock and declared packet-capture fixtures. No model inference or quality claim.
- The complete first-party Python suite passes: 663 tests, including the 605-test M01 checkpoint.
- Backlog consistency/self-tests and byte-exact source-library checks are recorded alongside this receipt.
- `git diff --check` and syntax checks pass.
- [The browser checker](../../../tools/check_memory_context_browser.py) exercises actual loopback HTTP, SQLite and the web UI with invented notes. Unified CI runs it alongside all retained backend browsers and the preserved console build/unit/browser suite.

The exact published commit/tree, combined GitHub CI results and browser counts are recorded on draft PR #16 and Actions after completion. This receipt does not claim a local Chromium pass: the previous local browser download failed, so browser acceptance is delegated to the existing isolated CI workflow. [source-hashes.json](source-hashes.json) identifies the first-party source used for this local checkpoint without a self-referential commit hash.

## Limits and remaining programme

This is current-time retrieval using existing keyword scoring and the ledger's narrow structural conflict rule, not a general semantic conflict detector, calibrated truth score, historical question engine or FTS/vector benchmark. Review acceptance and valid citations do not prove semantic entailment or real-world truth. Model prompt handling treats statements and source text as untrusted data; no prompt-injection immunity claim.

Existing credential/workspace/source checks remain coarse and actor-private. Person/device identity, credential rotation and fine-grained grants are M02. Secure correction/deletion, encryption, backup/tombstone/restore accounting are M05. Indexed snapshots and final transactions do not make a hostile filesystem or endpoint an atomic trusted system. Withdrawn values can remain in the review ledger and permitted historical/audit/backups; stale conversation results are removed from active application rows, not securely erased from storage.

M01 and M03 are implemented on this draft branch, subject to review. M02 and M04-M12 remain planned and issue #11 stays open. No private vault/account access, deployment, host installation, vault writes, third-party runtime adoption, console adapter, main merge or blocked model experiment.
