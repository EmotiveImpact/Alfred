# Validation record

25 September 2026. The original prototype was run locally with Python 3.13.5.

```sh
python3 -m unittest discover -s tests -v
python3 -m alfred.demo
```

Result: **60 unit tests passed**: 26 attention/evidence tests, 22 action-contract tests
and 12 source-import helper tests. No external dependencies were installed. The demo
ran and printed explicitly synthetic routing and action-state transitions.

## What the checks establish

Attention: explicit registered source/kind/basis, matching test scope/source, expiry,
future and out-of-order events, duplicate versus conflicting IDs, equal-time reconciliation,
simulation/analysis separation, bounded state, basic validation and deterministic routing.

Actions: immutable proposal identity, exact approval hash, actor matching in the trusted
harness, expiry/policy recheck, allowed state transitions, receipt distinct from verification,
unknown outcome, cancellation not undo, scoped lookup, bounded storage and JSON validation.

Import helpers: safe archive paths, retained exact bytes, licence-hash checking, duplicate
path rejection, links not followed, sensitive-path filtering and non-execution of copied
fixture scripts. The selected-source network worker has additional boundedness/validation
but its real network behaviour is evidenced by its Actions logs, not these 12 unit tests.

## What these checks do NOT establish

No real user/device authentication, authorisation server, encryption, tenant isolation,
durable event store/outbox, crash recovery, live model, semantic relevance quality,
voice/audio capture, browser UI, cloud deployment, real connector or physical result
verification is implemented. No upstream application is run or benchmarked.

The test called external_instruction_is_only_data is a deterministic parser/routing check,
not proof against prompt injection into an LLM. Scope checks use trusted test arguments;
they are not a security perimeter. The verified action state is reached with a fixture
signal; the prototype does not independently inspect any external service or device.
In-memory stores have bounded capacity and reject when full; they do not provide production
retention/eviction or recovery semantics. JSON/provenance validation is deliberately small
and still needs adversarial and transport-level hardening before exposure.

## Source import evidence

The import workflow downloads pinned public source as data, retains licences/notices,
commits copied files to the research branch and verifies file-set and byte hashes. The
receipt records current failures and previous failures rather than hiding retries.

Initial archive attempt copied three snapshots; two large archives exceeded the 64 MiB
download cap. Focused imports then encountered HTTP 429 and a binary illustration whose
name matched a legal-notice filter. The importer was changed to throttle/retry according
to server response, exclude binary illustration suffixes and use bounded selections.
The actual final result must be read from third_party/IMPORT_RECEIPT.json and Actions;
this history is not itself a claim that all retries succeeded.

Hash verification proves correspondence to retained bytes/pins, not absence of malicious
code, full commercial clearance or completeness of a repository. Source manifests are
not a deployed dependency SBOM.

## CI scope

The ALFRED contract-check workflow runs only ALFRED-owned tests and the synthetic demo,
then verifies staged source bytes. It does not load upstream tests, workflows, packages
or skills. A published workflow is not evidence of green CI: inspect the actual run for
the current commit. Hosted runner Python may differ from the local 3.13.5 environment.

## Next validation gate

Authenticate real local clients, persist the ledger/outbox, exercise crash/retry paths,
then run one isolated runtime and one read-only connector on synthetic/test-account data.
Publish negative tests and failed cases. Voice latency, battery, safety and real-world
usefulness require their own experiments, not inference from this unit-test count.
