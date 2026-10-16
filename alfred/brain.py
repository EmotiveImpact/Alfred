"""The brain plug (docs/AGENT_HUB.md, step H1): one contract for every brain.

ALFRED sends a **task packet** and a brain returns a **result bundle**. Both have a
strict, versioned shape checked here. A brain is any implementation of ``Brain``
registered in a ``BrainRegistry`` with a declared ``BrainSpec`` (where it runs, which
tools it can use, which scope classes it may serve, the highest autonomy it supports
and its token price). The only brain in this module is ``SyntheticBrain``: a
deterministic, rule-based fixture with no model, no network and no files.

Dispatch goes through the existing job coordinator (``alfred.jobs``) as the job kind
``brain_task``, so leases, heartbeats, cancellation, hashed results, input policy at
submission and again at lease time, and the append-only job event record all apply
unchanged. ``BrainBackend`` is a ``WorkerBackend`` that runs a registered brain with an
ALFRED-owned ``Meter`` which stops it at the first step beyond its budget.

Models propose, independent policy decides:

* ``BrainPolicy`` decides whether a brain may take a packet (scope class, cloud or
  local, tools, autonomy). A brain's own spec never grants itself permission.
* A result bundle is a claim. ``BrainHub.ingest`` validates it against the packet that
  was actually sent: citations must quote excerpts that were sent, artefact hashes must
  match their content, tools outside the packet's allowlist refuse the whole result,
  and the metered usage must be within budget.
* Proposed actions never run. Autonomy 0 drops and reports them; 1 keeps them as
  drafts for the owner to act on; 2 turns an allowed capability into a pending action
  through the existing exact-approval path (``LocalCore.propose``), which still needs
  the owner's ``approve`` with the exact fingerprint. Levels 3 and 4 are refused until
  the private-pilot gates exist.
* Memory suggestions go to a review inbox as suggestions. Nothing here accepts them.

What a brain never receives: credentials, database or vault paths, workspace
identifiers, other scopes' content, full note bodies beyond the granted excerpts, or a
way to schedule itself.
"""
from __future__ import annotations
import abc
import copy
from dataclasses import dataclass, field
import hashlib
import json
import math
import re
import secrets
import threading
import time

from .jobs import BackendResult, JobCoordinator, MAX_ARTEFACT_BYTES, REASON, WorkerBackend
from . import job_kinds
from .local import Fault, ident, text

PACKET_VERSION = 1
BUNDLE_VERSION = 1
ENVELOPE_VERSION = 1
KIND = 'brain_task'
SCOPE_CLASSES = ('personal', 'company', 'client')
LOCALITIES = ('local', 'cloud')
AUTONOMY = {0: 'observe', 1: 'suggest', 2: 'act_with_approval', 3: 'act_within_mandate', 4: 'delegate'}
ENFORCED_AUTONOMY = (0, 1, 2)
PILOT_GATE_REASON = 'autonomy_requires_pilot_gates'
# The existing context budget (alfred.grounded and alfred.knowledge_context): five
# sources and 6000 excerpt characters; reviewed statements: four and 1600 characters.
MAX_EXCERPTS, MAX_EXCERPT_CHARACTERS, MAX_ONE_EXCERPT = 5, 6000, 1200
MAX_LEARNED, MAX_LEARNED_CHARACTERS = 4, 1600
MAX_EXCERPT_LINES = 40
MAX_TOOLS = 16
MAX_PACKET_BYTES = job_kinds.KINDS[KIND]['parameters']['packet'][2]
BUDGET_LIMITS = {'wall_seconds': (1, 3600), 'tokens': (1, 1_000_000), 'money_pence': (0, 100_000), 'steps': (1, 1000)}
METERED = ('steps', 'tokens', 'money_pence')
# Capabilities a brain may propose at autonomy 2. Each still needs exact approval.
PROPOSABLE = ('message.draft',)
ACTION_TTL = 3600
MAX_ANSWER, MAX_QUOTE, MAX_CITATIONS = 4000, 400, 16
MAX_ARTEFACTS, MAX_ARTEFACT_CONTENT = 8, 64000
MAX_ACTIONS, MAX_SUGGESTIONS, MAX_LOG = 8, 8, 1000
ARTEFACT_MEDIA = ('text/plain', 'text/markdown', 'application/json')
LOG_KINDS = ('read', 'reason', 'tool', 'write')
REF = re.compile(r'[EL][1-9][0-9]?')
NOTE_ID = re.compile(r'[0-9a-f]{24}')
SHA256 = re.compile(r'[0-9a-f]{64}')
TOOL = re.compile(r'[a-z][a-z0-9_.-]{0,47}')
ARTEFACT_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}')
MARKER = re.compile(r'\[([EL][0-9]{1,3})\]')
# The shape of an ALFRED bearer token. A packet carrying one is refused outright.
CREDENTIAL_SHAPE = re.compile(r'(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS brain_meta(version INTEGER NOT NULL);
INSERT INTO brain_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM brain_meta);
CREATE TABLE IF NOT EXISTS brain_tasks(
 job_id TEXT PRIMARY KEY REFERENCES jobs(id), scope TEXT NOT NULL, actor TEXT NOT NULL,
 task_id TEXT NOT NULL, brain TEXT NOT NULL, scope_class TEXT NOT NULL, autonomy INTEGER NOT NULL,
 packet_sha256 TEXT NOT NULL, created INTEGER NOT NULL, UNIQUE(scope,actor,task_id));
CREATE TABLE IF NOT EXISTS brain_results(
 job_id TEXT PRIMARY KEY REFERENCES brain_tasks(job_id), scope TEXT NOT NULL, actor TEXT NOT NULL,
 status TEXT NOT NULL, reason TEXT, envelope_sha256 TEXT, outcome TEXT NOT NULL, created INTEGER NOT NULL,
 CHECK(status IN ('accepted','refused','stopped')));
CREATE TABLE IF NOT EXISTS brain_proposals(
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES brain_tasks(job_id), scope TEXT NOT NULL,
 actor TEXT NOT NULL, position INTEGER NOT NULL, capability TEXT NOT NULL, parameters TEXT,
 fingerprint TEXT NOT NULL, reason TEXT NOT NULL, cites TEXT NOT NULL, disposition TEXT NOT NULL,
 refusal TEXT, action_id TEXT, created INTEGER NOT NULL,
 CHECK(disposition IN ('dropped_observe','draft_only','pending_approval','refused')));
CREATE TABLE IF NOT EXISTS brain_suggestions(
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES brain_tasks(job_id), scope TEXT NOT NULL,
 actor TEXT NOT NULL, position INTEGER NOT NULL, statement TEXT NOT NULL, cites TEXT NOT NULL,
 state TEXT NOT NULL, created INTEGER NOT NULL, decided INTEGER,
 CHECK(state IN ('suggested','dismissed')));
