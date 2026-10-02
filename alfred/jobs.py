"""Stage 0 local job coordinator, replaceable worker backend and bounded cache.

The coordinator owns durable job records in ALFRED's own SQLite database: jobs,
append-only job events with a per-job sequence, enrolled workers and
content-addressed result artefacts. It is separate from the action outbox in
``alfred.local``, whose only effect remains an approved local draft.

Execution happens behind ``WorkerBackend``. The only backend here is
``LocalSubprocessBackend``: a local subprocess on the same host, user account
and kernel. It is not VM isolation, not a remote worker and not a sandbox.

Models propose, independent policy decides. Declared note inputs are checked
against source grants at submission and again at lease time, bound to exact
revisions, and only their bytes reach the job process. A worker's result is a
claim: the coordinator verifies that the bytes match the SHA-256 the worker
states, not that the content is correct. See docs/JOBS.md.

Job states and transitions (every transition appends a job event):

    queued           -> leased (worker lease), cancelled (owner cancel),
                        failed (inputs or authority denied at lease time)
    leased           -> running (worker start), cancel_requested (owner cancel),
                        queued/failed/effect_unknown (lease expiry, see recover)
    running          -> succeeded (verified result), failed, queued (retryable
                        failure of a side-effect-free job with attempts left),
                        effect_unknown (any non-success of a job with possible
                        effects), cancel_requested (owner cancel), lease expiry
    cancel_requested -> cancelled (worker stopped a side-effect-free job, or its
                        lease expired), effect_unknown (job with possible
                        effects), succeeded (finished before it saw the request)
    effect_unknown   -> reconciled (owner records a finding; acknowledgement,
                        not verification)
    succeeded, failed, cancelled, reconciled: final.
"""
from __future__ import annotations
import abc
import base64
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time

from . import job_kinds
from .local import Fault, canonical, fingerprint, ident, text
from .policy import permitted

JOBS_VERSION = 1
STATES = ('queued', 'leased', 'running', 'cancel_requested', 'succeeded', 'failed',
          'cancelled', 'effect_unknown', 'reconciled')
ACTIVE = ('leased', 'running', 'cancel_requested')
FINISHED = ('succeeded', 'failed', 'cancelled', 'effect_unknown', 'reconciled')
FINDINGS = ('effect_happened', 'effect_did_not_happen', 'undetermined')
MEDIA_TYPES = ('application/json', 'text/plain', 'application/octet-stream')
MAX_INPUTS = 16
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_ARTEFACT_BYTES = 1024 * 1024
MAX_SCOPE_ARTEFACT_BYTES = 256 * 1024 * 1024
MAX_JOBS = 10000
MAX_WORKERS = 64
MAX_ATTEMPTS = 10
MAX_LEASE_SECONDS = 3600
DEFAULT_ATTEMPTS = 3
NOTE_ID = re.compile(r'[0-9a-f]{24}')
SHA256 = re.compile(r'[0-9a-f]{64}')
REASON = re.compile(r'[a-z][a-z0-9_]{0,63}')
REPOSITORY = Path(__file__).resolve().parents[1]
BACKEND_NOTE = 'local subprocess: not VM isolation, not a remote worker, not a sandbox'

SCHEMA = '''
CREATE TABLE IF NOT EXISTS jobs_meta(version INTEGER NOT NULL);
INSERT INTO jobs_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM jobs_meta);
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL REFERENCES workspaces(id),
 actor TEXT NOT NULL REFERENCES credentials(id), kind TEXT NOT NULL,
 parameters TEXT NOT NULL, inputs TEXT NOT NULL, idempotency_key TEXT NOT NULL,
 fingerprint TEXT NOT NULL, side_effect_free INTEGER NOT NULL, state TEXT NOT NULL,
 reason TEXT, attempt INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
 lease_owner TEXT, lease_digest TEXT, lease_until INTEGER, started INTEGER,
 cancel_requested INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL,
 updated INTEGER NOT NULL, result_artefact TEXT,
 UNIQUE(scope,actor,idempotency_key),
 CHECK(state IN ('queued','leased','running','cancel_requested','succeeded','failed',
                 'cancelled','effect_unknown','reconciled')));
CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(scope,state,created);
CREATE TABLE IF NOT EXISTS job_events(
 job_id TEXT NOT NULL REFERENCES jobs(id), sequence INTEGER NOT NULL,
 kind TEXT NOT NULL, detail TEXT NOT NULL, at INTEGER NOT NULL,
 PRIMARY KEY(job_id,sequence));
CREATE TRIGGER IF NOT EXISTS job_events_sequence BEFORE INSERT ON job_events
 WHEN NEW.sequence != (SELECT coalesce(max(sequence),0)+1 FROM job_events WHERE job_id=NEW.job_id)
 BEGIN SELECT RAISE(ABORT,'job_event_sequence'); END;
CREATE TRIGGER IF NOT EXISTS job_events_no_update BEFORE UPDATE ON job_events
 BEGIN SELECT RAISE(ABORT,'job_events_append_only'); END;
CREATE TRIGGER IF NOT EXISTS job_events_no_delete BEFORE DELETE ON job_events
 BEGIN SELECT RAISE(ABORT,'job_events_append_only'); END;
CREATE TABLE IF NOT EXISTS workers(
 scope TEXT NOT NULL REFERENCES workspaces(id), id TEXT NOT NULL, label TEXT NOT NULL,
 capabilities TEXT NOT NULL, enrolled_by TEXT NOT NULL REFERENCES credentials(id),
 enrolled_at INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(scope,id));
CREATE TABLE IF NOT EXISTS artefacts(
 scope TEXT NOT NULL REFERENCES workspaces(id), sha256 TEXT NOT NULL,
 size INTEGER NOT NULL, media_type TEXT NOT NULL, job_id TEXT NOT NULL REFERENCES jobs(id),
 created INTEGER NOT NULL, lineage TEXT NOT NULL, body BLOB NOT NULL,
 PRIMARY KEY(scope,sha256));
'''


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _bounded_ttl(ttl) -> int:
    if type(ttl) is not int or not 1 <= ttl <= MAX_LEASE_SECONDS:
        raise Fault('invalid_lease_ttl')
    return ttl


