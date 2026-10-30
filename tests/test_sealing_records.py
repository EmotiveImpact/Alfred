"""Sealing conversations, executive records, drafts and actions (encryption step 2, part 3).

Synthetic keys and an invented vault only. A sealed workspace keeps a conversation's title,
its questions and answers, an executive record's text, decision and progress trails, an
action's parameters and proof, a local draft and a draft's source binding sealed, and keeps
keyed fingerprints in place of plain SHA-256 hashes of that text. Everything here is made in
ALFRED rather than read from one note, so it is in the workspace's default area.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from alfred import drafts, inbox, lifecycle, sealing
from alfred.conversation import ConversationService
from alfred.executive import ExecutiveRecords
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.local import Fault, fingerprint
from alfred.voice import VoiceLog
from grant_helpers import grant_all
from test_sealing import keyring

# Words that appear only in this invented vault and these records, so finding one in a file means it leaked.
PRIVATE = ('Quillmarsh', 'Rowanhythe', 'Saltergate', 'Thistlemere', 'Umberleigh', 'Vexmoor', 'Wrenfold',
           'Yarrowby', 'Zeldacott', 'Brackenhow')
NOTE = 'Quillmarsh plan.md'
BODY = ('# Quillmarsh plan\n'
        'Quillmarsh meets Rowanhythe on Thursday.\n'
        'Saltergate budget waits on Thistlemere.\n')
QUESTION = 'When does Quillmarsh meet Rowanhythe?'
ANSWER = 'Synthetic reading: Vexmoor follows Quillmarsh.'
DRAFT = 'Please confirm Wrenfold with Yarrowby.'
SPOKEN = 'Rowanhythe answer read aloud'


class Model:
    """A stand-in for a local model: one cited interpretation, nothing else."""
    model = 'fixture-not-an-llm'

    def generate(self, packet):
        source = packet['evidence'][0]
        return {'answerable': True, 'claims': [{'text': ANSWER, 'citations': [
            {'source_id': source['source_id'], 'start_line': source['start_line'], 'end_line': source['end_line']}]}]}


class ClientStore(KnowledgeStore):
    """Every source in one client area, as a folder rule (part 5) would place it."""
    def source_area(self, db, scope, source):
        return 'client-a'


class SealedRecordsBase(unittest.TestCase):
    store_class = KnowledgeStore

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'db.sqlite'
        self.keyring = keyring(self.root, 'personal', 'client-a')
        sealing.attach(self.path, sealing.Sealed(self.keyring))
        self.addCleanup(sealing.detach, self.path)
        self.clock = [1_000_000]
        self.store = self.store_class(self.path, clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=2592000)
        self.source = self.store.provision('work', 'source', 'source', ttl=2592000)
        grant_all(self.store, self.owner, ('read', 'model', 'inbox.write'))
        self.actor = self.store.principal(self.owner, {'owner'})['id']
        vault = self.root / 'vault'
        vault.mkdir()
        (vault / NOTE).write_text(BODY, encoding='utf-8')
        MarkdownVault(self.store, self.source, vault).scan()
        # A conversation: one question answered from sources, one interpreted by the stand-in model.
        self.chat = ConversationService(self.store, Model(), 'work')
        self.addCleanup(self.chat.stop)
        self.sid = self.chat.create(self.owner, {'title': 'Umberleigh planning'})['id']
        self.asked = [self.ask(self.sid, 0, 'sources'), self.ask(self.sid, 1, 'local_model')]
        self.turns = [t['id'] for t in self.chat.view(self.owner, self.sid)['turns']]
        self.drafted = self.chat.propose_draft(self.owner, self.sid, {'turn_id': self.turns[1], 'text': DRAFT, 'request_id': 'draft-1'})
        self.store.approve(self.owner, 'draft-1', self.drafted['fingerprint'])
        self.assertEqual(self.store.tick(self.owner)['state'], 'verified')
        # A second conversation whose draft outlives it: its source binding moves to the draft.
        other = self.chat.create(self.owner, {'title': 'Umberleigh follow-up'})['id']
        self.ask(other, 0, 'sources')
        turn = self.chat.view(self.owner, other)['turns'][0]['id']
        self.chat.propose_draft(self.owner, other, {'turn_id': turn, 'text': 'Ask Brackenhow about Saltergate.', 'request_id': 'draft-2'})
        self.chat.forget(self.owner, other)
        # An action proposed directly, and a note for the vault's inbox, carried out.
        self.direct = {'id': 'local-1', 'capability': 'message.draft', 'parameters': {'text': 'Zeldacott reminder'},
                       'expires_at': self.clock[0] + 600}
        self.store.propose(self.owner, self.direct)
        self.note_action = inbox.propose(self.store, self.owner, {'request_id': 'inbox-1', 'source': 'source',
                                                                  'filename': 'Umberleigh follow-up.md',
                                                                  'content': '# Umberleigh follow-up\nAsk Yarrowby.\n'})
        self.store.approve(self.owner, 'inbox-1', self.note_action['fingerprint'])
        self.assertEqual(self.store.tick(self.owner)['state'], 'verified')
        # Executive records: a decided decision with options, and a milestone with a progress note.
        self.records = ExecutiveRecords(self.store)
        self.record_bodies = []
        decision = self.record('d1', 'decision', 'Zeldacott pricing', detail='Brackenhow asked for a choice.',
                               responsible='Wrenfold', options=[{'label': 'Quillmarsh first'}, {'label': 'Saltergate first'}])
        option = decision['options'][0]['id']
        self.decision = self.records.decide(self.owner, decision['id'], {'version': decision['version'], 'option': option,
                                                                         'rationale': 'Thistlemere agreed.'})
        milestone = self.record('m1', 'milestone', 'Vexmoor launch', detail='')
        self.milestone = self.records.add_progress(self.owner, milestone['id'], {'version': milestone['version'],
                                                                                 'note': 'Vexmoor brief drafted.'})
        # A read-aloud record keeps only a hash of what was spoken.
        self.voice = VoiceLog(self.store)
        self.spoken = self.voice.generated(self.owner, {'turn_id': self.turns[1], 'text_sha256': hashlib.sha256(SPOKEN.encode()).hexdigest(),
                                                        'characters': len(SPOKEN), 'voice_local': True})

    def ask(self, sid, after, mode):
        body = {'question': QUESTION, 'mode': mode, 'follow_up': False, 'request_id': f'q{after}', 'after': after}
        self.asked_bodies = getattr(self, 'asked_bodies', []) + [body]
        self.chat.submit(self.owner, sid, body)
        self.assertTrue(self.chat.process_one())
        return body

    def record(self, request, kind, title, **over):
        body = {'request_id': request, 'kind': kind, 'title': title, 'detail': '', 'project': None, 'due': None,
                'rank': None, 'support': None, **over}
        self.record_bodies.append(body)
        return self.records.create(self.owner, body)

    def stored_bytes(self):
        found = b''
        for suffix in ('', '-wal', '-shm', '-journal', lifecycle.JOURNAL_SUFFIX):
            part = Path(str(self.path) + suffix)
            if part.exists():
                found += part.read_bytes()
        return found

    def raw(self, sql, params=()):
        with self.store.connection() as db:
            return [dict(r) for r in db.execute(sql, params)]

    def counting_seals(self):
        sealed, real = [], self.keyring.seal

        def seal(area, plaintext, where):
            sealed.append(where)
            return real(area, plaintext, where)
        self.keyring.seal = seal
        self.addCleanup(lambda: vars(self.keyring).pop('seal', None))
        return sealed

    def fault(self, call):
        with self.assertRaises(Fault) as caught:
            call()
        return caught.exception.code, caught.exception.status


class SealedRecordsAtRestTests(SealedRecordsBase):
    def test_everything_still_opens_sealed(self):
        # What follows is read from sealed values, not from text kept plain beside them.
        for table, column in (('conversations', 'title'), ('conversation_turns', 'question'), ('conversation_turns', 'result'),
                              ('conversation_action_sources', 'references_json'), ('draft_sources', 'binding'),
                              ('actions', 'parameters'), ('actions', 'proof'), ('drafts', 'body'),
                              ('executive_records', 'title'), ('executive_records', 'options'), ('executive_records', 'rationale'),
                              ('executive_progress', 'note'), ('executive_decisions', 'option_label')):
            values = [r['v'] for r in self.raw(f'SELECT {column} AS v FROM {table} WHERE {column} IS NOT NULL')]
            self.assertTrue(values and all(v.startswith('alfred-seal:1:') for v in values), (table, column))
        listing = self.chat.listing(self.owner)['sessions']
        self.assertEqual([s['title'] for s in listing], ['Umberleigh planning'])
        view = self.chat.view(self.owner, self.sid)
        self.assertEqual((view['title'], [t['state'] for t in view['turns']]), ('Umberleigh planning', ['completed', 'completed']))
        self.assertEqual(view['turns'][0]['question'], QUESTION)
        self.assertIn('Rowanhythe', view['turns'][0]['result']['packet']['evidence'][0]['excerpt'])
        self.assertEqual(view['turns'][1]['result']['claims'][0]['text'], ANSWER)
        # The draft from the conversation was carried out; its text, proof and readback open.
        found = {d['id']: d for d in drafts.search(self.store, self.owner, {'archived': 'include'})['drafts']}
        self.assertEqual((found['draft-1']['text'], found['draft-1']['status']), (DRAFT, 'verified'))
        self.assertEqual(found['inbox-1']['path'], 'ALFRED/Inbox/Umberleigh follow-up.md')
        self.assertEqual(drafts.search(self.store, self.owner, {'q': 'wrenfold'})['matched'], 1)
        state = {a['id']: a for a in self.store.state(self.owner)['actions']}
        self.assertEqual(state['local-1']['parameters'], {'text': 'Zeldacott reminder'})
        self.assertEqual(state['inbox-1']['proof']['path'], 'ALFRED/Inbox/Umberleigh follow-up.md')
        self.assertEqual(state['draft-1']['proof']['type'], 'local_sqlite_draft_readback')
        # A conversation draft whose conversation was forgotten still knows its sources.
        self.assertEqual(drafts.reopen(self.store, self.owner, 'draft-2')['origin'], 'sources')
        # Executive records and their trails.
        records = {r['id']: r for r in self.records.view(self.owner)['records']}
        decision = records[self.decision['id']]
        self.assertEqual((decision['title'], decision['detail'], decision['responsible']),
                         ('Zeldacott pricing', 'Brackenhow asked for a choice.', 'Wrenfold'))
        self.assertEqual([o['label'] for o in decision['options']], ['Quillmarsh first', 'Saltergate first'])
        self.assertEqual((decision['choice']['label'], decision['choice']['rationale']), ('Quillmarsh first', 'Thistlemere agreed.'))
        self.assertEqual([(h['event'], h['label'], h['rationale']) for h in decision['decision_history']],
                         [('decided', 'Quillmarsh first', 'Thistlemere agreed.')])
        self.assertEqual([p['note'] for p in records[self.milestone['id']]['progress']], ['Vexmoor brief drafted.'])
        # Replaying a request is recognised by its keyed hash; changing it is refused.
        self.assertEqual(self.records.create(self.owner, self.record_bodies[1])['id'], self.milestone['id'])
        self.assertEqual(self.fault(lambda: self.records.create(self.owner, {**self.record_bodies[1], 'title': 'Other'}))[0],
                         'executive_request_collision')
        self.assertTrue(self.chat.submit(self.owner, self.sid, self.asked[0])['reused'])
        self.assertEqual(self.store.propose(self.owner, self.direct)['id'], 'local-1')

    def test_no_private_text_or_plain_fingerprint_at_rest(self):
        self.chat.view(self.owner, self.sid)
        self.records.view(self.owner)
        raw = self.stored_bytes()
        leaked = [form for word in PRIVATE + (QUESTION, ANSWER, DRAFT) for form in {word, word.lower(), word.upper()}
                  if form.encode('utf-8') in raw]
        self.assertFalse(leaked, f'private text in the stored files: {leaked}')
        plain = [fingerprint(body) for body in self.asked_bodies]
        plain += [hashlib.sha256(json.dumps({k: v for k, v in body.items() if k in ('request_id', 'kind', 'title', 'detail', 'project',
                                                                                       'due', 'rank', 'support') or v is not None},
                                            sort_keys=True).encode()).hexdigest() for body in self.record_bodies]
        plain += [fingerprint({**self.direct, 'scope': 'work', 'actor': self.actor})]
        plain += [hashlib.sha256(text.encode()).hexdigest() for text in (DRAFT, SPOKEN, '# Umberleigh follow-up\nAsk Yarrowby.\n')]
        found = [d[:n] for d in plain for n in (16, 24, 32, 40, 64) if d[:n].encode() in raw]
        self.assertFalse(found, 'plain fingerprints in the stored files')
        # The keyed forms are what the person sees and approves with.
        self.assertNotIn(self.spoken['text_sha256'], plain)
        self.assertEqual(len(self.drafted['fingerprint']), 64)

    def test_reading_seals_nothing_and_unchanged_text_keeps_its_sealed_value(self):
        before = self.raw('SELECT title, detail, responsible FROM executive_records ORDER BY id')
        sealed = self.counting_seals()
        self.chat.listing(self.owner)
        self.chat.view(self.owner, self.sid)
        self.records.view(self.owner)
        drafts.search(self.store, self.owner, {'archived': 'include'})
        self.store.state(self.owner)
        self.voice.history(self.owner, self.turns[1])
        self.assertEqual(sealed, [])
        # Saving a record with its title unchanged keeps the title's stored sealed value.
        record = next(r for r in self.records.view(self.owner)['records'] if r['id'] == self.decision['id'])
        self.records.update(self.owner, record['id'], {'version': record['version'], 'title': 'Zeldacott pricing', 'rank': 3})
        self.assertEqual(sealed, [])
        self.assertEqual(self.raw('SELECT title, detail, responsible FROM executive_records ORDER BY id'), before)
        self.records.update(self.owner, record['id'], {'version': record['version'] + 1, 'detail': 'Brackenhow chose.'})
        self.assertEqual([where.split('/')[:2] for where in sealed], [['executive_records', 'detail']])

    def test_a_value_moved_to_another_row_does_not_open(self):
        with self.store.connection() as db:
            questions = db.execute('SELECT id, question FROM conversation_turns WHERE session=? ORDER BY ordinal', (self.sid,)).fetchall()
            db.execute('UPDATE conversation_turns SET question=? WHERE id=?', (questions[0]['question'], questions[1]['id']))
        self.assertEqual(self.fault(lambda: self.chat.view(self.owner, self.sid))[0], 'seal_does_not_match')

    def test_action_parameters_moved_to_another_action_do_not_open(self):
        with self.store.connection() as db:
            value = db.execute("SELECT parameters FROM actions WHERE id='local-1'").fetchone()[0]
            db.execute("UPDATE actions SET parameters=? WHERE id='draft-1'", (value,))
        self.assertEqual(self.fault(lambda: drafts.search(self.store, self.owner))[0], 'seal_does_not_match')

    def test_a_trail_entry_moved_to_another_record_does_not_open(self):
        with self.store.connection() as db:
            note = db.execute('SELECT note FROM executive_progress WHERE note IS NOT NULL').fetchone()[0]
            db.execute('INSERT INTO executive_progress VALUES (?,?,?,?,?,?)', (self.milestone['id'], 99, 'note', note, None, 1))
        self.assertEqual(self.fault(lambda: self.records.view(self.owner))[0], 'seal_does_not_match')

    def test_destroying_the_area_erases_conversations_records_and_drafts(self):
        self.keyring.destroy_area('personal')
        for call in (lambda: self.chat.listing(self.owner), lambda: self.chat.view(self.owner, self.sid),
                     lambda: self.records.view(self.owner), lambda: drafts.search(self.store, self.owner),
                     lambda: self.store.state(self.owner)):
            self.assertEqual(self.fault(call), ('area_destroyed', 410))


class RecordAreaTests(SealedRecordsBase):
    """Conversations, records, drafts and actions are made in ALFRED, so they stay in the
    default area even when every note they cite is in a client's area."""
    store_class = ClientStore

    def areas(self, sql):
        return {sealing.area_of(r['v']) for r in self.raw(sql)}

    def test_made_in_alfred_stays_in_the_default_area(self):
        self.assertEqual(self.areas('SELECT path AS v FROM knowledge_notes'), {'client-a'})
        for sql in ('SELECT title AS v FROM conversations', 'SELECT question AS v FROM conversation_turns',
                    'SELECT result AS v FROM conversation_turns', 'SELECT references_json AS v FROM conversation_action_sources',
                    'SELECT binding AS v FROM draft_sources', 'SELECT parameters AS v FROM actions',
                    'SELECT proof AS v FROM actions WHERE proof IS NOT NULL', 'SELECT body AS v FROM drafts',
                    'SELECT title AS v FROM executive_records', 'SELECT note AS v FROM executive_progress WHERE note IS NOT NULL',
                    'SELECT rationale AS v FROM executive_decisions WHERE rationale IS NOT NULL'):
            self.assertEqual(self.areas(sql), {'personal'}, sql)
        sealer = self.store.sealer
        hashes = {r['request_id']: r['request_hash'] for r in self.raw('SELECT request_id, request_hash FROM conversation_turns')}
        self.assertEqual(hashes['q0'], sealer.fingerprint('personal', fingerprint(self.asked_bodies[0])))
        draft = self.raw("SELECT digest FROM drafts WHERE action_id='draft-1'")[0]['digest']
        self.assertEqual(draft, sealer.fingerprint('personal', hashlib.sha256(DRAFT.encode()).hexdigest()))
        action = self.raw("SELECT fingerprint FROM actions WHERE id='local-1'")[0]['fingerprint']
        self.assertEqual(action, sealer.fingerprint('personal', fingerprint({**self.direct, 'scope': 'work', 'actor': self.actor})))


