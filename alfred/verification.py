"""Independent verification of brain results (docs/AGENT_HUB.md, step H4).

A brain's result bundle is a claim. H1 (``alfred.brain``) already refuses a bundle whose
contract fails: unsent or misquoted citations, wrong artefact hashes, unlisted tools or
metered use over budget. This module adds the next gate: acceptance checks that the owner
(or, later, a mandate) declares in the task packet, run by ALFRED on the bytes the brain
returned, before a result may count as done.

Who declares the checks
    Only ALFRED's packet carries them, under ``acceptance``, built from the owner's
    request by ``BrainHub.build_packet`` (``declare`` fills defaults and numbers the
    checks C1, C2, ...). The result bundle has no field for them, so a brain cannot add,
    remove or weaken a check; the verifier reads the checks from the packet ALFRED
    recorded at submission (hash-checked), never from what the brain was given or said.

Check kinds (version 1), all deterministic, no model and no network
    claims_cited             every claim sentence in the answer carries a citation marker
                             to a sent excerpt whose quote is literal in that excerpt
    numbers_cited            every number in the answer appears literally in the text the
                             sentence cites (optionally: every number in the artefacts
                             appears somewhere in the sent material)
    artefact_sections        a Markdown artefact has the named headings (and, by default,
                             each has content)
    artefact_fields          a JSON artefact has the named fields (dotted paths)
    artefact_schema          a JSON artefact matches a declared schema (a small, strict
                             JSON Schema subset; an unsupported keyword is refused at
                             declaration rather than silently ignored)
    artefact_pattern         an artefact matches a declared regular expression, evaluated in
                             a separate, time-limited Python process
    no_out_of_scope_content  the brain's proposed drafts (optionally its answer and
                             artefacts) share no run of words with notes the person may
                             read that is not in the material sent for this task
    effect_readback          every effect the brain proposed (autonomy 2) was executed and
                             reads back exactly as proposed, through the same local draft
                             records the outbox verifies

Each check ends ``passed``, ``failed`` (with reasons) or ``unverifiable``. A check that
cannot run (an effect not yet executed, a result no longer readable, a pattern that ran
out of time, nothing to check) is ``unverifiable`` and never counts as passed.

Result states
    returned        the brain says it is done (its job succeeded and the bundle passed the
                    H1 contract); nothing has been verified. Also the state while some
                    declared check could not run and none failed.
    checked         every declared check passed. Needs at least one declared check.
    failed_checks   at least one check failed. Failure is sticky: a later run cannot
                    erase it. A bundle H1 refused is ``failed_checks`` (``bundle_contract``).
    acknowledged    the owner accepted the result, bound to the exact run they saw, and
                    explicitly over failed checks when there were any. A later run that
                    fails a check the owner did not accept ends the acknowledgement.

Only ``checked`` and ``acknowledged`` count as verified. The brain's answer text, work
log, artefacts, confidence or self-test output are never read as a status: a brain that
writes "verified_done" or pastes passing test output is exactly as unverified as one
that says nothing. A ``checked`` result is checked against these rules only; it is not
proof of truth or entailment.

Gate on effects
    ``holds_effects`` is consulted by ``alfred.brain.action_current`` at approval and
    again at dispatch. When the packet declared checks, a draft the brain proposed cannot
    be approved or dispatched until the checks have run, nor while any has failed unless
    the owner acknowledged the result. Results without declared checks keep H1 behaviour.

``outcomes`` is the small query routing statistics (H3) read: per result and per brain,
the check outcome (``checked``, ``failed_checks``, ``returned``, ``not_returned``) and
whether the owner acknowledged it. ``outcome_rows`` is the same reading inside a caller's
transaction, and ``evidence_class`` sorts each result into one routing evidence class:

    verified        checks were declared and all passed, or the owner acknowledged the
                    result, which had declared checks
    failed_checks   a declared check failed, or H1 refused the bundle (its contract, C0)
    unverifiable    checks were declared but could not run, or have not run yet
    no_checks       nothing was declared, so nothing was verified (even if acknowledged)
    not_returned    the job stopped without a result

Records are private to the person who submitted the task (``policy.ledger``: the person,
shared by all of that person's devices), as the job coordinator treats submitters.
"""
from __future__ import annotations
import copy
from dataclasses import dataclass
import hashlib
import json
import math
import re
import secrets
import subprocess
import sys

from . import brain as plug
from .evidence_review import NUMBER
from .local import Fault, ident, text
from .policy import ledger, person_credentials

VERSION = 1
ACCEPTANCE_VERSION = 1
REPORT_VERSION = 1
STATES = ('returned', 'checked', 'failed_checks', 'acknowledged')
OUTCOMES = ('returned', 'checked', 'failed_checks')
VERIFIED = ('checked', 'acknowledged')
EVIDENCE = ('verified', 'failed_checks', 'unverifiable', 'no_checks', 'not_returned')
CHECK_STATUSES = ('passed', 'failed', 'unverifiable')
# Who started a run. Both are judged and counted the same; runs from before this field read as 'owner'.
INITIATORS = ('automatic', 'owner')
DECLARERS = ('owner', 'mandate')
MAX_CHECKS, MAX_ACCEPTANCE_BYTES, MAX_REASONS = 8, 4096, 20
BASIS = 'deterministic_checks_on_returned_bytes_not_truth_or_entailment'
LIMITS = ('Deterministic checks only. A passed check means the returned bytes meet the declared rule; it does not '
          'show that a claim is true or follows from its source, that a section says anything useful, or that '
          'nothing else was wrong. Brain statements about completion, confidence or self-tests are never counted.')
REQUIRED = object()
KINDS = {
    'claims_cited': {'refs': 'excerpts', 'min_words': 3},
    'numbers_cited': {'against': 'excerpt', 'targets': ['answer']},
    'artefact_sections': {'artefact': REQUIRED, 'sections': REQUIRED, 'non_empty': True},
    'artefact_fields': {'artefact': REQUIRED, 'fields': REQUIRED, 'non_empty': True},
    'artefact_schema': {'artefact': REQUIRED, 'schema': REQUIRED},
    'artefact_pattern': {'artefact': REQUIRED, 'pattern': REQUIRED, 'mode': 'search', 'flags': ''},
    'no_out_of_scope_content': {'targets': ['drafts'], 'min_words': 8},
    'effect_readback': {},
}
FIELD_PATH = re.compile(r'[A-Za-z0-9_-]{1,64}(?:\.[A-Za-z0-9_-]{1,64}){0,7}')
SCHEMA_KEYWORDS = frozenset({'type', 'properties', 'required', 'additionalProperties', 'items', 'enum',
                             'minLength', 'maxLength', 'minimum', 'maximum', 'minItems', 'maxItems'})
