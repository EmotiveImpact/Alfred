"""Additive v0.3 desk state over the unchanged v0.2 local core.

One desktop process per database. Synthetic, locally selected project documents
only. No network connector, model or delivery capability is enabled.
"""
from __future__ import annotations
import hashlib
import json
import secrets
from pathlib import Path
import time
from .local import LocalCore, Fault, SCHEMA, canonical, exact, fingerprint, ident, text, timestamp

DESK_SCHEMA = '''
CREATE TABLE IF NOT EXISTS desk_meta(version INTEGER NOT NULL);
INSERT INTO desk_meta SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM desk_meta);
CREATE TABLE IF NOT EXISTS desk_settings(scope TEXT PRIMARY KEY, paused INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS desk_documents(
 scope TEXT NOT NULL, source TEXT NOT NULL, document_id TEXT NOT NULL,
 filename TEXT NOT NULL, title TEXT NOT NULL, revision INTEGER NOT NULL,
 sha256 TEXT NOT NULL, event_id TEXT NOT NULL, status TEXT NOT NULL, checked INTEGER NOT NULL,
 PRIMARY KEY(scope,source,document_id), UNIQUE(scope,source,filename));
CREATE TABLE IF NOT EXISTS desk_links(
 seq INTEGER PRIMARY KEY REFERENCES events(seq), filename TEXT NOT NULL,
 title TEXT NOT NULL, revision INTEGER NOT NULL, sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS desk_action_evidence(
 scope TEXT NOT NULL, action_id TEXT NOT NULL, event_seq INTEGER NOT NULL REFERENCES events(seq),
 event_fingerprint TEXT NOT NULL,
 PRIMARY KEY(scope,action_id), FOREIGN KEY(scope,action_id) REFERENCES actions(scope,id));
CREATE TABLE IF NOT EXISTS desk_ack(
 scope TEXT NOT NULL, actor TEXT NOT NULL, event_seq INTEGER NOT NULL REFERENCES events(seq),
 at INTEGER NOT NULL, PRIMARY KEY(scope,actor,event_seq));
'''


