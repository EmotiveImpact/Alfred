"""Explicit local person/device enrolment and source capability decisions.

Legacy workspaces retain their documented coarse scope policy until an owner
enables grants. Enabling is fail closed. Names never link people. Device review
ledgers remain separate even after explicit enrolment into the same person.
"""
import hashlib
import secrets
from .local import Fault, ident, timestamp

CAPABILITIES = {'read', 'model', 'inbox.write', 'sync', 'connector.read'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS identity_devices(
 credential TEXT PRIMARY KEY REFERENCES credentials(id), person TEXT NOT NULL,
 device TEXT UNIQUE NOT NULL, generation INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS source_policy(scope TEXT PRIMARY KEY, strict INTEGER NOT NULL, epoch INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS source_grants(
 scope TEXT NOT NULL, person TEXT NOT NULL, source TEXT NOT NULL, capability TEXT NOT NULL,
 expires INTEGER NOT NULL, PRIMARY KEY(scope,person,source,capability));
CREATE TABLE IF NOT EXISTS memory_tombstones(
 scope TEXT NOT NULL, source TEXT NOT NULL, note_id TEXT NOT NULL, path TEXT NOT NULL,
 at INTEGER NOT NULL, receipt TEXT NOT NULL, PRIMARY KEY(scope,source,note_id));
'''


def initialise(db):
    db.executescript(SCHEMA)
    # Each old credential becomes a different person. This is a migration, not
    # an assertion about the identity of its bearer.
    for row in db.execute('SELECT id FROM credentials').fetchall():
        enrol(db, row['id'])


def enrol(db, credential):
    db.execute('INSERT OR IGNORE INTO identity_devices VALUES (?,?,?,1)',
               (credential, 'person-'+secrets.token_hex(12), 'device-'+secrets.token_hex(12)))


def permitted(db, principal, source, now, capability='read'):
    if capability not in CAPABILITIES:
        return False
    row = db.execute('SELECT scope,role,revoked,expires FROM credentials WHERE id=?', (source,)).fetchone()
    if not row or row['scope'] != principal['scope'] or row['role'] != 'source' or row['revoked'] or row['expires'] <= now:
        return False
    policy = db.execute('SELECT strict FROM source_policy WHERE scope=?', (principal['scope'],)).fetchone()
    if not policy or not policy['strict']:
        return capability in {'read', 'model'}
    device = db.execute('SELECT person FROM identity_devices WHERE credential=?', (principal['id'],)).fetchone()
    return bool(device and db.execute('''SELECT 1 FROM source_grants WHERE scope=? AND person=?
        AND source=? AND capability=? AND expires>?''',
        (principal['scope'], device['person'], source, capability, now)).fetchone())


class IdentityPolicy:
    def __init__(self, store):
        self.store = store

    def view(self, bearer):
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            row = db.execute('SELECT * FROM source_policy WHERE scope=?', (p['scope'],)).fetchone()
            grants = [dict(r) for r in db.execute('''SELECT source,capability,expires FROM source_grants
                WHERE scope=? AND person=? AND expires>? ORDER BY source,capability''',
                (p['scope'], p['person_id'], self.store.now()))]
            return {'person_id':p['person_id'], 'device_id':p['device_id'], 'generation':p['generation'],
                    'scope':p['scope'], 'mode':'explicit_grants' if row and row['strict'] else 'legacy_scope',
                    'epoch':row['epoch'] if row else 0, 'grants':grants, 'device_reviews_shared':False}

    def enable(self, bearer, epoch):
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            self._epoch(db, p, epoch)
            db.execute('''INSERT INTO source_policy VALUES (?,1,1) ON CONFLICT(scope)
                DO UPDATE SET strict=1,epoch=epoch+1''', (p['scope'],))
            self.store.log(db, p['scope'], p['id'], 'policy.enabled', p['scope'])
        return self.view(bearer)

    @staticmethod
    def _epoch(db, p, expected):
        timestamp(expected)
        row = db.execute('SELECT epoch FROM source_policy WHERE scope=?', (p['scope'],)).fetchone()
        if (row['epoch'] if row else 0) != expected:
            raise Fault('policy_changed', 409)

    def grant(self, bearer, source, capability, expires, epoch, *, revoke=False):
        ident(source); timestamp(expires)
        if capability not in CAPABILITIES or type(revoke) is not bool:
            raise Fault('invalid_capability')
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            self._epoch(db, p, epoch)
            row = db.execute('SELECT * FROM credentials WHERE id=? AND scope=? AND role=?',
                             (source, p['scope'], 'source')).fetchone()
            if not row or row['revoked'] or row['expires'] <= self.store.now():
                raise Fault('source_not_available', 404)
            if not revoke and not self.store.now() < expires <= min(row['expires'], self.store.now()+2592000):
                raise Fault('invalid_grant_expiry')
            if revoke:
                from .lifecycle import append
                append(self.store, {'kind': 'grant_revoked', 'scope': p['scope'], 'person': p['person_id'], 'subject': source,
                                    'capability': capability, 'at': self.store.now()})
                db.execute('DELETE FROM source_grants WHERE scope=? AND person=? AND source=? AND capability=?',
                           (p['scope'], p['person_id'], source, capability))
            else:
                db.execute('INSERT OR REPLACE INTO source_grants VALUES (?,?,?,?,?)',
                           (p['scope'], p['person_id'], source, capability, expires))
            # Granting also enables strict policy. An owner cannot grant another
            # person by guessing their ID. Pairing requires both active bearers.
            db.execute('''INSERT INTO source_policy VALUES (?,1,1) ON CONFLICT(scope)
                DO UPDATE SET strict=1,epoch=epoch+1''', (p['scope'],))
            self.store.log(db, p['scope'], p['id'], 'grant.revoked' if revoke else 'grant.created', source)
        return self.view(bearer)

    def rotate(self, bearer, generation, *, ttl=86400):
        timestamp(generation)
        if type(ttl) is not int or not 1 <= ttl <= 2592000:
            raise Fault('invalid_ttl')
        replacement = secrets.token_urlsafe(32)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader', 'source'})
            if p['generation'] != generation:
                raise Fault('credential_changed', 409)
            db.execute('UPDATE credentials SET digest=?,expires=? WHERE id=?',
                       (hashlib.sha256(replacement.encode()).hexdigest(), self.store.now()+ttl, p['id']))
            db.execute('UPDATE identity_devices SET generation=generation+1 WHERE credential=?', (p['id'],))
            self.store.log(db, p['scope'], p['id'], 'credential.rotated', p['device_id'])
        return replacement

    def pair(self, primary, secondary, expected_person, expected_device):
        """Offline explicit enrolment; never changes source IDs or review actors."""
        with self.store.transaction() as db:
            p = self.store.authenticate(db, primary, {'owner'})
            q = self.store.authenticate(db, secondary, {'owner'})
            if p['scope'] != q['scope'] or p['id'] == q['id']:
                raise Fault('invalid_person_pairing')
            if p['person_id'] != expected_person or q['device_id'] != expected_device:
                raise Fault('identity_changed', 409)
            # Existing grants indicate an established person. Do not fold them
            # into another person or transfer their authority implicitly.
            if db.execute('SELECT 1 FROM source_grants WHERE scope=? AND person=?',
                          (q['scope'], q['person_id'])).fetchone():
                raise Fault('established_person_cannot_be_paired', 409)
            db.execute('UPDATE identity_devices SET person=? WHERE credential=?', (p['person_id'], q['id']))
            self.store.log(db, p['scope'], p['id'], 'device.explicitly_paired', q['device_id'])
        return self.view(secondary)
