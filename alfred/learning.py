"""Daily learning that keeps ALFRED supreme (docs/AGENT_HUB.md, step H3).

The learning loop lives in ALFRED, not in any worker. It is deterministic: stated rules
over ALFRED's own value-free records, no model. It runs as the allowlisted routine kind
``daily-learning`` (alfred/routines.py), so the owner authors its schedule, run budget,
proposal budget per run and pause exactly like the other routines, and every run is
recorded once, inside one transaction, under the credential this host runs with.

Each run:

1. Gathers evidence from the person's own records, value-free where possible: approvals
   and refusals (audit), dismissed suggestions (routine nominations, brain suggestions,
   capture policy proposals), owner corrections (supersessions and disputes in the review
   history), drafts lapsed, archived and re-proposed, brain results (ALFRED's own
   ingestion outcome in ``brain_results`` and H4's verification outcome per result:
   verified, failed checks, unverifiable, no declared checks, not returned), budget stops
   and what happened to goal work in the hub journal (H2: budget warnings and hard stops,
   goals and brains paused, stopped or reassigned by the owner, tasks refused by the
   mandate gate, heartbeat slots missed). Only identifiers, states, codes, times and counts
   are kept. The one place a value is read is a re-proposed draft: its old and new text are
   compared for length and sentence count, and only the direction (shorter, longer, fewer
   sentences, more sentences) is kept.
2. Proposes learnings of three kinds, each bound to the evidence identifiers that
   support it and a minimum-evidence threshold: preferences, procedure drafts (to read,
   never to run) and routing notes (per brain, kind of work and scope class, counted from
   ALFRED's checks and the owner's acknowledgement, never from the brain's own confidence
   or its saying it is done; a result without declared checks never counts as verified;
   and per brain, from the goal outcomes in the hub journal).
3. Puts every proposal in the learning review inbox as a suggestion. Accepting one makes
   an owner-owned, versioned record; ``select_learned`` and ``packet_statements`` let
   H1's ``BrainHub`` carry current preference and procedure records in a packet's
   ``learned`` field within H1's limits. A dismissed learning is not offered again until
   new evidence arrives after the dismissal.
4. ``harvest`` and ``harvest_staged`` turn text a worker produced (artefacts of an
   accepted brain result, or skills and memories a worker staged for approval) into
   proposals in the same inbox. Credentials in the text are blanked first (alfred.scrub)
   and only their kinds and counts are kept. Nothing harvested runs or is trusted.
5. Compares the pinned commit of every project in the source library catalogue with an
   owner-supplied file of latest known upstream versions and writes an update brief per
   project. There is no network here: fetching is a declared future capability. Nothing
   is installed and no file under third_party/ is executed or imported; the catalogue is
   read as JSON data and manifests are only hashed.

The owner may also author one "trusted kinds" rule, off by default, naming categories from
a closed list of writing style and presentation preferences. A preference learning in a
named category is then accepted by that rule, recorded with the rule's identifier and
version, shown in the daily digest as accepted by your rule, and can be undone. Nothing
about people, money, commitments, procedures, routing or anything a worker supplied can
ever be accepted that way; the check is in code, independent of what the rule names.

Learning never changes policy, grants, scopes, autonomy levels, budgets, mandates,
routines or capture policies. It changes only what ALFRED proposes and what context it
sends; routing notes are not even sent.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat

from .local import Fault, exact, ident, open_action, text
from .policy import ledger, person_credentials

VERSION = 1
DAY = 86400
WINDOW_DAYS = 30
WINDOW = WINDOW_DAYS * DAY
MIN_EVIDENCE = 3
KINDS = ('preference', 'procedure', 'routing')
# What a packet may carry. Routing notes are for ALFRED's own choice of brain, not for workers.
PACKET_KINDS = ('preference', 'procedure')
MAX_OPEN, MAX_RECORDS, MAX_EVIDENCE_IDS, MAX_SCAN, KEEP_DECIDED = 64, 256, 48, 2000, 400
MAX_BATCH, DIGEST_DAYS = 64, 14
MAX_HARVEST_ITEMS, MAX_HARVEST_TEXT = 8, 2000
PACKET_STATEMENT = 600
MAX_CATALOGUE_BYTES, MAX_OWNER_FILE_BYTES, MAX_MANIFEST_BYTES = 4 << 20, 256 << 10, 64 << 20
MAX_NOTES, MAX_NOTE = 8, 300
RECORD_ID = re.compile(r'lrn-[0-9a-f]{24}')
REPOSITORY = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}')
COMMIT = re.compile(r'[0-9a-f]{40}')
SHA256 = re.compile(r'[0-9a-f]{64}')
DAY_TEXT = re.compile(r'([0-9]{4})-([0-9]{2})-([0-9]{2})')
ROUTINE_KIND = 'daily-learning'
# Read from the hub journal (H2) as codes and identifiers, never trusted as anything else.
HUB_EVENTS = ('budget.warning', 'budget.hard_stop', 'goal.paused', 'goal.stopped', 'brain.paused', 'brain.stopped',
              'goal.reassigned', 'task.refused', 'heartbeat.missed')
BRAIN_ID = re.compile(r'[a-z0-9][a-z0-9_.-]{0,63}')
WORK_KIND = re.compile(r'[a-z][a-z0-9_-]{0,31}')
CODE = re.compile(r'[a-z][a-z0-9_]{0,63}')
TRUST_RULE = 'trusted-kinds'
FETCH = {'capability': 'upstream.fetch', 'status': 'declared_future_capability_not_built', 'network_used': False}

# Every category a learning can carry. Only TRUSTABLE ones may ever be accepted by the
# owner's trusted-kinds rule: preferences about writing style or presentation, nothing else.
CATEGORIES = {
    'writing_length': 'Writing style: how long your drafts are',
    'writing_structure': 'Presentation: how many sentences your drafts are broken into',
    'capture_review': 'How you review what a capture policy proposes',
    'reminder_review': 'How you review routine reminders and draft offers',
    'approval_timing': 'Whether drafts lapse before you decide',
    'statement_corrections': 'Corrections to accepted statements about people, projects and commitments',
    'procedure': 'A sequence of steps you repeat',
    'routing': 'Which brain did which work, by ALFRED\'s own checks',
    'worker_note': 'Text a worker produced',
    'worker_skill': 'A skill a worker staged for approval',
    'worker_memory': 'A memory a worker staged for approval',
}
TRUSTABLE = ('writing_length', 'writing_structure')
DECISIONS = {'accepted_by_you': 'Accepted by you', 'accepted_by_your_rule': 'Accepted by your rule',
             'accepted_in_batch': 'Accepted with the day\'s list', 'dismissed': 'Dismissed',
             'returned_by_undo': 'Back for your review: you undid your rule\'s acceptance'}

ROUTINE_RULES = (
    {'id': 'evidence', 'rule': 'Reads only your own records from the last 30 days: approvals, refusals, dismissed suggestions, '
                               'corrections to accepted statements, lapsed, archived and re-proposed drafts, brain results with their '
                               'verification outcome, budget stops and what happened to goal work (budget warnings and hard stops, '
                               'goals paused, stopped or reassigned, tasks refused by a mandate, missed heartbeats). It keeps '
                               'identifiers, states, times and counts, never the text, except the direction of a draft edit.'},
    {'id': 'draft_edits', 'rule': 'Drafts you edit before proposing again: with at least 3 edits, two thirds of them in one direction '
                                  '(shorter or longer, fewer or more sentences), a writing style preference is proposed.'},
    {'id': 'dismissals', 'rule': 'A capture policy whose proposals you dismissed at least 3 times and at least half the time, or a routine '
                                 'rule whose nominations you dismissed at least 3 times and two thirds of the time, is noted as a preference. '
                                 'The policy and the routine are never changed.'},
    {'id': 'lapses_and_corrections', 'rule': 'At least 3 drafts lapsing before you decided, at least half of the drafts you decided, or '
                                             'at least 3 corrections to accepted statements of one kind, is noted as a preference.'},
    {'id': 'procedures', 'rule': 'Drafts you approved after the same sequence of at least three recorded steps, at least 3 times, are '
                                 'proposed as a procedure draft. Procedures are kept to be read and are never run.'},
    {'id': 'routing', 'rule': 'Brain results per brain, kind of work and scope class, at least 3: counted as verified (declared checks '
                              'passed, or you acknowledged the result), failed checks, could not be verified, no declared checks, not '
                              'returned or stopped at a budget limit. A result without declared checks never counts as verified, and '
                              'nothing a brain says about itself, its confidence or its being done is ever counted.'},
    {'id': 'goal_outcomes', 'rule': 'Goal work per brain, at least 3 setbacks in the hub journal: hard budget stops, tasks refused by a '
                                    'mandate, goals or the brain paused or stopped by you, goals moved to another brain. Budget warnings '
                                    'and missed heartbeats are shown alongside. A routing note only; nothing in the hub is changed.'},
    {'id': 'review', 'rule': 'Every learning waits in your review inbox and daily digest. One open proposal per learning. A dismissed '
                             'learning is offered again only when at least 3 new pieces of evidence arrive after you dismissed it.'},
    {'id': 'trusted_kinds', 'rule': 'Off unless you switch it on: your trusted-kinds rule may accept writing style and presentation '
                                    'preferences for you. Nothing about people, money, commitments, procedures, routing or worker text.'},
    {'id': 'upstream', 'rule': 'Compares the pinned version of each project in the source library with your file of latest known '
                               'versions and writes an update brief. Nothing is fetched or installed.'},
    {'id': 'no_authority', 'rule': 'Learning never changes policy, grants, scopes, autonomy levels, budgets, mandates, acceptance '
                                   'checks, routines or capture policies.'},
)

NOT_PROPOSED = ('already_open', 'already_accepted', 'accepted_evidence_unchanged', 'dismissed_evidence_unchanged',
                'dismissed_same_content', 'proposal_budget', 'proposal_capacity')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS learning_meta(version INTEGER NOT NULL);
INSERT INTO learning_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM learning_meta);
CREATE TABLE IF NOT EXISTS learning_proposals(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, kind TEXT NOT NULL, category TEXT NOT NULL,
 key TEXT NOT NULL, rule TEXT NOT NULL, signature TEXT NOT NULL, statement TEXT NOT NULL, detail TEXT NOT NULL,
 evidence TEXT NOT NULL, evidence_total INTEGER NOT NULL, threshold INTEGER NOT NULL, origin TEXT NOT NULL,
 run_id TEXT, supersedes TEXT, state TEXT NOT NULL, version INTEGER NOT NULL, created INTEGER NOT NULL,
 decided INTEGER, decided_by TEXT, decision TEXT, record_id TEXT,
 CHECK(kind IN ('preference','procedure','routing')), CHECK(state IN ('suggested','accepted','dismissed')));
CREATE INDEX IF NOT EXISTS learning_proposals_key ON learning_proposals(scope,actor,key);
CREATE INDEX IF NOT EXISTS learning_proposals_day ON learning_proposals(scope,actor,created);
CREATE TABLE IF NOT EXISTS learning_records(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, kind TEXT NOT NULL, category TEXT NOT NULL,
 key TEXT NOT NULL, version INTEGER NOT NULL, signature TEXT NOT NULL, statement TEXT NOT NULL, detail TEXT NOT NULL,
 evidence TEXT NOT NULL, origin TEXT NOT NULL, proposal_id TEXT NOT NULL, supersedes TEXT, state TEXT NOT NULL,
 accepted INTEGER NOT NULL, accepted_by TEXT NOT NULL, trust_rule TEXT, trust_rule_version INTEGER, changed INTEGER NOT NULL,
 UNIQUE(scope,actor,key,version), CHECK(state IN ('current','superseded','retired','undone')));
CREATE TABLE IF NOT EXISTS learning_trust_rules(
 scope TEXT NOT NULL, actor TEXT NOT NULL, id TEXT NOT NULL, version INTEGER NOT NULL, enabled INTEGER NOT NULL,
 categories TEXT NOT NULL, updated INTEGER NOT NULL, updated_by TEXT NOT NULL, PRIMARY KEY(scope,actor,id));
CREATE TABLE IF NOT EXISTS learning_upstream_briefs(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, repository TEXT NOT NULL,
 brief_sha256 TEXT NOT NULL, brief TEXT NOT NULL, run_id TEXT, created INTEGER NOT NULL,
 UNIQUE(scope,actor,repository,brief_sha256));
'''

STEP_TEXT = {
    'proposed': 'a draft was proposed for your approval',
    'proposed_by_brain': 'a brain proposed it',
    'proposed_from_routine': 'a routine offered it and you accepted the offer',
    'proposed_from_conversation': 'it was proposed from a conversation',
    'proposed_from_evidence': 'it was proposed from a reported change',
    'proposed_inbox_note': 'an inbox note was proposed',
    'proposed_vault_append': 'an addition to a note was proposed',
    'lapsed': 'its approval window lapsed',
    'archived': 'you archived it',
    'unarchived': 'you brought it back from the archive',
    'reproposed': 'you proposed it again',
    'reproposed_edited': 'you edited it and proposed it again',
    'approved': 'you approved its exact text',
}
PATH_KINDS = {'action.proposed': 'proposed', 'action.proposed_from_routine': 'proposed_from_routine',
              'action.proposed_from_conversation': 'proposed_from_conversation',
              'action.proposed_from_evidence': 'proposed_from_evidence',
              'action.proposed_inbox_note': 'proposed_inbox_note', 'action.proposed_vault_append': 'proposed_vault_append',
              'draft.archived': 'archived', 'draft.unarchived': 'unarchived',
              'action.reproposed_from_draft': 'reproposed', 'action.approved': 'approved'}
CAPABILITY_TEXT = {'message.draft': 'message draft', 'vault.inbox_note': 'inbox note', 'vault.append': 'note addition'}
ROUTING_TEXT = {'often_stops_at_budget': 'often stopped at a budget limit',
                'often_fails_checks': 'results often failed ALFRED\'s checks',
                'mostly_verified': 'results were mostly verified by ALFRED\'s checks or your acknowledgement',
                'mostly_refused_or_stopped': 'results were mostly refused or stopped',
                'mostly_not_verified': 'results were mostly not verified (no declared checks, or checks that could not run)',
                'mixed': 'results were mixed'}
GOAL_TEXT = {'often_hard_stopped': 'its goal work often hit a hard budget stop',
             'often_refused_by_mandate': 'its goal tasks were often refused by the mandate',
             'often_paused_stopped_or_moved': 'its goal work was often paused, stopped or moved to another brain by you',
             'goal_setbacks_mixed': 'its goal work met mixed setbacks'}
VERIFICATION_CLASSES = ('verified', 'failed_checks', 'unverifiable', 'no_checks', 'not_returned')


# Helpers -----------------------------------------------------------------------------

def _dump(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def _has(db, table):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _marks(values):
    return ','.join('?' * len(values))


def _creds(db, p):
    """Every device credential of the caller's person: evidence is the person's, not one device's."""
    return sorted(person_credentials(db, ledger(db, p)) | {p['id']})


