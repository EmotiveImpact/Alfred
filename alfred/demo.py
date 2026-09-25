"""Run with python3 -m alfred.demo. Entirely synthetic, no external actions."""
from dataclasses import asdict, replace
import json
from .core import Attention, Evidence, ActionLedger, Proposal


def main() -> None:
    allowed = {("fixture", "demo"): {
        ("briefing.changed", "reported"), ("vehicle.status", "observed"),
        ("briefing.changed", "simulated"), ("note", "reported")}}
    engine = Attention(allowed, {"briefing.changed"})
    first = Evidence("e1", "demo", "fixture", "briefing-1", "briefing.changed",
                     100, 160, "reported", "Approved briefing timing has changed.")
    events = [first, first, replace(first, event_id="e2", observed_at=80, expires_at=95),
              replace(first, event_id="e3", basis="simulated"),
              replace(first, event_id="e4", scope="private"),
              replace(first, event_id="e5", kind="note", summary="Routine information.")]
    print("ALFRED offline contract replay. These are synthetic inputs, not live observations.")
    for event in events:
        result = engine.evaluate(event, authenticated_source="fixture", active_scope="demo", now=110)
        print(json.dumps(asdict(result)))
    proposal = Proposal("a1", "demo-user", "demo", "message.draft", '{"text":"Synthetic update"}', 200)
    ledger = ActionLedger()
    ledger.propose(proposal)
    for signal in ("approve", "dispatch", "receipt", "verify"):
        state = ledger.advance(scope="demo", action_id="a1", actor="demo-user", signal=signal,
                               now=110, policy_allows=True, approved_hash=proposal.fingerprint)
        print("SIMULATED action state:", state)
    print("No message was sent. Receipt and verification signals were supplied by this fixture.")


if __name__ == "__main__":
    main()
