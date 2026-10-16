# Changelog entry (for the integrator)

- **Capture policies (plan 2.4, MEM-004, M04, M10):** owner-authored, versioned, deterministic capture rules (line prefix, dated line) propose reviewed-memory statements bound to exact note, revision and line; nothing is auto-accepted, rescans and dismissed lines are not re-offered, and per-policy and overall daily budgets count excess. HTTP under `/desk/capture`, supervisor hook, read-only Capture tab in the console Routines dialog. [Receipt](docs/evidence/capture-policies/RECEIPT.md).
- Tests: `tests/test_capture_policies.py` (24), `console/tests/capture.test.ts` (4), `tools/check_capture_browser.py` (15 browser checks); full backend suite 1,137 passing.

## Register

MEM-004 stays `partial` (memory types are still not fully separated as working and episodic stores). Suggested changes:

- Add `tests/test_capture_policies.py` and `tools/check_capture_browser.py` to MEM-004 `acceptance_evidence`.
- Replace the MEM-004 note's last sentence "Automatic capture policies remain pending." with: "Owner-authored deterministic capture policies propose typed statements for review with daily budgets (plan 2.4); nothing is auto-accepted. Model extraction remains absent."
- MEM-005 may also cite `tests/test_capture_policies.py`: rule proposals are inspectable and reviewed before promotion. Its status stays `partial`.