class DeskStore(LocalCore):
    def __init__(self, path, clock=time.time):
        self.path, self.clock = Path(path).expanduser(), clock
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise Fault('database_symlink_rejected')
        with self.connection() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 2, 3):
                raise Fault('unsupported_database_version')
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + DESK_SCHEMA + '\nPRAGMA user_version=3; COMMIT;')
            if db.execute('SELECT version FROM desk_meta').fetchall()[0][0] != 1:
                raise Fault('unsupported_desk_version')
        self.path.chmod(0o600)

    def principal(self, bearer, roles=frozenset({'owner', 'reader'})):
        with self.connection() as db:
            return dict(self.authenticate(db, bearer, set(roles)))

    def paused(self, scope):
        with self.connection() as db:
            row = db.execute('SELECT paused FROM desk_settings WHERE scope=?', (scope,)).fetchone()
            return bool(row and row[0])

    def set_paused(self, bearer, paused):
        if type(paused) is not bool:
            raise Fault('invalid_pause')
        with self.transaction() as db:
            p = self.authenticate(db, bearer, {'owner'})
            db.execute('INSERT INTO desk_settings VALUES (?,?) ON CONFLICT(scope) DO UPDATE SET paused=excluded.paused', (p['scope'], int(paused)))
            self.log(db, p['scope'], p['id'], 'desk.paused' if paused else 'desk.resumed', p['scope'])
        return {'paused': paused, 'does_not_undo_completed_work': True}

    def document(self, source_bearer, filename, data, raw_sha):
        """Ingest a bounded file snapshot; original bytes remain outside the database.

        Event-first and metadata-second is crash-recoverable: the deterministic
        event ID makes an interrupted metadata commit safe to retry next scan.
        """
        exact(data, {'document_id', 'title', 'revision', 'observed_at', 'expires_at', 'summary'})
        ident(data['document_id']); text(data['title'], 120); text(data['summary'], 1800)
        if type(data['revision']) is not int or not 1 <= data['revision'] <= 1000000:
            raise Fault('invalid_revision')
        p = self.principal(source_bearer, {'source'})
        scope, source = p['scope'], p['id']
        with self.connection() as db:
            prior = db.execute('SELECT * FROM desk_documents WHERE scope=? AND source=? AND document_id=?', (scope, source, data['document_id'])).fetchone()
            other = db.execute('SELECT document_id FROM desk_documents WHERE scope=? AND source=? AND filename=?', (scope, source, filename)).fetchone()
        if other and other[0] != data['document_id']:
            raise Fault('document_identity_changed', 409)
        if prior:
            if prior['filename'] != filename:
                raise Fault('document_id_at_another_path', 409)
            if data['revision'] < prior['revision']:
                raise Fault('revision_rollback', 409)
            if data['revision'] == prior['revision']:
                if raw_sha != prior['sha256']:
                    raise Fault('revision_content_conflict', 409)
                self.document_status(scope, source, filename, 'ready')
                return {'state': 'unchanged', 'event_id': prior['event_id']}
        event_id = 'doc-' + hashlib.sha256(f"{data['document_id']}:{data['revision']}".encode()).hexdigest()
        result = self.ingest(source_bearer, {
            'id': event_id, 'subject': data['document_id'], 'kind': 'briefing.changed',
            'basis': 'reported', 'observed_at': data['observed_at'],
            'expires_at': data['expires_at'], 'summary': data['summary'],
        })
        if result['reason'] in {'out_of_order', 'needs_reconciliation'}:
            raise Fault('revision_time_needs_review', 409)
        with self.transaction() as db:
            self.authenticate(db, source_bearer, {'source'})
            stored = db.execute('SELECT seq,reason FROM events WHERE scope=? AND source=? AND event_id=?', (scope, source, event_id)).fetchone()
            if stored['reason'] in {'out_of_order', 'needs_reconciliation'}:
                raise Fault('revision_time_needs_review', 409)
            seq = stored['seq']
            db.execute('INSERT OR IGNORE INTO desk_links VALUES (?,?,?,?,?)', (seq, filename, data['title'], data['revision'], raw_sha))
            db.execute('INSERT INTO desk_documents VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(scope,source,document_id) DO UPDATE SET title=excluded.title,revision=excluded.revision,sha256=excluded.sha256,event_id=excluded.event_id,status=excluded.status,checked=excluded.checked',
                       (scope, source, data['document_id'], filename, data['title'], data['revision'], raw_sha, event_id, 'ready', self.now()))
        return {'state': 'imported', 'event_id': event_id}

    def document_status(self, scope, source, filename, status):
        if status not in {'ready', 'missing', 'error'}:
            raise Fault('invalid_document_status')
        with self.transaction() as db:
            db.execute('UPDATE desk_documents SET status=?,checked=? WHERE scope=? AND source=? AND filename=?', (status, self.now(), scope, source, filename))

    def missing_documents(self, scope, source, seen):
        with self.connection() as db:
            names = [r[0] for r in db.execute('SELECT filename FROM desk_documents WHERE scope=? AND source=?', (scope, source))]
        for filename in names:
            if filename not in seen:
                self.document_status(scope, source, filename, 'missing')

    def source_failed(self, scope, source):
        with self.transaction() as db:
            db.execute('UPDATE desk_documents SET status=?,checked=? WHERE scope=? AND source=?', ('error', self.now(), scope, source))

    def _evidence(self, db, scope, seq):
        if type(seq) is not int or seq < 1:
            raise Fault('invalid_evidence_id')
        row = db.execute('SELECT e.*,l.filename,l.title,l.revision,l.sha256 FROM events e LEFT JOIN desk_links l ON l.seq=e.seq WHERE e.scope=? AND e.seq=?', (scope, seq)).fetchone()
        if not row:
            raise Fault('not_found', 404)
        doc = db.execute('SELECT event_id,status FROM desk_documents WHERE scope=? AND source=? AND document_id=?', (scope, row['source'], row['subject'])).fetchone()
        source = db.execute('SELECT revoked,expires FROM credentials WHERE id=?', (row['source'],)).fetchone()
        active = bool(doc and doc['event_id'] == row['event_id'] and doc['status'] == 'ready' and source and not source['revoked'] and source['expires'] > self.now())
        status = 'current' if active else ('superseded' if doc and doc['event_id'] != row['event_id'] else 'source_unavailable')
        if row['expires'] <= self.now():
            status = 'expired'
        if row['reason'] in {'needs_reconciliation', 'out_of_order'}:
            status = 'needs_review'
        return row, status

    def evidence_view(self, db, scope, seq, actor):
        row, status = self._evidence(db, scope, seq)
        return {**json.loads(row['body']), 'seq': row['seq'], 'source': row['source'],
                'received_at': row['received'], 'route': row['route'], 'reason': row['reason'],
                'fingerprint': row['fingerprint'], 'status': status,
                'filename': row['filename'], 'title': row['title'] or row['subject'],
                'revision': row['revision'], 'source_sha256': row['sha256'],
                'acknowledged': bool(db.execute('SELECT 1 FROM desk_ack WHERE scope=? AND actor=? AND event_seq=?', (scope, actor, seq)).fetchone())}

    def evidence(self, bearer, seq):
        with self.connection() as db:
            p = self.authenticate(db, bearer, {'owner', 'reader'})
            return self.evidence_view(db, p['scope'], seq, p['id'])

    def acknowledge(self, bearer, seq):
        with self.transaction() as db:
            p = self.authenticate(db, bearer, {'owner', 'reader'})
            self._evidence(db, p['scope'], seq)
            changed = db.execute('INSERT OR IGNORE INTO desk_ack VALUES (?,?,?,?)', (p['scope'], p['id'], seq, self.now())).rowcount
            if changed:
                self.log(db, p['scope'], p['id'], 'evidence.acknowledged', str(seq))
        return {'acknowledged': True}

    def propose_from_evidence(self, bearer, value):
        exact(value, {'event_seq', 'text', 'request_id'})
        text(value['text']); ident(value['request_id'])
        with self.transaction() as db:
            p = self.authenticate(db, bearer, {'owner'})
            event, status = self._evidence(db, p['scope'], value['event_seq'])
            if status != 'current':
                raise Fault('evidence_not_current', 409)
            action_id = value['request_id']
            existing = db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (p['scope'], action_id)).fetchone()
            link = db.execute('SELECT * FROM desk_action_evidence WHERE scope=? AND action_id=?', (p['scope'], action_id)).fetchone()
            if existing:
                if existing['actor'] != p['id'] or not link or link['event_seq'] != value['event_seq'] or json.loads(existing['parameters']) != {'text': value['text']}:
                    raise Fault('action_id_collision', 409)
                return self.action_view(existing)
            if db.execute('SELECT count(*) FROM actions WHERE scope=?', (p['scope'],)).fetchone()[0] >= 5000:
                raise Fault('action_capacity', 409)
            expiry = min(self.now() + 900, event['expires'])
            bound = {'id': action_id, 'scope': p['scope'], 'actor': p['id'], 'capability': 'message.draft',
                     'parameters': {'text': value['text']}, 'expires_at': expiry,
                     'evidence': {'seq': event['seq'], 'fingerprint': event['fingerprint']}}
            db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,?,?,?,?)', (p['scope'], action_id, p['id'], 'message.draft', canonical(bound['parameters']), fingerprint(bound), expiry, 'proposed', self.now(), None))
            db.execute('INSERT INTO desk_action_evidence VALUES (?,?,?,?)', (p['scope'], action_id, event['seq'], event['fingerprint']))
            self.log(db, p['scope'], p['id'], 'action.proposed_from_evidence', action_id)
            return self.action_view(db.execute('SELECT * FROM actions WHERE scope=? AND id=?', (p['scope'], action_id)).fetchone())

    def evidence_valid(self, db, row):
        link = db.execute('SELECT * FROM desk_action_evidence WHERE scope=? AND action_id=?', (row['scope'], row['id'])).fetchone()
        if not link:
            return False
        event, status = self._evidence(db, row['scope'], link['event_seq'])
        return status == 'current' and event['fingerprint'] == link['event_fingerprint']

    def valid_origin(self, db, row):
        paused = db.execute('SELECT paused FROM desk_settings WHERE scope=?', (row['scope'],)).fetchone()
        return super().valid_origin(db, row) and not (paused and paused[0]) and self.evidence_valid(db, row)

    def approve(self, bearer, action_id, digest):
        # Inline the small original approval transaction so evidence check and queue
        # insertion are atomic. The unchanged v0.2 API remains in LocalCore.
        with self.transaction() as db:
            p, row = self.owned_action(db, bearer, action_id)
            if type(digest) is not str or not secrets.compare_digest(row['fingerprint'], digest):
                raise Fault('approval_mismatch', 409)
            if row['expires'] <= self.now() or not self.evidence_valid(db, row):
                raise Fault('evidence_or_approval_expired', 409)
            if row['state'] == 'queued':
                return self.action_view(row)
            if row['state'] != 'proposed':
                raise Fault('invalid_state', 409)
            db.execute('UPDATE actions SET state=? WHERE scope=? AND id=?', ('queued', p['scope'], action_id))
            db.execute('INSERT INTO outbox(scope,action_id,state) VALUES (?,?,?)', (p['scope'], action_id, 'queued'))
            self.log(db, p['scope'], p['id'], 'action.approved', action_id)
            return {'id': action_id, 'state': 'queued', 'effect': 'local_draft_only_not_sent'}

    def tick(self, bearer, **kwargs):
        p = self.principal(bearer, {'owner'})
        if self.paused(p['scope']):
            return {'state': 'paused'}
        return super().tick(bearer, **kwargs)

    def desk_state(self, bearer, before=None, limit=30):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise Fault('invalid_limit')
        if before is not None and (type(before) is not int or before < 1):
            raise Fault('invalid_cursor')
        with self.transaction() as db:
            p = self.authenticate(db, bearer, {'owner', 'reader'})
            scope = p['scope']
            query = 'SELECT seq FROM events WHERE scope=?'
            args = [scope]
            if before is not None:
                query += ' AND seq<?'; args.append(before)
            rows = db.execute(query + ' ORDER BY seq DESC LIMIT ?', (*args, limit + 1)).fetchall()
            events = [self.evidence_view(db, scope, r[0], p['id']) for r in rows[:limit]]
            actions = []
            for r in db.execute('SELECT * FROM actions WHERE scope=? ORDER BY created DESC,id DESC LIMIT 100', (scope,)):
                link = db.execute('SELECT event_seq FROM desk_action_evidence WHERE scope=? AND action_id=?', (scope, r['id'])).fetchone()
                actions.append({**self.action_view(r), 'created_at': r['created'], 'event_seq': link[0] if link else None,
                                'evidence_current': self.evidence_valid(db, r), 'mine': r['actor'] == p['id']})
            documents = [dict(r) for r in db.execute('SELECT document_id,filename,title,revision,status,checked,source FROM desk_documents WHERE scope=? ORDER BY title', (scope,))]
            paused = db.execute('SELECT paused FROM desk_settings WHERE scope=?', (scope,)).fetchone()
            return {'version': '0.3.0-dev', 'scope': scope, 'role': p['role'], 'actor': p['id'],
                    'synthetic_workspace': bool(db.execute('SELECT simulation FROM workspaces WHERE id=?', (scope,)).fetchone()[0]),
                    'now': self.now(), 'paused': bool(paused and paused[0]), 'events': events, 'actions': actions,
                    'next_cursor': rows[limit - 1][0] if len(rows) > limit else None, 'documents': documents,
                    'counts': {name: db.execute('SELECT count(*) FROM ' + name + ' WHERE scope=?', (scope,)).fetchone()[0] for name in ('events', 'actions', 'drafts')},
                    'audit': [dict(r) for r in db.execute('SELECT seq,actor,kind,subject,at FROM audit WHERE scope=? ORDER BY seq DESC LIMIT 100', (scope,))],
                    'live_ai': False, 'microphone': False, 'external_effects': False,
                    'action_window_limit': 100, 'audit_window_limit': 100}
