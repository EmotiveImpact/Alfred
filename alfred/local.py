"""ALFRED v0.2 local development core. Only effect: an authorised SQLite draft.

Provisioning is offline administration. Bearer possession is authentication,
not biometric identity. No model, microphone, shell or external connector runs.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Callable


class Fault(Exception):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code, self.status = code, status


def ident(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value):
        raise Fault('invalid_identifier')
    return value


def timestamp(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 2**53:
        raise Fault('invalid_timestamp')
    return value


def text(value: object, limit: int = 4096) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        raise Fault('invalid_text')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise Fault('invalid_unicode') from None
    if any(ord(c) < 32 or 127 <= ord(c) < 160 for c in value):
        raise Fault('control_character')
    return value


def exact(obj: object, keys: set[str]) -> dict:
    if type(obj) is not dict or set(obj) != keys:
        raise Fault('invalid_fields')
    return obj


def canonical(value: object) -> str:
    try:
        result = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False, ensure_ascii=True)
    except (TypeError, ValueError, RecursionError):
        raise Fault('invalid_json') from None
    if len(result.encode()) > 16384:
        raise Fault('payload_too_large', 413)
    return result


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def parse_json(raw: bytes) -> dict:
    if len(raw) > 16384:
        raise Fault('payload_too_large', 413)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Fault('duplicate_json_key')
            result[key] = value
        return result
    def invalid_constant(_):
        raise Fault('non_finite_number')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (UnicodeError, ValueError, RecursionError):
        raise Fault('invalid_json') from None
    if type(value) is not dict:
        raise Fault('object_required')
    canonical(value)
    return value


SCHEMA = '''
CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY, simulation INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS credentials(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL REFERENCES workspaces(id), role TEXT NOT NULL,
 digest TEXT UNIQUE NOT NULL, expires INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS events(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, source TEXT NOT NULL,
 event_id TEXT NOT NULL, subject TEXT NOT NULL, kind TEXT NOT NULL, basis TEXT NOT NULL,
 observed INTEGER NOT NULL, expires INTEGER NOT NULL, received INTEGER NOT NULL,
 body TEXT NOT NULL, fingerprint TEXT NOT NULL, route TEXT NOT NULL, reason TEXT NOT NULL,
 UNIQUE(scope,source,event_id));
CREATE INDEX IF NOT EXISTS event_latest ON events(scope,source,subject,kind,basis,observed);
CREATE TABLE IF NOT EXISTS actions(
 scope TEXT NOT NULL, id TEXT NOT NULL, actor TEXT NOT NULL REFERENCES credentials(id),
 capability TEXT NOT NULL, parameters TEXT NOT NULL, fingerprint TEXT NOT NULL,
 expires INTEGER NOT NULL, state TEXT NOT NULL, created INTEGER NOT NULL, proof TEXT,
 PRIMARY KEY(scope,id));
CREATE TABLE IF NOT EXISTS outbox(
 scope TEXT NOT NULL, action_id TEXT NOT NULL, state TEXT NOT NULL,
 lease TEXT, lease_until INTEGER, attempts INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(scope,action_id), FOREIGN KEY(scope,action_id) REFERENCES actions(scope,id));
CREATE TABLE IF NOT EXISTS drafts(
 scope TEXT NOT NULL, action_id TEXT NOT NULL, body TEXT NOT NULL, digest TEXT NOT NULL,
 created INTEGER NOT NULL, PRIMARY KEY(scope,action_id),
 FOREIGN KEY(scope,action_id) REFERENCES actions(scope,id));
CREATE TABLE IF NOT EXISTS audit(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, actor TEXT NOT NULL,
 kind TEXT NOT NULL, subject TEXT NOT NULL, at INTEGER NOT NULL);
'''


class LocalCore:
    def __init__(self, path: str | Path, clock: Callable[[], float] = time.time):
        self.path, self.clock = Path(path).expanduser(), clock
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise Fault('database_symlink_rejected')
        with self.connection() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 2):
                raise Fault('unsupported_database_version')
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nPRAGMA user_version=2; COMMIT;')
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('PRAGMA busy_timeout=5000')
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def now(self) -> int:
        return timestamp(int(self.clock()))

    def provision(self, scope: str, credential_id: str, role: str, *, ttl: int = 86400,
                  simulation: bool = True) -> str:
        """Offline administrator only. Not exposed by HTTP; creates a random bearer."""
        ident(scope); ident(credential_id)
        if role not in {'owner', 'reader', 'source'} or type(simulation) is not bool:
            raise Fault('invalid_provisioning')
        if type(ttl) is not int or not 1 <= ttl <= 2592000:
            raise Fault('invalid_ttl')
        bearer = secrets.token_urlsafe(32)
        with self.transaction() as db:
            prior = db.execute('SELECT simulation FROM workspaces WHERE id=?', (scope,)).fetchone()
            if prior and prior['simulation'] != int(simulation):
                raise Fault('workspace_mode_conflict', 409)
            db.execute('INSERT OR IGNORE INTO workspaces VALUES (?,?)', (scope, int(simulation)))
            if db.execute('SELECT count(*) FROM credentials').fetchone()[0] >= 128:
                raise Fault('credential_capacity', 409)
            try:
                db.execute('INSERT INTO credentials(id,scope,role,digest,expires) VALUES (?,?,?,?,?)',
                           (credential_id, scope, role, hashlib.sha256(bearer.encode()).hexdigest(), self.now()+ttl))
            except sqlite3.IntegrityError:
                raise Fault('credential_exists', 409) from None
            self.log(db, scope, credential_id, 'credential.provisioned', credential_id)
        return bearer

    def revoke(self, credential_id: str) -> None:
        """Offline administration; revocation is checked again before local execution."""
        ident(credential_id)
        with self.transaction() as db:
            row = db.execute('SELECT * FROM credentials WHERE id=?', (credential_id,)).fetchone()
            if not row:
                raise Fault('not_found', 404)
            db.execute('UPDATE credentials SET revoked=1 WHERE id=?', (credential_id,))
            self.log(db, row['scope'], 'local-admin', 'credential.revoked', credential_id)

    def authenticate(self, db, bearer: str, roles: set[str]):
        if not isinstance(bearer, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', bearer):
            raise Fault('unauthorised', 401)
        key = hashlib.sha256(bearer.encode()).hexdigest()
        row = db.execute('SELECT * FROM credentials WHERE digest=?', (key,)).fetchone()
        if not row or row['revoked'] or row['expires'] <= self.now():
            raise Fault('unauthorised', 401)
        if row['role'] not in roles:
            raise Fault('forbidden', 403)
        return row

    def log(self, db, scope, actor, kind, subject):
        db.execute('INSERT INTO audit(scope,actor,kind,subject,at) VALUES (?,?,?,?,?)',
                   (scope, actor, kind, subject, self.now()))

    def ingest(self, bearer: str, value: dict) -> dict:
        exact(value, {'id','subject','kind','basis','observed_at','expires_at','summary'})
        ident(value['id']); ident(value['subject']); text(value['summary'], 2048)
        if value['kind'] not in {'briefing.changed','status.changed','note'}:
            raise Fault('unsupported_event')
        if value['basis'] not in {'observed','reported','derived','simulated'}:
            raise Fault('unsupported_basis')
        start, end = timestamp(value['observed_at']), timestamp(value['expires_at'])
        if not start < end or end-start > 604800:
            raise Fault('invalid_freshness_window')
        digest = fingerprint(value)
        with self.transaction() as db:
            principal = self.authenticate(db, bearer, {'source'})
            scope, source, now = principal['scope'], principal['id'], self.now()
            if start > now:
                raise Fault('future_observation')
            sim = db.execute('SELECT simulation FROM workspaces WHERE id=?', (scope,)).fetchone()[0]
            if value['basis'] == 'simulated' and not sim:
                raise Fault('simulation_not_live', 403)
            previous = db.execute('SELECT * FROM events WHERE scope=? AND source=? AND event_id=?',
                                  (scope,source,value['id'])).fetchone()
            if previous:
                if previous['fingerprint'] != digest:
                    raise Fault('event_id_collision', 409)
                return {'id':value['id'], 'route':'suppress', 'reason':'duplicate', 'synthetic_workspace':bool(sim)}
            if db.execute('SELECT count(*) FROM events WHERE scope=?', (scope,)).fetchone()[0] >= 10000:
                raise Fault('event_capacity', 409)
            latest = db.execute('SELECT max(observed) FROM events WHERE scope=? AND source=? AND subject=? AND kind=? AND basis=? AND reason!=?',
                                (scope,source,value['subject'],value['kind'],value['basis'],'expired')).fetchone()[0]
            if now >= end:
                route, reason = 'suppress', 'expired'
            elif latest is not None and start < latest:
                route, reason = 'suppress', 'out_of_order'
            elif latest == start:
                route, reason = 'queue', 'needs_reconciliation'
            elif value['basis'] in {'derived','simulated'}:
                route, reason = 'queue', 'analysis_not_observation'
            elif value['kind'] == 'briefing.changed':
                route, reason = 'display', 'explicit_change_rule'
            else:
                route, reason = 'queue', 'next_briefing'
            db.execute('INSERT INTO events(scope,source,event_id,subject,kind,basis,observed,expires,received,body,fingerprint,route,reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (scope,source,value['id'],value['subject'],value['kind'],value['basis'],start,end,now,canonical(value),digest,route,reason))
            self.log(db, scope, source, 'event.'+route, value['id'])
            return {'id':value['id'], 'route':route, 'reason':reason, 'synthetic_workspace':bool(sim)}

    def propose(self, bearer: str, value: dict) -> dict:
        exact(value, {'id','capability','parameters','expires_at'})
        ident(value['id']); timestamp(value['expires_at'])
        if value['capability'] != 'message.draft':
            raise Fault('capability_not_allowed', 403)
        exact(value['parameters'], {'text'}); text(value['parameters']['text'])
        with self.transaction() as db:
            p = self.authenticate(db, bearer, {'owner'})
            if not self.now() < value['expires_at'] <= self.now()+86400:
                raise Fault('invalid_action_expiry')
            bound = {**value, 'scope':p['scope'], 'actor':p['id']}
            digest = fingerprint(bound)
            prior = db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (p['scope'],value['id'])).fetchone()
            if prior:
                if prior['fingerprint'] != digest:
                    raise Fault('action_id_collision', 409)
                return self.action_view(prior)
            if db.execute('SELECT count(*) FROM actions WHERE scope=?', (p['scope'],)).fetchone()[0] >= 5000:
                raise Fault('action_capacity', 409)
            db.execute('INSERT INTO actions(scope,id,actor,capability,parameters,fingerprint,expires,state,created,proof) VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (p['scope'],value['id'],p['id'],value['capability'],canonical(value['parameters']),digest,value['expires_at'],'proposed',self.now(),None))
            self.log(db,p['scope'],p['id'],'action.proposed',value['id'])
            return self.action_view(db.execute('SELECT * FROM actions WHERE scope=? AND id=?',(p['scope'],value['id'])).fetchone())

    @staticmethod
    def action_view(row) -> dict:
        return {'id':row['id'],'actor':row['actor'],'capability':row['capability'],
                'parameters':json.loads(row['parameters']),'fingerprint':row['fingerprint'],
                'expires_at':row['expires'],'state':row['state'],
                'proof':json.loads(row['proof']) if row['proof'] else None,
                'effect':'local_draft_only_not_sent'}

    def owned_action(self, db, bearer, action_id):
        ident(action_id)
        p = self.authenticate(db,bearer,{'owner'})
        row = db.execute('SELECT * FROM actions WHERE scope=? AND id=?',(p['scope'],action_id)).fetchone()
        if not row or row['actor'] != p['id']:
            raise Fault('not_found',404)
        return p,row

    def approve(self,bearer: str,action_id: str,digest: str) -> dict:
        with self.transaction() as db:
            p,row = self.owned_action(db,bearer,action_id)
            if not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest) or not secrets.compare_digest(row['fingerprint'],digest):
                raise Fault('approval_mismatch',409)
            if row['expires'] <= self.now():
                raise Fault('action_expired',409)
            if row['state'] == 'queued':
                return self.action_view(row)
            if row['state'] != 'proposed':
                raise Fault('invalid_state',409)
            db.execute('UPDATE actions SET state=? WHERE scope=? AND id=?',('queued',p['scope'],action_id))
            db.execute('INSERT INTO outbox(scope,action_id,state) VALUES (?,?,?)',(p['scope'],action_id,'queued'))
            self.log(db,p['scope'],p['id'],'action.approved',action_id)
            return {'id':action_id,'state':'queued','effect':'local_draft_only_not_sent'}

    def cancel(self,bearer: str,action_id: str) -> dict:
        with self.transaction() as db:
            p,row = self.owned_action(db,bearer,action_id)
            if row['state'] == 'cancelled':
                return {'id':action_id,'state':'cancelled'}
            if row['state'] not in {'proposed','queued'}:
                raise Fault('cancellation_is_not_undo',409)
            db.execute('UPDATE actions SET state=? WHERE scope=? AND id=?',('cancelled',p['scope'],action_id))
            db.execute('UPDATE outbox SET state=? WHERE scope=? AND action_id=?',('cancelled',p['scope'],action_id))
            self.log(db,p['scope'],p['id'],'action.cancelled',action_id)
            return {'id':action_id,'state':'cancelled'}

    def valid_origin(self,db,row) -> bool:
        origin=db.execute('SELECT * FROM credentials WHERE id=?',(row['actor'],)).fetchone()
        return bool(origin and not origin['revoked'] and origin['expires']>self.now()
                    and origin['role']=='owner' and origin['scope']==row['scope']
                    and row['expires']>self.now() and row['capability']=='message.draft')

    def claim(self,bearer: str) -> dict | None:
        with self.transaction() as db:
            p=self.authenticate(db,bearer,{'owner'}); scope=p['scope']
            expired=db.execute('SELECT action_id FROM outbox WHERE scope=? AND state=? AND lease_until<=?',(scope,'executing',self.now())).fetchall()
            for item in expired:
                db.execute('UPDATE actions SET state=? WHERE scope=? AND id=?',('uncertain',scope,item['action_id']))
                db.execute('UPDATE outbox SET state=? WHERE scope=? AND action_id=?',('uncertain',scope,item['action_id']))
                self.log(db,scope,p['id'],'action.uncertain',item['action_id'])
            row=db.execute('SELECT a.* FROM actions a JOIN outbox o ON a.scope=o.scope AND a.id=o.action_id WHERE a.scope=? AND a.state=? AND o.state=? ORDER BY a.created,a.id LIMIT 1',(scope,'queued','queued')).fetchone()
            if not row:
                return None
            if not self.valid_origin(db,row):
                db.execute('UPDATE actions SET state=? WHERE scope=? AND id=?',('blocked',scope,row['id']))
                db.execute('UPDATE outbox SET state=? WHERE scope=? AND action_id=?',('blocked',scope,row['id']))
                self.log(db,scope,p['id'],'action.blocked',row['id'])
                return {'id':row['id'],'scope':scope,'state':'blocked'}
            lease=secrets.token_hex(16)
            db.execute('UPDATE actions SET state=? WHERE scope=? AND id=?',('executing',scope,row['id']))
            db.execute('UPDATE outbox SET state=?,lease=?,lease_until=?,attempts=attempts+1 WHERE scope=? AND action_id=?',('executing',lease,self.now()+30,scope,row['id']))
            self.log(db,scope,p['id'],'action.dispatched',row['id'])
            return {'id':row['id'],'scope':scope,'lease':lease,'state':'executing'}

    def leased(self,db,bearer,job):
        p=self.authenticate(db,bearer,{'owner'})
        if p['scope']!=job['scope']:
            raise Fault('forbidden',403)
        row=db.execute('SELECT a.*,o.lease,o.lease_until FROM actions a JOIN outbox o ON a.scope=o.scope AND a.id=o.action_id WHERE a.scope=? AND a.id=? AND a.state=? AND o.state=?',(p['scope'],job['id'],'executing','executing')).fetchone()
        if not row or row['lease']!=job['lease'] or row['lease_until']<=self.now():
            raise Fault('stale_lease',409)
        if not self.valid_origin(db,row):
            raise Fault('authority_revoked_or_expired',403)
        return p,row

    def execute_local(self,bearer,job):
        """The ONLY connector. Its idempotency and verification apply to SQLite drafts."""
        with self.transaction() as db:
            p,row=self.leased(db,bearer,job)
            body=json.loads(row['parameters'])['text']; digest=hashlib.sha256(body.encode()).hexdigest()
            prior=db.execute('SELECT * FROM drafts WHERE scope=? AND action_id=?',(row['scope'],row['id'])).fetchone()
            if prior and (prior['body']!=body or prior['digest']!=digest):
                raise Fault('draft_collision',409)
            db.execute('INSERT OR IGNORE INTO drafts VALUES (?,?,?,?,?)',(row['scope'],row['id'],body,digest,self.now()))
            self.log(db,row['scope'],p['id'],'connector.receipt',row['id'])

    def verify_draft(self,db,row) -> dict | None:
        draft=db.execute('SELECT * FROM drafts WHERE scope=? AND action_id=?',(row['scope'],row['id'])).fetchone()
        body=json.loads(row['parameters'])['text']; digest=hashlib.sha256(body.encode()).hexdigest()
        if not draft:
            return None
        if draft['body']!=body or draft['digest']!=digest:
            raise Fault('verification_mismatch',409)
        proof={'type':'local_sqlite_draft_readback','sha256':digest,'sent':False}
        db.execute('UPDATE actions SET state=?,proof=? WHERE scope=? AND id=?',('verified',canonical(proof),row['scope'],row['id']))
        db.execute('UPDATE outbox SET state=? WHERE scope=? AND action_id=?',('done',row['scope'],row['id']))
        self.log(db,row['scope'],row['actor'],'action.verified_local_draft',row['id'])
        return proof

    def finish(self,bearer,job) -> dict:
        with self.transaction() as db:
            _,row=self.leased(db,bearer,job); proof=self.verify_draft(db,row)
            if proof is None:
                raise Fault('no_result_to_verify',409)
            return {'id':row['id'],'state':'verified','proof':proof,'effect':'local_draft_only_not_sent'}

    def reconcile(self,bearer: str,action_id: str) -> dict:
        with self.transaction() as db:
            _,row=self.owned_action(db,bearer,action_id)
            if row['state']=='verified':
                return self.action_view(row)
            if row['state']!='uncertain':
                raise Fault('invalid_state',409)
            proof=self.verify_draft(db,row)
            return {'id':action_id,'state':'verified' if proof else 'uncertain','proof':proof,'effect':'local_draft_only_not_sent'}

    def tick(self,bearer: str,*,crash_at: str | None=None) -> dict:
        job=self.claim(bearer)
        if not job or job['state']=='blocked':
            return job or {'state':'idle'}
        if crash_at=='before_effect':
            raise RuntimeError('injected_crash_before_effect')
        self.execute_local(bearer,job)
        if crash_at=='after_effect':
            raise RuntimeError('injected_crash_after_effect')
        return self.finish(bearer,job)

    def state(self,bearer: str) -> dict:
        with self.transaction() as db:
            p=self.authenticate(db,bearer,{'owner','reader'}); scope=p['scope']
            sim=db.execute('SELECT simulation FROM workspaces WHERE id=?',(scope,)).fetchone()[0]
            events=[]
            for row in db.execute('SELECT * FROM events WHERE scope=? ORDER BY seq DESC LIMIT 100',(scope,)):
                events.append({**json.loads(row['body']),'source':row['source'],'received_at':row['received'],
                               'route':row['route'],'reason':row['reason'],'stale':row['expires']<=self.now()})
            actions=[self.action_view(r) for r in db.execute('SELECT * FROM actions WHERE scope=? ORDER BY created DESC,id LIMIT 100',(scope,))]
            audit=[dict(r) for r in db.execute('SELECT seq,actor,kind,subject,at FROM audit WHERE scope=? ORDER BY seq DESC LIMIT 100',(scope,))]
            return {'version':'0.2.0-dev','scope':scope,'synthetic_workspace':bool(sim),
                    'events':events,'actions':actions,'audit':audit,'window_limit':100,
                    'counts':{name:db.execute('SELECT count(*) FROM '+name+' WHERE scope=?',(scope,)).fetchone()[0] for name in ('events','actions','drafts','audit')},
                    'live_ai':False,'external_effects':False}