def _version(body, code='invalid_learning_decision'):
    exact(body, {'version'})
    if type(body['version']) is not int or body['version'] < 1:
        raise Fault(code)
    return body['version']


def _one_line(value):
    return ' '.join(value.split())


def _credential_shaped(value):
    from .brain import CREDENTIAL_SHAPE
    return bool(CREDENTIAL_SHAPE.search(value))


def trustable(kind, category, origin):
    """The only learnings the owner's trusted-kinds rule may ever accept, whatever it names."""
    return kind == 'preference' and category in TRUSTABLE and origin == 'daily_learning'


def is_record_id(value):
    return isinstance(value, str) and bool(RECORD_ID.fullmatch(value))


def _day_start(moment, offset_minutes):
    local = moment + offset_minutes * 60
    return local - local % DAY - offset_minutes * 60


def _day_text(start, offset_minutes):
    return datetime.fromtimestamp(start + offset_minutes * 60, timezone.utc).strftime('%Y-%m-%d')


def _parse_day(value, offset_minutes):
    match = DAY_TEXT.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise Fault('invalid_learning_day')
    try:
        moment = datetime(int(match[1]), int(match[2]), int(match[3]), tzinfo=timezone(timedelta(minutes=offset_minutes)))
    except ValueError:
        raise Fault('invalid_learning_day') from None
    return int(moment.timestamp())


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _constant(_):
    raise ValueError('non-finite number')


def _read_json(path, limit):
    """(value, None) or (None, reason). Never follows a symbolic link; bounded size; data only."""
    if path is None:
        return None, 'not_configured'
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None, 'missing'
    except OSError:
        return None, 'unreadable'
    if not stat.S_ISREG(info.st_mode):
        return None, 'not_a_regular_file'
    if info.st_size > limit:
        return None, 'too_large'
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0))
        with os.fdopen(fd, 'rb') as handle:
            raw = handle.read(limit + 1)
    except OSError:
        return None, 'unreadable'
    if len(raw) > limit:
        return None, 'too_large'
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_constant), None
    except (UnicodeError, ValueError, RecursionError):
        return None, 'invalid_json'


# Evidence ----------------------------------------------------------------------------

def _audit(db, scope, creds, kinds, since, now):
    """The person's audit rows of the given kinds in the window, oldest first, bounded."""
    if not kinds:
        return []
    rows = db.execute(f'''SELECT seq,kind,subject,at FROM audit WHERE scope=? AND actor IN ({_marks(creds)})
        AND kind IN ({_marks(kinds)}) AND at>=? AND at<=? ORDER BY seq DESC LIMIT ?''',
                      (scope, *creds, *kinds, since, now, MAX_SCAN)).fetchall()
    return [dict(r) for r in reversed(rows)]


_SENTENCE = re.compile(r'[.!?]+(?:\s|$)')


def _sentences(value):
    """How many sentences a draft is broken into. Only the count is kept, never the words."""
    return len([part for part in _SENTENCE.split(value) if part.strip()])


def _text_of(db, scope, action_id):
    row = open_action(db, db.execute('SELECT scope,id,capability,parameters,expires FROM actions WHERE scope=? AND id=?',
                                     (scope, action_id)).fetchone())
    if not row:
        return None
    try:
        params = json.loads(row['parameters'])
    except ValueError:
        params = {}
    return {'capability': row['capability'], 'expires': row['expires'],
            'text': params.get('text') if isinstance(params, dict) and isinstance(params.get('text'), str) else None}