class RegisterTests(unittest.TestCase):
    def test_part_three_tables_are_registered(self):
        for table in ('conversations', 'conversation_turns', 'conversation_action_sources', 'executive_records',
                      'executive_progress', 'executive_decisions', 'actions', 'drafts', 'draft_sources', 'voice_playbacks'):
            self.assertIn(table, sealing.TABLES)
        self.assertEqual(sealing.TABLES['actions'][2], ('fingerprint',))
        self.assertEqual(sealing.TABLES['drafts'][2], ('digest',))
        self.assertEqual(sealing.TABLES['voice_playbacks'][2], ('text_sha256',))
        self.assertIn('request_hash', sealing.TABLES['conversation_turns'][2])
        self.assertIn('request_hash', sealing.TABLES['executive_records'][2])

    def test_a_lost_sealing_record_is_refused_when_only_a_record_is_sealed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'db.sqlite'
            sealing.attach(path, sealing.Sealed(keyring(directory, 'personal')))
            try:
                store = KnowledgeStore(path)
                owner = store.provision('work', 'owner', 'owner')
                ExecutiveRecords(store).create(owner, {'request_id': 'r1', 'kind': 'priority', 'title': 'Zeldacott', 'detail': '',
                                                       'project': None, 'due': None, 'rank': None, 'support': None})
            finally:
                sealing.detach(path)
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('DELETE FROM sealing')
            with self.assertRaises(Fault) as caught:
                KnowledgeStore(path)
            self.assertEqual(caught.exception.code, 'sealing_record_damaged')


if __name__ == '__main__':
    unittest.main()
