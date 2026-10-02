"""Recorded time for reviewed statements (MEM-007): an append-only review history.

Each row says which state a statement entered, when ALFRED recorded it and who made the
change: the reviewer, or ALFRED itself for an invalidation or an availability change. Rows
hold identifiers, states, times and the valid period only, never a statement's value, so
forgetting a statement, and replaying that forget on restore, leaves no value here.
Valid time stays on the statement (valid_from, valid_until, half-open).

Where a row came from:
  recorded  written in the same transaction as the change it describes
  observed  ALFRED noticed the support become unavailable (or available again) when it
            next looked; the actual change may have happened earlier
  migrated  reconstructed once from earlier records: the statement's own creation and
            review times and the audit log. A time that cannot be known is never
            invented: such a row has time_known=0 and its time is the latest moment the
            change could have happened (the review time, or the migration itself)
  replayed  a forget or source removal replayed from the lifecycle journal on restore,
            at the time the journal recorded

The as-of report is a historical report of ALFRED's own review records for one person.
It is not a statement about the world, and it never changes what current answers use:
those still take only accepted, current, authorised and valid statements.
"""
from __future__ import annotations
from .local import Fault, ident, timestamp

VERSION = 1
REVIEW_STATES = ('proposed', 'accepted', 'disputed', 'withdrawn', 'superseded', 'invalidated', 'forgotten')
AVAILABILITY = ('withheld', 'restored')
MAX_HISTORY_PER_CLAIM = 200
SCHEMA = '''
CREATE TABLE IF NOT EXISTS memory_history_meta(version INTEGER NOT NULL, migrated INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS memory_claim_history(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, actor TEXT NOT NULL,
 claim_id TEXT NOT NULL, state TEXT NOT NULL, at INTEGER NOT NULL, time_known INTEGER NOT NULL,
 by TEXT NOT NULL, origin TEXT NOT NULL, related_id TEXT, detail TEXT,
 sets_valid INTEGER NOT NULL, valid_from INTEGER, valid_until INTEGER);
CREATE INDEX IF NOT EXISTS memory_claim_history_claim ON memory_claim_history(scope,actor,claim_id,seq);
'''
AUDIT_STATES = {'memory.accepted': 'accepted', 'memory.disputed': 'disputed', 'memory.withdrawn': 'withdrawn',
                'memory.superseded': 'superseded', 'memory.invalidated': 'invalidated',
                'lifecycle.claim_forgotten': 'forgotten'}
SYSTEM = 'alfred'
BASIS = 'alfred_review_records_not_a_claim_about_the_world'
LABEL = ("A historical report from ALFRED's own review records: what you had accepted on that date. "
         'It is not a statement about what was true in the world.')