def gather(db, p, now):
    """The person's value-free evidence for the learning window, and today's counts."""
    from .drafts import CAPABILITIES as DRAFT_CAPABILITIES, REMOVED
    scope, person, creds = p['scope'], ledger(db, p), _creds(db, p)
    since = now - WINDOW
    ev = {name: [] for name in ('approvals', 'refusals', 'archived', 'reproposed', 'lapsed', 'routine_dismissed',
                                'routine_accepted', 'brain_suggestions_dismissed', 'capture_decided', 'corrections',
                                'brain_results', 'budget_stops', 'hub_budget', 'hub_controls', 'hub_refusals', 'hub_missed')}
    for row in _audit(db, scope, creds, ('action.approved', 'action.cancelled', 'draft.archived', 'action.reproposed_from_draft',
                                         'routine.nomination_dismissed', 'routine.nomination_accepted',
                                         'brain.suggestion_dismissed'), since, now):
        item = {'id': f'audit:{row["seq"]}', 'at': row['at'], 'subject': row['subject']}
        if row['kind'] == 'action.approved':
            ev['approvals'].append(item)
        elif row['kind'] == 'action.cancelled':
            ev['refusals'].append(item)
        elif row['kind'] == 'draft.archived':
            ev['archived'].append(item)
        elif row['kind'] == 'brain.suggestion_dismissed':
            ev['brain_suggestions_dismissed'].append(item)
        elif row['kind'] == 'action.reproposed_from_draft':
            # Only the direction of an edit is kept. The text is read here and dropped.
            link = db.execute('SELECT reproposed_from FROM draft_records WHERE scope=? AND action_id=?',
                              (scope, row['subject'])).fetchone() if _has(db, 'draft_records') else None
            new = _text_of(db, scope, row['subject'])
            old = _text_of(db, scope, link['reproposed_from']) if link and link['reproposed_from'] else None
            item['length'] = item['structure'] = None
            if (new and old and new['capability'] == 'message.draft' == old['capability'] and new['text'] and old['text']
                    and REMOVED not in (new['text'], old['text']) and new['text'] != old['text']):
                a, b = len(old['text']), len(new['text'])
                item['length'] = 'shorter' if b < a else 'longer' if b > a else 'same'
                la, lb = _sentences(old['text']), _sentences(new['text'])
                item['structure'] = 'fewer_sentences' if lb < la else 'more_sentences' if lb > la else 'same'
            ev['reproposed'].append(item)
        else:
            rule = None
            if _has(db, 'routine_nominations'):
                found = db.execute('SELECT routine,kind,rule FROM routine_nominations WHERE scope=? AND id=?',
                                   (scope, row['subject'])).fetchone()
                rule = f'{found["routine"]}:{found["rule"]}' if found else None
            item['rule'] = rule
            ev['routine_dismissed' if row['kind'] == 'routine.nomination_dismissed' else 'routine_accepted'].append(item)
    for row in db.execute(f'''SELECT id,expires FROM actions WHERE scope=? AND actor IN ({_marks(creds)}) AND state='proposed'
            AND capability IN ({_marks(DRAFT_CAPABILITIES)}) AND expires<=? AND expires>=? ORDER BY expires DESC LIMIT ?''',
                          (scope, *creds, *DRAFT_CAPABILITIES, now, since, MAX_SCAN)).fetchall()[::-1]:
        ev['lapsed'].append({'id': f'action:{row["id"]}', 'at': row['expires']})
    if _has(db, 'memory_claim_history') and _has(db, 'capture_proposals'):
        for row in db.execute(f'''SELECT h.seq,h.at,h.state,h.claim_id,x.policy_id FROM memory_claim_history h
                JOIN capture_proposals x ON x.claim_id=h.claim_id AND x.scope=h.scope
                WHERE h.scope=? AND h.actor=? AND x.actor IN ({_marks(creds)}) AND h.by IN ({_marks(creds)}) AND h.at>=?
                AND h.state IN ('accepted','withdrawn','disputed') ORDER BY h.seq DESC LIMIT ?''',
                              (scope, person, *creds, *creds, since, MAX_SCAN)).fetchall()[::-1]:
            ev['capture_decided'].append({'id': f'history:{row["seq"]}', 'at': row['at'], 'claim': row['claim_id'],
                                          'policy': row['policy_id'], 'dismissed': row['state'] != 'accepted'})
    if _has(db, 'memory_claim_history'):
        for row in db.execute(f'''SELECT h.seq,h.at,h.state,c.predicate FROM memory_claim_history h
                LEFT JOIN memory_claims c ON c.id=h.claim_id
                WHERE h.scope=? AND h.actor=? AND h.by IN ({_marks(creds)}) AND h.at>=? AND (h.state='superseded'
                OR (h.state='disputed' AND EXISTS(SELECT 1 FROM memory_claim_history a WHERE a.scope=h.scope AND a.actor=h.actor
                    AND a.claim_id=h.claim_id AND a.state='accepted' AND a.seq<h.seq)))
                ORDER BY h.seq DESC LIMIT ?''', (scope, person, *creds, since, MAX_SCAN)).fetchall()[::-1]:
            ev['corrections'].append({'id': f'history:{row["seq"]}', 'at': row['at'], 'predicate': row['predicate']})
    if _has(db, 'brain_results') and _has(db, 'brain_tasks'):
        # H4's outcome per result: ALFRED's checks and the owner's acknowledgement, never the brain's words.
        from .verification import outcome_rows
        hub = _has(db, 'hub_tasks')
        for row in outcome_rows(db, scope, creds, since=since, limit=MAX_SCAN):
            found = db.execute('SELECT work FROM hub_tasks WHERE job_id=?', (row['job'],)).fetchone() if hub else None
            work = found['work'] if found and isinstance(found['work'], str) and WORK_KIND.fullmatch(found['work']) else None
            over = bool(row['reason'] and row['reason'].startswith('over_budget_'))
            # The latest time ALFRED's record of the result changed: ingested, or checked or acknowledged later.
            item = {'id': f'brain_result:{row["job"]}', 'at': max(row['ingested_at'], row['updated_at'] or 0),
                    'brain': row['brain'], 'job_kind': work or 'brain_task', 'scope_class': row['scope_class'],
                    'status': row['contract'], 'over_budget': over, 'verification': row['evidence'],
                    'declared': row['declared'], 'acknowledged': row['state'] == 'acknowledged'}
            ev['brain_results'].append(item)
            if over:
                ev['budget_stops'].append({'id': item['id'], 'at': item['at'], 'kind': 'brain'})
    if _has(db, 'hub_journal'):
        _hub_evidence(db, scope, creds, since, now, ev)
    if _has(db, 'routine_runs'):
        for row in db.execute(f'''SELECT id,started FROM routine_runs WHERE scope=? AND actor IN ({_marks(creds)})
                AND status='skipped' AND skipped_reason='budget_exhausted' AND started>=? ORDER BY started DESC LIMIT ?''',
                              (scope, *creds, since, MAX_SCAN)).fetchall()[::-1]:
            ev['budget_stops'].append({'id': f'routine_run:{row["id"]}', 'at': row['started'], 'kind': 'routine'})
    if _has(db, 'capture_deferred'):
        for row in db.execute(f'''SELECT day,policy_id,count(*) AS n FROM capture_deferred WHERE scope=? AND actor IN ({_marks(creds)})
                AND day>=? GROUP BY day,policy_id ORDER BY day,policy_id LIMIT ?''',
                              (scope, *creds, since // DAY, MAX_SCAN)).fetchall():
            ev['budget_stops'].append({'id': f'capture_deferred:{row["day"]}:{row["policy_id"]}', 'at': row['day'] * DAY,
                                       'kind': 'capture', 'count': row['n']})
    return ev


def _hub_brain(target, detail, name='brain'):
    value = target[len('brain:'):] if name == 'brain' and target.startswith('brain:') else detail.get(name)
    return value if isinstance(value, str) and BRAIN_ID.fullmatch(value) else None


def _hub_evidence(db, scope, creds, since, now, ev):
    """What happened to goal work, from the hub journal: identifiers, codes, times and counts.
    The journal is ALFRED's own record of its gate and the owner's controls; nothing a brain
    wrote reaches it."""
    rows = db.execute(f'''SELECT seq,target,event,detail,at FROM hub_journal WHERE scope=? AND actor IN ({_marks(creds)})
        AND event IN ({_marks(HUB_EVENTS)}) AND at>=? AND at<=? ORDER BY seq DESC LIMIT ?''',
                      (scope, *creds, *HUB_EVENTS, since, now, MAX_SCAN)).fetchall()[::-1]
    for row in rows:
        try:
            detail = json.loads(row['detail'])
        except ValueError:
            detail = {}
        detail = detail if isinstance(detail, dict) else {}
        item = {'id': f'hub_journal:{row["seq"]}', 'at': row['at']}
        event, target = row['event'], row['target']
        if event.startswith('budget.'):
            level = 'brain' if target.startswith('brain:') else 'goal' if target.startswith('goal:') else 'overall'
            item.update(level=event[len('budget.'):], target_level=level, brain=_hub_brain(target, detail))
            ev['hub_budget'].append(item)
            if item['level'] == 'hard_stop':
                ev['budget_stops'].append({'id': item['id'], 'at': item['at'], 'kind': 'hub'})
        elif event in ('goal.paused', 'goal.stopped', 'brain.paused', 'brain.stopped'):
            if detail.get('reason') != 'operator':
                continue  # A hold a budget caused is already counted as its hard stop.
            item.update(action=event.split('.')[1], target_level=event.split('.')[0], brain=_hub_brain(target, detail))
            ev['hub_controls'].append(item)
        elif event == 'goal.reassigned':
            item.update(action='reassigned', target_level='goal', brain=_hub_brain('', detail, 'from'))
            ev['hub_controls'].append(item)
        elif event == 'task.refused':
            reason, stage = detail.get('reason'), detail.get('stage')
            item.update(brain=_hub_brain('', detail), reason=reason if isinstance(reason, str) and CODE.fullmatch(reason) else None,
                        stage=stage if stage in ('admission', 'dispatch') else None)
            ev['hub_refusals'].append(item)
        else:
            missed = detail.get('missed')
            item.update(brain=_hub_brain('', detail), missed=missed if type(missed) is int and 0 < missed <= 1000 else 0)
            ev['hub_missed'].append(item)


def summary(ev, now):
    """Value-free counts for today (the last 24 hours) and the whole window."""
    groups = {'approvals': ev['approvals'], 'refusals': ev['refusals'],
              'dismissed_suggestions': ev['routine_dismissed'] + ev['brain_suggestions_dismissed']
              + [c for c in ev['capture_decided'] if c['dismissed']],
              'corrections': ev['corrections'], 'drafts_lapsed': ev['lapsed'], 'drafts_archived': ev['archived'],
              'drafts_reproposed': ev['reproposed'], 'brain_results': ev['brain_results'], 'budget_stops': ev['budget_stops'],
              'hub_budget_warnings': [i for i in ev['hub_budget'] if i['level'] == 'warning'],
              'hub_hard_stops': [i for i in ev['hub_budget'] if i['level'] == 'hard_stop'],
              'paused_or_stopped_by_you': [i for i in ev['hub_controls'] if i['action'] != 'reassigned'],
              'work_reassigned': [i for i in ev['hub_controls'] if i['action'] == 'reassigned'],
              'mandate_refusals': ev['hub_refusals']}
    today = {name: sum(i['at'] >= now - DAY for i in items) for name, items in groups.items()}
    window = {name: len(items) for name, items in groups.items()}
    today['heartbeat_slots_missed'] = sum(i['missed'] for i in ev['hub_missed'] if i['at'] >= now - DAY)
    window['heartbeat_slots_missed'] = sum(i['missed'] for i in ev['hub_missed'])
    for name in VERIFICATION_CLASSES:
        today['results_' + name] = sum(i['verification'] == name and i['at'] >= now - DAY for i in ev['brain_results'])
        window['results_' + name] = sum(i['verification'] == name for i in ev['brain_results'])
    return today, window


# Rules: evidence to candidate learnings ---------------------------------------------

def _candidate(kind, category, rule, key, signature, statement, detail, evidence, threshold=MIN_EVIDENCE, origin='daily_learning'):
    if len(evidence) < threshold:
        raise AssertionError('a learning is never proposed below its evidence threshold')
    return {'kind': kind, 'category': category, 'rule': rule, 'key': key, 'signature': signature,
            'statement': statement[:PACKET_STATEMENT] if origin == 'daily_learning' else statement, 'detail': detail,
            'evidence': sorted(((e['id'], e['at']) for e in evidence), key=lambda x: (x[1], x[0])),
            'threshold': threshold, 'origin': origin}


def _edit_rule(items, field, category, key, words):
    edits = [i for i in items if i.get(field) is not None]
    counts = {}
    for i in edits:
        counts[i[field]] = counts.get(i[field], 0) + 1
    for direction, phrase in words.items():
        n = counts.get(direction, 0)
        if n >= MIN_EVIDENCE and 3 * n >= 2 * len(edits):
            return _candidate('preference', category, 'draft_edits', key, direction,
                              f'When you edit a draft before proposing it again, you usually {phrase} '
                              f'({n} of {len(edits)} edits in {WINDOW_DAYS} days).',
                              {'edits': len(edits), **{k: counts.get(k, 0) for k in words}},
                              [i for i in edits if i[field] == direction])
    return None


def _procedure_steps(db, scope, creds, approval, brain_actions):
    chain, seen = [approval['subject']], set()
    if _has(db, 'draft_records'):
        while len(chain) < 10:
            row = db.execute('SELECT reproposed_from FROM draft_records WHERE scope=? AND action_id=?', (scope, chain[0])).fetchone()
            if not row or not row['reproposed_from'] or row['reproposed_from'] in seen:
                break
            seen.add(row['reproposed_from'])
            chain.insert(0, row['reproposed_from'])
    steps, previous, capability = [], None, None
    for action_id in chain:
        current = _text_of(db, scope, action_id)
        if current is None:
            return None, None
        capability = current['capability']
        for row in db.execute(f'''SELECT kind,at FROM audit WHERE scope=? AND subject=? AND actor IN ({_marks(creds)})
                AND kind IN ({_marks(list(PATH_KINDS))}) ORDER BY seq''', (scope, action_id, *creds, *PATH_KINDS)):
            step = PATH_KINDS[row['kind']]
            if step == 'proposed' and action_id in brain_actions:
                step = 'proposed_by_brain'
            if step == 'reproposed':
                if previous is not None and previous['expires'] <= row['at']:
                    steps.append('lapsed')
                if previous is not None and previous['text'] != current['text']:
                    step = 'reproposed_edited'
            if not steps or steps[-1] != step:
                steps.append(step)
        previous = current
    return capability, steps


def derive(db, p, ev, now):
    """Candidate learnings, in a fixed order, from the evidence. Deterministic."""
    found = []
    edit = _edit_rule(ev['reproposed'], 'length', 'writing_length', 'preference:draft_length',
                      {'shorter': 'make it shorter', 'longer': 'make it longer'})
    if edit:
        found.append(edit)
    edit = _edit_rule(ev['reproposed'], 'structure', 'writing_structure', 'preference:draft_structure',
                      {'fewer_sentences': 'put it in fewer sentences', 'more_sentences': 'break it into more sentences'})
    if edit:
        found.append(edit)
    policies = {}
    for item in ev['capture_decided']:
        entry = policies.setdefault(item['policy'], {'decided': set(), 'dismissed': {}, 'evidence': []})
        entry['decided'].add(item['claim'])
        if item['dismissed']:
            entry['dismissed'].setdefault(item['claim'], item)
    for policy in sorted(policies):
        entry = policies[policy]
        n, m = len(entry['dismissed']), len(entry['decided'])
        if n >= MIN_EVIDENCE and 2 * n >= m:
            found.append(_candidate('preference', 'capture_review', 'dismissals', f'preference:capture_dismissed:{policy}',
                                    'mostly_dismissed',
                                    f'You dismiss at least half of what capture policy "{policy}" proposes ({n} of {m} decided in '
                                    f'{WINDOW_DAYS} days). The policy is unchanged; editing it is your decision.',
                                    {'policy': policy, 'dismissed': n, 'decided': m}, list(entry['dismissed'].values())))
    rules = {}
    for name in ('routine_dismissed', 'routine_accepted'):
        for item in ev[name]:
            if item['rule']:
                rules.setdefault(item['rule'], {'routine_dismissed': [], 'routine_accepted': []})[name].append(item)
    for rule in sorted(rules):
        dismissed, accepted = rules[rule]['routine_dismissed'], rules[rule]['routine_accepted']
        n, m = len(dismissed), len(dismissed) + len(accepted)
        if n >= MIN_EVIDENCE and 3 * n >= 2 * m:
            routine, rule_id = rule.split(':', 1)
            found.append(_candidate('preference', 'reminder_review', 'dismissals', f'preference:routine_dismissed:{rule}',
                                    'mostly_dismissed',
                                    f'You usually dismiss {routine.replace("-", " ")} nominations made by the rule "{rule_id}" '
                                    f'({n} of {m} decided in {WINDOW_DAYS} days). The routine is unchanged.',
                                    {'routine': routine, 'rule': rule_id, 'dismissed': n, 'decided': m}, dismissed))
    lapsed, decided = len(ev['lapsed']), len(ev['lapsed']) + len(ev['approvals']) + len(ev['refusals'])
    if lapsed >= MIN_EVIDENCE and 2 * lapsed >= decided:
        found.append(_candidate('preference', 'approval_timing', 'lapses_and_corrections', 'preference:drafts_lapse',
                                'mostly_lapse',
                                f'At least half of the drafts offered to you lapse before you decide on them ({lapsed} of {decided} in '
                                f'{WINDOW_DAYS} days).', {'lapsed': lapsed, 'decided_or_lapsed': decided}, ev['lapsed']))
    predicates = {}
    for item in ev['corrections']:
        if item['predicate']:
            predicates.setdefault(item['predicate'], []).append(item)
    for predicate in sorted(predicates):
        items = predicates[predicate]
        if len(items) >= MIN_EVIDENCE:
            found.append(_candidate('preference', 'statement_corrections', 'lapses_and_corrections',
                                    f'preference:corrections:{predicate}', 'often_corrected',
                                    f'You often correct accepted "{predicate.replace("_", " ")}" statements '
                                    f'({len(items)} corrections in {WINDOW_DAYS} days).',
                                    {'predicate': predicate, 'corrections': len(items)}, items))
    scope, creds = p['scope'], _creds(db, p)
    brain_actions = set()
    if _has(db, 'brain_proposals'):
        brain_actions = {r[0] for r in db.execute('SELECT action_id FROM brain_proposals WHERE scope=? AND action_id IS NOT NULL', (scope,))}
    paths = {}
    for approval in ev['approvals']:
        capability, steps = _procedure_steps(db, scope, creds, approval, brain_actions)
        if steps and len(steps) >= 3 and steps[-1] == 'approved':
            paths.setdefault((capability, tuple(steps)), []).append(approval)
    for (capability, steps) in sorted(paths):
        items = paths[(capability, steps)]
        if len(items) >= MIN_EVIDENCE:
            path = capability + '|' + '>'.join(steps)
            words = '; '.join(f'{n}. {STEP_TEXT[s]}' for n, s in enumerate(steps, 1))
            found.append(_candidate('procedure', 'procedure', 'procedures',
                                    'procedure:path:' + hashlib.sha256(path.encode()).hexdigest()[:16], path,
                                    f'Procedure draft for a {CAPABILITY_TEXT.get(capability, "draft")}: {words}. Seen '
                                    f'{len(items)} times in {WINDOW_DAYS} days. Kept to be read; never run.',
                                    {'capability': capability, 'steps': list(steps), 'seen': len(items)}, items))
    groups = {}
    for item in ev['brain_results']:
        groups.setdefault((item['brain'], item['job_kind'], item['scope_class']), []).append(item)
    for (brain, job_kind, scope_class) in sorted(groups):
        items = groups[(brain, job_kind, scope_class)]
        total = len(items)
        if total < MIN_EVIDENCE:
            continue
        counts = {s: sum(i['status'] == s for i in items) for s in ('accepted', 'refused', 'stopped')}
        over = sum(i['over_budget'] for i in items)
        checks = {c: sum(i['verification'] == c for i in items) for c in VERIFICATION_CLASSES}
        unconfirmed = checks['no_checks'] + checks['unverifiable']
        if over >= MIN_EVIDENCE and 3 * over >= total:
            category = 'often_stops_at_budget'
        elif checks['failed_checks'] >= MIN_EVIDENCE and 3 * checks['failed_checks'] >= total:
            category = 'often_fails_checks'
        elif checks['verified'] >= MIN_EVIDENCE and 5 * checks['verified'] >= 4 * total:
            category = 'mostly_verified'
        elif 2 * counts['accepted'] < total:
            category = 'mostly_refused_or_stopped'
        elif unconfirmed >= MIN_EVIDENCE and 2 * unconfirmed >= total:
            category = 'mostly_not_verified'
        else:
            category = 'mixed'
        found.append(_candidate('routing', 'routing', 'routing', f'routing:{brain}:{job_kind}:{scope_class}', category,
                                f'Brain "{brain}" on {job_kind.replace("_", " ")} work in {scope_class} scope: '
                                f'{ROUTING_TEXT[category]} ({checks["verified"]} verified, {checks["failed_checks"]} failed checks, '
                                f'{checks["unverifiable"]} could not be verified, {checks["no_checks"]} with no declared checks, '
                                f'{checks["not_returned"]} not returned, {over} at a budget limit, in {WINDOW_DAYS} days). '
                                'Verified means ALFRED\'s declared checks passed or you acknowledged the result; a result with '
                                'no declared checks never counts as verified, and the brain\'s own confidence is never counted.',
                                {'brain': brain, 'job_kind': job_kind, 'scope_class': scope_class, **counts,
                                 'over_budget': over, 'total': total, 'verification': checks, 'verified': checks['verified'],
                                 'acknowledged': sum(i['acknowledged'] and i['verification'] == 'verified' for i in items),
                                 'no_checks_counted_as_verified': False,
                                 'basis': 'alfred_checks_and_owner_acknowledgement_not_brain_confidence'}, items))
    found.extend(_goal_outcomes(ev))
    return found


def _goal_outcomes(ev):
    """One routing note per brain from what happened to its goal work (the hub journal)."""
    brains = {}
    for name in ('hub_budget', 'hub_controls', 'hub_refusals', 'hub_missed'):
        for item in ev[name]:
            if item.get('brain'):
                brains.setdefault(item['brain'], {n: [] for n in ('hub_budget', 'hub_controls', 'hub_refusals', 'hub_missed')})[name].append(item)
    found = []
    for brain in sorted(brains):
        entry = brains[brain]
        hard = [i for i in entry['hub_budget'] if i['level'] == 'hard_stop']
        warnings = sum(i['level'] == 'warning' for i in entry['hub_budget'])
        refused, controls = entry['hub_refusals'], entry['hub_controls']
        setbacks = hard + refused + controls
        if len(setbacks) < MIN_EVIDENCE:
            continue
        groups = (('often_hard_stopped', hard), ('often_refused_by_mandate', refused), ('often_paused_stopped_or_moved', controls))
        largest = max(len(items) for _, items in groups)
        category = next((name for name, items in groups if len(items) == largest and largest >= MIN_EVIDENCE), 'goal_setbacks_mixed')
        moved = sum(i['action'] == 'reassigned' for i in controls)
        missed = sum(i['missed'] for i in entry['hub_missed'])
        reasons = {}
        for item in refused:
            if item['reason']:
                reasons[item['reason']] = reasons.get(item['reason'], 0) + 1
        found.append(_candidate('routing', 'routing', 'goal_outcomes', f'routing-goals:{brain}', category,
                                f'Goal work routed to brain "{brain}": {GOAL_TEXT[category]} ({len(hard)} hard budget stops, '
                                f'{warnings} budget warnings, {len(refused)} tasks refused by the mandate, '
                                f'{len(controls) - moved} pauses or stops by you, {moved} goals moved to another brain, '
                                f'{missed} heartbeat slots missed while ALFRED was not running, in {WINDOW_DAYS} days). Counted '
                                'from ALFRED\'s hub journal, never from the brain. A note only: no budget, mandate or '
                                'assignment is changed.',
                                {'brain': brain, 'hard_stops': len(hard), 'budget_warnings': warnings, 'mandate_refusals': len(refused),
                                 'refusal_reasons': dict(sorted(reasons.items())), 'paused_or_stopped_by_you': len(controls) - moved,
                                 'moved_to_another_brain': moved, 'heartbeat_slots_missed': missed, 'setbacks': len(setbacks),
                                 'basis': 'alfred_hub_journal_not_brain_report'}, setbacks))
    return found


# Upstream watch ----------------------------------------------------------------------

def _notes(value, code):
    if value is None:
        return []
    if type(value) is not list or len(value) > MAX_NOTES:
        raise Fault(code)
    for item in value:
        text(item, MAX_NOTE)
    return list(value)


def owner_file(value):
    """Validate the owner's file of latest known upstream versions. Data only."""
    if type(value) is not dict or set(value) - {'schema_version', 'observed_on', 'projects'} or value.get('schema_version') != 1:
        raise Fault('invalid_upstream_file')
    observed = value.get('observed_on')
    if observed is not None and (not isinstance(observed, str) or not DAY_TEXT.fullmatch(observed)):
        raise Fault('invalid_upstream_file')
    projects = value.get('projects')
    if type(projects) is not dict or len(projects) > 500:
        raise Fault('invalid_upstream_file')
    result = {}
    for name, entry in projects.items():
        if not REPOSITORY.fullmatch(name) or '..' in name or type(entry) is not dict:
            raise Fault('invalid_upstream_project')
        if set(entry) - {'commit', 'release', 'licence', 'changed_defaults', 'licence_notes', 'security_notes'}:
            raise Fault('invalid_upstream_project')
        commit, release, licence = entry.get('commit'), entry.get('release'), entry.get('licence')
        if commit is not None and (not isinstance(commit, str) or not COMMIT.fullmatch(commit)):
            raise Fault('invalid_upstream_commit')
        if commit is None and release is None:
            raise Fault('invalid_upstream_project')
        if release is not None:
            text(release, 80)
        if licence is not None:
            text(licence, 120)
        result[name] = {'commit': commit, 'release': release, 'licence': licence,
                        'changed_defaults': _notes(entry.get('changed_defaults'), 'invalid_upstream_notes'),
                        'licence_notes': _notes(entry.get('licence_notes'), 'invalid_upstream_notes'),
                        'security_notes': _notes(entry.get('security_notes'), 'invalid_upstream_notes')}
    return observed, result


def catalogue_entries(value):
    """The pinned projects of the source library catalogue. Reads only what is needed."""
    if type(value) is not dict or value.get('schema_version') != 1 or type(value.get('repositories')) is not list:
        raise Fault('invalid_catalogue')
    entries = []
    for item in value['repositories'][:500]:
        if type(item) is not dict:
            raise Fault('invalid_catalogue')
        name, commit, status = item.get('repository'), item.get('commit'), item.get('status')
        if not isinstance(name, str) or not REPOSITORY.fullmatch(name) or '..' in name:
            raise Fault('invalid_catalogue')
        if not isinstance(commit, str) or not COMMIT.fullmatch(commit) or status not in ('copied', 'reference_only'):
            raise Fault('invalid_catalogue')
        licence = item.get('licence') if isinstance(item.get('licence'), str) else None
        manifest = item.get('manifest_sha256')
        entries.append({'repository': name, 'commit': commit, 'status': status,
                        'licence': licence[:120] if licence else None,
                        'manifest_sha256': manifest if isinstance(manifest, str) and SHA256.fullmatch(manifest) else None})
    return entries


# The learning service ----------------------------------------------------------------

class Learning:
    """Learning proposals, owner-owned records, the daily digest, the trusted-kinds rule,
    harvest and the upstream watch, over the shared store. Person-private (policy.ledger)."""

    def __init__(self, store, *, catalogue=None, upstream_file=None):
        self.store = store
        root = Path(__file__).resolve().parents[1]
        self.catalogue = Path(catalogue) if catalogue is not None else root / 'third_party' / 'library' / 'CATALOGUE.json'
        path = getattr(store, 'path', None)
        self.upstream_file = Path(upstream_file) if upstream_file is not None else (
            Path(path).parent / 'upstream-latest.json' if path is not None else None)
        self._manifests = {}
        with store.connection() as db:
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
            if [r[0] for r in db.execute('SELECT version FROM learning_meta')] != [VERSION]:
                raise Fault('unsupported_learning_version')

    # Standing of a learning key ---------------------------------------------------

    @staticmethod
    def _current(db, scope, person, key):
        row = db.execute("SELECT * FROM learning_records WHERE scope=? AND actor=? AND key=? AND state='current'",
                         (scope, person, key)).fetchone()
        return dict(row) if row else None

    def _standing(self, db, scope, person, candidate):
        """None when the candidate may be proposed now, else the reason it is not."""
        key = candidate['key']
        if db.execute("SELECT 1 FROM learning_proposals WHERE scope=? AND actor=? AND key=? AND state='suggested'",
                      (scope, person, key)).fetchone():
            return 'already_open', None
        times = [at for _, at in candidate['evidence']]
        record = self._current(db, scope, person, key)
        if record:
            if record['signature'] == candidate['signature']:
                return 'already_accepted', None
            if sum(at > record['accepted'] for at in times) < candidate['threshold']:
                return 'accepted_evidence_unchanged', None
            return None, record['id']
        refused = [r[0] for r in db.execute('''SELECT decided FROM learning_proposals WHERE scope=? AND actor=? AND key=?
            AND state='dismissed' AND decided IS NOT NULL''', (scope, person, key))]
        refused += [r[0] for r in db.execute("SELECT changed FROM learning_records WHERE scope=? AND actor=? AND key=? AND state='retired'",
                                             (scope, person, key))]
        if refused:
            if candidate['origin'] != 'daily_learning':
                # Harvested text is its own evidence: the same content once dismissed stays dismissed.
                return 'dismissed_same_content', None
            if sum(at > max(refused) for at in times) < candidate['threshold']:
                return 'dismissed_evidence_unchanged', None
        return None, None

    def _insert(self, db, p, person, candidate, run_id, supersedes, now):
        identity = 'lp-' + secrets.token_hex(12)
        evidence = [e for e, _ in candidate['evidence']][-MAX_EVIDENCE_IDS:]
        db.execute('INSERT INTO learning_proposals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (identity, p['scope'], person, candidate['kind'], candidate['category'], candidate['key'], candidate['rule'],
                    candidate['signature'], candidate['statement'], _dump(candidate['detail']), _dump(evidence),
                    len(candidate['evidence']), candidate['threshold'], candidate['origin'], run_id, supersedes,
                    'suggested', 1, now, None, None, None, None))
        self.store.log(db, p['scope'], p['id'], 'learning.proposed', identity)
        return dict(db.execute('SELECT * FROM learning_proposals WHERE id=?', (identity,)).fetchone())

    def _offer(self, db, p, candidates, run_id, now, budget, rule=None):
        """Propose what may be proposed, within the budget and capacity. Returns (offered, skipped)."""
        person = ledger(db, p)
        skipped = dict.fromkeys(NOT_PROPOSED, 0)
        offered = []
        open_count = db.execute("SELECT count(*) FROM learning_proposals WHERE scope=? AND actor=? AND state='suggested'",
                                (p['scope'], person)).fetchone()[0]
        for candidate in candidates:
            reason, supersedes = self._standing(db, p['scope'], person, candidate)
            if reason:
                skipped[reason] += 1
                continue
            if budget is not None and len(offered) >= budget:
                # Counted only. A later run may propose it; nothing about it is stored now.
                skipped['proposal_budget'] += 1
                continue
            if open_count >= MAX_OPEN:
                skipped['proposal_capacity'] += 1
                continue
            row = self._insert(db, p, person, candidate, run_id, supersedes, now)
            open_count += 1
            entry = {'proposal': row['id'], 'kind': row['kind'], 'category': row['category'], 'rule': row['rule']}
            if rule is not None and trustable(row['kind'], row['category'], row['origin']) and row['category'] in rule['categories']:
                record = self._accept(db, p, row, 'accepted_by_your_rule', rule)
                open_count -= 1
                entry['accepted_by_rule'] = {'rule': rule['id'], 'version': rule['version'], 'record': record}
            offered.append(entry)
        return offered, skipped

    # The daily run (inside the routine's transaction) -----------------------------

    def run_in(self, db, p, settings, run_id, now):
        """One learning run for the routine. Proposals only, except what the owner's own
        trusted-kinds rule accepts. Returns the run's stored outcome: counts and identifiers."""
        ev = gather(db, p, now)
        today, window = summary(ev, now)
        candidates = derive(db, p, ev, now)
        rule = self._rule(db, p)
        offered, skipped = self._offer(db, p, candidates, run_id, now, settings['nominations_per_run'],
                                       rule if rule and rule['enabled'] else None)
        upstream = self._upstream(db, p, now, run_id)
        self._prune(db, p)
        return {'read': today, 'window': {'days': WINDOW_DAYS, 'evidence': window}, 'candidates': len(candidates),
                'proposed': offered, 'not_proposed': skipped,
                'accepted_by_rule': sum('accepted_by_rule' in o for o in offered),
                'upstream': upstream, 'nothing_due': not offered,
                'budget_note': 'proposals per run come from this routine\'s nominations per run',
                'basis': 'stated_rules_over_value_free_evidence_proposals_only', 'changes_authority': False}

    def _prune(self, db, p):
        person = ledger(db, p)
        db.execute('''DELETE FROM learning_proposals WHERE scope=? AND actor=? AND state!='suggested' AND id IN (SELECT id FROM
            learning_proposals WHERE scope=? AND actor=? AND state!='suggested' ORDER BY decided DESC,id LIMIT -1 OFFSET ?)''',
                   (p['scope'], person, p['scope'], person, KEEP_DECIDED))

    # Upstream watch ---------------------------------------------------------------

    def _manifest(self, entry):
        if entry['status'] != 'copied':
            return 'not_copied'
        if not entry['manifest_sha256']:
            return 'not_listed'
        folder = self.catalogue.parent / 'manifests'
        path = folder / (entry['repository'].replace('/', '__') + '.json')
        try:
            info = os.lstat(path)
        except OSError:
            return 'missing'
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_MANIFEST_BYTES:
            return 'missing'
        key = (str(path), info.st_size, info.st_mtime_ns)
        if key not in self._manifests:
            digest = hashlib.sha256()
            try:
                fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_CLOEXEC', 0))
                with os.fdopen(fd, 'rb') as handle:
                    for block in iter(lambda: handle.read(1 << 20), b''):
                        digest.update(block)
            except OSError:
                return 'missing'
            self._manifests[key] = digest.hexdigest()
        return 'match' if self._manifests[key] == entry['manifest_sha256'] else 'mismatch'

    def compare_upstream(self):
        """Briefs from the catalogue and the owner's file. Reads data; fetches and installs nothing."""
        raw, problem = _read_json(self.catalogue, MAX_CATALOGUE_BYTES)
        if problem:
            return {'status': 'catalogue_unavailable', 'reason': problem}, []
        try:
            entries = catalogue_entries(raw)
        except Fault as exc:
            return {'status': 'catalogue_invalid', 'reason': exc.code}, []
        raw, problem = _read_json(self.upstream_file, MAX_OWNER_FILE_BYTES)
        if problem:
            return {'status': 'no_owner_file' if problem in ('missing', 'not_configured') else 'owner_file_invalid',
                    'reason': problem, 'projects': len(entries)}, []
        try:
            observed, latest = owner_file(raw)
        except Fault as exc:
            return {'status': 'owner_file_invalid', 'reason': exc.code, 'projects': len(entries)}, []
        briefs = []
        for entry in entries:
            known = latest.get(entry['repository'])
            if known is None:
                comparison = 'not_in_owner_file'
            elif known['commit'] is None:
                comparison = 'release_reported_without_commit'
            elif known['commit'] == entry['commit']:
                comparison = 'pinned_matches_latest_known'
            else:
                comparison = 'newer_reported'
            licence_changed = None
            if known and known['licence'] and entry['licence']:
                licence_changed = known['licence'] != entry['licence']
            review = []
            if comparison in ('newer_reported', 'release_reported_without_commit'):
                review += [field for field in ('changed_defaults', 'licence_notes', 'security_notes') if not known[field]]
            briefs.append({'repository': entry['repository'], 'library_status': entry['status'],
                           'pinned_commit': entry['commit'], 'pinned_licence': entry['licence'],
                           'available_commit': known['commit'] if known else None,
                           'available_release': known['release'] if known else None,
                           'reported_licence': known['licence'] if known else None,
                           'comparison': comparison, 'licence_changed': licence_changed,
                           'changed_defaults': known['changed_defaults'] if known else [],
                           'licence_notes': known['licence_notes'] if known else [],
                           'security_notes': known['security_notes'] if known else [],
                           'fields_to_review': review, 'manifest_integrity': self._manifest(entry),
                           'owner_file_observed_on': observed, 'fetched': False, 'installed': False,
                           'adoption': 'separate_owner_approved_step_that_reruns_the_fence_tests'})
        unknown = sorted(set(latest) - {e['repository'] for e in entries})
        return {'status': 'compared', 'projects': len(entries), 'owner_file_observed_on': observed,
                'unknown_projects_in_owner_file': len(unknown)}, briefs

    def _upstream(self, db, p, now, run_id):
        person = ledger(db, p)
        result, briefs = self.compare_upstream()
        written = 0
        for brief in briefs:
            digest = hashlib.sha256(_dump(brief).encode()).hexdigest()
            if db.execute('SELECT 1 FROM learning_upstream_briefs WHERE scope=? AND actor=? AND repository=? AND brief_sha256=?',
                          (p['scope'], person, brief['repository'], digest)).fetchone():
                continue
            db.execute('INSERT INTO learning_upstream_briefs VALUES (?,?,?,?,?,?,?,?)',
                       ('ub-' + secrets.token_hex(12), p['scope'], person, brief['repository'], digest, _dump(brief), run_id, now))
            written += 1
        if written:
            self.store.log(db, p['scope'], p['id'], 'learning.upstream_briefs', run_id or 'manual')
        counts = {}
        for brief in briefs:
            counts[brief['comparison']] = counts.get(brief['comparison'], 0) + 1
        return {**result, 'comparisons': counts, 'briefs_written': written,
                'licence_changed': sum(bool(b['licence_changed']) for b in briefs),
                'manifest_mismatch': sum(b['manifest_integrity'] == 'mismatch' for b in briefs),
                'fetch': FETCH['status'], 'installs': False}

    # Decisions --------------------------------------------------------------------

    def _proposal(self, db, p, identity):
        ident(identity)
        row = db.execute('SELECT * FROM learning_proposals WHERE id=? AND scope=? AND actor=?',
                         (identity, p['scope'], ledger(db, p))).fetchone()
        if not row:
            # Unknown and someone else's look alike.
            raise Fault('learning_not_found', 404)
        return dict(row)

    def _accept(self, db, p, row, decision, rule=None):
        person, now = ledger(db, p), self.store.now()
        prior = self._current(db, p['scope'], person, row['key'])
        if (prior['id'] if prior else None) != row['supersedes']:
            # The record this proposal would replace changed after it was proposed.
            raise Fault('learning_changed', 409)
        if not prior and db.execute("SELECT count(*) FROM learning_records WHERE scope=? AND actor=? AND state='current'",
                                    (p['scope'], person)).fetchone()[0] >= MAX_RECORDS:
            raise Fault('learning_capacity', 409)
        if decision == 'accepted_by_your_rule' and (rule is None or not trustable(row['kind'], row['category'], row['origin'])):
            raise Fault('learning_not_trustable', 403)
        version = (db.execute('SELECT max(version) FROM learning_records WHERE scope=? AND actor=? AND key=?',
                              (p['scope'], person, row['key'])).fetchone()[0] or 0) + 1
        record = 'lrn-' + secrets.token_hex(12)
        db.execute('INSERT INTO learning_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (record, p['scope'], person, row['kind'], row['category'], row['key'], version, row['signature'],
                    row['statement'], row['detail'], row['evidence'], row['origin'], row['id'], row['supersedes'], 'current',
                    now, p['id'], rule['id'] if rule else None, rule['version'] if rule else None, now))
        if prior:
            db.execute("UPDATE learning_records SET state='superseded',changed=? WHERE id=?", (now, prior['id']))
        db.execute('''UPDATE learning_proposals SET state='accepted',version=version+1,decided=?,decided_by=?,decision=?,record_id=?
                      WHERE id=?''', (now, p['id'], decision, record, row['id']))
        self.store.log(db, p['scope'], p['id'], 'learning.accepted_by_rule' if rule else 'learning.accepted', row['id'])
        return record

    def accept(self, bearer, identity, body):
        version = _version(body)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            row = self._proposal(db, p, identity)
            if row['state'] == 'accepted' and row['version'] == version + 1 and row['decision'] == 'accepted_by_you':
                return self._decided(db, p, row['id'])
            if row['version'] != version:
                raise Fault('learning_changed', 409)
            if row['state'] != 'suggested':
                raise Fault('learning_closed', 409)
            self._accept(db, p, row, 'accepted_by_you')
            return self._decided(db, p, row['id'])

    def dismiss(self, bearer, identity, body):
        version = _version(body)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            row = self._proposal(db, p, identity)
            if row['state'] == 'dismissed' and row['version'] == version + 1:
                return self._decided(db, p, row['id'])
            if row['version'] != version:
                raise Fault('learning_changed', 409)
            if row['state'] != 'suggested':
                raise Fault('learning_closed', 409)
            db.execute('''UPDATE learning_proposals SET state='dismissed',version=version+1,decided=?,decided_by=?,decision=?
                          WHERE id=?''', (self.store.now(), p['id'], 'dismissed', row['id']))
            self.store.log(db, p['scope'], p['id'], 'learning.dismissed', row['id'])
            return self._decided(db, p, row['id'])

    def _record(self, db, p, identity):
        if not is_record_id(identity):
            raise Fault('learning_record_not_found', 404)
        row = db.execute('SELECT * FROM learning_records WHERE id=? AND scope=? AND actor=?',
                         (identity, p['scope'], ledger(db, p))).fetchone()
        if not row:
            raise Fault('learning_record_not_found', 404)
        return dict(row)

    def retire(self, bearer, identity, body):
        """The owner takes an accepted learning out of use. Kept, labelled, never sent again."""
        version = _version(body)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            row = self._record(db, p, identity)
            if row['state'] == 'retired' and row['version'] == version:
                return {'record': self._record_view(row)}
            if row['version'] != version or row['state'] != 'current':
                raise Fault('learning_changed', 409)
            db.execute("UPDATE learning_records SET state='retired',changed=? WHERE id=?", (self.store.now(), identity))
            self.store.log(db, p['scope'], p['id'], 'learning.retired', identity)
            return {'record': self._record_view(self._record(db, p, identity))}

    def undo(self, bearer, identity, body):
        """Undo an acceptance made by the trusted-kinds rule. The record is marked undone, a
        learning it replaced is current again, and the proposal returns to the owner's review."""
        version = _version(body)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            row = self._record(db, p, identity)
            if row['state'] == 'undone' and row['version'] == version:
                return {'record': self._record_view(row), 'proposal': self._proposal_view(self._proposal(db, p, row['proposal_id']))}
            if row['trust_rule'] is None:
                raise Fault('learning_not_accepted_by_rule', 409)
            if row['version'] != version or row['state'] != 'current':
                raise Fault('learning_changed', 409)
            now = self.store.now()
            db.execute("UPDATE learning_records SET state='undone',changed=? WHERE id=?", (now, identity))
            if row['supersedes']:
                db.execute("UPDATE learning_records SET state='current',changed=? WHERE id=? AND state='superseded'",
                           (now, row['supersedes']))
            db.execute('''UPDATE learning_proposals SET state='suggested',version=version+1,decided=NULL,decided_by=?,
                          decision='returned_by_undo',record_id=NULL WHERE id=? AND state='accepted' ''',
                       (p['id'], row['proposal_id']))
            self.store.log(db, p['scope'], p['id'], 'learning.undone', identity)
            return {'record': self._record_view(self._record(db, p, identity)),
                    'proposal': self._proposal_view(self._proposal(db, p, row['proposal_id']))}

    def _decided(self, db, p, identity):
        row = self._proposal(db, p, identity)
        result = {'proposal': self._proposal_view(row)}
        if row['record_id']:
            result['record'] = self._record_view(self._record(db, p, row['record_id']))
        return result

    # The trusted-kinds rule -------------------------------------------------------

    @staticmethod
    def _rule(db, p):
        row = db.execute('SELECT * FROM learning_trust_rules WHERE scope=? AND actor=? AND id=?',
                         (p['scope'], ledger(db, p), TRUST_RULE)).fetchone()
        if not row:
            return None
        return {'id': row['id'], 'version': row['version'], 'enabled': bool(row['enabled']),
                'categories': json.loads(row['categories']), 'updated': row['updated']}

    def set_trust_rule(self, bearer, body):
        """Owner only, version-checked and audited. Categories from the closed list only."""
        exact(body, {'version', 'enabled', 'categories'})
        if type(body['version']) is not int or body['version'] < 0 or type(body['enabled']) is not bool:
            raise Fault('invalid_trust_rule')
        categories = body['categories']
        if type(categories) is not list or len(categories) > 16 or len(set(map(str, categories))) != len(categories):
            raise Fault('invalid_trust_rule')
        for category in categories:
            if category not in TRUSTABLE:
                # People, money, commitments, procedures, routing and worker text are never trustable.
                raise Fault('category_not_trustable', 403)
        if body['enabled'] and not categories:
            raise Fault('invalid_trust_rule')
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            rule = self._rule(db, p)
            if (rule['version'] if rule else 0) != body['version']:
                raise Fault('trust_rule_changed', 409)
            now = self.store.now()
            db.execute('''INSERT INTO learning_trust_rules VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(scope,actor,id) DO UPDATE SET
                          version=version+1,enabled=excluded.enabled,categories=excluded.categories,updated=excluded.updated,
                          updated_by=excluded.updated_by''',
                       (p['scope'], ledger(db, p), TRUST_RULE, 1, int(body['enabled']), _dump(sorted(categories)), now, p['id']))
            self.store.log(db, p['scope'], p['id'], 'learning.trust_rule_updated' if rule else 'learning.trust_rule_created', TRUST_RULE)
            return {'trust_rule': self._rule_view(self._rule(db, p))}

    @staticmethod
    def _rule_view(rule):
        base = {'id': TRUST_RULE, 'trustable_categories': [{'id': c, 'label': CATEGORIES[c]} for c in TRUSTABLE],
                'never_trustable': 'People, money, commitments, procedures, routing and anything a worker supplied.',
                'default': 'off'}
        if rule is None:
            return {**base, 'version': 0, 'enabled': False, 'categories': [], 'configured': False}
        return {**base, 'version': rule['version'], 'enabled': rule['enabled'], 'categories': rule['categories'],
                'configured': True, 'updated': rule['updated']}

    # Daily digest and batch approval ----------------------------------------------

    @staticmethod
    def _offset(db, scope):
        if not _has(db, 'routine_settings'):
            return 0
        row = db.execute('SELECT settings FROM routine_settings WHERE scope=? AND kind=?', (scope, ROUTINE_KIND)).fetchone()
        return json.loads(row['settings'])['utc_offset_minutes'] if row else 0

    def digest(self, bearer, day=None):
        """One list per day of the learnings proposed that day, in the routine's local time."""
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            offset, now = self._offset(db, p['scope']), self.store.now()
            start = _day_start(now, offset) if day is None else _parse_day(day, offset)
            return self._digest(db, p, start, offset, now)

    def _digest(self, db, p, start, offset, now):
        person = ledger(db, p)
        rows = [dict(r) for r in db.execute('''SELECT * FROM learning_proposals WHERE scope=? AND actor=? AND created>=? AND created<?
            ORDER BY created,id''', (p['scope'], person, start, start + DAY))]
        items = [self._proposal_view(r, db=db, p=p) for r in rows]
        days = [{'day': _day_text(_day_start(r['created'], offset), offset), 'proposed': r['n']} for r in db.execute(
            f'''SELECT min(created) AS created,count(*) AS n FROM learning_proposals WHERE scope=? AND actor=? AND created>=?
                GROUP BY (created+{int(offset) * 60})/{DAY} ORDER BY created DESC''', (p['scope'], person, now - DIGEST_DAYS * DAY))]
        return {'day': _day_text(start, offset), 'day_start': start, 'utc_offset_minutes': offset, 'items': items,
                'counts': {'proposed': len(items), 'awaiting_review': sum(i['state'] == 'suggested' for i in items),
                           'accepted_by_your_rule': sum(i['decision'] == 'accepted_by_your_rule' for i in items)},
                'approvable': [{'id': i['id'], 'version': i['version']} for i in items if i['state'] == 'suggested'],
                'recent_days': days, 'model_used': False, 'authority_granted': False,
                'basis': 'learning_suggestions_need_review_not_accepted_facts'}

    def approve_batch(self, bearer, body):
        """Accept exactly the listed set from one day's digest. Every item must still be
        awaiting review at the listed version, or nothing is accepted."""
        exact(body, {'day', 'items'})
        items = body['items']
        if type(items) is not list or not 1 <= len(items) <= MAX_BATCH:
            raise Fault('invalid_learning_batch')
        for item in items:
            exact(item, {'id', 'version'})
            ident(item['id'])
            if type(item['version']) is not int or item['version'] < 1:
                raise Fault('invalid_learning_batch')
        if len({i['id'] for i in items}) != len(items):
            raise Fault('invalid_learning_batch')
        batch = 'lb-' + hashlib.sha256(_dump({'day': body['day'], 'items': sorted(items, key=lambda i: i['id'])}).encode()).hexdigest()[:24]
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            offset = self._offset(db, p['scope'])
            start = _parse_day(body['day'], offset)
            rows = []
            for item in items:
                try:
                    row = self._proposal(db, p, item['id'])
                except Fault:
                    raise Fault('learning_not_in_digest', 409) from None
                if not start <= row['created'] < start + DAY:
                    raise Fault('learning_not_in_digest', 409)
                rows.append((item, row))
            if all(r['state'] == 'accepted' and r['decision'] == 'accepted_in_batch' and r['version'] == i['version'] + 1
                   for i, r in rows):
                # The same batch sent again returns its recorded result.
                return {'batch': batch, 'accepted': [r['record_id'] for _, r in rows], 'repeated': True,
                        'digest': self._digest(db, p, start, offset, self.store.now())}
            for item, row in rows:
                if row['state'] != 'suggested' or row['version'] != item['version']:
                    raise Fault('learning_changed', 409)
            accepted = [self._accept(db, p, row, 'accepted_in_batch') for _, row in rows]
            self.store.log(db, p['scope'], p['id'], 'learning.batch_accepted', batch)
            return {'batch': batch, 'accepted': accepted, 'repeated': False,
                    'digest': self._digest(db, p, start, offset, self.store.now())}

    # Harvest ------------------------------------------------------------------------

    def _harvest_result(self, db, p, job):
        ident(job)
        if not _has(db, 'brain_results'):
            raise Fault('harvest_result_not_found', 404)
        creds = _creds(db, p)
        row = db.execute(f'''SELECT r.*,t.brain FROM brain_results r JOIN brain_tasks t ON t.job_id=r.job_id
            WHERE r.job_id=? AND r.scope=? AND r.actor IN ({_marks(creds)})''', (job, p['scope'], *creds)).fetchone()
        if not row:
            raise Fault('harvest_result_not_found', 404)
        if row['status'] != 'accepted':
            # A refused or stopped result is not a source of anything, harvested or otherwise.
            raise Fault('harvest_result_not_accepted', 409)
        return dict(row)

    @staticmethod
    def _harvest_text(content, sha256):
        if not isinstance(content, str) or not 1 <= len(content) <= MAX_HARVEST_TEXT or not content.strip():
            raise Fault('harvest_content_too_long' if isinstance(content, str) and len(content) > MAX_HARVEST_TEXT
                        else 'invalid_harvest_item')
        if any((ord(c) < 32 and c not in '\n\t') or 127 <= ord(c) < 160 for c in content):
            raise Fault('control_character')
        if not isinstance(sha256, str) or not SHA256.fullmatch(sha256) or hashlib.sha256(content.encode('utf-8')).hexdigest() != sha256:
            raise Fault('harvest_hash_mismatch', 409)
        if _credential_shaped(content):
            raise Fault('credential_shaped_value_in_harvest', 409)
        return content

    def _harvest(self, bearer, job, items, origin):
        # The hash and the refusals above were checked on the text as supplied, so the
        # artefact is still the one recorded; what is proposed is the scrubbed text.
        from .scrub import scrub
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            result = self._harvest_result(db, p, job)
            candidates, scrubbed = [], {}
            for item in items(result):
                evidence = [{'id': f'brain_result:{job}', 'at': result['created']},
                            {'id': f'artefact:{item["sha256"]}', 'at': result['created']}]
                (content, found), (name, named) = scrub(item['content']), scrub(item['name'])
                counts = {}
                for finding in found + named:
                    counts[finding.kind] = counts.get(finding.kind, 0) + 1
                    scrubbed[finding.kind] = scrubbed.get(finding.kind, 0) + 1
                detail = {'brain': result['brain'], 'job': job, 'name': name, 'sha256': item['sha256'], 'source': origin,
                          'basis': 'worker_text_needs_review_never_run'}
                if counts:
                    detail['scrubbed'] = dict(sorted(counts.items()))
                candidates.append(_candidate(item['kind'], item['category'], origin, 'harvest:' + item['sha256'], item['sha256'],
                                             content, detail, evidence, threshold=1, origin=origin))
            offered, skipped = self._offer(db, p, candidates, None, self.store.now(), None)
            return {'proposed': offered, 'not_proposed': skipped, 'auto_accepted': 0, 'executed': False,
                    'scrubbed': dict(sorted(scrubbed.items())), 'basis': 'harvested_worker_text_is_a_proposal_only'}

    def harvest(self, bearer, body):
        """Text artefacts of an accepted brain result become proposals only. Each artefact
        must be one the result recorded, with the same SHA-256 as its content."""
        exact(body, {'job', 'artefacts'})
        artefacts = body['artefacts']
        if type(artefacts) is not list or not 1 <= len(artefacts) <= MAX_HARVEST_ITEMS:
            raise Fault('invalid_harvest_item')

        def items(result):
            recorded = {a['name']: a for a in json.loads(result['outcome']).get('artefacts', [])}
            chosen = []
            for item in artefacts:
                exact(item, {'name', 'sha256', 'content', 'as'})
                if item['as'] not in ('procedure', 'preference'):
                    raise Fault('invalid_harvest_item')
                known = recorded.get(item['name']) if isinstance(item['name'], str) else None
                if not known or known['sha256'] != item['sha256'] or known['media_type'] not in ('text/markdown', 'text/plain'):
                    raise Fault('harvest_artefact_not_in_result', 409)
                chosen.append({'kind': item['as'], 'category': 'worker_note', 'name': item['name'], 'sha256': item['sha256'],
                               'content': self._harvest_text(item['content'], item['sha256'])})
            return chosen
        return self._harvest(bearer, body['job'], items, 'harvest_artefact')

    def harvest_staged(self, bearer, body):
        """Skills and memories a worker staged for approval (for example in a write-approval
        staging mode) become proposals in the same inbox. Never written, run or trusted."""
        exact(body, {'job', 'staged'})
        staged = body['staged']
        if type(staged) is not list or not 1 <= len(staged) <= MAX_HARVEST_ITEMS:
            raise Fault('invalid_harvest_item')

        def items(_result):
            chosen = []
            for item in staged:
                exact(item, {'target', 'name', 'sha256', 'content'})
                if item['target'] not in ('skill', 'memory'):
                    raise Fault('invalid_harvest_item')
                text(item['name'], 120)
                kind, category = ('procedure', 'worker_skill') if item['target'] == 'skill' else ('preference', 'worker_memory')
                chosen.append({'kind': kind, 'category': category, 'name': item['name'], 'sha256': item['sha256'],
                               'content': self._harvest_text(item['content'], item['sha256'])})
            return chosen
        return self._harvest(bearer, body['job'], items, 'harvest_staged')

    # Packets ------------------------------------------------------------------------

    @staticmethod
    def _packet_statement(row):
        """A record's statement as one line for a packet, or None when it cannot be sent."""
        if row['kind'] not in PACKET_KINDS or row['state'] != 'current':
            return None
        statement = _one_line(row['statement'])
        if not 1 <= len(statement) <= PACKET_STATEMENT or _credential_shaped(statement):
            return None
        try:
            text(statement, PACKET_STATEMENT)
        except Fault:
            return None
        return statement

    def select_learned(self, bearer, *, kinds=PACKET_KINDS, limit=None, characters=None):
        """Record identifiers for a packet's ``learned`` field, within H1's limits: current,
        owner-accepted preferences and procedures of the caller's person, newest first."""
        from .brain import MAX_LEARNED, MAX_LEARNED_CHARACTERS
        limit = MAX_LEARNED if limit is None else limit
        characters = MAX_LEARNED_CHARACTERS if characters is None else characters
        if type(limit) is not int or not 0 <= limit <= MAX_LEARNED or type(characters) is not int or not 0 <= characters <= MAX_LEARNED_CHARACTERS:
            raise Fault('invalid_learned')
        if type(kinds) not in (tuple, list) or any(k not in PACKET_KINDS for k in kinds):
            raise Fault('invalid_learned')
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            chosen, total = [], 0
            for row in db.execute(f'''SELECT * FROM learning_records WHERE scope=? AND actor=? AND state='current'
                    AND kind IN ({_marks(kinds) if kinds else "''"}) ORDER BY kind,accepted DESC,id''',
                                  (p['scope'], ledger(db, p), *kinds)):
                statement = self._packet_statement(dict(row))
                if statement is None or len(chosen) >= limit or total + len(statement) > characters:
                    continue
                chosen.append(row['id'])
                total += len(statement)
            return chosen

    # Views ---------------------------------------------------------------------------

    def procedure_registry(self, bearer):
        """Learned procedure drafts for the procedure registry (MEM-015): every version the
        owner accepted, and drafts awaiting review. To be read; nothing here runs."""
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            person = ledger(db, p)
            items = [{'id': r['id'], 'key': r['key'], 'version': r['version'], 'state': r['state'], 'statement': r['statement'],
                      'origin': r['origin'], 'supersedes': r['supersedes'], 'accepted': r['accepted'],
                      'review_state': 'accepted', 'executable': False, 'grants_authority': False,
                      'basis': 'owner_accepted_procedure_draft_not_instruction'}
                     for r in db.execute('''SELECT * FROM learning_records WHERE scope=? AND actor=? AND kind='procedure'
                        ORDER BY key,version DESC LIMIT 64''', (p['scope'], person))]
            items += [{'id': r['id'], 'key': r['key'], 'version': None, 'state': 'draft_awaiting_review', 'statement': r['statement'],
                       'origin': r['origin'], 'supersedes': r['supersedes'], 'accepted': None, 'review_state': 'suggested',
                       'executable': False, 'grants_authority': False, 'basis': 'learning_suggestion_needs_review_not_instruction'}
                      for r in db.execute('''SELECT * FROM learning_proposals WHERE scope=? AND actor=? AND kind='procedure'
                        AND state='suggested' ORDER BY created DESC,id LIMIT 64''', (p['scope'], person))]
            return items

    @staticmethod
    def _proposal_view(row, db=None, p=None):
        view = {'id': row['id'], 'version': row['version'], 'kind': row['kind'], 'category': row['category'],
                'category_label': CATEGORIES.get(row['category'], row['category']), 'key': row['key'], 'rule': row['rule'],
                'statement': row['statement'], 'detail': json.loads(row['detail']), 'evidence': json.loads(row['evidence']),
                'evidence_total': row['evidence_total'], 'threshold': row['threshold'], 'origin': row['origin'],
                'run': row['run_id'], 'supersedes': row['supersedes'], 'state': row['state'], 'created': row['created'],
                'decided': row['decided'], 'decision': row['decision'],
                'decision_label': DECISIONS.get(row['decision']) if row['decision'] else 'Awaiting your review',
                'record': row['record_id'], 'trustable': trustable(row['kind'], row['category'], row['origin']),
                'basis': 'learning_suggestion_needs_review_not_accepted_fact', 'executable': False, 'authority_granted': False}
        if db is not None and row['record_id']:
            record = db.execute('SELECT state,version,trust_rule,trust_rule_version FROM learning_records WHERE id=?',
                                (row['record_id'],)).fetchone()
            if record:
                view['record_state'] = record['state']
                view['record_version'] = record['version']
                if record['trust_rule']:
                    view['accepted_by_rule'] = {'rule': record['trust_rule'], 'version': record['trust_rule_version']}
                view['undo_available'] = bool(record['trust_rule'] and record['state'] == 'current')
        return view

    def _record_view(self, row):
        return {'id': row['id'], 'version': row['version'], 'kind': row['kind'], 'category': row['category'],
                'category_label': CATEGORIES.get(row['category'], row['category']), 'key': row['key'],
                'statement': row['statement'], 'detail': json.loads(row['detail']), 'evidence': json.loads(row['evidence']),
                'origin': row['origin'], 'proposal': row['proposal_id'], 'supersedes': row['supersedes'], 'state': row['state'],
                'accepted': row['accepted'], 'accepted_by': 'your_rule' if row['trust_rule'] else 'you',
                'trust_rule': {'id': row['trust_rule'], 'version': row['trust_rule_version']} if row['trust_rule'] else None,
                'changed': row['changed'], 'sent_to_brains': self._packet_statement(row) is not None,
                'executable': False, 'authority_granted': False, 'basis': 'owner_accepted_learning_not_verified_fact'}

    def view(self, bearer):
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            person, now = ledger(db, p), self.store.now()
            proposals = [self._proposal_view(dict(r), db=db, p=p) for r in db.execute(
                '''SELECT * FROM learning_proposals WHERE scope=? AND actor=? AND (state='suggested' OR id IN (SELECT id FROM
                   learning_proposals WHERE scope=? AND actor=? AND state!='suggested' ORDER BY decided DESC,id LIMIT 20))
                   ORDER BY state!='suggested',created DESC,id''', (p['scope'], person, p['scope'], person))]
            records = [self._record_view(dict(r)) for r in db.execute(
                '''SELECT * FROM learning_records WHERE scope=? AND actor=? AND (state='current' OR id IN (SELECT id FROM
                   learning_records WHERE scope=? AND actor=? AND state!='current' ORDER BY changed DESC,id LIMIT 20))
                   ORDER BY state!='current',kind,accepted DESC,id''', (p['scope'], person, p['scope'], person))]
            briefs = [json.loads(r['brief']) | {'written': r['created']} for r in db.execute(
                '''SELECT b.brief,b.created FROM learning_upstream_briefs b WHERE b.scope=? AND b.actor=? AND b.created=(SELECT
                   max(created) FROM learning_upstream_briefs c WHERE c.scope=b.scope AND c.actor=b.actor AND c.repository=b.repository)
                   ORDER BY b.repository LIMIT 500''', (p['scope'], person))]
            latest = None
            if _has(db, 'routine_runs'):
                row = db.execute('SELECT id,started,status,skipped_reason,outcome FROM routine_runs WHERE scope=? AND kind=? AND actor IN ('
                                 + _marks(_creds(db, p)) + ') ORDER BY started DESC,rowid DESC LIMIT 1',
                                 (p['scope'], ROUTINE_KIND, *_creds(db, p))).fetchone()
                if row:
                    latest = {'id': row['id'], 'started': row['started'], 'status': row['status'],
                              'skipped_reason': row['skipped_reason'], 'outcome': json.loads(row['outcome'])}
            return {'scope': p['scope'], 'now': now, 'proposals': proposals, 'records': records,
                    'counts': {'awaiting_review': sum(x['state'] == 'suggested' for x in proposals),
                               'current_records': sum(r['state'] == 'current' for r in records)},
                    'trust_rule': self._rule_view(self._rule(db, p)), 'upstream': {'briefs': briefs, 'fetch': FETCH},
                    'latest_run': latest, 'rules': list(ROUTINE_RULES), 'categories': CATEGORIES,
                    'limits': {'window_days': WINDOW_DAYS, 'minimum_evidence': MIN_EVIDENCE, 'open_proposals': MAX_OPEN,
                               'records': MAX_RECORDS, 'batch': MAX_BATCH, 'packet_statement': PACKET_STATEMENT},
                    'model_used': False, 'auto_accept': 'only_by_your_trusted_kinds_rule', 'authority_granted': False,
                    'changes_authority': False, 'basis': 'stated_rules_over_value_free_evidence'}


