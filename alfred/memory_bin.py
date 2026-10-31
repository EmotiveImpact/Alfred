"""The bin for ordinary forgets (M05, the owner's rule of 22 October 2026).

An ordinary forget of a reviewed statement or a record keeps a copy here for 30 days so
the owner can undo it: the values the forget cleared and, for a record, its name. Only
the owner sees their bin. An absolute forget removes every copy that holds its subject,
and copies leave on their own once the 30 days pass. Undo puts back what the forget
cleared; answers and drafts the forget withdrew stay withdrawn.

The bin is separate from backups: a restore from an older backup brings an ordinary
forget back whether or not the bin still holds it (alfred/lifecycle.py).
"""
from __future__ import annotations
import json
import secrets
from .local import Fault

DAYS = 30
SECONDS = DAYS * 86400
SCHEMA = '''
CREATE TABLE IF NOT EXISTS memory_bin(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, kind TEXT NOT NULL,
 subject TEXT NOT NULL, deleted INTEGER NOT NULL, expires INTEGER NOT NULL,
 receipt TEXT NOT NULL, snapshot TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS memory_bin_owner ON memory_bin(scope,actor);
'''
KIND = {'claim_forgotten': 'statement', 'entity_forgotten': 'entity'}
FORGET = {v: k for k, v in KIND.items()}
CLAIM = ('id', 'state', 'predicate', 'subject_id', 'object_id', 'value', 'note_id')


def _has(db):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_bin'").fetchone())


def snapshot(db, scope, keys, kind, subject):
    """What an ordinary forget is about to clear, read before it clears it."""
    within = f"actor IN ({','.join('?' * len(keys))})"
    names = {r[0]: r[1] for r in db.execute(f'SELECT id,name FROM memory_entities WHERE scope=? AND {within}', (scope, *keys))}
    if kind == 'claim_forgotten':
        rows = db.execute(f"SELECT {','.join(CLAIM)} FROM memory_claims WHERE id=? AND scope=? AND {within} AND state!='forgotten'",
                          (subject, scope, *keys)).fetchall()
        claims = [dict(r) for r in rows]
        c = claims[0] if claims else {'subject_id': None, 'predicate': None, 'value': None, 'object_id': None}
        return {'claims': claims, 'entity': None, 'label': _label(c, names)}
    entity = db.execute(f'SELECT id,kind,name,created FROM memory_entities WHERE id=? AND scope=? AND {within}',
                        (subject, scope, *keys)).fetchone()
    claims = [dict(r) for r in db.execute(f"SELECT {','.join(CLAIM)} FROM memory_claims WHERE scope=? AND {within} "
                                          "AND (subject_id=? OR object_id=?) AND state!='forgotten'",
                                          (scope, *keys, subject, subject))]
    return {'claims': claims, 'entity': dict(entity) if entity else None,
            'label': {'name': entity['name'] if entity else None, 'kind': entity['kind'] if entity else None,
                      'statements': len(claims)}}


def _label(claim, names):
    return {'subject': names.get(claim['subject_id']), 'predicate': claim['predicate'], 'value': claim['value'],
            'object': names.get(claim['object_id']) if claim['object_id'] else None}


def put(db, scope, actor, kind, subject, receipt, snap, now) -> int:
    """Keep one ordinary forget's copy until it can no longer be undone. Returns that time."""
    expires = now + SECONDS
    db.execute('INSERT INTO memory_bin VALUES (?,?,?,?,?,?,?,?,?)',
               ('bin-' + secrets.token_hex(12), scope, actor, KIND[kind], subject, now, expires, receipt,
                json.dumps(snap, sort_keys=True)))
    return expires


def _holds(claim, entity, claims, notes):
    return (claim['id'] in claims or claim.get('note_id') in notes
            or (entity is not None and entity in (claim['subject_id'], claim['object_id'])))


def _rows(db, scope):
    return [(r['id'], r['kind'], r['subject'], json.loads(r['snapshot']))
            for r in db.execute('SELECT id,kind,subject,snapshot FROM memory_bin WHERE scope=?', (scope,)).fetchall()]


