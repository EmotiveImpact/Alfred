"""Explicit local person/device enrolment and source capability decisions.

Strict by default: a workspace created by this version grants no source to anyone,
the owner included, until the owner grants it (SYS-001). Only a workspace that
predates this version keeps its recorded whole-workspace (legacy) mode, until the
owner enables grants. Enabling is fail closed. Names never link people. The review
ledger belongs to the person, so every device of one person shares one review
history; each review still records the device credential that made it.
"""
import hashlib
import re
import secrets
from .local import Fault, ident, text, timestamp

CAPABILITIES = {'read', 'model', 'inbox.write', 'sync', 'connector.read'}
# Only these may be granted to another person; vault writing and imports stay with the owner.
SHAREABLE = {'read', 'model'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS identity_devices(
 credential TEXT PRIMARY KEY REFERENCES credentials(id), person TEXT NOT NULL,
 device TEXT UNIQUE NOT NULL, generation INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS source_policy(scope TEXT PRIMARY KEY, strict INTEGER NOT NULL, epoch INTEGER NOT NULL);
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
CREATE TABLE IF NOT EXISTS identity_meta(version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS person_enrolments(
 code_hash TEXT PRIMARY KEY, scope TEXT NOT NULL, person TEXT NOT NULL, label TEXT NOT NULL,
 created_by TEXT NOT NULL, expires INTEGER NOT NULL, redeemed_credential TEXT, redeemed_at INTEGER);
CREATE TABLE IF NOT EXISTS person_labels(
 scope TEXT NOT NULL, person TEXT NOT NULL, label TEXT NOT NULL, PRIMARY KEY(scope,person));
'''
# Workspaces that existed before strict-by-default keep an explicit legacy record, once.
# A workspace created afterwards has no record and is therefore strict.
STRICT_BY_DEFAULT = '''BEGIN IMMEDIATE;
INSERT OR IGNORE INTO source_policy SELECT id,0,0 FROM workspaces WHERE NOT EXISTS(SELECT 1 FROM identity_meta);
INSERT INTO identity_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM identity_meta);
COMMIT;'''
LEDGER_TABLES = ('memory_entities', 'memory_claims', 'memory_claim_history', 'lifecycle_receipts')
PERSON = re.compile(r'person-[0-9a-f]{24}')


def initialise(db):
    db.executescript(SCHEMA)
    db.executescript(STRICT_BY_DEFAULT)
    # Each old credential becomes a different person. This is a migration, not
    # an assertion about the identity of its bearer.
    for row in db.execute('SELECT id FROM credentials').fetchall():
        enrol(db, row['id'])


def enrol(db, credential):
    db.execute('INSERT OR IGNORE INTO identity_devices VALUES (?,?,?,1)',
               (credential, 'person-'+secrets.token_hex(12), 'device-'+secrets.token_hex(12)))


def ledger(db, principal):
    """The review ledger key for a principal: its person, shared by all of that person's devices."""
    if principal.get('ledger'):
        return principal['ledger']
    row = db.execute('SELECT person FROM identity_devices WHERE credential=?', (principal['id'],)).fetchone()
    return row['person'] if row else principal['id']


def ledger_keys(db, key):
    """Every actor value that may still name one person's ledger: the person and its device
    credentials. Rows written before ledgers were per person, and journal entries replayed
    into an older backup, can carry a credential."""
    row = db.execute('SELECT person FROM identity_devices WHERE credential=?', (key,)).fetchone()
    person = row['person'] if row else key
    return sorted({key, person} | person_credentials(db, person))


def person_credentials(db, person):
    return {r[0] for r in db.execute('SELECT credential FROM identity_devices WHERE person=?', (person,))}


def migrate_ledgers(db):
    """Move review ledger rows keyed by a device credential to that device's person. Idempotent.

    A row that would collide with the same request already in the person's ledger (two devices
    explicitly paired before this version) stays under its credential, untouched."""
    for table in LEDGER_TABLES:
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            db.execute(f'''UPDATE OR IGNORE {table} SET actor=(SELECT person FROM identity_devices WHERE credential={table}.actor)
                WHERE actor IN (SELECT credential FROM identity_devices)''')


def permitted(db, principal, source, now, capability='read'):
    if capability not in CAPABILITIES:
        return False
    row = db.execute('SELECT scope,role,revoked,expires FROM credentials WHERE id=?', (source,)).fetchone()
    if not row or row['scope'] != principal['scope'] or row['role'] != 'source' or row['revoked'] or row['expires'] <= now:
        return False
    policy = db.execute('SELECT strict FROM source_policy WHERE scope=?', (principal['scope'],)).fetchone()
    # No record means strict. Only a workspace recorded as legacy keeps whole-workspace reads.
    if policy is not None and not policy['strict']:
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
                    'scope':p['scope'], 'role':p['role'], 'mode':'legacy_scope' if row and not row['strict'] else 'explicit_grants',
                    'epoch':row['epoch'] if row else 0, 'grants':grants, 'sources':sources, 'devices':devices,
                    'device_reviews_shared':True}

    def people(self, bearer):
        """Owner only: every person holding an active key in this workspace, with their grants.

        A person is labelled by the owner's enrolment label, never by device names."""
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            now = self.store.now()
            row = db.execute('SELECT * FROM source_policy WHERE scope=?', (p['scope'],)).fetchone()
            labels = {r['person']: r['label'] for r in db.execute('SELECT person,label FROM person_labels WHERE scope=?', (p['scope'],))}
            people = {}
            for r in db.execute('''SELECT d.person,c.role FROM identity_devices d JOIN credentials c ON c.id=d.credential
                    WHERE c.scope=? AND c.role IN ('owner','reader') AND c.revoked=0 AND c.expires>? ORDER BY d.person''',
                    (p['scope'], now)):
                entry = people.setdefault(r['person'], {'person_id': r['person'], 'you': r['person'] == p['person_id'],
                                                        'label': 'You' if r['person'] == p['person_id'] else labels.get(r['person'], 'Unnamed person'),
                                                        'roles': set(), 'devices': 0, 'grants': []})
                entry['roles'].add(r['role'])
                entry['devices'] += 1
            for g in db.execute('''SELECT person,source,capability,expires FROM source_grants WHERE scope=? AND expires>?
                    ORDER BY source,capability''', (p['scope'], now)):
                if g['person'] in people:
                    people[g['person']]['grants'].append({'source': g['source'], 'capability': g['capability'], 'expires': g['expires']})
            listed = sorted(people.values(), key=lambda e: (not e['you'], e['label'].casefold(), e['person_id']))
            for e in listed:
                e['roles'] = sorted(e['roles'])
            return {'epoch': row['epoch'] if row else 0, 'mode': 'legacy_scope' if row and not row['strict'] else 'explicit_grants',
                    'people': listed, 'shareable': sorted(SHAREABLE)}

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

    def offer_enrolment(self, bearer, label, epoch):
        """A one-time code that enrols a new person with their own reader key and no grants.

        The new person sees nothing until the owner grants a source. Owners are never
        enrolled this way: more than one owner person per workspace is not supported.
        """
        text(label, 60)
        if not label.strip():
            raise Fault('person_label_required')
        code = secrets.token_urlsafe(18)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            self._epoch(db, p, epoch)
            now = self.store.now()
            if db.execute('SELECT count(*) FROM person_enrolments WHERE scope=? AND redeemed_at IS NULL AND expires>?',
                          (p['scope'], now)).fetchone()[0] >= 8:
                raise Fault('enrolment_capacity', 409)
            person = 'person-' + secrets.token_hex(12)
            db.execute('INSERT INTO person_enrolments VALUES (?,?,?,?,?,?,NULL,NULL)',
                       (hashlib.sha256(code.encode()).hexdigest(), p['scope'], person, label.strip(), p['id'], now + 900))
            self.store.log(db, p['scope'], p['id'], 'person.enrolment_offered', person)
        return {'code': code, 'expires_at': now + 900, 'role': 'reader', 'single_use': True, 'grants': [],
                'person_id': person, 'label': label.strip()}

    def redeem_pairing(self, code, label):
        """Called by the new device, which holds only the code. Returns its own key once.

        The code is either a pairing code (another device of the same person) or an
        enrolment code (a new person); both use the same screen and refusal."""
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{24}', code):
            raise Fault('pairing_not_valid', 404)
        text(label, 60)
        if not label.strip():
            raise Fault('device_label_required')
        bearer = secrets.token_urlsafe(32)
        with self.store.transaction() as db:
            now = self.store.now()
            row = db.execute('SELECT * FROM device_pairings WHERE code_hash=?', (hashlib.sha256(code.encode()).hexdigest(),)).fetchone()
            if not row:
                return self._redeem_enrolment(db, code, label, bearer, now)
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

    def _redeem_enrolment(self, db, code, label, bearer, now):
        row = db.execute('SELECT * FROM person_enrolments WHERE code_hash=?', (hashlib.sha256(code.encode()).hexdigest(),)).fetchone()
        offering = db.execute('SELECT * FROM credentials WHERE id=?', (row['created_by'],)).fetchone() if row else None
        # Unknown, used, expired and orphaned codes are indistinguishable from bad pairing codes.
        if (not row or row['redeemed_at'] is not None or row['expires'] <= now or not offering or offering['revoked']
                or offering['expires'] <= now or offering['role'] != 'owner' or offering['scope'] != row['scope']):
            raise Fault('pairing_not_valid', 404)
        if db.execute('SELECT count(*) FROM credentials').fetchone()[0] >= 128:
            raise Fault('credential_capacity', 409)
        credential, device = 'device-' + secrets.token_hex(12), 'device-' + secrets.token_hex(12)
        db.execute('INSERT INTO credentials(id,scope,role,digest,expires) VALUES (?,?,?,?,?)',
                   (credential, row['scope'], 'reader', hashlib.sha256(bearer.encode()).hexdigest(), offering['expires']))
        db.execute('INSERT INTO identity_devices VALUES (?,?,?,1)', (credential, row['person'], device))
        db.execute('INSERT INTO device_details VALUES (?,?,?,?)', (credential, label.strip(), row['created_by'], now))
        db.execute('INSERT OR REPLACE INTO person_labels VALUES (?,?,?)', (row['scope'], row['person'], row['label']))
        db.execute('UPDATE person_enrolments SET redeemed_credential=?,redeemed_at=? WHERE code_hash=?', (credential, now, row['code_hash']))
        self.store.log(db, row['scope'], credential, 'person.enrolled', row['person'])
        return {'key': bearer, 'device_id': device, 'role': 'reader', 'expires_at': offering['expires'], 'new_person': True}

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

    def grant(self, bearer, source, capability, expires, epoch, *, revoke=False, person=None):
        """Grant or revoke one capability on one source for the owner's own person or, with
        ``person``, for another person who holds an active key in this workspace.

        Version-checked by epoch. A revocation is journalled before it applies, so restoring
        an older backup cannot bring the access back; every change is in the audit log."""
        ident(source); timestamp(expires)
        if capability not in CAPABILITIES or type(revoke) is not bool:
            raise Fault('invalid_capability')
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            self._epoch(db, p, epoch)
            target = p['person_id']
            if person is not None and person != p['person_id']:
                if not isinstance(person, str) or not PERSON.fullmatch(person):
                    raise Fault('person_not_available', 404)
                # Only a person with an active key here; an ID from elsewhere is simply unknown.
                if not db.execute('''SELECT 1 FROM identity_devices d JOIN credentials c ON c.id=d.credential
                        WHERE d.person=? AND c.scope=? AND c.role IN ('owner','reader') AND c.revoked=0 AND c.expires>?''',
                        (person, p['scope'], self.store.now())).fetchone():
                    raise Fault('person_not_available', 404)
                if capability not in SHAREABLE:
                    raise Fault('invalid_capability')
                target = person
            row = db.execute('SELECT * FROM credentials WHERE id=? AND scope=? AND role=?',
                             (source, p['scope'], 'source')).fetchone()
            if not row or row['revoked'] or row['expires'] <= self.store.now():
                raise Fault('source_not_available', 404)
            if not revoke and not self.store.now() < expires <= min(row['expires'], self.store.now()+2592000):
                raise Fault('invalid_grant_expiry')
            if revoke:
                from .lifecycle import append
                append(self.store, {'kind': 'grant_revoked', 'scope': p['scope'], 'person': target, 'subject': source,
                                    'capability': capability, 'at': self.store.now()})
                db.execute('DELETE FROM source_grants WHERE scope=? AND person=? AND source=? AND capability=?',
                           (p['scope'], target, source, capability))
            else:
                db.execute('INSERT OR REPLACE INTO source_grants VALUES (?,?,?,?,?)',
                           (p['scope'], target, source, capability, expires))
            # Granting also enables strict policy. Another person can be granted only once
            # they hold an active key here (enrolment, invitation or offline provisioning).
            db.execute('''INSERT INTO source_policy VALUES (?,1,1) ON CONFLICT(scope)
                DO UPDATE SET strict=1,epoch=epoch+1''', (p['scope'],))
            self.store.log(db, p['scope'], p['id'], 'grant.revoked' if revoke else 'grant.created',
                           source if target == p['person_id'] else f'{source}:{capability}:{target}')
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
        """Offline explicit enrolment; never changes source IDs or merges review ledgers."""
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
            # So does a review history: ledgers are per person and never merged implicitly.
            for table in LEDGER_TABLES:
                if (db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                        and db.execute(f'SELECT 1 FROM {table} WHERE scope=? AND actor IN (?,?)',
                                       (q['scope'], q['person_id'], q['id'])).fetchone()):
                    raise Fault('established_person_cannot_be_paired', 409)
            db.execute('UPDATE identity_devices SET person=? WHERE credential=?', (p['person_id'], q['id']))
            self.store.log(db, p['scope'], p['id'], 'device.explicitly_paired', q['device_id'])
        return self.view(secondary)
