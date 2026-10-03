"""Explicit local person/device enrolment and source capability decisions.

New workspaces are default-deny. Legacy access is a bounded migration snapshot,
never a grant to new credentials or sources. Names never link people. Device review
ledgers remain separate even after explicit enrolment into the same person.
"""
import hashlib
import re
import secrets
from .local import Fault, ident, text, timestamp

CAPABILITIES = {'read', 'model', 'inbox.write', 'sync', 'connector.read'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS identity_devices(
 credential TEXT PRIMARY KEY REFERENCES credentials(id), person TEXT NOT NULL,
 device TEXT UNIQUE NOT NULL, generation INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS source_policy(scope TEXT PRIMARY KEY, strict INTEGER NOT NULL, epoch INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS source_policy_migrations(scope TEXT PRIMARY KEY, mode TEXT NOT NULL, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS source_legacy_access(
 scope TEXT NOT NULL, credential TEXT NOT NULL, source TEXT NOT NULL, expires INTEGER NOT NULL,
 PRIMARY KEY(scope,credential,source));
CREATE TABLE IF NOT EXISTS source_grants(
 scope TEXT NOT NULL, person TEXT NOT NULL, source TEXT NOT NULL, capability TEXT NOT NULL,
 expires INTEGER NOT NULL, PRIMARY KEY(scope,person,source,capability));
CREATE TABLE IF NOT EXISTS grant_invitations(
 code_hash TEXT PRIMARY KEY, scope TEXT NOT NULL, source TEXT NOT NULL, capability TEXT NOT NULL,
 grant_expires INTEGER NOT NULL, expires INTEGER NOT NULL, created_by TEXT NOT NULL,
 redeemed_by TEXT, redeemed_at INTEGER);
CREATE TABLE IF NOT EXISTS device_pairings(
 code_hash TEXT PRIMARY KEY, scope TEXT NOT NULL, person TEXT NOT NULL, role TEXT NOT NULL,
 created_by TEXT NOT NULL, expires INTEGER NOT NULL, redeemed_credential TEXT, redeemed_at INTEGER);
CREATE TABLE IF NOT EXISTS device_details(
 credential TEXT PRIMARY KEY REFERENCES credentials(id), label TEXT NOT NULL, paired_from TEXT, paired_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS memory_tombstones(
 scope TEXT NOT NULL, source TEXT NOT NULL, note_id TEXT NOT NULL, path TEXT NOT NULL,
 at INTEGER NOT NULL, receipt TEXT NOT NULL, PRIMARY KEY(scope,source,note_id));
'''


def initialise(db):
    db.executescript(SCHEMA)
    # Capture compatibility once, atomically. Reopening/adding a credential must
    # never enlarge this snapshot. Expiry/revocation still apply at every read.
    db.execute('BEGIN IMMEDIATE')
    try:
        for row in db.execute('SELECT id FROM credentials').fetchall():
            enrol(db, row['id'])
        for workspace in db.execute('SELECT id FROM workspaces').fetchall():
            scope = workspace['id']
            if db.execute('SELECT 1 FROM source_policy_migrations WHERE scope=?', (scope,)).fetchone():
                continue
            policy = db.execute('SELECT strict FROM source_policy WHERE scope=?', (scope,)).fetchone()
            db.execute('INSERT OR IGNORE INTO source_policy VALUES (?,0,0)', (scope,))
            legacy = not policy or not policy['strict']
            if legacy:
                snapshot_legacy(db, scope)
            db.execute('INSERT INTO source_policy_migrations VALUES (?,?,0)',
                       (scope, 'legacy_snapshot' if legacy else 'explicit_existing'))
        db.commit()
    except BaseException:
        db.rollback()
        raise


def snapshot_legacy(db, scope):
    db.execute('''INSERT OR IGNORE INTO source_legacy_access
        SELECT a.scope,a.id,s.id,min(a.expires,s.expires) FROM credentials a JOIN credentials s ON s.scope=a.scope
        WHERE a.scope=? AND a.role IN ('owner','reader') AND s.role='source' AND a.revoked=0 AND s.revoked=0''', (scope,))


def enrol(db, credential):
    db.execute('INSERT OR IGNORE INTO identity_devices VALUES (?,?,?,1)',
               (credential, 'person-'+secrets.token_hex(12), 'device-'+secrets.token_hex(12)))


def permitted(db, principal, source, now, capability='read'):
    if capability not in CAPABILITIES:
        return False
    row = db.execute('SELECT scope,role,revoked,expires FROM credentials WHERE id=?', (source,)).fetchone()
    if not row or row['scope'] != principal['scope'] or row['role'] != 'source' or row['revoked'] or row['expires'] <= now:
        return False
    actor = db.execute('SELECT scope,role,revoked,expires FROM credentials WHERE id=?', (principal['id'],)).fetchone()
    if not actor or actor['scope'] != principal['scope'] or actor['role'] not in {'owner','reader'} or actor['revoked'] or actor['expires'] <= now:
        return False
    policy = db.execute('SELECT strict FROM source_policy WHERE scope=?', (principal['scope'],)).fetchone()
    if not policy:
        return False
    if not policy['strict']:
        return capability in {'read', 'model'} and bool(db.execute(
            'SELECT 1 FROM source_legacy_access WHERE scope=? AND credential=? AND source=? AND expires>?',
            (principal['scope'],principal['id'],source,now)).fetchone())
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
            migration = db.execute('SELECT mode,at FROM source_policy_migrations WHERE scope=?',(p['scope'],)).fetchone()
            now = self.store.now()
            grants = [dict(r) for r in db.execute('''SELECT source,capability,expires FROM source_grants
                WHERE scope=? AND person=? AND expires>? ORDER BY source,capability''',
                (p['scope'], p['person_id'], now))]
            # Source labels are shown only to owners; a reader sees only what it may read.
            sources = []
            labels = {}
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_sources'").fetchone():
                labels = {r['source']: r['label'] for r in db.execute('SELECT source,label FROM knowledge_sources WHERE scope=?', (p['scope'],))}
            for c in db.execute("SELECT id,expires FROM credentials WHERE scope=? AND role='source' AND revoked=0 AND expires>? ORDER BY id", (p['scope'], now)):
                allowed = {cap: permitted(db, p, c['id'], now, cap) for cap in sorted(CAPABILITIES)}
                if p['role'] != 'owner' and not allowed['read']:
                    continue
                sources.append({'source': c['id'], 'label': labels.get(c['id'], 'Unnamed source'), 'permitted': allowed,
                                'credential_expires': c['expires']})
            # Only this person's own active devices. Other people's devices are never listed.
            devices = [{'device': r['device'], 'label': r['label'] or 'Provisioned access key', 'role': r['role'],
                        'expires': r['expires'], 'paired_at': r['paired_at'], 'current': r['credential'] == p['id']}
                       for r in db.execute('''SELECT d.credential,d.device,c.role,c.expires,dd.label,dd.paired_at
                           FROM identity_devices d JOIN credentials c ON c.id=d.credential
                           LEFT JOIN device_details dd ON dd.credential=d.credential
                           WHERE d.person=? AND c.scope=? AND c.role IN ('owner','reader') AND c.revoked=0 AND c.expires>?
                           ORDER BY c.expires DESC,d.device''', (p['person_id'], p['scope'], now))]
            return {'person_id':p['person_id'], 'device_id':p['device_id'], 'generation':p['generation'],
                    'scope':p['scope'], 'role':p['role'], 'mode':'explicit_grants' if row and row['strict'] else 'legacy_scope',
                    'epoch':row['epoch'] if row else 0, 'grants':grants, 'sources':sources, 'devices':devices,
                    'migration':dict(migration) if migration else None,
                    'device_reviews_shared':False}

    def offer_pairing(self, bearer, role):
        """A one-time code that adds a device for this same person, without copying a key.

        The new device gets its own credential, never more authority than the offering
        one: the same role or reader, and an expiry no later than the offering key's.
        """
        code = secrets.token_urlsafe(18)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            if role not in ('owner', 'reader') or (p['role'] == 'reader' and role != 'reader'):
                raise Fault('invalid_pairing_role')
            now = self.store.now()
            if db.execute('SELECT count(*) FROM device_pairings WHERE scope=? AND redeemed_at IS NULL AND expires>?',
                          (p['scope'], now)).fetchone()[0] >= 8:
                raise Fault('pairing_capacity', 409)
            db.execute('INSERT INTO device_pairings VALUES (?,?,?,?,?,?,NULL,NULL)',
                       (hashlib.sha256(code.encode()).hexdigest(), p['scope'], p['person_id'], role, p['id'], now + 600))
            self.store.log(db, p['scope'], p['id'], 'device.pairing_offered', p['device_id'])
        return {'code': code, 'expires_at': now + 600, 'role': role, 'single_use': True,
                'device_expires_no_later_than': p['expires']}

    def redeem_pairing(self, code, label):
        """Called by the new device, which holds only the code. Returns its own key once."""
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{24}', code):
            raise Fault('pairing_not_valid', 404)
        text(label, 60)
        if not label.strip():
            raise Fault('device_label_required')
        bearer = secrets.token_urlsafe(32)
        with self.store.transaction() as db:
            now = self.store.now()
            row = db.execute('SELECT * FROM device_pairings WHERE code_hash=?', (hashlib.sha256(code.encode()).hexdigest(),)).fetchone()
            offering = db.execute('SELECT * FROM credentials WHERE id=?', (row['created_by'],)).fetchone() if row else None
            person = db.execute('SELECT person FROM identity_devices WHERE credential=?', (row['created_by'],)).fetchone() if row else None
            # Unknown, used, expired and orphaned codes are indistinguishable.
            if (not row or row['redeemed_at'] is not None or row['expires'] <= now or not offering or offering['revoked']
                    or offering['expires'] <= now or not person or person['person'] != row['person']):
                raise Fault('pairing_not_valid', 404)
            if db.execute('SELECT count(*) FROM credentials').fetchone()[0] >= 128:
                raise Fault('credential_capacity', 409)
            credential, device = 'device-' + secrets.token_hex(12), 'device-' + secrets.token_hex(12)
            db.execute('INSERT INTO credentials(id,scope,role,digest,expires) VALUES (?,?,?,?,?)',
                       (credential, row['scope'], row['role'], hashlib.sha256(bearer.encode()).hexdigest(), offering['expires']))
            db.execute('INSERT INTO identity_devices VALUES (?,?,?,1)', (credential, row['person'], device))
            db.execute('INSERT INTO device_details VALUES (?,?,?,?)', (credential, label.strip(), row['created_by'], now))
            db.execute('UPDATE device_pairings SET redeemed_credential=?,redeemed_at=? WHERE code_hash=?', (credential, now, row['code_hash']))
            self.store.log(db, row['scope'], credential, 'device.paired', row['created_by'])
        return {'key': bearer, 'device_id': device, 'role': row['role'], 'expires_at': offering['expires']}

    def revoke_device(self, bearer, device_id):
        """A person removes one of their own other devices. Revoking this device stays offline."""
        if not isinstance(device_id, str) or not re.fullmatch(r'device-[0-9a-f]{24}', device_id):
            raise Fault('not_found', 404)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            target = db.execute('''SELECT d.credential FROM identity_devices d JOIN credentials c ON c.id=d.credential
                WHERE d.device=? AND d.person=? AND c.scope=? AND c.role IN ('owner','reader') AND c.revoked=0''',
                (device_id, p['person_id'], p['scope'])).fetchone()
            if not target:
                raise Fault('not_found', 404)
            if target['credential'] == p['id']:
                raise Fault('cannot_revoke_current_device', 409)
        self.store.revoke(target['credential'], actor=p['id'])
        return self.view(bearer)

    def invite(self, bearer, source, capability, grant_expires, epoch):
        """A one-time code another person redeems with their own key. No one is granted by ID."""
        ident(source); timestamp(grant_expires)
        if capability not in CAPABILITIES or capability == 'inbox.write':
            # Writing into the vault stays with the owner's own person.
            raise Fault('invalid_capability')
        code = secrets.token_urlsafe(18)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            self._epoch(db, p, epoch)
            row = db.execute("SELECT * FROM credentials WHERE id=? AND scope=? AND role='source'", (source, p['scope'])).fetchone()
            if not row or row['revoked'] or row['expires'] <= self.store.now():
                raise Fault('source_not_available', 404)
            if not self.store.now() < grant_expires <= min(row['expires'], self.store.now()+2592000):
                raise Fault('invalid_grant_expiry')
            if db.execute('SELECT count(*) FROM grant_invitations WHERE scope=? AND redeemed_by IS NULL AND expires>?',
                          (p['scope'], self.store.now())).fetchone()[0] >= 16:
                raise Fault('invitation_capacity', 409)
            db.execute('INSERT INTO grant_invitations VALUES (?,?,?,?,?,?,?,NULL,NULL)',
                       (hashlib.sha256(code.encode()).hexdigest(), p['scope'], source, capability, grant_expires,
                        self.store.now()+900, p['id']))
            self.store.log(db, p['scope'], p['id'], 'grant.invited', source)
        return {'code': code, 'expires_at': self.store.now()+900, 'source': source, 'capability': capability,
                'single_use': True, 'grants_only_this_source_and_capability': True}

    def redeem(self, bearer, code):
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{24}', code):
            raise Fault('invitation_not_valid', 404)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            row = db.execute('SELECT * FROM grant_invitations WHERE code_hash=?', (hashlib.sha256(code.encode()).hexdigest(),)).fetchone()
            # Wrong workspace, used, expired and unknown codes are indistinguishable.
            if (not row or row['scope'] != p['scope'] or row['redeemed_by'] is not None or row['expires'] <= self.store.now()
                    or row['created_by'] == p['id']):
                raise Fault('invitation_not_valid', 404)
            source = db.execute('SELECT revoked,expires FROM credentials WHERE id=?', (row['source'],)).fetchone()
            if not source or source['revoked'] or source['expires'] <= self.store.now():
                raise Fault('invitation_not_valid', 404)
            db.execute('UPDATE grant_invitations SET redeemed_by=?,redeemed_at=? WHERE code_hash=?', (p['id'], self.store.now(), row['code_hash']))
            db.execute('INSERT OR REPLACE INTO source_grants VALUES (?,?,?,?,?)',
                       (p['scope'], p['person_id'], row['source'], row['capability'], min(row['grant_expires'], source['expires'])))
            db.execute('''INSERT INTO source_policy VALUES (?,1,1) ON CONFLICT(scope)
                DO UPDATE SET strict=1,epoch=epoch+1''', (p['scope'],))
            self.store.log(db, p['scope'], p['id'], 'grant.redeemed', row['source'])
        return self.view(bearer)

    def enable(self, bearer, epoch):
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            self._epoch(db, p, epoch)
            from .lifecycle import append
            append(self.store,{'kind':'policy_strict','scope':p['scope'],'at':self.store.now()})
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

    def migrate_legacy(self, bearer, epoch, *, preserve_reads):
        """Offline owner decision: retain recorded reads or deny ungranted access.

        Never migrates implicit model egress, sync or writes. Explicit grants
        remain; only active snapshot participants acquire read grants.
        """
        if type(preserve_reads) is not bool:
            raise Fault('invalid_migration_policy')
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            self._epoch(db, p, epoch)
            policy = db.execute('SELECT strict FROM source_policy WHERE scope=?', (p['scope'],)).fetchone()
            if policy and policy['strict']:
                return {'migrated': False, 'mode': 'explicit_grants', 'read_grants_added': 0}
            from .lifecycle import append
            append(self.store,{'kind':'policy_strict','scope':p['scope'],'at':self.store.now()})
            added = 0
            if preserve_reads:
                for row in db.execute('''SELECT l.source,l.expires,d.person FROM source_legacy_access l
                    JOIN credentials a ON a.id=l.credential JOIN credentials s ON s.id=l.source
                    JOIN identity_devices d ON d.credential=a.id
                    WHERE l.scope=? AND l.expires>? AND a.revoked=0 AND s.revoked=0 AND a.expires>? AND s.expires>?''',
                    (p['scope'],self.store.now(),self.store.now(),self.store.now())).fetchall():
                    added += db.execute('INSERT OR IGNORE INTO source_grants VALUES (?,?,?,?,?)',
                                        (p['scope'],row['person'],row['source'],'read',row['expires'])).rowcount
            db.execute('INSERT INTO source_policy VALUES (?,1,1) ON CONFLICT(scope) DO UPDATE SET strict=1,epoch=epoch+1', (p['scope'],))
            db.execute('UPDATE source_policy_migrations SET mode=?,at=? WHERE scope=?',
                       ('explicit_migrated',self.store.now(),p['scope']))
            db.execute('DELETE FROM source_legacy_access WHERE scope=?', (p['scope'],))
            self.store.log(db,p['scope'],p['id'],'policy.migrated',p['scope'])
            return {'migrated':True,'mode':'explicit_grants','read_grants_added':added,
                    'model_egress_migrated':False,'writes_migrated':False}

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
            policy = db.execute('SELECT strict FROM source_policy WHERE scope=?',(p['scope'],)).fetchone()
            if not policy or not policy['strict']:
                from .lifecycle import append
                append(self.store,{'kind':'policy_strict','scope':p['scope'],'at':self.store.now()})
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

    def rotate(self, bearer, generation, *, ttl=86400, replacement=None):
        timestamp(generation)
        if type(ttl) is not int or not 1 <= ttl <= 2592000:
            raise Fault('invalid_ttl')
        if replacement is None:
            replacement = secrets.token_urlsafe(32)
        elif not isinstance(replacement, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', replacement):
            raise Fault('invalid_replacement')
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
