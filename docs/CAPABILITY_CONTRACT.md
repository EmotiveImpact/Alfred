# Capability contract for independent specialist products (OPS-002)

**Status:** proposal. Contract version 1 is implemented on the integration branch in
[`alfred/capabilities.py`](../alfred/capabilities.py) with a synthetic simulation adapter and
contract tests ([`tests/test_capability_contract.py`](../tests/test_capability_contract.py)).
The owner has not yet accepted the contract, and **no real product adapter exists.**

## Why it exists

ENDSTATE, 8BALL, Noir/Black State, Loc8 and God's Eye stay independent products with their
own owners, data and release cycles. ALFRED does not absorb them, copy their logic or speak
for them. When a product's owner provides its real interface, an adapter can feed that
product's observations into ALFRED's existing evidence pipeline under one common contract,
read-only first.

None of those interfaces was available to this build. Nothing here imitates, names or
models any of them. The only adapter is a clearly fictional exercise feed that exists to
prove the rules below.

## Manifest

An adapter declares one manifest. `validate_manifest` rejects any other shape.

| Field | Rule |
|---|---|
| `contract_version` | Must be `1`. |
| `product` | `id`, `name`, `owner` and `independent`, which must be `true`. |
| `mode` | `live`, `replay` or `simulation`. |
| `identity` | `record_id_scheme` described in words, and `stable: true`. Record IDs must not change between reads. |
| `freshness_seconds` | 60 to 604800. Becomes the expiry of every event the adapter produces. |
| `capabilities` | 1 to 32 unique items, each `id`, `kind`, `description`, `effect`, `approval`. |

A `read` capability must declare `effect: none` and `approval: not_required`. An `action`
capability must declare `effect: external` and `approval: exact_approval_required`; an
adapter cannot describe an effect as harmless to avoid approval.

## Observations

Every item an adapter returns is validated on its own, so one bad item is rejected without
losing the rest.

| Field | Rule |
|---|---|
| `record_id` | Stable identifier from the product. |
| `kind` | `status`, `alert`, `report` or `assessment`. |
| `observed_at` | The product's original time. A future time is rejected. ALFRED records its own receipt time separately and never overwrites the original. |
| `basis` | `observed`, `reported`, `derived` or `simulated`. |
| `health` | `ok`, `degraded` or `unknown`. |
| `summary`, `evidence` | Bounded text and up to eight evidence references. |

The rules that keep AGENTS.md's distinctions:

- **Simulation and replay are never observations.** In `replay` or `simulation` mode every
  item must have basis `simulated`; anything else is rejected as
  `simulation_mislabelled_as_observation`. A `live` adapter cannot emit `simulated` items.
- **An assessment is analysis, not observation.** An `assessment` must have basis `derived`
  or `simulated`.
- **Simulated data stays in simulation workspaces.** The bridge uses the existing
  `LocalCore.ingest`, which refuses simulated events in a workspace that is not marked as a
  simulation (`simulation_not_live`).
- **Freshness, ordering and duplicates use the existing rules.** A stale item is recorded as
  `expired`, not current; a repeated item is idempotent (`duplicate`).
- Every event summary carries a visible label with the product name, mode, kind, basis and
  health, so a reader can tell a scripted exercise from a live report at a glance.

## Binding and authority

- `SpecialistBridge` writes only through the product's own source credential, which must be
  named `specialist-<product id>`. One adapter cannot write as another product or as the
  owner (`adapter_credential_mismatch`).
- Reads happen through `sync()`, which reads once, validates every item and ingests the valid
  ones, returning a per-item outcome and keeping simple health counters.
- **Actions are declared, never enabled.** `capabilities()` reports every action as
  `declared_not_enabled`, and `invoke()` always refuses (`action_not_enabled`). Enabling an
  effect would need ACT-001's exact approval binding to the action's parameters and source
  conditions, capability-specific reconciliation of uncertain effects, and the owner's
  decision for that product.
- A manifest, an observation or a product's description of itself never grants permission.

## Adding a real adapter later

1. The product's owner provides the actual interface and its terms. Read it before writing
   anything; do not infer an interface from a name.
2. Build a read-only adapter that maps the product's records to the observation fields above,
   with provenance for every field and an honest `mode`.
3. Provision a `specialist-<product id>` source credential in the workspace that should
   receive the feed, and run the contract tests against recorded, synthetic or owner-approved
   samples.
4. Record the source, licence, data-egress and containment evidence that AGENTS.md requires
   before deliberate adoption.
5. Leave actions declared but disabled until ACT-001 binding and the owner's approval exist.

## Not built

- No real product adapter, and no claim that any product's interface is understood.
- No HTTP route or console view to register adapters or browse specialist feeds; bridges are
  constructed in code by the host, and accepted events appear in the existing evidence view.
- No scheduling of `sync()`; nothing polls a product.
- No action execution of any kind.
- Role-limited team and operational workspaces (OPS-001) are not started.
