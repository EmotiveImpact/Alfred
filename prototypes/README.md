# Opt-in PILOT-GROUNDWORK contracts

These first-party synthetic prototypes are outside the default ALFRED runtime.
No provider SDK, native shell, FUSE mount, network service or crypto dependency
was adopted. Candidate code under `third_party/` is not imported or executed.

The [file-tier model](pilot_file_tier.py) asks whether the existing bounded cache
can express on-demand/pinned reads without making a cached copy a permission,
and whether revision conflicts/tombstones remain explicit. Construction requires
`synthetic=True`; bytes must start with `synthetic:` and be at most 4096 bytes.
The six acceptance tests use no remote object store or user data:

```sh
TMPDIR=/var/tmp python3 -m unittest tests.test_pilot_file_contract -v
```

The [node contract tests](../tests/test_pilot_node_contract.py) use the existing
JobCoordinator and SQLite authority with two logical worker IDs. They exercise
transaction contention, disconnected lease expiry/reconnect, cancellation and
refusal of a lease under another/revoked identity. There is no second executor:

```sh
TMPDIR=/var/tmp python3 -m unittest tests.test_pilot_node_contract tests.test_pilot_recovery -v
```

The file model's catalogue and object bytes are volatile; its authority callback
is supplied by the experiment; no persistent remote catalogue or offline policy
is established. The node tests run on one host and do not prove isolation, remote
identity, a real machine fork or always-on laptop-off operation. Source/workspace
keys must be stripped before any later image fork; passing a lease-owner test
alone does not prove provider snapshots strip credentials. See the [platform
decision package](../research/PILOT_PLATFORM_2026-10-03.md) for promotion gates.