SCHEMA_TYPES = ('object', 'array', 'string', 'integer', 'number', 'boolean', 'null')
MAX_SCHEMA_DEPTH, MAX_SCHEMA_BYTES = 8, 2048
PATTERN_FLAGS = 'ims'
MAX_PATTERN = 200
SENTENCE_END = re.compile(r'(?<=[.!?])\s+')
WORD = re.compile(r'\w+')
FENCE = re.compile(r' {0,3}(`{3,}|~{3,})')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS verification_meta(version INTEGER NOT NULL);
INSERT INTO verification_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM verification_meta);
CREATE TABLE IF NOT EXISTS verification_runs(
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES brain_tasks(job_id), scope TEXT NOT NULL, actor TEXT NOT NULL,
 position INTEGER NOT NULL, outcome TEXT NOT NULL, report TEXT NOT NULL, report_sha256 TEXT NOT NULL,
 created INTEGER NOT NULL, initiated TEXT CHECK(initiated IS NULL OR initiated IN ('automatic','owner')),
 UNIQUE(job_id,position), CHECK(outcome IN ('returned','checked','failed_checks')));
CREATE TRIGGER IF NOT EXISTS verification_runs_no_update BEFORE UPDATE ON verification_runs
 BEGIN SELECT RAISE(ABORT,'verification_runs_append_only'); END;
CREATE TABLE IF NOT EXISTS verification_results(
 job_id TEXT PRIMARY KEY REFERENCES brain_tasks(job_id), scope TEXT NOT NULL, actor TEXT NOT NULL,
 brain TEXT NOT NULL, state TEXT NOT NULL, failed TEXT NOT NULL, passed_complete INTEGER NOT NULL,
 runs INTEGER NOT NULL, last_run TEXT NOT NULL REFERENCES verification_runs(id), last_run_sha256 TEXT NOT NULL,
 acknowledged_run TEXT, acknowledged_over TEXT, acknowledged_failed TEXT, acknowledged_at INTEGER,
 created INTEGER NOT NULL, updated INTEGER NOT NULL,
 CHECK(state IN ('returned','checked','failed_checks','acknowledged')),
 CHECK(acknowledged_over IS NULL OR acknowledged_over IN ('returned','checked','failed_checks')));
'''

# The pattern check runs here, in a separate isolated interpreter, so a pattern that
# backtracks badly on returned text can be stopped. It gets the pattern and text only.
PATTERN_CHILD = '''
import json, re, sys
try:
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (536870912, 536870912))
except Exception:
    pass
job = json.loads(sys.stdin.read())
flags = 0
for flag in job["flags"]:
    flags |= {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL}[flag]
