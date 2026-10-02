"""Honest voice output records (VOI-001, playback only). No microphone, ever, in this module.

Speech is produced by the person's own browser with an on-device voice; this module never
receives audio or the spoken text, only a hash and length of what the console assembled.
It keeps four things apart:

- generated: the console assembled exactly this text for one answer;
- played: the browser reported that playback ended, was stopped or failed (a device
  report, not proof that anyone heard it);
- acknowledged: the person said they heard it, by an explicit action.

A network voice is refused: text sent to an online speech service would leave the
machine, so the console only uses voices the browser marks as local, and says so.
"""
from __future__ import annotations
import re
import secrets
from .local import Fault, exact, ident

SCHEMA = '''
CREATE TABLE IF NOT EXISTS voice_playbacks(
 id TEXT PRIMARY KEY, scope TEXT NOT NULL, actor TEXT NOT NULL, turn_id TEXT NOT NULL,
 text_sha256 TEXT NOT NULL, characters INTEGER NOT NULL, created INTEGER NOT NULL,
 outcome TEXT, reported INTEGER, acknowledged INTEGER);
CREATE INDEX IF NOT EXISTS voice_playbacks_turn ON voice_playbacks(scope,actor,turn_id);
'''
OUTCOMES = ('ended', 'stopped', 'error')
MAX_CHARACTERS = 4000


def _view(row):
    state = 'acknowledged' if row['acknowledged'] else {'ended': 'played', 'stopped': 'stopped', 'error': 'failed'}.get(row['outcome'], 'generated')
    return {'id': row['id'], 'turn_id': row['turn_id'], 'text_sha256': row['text_sha256'], 'characters': row['characters'],
            'state': state, 'generated_at': row['created'], 'outcome': row['outcome'], 'reported_at': row['reported'],
            'acknowledged_at': row['acknowledged'],
            'basis': {'played': 'browser_report_not_proof_of_hearing', 'acknowledged': 'explicit_human_action'}}


class VoiceLog:
    def __init__(self, store):
        self.store = store
        with store.connection() as db:
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')

    def _turn(self, db, p, turn_id):
        ident(turn_id)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversation_turns'").fetchone():
            raise Fault('not_found', 404)
        row = db.execute('''SELECT t.id FROM conversation_turns t JOIN conversations s ON s.id=t.session
                            WHERE t.id=? AND s.scope=? AND s.actor=? AND t.result IS NOT NULL''', (turn_id, p['scope'], p['id'])).fetchone()
        if not row:
            raise Fault('not_found', 404)  # Unknown, withdrawn and other people's answers look alike.

    def generated(self, bearer, body):
        exact(body, {'turn_id', 'text_sha256', 'characters', 'voice_local'})
        if body['voice_local'] is not True:
            raise Fault('network_voice_refused', 403)
        if not isinstance(body['text_sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', body['text_sha256']):
            raise Fault('invalid_text_hash')
        if type(body['characters']) is not int or not 1 <= body['characters'] <= MAX_CHARACTERS:
            raise Fault('invalid_characters')
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            self._turn(db, p, body['turn_id'])
            if db.execute('SELECT count(*) FROM voice_playbacks WHERE scope=? AND actor=?', (p['scope'], p['id'])).fetchone()[0] >= 500:
                db.execute('DELETE FROM voice_playbacks WHERE id IN (SELECT id FROM voice_playbacks WHERE scope=? AND actor=? ORDER BY created,rowid LIMIT 100)',
                           (p['scope'], p['id']))
            identity = 'voice-' + secrets.token_hex(10)
            db.execute('INSERT INTO voice_playbacks VALUES (?,?,?,?,?,?,?,NULL,NULL,NULL)',
                       (identity, p['scope'], p['id'], body['turn_id'], body['text_sha256'], body['characters'], self.store.now()))
            self.store.log(db, p['scope'], p['id'], 'voice.generated', identity)
            return _view(db.execute('SELECT * FROM voice_playbacks WHERE id=?', (identity,)).fetchone())

    def _own(self, db, bearer, identity):
        if not isinstance(identity, str) or not re.fullmatch(r'voice-[0-9a-f]{20}', identity):
            raise Fault('not_found', 404)
        p = self.store.authenticate(db, bearer, {'owner', 'reader'})
        row = db.execute('SELECT * FROM voice_playbacks WHERE id=? AND scope=? AND actor=?', (identity, p['scope'], p['id'])).fetchone()
        if not row:
            raise Fault('not_found', 404)
        return p, row

    def report(self, bearer, identity, body):
        """The browser's own report of how playback finished. Recorded once."""
        exact(body, {'outcome'})
        if body['outcome'] not in OUTCOMES:
            raise Fault('invalid_outcome')
        with self.store.transaction() as db:
            p, row = self._own(db, bearer, identity)
            if row['outcome'] is not None:
                raise Fault('playback_already_reported', 409)
            db.execute('UPDATE voice_playbacks SET outcome=?,reported=? WHERE id=?', (body['outcome'], self.store.now(), identity))
            self.store.log(db, p['scope'], p['id'], 'voice.' + body['outcome'], identity)
            return _view(db.execute('SELECT * FROM voice_playbacks WHERE id=?', (identity,)).fetchone())

    def acknowledge(self, bearer, identity, body):
        """The person says they heard it. Only after the browser reported that playback ended."""
        exact(body, set())
        with self.store.transaction() as db:
            p, row = self._own(db, bearer, identity)
            if row['outcome'] != 'ended':
                raise Fault('playback_not_finished', 409)
            if row['acknowledged'] is None:
                db.execute('UPDATE voice_playbacks SET acknowledged=? WHERE id=?', (self.store.now(), identity))
                self.store.log(db, p['scope'], p['id'], 'voice.acknowledged', identity)
            return _view(db.execute('SELECT * FROM voice_playbacks WHERE id=?', (identity,)).fetchone())

    def history(self, bearer, turn_id):
        with self.store.transaction() as db:
            p = self.store.authenticate(db, bearer, {'owner', 'reader'})
            ident(turn_id)
            return {'playbacks': [_view(r) for r in db.execute(
                'SELECT * FROM voice_playbacks WHERE scope=? AND actor=? AND turn_id=? ORDER BY created DESC,rowid DESC LIMIT 20',
                (p['scope'], p['id'], turn_id))], 'microphone': 'never_requested'}