def packet_statements(store, bearer, identities):
    """Current, sendable learning records for H1's packet ``learned`` field: id to version
    and one-line statement. Anything else is refused, as an unusable reviewed statement is."""
    if not identities:
        return {}
    with store.transaction() as db:
        p = store.authenticate(db, bearer, {'owner'})
        found = {}
        for identity in identities:
            row = db.execute('SELECT * FROM learning_records WHERE id=? AND scope=? AND actor=?',
                             (identity, p['scope'], ledger(db, p))).fetchone() if is_record_id(identity) else None
            statement = Learning._packet_statement(dict(row)) if row else None
            if statement is None:
                raise Fault('learned_not_usable', 409)
            found[identity] = {'version': row['version'], 'statement': statement}
        return found


# HTTP ------------------------------------------------------------------------------

PROPOSAL_OPERATION = re.compile(r'/desk/learning/proposals/([A-Za-z0-9][A-Za-z0-9_.-]{0,79})/(accept|dismiss)')
RECORD_OPERATION = re.compile(r'/desk/learning/records/(lrn-[0-9a-f]{24})/(retire|undo)')
DIGEST_DAY = re.compile(r'/desk/learning/digest/([0-9]{4}-[0-9]{2}-[0-9]{2})')


def route(server, path, mutation, bearer, body):
    """Reached only through the guarded desk handler (loopback Host/Origin, session, CSRF)."""
    learning = getattr(server, 'learning', None)
    if learning is None:
        raise Fault('learning_not_configured', 409)
    if not mutation:
        if path == '/desk/learning':
            return learning.view(bearer)
        if path == '/desk/learning/digest':
            return learning.digest(bearer)
        match = DIGEST_DAY.fullmatch(path)
        if match:
            return learning.digest(bearer, match[1])
        raise Fault('not_found', 404)
    if path == '/desk/learning/run':
        routines = getattr(server, 'routines', None)
        if routines is None:
            raise Fault('routines_not_configured', 409)
        # Run now goes through the routine, so its pause, budgets and authority apply.
        return routines.manual(bearer, ROUTINE_KIND, body)
    if path == '/desk/learning/digest/approve':
        return learning.approve_batch(bearer, body)
    if path == '/desk/learning/trust':
        return learning.set_trust_rule(bearer, body)
    match = PROPOSAL_OPERATION.fullmatch(path)
    if match:
        return (learning.accept if match[2] == 'accept' else learning.dismiss)(bearer, match[1], body)
    match = RECORD_OPERATION.fullmatch(path)
    if match:
        return (learning.retire if match[2] == 'retire' else learning.undo)(bearer, match[1], body)
    raise Fault('not_found', 404)