def _has(db, table):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def record(db, scope, actor, claim_id, state, at, by, *, origin='recorded', related=None, detail=None,
           time_known=True, valid=None):
    """Append one row in the caller's transaction. Never takes a value."""
    if state not in REVIEW_STATES + AVAILABILITY:
        raise Fault('invalid_memory_history_state')
    valid_from, valid_until = valid if valid is not None else (None, None)
    db.execute('''INSERT INTO memory_claim_history(scope,actor,claim_id,state,at,time_known,by,origin,related_id,detail,sets_valid,valid_from,valid_until)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
               (scope, actor, claim_id, state, int(at), int(bool(time_known)), by, origin, related, detail,
                int(valid is not None), valid_from, valid_until))


def record_if_present(db, scope, actor, claim_id, state, at, by, **kw):
    """For lifecycle paths that may run against a database (or restored backup) without history."""
    if _has(db, 'memory_claim_history'):
        record(db, scope, actor, claim_id, state, at, by, **kw)


def count(db, scope, actor, claim_id):
    return db.execute('SELECT count(*) FROM memory_claim_history WHERE scope=? AND actor=? AND claim_id=?',
                      (scope, actor, claim_id)).fetchone()[0]


def initialise(store):
    """Create the history and, once, migrate statements that predate it."""
    with store.connection() as db:
        db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
    with store.transaction() as db:
        rows = [r[0] for r in db.execute('SELECT version FROM memory_history_meta')]
        if rows and rows != [VERSION]:
            raise Fault('unsupported_memory_history_version')
        if not rows:
            now = store.now()
            migrate(db, now)
            db.execute('INSERT INTO memory_history_meta VALUES (?,?)', (VERSION, now))


def migrate(db, now):
    """Record only what earlier records can show, marked as migrated.

    The proposal time comes from the statement itself. Later transitions come from the
    audit log, which names the statement, the kind of change and the time. Where the
    audit cannot show a change (for example an invalidation by whole-source removal),
    the current state is recorded as reached no later than now, with its time unknown.
    """
    claims = [dict(r) for r in db.execute('''SELECT c.* FROM memory_claims c WHERE NOT EXISTS(
        SELECT 1 FROM memory_claim_history h WHERE h.claim_id=c.id AND h.scope=c.scope AND h.actor=c.actor)
        ORDER BY c.created,c.id''')]
    replaced_by = {}
    for r in db.execute('SELECT id,replaces_id FROM memory_claims WHERE replaces_id IS NOT NULL'):
        replaced_by.setdefault(r['replaces_id'], []).append(r['id'])
    for c in claims:
        scope, actor, cid = c['scope'], c['actor'], c['id']

        def add(state, at, by, known=True, detail=None, related=None, valid=None):
            record(db, scope, actor, cid, state, at, by, origin='migrated', time_known=known, detail=detail,
                   related=related, valid=valid)
        add('proposed', c['created'], actor, detail='from_statement_record', valid=(c['valid_from'], c['valid_until']))
        last = 'proposed'
        audited = db.execute(f'''SELECT kind,at FROM audit WHERE scope=? AND actor=? AND subject=?
            AND kind IN ({','.join('?' * len(AUDIT_STATES))}) ORDER BY seq''', (scope, actor, cid, *AUDIT_STATES)).fetchall()
        for row in audited:
            state = AUDIT_STATES[row['kind']]
            if state == last:
                continue
            by = SYSTEM if state == 'invalidated' else actor
            related = None
            if state == 'superseded' and len(replaced_by.get(cid, [])) == 1:
                related = replaced_by[cid][0]
            add(state, row['at'], by, detail='from_audit_log', related=related)
            last = state
        if not audited and c['reviewed'] is not None and c['state'] in ('accepted', 'disputed', 'withdrawn', 'superseded'):
            # The last review time is known; whether an earlier review preceded it is not.
            add(c['state'], c['reviewed'], c['reviewer'] or actor, known=False, detail='last_review_time_from_statement_record')
            last = c['state']
        if last != c['state']:
            add(c['state'], now, SYSTEM if c['state'] in ('invalidated', 'forgotten') else actor, known=False,
                detail='state_found_at_migration')


def rows(db, scope, actor, claim_id=None):
    sql = 'SELECT * FROM memory_claim_history WHERE scope=? AND actor=?'
    args = [scope, actor]
    if claim_id is not None:
        sql += ' AND claim_id=?'; args.append(claim_id)
    result = {}
    for r in db.execute(sql + ' ORDER BY seq', args):
        result.setdefault(r['claim_id'], []).append(dict(r))
    return result


def observe(db, p, claims, now):
    """Note when support became unavailable or available again, as ALFRED noticed it.

    Withheld is not invalidated: nothing about the review changes, and its value is
    hidden while the support cannot be read. Only the change is recorded, once.
    """
    last = {}
    for r in db.execute('''SELECT claim_id,state FROM memory_claim_history WHERE scope=? AND actor=?
                           AND state IN ('withheld','restored') ORDER BY seq''', (p['scope'], p['id'])):
        last[r['claim_id']] = r['state']
    for c in claims:
        if c['state'] in ('invalidated', 'forgotten'):
            continue
        before = last.get(c['id'])
        if c['withheld'] and before != 'withheld':
            state = 'withheld'
        elif not c['withheld'] and before == 'withheld':
            state = 'restored'
        else:
            continue
        if count(db, p['scope'], p['id'], c['id']) < MAX_HISTORY_PER_CLAIM:
            record(db, p['scope'], p['id'], c['id'], state, now, SYSTEM, origin='observed',
                   detail='support_unavailable_or_not_permitted' if state == 'withheld' else 'support_readable_again')


def state_at(entries, at):
    """Review state at a recorded time, from history alone.

    Returns (state, certain, since, since_known). A row with an unknown time marks a change
    that happened no later than its time; before that time the state is uncertain.
    """
    state, since, known = None, None, True
    for e in entries:
        if e['state'] in AVAILABILITY:
            continue
        if e['at'] <= at:
            state, since, known = e['state'], e['at'], bool(e['time_known'])
            continue
        if not e['time_known']:
            return state, False, since, known
        break
    return state, True, since, known


def availability_at(entries, at):
    state = None
    for e in entries:
        if e['state'] in AVAILABILITY and e['at'] <= at:
            state = e['state']
    return 'withheld_noticed' if state == 'withheld' else None


def valid_at(claim, moment):
    return (claim['valid_from'] is None or claim['valid_from'] <= moment) and (
        claim['valid_until'] is None or claim['valid_until'] > moment)


def hidden(claim):
    """Why a value is not shown now: forgotten and invalidated values are gone; withheld ones are hidden."""
    if claim['state'] == 'forgotten':
        return 'forgotten'
    if claim['state'] == 'invalidated':
        return 'support_changed'
    if claim.get('withheld'):
        return 'withheld'
    return None


def _entity(entities, identity):
    return {k: entities[identity][k] for k in ('id', 'kind', 'name')} if identity in entities else None


def summary(claim, entities):
    reason = hidden(claim)
    return {'claim_id': claim['id'], 'version': claim['version'], 'state': claim['state'],
            'subject': _entity(entities, claim['subject_id']), 'predicate': claim['predicate'],
            'value': None if reason else claim['value'],
            'object': None if reason else _entity(entities, claim['object_id']),
            'value_hidden': reason, 'valid_from': claim['valid_from'], 'valid_until': claim['valid_until'],
            'recorded': claim['created'], 'reviewed': claim['reviewed'], 'replaces_id': claim['replaces_id']}


def lineage(claims, identity):
    """The explicit replacement chain, both ways. Lineage comes only from recorded supersessions."""
    by_id = {c['id']: c for c in claims}
    replaced_by = {c['replaces_id']: c['id'] for c in claims if c['replaces_id']}
    back, forward, seen = [], [], {identity}
    current = by_id[identity]['replaces_id']
    while current in by_id and current not in seen:
        back.append(current); seen.add(current); current = by_id[current]['replaces_id']
    current = replaced_by.get(identity)
    while current in by_id and current not in seen:
        forward.append(current); seen.add(current); current = replaced_by.get(current)
    return back, forward


def _entry_view(e, p):
    return {'seq': e['seq'], 'state': e['state'], 'at': e['at'], 'time_known': bool(e['time_known']),
            'by': 'you' if e['by'] == p['id'] else 'alfred' if e['by'] == SYSTEM else 'another_credential',
            'origin': e['origin'], 'related_id': e['related_id'], 'detail': e['detail'],
            # Only a proposal, or a decision that set the period, records a valid period.
            'valid_period': {'from': e['valid_from'], 'until': e['valid_until']} if e['sets_valid'] else None}


class MemoryHistory:
    """Read-side views over the history. Every call rechecks authority and source support
    through the same snapshot as the reviewed-memory view."""

    def __init__(self, memory):
        self.memory, self.store = memory, memory.store

    def history(self, bearer, identity):
        ident(identity)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            entities, claims = self.memory._snapshot(db, p, self.store.now())
            found = [c for c in claims if c['id'] == identity]
            if not found:
                # Unknown and another person's statements are indistinguishable.
                raise Fault('memory_claim_not_found', 404)
            claim = found[0]
            entries = rows(db, p['scope'], p['id'], identity).get(identity, [])
            back, forward = lineage(claims, identity)
            by_id = {c['id']: c for c in claims}
            return {'claim': summary(claim, entities) | {'usable': claim['usable'], 'conflicts': claim['conflicts'],
                                                         'withheld': bool(claim['withheld'])},
                    'entries': [_entry_view(e, p) for e in entries],
                    'recorded_from_start': bool(entries) and entries[0]['origin'] != 'migrated',
                    'times_unknown': sum(not e['time_known'] for e in entries),
                    'lineage': {'replaces': [summary(by_id[i], entities) for i in back],
                                'replaced_by': [summary(by_id[i], entities) for i in forward]},
                    'basis': 'recorded_review_history_without_values', 'values_in_history': False,
                    'authority_granted': False}

    def as_of(self, bearer, at, valid=None):
        timestamp(at)
        if valid is not None:
            timestamp(valid)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            now = self.store.now()
            entities, claims = self.memory._snapshot(db, p, now)
            moment = min(at, now)
            when_valid = valid if valid is not None else moment
            history = rows(db, p['scope'], p['id'])
            replaced_by = {c['replaces_id']: c['id'] for c in claims if c['replaces_id']}
            held, outside, uncertain = [], [], []
            not_held = {s: 0 for s in REVIEW_STATES if s != 'accepted'}
            later = missing = 0
            for c in claims:
                entries = history.get(c['id'])
                if not entries:
                    missing += 1
                    continue
                state, certain, since, since_known = state_at(entries, moment)
                item = summary(c, entities) | {'state_now': c['state'], 'replaced_by': replaced_by.get(c['id']),
                                               'since': since, 'since_known': since_known,
                                               'availability_then': availability_at(entries, moment)}
                if not certain:
                    uncertain.append(item | {'state_then': state})
                elif state is None:
                    later += 1
                elif state != 'accepted':
                    not_held[state] += 1
                elif valid_at(c, when_valid):
                    held.append((c, item))
                else:
                    outside.append(item)
            from .reviewed_memory import RELATIONS, overlap
            for c, item in held:
                # The structural single-value rule, applied to what was held then. A value
                # removed or withheld now is not compared, so that pairing is only a possibility.
                conflicts, possible = [], []
                for other, _ in held:
                    if other is c or not RELATIONS[c['predicate']]['single'] or (other['subject_id'], other['predicate']) != (c['subject_id'], c['predicate']) or not overlap(c, other):
                        continue
                    if hidden(c) or hidden(other):
                        # Never compare a value that is gone or hidden now.
                        possible.append(other['id'])
                    elif (other['object_id'], other['value']) != (c['object_id'], c['value']):
                        conflicts.append(other['id'])
                item['conflicts_then'], item['possible_conflicts_then'] = conflicts, possible
            order = lambda x: ((x['subject'] or {}).get('name', '').casefold(), (x['subject'] or {}).get('id') or '',
                               x['predicate'], x['since'] or 0, x['claim_id'])
            return {'kind': 'historical_report', 'basis': BASIS, 'label': LABEL,
                    'at': moment, 'valid_at': when_valid, 'requested_at': at, 'clamped_to_now': at > now, 'generated_at': now,
                    'held': sorted((item for _, item in held), key=order), 'accepted_outside_valid_period': sorted(outside, key=order),
                    'uncertain': sorted(uncertain, key=order),
                    'not_held': not_held, 'not_yet_recorded': later, 'without_history': missing,
                    'current_answers': 'Current answers still use only accepted, current, authorised and valid statements.',
                    'model_used': False, 'authority_granted': False}


def route(history, path, mutation, bearer):
    """GET /desk/memory/claims/{id}/history, /desk/memory/as-of/{t} and /desk/memory/as-of/{t}/valid/{v}."""
    import re
    if mutation:
        raise Fault('not_found', 404)
    match = re.fullmatch(r'/desk/memory/claims/([A-Za-z0-9][A-Za-z0-9_.-]{0,79})/history', path)
    if match:
        return history.history(bearer, match.group(1))
    match = re.fullmatch(r'/desk/memory/as-of/([0-9]{1,16})(?:/valid/([0-9]{1,16}))?', path)
    if match:
        return history.as_of(bearer, int(match.group(1)), int(match.group(2)) if match.group(2) else None)
    raise Fault('not_found', 404)