class JobCoordinator:
    """Durable job authority over a ``LocalCore``-family store.

    Every call authenticates a bearer with ``store.authenticate`` inside the
    transaction that reads or changes job state. Owners submit, cancel,
    reconcile, recover and enrol or revoke workers. Owners and readers view
    jobs, events and artefacts in their own workspace scope only. Worker calls
    must present the bearer of the owner credential that enrolled the worker,
    the worker ID and, after leasing, the job's lease token.
    """

    def __init__(self, store, *, cache: 'BoundedCache | None' = None):
        self.store, self.cache = store, cache
        with store.connection() as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs_meta'").fetchone()
            versions = [r[0] for r in db.execute('SELECT version FROM jobs_meta')] if exists else [JOBS_VERSION]
            if versions != [JOBS_VERSION]:
                raise Fault('unsupported_jobs_version')
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')

    # Shared helpers -----------------------------------------------------

    @contextmanager
    def _read(self):
        with self.store.connection() as db:
            db.execute('BEGIN')
            try:
                yield db
            finally:
                db.rollback()

    def _event(self, db, job_id, kind, detail=None):
        now = self.store.now()
        sequence = db.execute('SELECT coalesce(max(sequence),0)+1 FROM job_events WHERE job_id=?', (job_id,)).fetchone()[0]
        db.execute('INSERT INTO job_events(job_id,sequence,kind,detail,at) VALUES (?,?,?,?,?)',
                   (job_id, sequence, kind, canonical(detail or {}), now))
        db.execute('UPDATE jobs SET updated=? WHERE id=?', (now, job_id))
        return sequence

    def _job(self, db, scope, job_id):
        ident(job_id)
        row = db.execute('SELECT * FROM jobs WHERE scope=? AND id=?', (scope, job_id)).fetchone()
        if not row:
            raise Fault('not_found', 404)
        return row

    def _settle(self, db, row, state, reason):
        db.execute('UPDATE jobs SET state=?,reason=?,lease_owner=NULL,lease_digest=NULL,lease_until=NULL WHERE id=?',
                   (state, reason, row['id']))

    def _view(self, db, row) -> dict:
        result = None
        if row['result_artefact']:
            artefact = db.execute('SELECT sha256,size,media_type FROM artefacts WHERE scope=? AND sha256=?',
                                  (row['scope'], row['result_artefact'])).fetchone()
            result = dict(artefact) | {'basis': 'worker_claim_bytes_match_sha256_content_not_verified'}
        last = db.execute('SELECT coalesce(max(sequence),0) FROM job_events WHERE job_id=?', (row['id'],)).fetchone()[0]
        return {'id': row['id'], 'scope': row['scope'], 'actor': row['actor'], 'kind': row['kind'],
                'parameters': json.loads(row['parameters']), 'inputs': json.loads(row['inputs']),
                'idempotency_key': row['idempotency_key'], 'fingerprint': row['fingerprint'],
                'side_effect_free': bool(row['side_effect_free']), 'state': row['state'],
                'reason': row['reason'], 'attempt': row['attempt'], 'max_attempts': row['max_attempts'],
                'lease_owner': row['lease_owner'], 'lease_until': row['lease_until'],
                'started_at': row['started'], 'cancel_requested': bool(row['cancel_requested']),
                'created_at': row['created'], 'updated_at': row['updated'], 'result': result,
                'last_sequence': last, 'finished': row['state'] in FINISHED,
                'needs_reconciliation': row['state'] == 'effect_unknown'}

    @staticmethod
    def _worker_view(row) -> dict:
        return {'id': row['id'], 'scope': row['scope'], 'label': row['label'],
                'capabilities': json.loads(row['capabilities']), 'enrolled_by': row['enrolled_by'],
                'enrolled_at': row['enrolled_at'], 'revoked': bool(row['revoked'])}

    # Inputs and policy --------------------------------------------------

    @staticmethod
    def _declared(inputs) -> list:
        if type(inputs) is not list or len(inputs) > MAX_INPUTS:
            raise Fault('invalid_inputs')
        declared, seen = [], set()
        for item in inputs:
            if type(item) is not dict:
                raise Fault('invalid_inputs')
            if set(item) in ({'note'}, {'note', 'revision'}):
                if not isinstance(item['note'], str) or not NOTE_ID.fullmatch(item['note']):
                    raise Fault('invalid_inputs')
                ref = {'note': item['note']}
                if 'revision' in item:
                    if type(item['revision']) is not int or not 1 <= item['revision'] <= 2**31:
                        raise Fault('invalid_inputs')
                    ref['revision'] = item['revision']
                key = ('note', item['note'])
            elif set(item) == {'artefact'}:
                if not isinstance(item['artefact'], str) or not SHA256.fullmatch(item['artefact']):
                    raise Fault('invalid_inputs')
                ref, key = {'artefact': item['artefact']}, ('artefact', item['artefact'])
            else:
                raise Fault('invalid_inputs')
            if key in seen:
                raise Fault('duplicate_input')
            seen.add(key)
            declared.append(ref)
        return declared

    def _note(self, db, scope, note_id):
        """The current, ready note from an active source, or None. Policy is checked separately."""
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_notes'").fetchone():
            return None
        return db.execute('''SELECT n.source,n.revision,n.sha256,n.body FROM knowledge_notes n
            JOIN credentials c ON c.id=n.source AND c.scope=n.scope
            JOIN knowledge_sources s ON s.scope=n.scope AND s.source=n.source
            WHERE n.scope=? AND n.id=? AND n.status='ready' AND c.revoked=0 AND c.expires>?
            AND s.status IN ('ready','attention')''', (scope, note_id, self.store.now())).fetchone()

    @staticmethod
    def _lineage_live(db, scope, lineage) -> bool:
        """False once any note a result was derived from has been deleted (M05).

        Deletion blocks dependent results; a later edit does not, because the result
        records the exact revision it was derived from.
        """
        pending, seen = [lineage], set()
        while pending:
            current = pending.pop()
            for note in current.get('notes', []):
                row = db.execute('SELECT status FROM knowledge_notes WHERE scope=? AND id=?', (scope, note['id'])).fetchone()
                if not row or row['status'] == 'missing':
                    return False
            for parent in current.get('artefacts', []):
                if parent in seen:
                    continue
                seen.add(parent)
                row = db.execute('SELECT lineage FROM artefacts WHERE scope=? AND sha256=?', (scope, parent)).fetchone()
                if not row:
                    return False
                pending.append(json.loads(row['lineage']))
        return True

    def _sources_permitted(self, db, principal, sources, capability) -> bool:
        now = self.store.now()
        return all(permitted(db, principal, source, now, capability) for source in sources)

    def _resolve(self, db, principal, declared, capability):
        """Bind declared references to current revisions. Returns (bound, size) or raises."""
        bound, size = [], 0
        for ref in declared:
            if 'note' in ref:
                note = self._note(db, principal['scope'], ref['note'])
                if not note or not self._sources_permitted(db, principal, [note['source']], capability):
                    raise Fault('inputs_denied', 403)
                if 'revision' in ref and ref['revision'] != note['revision']:
                    raise Fault('input_revision_changed', 409)
                bound.append({'type': 'note', 'id': ref['note'], 'source': note['source'],
                              'revision': note['revision'], 'source_sha256': note['sha256']})
                size += len(note['body'].encode('utf-8'))
            else:
                artefact = db.execute('SELECT size,lineage FROM artefacts WHERE scope=? AND sha256=?',
                                      (principal['scope'], ref['artefact'])).fetchone()
                lineage = json.loads(artefact['lineage']) if artefact else None
                sources = lineage['sources'] if artefact else None
                if (not artefact or not self._sources_permitted(db, principal, sources, capability)
                        or not self._lineage_live(db, principal['scope'], lineage)):
                    raise Fault('inputs_denied', 403)
                bound.append({'type': 'artefact', 'sha256': ref['artefact'], 'size': artefact['size'],
                              'sources': sources})
                size += artefact['size']
        if size > MAX_INPUT_BYTES:
            raise Fault('inputs_too_large', 413)
        return bound

    def _actor_valid(self, db, row) -> bool:
        actor = db.execute('SELECT scope,role,revoked,expires FROM credentials WHERE id=?', (row['actor'],)).fetchone()
        return bool(actor and not actor['revoked'] and actor['expires'] > self.store.now()
                    and actor['role'] == 'owner' and actor['scope'] == row['scope'])

    def _dispatch_inputs(self, db, row):
        """Recheck authority and every bound input at lease time. Returns (inputs, reason)."""
        if not self._actor_valid(db, row):
            return None, 'authority_revoked'
        if row['kind'] not in job_kinds.KINDS:
            return None, 'unknown_job_kind'
        principal = {'scope': row['scope'], 'id': row['actor']}
        capability = job_kinds.KINDS[row['kind']]['capability']
        delivered = []
        for index, item in enumerate(json.loads(row['inputs'])):
            if item['type'] == 'note':
                note = self._note(db, row['scope'], item['id'])
                if not note or not self._sources_permitted(db, principal, [note['source']], capability):
                    return None, 'inputs_denied'
                if note['revision'] != item['revision'] or note['sha256'] != item['source_sha256']:
                    return None, 'inputs_changed'
                data = note['body'].encode('utf-8')
            else:
                artefact = db.execute('SELECT lineage,body FROM artefacts WHERE scope=? AND sha256=?',
                                      (row['scope'], item['sha256'])).fetchone()
                if (not artefact or not self._sources_permitted(db, principal, json.loads(artefact['lineage'])['sources'], capability)
                        or not self._lineage_live(db, row['scope'], json.loads(artefact['lineage']))):
                    return None, 'inputs_denied'
                data = bytes(artefact['body'])
                if hashlib.sha256(data).hexdigest() != item['sha256']:
                    return None, 'input_artefact_corrupt'
            delivered.append({'name': f'input-{index}', 'sha256': hashlib.sha256(data).hexdigest(),
                              'size': len(data), 'data': data})
        if sum(item['size'] for item in delivered) > MAX_INPUT_BYTES:
            return None, 'inputs_too_large'
        return delivered, None

    @staticmethod
    def _lineage(row) -> dict:
        sources, notes, artefacts = set(), [], []
        for item in json.loads(row['inputs']):
            if item['type'] == 'note':
                sources.add(item['source'])
                notes.append({'id': item['id'], 'revision': item['revision'], 'source_sha256': item['source_sha256']})
            else:
                sources.update(item['sources'])
                artefacts.append(item['sha256'])
        return {'sources': sorted(sources), 'notes': notes, 'artefacts': artefacts}

    # Owner and reader calls --------------------------------------------

    def submit(self, bearer, request) -> dict:
        """Create a job, or return the existing one for the same key and request."""
        required = {'idempotency_key', 'kind', 'parameters', 'inputs', 'side_effect_free'}
        if type(request) is not dict or not required <= set(request) or not set(request) <= required | {'max_attempts'}:
            raise Fault('invalid_fields')
        key = ident(request['idempotency_key'])
        try:
            parameters = job_kinds.validate(request['kind'], request['parameters'])
        except ValueError as exc:
            raise Fault(str(exc)) from None
        kind = request['kind']
        side_effect_free = request['side_effect_free']
        if type(side_effect_free) is not bool:
            raise Fault('invalid_side_effect_flag')
        if side_effect_free and not job_kinds.KINDS[kind]['side_effect_free']:
            raise Fault('side_effect_claim_not_allowed')
        max_attempts = request.get('max_attempts', DEFAULT_ATTEMPTS)
        if type(max_attempts) is not int or not 1 <= max_attempts <= MAX_ATTEMPTS:
            raise Fault('invalid_max_attempts')
        declared = self._declared(request['inputs'])
        digest = fingerprint({'kind': kind, 'parameters': parameters, 'inputs': declared,
                              'side_effect_free': side_effect_free, 'max_attempts': max_attempts})
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            prior = db.execute('SELECT * FROM jobs WHERE scope=? AND actor=? AND idempotency_key=?',
                               (p['scope'], p['id'], key)).fetchone()
            if prior:
                if not secrets.compare_digest(prior['fingerprint'], digest):
                    raise Fault('idempotency_key_collision', 409)
                return self._view(db, prior)
            if db.execute('SELECT count(*) FROM jobs WHERE scope=?', (p['scope'],)).fetchone()[0] >= MAX_JOBS:
                raise Fault('job_capacity', 409)
            bound = self._resolve(db, p, declared, job_kinds.KINDS[kind]['capability'])
            job_id, now = 'job-' + secrets.token_hex(12), self.store.now()
            db.execute('''INSERT INTO jobs(id,scope,actor,kind,parameters,inputs,idempotency_key,fingerprint,
                side_effect_free,state,max_attempts,created,updated) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                       (job_id, p['scope'], p['id'], kind, canonical(parameters), json.dumps(bound, sort_keys=True),
                        key, digest, int(side_effect_free), 'queued', max_attempts, now, now))
            self._event(db, job_id, 'submitted', {'by': p['id'], 'kind': kind, 'inputs': len(bound),
                                                  'side_effect_free': side_effect_free})
            self.store.log(db, p['scope'], p['id'], 'job.submitted', job_id)
            return self._view(db, self._job(db, p['scope'], job_id))

    def view(self, bearer, job_id) -> dict:
        with self._read() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            return self._view(db, self._job(db, p['scope'], job_id))

    def jobs(self, bearer, *, limit=50) -> list:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise Fault('invalid_limit')
        with self._read() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            rows = db.execute('SELECT * FROM jobs WHERE scope=? ORDER BY created DESC,id DESC LIMIT ?', (p['scope'], limit)).fetchall()
            return [self._view(db, row) for row in rows]

    def events(self, bearer, job_id, after_sequence=0, *, limit=100) -> dict:
        """Events after a cursor, so a reconnecting client resumes where it stopped."""
        if type(after_sequence) is not int or after_sequence < 0:
            raise Fault('invalid_cursor')
        if type(limit) is not int or not 1 <= limit <= 500:
            raise Fault('invalid_limit')
        with self._read() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            row = self._job(db, p['scope'], job_id)
            items = [{'sequence': r['sequence'], 'kind': r['kind'], 'detail': json.loads(r['detail']), 'at': r['at']}
                     for r in db.execute('SELECT * FROM job_events WHERE job_id=? AND sequence>? ORDER BY sequence LIMIT ?',
                                         (row['id'], after_sequence, limit + 1))]
            more = len(items) > limit
            items = items[:limit]
            return {'job': row['id'], 'state': row['state'], 'finished': row['state'] in FINISHED,
                    'events': items, 'next_cursor': items[-1]['sequence'] if items else after_sequence,
                    'more': more}

    def cancel(self, bearer, job_id) -> dict:
        """Cooperative cancellation. A queued job is cancelled at once; cancellation is not undo."""
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            row = self._job(db, p['scope'], job_id)
            if row['state'] in ('cancelled', 'cancel_requested'):
                return self._view(db, row)
            if row['state'] == 'queued':
                self._settle(db, row, 'cancelled', 'cancelled_before_lease')
                db.execute('UPDATE jobs SET cancel_requested=1 WHERE id=?', (row['id'],))
                self._event(db, row['id'], 'cancelled', {'by': p['id'], 'before_lease': True})
            elif row['state'] in ('leased', 'running'):
                db.execute("UPDATE jobs SET state='cancel_requested',cancel_requested=1 WHERE id=?", (row['id'],))
                self._event(db, row['id'], 'cancel_requested', {'by': p['id']})
            else:
                raise Fault('cancellation_is_not_undo', 409)
            self.store.log(db, p['scope'], p['id'], 'job.cancel', row['id'])
            return self._view(db, self._job(db, p['scope'], job_id))

    def reconcile(self, bearer, job_id, finding) -> dict:
        """Record the owner's finding for a job whose external effect is unknown."""
        if finding not in FINDINGS:
            raise Fault('invalid_finding')
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            row = self._job(db, p['scope'], job_id)
            if row['state'] != 'effect_unknown':
                raise Fault('invalid_state', 409)
            db.execute("UPDATE jobs SET state='reconciled',reason=? WHERE id=?", (finding, row['id']))
            self._event(db, row['id'], 'reconciled', {'by': p['id'], 'finding': finding,
                                                      'basis': 'owner_acknowledgement_not_verification'})
            self.store.log(db, p['scope'], p['id'], 'job.reconciled', row['id'])
            return self._view(db, self._job(db, p['scope'], job_id))

    def artefact(self, bearer, sha256) -> dict:
        """Read a result after rechecking every source in its lineage."""
        if not isinstance(sha256, str) or not SHA256.fullmatch(sha256):
            raise Fault('invalid_sha256')
        with self._read() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            row = db.execute('SELECT * FROM artefacts WHERE scope=? AND sha256=?', (p['scope'], sha256)).fetchone()
            if (not row or not self._sources_permitted(db, p, json.loads(row['lineage'])['sources'], 'read')
                    or not self._lineage_live(db, p['scope'], json.loads(row['lineage']))):
                raise Fault('artefact_not_available', 404)
            meta = {'sha256': row['sha256'], 'size': row['size'], 'media_type': row['media_type'],
                    'job_id': row['job_id'], 'created_at': row['created'], 'lineage': json.loads(row['lineage'])}
            body = bytes(row['body'])
        data, served = None, 'database'
        if self.cache is not None:
            try:
                data = self.cache.get(sha256)
            except Fault:
                data = None  # The cache removed a corrupt local copy; fall back to the record.
            served = 'cache' if data is not None else served
        if data is None:
            if hashlib.sha256(body).hexdigest() != sha256:
                raise Fault('artefact_corrupt', 500)
            data = body
            self._mirror(data)
        return meta | {'data': data, 'served_from': served}

    def _mirror(self, data):
        if self.cache is None:
            return
        try:
            self.cache.put(data)
        except (Fault, OSError):
            pass  # The cache is an accelerator; the database copy remains the record.

    # Workers --------------------------------------------------------------

    def enrol_worker(self, bearer, worker_id, label, capabilities) -> dict:
        ident(worker_id); text(label, 120)
        if (type(capabilities) is not list or not 1 <= len(capabilities) <= len(job_kinds.KINDS)
                or any(not isinstance(c, str) or c not in job_kinds.KINDS for c in capabilities)
                or len(set(capabilities)) != len(capabilities)):
            raise Fault('invalid_capabilities')
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            if db.execute('SELECT 1 FROM workers WHERE scope=? AND id=?', (p['scope'], worker_id)).fetchone():
                raise Fault('worker_exists', 409)
            if db.execute('SELECT count(*) FROM workers WHERE scope=?', (p['scope'],)).fetchone()[0] >= MAX_WORKERS:
                raise Fault('worker_capacity', 409)
            db.execute('INSERT INTO workers VALUES (?,?,?,?,?,?,0)',
                       (p['scope'], worker_id, label, json.dumps(sorted(capabilities)), p['id'], self.store.now()))
            self.store.log(db, p['scope'], p['id'], 'job.worker_enrolled', worker_id)
            return self._worker_view(db.execute('SELECT * FROM workers WHERE scope=? AND id=?', (p['scope'], worker_id)).fetchone())

    def workers(self, bearer) -> list:
        with self._read() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            return [self._worker_view(r) for r in db.execute('SELECT * FROM workers WHERE scope=? ORDER BY id', (p['scope'],))]

    def revoke_worker(self, bearer, worker_id) -> dict:
        """Permanent. The worker's active leases end now and are recovered."""
        ident(worker_id)
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            worker = db.execute('SELECT * FROM workers WHERE scope=? AND id=?', (p['scope'], worker_id)).fetchone()
            if not worker:
                raise Fault('not_found', 404)
            if not worker['revoked']:
                db.execute('UPDATE workers SET revoked=1 WHERE scope=? AND id=?', (p['scope'], worker_id))
                self.store.log(db, p['scope'], p['id'], 'job.worker_revoked', worker_id)
            for row in db.execute("SELECT * FROM jobs WHERE scope=? AND lease_owner=? AND state IN ('leased','running','cancel_requested')",
                                  (p['scope'], worker_id)).fetchall():
                db.execute('UPDATE jobs SET lease_until=? WHERE id=?', (self.store.now(), row['id']))
                self._event(db, row['id'], 'lease_revoked', {'worker': worker_id, 'by': p['id']})
            recovered = self._recover(db, p['scope'], p['id'])
            worker = db.execute('SELECT * FROM workers WHERE scope=? AND id=?', (p['scope'], worker_id)).fetchone()
            return {'worker': self._worker_view(worker), 'recovered': recovered}

    def _worker(self, db, bearer, worker_id):
        ident(worker_id)
        p = self.store.authenticate(db, bearer, {'owner'})
        worker = db.execute('SELECT * FROM workers WHERE scope=? AND id=?', (p['scope'], worker_id)).fetchone()
        if not worker:
            raise Fault('not_found', 404)
        if worker['revoked']:
            raise Fault('worker_revoked', 403)
        if worker['enrolled_by'] != p['id']:
            raise Fault('worker_operator_mismatch', 403)
        return p, worker

    def _leased(self, db, bearer, worker_id, job_id, lease):
        p, worker = self._worker(db, bearer, worker_id)
        row = self._job(db, p['scope'], job_id)
        if (row['state'] not in ACTIVE or row['lease_owner'] != worker['id'] or not isinstance(lease, str)
                or not row['lease_digest'] or not secrets.compare_digest(row['lease_digest'], _digest(lease))
                or row['lease_until'] <= self.store.now()):
            raise Fault('stale_lease', 409)
        return p, worker, row

    def _recover(self, db, scope, by) -> dict:
        """Settle expired leases: requeue only side-effect-free work with attempts left."""
        outcome = {'requeued': [], 'failed': [], 'cancelled': [], 'effect_unknown': []}
        for row in db.execute("""SELECT * FROM jobs WHERE scope=? AND state IN ('leased','running','cancel_requested')
                AND lease_until<=? ORDER BY created,id""", (scope, self.store.now())).fetchall():
            if not row['side_effect_free']:
                state, reason = 'effect_unknown', 'lease_expired_with_possible_effect'
            elif row['state'] == 'cancel_requested':
                state, reason = 'cancelled', 'lease_expired_after_cancel_request'
            elif row['attempt'] < row['max_attempts']:
                state, reason = 'queued', 'lease_expired_requeued'
            else:
                state, reason = 'failed', 'attempts_exhausted'
            self._settle(db, row, state, reason)
            self._event(db, row['id'], 'lease_expired', {'worker': row['lease_owner'], 'attempt': row['attempt'],
                                                         'outcome': state, 'by': by})
            outcome['requeued' if state == 'queued' else state].append(row['id'])
        return outcome

    def recover(self, bearer) -> dict:
        """Explicit sweep of expired leases in the caller's scope (``lease`` also does this)."""
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner'})
            return self._recover(db, p['scope'], p['id'])

    def lease(self, bearer, worker_id, *, ttl=30) -> dict | None:
        """Give one queued job this worker is capable of, with only its permitted input bytes."""
        _bounded_ttl(ttl)
        with self.store.transaction() as db:
            p, worker = self._worker(db, bearer, worker_id)
            self._recover(db, p['scope'], p['id'])
            kinds = json.loads(worker['capabilities'])
            rows = db.execute(f"""SELECT * FROM jobs WHERE scope=? AND state='queued'
                AND kind IN ({','.join('?' * len(kinds))}) ORDER BY created,id LIMIT 64""", (p['scope'], *kinds)).fetchall()
            now = self.store.now()
            for row in rows:
                inputs, reason = self._dispatch_inputs(db, row)
                if reason:
                    self._settle(db, row, 'failed', reason)
                    self._event(db, row['id'], 'dispatch_denied', {'worker': worker['id'], 'reason': reason})
                    continue
                token, attempt = secrets.token_hex(16), row['attempt'] + 1
                db.execute("UPDATE jobs SET state='leased',attempt=?,lease_owner=?,lease_digest=?,lease_until=? WHERE id=?",
                           (attempt, worker['id'], _digest(token), now + ttl, row['id']))
                self._event(db, row['id'], 'leased', {'worker': worker['id'], 'attempt': attempt, 'lease_until': now + ttl})
                return {'job': row['id'], 'lease': token, 'lease_until': now + ttl, 'attempt': attempt,
                        'kind': row['kind'], 'parameters': json.loads(row['parameters']),
                        'side_effect_free': bool(row['side_effect_free']), 'inputs': inputs}
            return None

    def start(self, bearer, worker_id, job_id, lease, *, backend) -> dict:
        ident(backend)
        with self.store.transaction() as db:
            _, worker, row = self._leased(db, bearer, worker_id, job_id, lease)
            state = row['state']
            if state == 'leased':
                db.execute("UPDATE jobs SET state='running',started=? WHERE id=?", (self.store.now(), row['id']))
                self._event(db, row['id'], 'started', {'worker': worker['id'], 'backend': backend, 'attempt': row['attempt']})
                state = 'running'
            return {'state': state, 'cancel_requested': bool(row['cancel_requested'])}

    def heartbeat(self, bearer, worker_id, job_id, lease, *, ttl=30) -> dict:
        """Extend the lease. The answer says whether the owner asked to cancel."""
        _bounded_ttl(ttl)
        with self.store.transaction() as db:
            _, _, row = self._leased(db, bearer, worker_id, job_id, lease)
            until = self.store.now() + ttl
            db.execute('UPDATE jobs SET lease_until=? WHERE id=?', (until, row['id']))
            return {'state': row['state'], 'cancel_requested': bool(row['cancel_requested']), 'lease_until': until}

    def complete(self, bearer, worker_id, job_id, lease, *, sha256, data, media_type='application/json') -> dict:
        """Accept a result only if its bytes match the SHA-256 the worker claims."""
        if not isinstance(sha256, str) or not SHA256.fullmatch(sha256):
            raise Fault('invalid_sha256')
        if type(data) is not bytes:
            raise Fault('invalid_artefact')
        if len(data) > MAX_ARTEFACT_BYTES:
            raise Fault('artefact_too_large', 413)
        if media_type not in MEDIA_TYPES:
            raise Fault('invalid_media_type')
        actual, rejected = hashlib.sha256(data).hexdigest(), False
        with self.store.transaction() as db:
            _, worker, row = self._leased(db, bearer, worker_id, job_id, lease)
            if not secrets.compare_digest(actual, sha256):
                # Record the rejected claim durably, then refuse it after commit.
                self._event(db, row['id'], 'result_rejected', {'worker': worker['id'], 'claimed_sha256': sha256,
                                                               'actual_sha256': actual, 'size': len(data),
                                                               'reason': 'artefact_hash_mismatch'})
                rejected = True
            else:
                if media_type == 'application/json':
                    try:
                        json.loads(data.decode('utf-8'))
                    except (UnicodeError, ValueError, RecursionError):
                        raise Fault('result_not_json') from None
                lineage = self._lineage(row)
                existing = db.execute('SELECT lineage FROM artefacts WHERE scope=? AND sha256=?', (row['scope'], actual)).fetchone()
                if existing:
                    # Identical bytes from another job: reading needs every source of every producer (fail closed).
                    merged = json.loads(existing['lineage'])
                    merged['sources'] = sorted(set(merged['sources']) | set(lineage['sources']))
                    notes = {(n['id'], n['revision']): n for n in merged.get('notes', []) + lineage['notes']}
                    merged['notes'] = [notes[k] for k in sorted(notes)]
                    merged['artefacts'] = sorted(set(merged.get('artefacts', [])) | set(lineage['artefacts']))
                    db.execute('UPDATE artefacts SET lineage=? WHERE scope=? AND sha256=?', (json.dumps(merged, sort_keys=True), row['scope'], actual))
                else:
                    count, total = db.execute('SELECT count(*),coalesce(sum(size),0) FROM artefacts WHERE scope=?', (row['scope'],)).fetchone()
                    if count >= MAX_JOBS or total + len(data) > MAX_SCOPE_ARTEFACT_BYTES:
                        raise Fault('artefact_capacity', 409)
                    db.execute('INSERT INTO artefacts VALUES (?,?,?,?,?,?,?,?)',
                               (row['scope'], actual, len(data), media_type, row['id'], self.store.now(),
                                json.dumps(lineage, sort_keys=True), sqlite3.Binary(data)))
                self._settle(db, row, 'succeeded', None)
                db.execute('UPDATE jobs SET result_artefact=? WHERE id=?', (actual, row['id']))
                if row['cancel_requested']:
                    self._event(db, row['id'], 'completed_after_cancel_request', {'worker': worker['id']})
                self._event(db, row['id'], 'succeeded', {'worker': worker['id'], 'sha256': actual, 'size': len(data),
                                                         'media_type': media_type, 'verified': 'sha256_of_bytes_only'})
                view = self._view(db, self._job(db, row['scope'], row['id']))
        if rejected:
            raise Fault('artefact_hash_mismatch', 409)
        self._mirror(data)
        return view

    def fail(self, bearer, worker_id, job_id, lease, reason, *, retryable=False) -> dict:
        """Report a non-success. Jobs with possible effects become effect_unknown, never retried."""
        if not isinstance(reason, str) or not REASON.fullmatch(reason):
            raise Fault('invalid_reason')
        if type(retryable) is not bool:
            raise Fault('invalid_retryable')
        with self.store.transaction() as db:
            _, worker, row = self._leased(db, bearer, worker_id, job_id, lease)
            if not row['side_effect_free']:
                state = 'effect_unknown'
            elif row['state'] == 'cancel_requested':
                state = 'cancelled'
            elif retryable and row['attempt'] < row['max_attempts']:
                state = 'queued'
            else:
                state = 'failed'
            self._settle(db, row, state, reason)
            self._event(db, row['id'], 'retry_scheduled' if state == 'queued' else state,
                        {'worker': worker['id'], 'reason': reason, 'attempt': row['attempt'], 'retryable': retryable})
            return self._view(db, self._job(db, row['scope'], row['id']))


# Backends -------------------------------------------------------------------

@dataclass(frozen=True)
class BackendResult:
    ok: bool
    output: bytes | None
    reason: str | None
    exit_code: int | None
    diagnostics: str = ''


class WorkerBackend(abc.ABC):
    """A replaceable execution environment for one leased job at a time per handle.

    A backend runs work and reports bytes. It holds no job authority: leases,
    retries, cancellation records, input policy and result verification stay
    in ``JobCoordinator``. A later remote or isolated backend (RUN-002/RUN-003)
    implements the same four calls.
    """
    name = 'abstract'

    @abc.abstractmethod
    def submit(self, handle: str, kind: str, parameters: dict, inputs: list) -> None:
        """Start running ``kind`` over ``inputs`` (dicts with ``name`` and ``data`` bytes)."""

    @abc.abstractmethod
    def status(self, handle: str) -> str:
        """'running' or 'finished'."""

    @abc.abstractmethod
    def cancel(self, handle: str) -> None:
        """Hard stop. Safe to call more than once or after the work finished."""

    @abc.abstractmethod
    def collect(self, handle: str, timeout: float | None = None) -> BackendResult:
        """Wait for the work to end, release its resources and return the outcome."""


class _Run:
    def __init__(self, process, workdir):
        self.process, self.workdir = process, workdir
        self.chunks, self.total, self.stderr = [], 0, b''
        self.reason, self.lock, self.threads, self.timer = None, threading.Lock(), [], None

    def stop(self, reason):
        with self.lock:
            if self.reason is None and self.process.poll() is None:
                self.reason = reason
            _kill(self.process)


def _kill(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)  # The child leads its own session and group.
    except (AttributeError, ProcessLookupError, PermissionError):
        try:
            process.kill()
        except ProcessLookupError:
            pass


class LocalSubprocessBackend(WorkerBackend):
    """Runs one allowlisted first-party job kind in a separate local OS process.

    Honest scope: a local subprocess on the same host, user account and kernel as
    ALFRED. It is not VM isolation, not a remote worker and not a sandbox. The
    program is always ``alfred/job_kinds.py`` under the current interpreter in
    isolated mode; there is no shell and no arbitrary command. The process gets
    an empty environment, a fresh empty working directory, its own session,
    only the declared input bytes on standard input, a wall-clock limit, an
    output size limit, POSIX CPU and memory limits and an audit-hook tripwire.
    It gets no database path and no credential. Nothing here blocks a modified
    kind from using the network; the first-party kinds simply do not.
    """
    name = 'local_subprocess'
    PROGRAM = Path(__file__).with_name('job_kinds.py')

    def __init__(self, *, wall_clock=30.0, output_limit=MAX_ARTEFACT_BYTES, memory_limit=1024 * 1024 * 1024):
        if type(wall_clock) not in (int, float) or not 0 < wall_clock <= MAX_LEASE_SECONDS:
            raise Fault('invalid_wall_clock_limit')
        if type(output_limit) is not int or not 1 <= output_limit <= MAX_ARTEFACT_BYTES:
            raise Fault('invalid_output_limit')
        if type(memory_limit) is not int or memory_limit < 64 * 1024 * 1024:
            raise Fault('invalid_memory_limit')
        self.wall_clock, self.output_limit, self.memory_limit = float(wall_clock), output_limit, memory_limit
        self._runs, self._lock = {}, threading.Lock()

    def _run(self, handle) -> _Run:
        with self._lock:
            run = self._runs.get(handle)
        if run is None:
            raise Fault('unknown_backend_handle', 404)
        return run

    def process_id(self, handle) -> int | None:
        """The OS process ID while the handle is held, for inspection and tests."""
        with self._lock:
            run = self._runs.get(handle)
        return run.process.pid if run else None

    def submit(self, handle, kind, parameters, inputs) -> None:
        ident(handle)
        if kind not in job_kinds.KINDS:
            raise Fault('unknown_job_kind')
        payload = json.dumps({'kind': kind, 'parameters': parameters,
                              'inputs': [{'name': item['name'], 'data': base64.b64encode(item['data']).decode('ascii')}
                                         for item in inputs]}).encode('ascii')
        if len(payload) > job_kinds.MAX_REQUEST_BYTES:
            raise Fault('request_too_large', 413)
        command = [sys.executable, '-I', '-S', '-B', str(self.PROGRAM),
                   '--cpu-seconds', str(math.ceil(self.wall_clock) + 1), '--memory-bytes', str(self.memory_limit)]
        with self._lock:
            if handle in self._runs:
                raise Fault('backend_handle_exists', 409)
            workdir = tempfile.mkdtemp(prefix='alfred-job-')
            try:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, cwd=workdir, env={}, close_fds=True,
                                           start_new_session=True, shell=False)
            except OSError:
                shutil.rmtree(workdir, ignore_errors=True)
                raise Fault('backend_start_failed', 500) from None
            run = self._runs[handle] = _Run(process, workdir)
        run.threads = [threading.Thread(target=target, args=args, daemon=True) for target, args in (
            (self._write, (run, payload)), (self._read_output, (run,)), (self._read_errors, (run,)))]
        for thread in run.threads:
            thread.start()
        run.timer = threading.Timer(self.wall_clock, run.stop, args=('wall_clock_limit',))
        run.timer.daemon = True
        run.timer.start()

    @staticmethod
    def _write(run, payload):
        try:
            run.process.stdin.write(payload)
        except (BrokenPipeError, OSError, ValueError):
            pass
        finally:
            try:
                run.process.stdin.close()
            except (BrokenPipeError, OSError):
                pass

    def _read_output(self, run):
        try:
            while True:
                chunk = run.process.stdout.read1(65536)
                if not chunk:
                    break
                run.total += len(chunk)
                if run.total > self.output_limit:
                    run.stop('output_too_large')
                    break
                run.chunks.append(chunk)
        except (OSError, ValueError):
            pass
        finally:
            run.process.stdout.close()

    @staticmethod
    def _read_errors(run):
        try:
            while True:
                chunk = run.process.stderr.read1(4096)
                if not chunk:
                    break
                run.stderr = (run.stderr + chunk)[:2048]
        except (OSError, ValueError):
            pass
        finally:
            run.process.stderr.close()

    def status(self, handle) -> str:
        return 'running' if self._run(handle).process.poll() is None else 'finished'

    def cancel(self, handle) -> None:
        self._run(handle).stop('cancelled')

    def collect(self, handle, timeout=None) -> BackendResult:
        run = self._run(handle)
        try:
            run.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise Fault('backend_still_running', 409) from None
        for thread in run.threads:
            thread.join(5)
        run.timer.cancel()
        with self._lock:
            self._runs.pop(handle, None)
        shutil.rmtree(run.workdir, ignore_errors=True)
        code, diagnostics = run.process.returncode, run.stderr.decode('utf-8', errors='replace')
        if run.reason:
            return BackendResult(False, None, run.reason, code, diagnostics)
        if code != 0:
            first = diagnostics.split('\n', 1)[0].strip()
            if code == job_kinds.EXIT_KIND_ERROR and REASON.fullmatch(first):
                reason = first
            else:
                reason = 'process_killed' if code < 0 else 'process_failed'
            return BackendResult(False, None, reason, code, diagnostics)
        return BackendResult(True, b''.join(run.chunks), None, 0, diagnostics)


class JobWorker:
    """Pull loop for one enrolled worker: lease, start, run on a backend, report.

    Runs in an ALFRED-owned process (for example a thread of the local host),
    never inside the job's process. It presents the enrolling owner's bearer to
    the coordinator; the job process receives no credential. The loop does not
    depend on the client that submitted a job, so a client may disconnect and
    reconnect later by reading the job's events from its last cursor.
    """

    def __init__(self, coordinator, backend, bearer, worker_id, *, lease_seconds=30,
                 heartbeat_seconds=None, poll_seconds=0.05):
        _bounded_ttl(lease_seconds)
        self.coordinator, self.backend, self.bearer, self.worker_id = coordinator, backend, bearer, ident(worker_id)
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds if heartbeat_seconds is not None else lease_seconds / 3
        self.poll_seconds = poll_seconds
        self.stopped_reason = None

    def _report(self, call, *args, **kwargs):
        try:
            return call(self.bearer, self.worker_id, *args, **kwargs)
        except Fault:
            return None  # Stale lease or lost authority: the coordinator's record stands.

    def run_once(self) -> str | None:
        """Process at most one job. Returns its ID, or None when nothing was leased."""
        grant = self.coordinator.lease(self.bearer, self.worker_id, ttl=self.lease_seconds)
        if grant is None:
            return None
        job, lease = grant['job'], grant['lease']
        started = self._report(self.coordinator.start, job, lease, backend=self.backend.name)
        if started is None:
            return job
        if started['cancel_requested']:
            self._report(self.coordinator.fail, job, lease, 'cancelled_before_start')
            return job
        handle = f"{job}.{grant['attempt']}"
        try:
            self.backend.submit(handle, grant['kind'], grant['parameters'], grant['inputs'])
        except Fault as exc:
            self._report(self.coordinator.fail, job, lease, exc.code if REASON.fullmatch(exc.code) else 'backend_error')
            return job
        beat = time.monotonic() + self.heartbeat_seconds
        try:
            while self.backend.status(handle) == 'running':
                time.sleep(self.poll_seconds)
                if time.monotonic() >= beat:
                    state = self.coordinator.heartbeat(self.bearer, self.worker_id, job, lease, ttl=self.lease_seconds)
                    if state['cancel_requested']:
                        self.backend.cancel(handle)
                    beat = time.monotonic() + self.heartbeat_seconds
        except Fault:
            # Lost the lease or the authority to hold it: stop the work and report nothing.
            self.backend.cancel(handle)
            self.backend.collect(handle)
            return job
        result = self.backend.collect(handle)
        if result.ok:
            self._report(self.coordinator.complete, job, lease, sha256=hashlib.sha256(result.output).hexdigest(),
                         data=result.output)
        else:
            self._report(self.coordinator.fail, job, lease, result.reason)
        return job

    def run(self, stop: threading.Event, *, idle_seconds=0.1) -> None:
        """Loop until ``stop`` is set or the worker loses its authority."""
        while not stop.is_set():
            try:
                job = self.run_once()
            except Fault as exc:
                if exc.status in (401, 403, 404):
                    self.stopped_reason = exc.code
                    return
                job = None
            if job is None:
                stop.wait(idle_seconds)


# Bounded content-addressed cache --------------------------------------------

CACHE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS cache_meta(version INTEGER NOT NULL, tick INTEGER NOT NULL, corrupt_removed INTEGER NOT NULL);
INSERT INTO cache_meta SELECT 1,0,0 WHERE NOT EXISTS(SELECT 1 FROM cache_meta);
CREATE TABLE IF NOT EXISTS entries(sha256 TEXT PRIMARY KEY, size INTEGER NOT NULL, used INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS pins(sha256 TEXT PRIMARY KEY);
'''


class BoundedCache:
    """Content-addressed local files with a hard byte limit and an explicit pin list.

    Files live under a private directory (mode 0700, files 0600) that must be
    outside this repository. The cache itself enforces the limit on stored
    content bytes: before writing it evicts least-recently-used unpinned
    entries, never pinned ones, and it refuses an item larger than the limit or
    one that cannot fit beside the pinned entries. Every read verifies the
    SHA-256; a corrupt entry is removed and reported. Pins express wanted
    offline availability and survive restarts; a pinned item that is missing
    is reported, not fetched. The index file and filesystem block overhead are
    outside the counted limit. A cache is never the authoritative copy.
    """

    def __init__(self, root, limit_bytes):
        if type(limit_bytes) is not int or limit_bytes < 1:
            raise Fault('invalid_cache_limit')
        root = Path(root).expanduser().absolute()
        if root.is_symlink():
            raise Fault('cache_symlink_rejected')
        if root.resolve().is_relative_to(REPOSITORY):
            raise Fault('cache_inside_repository')
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        for name in ('objects', 'incoming'):
            (root / name).mkdir(exist_ok=True, mode=0o700)
        self.root, self.limit = root, limit_bytes
        with self._connect() as db:
            db.executescript(CACHE_SCHEMA)
            if [r[0] for r in db.execute('SELECT version FROM cache_meta')] != [1]:
                raise Fault('unsupported_cache_version')
        (root / 'index.sqlite3').chmod(0o600)
        self._reconcile()

    def _connect(self):
        db = sqlite3.connect(self.root / 'index.sqlite3', timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=5000')
        return _Closing(db)

    @contextmanager
    def _transaction(self):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise

    def _path(self, sha256) -> Path:
        return self.root / 'objects' / sha256[:2] / sha256

    @staticmethod
    def _check(sha256):
        if not isinstance(sha256, str) or not SHA256.fullmatch(sha256):
            raise Fault('invalid_sha256')
        return sha256

    @staticmethod
    def _tick(db) -> int:
        db.execute('UPDATE cache_meta SET tick=tick+1')
        return db.execute('SELECT tick FROM cache_meta').fetchone()[0]

    def _drop(self, db, sha256):
        db.execute('DELETE FROM entries WHERE sha256=?', (sha256,))
        try:
            self._path(sha256).unlink()
        except FileNotFoundError:
            pass

    def _reconcile(self):
        """Heal after a crash: clear partial writes, drop missing entries and orphans, enforce the limit."""
        with self._transaction() as db:
            for leftover in (self.root / 'incoming').iterdir():
                leftover.unlink(missing_ok=True)
            known = {}
            for row in db.execute('SELECT sha256,size FROM entries').fetchall():
                path = self._path(row['sha256'])
                if not path.is_file() or path.is_symlink() or path.stat().st_size != row['size']:
                    self._drop(db, row['sha256'])
                else:
                    known[row['sha256']] = row['size']
            for folder in (self.root / 'objects').iterdir():
                for item in folder.iterdir() if folder.is_dir() else ():
                    if item.name not in known:
                        item.unlink(missing_ok=True)
            pinned = db.execute('SELECT coalesce(sum(e.size),0) FROM entries e JOIN pins p USING(sha256)').fetchone()[0]
            if pinned > self.limit:
                raise Fault('cache_pins_exceed_limit', 409)
            for sha256 in self._eviction_plan(db, 0):
                self._drop(db, sha256)

    def _eviction_plan(self, db, incoming) -> list:
        used = db.execute('SELECT coalesce(sum(size),0) FROM entries').fetchone()[0]
        plan = []
        if used + incoming <= self.limit:
            return plan
        for row in db.execute('''SELECT e.sha256,e.size FROM entries e LEFT JOIN pins p USING(sha256)
                WHERE p.sha256 IS NULL ORDER BY e.used,e.sha256''').fetchall():
            plan.append(row['sha256'])
            used -= row['size']
            if used + incoming <= self.limit:
                return plan
        raise Fault('cache_full_of_pinned_entries', 507)

    def put(self, data, *, pin=False) -> str:
        """Store bytes, evicting LRU unpinned entries first. Returns the SHA-256."""
        if type(data) is not bytes or type(pin) is not bool:
            raise Fault('invalid_cache_item')
        if len(data) > self.limit:
            raise Fault('cache_item_too_large', 413)
        sha256 = hashlib.sha256(data).hexdigest()
        path = self._path(sha256)
        with self._transaction() as db:
            if pin:
                db.execute('INSERT OR IGNORE INTO pins VALUES (?)', (sha256,))
            row = db.execute('SELECT size FROM entries WHERE sha256=?', (sha256,)).fetchone()
            if row and path.is_file() and not path.is_symlink():
                db.execute('UPDATE entries SET used=? WHERE sha256=?', (self._tick(db), sha256))
                return sha256
            if row:
                self._drop(db, sha256)
            if pin:
                pinned = db.execute('SELECT coalesce(sum(e.size),0) FROM entries e JOIN pins p USING(sha256)').fetchone()[0]
                if pinned + len(data) > self.limit:
                    raise Fault('cache_full_of_pinned_entries', 507)
            for victim in self._eviction_plan(db, len(data)):
                self._drop(db, victim)
            incoming = self.root / 'incoming' / (sha256 + '.' + secrets.token_hex(4))
            try:
                descriptor = os.open(incoming, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
                with os.fdopen(descriptor, 'wb') as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                path.parent.mkdir(exist_ok=True, mode=0o700)
                os.replace(incoming, path)
            except OSError:
                incoming.unlink(missing_ok=True)
                # Keep the evictions already applied on disk consistent with the index.
                db.execute('COMMIT')
                db.execute('BEGIN IMMEDIATE')
                raise Fault('cache_write_failed', 507) from None
            db.execute('INSERT INTO entries VALUES (?,?,?)', (sha256, len(data), self._tick(db)))
        return sha256

    def get(self, sha256) -> bytes | None:
        """Verified bytes, or None if absent. A corrupt entry is removed and raises."""
        self._check(sha256)
        corrupt = False
        with self._transaction() as db:
            row = db.execute('SELECT size FROM entries WHERE sha256=?', (sha256,)).fetchone()
            if not row:
                return None
            try:
                descriptor = os.open(self._path(sha256), os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
                with os.fdopen(descriptor, 'rb') as handle:
                    data = handle.read(row['size'] + 1)
            except OSError:
                self._drop(db, sha256)
                return None
            if len(data) != row['size'] or hashlib.sha256(data).hexdigest() != sha256:
                self._drop(db, sha256)
                db.execute('UPDATE cache_meta SET corrupt_removed=corrupt_removed+1')
                corrupt = True
            else:
                db.execute('UPDATE entries SET used=? WHERE sha256=?', (self._tick(db), sha256))
        if corrupt:
            raise Fault('cache_entry_corrupt', 409)
        return data

    def contains(self, sha256) -> bool:
        self._check(sha256)
        with self._connect() as db:
            return bool(db.execute('SELECT 1 FROM entries WHERE sha256=?', (sha256,)).fetchone())

    def pin(self, sha256) -> None:
        """Add to the explicit offline pin list. Pinning a missing item records the wish."""
        self._check(sha256)
        with self._transaction() as db:
            size = db.execute('SELECT size FROM entries WHERE sha256=?', (sha256,)).fetchone()
            pinned = db.execute('SELECT coalesce(sum(e.size),0) FROM entries e JOIN pins p USING(sha256) WHERE e.sha256!=?', (sha256,)).fetchone()[0]
            if size and pinned + size['size'] > self.limit:
                raise Fault('cache_full_of_pinned_entries', 507)
            db.execute('INSERT OR IGNORE INTO pins VALUES (?)', (sha256,))

    def unpin(self, sha256) -> None:
        self._check(sha256)
        with self._transaction() as db:
            db.execute('DELETE FROM pins WHERE sha256=?', (sha256,))

    def pins(self) -> list:
        with self._connect() as db:
            return [r[0] for r in db.execute('SELECT sha256 FROM pins ORDER BY sha256')]

    def usage(self) -> dict:
        with self._connect() as db:
            used, entries = db.execute('SELECT coalesce(sum(size),0),count(*) FROM entries').fetchone()
            pinned_bytes, pinned_entries = db.execute('SELECT coalesce(sum(e.size),0),count(*) FROM entries e JOIN pins p USING(sha256)').fetchone()
            missing = [r[0] for r in db.execute('SELECT p.sha256 FROM pins p LEFT JOIN entries e USING(sha256) WHERE e.sha256 IS NULL ORDER BY p.sha256')]
            corrupt = db.execute('SELECT corrupt_removed FROM cache_meta').fetchone()[0]
        return {'limit_bytes': self.limit, 'used_bytes': used, 'free_bytes': self.limit - used,
                'entries': entries, 'pinned_entries': pinned_entries, 'pinned_bytes': pinned_bytes,
                'pinned_missing': missing, 'corrupt_removed': corrupt,
                'counts': 'stored content bytes; the index file and filesystem overhead are extra'}


class _Closing:
    """Close a sqlite3 connection on exit (its own context manager only commits)."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        self.db.close()
        return False
