"""Original, deterministic ALFRED contract prototype.

No network, model, microphone, shell or device control. Caller identities are
trusted test inputs, NOT authentication. State is bounded but in-memory only.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import json


def token(value: str) -> None:
    if type(value) is not str or not value or len(value) > 128:
        raise ValueError("Invalid identifier")
    if any(not (c.isascii() and (c.isalnum() or c in "._:/-")) for c in value):
        raise ValueError("Invalid identifier characters")


def second(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("Time must be a non-negative integer")


def digest(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(raw.encode()) > 8192:
        raise ValueError("Payload too large")
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class Evidence:
    event_id: str
    scope: str
    source: str
    subject: str
    kind: str
    observed_at: int
    expires_at: int
    basis: str
    summary: str

    def __post_init__(self) -> None:
        for field in (self.event_id, self.scope, self.source, self.subject, self.kind):
            token(field)
        second(self.observed_at)
        second(self.expires_at)
        if self.expires_at <= self.observed_at:
            raise ValueError("Expiry must follow observation")
        if self.basis not in {"reported", "observed", "derived", "simulated"}:
            raise ValueError("Unknown evidence basis")
        if type(self.summary) is not str or not 1 <= len(self.summary) <= 2048:
            raise ValueError("Invalid summary")
        if any(ord(c) < 32 for c in self.summary):
            raise ValueError("Control characters in summary")


@dataclass(frozen=True)
class Decision:
    route: str
    reason: str
    evidence_id: str
    basis: str


class Attention:
    """Deterministic replay selector. Not semantic understanding or a safety alarm."""
    def __init__(self, allowed_sources: dict, interrupt_kinds: set,
                 simulation: bool = False, capacity: int = 4096):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("Invalid capacity")
        # Each (source, scope) must explicitly allow the event kind and evidence basis.
        self.allowed = {key: frozenset(values) for key, values in allowed_sources.items()}
        self.interrupt = frozenset(interrupt_kinds)
        self.simulation = simulation
        self.capacity = capacity
        self.seen: dict[tuple, str] = {}
        self.latest: dict[tuple, int] = {}

    def evaluate(self, event: Evidence, *, authenticated_source: str,
                 active_scope: str, now: int, focus: bool = False) -> Decision:
        second(now)
        def answer(route: str, reason: str) -> Decision:
            return Decision(route, reason, event.event_id, event.basis)
        if authenticated_source != event.source or event.scope != active_scope:
            return answer("reject", "source-or-scope-mismatch")
        if (event.kind, event.basis) not in self.allowed.get((event.source, event.scope), ()):
            return answer("reject", "source-capability-not-allowed")
        if event.basis == "simulated" and not self.simulation:
            return answer("reject", "simulation-is-not-live-evidence")
        if event.observed_at > now:
            return answer("reject", "future-observation")
        key = (event.scope, event.source, event.event_id)
        fingerprint = digest(asdict(event))
        if key in self.seen:
            return answer("suppress" if self.seen[key] == fingerprint else "reject",
                          "duplicate" if self.seen[key] == fingerprint else "event-id-collision")
        if now >= event.expires_at:
            return answer("suppress", "expired")
        if len(self.seen) >= self.capacity:
            return answer("reject", "replay-capacity-reached")
        entity = (event.scope, event.source, event.subject, event.kind)
        latest = self.latest.get(entity, -1)
        self.seen[key] = fingerprint
        if event.observed_at < latest:
            return answer("suppress", "older-than-current-observation")
        if event.observed_at == latest:
            return answer("queue", "same-time-observation-needs-reconciliation")
        self.latest[entity] = event.observed_at
        if event.basis in {"derived", "simulated"}:
            return answer("queue", "analysis-not-observation")
        if event.kind in self.interrupt:
            return answer("speak", "explicit-interruption-rule")
        return answer("queue", "focus-digest" if focus else "next-briefing")


@dataclass(frozen=True)
class Proposal:
    action_id: str
    actor: str
    scope: str
    capability: str
    parameters_json: str
    expires_at: int

    def __post_init__(self) -> None:
        for value in (self.action_id, self.actor, self.scope, self.capability):
            token(value)
        second(self.expires_at)
        if type(self.parameters_json) is not str or len(self.parameters_json.encode()) > 8192:
            raise ValueError("Invalid parameters")
        params = json.loads(self.parameters_json)
        if type(params) is not dict:
            raise ValueError("Parameters must be an object")
        digest(params)

    @property
    def fingerprint(self) -> str:
        return digest(asdict(self))


class ActionLedger:
    """Effect-free action state contract, not an execution or authentication service."""
    def __init__(self, capacity: int = 4096):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("Invalid capacity")
        self.capacity = capacity
        self._items: dict[tuple, tuple[Proposal, str]] = {}

    def propose(self, proposal: Proposal) -> str:
        key = (proposal.scope, proposal.action_id)
        existing = self._items.get(key)
        if existing:
            if existing[0].fingerprint != proposal.fingerprint:
                raise ValueError("Action id reused with different content")
            return existing[1]
        if len(self._items) >= self.capacity:
            raise ValueError("Ledger capacity reached")
        self._items[key] = (proposal, "proposed")
        return "proposed"

    def advance(self, *, scope: str, action_id: str, actor: str, signal: str,
                now: int, policy_allows: bool, approved_hash: str = "") -> str:
        second(now)
        if type(policy_allows) is not bool:
            raise ValueError("Policy result must be boolean")
        key = (scope, action_id)
        proposal, state = self._items[key]
        if actor != proposal.actor:
            raise PermissionError("Wrong actor")
        transitions = {
            ("proposed", "approve"): "approved",
            ("approved", "dispatch"): "dispatched",
            ("dispatched", "receipt"): "received",
            ("received", "verify"): "verified",
            ("proposed", "cancel"): "cancelled",
            ("approved", "cancel"): "cancelled",
            ("dispatched", "uncertain"): "uncertain",
            ("received", "uncertain"): "uncertain",
        }
        target = transitions.get((state, signal))
        if target is None:
            raise ValueError("Invalid transition")
        if signal in {"approve", "dispatch"}:
            if not policy_allows or now >= proposal.expires_at:
                raise PermissionError("Expired or no longer authorised")
            if signal == "approve" and approved_hash != proposal.fingerprint:
                raise PermissionError("Approval is not bound to this proposal")
        self._items[key] = (proposal, target)
        return target

    def status(self, scope: str, action_id: str) -> str:
        return self._items[(scope, action_id)][1]