def count(db, scope, *, entity=None, claims=(), notes=()) -> int:
    """Copies in the bin that hold the subject, for the deletion report."""
    if not _has(db):
        return 0
    claims, notes = set(claims), set(notes)
    return sum((kind == 'entity' and subject == entity) or any(_holds(c, entity, claims, notes) for c in snap['claims'])
               for _, kind, subject, snap in _rows(db, scope))


def purge(db, scope, *, entity=None, claims=(), notes=()) -> int:
    """An absolute forget leaves no copy in the bin: drop every copy that holds its subject.

    A record's copy that also holds other statements keeps them and loses only these."""
    if not _has(db):
        return 0
    claims, notes, removed = set(claims), set(notes), 0
    for identity, kind, subject, snap in _rows(db, scope):
        if kind == 'entity' and subject == entity:
            db.execute('DELETE FROM memory_bin WHERE id=?', (identity,)); removed += 1
            continue
        kept = [c for c in snap['claims'] if not _holds(c, entity, claims, notes)]
        if len(kept) == len(snap['claims']):
            continue
        removed += 1
        if kind == 'statement':
            db.execute('DELETE FROM memory_bin WHERE id=?', (identity,))
        else:
            snap['claims'], snap['label']['statements'] = kept, len(kept)
            db.execute('UPDATE memory_bin SET snapshot=? WHERE id=?', (json.dumps(snap, sort_keys=True), identity))
    return removed


def held_claims(db, scope) -> set:
    """Statements a copy in the bin still holds."""
    return {c['id'] for *_, snap in _rows(db, scope) for c in snap['claims']} if _has(db) else set()


def items(db, scope, actor, now) -> list[dict]:
    return [{'id': r['id'], 'kind': r['kind'], 'subject': r['subject'], 'deleted': r['deleted'], 'expires': r['expires'],
             'label': json.loads(r['snapshot'])['label']}
            for r in db.execute('SELECT * FROM memory_bin WHERE scope=? AND actor=? AND expires>? ORDER BY deleted DESC,id',
                                (scope, actor, now))]


def keep(db, scope, item, claims):
    """Statements a record's undo could not put back, because they name a record still
    forgotten, stay in the bin as statements until the record's copy would have gone."""
    if not claims:
        return
    names = {r[0]: r[1] for r in db.execute('SELECT id,name FROM memory_entities WHERE scope=? AND actor=?', (scope, item['actor']))}
    names |= {snap['entity']['id']: snap['entity']['name'] for _, kind, _, snap in _rows(db, scope) if kind == 'entity' and snap['entity']}
    for c in claims:
        db.execute('INSERT INTO memory_bin VALUES (?,?,?,?,?,?,?,?,?)',
                   ('bin-' + secrets.token_hex(12), scope, item['actor'], 'statement', c['id'], item['deleted'], item['expires'],
                    item['receipt'], json.dumps({'claims': [c], 'entity': None, 'label': _label(c, names)}, sort_keys=True)))


def take(db, scope, actor, identity, now) -> dict:
    """One copy the owner may still undo, removed from the bin in the caller's transaction."""
    row = db.execute('SELECT * FROM memory_bin WHERE id=? AND scope=? AND actor=? AND expires>?',
                     (identity, scope, actor, now)).fetchone()
    if not row:
        raise Fault('not_in_bin', 404)
    db.execute('DELETE FROM memory_bin WHERE id=?', (identity,))
    return dict(row) | {'snapshot': json.loads(row['snapshot'])}


def expire(db, scope, now) -> list[str]:
    """Empty copies whose 30 days have passed. Returns their subjects."""
    if not _has(db):
        return []
    gone = [r[0] for r in db.execute('SELECT subject FROM memory_bin WHERE scope=? AND expires<=? ORDER BY id', (scope, now))]
    db.execute('DELETE FROM memory_bin WHERE scope=? AND expires<=?', (scope, now))
    return gone