expression = re.compile(job["pattern"], flags)
test = expression.fullmatch if job["mode"] == "fullmatch" else expression.search
sys.stdout.write("match" if test(job["text"]) else "no_match")
'''


def _compact(value) -> str:
    return plug._compact(value)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _table(db, name) -> bool:
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


# Declaration ------------------------------------------------------------------

def declare(value) -> dict:
    """The packet's ``acceptance`` from an owner's (or mandate's) request.

    The request names each check's ``kind`` and any parameters; defaults are filled and
    checks are numbered C1, C2, ... in order. Shape and limits are then enforced by
    ``validate_acceptance`` when the packet is validated.
    """
    if type(value) is not dict or not {'checks'} <= set(value) <= {'declared_by', 'ref', 'checks'}:
        raise Fault('invalid_acceptance')
    checks = value['checks']
    if type(checks) is not list or not 1 <= len(checks) <= MAX_CHECKS:
        raise Fault('invalid_acceptance')
    declared = []
    for index, item in enumerate(checks, 1):
        if type(item) is not dict or item.get('kind') not in KINDS:
            raise Fault('unknown_check_kind')
        spec = KINDS[item['kind']]
        if set(item) - {'kind'} - set(spec):
            raise Fault('invalid_check')
        check = {'id': f'C{index}', 'kind': item['kind']}
        for name, default in spec.items():
            if name in item:
                check[name] = copy.deepcopy(item[name])
            elif default is REQUIRED:
                raise Fault('invalid_check')
            else:
                check[name] = copy.deepcopy(default)
        declared.append(check)
    return {'version': ACCEPTANCE_VERSION, 'declared_by': value.get('declared_by', 'owner'),
            'ref': value.get('ref'), 'checks': declared}


def _choice(value, options, code):
    if not isinstance(value, str) or value not in options:
        raise Fault(code)
    return value


def _subset(value, options, code):
    if (type(value) is not list or not value or len(set(map(str, value))) != len(value)
            or any(not isinstance(v, str) or v not in options for v in value)):
        raise Fault(code)
    return value


def _bool(value, code):
    if type(value) is not bool:
        raise Fault(code)
    return value


def _number(value):
    return type(value) in (int, float) and not (type(value) is float and not math.isfinite(value))


def validate_schema(schema, depth=0):
    """Accept only the supported JSON Schema subset, so no rule is silently ignored."""
    if depth > MAX_SCHEMA_DEPTH:
        raise Fault('schema_too_deep')
    if type(schema) is not dict or not schema:
        raise Fault('invalid_schema')
    if set(schema) - SCHEMA_KEYWORDS:
        raise Fault('schema_keyword_not_supported')
    if 'type' in schema:
        kinds = [schema['type']] if isinstance(schema['type'], str) else schema['type']
        if (type(kinds) is not list or not kinds or len(set(map(str, kinds))) != len(kinds)
                or any(k not in SCHEMA_TYPES for k in kinds)):
            raise Fault('invalid_schema')
    if 'properties' in schema:
        properties = schema['properties']
        if type(properties) is not dict or len(properties) > 64:
            raise Fault('invalid_schema')
        for name, inner in properties.items():
            if not isinstance(name, str) or not 1 <= len(name) <= 64:
                raise Fault('invalid_schema')
            validate_schema(inner, depth + 1)
    if 'required' in schema:
        required = schema['required']
        if (type(required) is not list or len(required) > 64 or len(set(map(str, required))) != len(required)
                or any(not isinstance(n, str) or not 1 <= len(n) <= 64 for n in required)):
            raise Fault('invalid_schema')
    if 'additionalProperties' in schema:
        _bool(schema['additionalProperties'], 'invalid_schema')
    if 'items' in schema:
        validate_schema(schema['items'], depth + 1)
    if 'enum' in schema:
        options = schema['enum']
        if type(options) is not list or not 1 <= len(options) <= 32 or any(
                not (v is None or type(v) in (str, bool) or _number(v)) for v in options):
            raise Fault('invalid_schema')
    for name in ('minLength', 'maxLength', 'minItems', 'maxItems'):
        if name in schema and (type(schema[name]) is not int or not 0 <= schema[name] <= 1_000_000):
            raise Fault('invalid_schema')
    for name in ('minimum', 'maximum'):
        if name in schema and not _number(schema[name]):
            raise Fault('invalid_schema')
    return schema


def _compile(pattern, flags):
    if not isinstance(pattern, str) or not 1 <= len(pattern) <= MAX_PATTERN or '\x00' in pattern:
        raise Fault('invalid_pattern')
    if not isinstance(flags, str) or len(set(flags)) != len(flags) or not set(flags) <= set(PATTERN_FLAGS):
        raise Fault('invalid_pattern_flags')
    try:
        re.compile(pattern)  # Compiling is cheap and safe; matching returned text runs in a child process.
    except (re.error, RecursionError, OverflowError):
        raise Fault('invalid_pattern') from None
    return pattern


def validate_acceptance(acceptance, packet):
    """Return the declaration unchanged if it satisfies acceptance version 1, else raise."""
    plug._exact(acceptance, {'version', 'declared_by', 'ref', 'checks'}, 'invalid_acceptance')
    if type(acceptance['version']) is not int or acceptance['version'] != ACCEPTANCE_VERSION:
        raise Fault('unsupported_acceptance_version')
    _choice(acceptance['declared_by'], DECLARERS, 'invalid_acceptance_declarer')
    if acceptance['declared_by'] == 'owner':
        if acceptance['ref'] is not None:
            raise Fault('invalid_acceptance')
    else:
        ident(acceptance['ref'])
    checks = acceptance['checks']
    if type(checks) is not list or not 1 <= len(checks) <= MAX_CHECKS:
        raise Fault('invalid_acceptance')
    for index, check in enumerate(checks, 1):
        if type(check) is not dict or check.get('kind') not in KINDS:
            raise Fault('unknown_check_kind')
        plug._exact(check, {'id', 'kind'} | set(KINDS[check['kind']]), 'invalid_check')
        if check['id'] != f'C{index}':
            raise Fault('invalid_check_id')
        kind = check['kind']
        if 'artefact' in check and (not isinstance(check['artefact'], str) or not plug.ARTEFACT_NAME.fullmatch(check['artefact'])):
            raise Fault('invalid_check')
        if kind == 'claims_cited':
            _choice(check['refs'], ('excerpts', 'excerpts_or_learned'), 'invalid_check')
            plug._int(check['min_words'], 1, 12, 'invalid_check')
        elif kind == 'numbers_cited':
            _choice(check['against'], ('excerpt', 'quote'), 'invalid_check')
            _subset(check['targets'], ('answer', 'artefacts'), 'invalid_check')
        elif kind == 'artefact_sections':
            sections = check['sections']
            if type(sections) is not list or not 1 <= len(sections) <= 16:
                raise Fault('invalid_check')
            for name in sections:
                if not text(name, 120).strip():
                    raise Fault('invalid_check')
            if len({_heading_key(n) for n in sections}) != len(sections):
                raise Fault('invalid_check')
            _bool(check['non_empty'], 'invalid_check')
        elif kind == 'artefact_fields':
            fields = check['fields']
            if (type(fields) is not list or not 1 <= len(fields) <= 32 or len(set(map(str, fields))) != len(fields)
                    or any(not isinstance(f, str) or not FIELD_PATH.fullmatch(f) for f in fields)):
                raise Fault('invalid_check')
            _bool(check['non_empty'], 'invalid_check')
        elif kind == 'artefact_schema':
            validate_schema(check['schema'])
            if len(_compact(check['schema'])) > MAX_SCHEMA_BYTES:
                raise Fault('schema_too_large')
        elif kind == 'artefact_pattern':
            _compile(check['pattern'], check['flags'])
            _choice(check['mode'], ('search', 'fullmatch'), 'invalid_check')
        elif kind == 'no_out_of_scope_content':
            _subset(check['targets'], ('drafts', 'answer', 'artefacts'), 'invalid_check')
            plug._int(check['min_words'], 5, 40, 'invalid_check')
        elif kind == 'effect_readback' and packet.get('autonomy') != 2:
            # Only autonomy 2 turns a proposal into an action that can be executed and read back.
            raise Fault('readback_needs_autonomy_two')
    if len(_compact(acceptance)) > MAX_ACCEPTANCE_BYTES:
        raise Fault('acceptance_too_large')
    return acceptance


# Text helpers --------------------------------------------------------------------

def sentences(answer) -> list:
    """The answer's sentences, each with the citation markers it carries.

    Deterministic and conservative: lines are split after '.', '!' or '?' followed by
    space, and a segment holding only markers belongs to the sentence before it (so
    "Due on Friday. [E1]" is one cited sentence). An abbreviation can split a sentence;
    the fragment then counts as uncited, which fails rather than passes.
    """
    found = []
    for line in answer.splitlines():
        for part in SENTENCE_END.split(line):
            refs = plug.MARKER.findall(part)
            bare = plug.MARKER.sub(' ', part)
            words = WORD.findall(bare)
            if not words:
                if refs and found:
                    found[-1]['refs'].extend(r for r in dict.fromkeys(refs) if r not in found[-1]['refs'])
                continue
            found.append({'index': len(found) + 1, 'text': ' '.join(bare.split()), 'words': len(words),
                          'refs': list(dict.fromkeys(refs))})
    return found


def _is_claim(sentence, min_words) -> bool:
    return sentence['words'] >= min_words or any(c.isdigit() for c in sentence['text'])


def _numbers(value) -> list:
    return list(dict.fromkeys(NUMBER.findall(value)))


def _heading_key(name) -> str:
    return ' '.join(name.split()).casefold()


def _headings(content):
    """Markdown ATX headings outside fenced code: (line index, level, title)."""
    lines, found, fence = content.splitlines(), [], None
    for index, line in enumerate(lines):
        opening = FENCE.match(line)
        if fence:
            if opening and opening.group(1)[0] == fence[0] and len(opening.group(1)) >= len(fence):
                fence = None
            continue
        if opening:
            fence = opening.group(1)
            continue
        heading = _heading(line)
        if heading:
            found.append((index, *heading))
    return lines, found


def _heading(line):
    """(level, title) for an ATX heading line, else None. Plain string steps, no
    backtracking regular expression over returned text."""
    stripped = line.lstrip(' ')
    if len(line) - len(stripped) > 3 or not stripped.startswith('#'):
        return None
    level = len(stripped) - len(stripped.lstrip('#'))
    rest = stripped[level:]
    if level > 6 or (rest and rest[0] not in ' \t'):
        return None
    title = rest.strip(' \t')
    closing = title.rstrip('#')
    if closing != title and (not closing or closing[-1] in ' \t'):
        title = closing.rstrip(' \t')
    return level, title


def _strict_json(content):
    def pairs(items):
        keys = [k for k, _ in items]
        if len(set(keys)) != len(keys):
            raise ValueError('duplicate key')
        return dict(items)

    def constant(_):
        raise ValueError('constant')
    return json.loads(content, object_pairs_hook=pairs, parse_constant=constant)


def _json_type(value) -> str:
    if value is None:
        return 'null'
    if type(value) is bool:
        return 'boolean'
    if type(value) is int:
        return 'integer'
    if type(value) is float:
        return 'number'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, list):
        return 'array'
    return 'object'


def _same(left, right) -> bool:
    if _json_type(left) in ('integer', 'number') and _json_type(right) in ('integer', 'number'):
        return left == right
    return _json_type(left) == _json_type(right) and left == right


def _pointer(path, key) -> str:
    return path + '/' + str(key).replace('~', '~0').replace('/', '~1')


def schema_errors(schema, value, path='', errors=None) -> list:
    """Ways ``value`` breaks ``schema`` as JSON-pointer-located codes, stopping one past
    ``MAX_REASONS`` so a caller can tell the list was cut short."""
    errors = [] if errors is None else errors
    if len(errors) > MAX_REASONS:
        return errors
    where = path or '/'
    if 'type' in schema:
        kinds = [schema['type']] if isinstance(schema['type'], str) else schema['type']
        actual = _json_type(value)
        if not any(actual == k or (k == 'number' and actual == 'integer') for k in kinds):
            errors.append({'code': 'schema_type', 'path': where, 'expected': kinds, 'found': actual})
            return errors
    if 'enum' in schema and not any(_same(value, option) for option in schema['enum']):
        errors.append({'code': 'schema_enum', 'path': where})
    if isinstance(value, str):
        if len(value) < schema.get('minLength', 0):
            errors.append({'code': 'schema_min_length', 'path': where})
        if 'maxLength' in schema and len(value) > schema['maxLength']:
            errors.append({'code': 'schema_max_length', 'path': where})
    if _json_type(value) in ('integer', 'number'):
        if 'minimum' in schema and value < schema['minimum']:
            errors.append({'code': 'schema_minimum', 'path': where})
        if 'maximum' in schema and value > schema['maximum']:
            errors.append({'code': 'schema_maximum', 'path': where})
    if isinstance(value, list):
        if len(value) < schema.get('minItems', 0):
            errors.append({'code': 'schema_min_items', 'path': where})
        if 'maxItems' in schema and len(value) > schema['maxItems']:
            errors.append({'code': 'schema_max_items', 'path': where})
        if 'items' in schema:
            for index, item in enumerate(value):
                schema_errors(schema['items'], item, _pointer(path, index), errors)
    if isinstance(value, dict):
        for name in schema.get('required', []):
            if name not in value:
                errors.append({'code': 'schema_required', 'path': _pointer(path, name)})
        properties = schema.get('properties', {})
        for name, item in value.items():
            if name in properties:
                schema_errors(properties[name], item, _pointer(path, name), errors)
            elif schema.get('additionalProperties') is False:
                errors.append({'code': 'schema_additional_property', 'path': _pointer(path, name)})
    return errors


def _tokens(value) -> list:
    return [m.group(0).casefold() for m in WORD.finditer(value)]


def _shingles(tokens, size) -> set:
    return {tuple(tokens[i:i + size]) for i in range(len(tokens) - size + 1)}


def _strings(value):
    """Every string value inside proposed action parameters (keys excluded)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


# Gate helpers used inside other modules' transactions -----------------------------

def _row(db, scope, actor, job_id):
    if not _table(db, 'verification_results'):
        return None
    return db.execute('SELECT * FROM verification_results WHERE job_id=? AND scope=? AND actor=?',
                      (job_id, scope, actor)).fetchone()


def holds_effects(db, scope, actor, job_id, packet) -> bool:
    """True when a brain's proposed effect must wait: the packet declared acceptance
    checks and they have not run yet, or a check failed and the owner has not
    acknowledged the result. A packet without declared checks is never held here."""
    if 'acceptance' not in packet:
        return False
    row = _row(db, scope, actor, job_id)
    if row is None:
        return True
    return row['state'] == 'failed_checks'


def is_verified(db, scope, actor, job_id) -> bool:
    """Only ALFRED's checks or the owner's acknowledgement verify a result."""
    row = _row(db, scope, actor, job_id)
    return bool(row and row['state'] in VERIFIED)


def _checks_outcome(failed, complete) -> str:
    return 'failed_checks' if failed else 'checked' if complete else 'returned'


def submitters(db, p) -> list:
    """Every credential that names the caller's person: results are the person's, not one device's."""
    return sorted(person_credentials(db, ledger(db, p)) | {p['id']})


def _declared(parameters) -> int:
    """How many acceptance checks ALFRED's recorded packet declared. Never the bundle."""
    try:
        acceptance = json.loads(parameters)['packet'].get('acceptance')
        return len(acceptance['checks']) if acceptance else 0
    except (TypeError, KeyError, ValueError, AttributeError):
        return 0


def evidence_class(contract, declared, state, failed) -> str:
    """One routing evidence class per result, from ALFRED's records only.

    A result counts as verified only when checks were declared and they all passed, or the
    owner acknowledged it. A result with no declared checks is never verified, whatever
    else happened to it. The brain's own words are never read here.
    """
    if contract == 'stopped':
        return 'not_returned'
    if contract == 'refused':
        return 'failed_checks'  # The H1 bundle contract (C0) is ALFRED's check too.
    if not declared:
        return 'no_checks'
    if state in VERIFIED:
        return 'verified'
    if failed:
        return 'failed_checks'
    return 'unverifiable'


def outcome_rows(db, scope, actors, *, brain=None, since=None, limit=None) -> list:
    """Value-free verification rows for the brain results of the given credentials, oldest
    first (the newest ``limit`` when one is given).

    Runs inside the caller's transaction. Each row carries identifiers, states, counts and
    times only: never an answer, artefact, citation or anything the brain said.
    """
    if not actors or not _table(db, 'brain_results') or not _table(db, 'brain_tasks'):
        return []
    verification = _table(db, 'verification_results')
    columns = ('v.state,v.failed,coalesce(v.passed_complete,0) AS passed_complete,coalesce(v.runs,0) AS runs,'
               'v.acknowledged_over,v.updated' if verification
               else 'NULL AS state,NULL AS failed,0 AS passed_complete,0 AS runs,NULL AS acknowledged_over,NULL AS updated')
    join = 'LEFT JOIN verification_results v ON v.job_id=t.job_id' if verification else ''
    jobs = _table(db, 'jobs')
    rows = db.execute(
        f'''SELECT t.job_id,t.brain,t.task_id,t.scope_class,t.actor,r.status,r.reason,r.created AS ingested,
            {'j.parameters' if jobs else 'NULL AS parameters'},{columns}
            FROM brain_tasks t JOIN brain_results r ON r.job_id=t.job_id {join} {'LEFT JOIN jobs j ON j.id=t.job_id' if jobs else ''}
            WHERE t.scope=? AND t.actor IN ({','.join('?' * len(actors))}) AND (? IS NULL OR t.brain=?)
            AND (? IS NULL OR r.created>=?) ORDER BY r.created DESC,t.job_id DESC LIMIT ?''',
        (scope, *actors, brain, brain, since, since, -1 if limit is None else limit)).fetchall()[::-1]
    found = []
    for row in rows:
        failed = json.loads(row['failed']) if row['failed'] else []
        declared = _declared(row['parameters'])
        if row['status'] == 'stopped':
            checks = state = 'not_returned'
        elif row['state'] is None:
            checks = state = 'failed_checks' if row['status'] == 'refused' else 'returned'
        else:
            checks, state = _checks_outcome(failed, row['passed_complete']), row['state']
        found.append({'job': row['job_id'], 'brain': row['brain'], 'task_id': row['task_id'],
                      'scope_class': row['scope_class'], 'actor': row['actor'], 'contract': row['status'],
                      'reason': row['reason'], 'ingested_at': row['ingested'], 'declared': declared, 'checks': checks,
                      'state': state, 'verified': state in VERIFIED, 'acknowledged_over': row['acknowledged_over'],
                      'runs': row['runs'], 'updated_at': row['updated'],
                      'evidence': evidence_class(row['status'], declared, row['state'], failed)})
    return found


def outcomes(store, bearer, *, brain=None) -> dict:
    """Verification outcomes of the caller's brain results, for routing statistics (H3).

    ``checks`` is what ALFRED's checks established (``checked``, ``failed_checks``,
    ``returned`` when nothing was established, ``not_returned`` when the job stopped
    without a result). ``state`` adds the owner's acknowledgement. ``evidence`` is the
    routing evidence class (``EVIDENCE``). None of them ever comes from a brain's own claims.
    """
    if brain is not None:
        ident(brain)
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner'})
        rows = outcome_rows(db, p['scope'], submitters(db, p), brain=brain)
    results, by_brain, evidence = [], {}, {}
    for row in rows:
        results.append({k: row[k] for k in ('job', 'brain', 'task_id', 'ingested_at', 'contract', 'checks', 'state',
                                            'verified', 'acknowledged_over', 'runs', 'updated_at', 'declared', 'evidence')})
        counts = by_brain.setdefault(row['brain'], {'results': 0, 'checked': 0, 'failed_checks': 0, 'returned': 0,
                                                     'not_returned': 0, 'acknowledged': 0, 'verified': 0})
        counts['results'] += 1
        counts[row['checks']] += 1
        counts['acknowledged'] += row['state'] == 'acknowledged'
        counts['verified'] += row['verified']
        classes = evidence.setdefault(row['brain'], {'results': 0, **dict.fromkeys(EVIDENCE, 0)})
        classes['results'] += 1
        classes[row['evidence']] += 1
    return {'results': results, 'by_brain': by_brain, 'evidence_by_brain': evidence, 'basis': BASIS,
            'brain_claims_counted': False, 'no_checks_counted_as_verified': False}


# Verifier -------------------------------------------------------------------------

@dataclass
class _Context:
    bearer: str
    scope: str
    actor: str
    job_id: str
    packet: dict
    bundle: dict | None
    missing: str | None
    proposals: list

    @property
    def sent(self) -> dict:
        items = {item['id']: item['text'] for item in self.packet['context']}
        items.update({item['id']: item['statement'] for item in self.packet['learned']})
        return items

    def quotes(self) -> dict:
        """Per sent reference, the answer's citation quotes that are literally in it."""
        sent, found = self.sent, {}
        for item in self.bundle['answer']['citations']:
            if item['ref'] in sent and item['quote'] in sent[item['ref']]:
                found.setdefault(item['ref'], []).append(item['quote'])
        return found


def _result(status, reasons=(), **detail) -> dict:
    reasons = list(reasons)
    return {'status': status, 'reasons': reasons[:MAX_REASONS], 'truncated': len(reasons) > MAX_REASONS, 'detail': detail}


class Verifier:
    """ALFRED's verifier for brain results, over a ``BrainHub`` (its store and jobs).

    ``verify`` runs the packet's declared checks on the ingested result and records an
    append-only run; ``acknowledge`` records the owner accepting a result, bound to the
    exact run they saw; ``state`` reads the current position; ``outcomes`` is the query
    for routing statistics.
    """

    def __init__(self, hub, *, pattern_seconds=2.0):
        if type(pattern_seconds) not in (int, float) or not 0.1 <= pattern_seconds <= 10:
            raise Fault('invalid_pattern_seconds')
        self.hub, self.store, self.jobs = hub, hub.store, hub.jobs
        self.pattern_seconds = float(pattern_seconds)
        with self.store.connection() as db:
            versions = [r[0] for r in db.execute('SELECT version FROM verification_meta')] if _table(db, 'verification_meta') else [VERSION]
            if versions != [VERSION]:
                raise Fault('unsupported_verification_version')
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
            if 'initiated' not in {r[1] for r in db.execute('PRAGMA table_info(verification_runs)')}:
                # Additive: runs recorded before automatic verification read as the owner's.
                db.executescript("BEGIN IMMEDIATE;\nALTER TABLE verification_runs ADD COLUMN initiated TEXT "
                                 "CHECK(initiated IS NULL OR initiated IN ('automatic','owner'));\nCOMMIT;")

    # Reading what was sent and returned ------------------------------------------

    @staticmethod
    def _submitted(db, p, job_id):
        """The brain task, if the caller's person submitted it (from any of their devices).
        Anyone else is told it does not exist."""
        ident(job_id)
        actors = submitters(db, p)
        row = db.execute(f'''SELECT * FROM brain_tasks WHERE job_id=? AND scope=?
            AND actor IN ({','.join('?' * len(actors))})''', (job_id, p['scope'], *actors)).fetchone()
        if not row:
            raise Fault('not_found', 404)
        return row

    def _bundle(self, bearer, job, result, task):
        """The bundle ALFRED ingested, re-read through the coordinator, or (None, reason)."""
        if not job['result'] or job['result']['sha256'] != result['envelope_sha256']:
            return None, 'result_not_available'
        try:
            data = self.jobs.artefact(bearer, result['envelope_sha256'])['data']
        except Fault:
            return None, 'result_not_available'
        try:
            envelope = json.loads(bytes(data).decode('utf-8'))
            if type(envelope) is not dict or envelope.get('packet_sha256') != task['packet_sha256']:
                return None, 'result_not_readable'
            plug.validate_bundle(envelope['bundle'])
        except (Fault, KeyError, UnicodeError, ValueError, RecursionError):
            return None, 'result_not_readable'
        return envelope['bundle'], None

    def _artefact(self, ctx, name):
        return next((a for a in ctx.bundle['artefacts'] if a['name'] == name), None)

    # Checks ------------------------------------------------------------------------

    def _claims_cited(self, check, ctx):
        allowed = ('E',) if check['refs'] == 'excerpts' else ('E', 'L')
        quotes, reasons, claims = ctx.quotes(), [], 0
        found = sentences(ctx.bundle['answer']['text'])
        for sentence in found:
            if not _is_claim(sentence, check['min_words']):
                continue
            claims += 1
            if not sentence['refs']:
                reasons.append({'code': 'claim_without_citation', 'sentence': sentence['index']})
            elif not any(r[0] in allowed and r in quotes for r in sentence['refs']):
                reasons.append({'code': 'claim_without_literal_excerpt_citation', 'sentence': sentence['index'],
                                'refs': sentence['refs']})
        if not claims:
            # Nothing was claimed, so the rule established nothing about this answer.
            return _result('unverifiable', [{'code': 'no_claim_sentences'}], sentences=len(found), claims=0)
        return _result('failed' if reasons else 'passed', reasons, sentences=len(found), claims=claims)

    def _numbers_cited(self, check, ctx):
        reasons, counted, sent = [], 0, ctx.sent
        if 'answer' in check['targets']:
            quotes = ctx.quotes()
            for sentence in sentences(ctx.bundle['answer']['text']):
                numbers = _numbers(sentence['text'])
                if not numbers:
                    continue
                refs = [r for r in sentence['refs'] if r in sent]
                if check['against'] == 'quote':
                    evidence = '\n'.join(q for r in refs for q in quotes.get(r, []))
                else:
                    evidence = '\n'.join(sent[r] for r in refs)
                available = set(NUMBER.findall(evidence))
                for number in numbers:
                    counted += 1
                    if not refs:
                        reasons.append({'code': 'number_without_citation', 'sentence': sentence['index'], 'number': number})
                    elif number not in available:
                        reasons.append({'code': 'number_not_in_cited_text', 'sentence': sentence['index'],
                                        'number': number, 'refs': refs})
        if 'artefacts' in check['targets']:
            available = set(NUMBER.findall('\n'.join(sent.values())))
            for artefact in ctx.bundle['artefacts']:
                for number in _numbers(plug.MARKER.sub(' ', artefact['content'])):
                    counted += 1
                    if number not in available:
                        reasons.append({'code': 'number_not_in_sent_material', 'artefact': artefact['name'], 'number': number})
        return _result('failed' if reasons else 'passed', reasons, numbers=counted)

    def _artefact_sections(self, check, ctx):
        artefact = self._artefact(ctx, check['artefact'])
        if artefact is None:
            return _result('failed', [{'code': 'artefact_missing', 'artefact': check['artefact']}])
        if artefact['media_type'] not in ('text/markdown', 'text/plain'):
            return _result('failed', [{'code': 'artefact_not_text', 'artefact': check['artefact']}])
        lines, headings = _headings(artefact['content'])
        positions = {index for index, _, _ in headings}
        reasons = []
        for name in check['sections']:
            matches = [(i, h) for i, h in enumerate(headings) if _heading_key(h[2]) == _heading_key(name)]
            if not matches:
                reasons.append({'code': 'section_missing', 'section': name})
                continue
            if not check['non_empty']:
                continue
            filled = False
            for order, (line, level, _) in matches:
                end = next((h[0] for h in headings[order + 1:] if h[1] <= level), len(lines))
                if any(lines[n].strip() and n not in positions for n in range(line + 1, end)):
                    filled = True
                    break
            if not filled:
                reasons.append({'code': 'section_empty', 'section': name})
        return _result('failed' if reasons else 'passed', reasons, headings=len(headings))

    def _json_artefact(self, check, ctx):
        artefact = self._artefact(ctx, check['artefact'])
        if artefact is None:
            return None, _result('failed', [{'code': 'artefact_missing', 'artefact': check['artefact']}])
        try:
            return _strict_json(artefact['content']), None
        except (ValueError, RecursionError):
            return None, _result('failed', [{'code': 'artefact_not_json', 'artefact': check['artefact']}])

    def _artefact_fields(self, check, ctx):
        value, refusal = self._json_artefact(check, ctx)
        if refusal:
            return refusal
        if not isinstance(value, dict):
            return _result('failed', [{'code': 'artefact_not_json_object', 'artefact': check['artefact']}])
        reasons = []
        for path in check['fields']:
            current, present = value, True
            for part in path.split('.'):
                if not isinstance(current, dict) or part not in current:
                    present = False
                    break
                current = current[part]
            if not present:
                reasons.append({'code': 'field_missing', 'field': path})
            elif check['non_empty'] and (current is None or current == [] or current == {}
                                         or (isinstance(current, str) and not current.strip())):
                reasons.append({'code': 'field_empty', 'field': path})
        return _result('failed' if reasons else 'passed', reasons, fields=len(check['fields']))

    def _artefact_schema(self, check, ctx):
        value, refusal = self._json_artefact(check, ctx)
        if refusal:
            return refusal
        reasons = schema_errors(check['schema'], value)
        return _result('failed' if reasons else 'passed', reasons)

    def _artefact_pattern(self, check, ctx):
        artefact = self._artefact(ctx, check['artefact'])
        if artefact is None:
            return _result('failed', [{'code': 'artefact_missing', 'artefact': check['artefact']}])
        payload = json.dumps({'pattern': check['pattern'], 'flags': check['flags'], 'mode': check['mode'],
                              'text': artefact['content']}).encode('ascii')
        try:
            done = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', PATTERN_CHILD], input=payload,
                                  capture_output=True, timeout=self.pattern_seconds, env={}, close_fds=True,
                                  start_new_session=True, check=False)
        except subprocess.TimeoutExpired:
            return _result('unverifiable', [{'code': 'pattern_timeout', 'seconds': self.pattern_seconds}])
        except OSError:
            return _result('unverifiable', [{'code': 'pattern_could_not_run'}])
        answer = done.stdout.decode('ascii', 'replace').strip()
        if done.returncode != 0 or answer not in ('match', 'no_match'):
            return _result('unverifiable', [{'code': 'pattern_could_not_run'}])
        if answer == 'no_match':
            return _result('failed', [{'code': 'pattern_not_matched', 'artefact': check['artefact'], 'mode': check['mode']}])
        return _result('passed')

    def _no_out_of_scope_content(self, check, ctx):
        size = check['min_words']
        allowed = set()
        for value in [*ctx.sent.values(), ctx.packet['instruction'], ctx.packet['goal']['statement']]:
            allowed |= _shingles(_tokens(value), size)
        targets = []
        if 'drafts' in check['targets']:
            for position, action in enumerate(ctx.bundle['proposed_actions']):
                targets.extend(('draft', position, s) for s in _strings(action['parameters']))
        if 'answer' in check['targets']:
            targets.append(('answer', 0, plug.MARKER.sub(' ', ctx.bundle['answer']['text'])))
        if 'artefacts' in check['targets']:
            targets.extend(('artefact', a['name'], plug.MARKER.sub(' ', a['content'])) for a in ctx.bundle['artefacts'])
        wanted = {}
        for target, position, value in targets:
            for shingle in _shingles(_tokens(value), size) - allowed:
                wanted.setdefault(shingle, set()).add((target, position))
        if not wanted:
            return _result('passed', compared_runs=0, notes_compared=0)
        try:
            nodes = self.store.knowledge(ctx.bearer)['nodes']
        except Fault as exc:
            return _result('unverifiable', [{'code': 'notes_unavailable', 'reason': exc.code}])
        hits, unreadable, compared = {}, 0, 0
        firsts = {shingle[0] for shingle in wanted}
        for node in nodes:
            try:
                note = self.store.knowledge_note(ctx.bearer, node['id'])
            except Fault:
                unreadable += 1
                continue
            compared += 1
            tokens, lines = [], []
            for number, line in enumerate(note['body'].splitlines(), 1):
                for match in WORD.finditer(line):
                    tokens.append(match.group(0).casefold())
                    lines.append(number)
            for index in range(len(tokens) - size + 1):
                if tokens[index] not in firsts:
                    continue
                for where in wanted.get(tuple(tokens[index:index + size]), ()):
                    hits.setdefault((where, note['id']), lines[index])
        reasons = [{'code': 'out_of_scope_content', 'target': target, 'position': position, 'note': note_id, 'line': line}
                   for ((target, position), note_id), line in sorted(hits.items(), key=lambda h: (h[0][0][0], str(h[0][0][1]), h[0][1]))]
        detail = {'compared_runs': len(wanted), 'notes_compared': compared, 'notes_unreadable': unreadable}
        if reasons:
            return _result('failed', reasons, **detail)
        if unreadable:
            # A note listed as readable could not be read (changed or withdrawn meanwhile).
            return _result('unverifiable', [{'code': 'notes_changed_during_check', 'count': unreadable}], **detail)
        return _result('passed', **detail)

    def _effect_readback(self, check, ctx):
        pending = [p for p in ctx.proposals if p['disposition'] == 'pending_approval' and p['action_id']]
        if not pending:
            return _result('failed', [{'code': 'no_effect_proposed'}])
        failed, waiting = [], []
        with self.store.connection() as db:
            for proposal in pending:
                position, expected = proposal['position'], json.loads(proposal['parameters'])
                if ctx.bundle is not None and (position >= len(ctx.bundle['proposed_actions'])
                                               or ctx.bundle['proposed_actions'][position]['parameters'] != expected):
                    failed.append({'code': 'effect_differs_from_result', 'position': position})
                    continue
                action = db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (ctx.scope, proposal['action_id'])).fetchone()
                if (not action or action['actor'] != ctx.actor or action['capability'] != proposal['capability']
                        or json.loads(action['parameters']) != expected):
                    failed.append({'code': 'effect_record_differs', 'position': position})
                    continue
                if action['capability'] != 'message.draft':
                    waiting.append({'code': 'readback_not_supported', 'position': position})
                    continue
                if action['state'] != 'verified':
                    code = 'effect_uncertain_reconcile_first' if action['state'] == 'uncertain' else 'effect_not_executed'
                    waiting.append({'code': code, 'position': position, 'action_state': action['state']})
                    continue
                # The same comparison the outbox makes before it marks a local draft verified,
                # repeated read-only from the stored records.
                body = expected['text']
                digest = hashlib.sha256(body.encode()).hexdigest()
                draft = db.execute('SELECT body,digest FROM drafts WHERE scope=? AND action_id=?', (ctx.scope, action['id'])).fetchone()
                proof = json.loads(action['proof']) if action['proof'] else None
                if (not draft or draft['body'] != body or draft['digest'] != digest or type(proof) is not dict
                        or proof.get('type') != 'local_sqlite_draft_readback' or proof.get('sha256') != digest):
                    failed.append({'code': 'readback_mismatch', 'position': position})
        detail = {'effects': len(pending), 'read_back': len(pending) - len(failed) - len(waiting)}
        if failed:
            return _result('failed', failed + waiting, **detail)
        if waiting:
            return _result('unverifiable', waiting, **detail)
        return _result('passed', **detail)

    CONTENT = ('claims_cited', 'numbers_cited', 'artefact_sections', 'artefact_fields', 'artefact_schema',
               'artefact_pattern', 'no_out_of_scope_content')

    def _check(self, check, ctx):
        if check['kind'] in self.CONTENT and ctx.bundle is None:
            outcome = _result('unverifiable', [{'code': ctx.missing}])
        else:
            try:
                outcome = getattr(self, '_' + check['kind'])(check, ctx)
            except Exception:  # A check that cannot run is unverifiable, never passed.
                outcome = _result('unverifiable', [{'code': 'check_could_not_run'}])
        return {'id': check['id'], 'kind': check['kind'], **outcome}

    # Runs ----------------------------------------------------------------------------

    def verify(self, bearer, job_id, *, expected_runs=None, initiated='owner') -> dict:
        """Run the packet's declared checks on the ingested result and record the run.

        ``expected_runs`` is the number of runs the caller saw; when given, the run is
        refused if another run was recorded meanwhile. ``initiated`` records who started the
        run: ``owner``, or ``automatic`` when the goal hub ran it as the result arrived. It
        changes nothing about how the run is judged or counted."""
        ident(job_id)
        if expected_runs is not None and (type(expected_runs) is not int or expected_runs < 0):
            raise Fault('invalid_runs')
        if type(initiated) is not str or initiated not in INITIATORS:
            raise Fault('invalid_initiated')
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            task = dict(self._submitted(db, p, job_id))
            result = db.execute('SELECT * FROM brain_results WHERE job_id=?', (job_id,)).fetchone()
            if not result:
                raise Fault('not_ingested', 409)
            if result['status'] == 'stopped':
                raise Fault('result_not_returned', 409)
            result = dict(result)
            self._expect(db, p, task, job_id, expected_runs)
            proposals = [dict(r) for r in db.execute(
                'SELECT * FROM brain_proposals WHERE job_id=? AND scope=? AND actor=? ORDER BY position',
                (job_id, p['scope'], task['actor']))]
        job = self.jobs.view(bearer, job_id)
        packet = job['parameters']['packet']
        if plug.packet_sha256(packet) != task['packet_sha256']:
            raise Fault('packet_record_mismatch', 409)
        acceptance = packet.get('acceptance')
        declared = acceptance['checks'] if acceptance else []
        if result['status'] == 'refused':
            checks = [{'id': 'C0', 'kind': 'bundle_contract', **_result('failed', [{'code': result['reason']}])}]
            checks += [{'id': c['id'], 'kind': c['kind'], **_result('unverifiable', [{'code': 'bundle_refused'}])} for c in declared]
        else:
            bundle, missing = self._bundle(bearer, job, result, task)
            ctx = _Context(bearer, p['scope'], task['actor'], job_id, packet, bundle, missing, proposals)
            checks = [self._check(check, ctx) for check in declared]
        counts = {status: sum(c['status'] == status for c in checks) for status in CHECK_STATUSES}
        if counts['failed']:
            outcome = 'failed_checks'
        elif declared and counts['passed'] == len(checks):
            outcome = 'checked'
        else:
            outcome = 'returned'
        report = {'report_version': REPORT_VERSION, 'job': job_id, 'brain': task['brain'], 'task_id': task['task_id'],
                  'packet_sha256': task['packet_sha256'], 'envelope_sha256': result['envelope_sha256'],
                  'acceptance_sha256': _sha(_compact(acceptance)) if acceptance else None,
                  'declared_by': acceptance['declared_by'] if acceptance else None,
                  'declared_ref': acceptance['ref'] if acceptance else None,
                  'contract': result['status'], 'declared': len(declared), 'checks': checks, 'counts': counts,
                  'outcome': outcome, 'basis': BASIS, 'limits': LIMITS, 'brain_claims_counted': False}
        return self._record(bearer, job_id, task, report, expected_runs, initiated)

    @staticmethod
    def _expect(db, p, task, job_id, expected_runs):
        if expected_runs is None:
            return
        row = _row(db, p['scope'], task['actor'], job_id)
        if (row['runs'] if row else 0) != expected_runs:
            raise Fault('verification_changed', 409)

    def _record(self, bearer, job_id, task, report, expected_runs=None, initiated='owner') -> dict:
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            actor = self._submitted(db, p, job_id)['actor']
            self._expect(db, p, task, job_id, expected_runs)
            row = _row(db, p['scope'], actor, job_id)
            position, now = (row['runs'] if row else 0) + 1, self.store.now()
            report = dict(report, position=position, at=now)
            body = _compact(report)
            digest, run_id = _sha(body), 'vr-' + _sha(f'{job_id}|{position}')[:24]
            db.execute('''INSERT INTO verification_runs(id,job_id,scope,actor,position,outcome,report,report_sha256,created,
                initiated) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                       (run_id, job_id, p['scope'], actor, position, report['outcome'], body, digest, now, initiated))
            failed_now = sorted(c['id'] for c in report['checks'] if c['status'] == 'failed')
            failed = sorted(set(json.loads(row['failed']) if row else []) | set(failed_now))
            complete = int(bool(row and row['passed_complete']) or report['outcome'] == 'checked')
            state = _checks_outcome(failed, complete)
            acknowledgement = (None, None, None, None)
            if row and row['state'] == 'acknowledged':
                if set(failed) <= set(json.loads(row['acknowledged_failed'])):
                    state = 'acknowledged'
                    acknowledgement = (row['acknowledged_run'], row['acknowledged_over'], row['acknowledged_failed'],
                                       row['acknowledged_at'])
                else:
                    # A check failed that the owner did not accept when acknowledging.
                    self.store.log(db, p['scope'], p['id'], 'verification.acknowledgement_lapsed', job_id)
            if row:
                db.execute('''UPDATE verification_results SET state=?,failed=?,passed_complete=?,runs=?,last_run=?,
                    last_run_sha256=?,acknowledged_run=?,acknowledged_over=?,acknowledged_failed=?,acknowledged_at=?,updated=?
                    WHERE job_id=?''', (state, _compact(failed), complete, position, run_id, digest, *acknowledgement, now, job_id))
            else:
                db.execute('INSERT INTO verification_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           (job_id, p['scope'], actor, task['brain'], state, _compact(failed), complete, position, run_id,
                            digest, None, None, None, None, now, now))
            self.store.log(db, p['scope'], p['id'], 'verification.run_' + report['outcome'], job_id)
            return self._view(db, _row(db, p['scope'], actor, job_id))

    def acknowledge(self, bearer, job_id, run_sha256, *, accept_failures=False) -> dict:
        """The owner accepts a result, bound to the exact run they saw.

        Over failed checks only with ``accept_failures=True``. A refused or stopped result
        has nothing to accept. Acknowledgement grants no authority: proposed effects
        still need their own exact approval.
        """
        ident(job_id)
        if not isinstance(run_sha256, str) or not plug.SHA256.fullmatch(run_sha256):
            raise Fault('invalid_run_sha256')
        _bool(accept_failures, 'invalid_accept_failures')
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            actor = self._submitted(db, p, job_id)['actor']
            result = db.execute('SELECT status FROM brain_results WHERE job_id=?', (job_id,)).fetchone()
            if not result:
                raise Fault('not_ingested', 409)
            if result['status'] != 'accepted':
                raise Fault('nothing_to_acknowledge', 409)
            row = _row(db, p['scope'], actor, job_id)
            if row is None:
                raise Fault('not_verified_yet', 409)
            if not secrets.compare_digest(row['last_run_sha256'], run_sha256):
                raise Fault('acknowledgement_mismatch', 409)
            if row['state'] == 'acknowledged':
                return self._view(db, row)
            if row['state'] == 'failed_checks' and not accept_failures:
                raise Fault('failed_checks_need_explicit_acceptance', 409)
            now = self.store.now()
            db.execute('''UPDATE verification_results SET state='acknowledged',acknowledged_run=?,acknowledged_over=?,
                acknowledged_failed=?,acknowledged_at=?,updated=? WHERE job_id=?''',
                       (row['last_run'], row['state'], row['failed'], now, now, job_id))
            self.store.log(db, p['scope'], p['id'], 'verification.acknowledged', job_id)
            return self._view(db, _row(db, p['scope'], actor, job_id))

    # Views -----------------------------------------------------------------------------

    @staticmethod
    def _view(db, row) -> dict:
        run = db.execute('SELECT * FROM verification_runs WHERE id=?', (row['last_run'],)).fetchone()
        acknowledged = None
        if row['state'] == 'acknowledged':
            acknowledged = {'run': row['acknowledged_run'], 'over': row['acknowledged_over'],
                            'failed_accepted': json.loads(row['acknowledged_failed']), 'at': row['acknowledged_at']}
        report, failed = json.loads(run['report']), json.loads(row['failed'])
        return {'job': row['job_id'], 'brain': row['brain'], 'state': row['state'], 'verified': row['state'] in VERIFIED,
                'checks': _checks_outcome(failed, row['passed_complete']),
                'failed': failed, 'runs': row['runs'], 'acknowledged': acknowledged,
                'declared': report['declared'],
                'evidence': evidence_class(report['contract'], report['declared'], row['state'], failed),
                'last_run': {'position': run['position'], 'outcome': run['outcome'], 'sha256': run['report_sha256'],
                             'initiated': run['initiated'] or 'owner', 'report': report},
                'basis': BASIS, 'brain_claims_counted': False, 'authority_granted': False}

    def state(self, bearer, job_id) -> dict:
        """The current verification position of one of the caller's results."""
        ident(job_id)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            task = self._submitted(db, p, job_id)
            result = db.execute('SELECT status,reason FROM brain_results WHERE job_id=?', (job_id,)).fetchone()
            if not result:
                raise Fault('not_ingested', 404)
            row = _row(db, p['scope'], task['actor'], job_id)
            if row:
                return self._view(db, row)
            job = db.execute('SELECT parameters FROM jobs WHERE id=?', (job_id,)).fetchone() if _table(db, 'jobs') else None
            declared = _declared(job['parameters']) if job else 0
            if result['status'] == 'stopped':
                state = checks = 'not_returned'
            else:
                state = checks = 'failed_checks' if result['status'] == 'refused' else 'returned'
            return {'job': job_id, 'brain': task['brain'], 'state': state, 'verified': False, 'checks': checks,
                    'failed': ['C0'] if result['status'] == 'refused' else [], 'runs': 0, 'acknowledged': None,
                    'declared': declared, 'evidence': evidence_class(result['status'], declared, None, []),
                    'last_run': None, 'contract_reason': result['reason'], 'basis': BASIS,
                    'brain_claims_counted': False, 'authority_granted': False}

    def runs(self, bearer, job_id) -> list:
        """Every recorded run for one of the caller's results, oldest first."""
        ident(job_id)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            task = self._submitted(db, p, job_id)
            return [{'position': r['position'], 'outcome': r['outcome'], 'sha256': r['report_sha256'],
                     'initiated': r['initiated'] or 'owner', 'report': json.loads(r['report'])}
                    for r in db.execute('SELECT * FROM verification_runs WHERE job_id=? AND scope=? AND actor=? ORDER BY position',
                                        (job_id, p['scope'], task['actor']))]

    def outcomes(self, bearer, *, brain=None) -> dict:
        return outcomes(self.store, bearer, brain=brain)
