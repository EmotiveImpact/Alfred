"""Explicit grants for test fixtures under strict-by-default policy (SYS-001).

Workspaces are strict from creation: no person, the owner included, reads a source
until the owner grants it. Fixtures that need people to read call these helpers,
which go through the real owner-only, epoch-checked IdentityPolicy.grant path. They
never mark a workspace legacy and never write grant rows directly.
"""
from alfred.local import Fault
from alfred.policy import IdentityPolicy, SHAREABLE


def _scope_members(store, owner):
    with store.transaction() as db:
        p = store.authenticate(db, owner, {'owner'})
        now = store.now()
        people = [r[0] for r in db.execute('''SELECT DISTINCT d.person FROM identity_devices d JOIN credentials c ON c.id=d.credential
            WHERE c.scope=? AND c.role IN ('owner','reader') AND c.revoked=0 AND c.expires>? ORDER BY d.person''', (p['scope'], now))]
        sources = [(r['id'], r['expires']) for r in db.execute('''SELECT id,expires FROM credentials
            WHERE scope=? AND role='source' AND revoked=0 AND expires>? ORDER BY id''', (p['scope'], now))]
        return p, now, people, sources


def grant_all(store, owner, capabilities=('read', 'model'), *, sources=None, people=None):
    """The owner explicitly grants each capability on each active source in their workspace
    to every person holding an active key there (or to the given sources and people)."""
    policy = IdentityPolicy(store)
    p, now, members, active = _scope_members(store, owner)
    chosen = [(s, e) for s, e in active if sources is None or s in sources]
    for person in (members if people is None else people):
        for source, expires in chosen:
            for capability in capabilities:
                if person != p['person_id'] and capability not in SHAREABLE:
                    continue
                policy.grant(owner, source, capability, min(expires, now + 2592000), policy.view(owner)['epoch'],
                             person=None if person == p['person_id'] else person)


def revoke_all(store, owner):
    """The owner explicitly revokes every grant in their workspace, each one journalled."""
    policy = IdentityPolicy(store)
    with store.transaction() as db:
        p = store.authenticate(db, owner, {'owner'})
        grants = [tuple(r) for r in db.execute('SELECT person,source,capability FROM source_grants WHERE scope=?', (p['scope'],))]
    for person, source, capability in grants:
        try:
            policy.grant(owner, source, capability, store.now() + 1, policy.view(owner)['epoch'], revoke=True,
                         person=None if person == p['person_id'] else person)
        except Fault as e:
            # A grant on a source or for a person that is no longer active already reads nothing.
            if e.code not in ('source_not_available', 'person_not_available'):
                raise


def person_of(store, bearer):
    with store.connection() as db:
        return store.authenticate(db, bearer, {'owner', 'reader', 'source'})['person_id']


def as_pre_strict_database(path):
    """Make a database look as it did before strict-by-default (no identity_meta and no
    policy record), so that reopening it runs the one-time upgrade that records each
    existing workspace as legacy. Used only by tests of that upgrade path."""
    import sqlite3
    db = sqlite3.connect(path)
    try:
        db.executescript('DROP TABLE identity_meta; DELETE FROM source_policy;')
    finally:
        db.close()