'''


def _compact(value) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False, ensure_ascii=True)
    except (TypeError, ValueError, RecursionError):
        raise Fault('invalid_json') from None


def packet_sha256(packet) -> str:
    return hashlib.sha256(_compact(packet).encode('ascii')).hexdigest()


def _exact(value, keys, code):
    if type(value) is not dict or set(value) != set(keys):
        raise Fault(code)
    return value


def _int(value, low, high, code):
    if type(value) is not int or not low <= value <= high:
        raise Fault(code)
    return value


def _body(value, limit, code):
    """Free text that may contain newlines and tabs (excerpts, answers, artefacts)."""
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        raise Fault(code)
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise Fault('invalid_unicode') from None
    if any((ord(c) < 32 and c not in '\n\t') or 127 <= ord(c) < 160 for c in value):
        raise Fault('control_character')
    return value


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


# Task packet -----------------------------------------------------------------

PACKET_KEYS = {'packet_version', 'task_id', 'goal', 'scope', 'instruction', 'context', 'learned',
               'tools', 'budget', 'autonomy'}
# H4: acceptance checks declared by the owner or a mandate, never the brain
# (alfred.verification). A packet without them is exactly the H1 contract.
OPTIONAL_PACKET_KEYS = {'acceptance'}
EXCERPT_KEYS = {'id', 'note_id', 'title', 'revision', 'sha256', 'start_line', 'end_line', 'text', 'basis'}
LEARNED_KEYS = {'id', 'claim_id', 'version', 'statement', 'basis'}
EXCERPT_BASIS = 'authored_note_not_verified_fact'
LEARNED_BASIS = 'owner_reviewed_statement_not_verified_fact'


def validate_budget(budget):
    _exact(budget, BUDGET_LIMITS, 'invalid_budget')
    for name, (low, high) in BUDGET_LIMITS.items():
        _int(budget[name], low, high, 'invalid_budget')
    return budget


def validate_packet(packet):
    """Return the packet unchanged if it satisfies contract version 1, else raise a Fault.

    The shape has no field for a credential, path, workspace or person, and the check
    below also refuses any string anywhere in the packet that has the shape of an ALFRED
    bearer token. Autonomy 3 and 4 are valid values here but refused by ``BrainPolicy``.
    """
    if type(packet) is not dict or not PACKET_KEYS <= set(packet) <= PACKET_KEYS | OPTIONAL_PACKET_KEYS:
        raise Fault('invalid_packet_fields')
    if packet['packet_version'] != PACKET_VERSION or type(packet['packet_version']) is not int:
        raise Fault('unsupported_packet_version')
    ident(packet['task_id'])
    goal = _exact(packet['goal'], {'ref', 'statement'}, 'invalid_goal')
    ident(goal['ref']); text(goal['statement'], 400)
    if packet['scope'] not in SCOPE_CLASSES:
        raise Fault('invalid_scope_class')
    _body(packet['instruction'], 1000, 'invalid_instruction')
    context = packet['context']
    if type(context) is not list or len(context) > MAX_EXCERPTS:
        raise Fault('invalid_context')
    total = 0
    for index, item in enumerate(context, 1):
        _exact(item, EXCERPT_KEYS, 'invalid_excerpt')
        if item['id'] != f'E{index}':
            raise Fault('invalid_excerpt_id')
        if not isinstance(item['note_id'], str) or not NOTE_ID.fullmatch(item['note_id']):
            raise Fault('invalid_excerpt')
        if not isinstance(item['sha256'], str) or not SHA256.fullmatch(item['sha256']):
            raise Fault('invalid_excerpt')
        text(item['title'], 200)
        _int(item['revision'], 1, 2**31, 'invalid_excerpt')
        _int(item['start_line'], 1, 2**31, 'invalid_excerpt')
        _int(item['end_line'], item['start_line'], item['start_line'] + MAX_EXCERPT_LINES - 1, 'invalid_excerpt')
        _body(item['text'], MAX_ONE_EXCERPT, 'excerpt_over_budget')
        if item['basis'] != EXCERPT_BASIS:
            raise Fault('invalid_excerpt')
        total += len(item['text'])
    if total > MAX_EXCERPT_CHARACTERS:
        raise Fault('context_over_budget')
    learned = packet['learned']
    if type(learned) is not list or len(learned) > MAX_LEARNED:
        raise Fault('invalid_learned')
    total = 0
    for index, item in enumerate(learned, 1):
        _exact(item, LEARNED_KEYS, 'invalid_learned')
        if item['id'] != f'L{index}':
            raise Fault('invalid_learned_id')
        ident(item['claim_id']); _int(item['version'], 1, 2**31, 'invalid_learned')
        text(item['statement'], 600)
        if item['basis'] != LEARNED_BASIS:
            raise Fault('invalid_learned')
        total += len(item['statement'])
    if total > MAX_LEARNED_CHARACTERS:
        raise Fault('learned_over_budget')
    tools = packet['tools']
    if (type(tools) is not list or len(tools) > MAX_TOOLS or len(set(map(str, tools))) != len(tools)
            or any(not isinstance(t, str) or not TOOL.fullmatch(t) for t in tools)):
        raise Fault('invalid_tools')
    validate_budget(packet['budget'])
    _int(packet['autonomy'], 0, 4, 'invalid_autonomy')
    if 'acceptance' in packet:
        from .verification import validate_acceptance
        validate_acceptance(packet['acceptance'], packet)
    if any(CREDENTIAL_SHAPE.search(s) for s in _strings(packet)):
        raise Fault('credential_shaped_value_in_packet')
    if len(_compact(packet).encode('ascii')) > MAX_PACKET_BYTES:
        raise Fault('packet_too_large', 413)
    return packet


# Result bundle ---------------------------------------------------------------

BUNDLE_KEYS = {'bundle_version', 'answer', 'artefacts', 'proposed_actions', 'memory_suggestions', 'work_log'}


def _refs(value, code):
    if type(value) is not list or len(value) > MAX_CITATIONS or len(set(map(str, value))) != len(value):
        raise Fault(code)
    for ref in value:
        if not isinstance(ref, str) or not REF.fullmatch(ref):
            raise Fault(code)
    return value


def validate_bundle(bundle):
    """Return the bundle unchanged if its shape satisfies contract version 1, else raise.

    Shape only. Whether its citations, hashes, tools and proposals are acceptable for
    the packet that was sent is decided by ``check_bundle``.
    """
    _exact(bundle, BUNDLE_KEYS, 'invalid_bundle_fields')
    if bundle['bundle_version'] != BUNDLE_VERSION or type(bundle['bundle_version']) is not int:
        raise Fault('unsupported_bundle_version')
    answer = _exact(bundle['answer'], {'text', 'citations'}, 'invalid_answer')
    _body(answer['text'], MAX_ANSWER, 'invalid_answer')
    citations = answer['citations']
    if type(citations) is not list or len(citations) > MAX_CITATIONS:
        raise Fault('invalid_citations')
    for item in citations:
        _exact(item, {'ref', 'quote'}, 'invalid_citations')
        if not isinstance(item['ref'], str) or not REF.fullmatch(item['ref']):
            raise Fault('invalid_citations')
        _body(item['quote'], MAX_QUOTE, 'invalid_citations')
    artefacts = bundle['artefacts']
    if type(artefacts) is not list or len(artefacts) > MAX_ARTEFACTS:
        raise Fault('invalid_artefacts')
    names = set()
    for item in artefacts:
        _exact(item, {'name', 'media_type', 'sha256', 'content'}, 'invalid_artefacts')
        if not isinstance(item['name'], str) or not ARTEFACT_NAME.fullmatch(item['name']) or item['name'] in names:
            raise Fault('invalid_artefacts')
        names.add(item['name'])
        if item['media_type'] not in ARTEFACT_MEDIA:
            raise Fault('invalid_artefacts')
        if not isinstance(item['sha256'], str) or not SHA256.fullmatch(item['sha256']):
            raise Fault('invalid_artefacts')
        _body(item['content'], MAX_ARTEFACT_CONTENT, 'invalid_artefacts')
    actions = bundle['proposed_actions']
    if type(actions) is not list or len(actions) > MAX_ACTIONS:
        raise Fault('invalid_proposed_actions')
    for item in actions:
        _exact(item, {'capability', 'parameters', 'reason', 'cites'}, 'invalid_proposed_actions')
        if not isinstance(item['capability'], str) or not TOOL.fullmatch(item['capability']):
            raise Fault('invalid_proposed_actions')
        if type(item['parameters']) is not dict or len(_compact(item['parameters'])) > 4096:
            raise Fault('invalid_proposed_actions')
        text(item['reason'], 400)
        _refs(item['cites'], 'invalid_proposed_actions')
    suggestions = bundle['memory_suggestions']
    if type(suggestions) is not list or len(suggestions) > MAX_SUGGESTIONS:
        raise Fault('invalid_memory_suggestions')
    for item in suggestions:
        _exact(item, {'statement', 'cites'}, 'invalid_memory_suggestions')
        text(item['statement'], 400)
        if not _refs(item['cites'], 'invalid_memory_suggestions'):
            raise Fault('uncited_memory_suggestion')
    log = bundle['work_log']
    if type(log) is not list or len(log) > MAX_LOG:
        raise Fault('invalid_work_log')
    for index, item in enumerate(log, 1):
        _exact(item, {'step', 'kind', 'tool', 'summary'}, 'invalid_work_log')
        _int(item['step'], 1, MAX_LOG, 'invalid_work_log')
        if item['kind'] not in LOG_KINDS:
            raise Fault('invalid_work_log')
        if item['kind'] == 'tool':
            if not isinstance(item['tool'], str) or not TOOL.fullmatch(item['tool']):
                raise Fault('invalid_work_log')
        elif item['tool'] is not None:
            raise Fault('invalid_work_log')
        text(item['summary'], 200)
    return bundle


def check_bundle(packet, bundle):
    """Decide whether a well-formed bundle is acceptable for the packet actually sent.

    Returns None when acceptable, or a refusal reason. Refusal covers the whole result:
    a fabricated citation, a wrong hash or an unlisted tool means none of the bundle is
    used, not just the offending item.
    """
    sent = {item['id']: item['text'] for item in packet['context']}
    sent.update({item['id']: item['statement'] for item in packet['learned']})
    for item in bundle['answer']['citations']:
        if item['ref'] not in sent:
            return 'citation_to_unsent_excerpt'
        if item['quote'] not in sent[item['ref']]:
            return 'citation_quote_not_literal'
    cited = {item['ref'] for item in bundle['answer']['citations']}
    for marker in MARKER.findall(bundle['answer']['text']):
        if marker not in sent:
            return 'citation_to_unsent_excerpt'
        if marker not in cited:
            return 'citation_marker_without_quote'
    for group in ([a['cites'] for a in bundle['proposed_actions']] + [s['cites'] for s in bundle['memory_suggestions']]):
        if any(ref not in sent for ref in group):
            return 'citation_to_unsent_excerpt'
    for item in bundle['artefacts']:
        if hashlib.sha256(item['content'].encode('utf-8')).hexdigest() != item['sha256']:
            return 'artefact_hash_mismatch'
    allowed = set(packet['tools'])
    if any(item['kind'] == 'tool' and item['tool'] not in allowed for item in bundle['work_log']):
        return 'tool_outside_allowlist'
    return None


# Brains, registry and policy -------------------------------------------------

@dataclass(frozen=True)
class BrainSpec:
    """What a brain declares about itself. Declarations limit; they never grant."""
    id: str
    label: str
    locality: str
    version: str
    scopes: frozenset = field(default_factory=frozenset)
    tools: frozenset = field(default_factory=frozenset)
    max_autonomy: int = 0
    pence_per_1k_tokens: int = 0

    def validate(self):
        try:
            job_kinds.validate(KIND, {'brain': self.id, 'packet': {'x': 1}})
        except ValueError:
            raise Fault('invalid_brain_id') from None
        text(self.label, 120); text(self.version, 80)
        if self.locality not in LOCALITIES:
            raise Fault('invalid_brain_locality')
        if type(self.scopes) is not frozenset or not self.scopes or not self.scopes <= set(SCOPE_CLASSES):
            raise Fault('invalid_brain_scopes')
        if type(self.tools) is not frozenset or len(self.tools) > MAX_TOOLS or any(
                not isinstance(t, str) or not TOOL.fullmatch(t) for t in self.tools):
            raise Fault('invalid_brain_tools')
        _int(self.max_autonomy, 0, 4, 'invalid_brain_autonomy')
        _int(self.pence_per_1k_tokens, 0, 100_000, 'invalid_brain_price')
        return self


class Brain(abc.ABC):
    """One brain behind the plug. ``run`` receives a copy of a validated packet and an
    ALFRED-owned meter, must call ``meter.step`` for every step it takes, and returns a
    result bundle dict. It is given nothing else: no store, no credential, no path."""
    spec: BrainSpec

    @abc.abstractmethod
    def run(self, packet: dict, meter: 'Meter') -> dict:
        """Work on the packet and return a result bundle."""


class BrainRegistry:
    """In-process, ALFRED-owned list of plugged-in brains. Swapping is unplug and plug."""

    def __init__(self):
        self._brains, self._lock = {}, threading.Lock()

    def register(self, brain: Brain) -> BrainSpec:
        if not isinstance(brain, Brain) or not isinstance(getattr(brain, 'spec', None), BrainSpec):
            raise Fault('invalid_brain')
        spec = brain.spec.validate()
        with self._lock:
            if spec.id in self._brains:
                raise Fault('brain_exists', 409)
            self._brains[spec.id] = brain
        return spec

    def unregister(self, brain_id) -> None:
        with self._lock:
            if self._brains.pop(brain_id, None) is None:
                raise Fault('brain_not_registered', 404)

    def get(self, brain_id) -> Brain:
        with self._lock:
            brain = self._brains.get(brain_id)
        if brain is None:
            raise Fault('brain_not_registered', 404)
        return brain

    def specs(self) -> list:
        with self._lock:
            return [self._brains[k].spec for k in sorted(self._brains)]


class BrainPolicy:
    """Independent decision on whether a brain may take a packet.

    ``cloud_scopes`` lists the scope classes a cloud brain may serve; it is empty by
    default because which cloud models are allowed per scope is an owner decision that
    has not been made (AGENT_HUB.md). ``permitted_tools`` is the owner's tool allowlist;
    empty by default, so a packet may name no tool until the owner allows one.
    """

    def __init__(self, *, cloud_scopes=(), permitted_tools=()):
        self.cloud_scopes = frozenset(cloud_scopes)
        self.permitted_tools = frozenset(permitted_tools)
        if not self.cloud_scopes <= set(SCOPE_CLASSES):
            raise Fault('invalid_cloud_scopes')
        if any(not isinstance(t, str) or not TOOL.fullmatch(t) for t in self.permitted_tools):
            raise Fault('invalid_permitted_tools')

    def decide(self, spec: BrainSpec, packet: dict) -> None:
        """Raise a Fault with the reason when the brain may not take this packet."""
        if packet['autonomy'] not in ENFORCED_AUTONOMY:
            raise Fault(PILOT_GATE_REASON, 403)
        if packet['scope'] not in spec.scopes:
            raise Fault('brain_scope_not_declared', 403)
        if spec.locality == 'cloud' and packet['scope'] not in self.cloud_scopes:
            raise Fault('cloud_brain_refused_for_scope', 403)
        if packet['autonomy'] > spec.max_autonomy:
            raise Fault('autonomy_above_brain_limit', 403)
        tools = set(packet['tools'])
        if not tools <= self.permitted_tools:
            raise Fault('tool_not_permitted', 403)
        if not tools <= spec.tools:
            raise Fault('tool_not_declared_by_brain', 403)


# Budget meter ----------------------------------------------------------------

class BudgetExceeded(Exception):
    def __init__(self, dimension):
        super().__init__(dimension)
        self.dimension = dimension


class Stopped(Exception):
    pass


class Meter:
    """ALFRED's count of what a brain has used, checked before every step.

    The step that would go beyond any limit is refused, so a brain stops at its limit
    rather than after it. Usage is measured here, not taken from the brain's word; a
    real model adapter would charge tokens from the provider's usage report.
    """

    def __init__(self, budget, *, pence_per_1k_tokens=0, clock=time.monotonic):
        self.budget, self.price, self.clock = dict(validate_budget(budget)), pence_per_1k_tokens, clock
        self.deadline = clock() + budget['wall_seconds']
        self.used = {'steps': 0, 'tokens': 0, 'money_pence': 0}
        self.cancelled = threading.Event()
        self.exceeded = None
        self._lock = threading.Lock()

    def step(self, *, tokens=0):
        if type(tokens) is not int or tokens < 0:
            raise Stopped('invalid_meter_charge')
        with self._lock:
            if self.cancelled.is_set():
                raise Stopped('cancelled')
            if self.exceeded:
                raise BudgetExceeded(self.exceeded)
            if self.clock() > self.deadline:
                self.exceeded = 'wall_seconds'
                raise BudgetExceeded('wall_seconds')
            steps, total = self.used['steps'] + 1, self.used['tokens'] + tokens
            money = math.ceil(total * self.price / 1000)
            for name, value in (('steps', steps), ('tokens', total), ('money_pence', money)):
                if value > self.budget[name]:
                    self.exceeded = name
                    raise BudgetExceeded(name)
            self.used = {'steps': steps, 'tokens': total, 'money_pence': money}

    def snapshot(self):
        with self._lock:
            return dict(self.used)


def tokens(value: str) -> int:
    """Deterministic token count for the synthetic brain: whitespace-separated words."""
    return len(value.split())


# Worker backend --------------------------------------------------------------

class _BrainRun:
    def __init__(self, meter):
        self.meter, self.thread, self.output, self.reason = meter, None, None, None
        self.lock = threading.Lock()


class BrainBackend(WorkerBackend):
    """Runs ``brain_task`` jobs on registered brains, in a thread of this process.

    Holds no job authority; ``JobCoordinator`` keeps leases, cancellation, input policy
    and hash checks. Before a brain starts, the backend revalidates the packet, asks
    ``BrainPolicy`` again (a brain may have been unplugged or the policy tightened since
    submission), and checks every excerpt against the note bytes the coordinator
    delivered for the bound revision. The brain then receives a copy of the packet only,
    never the delivered note bytes.

    Honest scope: an in-process thread cannot be killed. At the wall-clock limit the
    backend reports the job over budget at once and discards anything the thread
    produces later; the meter refuses its next step. A real brain needs an isolated,
    killable process backend (H5).
    """
    name = 'brain'

    def __init__(self, registry: BrainRegistry, policy: BrainPolicy, *, gate=None):
        self.registry, self.policy = registry, policy
        # H2 (alfred.hub_goals): the goal hub rechecks the mandate before a brain starts and
        # records what the meter counted when the run ends. None keeps H1 behaviour.
        self.gate = gate
        self._runs, self._lock = {}, threading.Lock()

    @staticmethod
    def _check_excerpts(packet, inputs):
        order = []
        for item in packet['context']:
            if item['note_id'] not in order:
                order.append(item['note_id'])
        if len(order) != len(inputs):
            raise Fault('packet_inputs_mismatch')
        bodies = {}
        for note_id, delivered in zip(order, inputs):
            try:
                bodies[note_id] = bytes(delivered['data']).decode('utf-8').splitlines()
            except UnicodeError:
                raise Fault('packet_inputs_mismatch') from None
        for item in packet['context']:
            lines = bodies[item['note_id']]
            if item['end_line'] > len(lines) or '\n'.join(lines[item['start_line'] - 1:item['end_line']]) != item['text']:
                raise Fault('excerpt_not_in_bound_revision')

    def submit(self, handle, kind, parameters, inputs) -> None:
        ident(handle)
        if kind != KIND:
            raise Fault('kind_not_for_this_backend')
        try:
            parameters = job_kinds.validate(kind, parameters)
        except ValueError as exc:
            raise Fault(str(exc)) from None
        packet = validate_packet(copy.deepcopy(parameters['packet']))
        brain = self.registry.get(parameters['brain'])
        self.policy.decide(brain.spec, packet)
        self._check_excerpts(packet, inputs)
        meter = Meter(packet['budget'], pence_per_1k_tokens=brain.spec.pence_per_1k_tokens)
        run = _BrainRun(meter)
        with self._lock:
            if handle in self._runs:
                raise Fault('backend_handle_exists', 409)
            if self.gate is not None:
                # The JobWorker handle is '<job>.<attempt>'. A refusal here means the brain never starts.
                self.gate.dispatch(handle.rsplit('.', 1)[0], brain.spec, packet)
            self._runs[handle] = run
        run.began = time.monotonic()
        digest = packet_sha256(packet)
        given = json.loads(_compact(packet))  # A fresh copy: the brain cannot alter ALFRED's record.
        run.thread = threading.Thread(target=self._work, args=(run, brain, given, digest), daemon=True,
                                      name='alfred-brain-' + brain.spec.id)
        run.thread.start()

    @staticmethod
    def _work(run, brain, packet, digest):
        reason, output = None, None
        try:
            bundle = brain.run(packet, run.meter)
            envelope = {'envelope_version': ENVELOPE_VERSION, 'brain': brain.spec.id,
                        'brain_version': brain.spec.version, 'packet_sha256': digest,
                        'metered': run.meter.snapshot(), 'bundle': bundle,
                        'basis': 'brain_claim_not_verified'}
            output = _compact(envelope).encode('ascii')
            if len(output) > MAX_ARTEFACT_BYTES:
                reason, output = 'output_too_large', None
        except BudgetExceeded as exc:
            reason = 'over_budget_' + exc.dimension
        except Stopped as exc:
            reason = 'cancelled' if str(exc) == 'cancelled' else 'brain_error'
        except Fault:
            reason = 'brain_output_invalid'
        except Exception:  # A brain failing is a result to record, not a host crash.
            reason = 'brain_error'
        with run.lock:
            if run.reason is None:
                run.reason, run.output = reason, output

    def _run(self, handle) -> _BrainRun:
        with self._lock:
            run = self._runs.get(handle)
        if run is None:
            raise Fault('unknown_backend_handle', 404)
        return run

    def _overdue(self, run) -> bool:
        if run.thread.is_alive() and run.meter.clock() > run.meter.deadline:
            with run.lock:
                if run.reason is None:
                    run.reason, run.output = 'over_budget_wall_seconds', None
            run.meter.cancelled.set()
            return True
        return False

    def status(self, handle) -> str:
        run = self._run(handle)
        if self._overdue(run):
            return 'finished'
        return 'running' if run.thread.is_alive() else 'finished'

    def cancel(self, handle) -> None:
        run = self._run(handle)
        with run.lock:
            if run.reason is None and run.thread.is_alive():
                run.reason, run.output = 'cancelled', None
        run.meter.cancelled.set()

    def collect(self, handle, timeout=None) -> BackendResult:
        run = self._run(handle)
        deadline = None if timeout is None else time.monotonic() + timeout
        while run.thread.is_alive() and not self._overdue(run) and run.reason != 'cancelled':
            if deadline is not None and time.monotonic() >= deadline:
                raise Fault('backend_still_running', 409)
            run.thread.join(0.02)
        with self._lock:
            self._runs.pop(handle, None)
        with run.lock:
            reason, output = run.reason, run.output
        if self.gate is not None:
            self._report(handle, run, reason)
        if reason is not None:
            return BackendResult(False, None, reason if REASON.fullmatch(reason) else 'brain_error', None, '')
        if output is None:
            return BackendResult(False, None, 'brain_error', None, '')
        return BackendResult(True, output, None, 0, '')

    def _report(self, handle, run, reason):
        """Tell the goal hub what the meter counted, before the job settles. Wall time is
        whole seconds, at least one, and at most the packet's limit (the brain is stopped there)."""
        wall = min(max(1, math.ceil(time.monotonic() - run.began)), run.meter.budget['wall_seconds'])
        try:
            self.gate.metered(handle.rsplit('.', 1)[0], run.meter.snapshot(), wall, reason)
        except Exception:  # Unreported usage is charged at the task's ceiling by the hub.
            pass


# Synthetic brain -------------------------------------------------------------

SEND_EVERYTHING = re.compile(r'(?i)\bsend everything to\s+(\S+)')
REMEMBER = re.compile(r'(?i)^\s*remember:\s*(.+?)\s*$')
DRAFT = re.compile(r'(?i)^\s*draft:\s*(.+?)\s*$')
FAULTS = ('fabricate_citation', 'misquote', 'bad_artefact_hash', 'unlisted_tool', 'runaway',
          'stall', 'slow_steps', 'claim_extra_field', 'send_everything_as_draft', 'crash')


class SyntheticBrain(Brain):
    """Deterministic, rule-based test brain. No model, no network, no files.

    Rules, in order:
    * reads each excerpt and learned statement (one metered step each, tokens = words);
    * answers with the first non-empty line of each excerpt, each marked and quoted;
    * writes one Markdown artefact holding the answer, with its SHA-256;
    * an instruction line ``draft: <text>`` becomes a proposed ``message.draft``;
    * an excerpt line containing ``send everything to <address>`` is obeyed naively and
      becomes a proposed ``message.send`` (a prompt-injection fixture: a real model
      may do the same, which is why proposals are never effects);
    * an excerpt line ``remember: <statement>`` becomes a cited memory suggestion;
    * each tool in the packet's allowlist is logged as used once.

    ``faults`` switches on deliberate misbehaviour for contract tests.
    """

    def __init__(self, spec: BrainSpec | None = None, *, faults=(), seen=None):
        self.spec = spec or BrainSpec(id='synthetic', label='Synthetic rule-based brain (test fixture)',
                                      locality='local', version='1',
                                      scopes=frozenset(SCOPE_CLASSES), tools=frozenset({'calculator'}),
                                      max_autonomy=2, pence_per_1k_tokens=0)
        if any(f not in FAULTS for f in faults):
            raise ValueError('unknown synthetic fault')
        self.faults = frozenset(faults)
        self.seen = seen  # A list to record exactly what the brain received, for tests.

    def run(self, packet, meter):
        if self.seen is not None:
            self.seen.append(copy.deepcopy(packet))
        if 'crash' in self.faults:
            meter.step()
            raise RuntimeError('synthetic crash')
        log, lines, citations, actions, suggestions = [], [], [], [], []

        def step(kind, summary, *, tool=None, cost=0):
            meter.step(tokens=cost)
            if 'slow_steps' in self.faults:
                time.sleep(0.05)
            log.append({'step': len(log) + 1, 'kind': kind, 'tool': tool, 'summary': summary[:200]})

        for item in packet['context']:
            step('read', f"Read excerpt {item['id']}", cost=tokens(item['text']))
            first = next((line.strip() for line in item['text'].splitlines() if line.strip()), None)
            if first:
                lines.append(f"{first[:300]} [{item['id']}]")
                citations.append({'ref': item['id'], 'quote': first[:300]})
            for line in item['text'].splitlines():
                found = SEND_EVERYTHING.search(line)
                if found:
                    if 'send_everything_as_draft' in self.faults:
                        actions.append({'capability': 'message.draft',
                                        'parameters': {'text': f'Send everything to {found.group(1)}'},
                                        'reason': 'The excerpt asked for it.', 'cites': [item['id']]})
                    else:
                        actions.append({'capability': 'message.send',
                                        'parameters': {'to': found.group(1), 'text': 'everything'},
                                        'reason': 'The excerpt asked for it.', 'cites': [item['id']]})
                remembered = REMEMBER.match(line)
                if remembered:
                    suggestions.append({'statement': remembered.group(1)[:400], 'cites': [item['id']]})
        for item in packet['learned']:
            step('read', f"Read learned statement {item['id']}", cost=tokens(item['statement']))
        for line in packet['instruction'].splitlines():
            drafted = DRAFT.match(line)
            if drafted:
                actions.append({'capability': 'message.draft', 'parameters': {'text': drafted.group(1)[:4000]},
                                'reason': 'The instruction asked for a draft.', 'cites': []})
        for tool in packet['tools']:
            step('tool', f'Used {tool}', tool=tool, cost=1)
        if 'unlisted_tool' in self.faults:
            step('tool', 'Used web.fetch', tool='web.fetch', cost=1)
        if 'runaway' in self.faults:
            while True:
                step('reason', 'Thinking again', cost=10)
        if 'stall' in self.faults:
            meter.step()
            time.sleep(5)
        answer = '\n'.join(lines) if lines else 'No excerpt was provided, so there is nothing to report.'
        if 'fabricate_citation' in self.faults:
            answer += ' [E9]'
            citations.append({'ref': 'E9', 'quote': 'A source that was never sent.'})
        if 'misquote' in self.faults and citations:
            citations[0] = {'ref': citations[0]['ref'], 'quote': citations[0]['quote'] + ' (paraphrased)'}
        step('write', 'Wrote the answer', cost=tokens(answer))
        content = '# Synthetic brain notes\n\n' + answer + '\n'
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
        if 'bad_artefact_hash' in self.faults:
            digest = hashlib.sha256(b'something else').hexdigest()
        bundle = {'bundle_version': BUNDLE_VERSION,
                  'answer': {'text': answer, 'citations': citations},
                  'artefacts': [{'name': 'notes.md', 'media_type': 'text/markdown', 'sha256': digest, 'content': content}],
                  'proposed_actions': actions, 'memory_suggestions': suggestions, 'work_log': log}
        if 'claim_extra_field' in self.faults:
            bundle['verified_done'] = True
        return bundle


# Hub: packet building, dispatch and ingestion --------------------------------

class BrainHub:
    """ALFRED's side of the plug, over a ``KnowledgeStore`` and its ``JobCoordinator``.

    ``submit`` builds and validates a packet from the caller's own permitted notes and
    accepted reviewed statements, asks ``BrainPolicy``, and submits a ``brain_task`` job.
    ``ingest`` validates a finished job's bundle against that packet and records what
    follows from it. Proposals, suggestions and results are private to the submitter.
    """

    def __init__(self, store, jobs: JobCoordinator, registry: BrainRegistry, policy: BrainPolicy, *,
                 workspace_scopes=None, gate=None):
        self.store, self.jobs, self.registry, self.policy = store, jobs, registry, policy
        # H2 (alfred.hub_goals.GoalHub attaches itself here): with a gate, every task must
        # serve a current mandate and fit its budgets, or it is refused before a job exists.
        self.gate = gate
        self.workspace_scopes = dict(workspace_scopes or {})
        if any(v not in SCOPE_CLASSES for v in self.workspace_scopes.values()):
            raise Fault('invalid_workspace_scopes')
        with store.connection() as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='brain_meta'").fetchone()
            versions = [r[0] for r in db.execute('SELECT version FROM brain_meta')] if exists else [1]
            if versions != [1]:
                raise Fault('unsupported_brain_version')
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')

    # Packet ------------------------------------------------------------

    def _excerpts(self, bearer, selections):
        if type(selections) is not list or len(selections) > MAX_EXCERPTS:
            raise Fault('invalid_context')
        context, total = [], 0
        for index, item in enumerate(selections, 1):
            _exact(item, {'note', 'start_line', 'end_line'}, 'invalid_context')
            if not isinstance(item['note'], str) or not NOTE_ID.fullmatch(item['note']):
                raise Fault('invalid_context')
            first = _int(item['start_line'], 1, 2**31, 'invalid_context')
            last = _int(item['end_line'], first, first + MAX_EXCERPT_LINES - 1, 'invalid_context')
            try:
                note = self.store.knowledge_note(bearer, item['note'], purpose='model')
            except Fault as exc:
                if exc.code == 'note_not_available':
                    raise Fault('context_denied', 403) from None
                raise
            lines = note['body'].splitlines()
            if last > len(lines):
                raise Fault('invalid_context')
            body = '\n'.join(lines[first - 1:last])
            if not body.strip():
                raise Fault('empty_excerpt')
            if len(body) > MAX_ONE_EXCERPT:
                raise Fault('excerpt_over_budget')
            total += len(body)
            if total > MAX_EXCERPT_CHARACTERS:
                raise Fault('context_over_budget')
            context.append({'id': f'E{index}', 'note_id': note['id'], 'title': note['title'],
                            'revision': note['revision'], 'sha256': note['sha256'],
                            'start_line': first, 'end_line': last, 'text': body, 'basis': EXCERPT_BASIS})
        return context

    def _learned(self, bearer, claim_ids):
        if type(claim_ids) is not list or len(claim_ids) > MAX_LEARNED or len(set(map(str, claim_ids))) != len(claim_ids):
            raise Fault('invalid_learned')
        if not claim_ids:
            return []
        for claim_id in claim_ids:
            ident(claim_id)
        # Owner-accepted learning records (H3, alfred/learning.py) travel in the same field,
        # their record ID in ``claim_id``; one that is not current is refused like a claim.
        from .learning import is_record_id, packet_statements
        records = packet_statements(self.store, bearer, [c for c in claim_ids if is_record_id(c)])
        claims, entities = {}, {}
        if len(records) < len(claim_ids):
            from .reviewed_memory import ReviewedMemory
            view = ReviewedMemory(self.store).view(bearer)
            entities = {e['id']: e for e in view['entities']}
            claims = {c['id']: c for c in view['claims']}
        learned, total = [], 0
        for index, claim_id in enumerate(claim_ids, 1):
            if claim_id in records:
                statement, version = records[claim_id]['statement'], records[claim_id]['version']
            else:
                claim = claims.get(claim_id)
                if not claim or not claim['usable']:
                    raise Fault('learned_not_usable', 409)
                other = entities[claim['object_id']]['name'] if claim['object_id'] else claim['value']
                statement = f"{entities[claim['subject_id']]['name']} {claim['predicate'].replace('_', ' ')} {other}"
                version = claim['version']
            total += len(statement)
            if total > MAX_LEARNED_CHARACTERS:
                raise Fault('learned_over_budget')
            learned.append({'id': f'L{index}', 'claim_id': claim_id, 'version': version,
                            'statement': statement[:600], 'basis': LEARNED_BASIS})
        return learned

    def build_packet(self, bearer, request) -> dict:
        """A validated packet from the caller's own permitted material. Sends nothing."""
        keys = {'task_id', 'goal', 'scope', 'instruction', 'context', 'learned', 'tools', 'budget', 'autonomy'}
        if type(request) is not dict or not keys | {'brain'} <= set(request) <= keys | {'brain', 'acceptance'}:
            raise Fault('invalid_fields')
        with self.store.connection() as db:
            principal = self.store.authenticate(db, bearer, {'owner'})
        expected = self.workspace_scopes.get(principal['scope'])
        if expected is not None and request['scope'] != expected:
            raise Fault('scope_class_mismatch', 403)
        packet = {'packet_version': PACKET_VERSION, 'task_id': request['task_id'], 'goal': request['goal'],
                  'scope': request['scope'], 'instruction': request['instruction'],
                  'context': self._excerpts(bearer, request['context']),
                  'learned': self._learned(bearer, request['learned']),
                  'tools': request['tools'], 'budget': request['budget'], 'autonomy': request['autonomy']}
        if 'acceptance' in request:
            from .verification import declare
            packet['acceptance'] = declare(request['acceptance'])
        return validate_packet(packet)

    def submit(self, bearer, request, *, binding=None) -> dict:
        """Build a packet, ask policy, and submit it as a ``brain_task`` job.

        ``binding`` names the mandate and kind of work the task serves; the gate, when one
        is attached, refuses a task without one or outside it."""
        if type(request) is not dict or 'brain' not in request:
            raise Fault('invalid_fields')
        packet = self.build_packet(bearer, request)
        brain = self.registry.get(request['brain'])
        self.policy.decide(brain.spec, packet)
        if self.gate is not None:
            self.gate.authorise(bearer, brain.spec, packet, binding)
        elif binding is not None:
            raise Fault('mandate_gate_not_configured', 409)
        notes = []
        for item in packet['context']:
            if not any(n['note'] == item['note_id'] for n in notes):
                notes.append({'note': item['note_id'], 'revision': item['revision']})
        job = self.jobs.submit(bearer, {'idempotency_key': packet['task_id'], 'kind': KIND,
                                        'parameters': {'brain': brain.spec.id, 'packet': packet},
                                        'inputs': notes, 'side_effect_free': True, 'max_attempts': 1})
        digest = packet_sha256(packet)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            prior = db.execute('SELECT * FROM brain_tasks WHERE job_id=?', (job['id'],)).fetchone()
            if prior is None:
                db.execute('INSERT INTO brain_tasks VALUES (?,?,?,?,?,?,?,?,?)',
                           (job['id'], p['scope'], p['id'], packet['task_id'], brain.spec.id, packet['scope'],
                            packet['autonomy'], digest, self.store.now()))
                self.store.log(db, p['scope'], p['id'], 'brain.task_submitted', job['id'])
                if self.gate is not None:
                    self.gate.bind(db, p, job, brain.spec, packet, binding)
            elif prior['packet_sha256'] != digest:
                raise Fault('idempotency_key_collision', 409)
        return {'job': job, 'packet_sha256': digest, 'brain': brain.spec.id, 'autonomy': AUTONOMY[packet['autonomy']]}

    # Ingestion ----------------------------------------------------------

    def _task(self, db, p, job_id):
        ident(job_id)
        row = db.execute('SELECT * FROM brain_tasks WHERE job_id=? AND scope=? AND actor=?',
                         (job_id, p['scope'], p['id'])).fetchone()
        if not row:
            raise Fault('not_found', 404)
        return row

    def _record(self, db, p, task, status, reason, envelope_sha, outcome):
        db.execute('INSERT INTO brain_results VALUES (?,?,?,?,?,?,?,?)',
                   (task['job_id'], p['scope'], p['id'], status, reason, envelope_sha, _compact(outcome), self.store.now()))
        self.store.log(db, p['scope'], p['id'], 'brain.result_' + status, task['job_id'])

    def ingest(self, bearer, job_id) -> dict:
        """Validate a finished job's bundle and record what follows. Idempotent."""
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            task = self._task(db, p, job_id)
            prior = db.execute('SELECT * FROM brain_results WHERE job_id=?', (job_id,)).fetchone()
            if prior:
                return self._result_view(db, prior)
        job = self.jobs.view(bearer, job_id)
        if not job['finished']:
            raise Fault('job_not_finished', 409)
        envelope, envelope_sha, refusal = None, None, None
        if job['state'] != 'succeeded':
            status, refusal = 'stopped', job['reason'] or job['state']
        else:
            artefact = self.jobs.artefact(bearer, job['result']['sha256'])
            envelope_sha = artefact['sha256']
            status, refusal, envelope = self._judge(task, job, artefact['data'])
        pending = {}
        if status == 'accepted' and task['autonomy'] == 2:
            pending = self._pending(bearer, task, envelope['bundle']['proposed_actions'])
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            task = self._task(db, p, job_id)
            prior = db.execute('SELECT * FROM brain_results WHERE job_id=?', (job_id,)).fetchone()
            if prior:
                return self._result_view(db, prior)
            outcome = {'job_state': job['state'], 'over_budget': bool(refusal and refusal.startswith('over_budget_')),
                       'autonomy': AUTONOMY[task['autonomy']], 'proposals': {}, 'suggestions': 0, 'answer': None,
                       'artefacts': [], 'metered': envelope['metered'] if envelope else None,
                       'basis': 'brain_claim_checked_for_citations_hashes_tools_budget_not_verified_true'}
            if status == 'accepted':
                bundle = envelope['bundle']
                outcome['answer'] = bundle['answer']
                outcome['artefacts'] = [{k: a[k] for k in ('name', 'media_type', 'sha256')} for a in bundle['artefacts']]
                outcome['proposals'] = self._proposals(db, p, task, bundle['proposed_actions'], pending)
                outcome['suggestions'] = self._suggestions(db, p, task, bundle['memory_suggestions'])
            self._record(db, p, task, status, refusal, envelope_sha, outcome)
            return self._result_view(db, db.execute('SELECT * FROM brain_results WHERE job_id=?', (job_id,)).fetchone())

    def _judge(self, task, job, data):
        """Returns (status, refusal, envelope) for a succeeded job's result bytes."""
        packet = job['parameters']['packet']
        if packet_sha256(packet) != task['packet_sha256']:
            return 'refused', 'packet_record_mismatch', None
        try:
            envelope = json.loads(data.decode('utf-8'))
            _exact(envelope, {'envelope_version', 'brain', 'brain_version', 'packet_sha256', 'metered', 'bundle', 'basis'},
                   'invalid_envelope')
            if envelope['envelope_version'] != ENVELOPE_VERSION or envelope['brain'] != task['brain']:
                raise Fault('invalid_envelope')
            if envelope['packet_sha256'] != task['packet_sha256']:
                return 'refused', 'packet_record_mismatch', None
            metered = _exact(envelope['metered'], set(METERED), 'invalid_envelope')
            validate_bundle(envelope['bundle'])
        except Fault as exc:
            return 'refused', exc.code, None
        except (UnicodeError, ValueError, RecursionError):
            return 'refused', 'invalid_envelope', None
        for name in METERED:
            if type(metered[name]) is not int or metered[name] > packet['budget'][name]:
                return 'refused', 'over_budget_' + name, None
        if packet['autonomy'] not in ENFORCED_AUTONOMY:
            return 'refused', PILOT_GATE_REASON, None
        refusal = check_bundle(packet, envelope['bundle'])
        if refusal:
            return 'refused', refusal, None
        return 'accepted', None, envelope

    @staticmethod
    def _proposal_id(task, position):
        return 'bp-' + hashlib.sha256(f"{task['job_id']}|{position}".encode()).hexdigest()[:24]

    def _pending(self, bearer, task, actions) -> dict:
        """Autonomy 2: each allowed proposal becomes an action through the existing
        ``LocalCore.propose``, bound to its exact parameters. It stays 'proposed': only
        ``LocalCore.approve`` with that exact fingerprint queues it. Returns, per position,
        (disposition, refusal, action_id)."""
        decided = {}
        for position, action in enumerate(actions):
            if action['capability'] not in PROPOSABLE:
                decided[position] = ('refused', 'capability_not_allowed_for_brains', None)
                continue
            action_id = 'act-' + self._proposal_id(task, position)
            with self.store.connection() as db:
                existing = db.execute('SELECT parameters FROM actions WHERE scope=? AND id=?',
                                      (task['scope'], action_id)).fetchone()
            if existing:  # An earlier, interrupted ingestion already proposed it.
                same = json.loads(existing['parameters']) == action['parameters']
                decided[position] = ('pending_approval', None, action_id) if same else ('refused', 'action_id_collision', None)
                continue
            try:
                self.store.propose(bearer, {'id': action_id, 'capability': action['capability'],
                                            'parameters': action['parameters'],
                                            'expires_at': self.store.now() + ACTION_TTL})
                decided[position] = ('pending_approval', None, action_id)
            except Fault as exc:
                decided[position] = ('refused', exc.code, None)
        return decided

    def _proposals(self, db, p, task, actions, pending) -> dict:
        counts = {}
        for position, action in enumerate(actions):
            pid = self._proposal_id(task, position)
            digest = hashlib.sha256(_compact({'capability': action['capability'],
                                              'parameters': action['parameters']}).encode()).hexdigest()
            parameters, refusal, action_id = _compact(action['parameters']), None, None
            if task['autonomy'] == 0:
                disposition, parameters = 'dropped_observe', None
            elif task['autonomy'] == 1:
                disposition = 'draft_only'
            else:
                disposition, refusal, action_id = pending[position]
            db.execute('INSERT INTO brain_proposals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (pid, task['job_id'], p['scope'], p['id'], position, action['capability'], parameters, digest,
                        action['reason'], _compact(action['cites']), disposition, refusal, action_id, self.store.now()))
            counts[disposition] = counts.get(disposition, 0) + 1
        return counts

    def _suggestions(self, db, p, task, suggestions) -> int:
        for position, item in enumerate(suggestions):
            sid = 'bs-' + hashlib.sha256(f"{task['job_id']}|{position}".encode()).hexdigest()[:24]
            db.execute('INSERT INTO brain_suggestions VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (sid, task['job_id'], p['scope'], p['id'], position, item['statement'], _compact(item['cites']),
                        'suggested', self.store.now(), None))
        return len(suggestions)

    # Views ----------------------------------------------------------------

    @staticmethod
    def _result_view(db, row) -> dict:
        return {'job': row['job_id'], 'status': row['status'], 'reason': row['reason'],
                'envelope_sha256': row['envelope_sha256'], **json.loads(row['outcome']),
                'authority_granted': False}

    def result(self, bearer, job_id) -> dict:
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            self._task(db, p, job_id)
            row = db.execute('SELECT * FROM brain_results WHERE job_id=?', (job_id,)).fetchone()
            if not row:
                raise Fault('not_ingested', 404)
            return self._result_view(db, row)

    def proposals(self, bearer) -> list:
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            return [{'id': r['id'], 'job': r['job_id'], 'position': r['position'], 'capability': r['capability'],
                     'parameters': json.loads(r['parameters']) if r['parameters'] else None,
                     'fingerprint': r['fingerprint'], 'reason': r['reason'], 'cites': json.loads(r['cites']),
                     'disposition': r['disposition'], 'refusal': r['refusal'], 'action_id': r['action_id'],
                     'executed': False}
                    for r in db.execute('SELECT * FROM brain_proposals WHERE scope=? AND actor=? ORDER BY created,job_id,position',
                                        (p['scope'], p['id']))]

    def suggestions(self, bearer) -> list:
        """The review inbox for brain memory suggestions. Nothing here is accepted."""
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            return [{'id': r['id'], 'job': r['job_id'], 'statement': r['statement'], 'cites': json.loads(r['cites']),
                     'state': r['state'], 'basis': 'brain_suggestion_needs_review_not_accepted'}
                    for r in db.execute('SELECT * FROM brain_suggestions WHERE scope=? AND actor=? ORDER BY created,job_id,position',
                                        (p['scope'], p['id']))]

    def dismiss_suggestion(self, bearer, suggestion_id) -> dict:
        ident(suggestion_id)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            row = db.execute('SELECT * FROM brain_suggestions WHERE id=? AND scope=? AND actor=?',
                             (suggestion_id, p['scope'], p['id'])).fetchone()
            if not row:
                raise Fault('not_found', 404)
            if row['state'] == 'suggested':
                db.execute("UPDATE brain_suggestions SET state='dismissed',decided=? WHERE id=?", (self.store.now(), suggestion_id))
                self.store.log(db, p['scope'], p['id'], 'brain.suggestion_dismissed', suggestion_id)
            return {'id': suggestion_id, 'state': 'dismissed'}


def action_current(store, db, row):
    """Approval and dispatch condition for an action a brain proposed at autonomy 2.

    Checked in the caller's transaction by ``KnowledgeStore.evidence_valid``, at
    approval and again at dispatch. The proposal must belong to the same person, its
    result must have been accepted, and every excerpt in the packet the brain was given
    must still be the same revision of a ready note the person may read. A changed,
    deleted or no longer permitted source fails the action closed.
    """
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='brain_proposals'").fetchone():
        return False
    link = db.execute("SELECT * FROM brain_proposals WHERE scope=? AND action_id=? AND disposition='pending_approval'",
                      (row['scope'], row['id'])).fetchone()
    if not link or link['actor'] != row['actor'] or row['capability'] not in PROPOSABLE:
        return False
    result = db.execute('SELECT status FROM brain_results WHERE job_id=? AND scope=? AND actor=?',
                        (link['job_id'], row['scope'], row['actor'])).fetchone()
    job = db.execute('SELECT parameters FROM jobs WHERE id=? AND scope=? AND actor=?',
                     (link['job_id'], row['scope'], row['actor'])).fetchone()
    if not result or result['status'] != 'accepted' or not job:
        return False
    packet = json.loads(job['parameters'])['packet']
    # H4: declared acceptance checks must have run, and none failed unless the owner
    # acknowledged the result (alfred.verification).
    from .verification import holds_effects
    if holds_effects(db, row['scope'], row['actor'], link['job_id'], packet):
        return False
    from .policy import permitted
    principal, now = {'scope': row['scope'], 'id': row['actor']}, store.now()
    for item in packet['context']:
        note = db.execute('''SELECT n.source,n.revision,n.sha256 FROM knowledge_notes n
            JOIN credentials c ON c.id=n.source AND c.scope=n.scope
            JOIN knowledge_sources s ON s.scope=n.scope AND s.source=n.source
            WHERE n.scope=? AND n.id=? AND n.status='ready' AND c.revoked=0 AND c.expires>?
            AND s.status IN ('ready','attention')''', (row['scope'], item['note_id'], now)).fetchone()
        if (not note or (note['revision'], note['sha256']) != (item['revision'], item['sha256'])
                or not permitted(db, principal, note['source'], now, 'read')):
            return False
    return True


def new_task_id(prefix='brain-task') -> str:
    return f'{prefix}-{secrets.token_hex(8)}'
