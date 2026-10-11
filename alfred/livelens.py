"""Opt-in first-party LiveLens tools over ALFRED's authenticated desk transport.

Network reads require explicit source grants. Capture has a separate exact
approval ledger; a timeout after dispatch is uncertain and is never auto-retried.
Raw evidence is returned as untrusted data and is never saved as accepted memory.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
from .local import Fault, canonical, exact, fingerprint, ident, text
from .policy import permitted
from .livelens_client import LiveLensClient
from .livelens_gateway import LiveLensGateway

SCHEMA = '''
CREATE TABLE IF NOT EXISTS livelens_actions(
 scope TEXT NOT NULL,id TEXT NOT NULL,source TEXT NOT NULL,actor TEXT NOT NULL,
 person TEXT NOT NULL,generation INTEGER NOT NULL,config_hash TEXT NOT NULL,epoch INTEGER NOT NULL,
 operation TEXT NOT NULL,parameters TEXT NOT NULL,reason TEXT NOT NULL,fingerprint TEXT NOT NULL,
 state TEXT NOT NULL,created INTEGER NOT NULL,expires INTEGER NOT NULL,receipt TEXT,error TEXT,
 PRIMARY KEY(scope,id));
'''
READS = ('sessions', 'search', 'evidence', 'context', 'report', 'job')
CONTROLS = ('start_recording', 'stop_recording')
CONFIG_FIELDS = {'schemaVersion', 'scope', 'workspace', 'sourceCredential', 'baseUrl', 'sources',
                 'maxDurationSeconds', 'timeoutSeconds'}


def private_bytes(path, limit, vaults=()):
    from .placement import check_data_directory
    path = Path(path).expanduser().absolute()
    check_data_directory(path.parent, vaults)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        raise Fault('private_livelens_file_required') from None
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_size > limit
                or stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.getuid()):
            raise Fault('private_livelens_file_required')
        data = os.read(fd, limit + 1)
        if len(data) > limit:
            raise Fault('private_livelens_file_required')
        return data
    finally:
        os.close(fd)


def token_reader(path, vaults=()):
    path = Path(path).expanduser().absolute()
    def read():
        token = private_bytes(path, 256, vaults).decode('ascii').strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', token):
            raise Fault('invalid_livelens_runtime_token')
        return token
    read.path = path
    return read


class LiveLensTools:
    def __init__(self, store, config, *, token_provider):
        exact(config, CONFIG_FIELDS); ident(config['scope']); ident(config['sourceCredential'])
        if type(config['schemaVersion']) is not int or config['schemaVersion'] != 1 or not callable(token_provider) or config['sourceCredential'] != 'specialist-livelens':
            raise Fault('invalid_livelens_configuration')
        if type(config['maxDurationSeconds']) is not int or not 2 <= config['maxDurationSeconds'] <= 3600:
            raise Fault('invalid_livelens_duration')
        if type(config['timeoutSeconds']) not in (int, float) or not .05 <= config['timeoutSeconds'] <= 10:
            raise Fault('invalid_livelens_timeout')
        # Validate configured URL, sources and bounds without making a request.
        LiveLensClient(config['baseUrl'], 'x' * 43, config['timeoutSeconds'])
        LiveLensGateway(config['baseUrl'], config['workspace'], config['sources'], lambda: 'x' * 43,
                        lambda _: False, timeout=config['timeoutSeconds'], max_duration_seconds=config['maxDurationSeconds'])
        self.store, self.config, self.token_provider = store, json.loads(canonical(config)), token_provider
        self.config_hash = fingerprint(config)
        with store.connection() as db:
            db.executescript(SCHEMA)

    def principal(self, db, bearer, *, control=False, model=False):
        p = self.store.authenticate(db, bearer, {'owner'} if control else {'owner', 'reader'})
        if p['scope'] != self.config['scope']:
            raise Fault('livelens_not_available', 404)
        policy = db.execute('SELECT strict,epoch FROM source_policy WHERE scope=?', (p['scope'],)).fetchone()
        caps = ['connector.read', 'collection.control' if control else 'read'] + (['model'] if model else [])
        if not policy or not policy['strict'] or any(not permitted(db, p, self.config['sourceCredential'], self.store.now(), cap) for cap in caps):
            raise Fault('livelens_source_denied', 403)
        return p, policy['epoch']

    def gateway(self, bearer, *, action=None):
        p = self.store.principal(bearer)
        def grant(request):
            try:
                if request['subject'] != p['id'] or request['workspace'] != self.config['workspace']:
                    return False
                configured = {source['id'] for source in self.config['sources']}
                if not request['sourceIds'] or any(source not in configured for source in request['sourceIds']):
                    return False
                permission = request['permission']
                if permission not in ('source:read', 'collection:control', 'model:egress'):
                    return False
                with self.store.connection() as db:
                    current, epoch = self.principal(db, bearer, control=permission == 'collection:control', model=permission == 'model:egress')
                    if current['id'] != p['id']:
                        return False
                    if permission == 'collection:control':
                        if action is None or self.store.paused(current['scope']):
                            return False
                        row = db.execute('SELECT * FROM livelens_actions WHERE scope=? AND id=?', (current['scope'], action)).fetchone()
                        self.binding(row, current, epoch)
                        if row['state'] != 'dispatching':
                            return False
                return True
            except Fault:
                return False
        return LiveLensGateway(self.config['baseUrl'], self.config['workspace'], self.config['sources'], self.token_provider,
                               grant, timeout=self.config['timeoutSeconds'], max_duration_seconds=self.config['maxDurationSeconds'])

    def discovery(self, bearer):
        with self.store.connection() as db:
            p, _ = self.principal(db, bearer)
            control = p['role'] == 'owner' and permitted(db, p, self.config['sourceCredential'], self.store.now(), 'collection.control')
            model = permitted(db, p, self.config['sourceCredential'], self.store.now(), 'model')
        manifest = self.gateway(bearer).manifest()
        manifest.update(registeredInAlfred=True, registration='ALFRED authenticated desk tool transport',
                        transport='/desk/livelens', captureApproval='exact actor/parameters/configuration/source-policy binding')
        return {'configured': True, 'manifest': manifest, 'permissions': {'read': True, 'collectionControl': control, 'modelEgress': model},
                'scope': p['scope'], 'sourceCredential': self.config['sourceCredential'], 'automaticMonitoring': False}

    def read(self, bearer, body):
        exact(body, {'operation', 'parameters'})
        if body['operation'] not in READS:
            raise Fault('livelens_read_tool_required')
        with self.store.connection() as db:
            p, _ = self.principal(db, bearer)
        try:
            receipt = self.gateway(bearer).dispatch(p['id'], body['operation'], body['parameters'])
        except PermissionError:
            raise Fault('livelens_source_denied', 403) from None
        except RuntimeError:
            raise Fault('livelens_unavailable_or_timeout', 503) from None
        # Only request metadata/hash enters ALFRED's audit; no raw evidence is saved.
        with self.store.transaction() as db:
            self.principal(db, bearer)
            self.store.log(db, p['scope'], p['id'], 'livelens.read', body['operation'])
        return receipt

    def parameters(self, operation, value):
        if operation not in CONTROLS or type(value) is not dict:
            raise Fault('livelens_control_tool_required')
        fields = {'sourceId', 'jobId'} | ({'sessionId', 'maxDurationSeconds', 'segmentSeconds'} if operation == 'start_recording' else set())
        required = fields - {'segmentSeconds'}
        if set(value) - fields or not required <= set(value):
            raise Fault('invalid_livelens_parameters')
        value = json.loads(canonical(value))
        source = next((source for source in self.config['sources'] if source['id'] == value['sourceId']), None)
        if not source or not source.get('recorderSourceId'):
            raise Fault('livelens_source_denied', 403)
        from .livelens_gateway import identifier
        identifier(value['jobId'])
        if operation == 'start_recording':
            if value['sessionId'] not in source['sessionIds']:
                raise Fault('livelens_source_denied', 403)
            seconds = value['maxDurationSeconds']; value.setdefault('segmentSeconds', min(5, seconds) if type(seconds) is int else 5)
            if type(seconds) is not int or not 2 <= seconds <= self.config['maxDurationSeconds']:
                raise Fault('invalid_livelens_duration')
            if type(value['segmentSeconds']) is not int or not 2 <= value['segmentSeconds'] <= min(30, seconds):
                raise Fault('invalid_livelens_segment')
        return value

    def binding(self, row, p, epoch, *, expired=True):
        if not row or row['scope'] != p['scope'] or row['actor'] != p['id']:
            raise Fault('livelens_action_not_found', 404)
        if (row['person'] != p['person_id'] or row['generation'] != p['generation']
                or row['config_hash'] != self.config_hash or row['epoch'] != epoch):
            raise Fault('livelens_approval_changed', 409)
        if expired and row['expires'] <= self.store.now():
            raise Fault('livelens_approval_expired', 409)

    def view_row(self, row):
        return {'id': row['id'], 'state': row['state'], 'operation': row['operation'], 'parameters': json.loads(row['parameters']),
                'reason': row['reason'], 'fingerprint': row['fingerprint'], 'createdAt': row['created'], 'expiresAt': row['expires'],
                'receipt': json.loads(row['receipt']) if row['receipt'] else None, 'error': row['error'],
                'acceptanceIsCaptureCompletion': False}

    def propose(self, bearer, body):
        exact(body, {'operation', 'parameters', 'reason'}); text(body['reason'], 500)
        params = self.parameters(body['operation'], body['parameters'])
        with self.store.transaction() as db:
            p, epoch = self.principal(db, bearer, control=True)
            if self.store.paused(p['scope']):
                raise Fault('livelens_paused', 409)
            if db.execute('SELECT count(*) FROM livelens_actions WHERE scope=?', (p['scope'],)).fetchone()[0] >= 1000:
                raise Fault('livelens_action_capacity', 409)
            now, action_id = self.store.now(), 'livelens-' + secrets.token_hex(12)
            digest = fingerprint({'scope': p['scope'], 'actor': p['id'], 'person': p['person_id'], 'generation': p['generation'],
                                  'source': self.config['sourceCredential'], 'configuration': self.config_hash, 'epoch': epoch,
                                  'operation': body['operation'], 'parameters': params, 'reason': body['reason'], 'expires': now + 600})
            db.execute('INSERT INTO livelens_actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
                       (p['scope'], action_id, self.config['sourceCredential'], p['id'], p['person_id'], p['generation'], self.config_hash, epoch,
                        body['operation'], canonical(params), body['reason'], digest, 'proposed', now, now + 600))
            self.store.log(db, p['scope'], p['id'], 'livelens.proposed', action_id)
            return self.view_row(db.execute('SELECT * FROM livelens_actions WHERE scope=? AND id=?', (p['scope'], action_id)).fetchone())

    def view(self, bearer, action_id=None):
        with self.store.connection() as db:
            p, _ = self.principal(db, bearer, control=True)
            if action_id is None:
                return {'actions': [self.view_row(row) for row in db.execute('SELECT * FROM livelens_actions WHERE scope=? AND actor=? ORDER BY created DESC,id LIMIT 100', (p['scope'], p['id']))]}
            row = db.execute('SELECT * FROM livelens_actions WHERE scope=? AND id=? AND actor=?', (p['scope'], ident(action_id), p['id'])).fetchone()
            if not row:
                raise Fault('livelens_action_not_found', 404)
            return self.view_row(row)

    def approve(self, bearer, action_id, body):
        exact(body, {'fingerprint'})
        with self.store.transaction() as db:
            p, epoch = self.principal(db, bearer, control=True)
            row = db.execute('SELECT * FROM livelens_actions WHERE scope=? AND id=?', (p['scope'], ident(action_id))).fetchone()
            self.binding(row, p, epoch)
            if row['fingerprint'] != body['fingerprint']:
                raise Fault('livelens_fingerprint_mismatch', 409)
            if row['state'] not in ('proposed', 'approved'):
                raise Fault('livelens_action_state', 409)
            db.execute("UPDATE livelens_actions SET state='approved' WHERE scope=? AND id=?", (p['scope'], action_id))
            self.store.log(db, p['scope'], p['id'], 'livelens.approved', action_id)
        return self.view(bearer, action_id)

    def metadata_receipt(self, receipt):
        # Persist bounded job provenance only; captured words/media remain LiveLens-owned.
        fields = ('id', 'state', 'sourceId', 'sessionId', 'maxDurationSeconds', 'segmentSeconds', 'stopRequested', 'createdAtMs', 'startedAtMs', 'deadlineMs', 'completedAtMs')
        result = {key: receipt['result'][key] for key in fields if key in receipt['result']}
        saved = {key: receipt[key] for key in ('schemaVersion', 'id', 'workspace', 'subject', 'sourceIds', 'operation', 'receivedAtMs', 'trust', 'instructionsAccepted', 'memoryAccepted', 'modelEgress')}
        saved.update(result=result, gatewayResultSha256=receipt['resultSha256'], resultSha256=hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest(), resultProjection='bounded-job-metadata')
        return saved

    def dispatch(self, bearer, action_id, body):
        exact(body, {'fingerprint'})
        with self.store.transaction() as db:
            p, epoch = self.principal(db, bearer, control=True)
            row = db.execute('SELECT * FROM livelens_actions WHERE scope=? AND id=?', (p['scope'], ident(action_id))).fetchone()
            self.binding(row, p, epoch, expired=row is not None and row['state'] != 'completed')
            if row['fingerprint'] != body['fingerprint']:
                raise Fault('livelens_fingerprint_mismatch', 409)
            if row['state'] == 'completed':
                return self.view_row(row)
            if row['state'] != 'approved':
                raise Fault('livelens_action_requires_approval_or_reconciliation', 409)
            if self.store.paused(p['scope']):
                raise Fault('livelens_paused', 409)
            db.execute("UPDATE livelens_actions SET state='dispatching' WHERE scope=? AND id=?", (p['scope'], action_id))
            self.store.log(db, p['scope'], p['id'], 'livelens.dispatch_started', action_id)
        try:
            result = self.gateway(bearer, action=action_id).dispatch(p['id'], row['operation'], json.loads(row['parameters']))
            receipt, state, error = self.metadata_receipt(result), 'completed', None
        except (PermissionError, RuntimeError, Fault, ValueError):
            receipt, state, error = None, 'uncertain', 'livelens_outcome_requires_reconciliation'
        with self.store.transaction() as db:
            # Outcome survives credential/grant revocation; delivery still rechecks access.
            db.execute('UPDATE livelens_actions SET state=?,receipt=?,error=? WHERE scope=? AND id=?', (state, canonical(receipt) if receipt else None, error, p['scope'], action_id))
            self.store.log(db, p['scope'], p['id'], 'livelens.' + state, action_id)
        return self.view(bearer, action_id)

    def reconcile(self, bearer, action_id, body):
        exact(body, set())
        with self.store.connection() as db:
            p, _ = self.principal(db, bearer, control=True)
            row = db.execute('SELECT * FROM livelens_actions WHERE scope=? AND id=? AND actor=?', (p['scope'], ident(action_id), p['id'])).fetchone()
            if not row or row['config_hash'] != self.config_hash:
                raise Fault('livelens_action_not_found', 404)
            if row['state'] not in ('dispatching', 'uncertain', 'completed'):
                raise Fault('livelens_action_state', 409)
        params = json.loads(row['parameters'])
        try:
            receipt = self.gateway(bearer).dispatch(p['id'], 'job', {'sourceId': params['sourceId'], 'jobId': params['jobId']})
        except (PermissionError, RuntimeError):
            raise Fault('livelens_reconciliation_unavailable', 409) from None
        outcome = receipt['result']
        if row['operation'] == 'start_recording' and any(outcome.get(key) != params[key] for key in ('sessionId', 'maxDurationSeconds', 'segmentSeconds')):
            raise Fault('livelens_reconciliation_conflict', 409)
        accepted = row['operation'] == 'start_recording' or outcome.get('stopRequested') is True or outcome.get('state') == 'stopped'
        if not accepted:
            raise Fault('livelens_stop_outcome_unconfirmed', 409)
        with self.store.transaction() as db:
            self.principal(db, bearer, control=True)
            db.execute("UPDATE livelens_actions SET state='completed',receipt=?,error=NULL WHERE scope=? AND id=?", (canonical(self.metadata_receipt(receipt)), p['scope'], action_id))
            self.store.log(db, p['scope'], p['id'], 'livelens.reconciled', action_id)
        return self.view(bearer, action_id)


def route(service, path, mutation, bearer, body):
    if service is None:
        if path == '/desk/livelens' and not mutation:
            return {'configured': False, 'tools': [], 'automaticMonitoring': False}
        raise Fault('livelens_not_configured', 409)
    if path == '/desk/livelens' and not mutation:
        return service.discovery(bearer)
    if path == '/desk/livelens/read' and mutation:
        return service.read(bearer, body)
    if path == '/desk/livelens/actions':
        return service.propose(bearer, body) if mutation else service.view(bearer)
    match = re.fullmatch(r'/desk/livelens/actions/(livelens-[0-9a-f]{24})(?:/(approve|dispatch|reconcile))?', path)
    if match and mutation and match[2]:
        return getattr(service, match[2])(bearer, match[1], body)
    if match and not mutation and not match[2]:
        return service.view(bearer, match[1])
    raise Fault('not_found', 404)


def load_configuration(path, vaults=()):
    try:
        value = json.loads(private_bytes(path, 16384, vaults))
    except (ValueError, UnicodeError):
        raise Fault('invalid_livelens_configuration') from None
    exact(value, CONFIG_FIELDS | {'tokenFile'})
    token_file = value.pop('tokenFile')
    if not isinstance(token_file, str) or not Path(token_file).expanduser().is_absolute():
        raise Fault('absolute_livelens_token_file_required')
    reader = token_reader(token_file, vaults)
    reader()  # Validate now; each operation still reads the current private file.
    return value, reader


def installed(store, home, vaults=()):
    from .placement import check_data_directory
    check_data_directory(home, vaults)
    path = Path(home) / 'livelens-config.json'
    if not path.exists() and not path.is_symlink():
        return None
    config, token_provider = load_configuration(path, vaults)
    return LiveLensTools(store, config, token_provider=token_provider)


def connect(store, owner, home, config_file, *, collection=False, renew_source=False, vaults=()):
    """Offline explicit registration, using existing owner/source grant semantics."""
    from .connectors import offline
    from .policy import IdentityPolicy
    from .placement import check_data_directory
    check_data_directory(home, vaults)
    config, token_provider = load_configuration(config_file, vaults)
    with offline(Path(home)):
        tools = LiveLensTools(store, config, token_provider=token_provider)
        p = store.principal(owner, {'owner'})
        if p['scope'] != config['scope']:
            raise Fault('livelens_scope_mismatch', 403)
        with store.connection() as db:
            source = db.execute('SELECT * FROM credentials WHERE id=?', (config['sourceCredential'],)).fetchone()
            simulation = db.execute('SELECT simulation FROM workspaces WHERE id=?', (p['scope'],)).fetchone()[0]
        if source is None:
            # This is an ALFRED source identity, not a LiveLens API credential.
            # Its generated bearer is never printed or persisted as a runtime secret.
            store.provision(p['scope'], config['sourceCredential'], 'source', ttl=2592000, simulation=bool(simulation))
        with store.connection() as db:
            source = db.execute('SELECT * FROM credentials WHERE id=?', (config['sourceCredential'],)).fetchone()
        if source['scope'] != p['scope'] or source['role'] != 'source' or source['revoked']:
            raise Fault('livelens_source_not_available', 409)
        if renew_source:
            with store.transaction() as db:
                store.authenticate(db, owner, {'owner'})
                # Offline owner renewal never reactivates a revoked/forgotten source.
                changed = db.execute('UPDATE credentials SET expires=?,digest=? WHERE id=? AND scope=? AND role=? AND revoked=0',
                    (store.now()+2592000, hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest(), config['sourceCredential'], p['scope'], 'source')).rowcount
                if changed != 1:
                    raise Fault('livelens_source_not_available', 409)
                db.execute('UPDATE identity_devices SET generation=generation+1 WHERE credential=?', (config['sourceCredential'],))
                store.log(db, p['scope'], p['id'], 'livelens.source_renewed', config['sourceCredential'])
            with store.connection() as db:
                source = db.execute('SELECT * FROM credentials WHERE id=?', (config['sourceCredential'],)).fetchone()
        if source['expires'] <= store.now():
            raise Fault('livelens_source_renewal_required', 409)
        policy = IdentityPolicy(store)
        for cap in ('connector.read', 'read'):
            policy.grant(owner, config['sourceCredential'], cap, min(source['expires'], p['expires']), policy.view(owner)['epoch'])
        policy.grant(owner, config['sourceCredential'], 'collection.control', min(source['expires'], p['expires']),
                     policy.view(owner)['epoch'], revoke=not collection)
        target = Path(home) / 'livelens-config.json'
        value = dict(config, tokenFile=str(token_provider.path))
        temp = target.with_name(target.name + '.new-' + secrets.token_hex(6))
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(canonical(value) + '\n'); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, target)
            directory_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temp.unlink(missing_ok=True)
        with store.transaction() as db:
            p = store.authenticate(db, owner, {'owner'})
            store.log(db, p['scope'], p['id'], 'livelens.connected', config['sourceCredential'])
    return {'registered': True, 'scope': config['scope'], 'sourceCredential': config['sourceCredential'],
            'readGranted': True, 'collectionControlGranted': collection, 'modelGranted': False, 'automaticMonitoring': False}
