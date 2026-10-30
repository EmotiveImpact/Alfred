"""Drafts never silently disappear: lapse, archive, search, re-propose, forget.

Synthetic desk documents and a synthetic vault, real SQLite, real HTTP where the
boundary matters. No model and nothing is sent.
"""
from pathlib import Path
import http.client
import json
import tempfile
import threading
import time
import unittest
from alfred import drafts, lifecycle
from alfred.conversation import ConversationService, TTL
from alfred.desk import init_demo
from grant_helpers import grant_all
from alfred.desk_http import DeskHTTPServer
from alfred.desk_runtime import Supervisor
from alfred.desk_store import DeskStore
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.local import Fault
from alfred.reviewed_memory import ReviewedMemory
from test_routines import Base as RoutineBase, T as ROUTINE_T


class DeskDraftTests(unittest.TestCase):
    """Drafts proposed from desk evidence."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.keys = init_demo(self.root); self.now = [int(time.time())]
        self.store = DeskStore(self.root / 'desk.sqlite', clock=lambda: self.now[0])
        self.sup = Supervisor(self.store, self.keys['owner'], self.keys['source'], self.root / 'project', interval=.05)
        self.addCleanup(self.sup.stop)
        self.sup.cycle()
        self.owner = self.keys['owner']

    def event(self):
        return next(e for e in self.store.desk_state(self.owner)['events'] if e['filename'] == 'schedule.json')

    def propose(self, request_id='draft-1', text='Please review the sample change.'):
        return self.store.propose_from_evidence(self.owner, {'event_seq': self.event()['seq'], 'text': text, 'request_id': request_id})

    def find(self, **filters):
        return drafts.search(self.store, self.owner, filters)

    def fault(self, call, *args):
        with self.assertRaises(Fault) as caught:
            call(*args)
        return caught.exception.code

    def test_lapsed_draft_is_kept_and_visible(self):
        draft = self.propose()
        self.assertEqual(self.find()['drafts'][0]['status'], 'awaiting_approval')
        self.now[0] += 901
        found = self.find()['drafts']
        self.assertEqual([(d['id'], d['status'], d['text']) for d in found], [(draft['id'], 'lapsed', 'Please review the sample change.')])
        self.assertTrue(found[0]['approval_lapsed'])
        # The old approval can never be used once the window has lapsed.
        self.assertEqual(self.fault(self.store.approve, self.owner, draft['id'], draft['fingerprint']), 'evidence_or_approval_expired')
        # Still there hours later, after the evidence itself expired; nothing prunes it.
        self.now[0] += 20 * 3600
        self.assertEqual(self.find(status='lapsed')['matched'], 1)

    def test_repropose_makes_a_fresh_bound_approval(self):
        draft = self.propose(); self.now[0] += 901
        current = drafts.reopen(self.store, self.owner, draft['id'])
        self.assertTrue(current['reproposable']); self.assertIsNone(current['repropose_blocked_by'])
        fresh = drafts.repropose(self.store, self.owner, draft['id'], {'version': 1, 'request_id': 'draft-2'})
        self.assertEqual((fresh['id'], fresh['state'], fresh['reproposed_from']), ('draft-2', 'proposed', draft['id']))
        self.assertNotEqual(fresh['fingerprint'], draft['fingerprint'])
        self.assertEqual(fresh['parameters'], draft['parameters'])
        # The old fingerprint does not approve the new action, and the old action stays lapsed.
        self.assertEqual(self.fault(self.store.approve, self.owner, 'draft-2', draft['fingerprint']), 'approval_mismatch')
        self.store.approve(self.owner, 'draft-2', fresh['fingerprint'])
        self.assertEqual(self.store.tick(self.owner)['state'], 'verified')
        listed = {d['id']: d for d in self.find()['drafts']}
        self.assertEqual((listed[draft['id']]['status'], listed[draft['id']]['reproposed_as']), ('lapsed', ['draft-2']))
        self.assertEqual(listed['draft-2']['status'], 'verified')
        # Idempotent retry; a different request reusing the id collides.
        self.assertEqual(drafts.repropose(self.store, self.owner, draft['id'], {'version': 1, 'request_id': 'draft-2'})['id'], 'draft-2')
        self.assertEqual(self.fault(drafts.repropose, self.store, self.owner, draft['id'], {'version': 1, 'request_id': 'draft-2', 'text': 'Other.'}),
                         'action_id_collision')

    def test_repropose_with_edited_text_binds_the_new_text(self):
        draft = self.propose(); self.now[0] += 901
        fresh = drafts.repropose(self.store, self.owner, draft['id'], {'version': 1, 'request_id': 'draft-2', 'text': 'Edited sample.'})
        self.assertEqual(fresh['parameters'], {'text': 'Edited sample.'})
        self.store.approve(self.owner, 'draft-2', fresh['fingerprint']); self.store.tick(self.owner)
        with self.store.connection() as db:
            self.assertEqual(db.execute("SELECT body FROM drafts WHERE action_id='draft-2'").fetchone()[0], 'Edited sample.')

    def test_repropose_rechecks_evidence(self):
        draft = self.propose(); self.now[0] += 901
        path = self.root / 'project/schedule.json'; value = json.loads(path.read_text())
        value.update({'revision': value['revision'] + 1, 'observed_at': self.now[0], 'expires_at': self.now[0] + 600})
        path.write_text(json.dumps(value)); self.sup.cycle()
        self.assertEqual(drafts.reopen(self.store, self.owner, draft['id'])['repropose_blocked_by'], 'evidence_not_current')
        self.assertEqual(self.fault(drafts.repropose, self.store, self.owner, draft['id'], {'version': 1, 'request_id': 'draft-2'}),
                         'evidence_not_current')
        # Nothing half-made is left behind.
        with self.store.connection() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM actions WHERE id='draft-2'").fetchone())
            self.assertIsNone(db.execute("SELECT 1 FROM desk_action_evidence WHERE action_id='draft-2'").fetchone())
        # The draft itself is still findable.
        self.assertEqual(self.find(q='sample change')['drafts'][0]['id'], draft['id'])

    def test_cannot_repropose_while_awaiting_or_in_progress(self):
        draft = self.propose()
        self.assertEqual(self.fault(drafts.repropose, self.store, self.owner, draft['id'], {'version': 1, 'request_id': 'draft-2'}),
                         'draft_still_awaiting_approval')
        self.store.approve(self.owner, draft['id'], draft['fingerprint'])
        self.assertEqual(self.fault(drafts.repropose, self.store, self.owner, draft['id'], {'version': 1, 'request_id': 'draft-2'}),
                         'draft_in_progress')
        self.assertEqual(self.fault(drafts.archive, self.store, self.owner, draft['id'], {'version': 1}), 'draft_in_progress')

    def test_archive_and_unarchive_are_version_checked_and_journalled(self):
        draft = self.propose()
        archived = drafts.archive(self.store, self.owner, draft['id'], {'version': 1})
        self.assertEqual((archived['status'], archived['archived'], archived['version']), ('archived', True, 2))
        # Archiving closes the approval window; the draft text is kept.
        self.assertEqual(self.fault(self.store.approve, self.owner, draft['id'], draft['fingerprint']), 'evidence_or_approval_expired')
        self.assertEqual(self.find()['drafts'], [])
        self.assertEqual([d['id'] for d in self.find(archived='only')['drafts']], [draft['id']])
        self.assertEqual([d['id'] for d in self.find(status='archived')['drafts']], [draft['id']])
        self.assertEqual(self.find(archived='include')['matched'], 1)
        self.assertEqual(self.fault(drafts.unarchive, self.store, self.owner, draft['id'], {'version': 1}), 'draft_changed')
        back = drafts.unarchive(self.store, self.owner, draft['id'], {'version': 2})
        self.assertEqual((back['status'], back['version']), ('lapsed', 3))
        # A repeated archive request with a stale version is refused, not applied twice.
        self.assertEqual(self.fault(drafts.archive, self.store, self.owner, draft['id'], {'version': 2}), 'draft_changed')
        audit = [a['kind'] for a in self.store.desk_state(self.owner)['audit']]
        self.assertIn('draft.archived', audit); self.assertIn('draft.unarchived', audit)
        # An archived draft can still be re-proposed.
        drafts.archive(self.store, self.owner, draft['id'], {'version': 3})
        fresh = drafts.repropose(self.store, self.owner, draft['id'], {'version': 4, 'request_id': 'draft-2'})
        self.assertEqual(fresh['state'], 'proposed')
        self.assertIn('action.reproposed_from_draft', [a['kind'] for a in self.store.desk_state(self.owner)['audit']])

    def test_search_by_text_date_and_status(self):
        first = self.propose('draft-a', 'Budget note for the quarter.')
        self.now[0] += 2000
        second = self.propose('draft-b', 'Travel plan for the offsite.')
        self.assertEqual([d['id'] for d in self.find(q='BUDGET')['drafts']], [first['id']])
        self.assertEqual([d['id'] for d in self.find(since=self.now[0] - 1000)['drafts']], [second['id']])
        self.assertEqual([d['id'] for d in self.find(until=self.now[0] - 1000)['drafts']], [first['id']])
        self.assertEqual({d['id'] for d in self.find(status='lapsed')['drafts']}, {first['id']})
        self.assertEqual({d['id'] for d in self.find(status='awaiting_approval')['drafts']}, {second['id']})
        self.assertEqual(self.find(limit=1)['matched'], 2)
        self.assertEqual(len(self.find(limit=1)['drafts']), 1)

    def test_query_parsing(self):
        parsed = drafts.parse_query({'q': ['budget'], 'since': ['2026-10-01'], 'until': ['2026-10-02'], 'archived': ['include']})
        self.assertEqual(parsed['until'] - parsed['since'], 2 * 86400 - 1)
        for bad in ({'status': ['gone']}, {'archived': ['all']}, {'limit': ['0']}, {'since': ['yesterday']}, {'scope': ['x']}, {'q': ['a', 'b']}):
            with self.assertRaises(Fault):
                drafts.parse_query(bad)

    def test_drafts_are_private_to_their_owner(self):
        draft = self.propose()
        other = self.store.provision(self.event_scope(), 'second-owner', 'owner')
        self.assertEqual(drafts.search(self.store, other)['drafts'], [])
        for call, args in ((drafts.reopen, ()), (drafts.archive, ({'version': 1},)), (drafts.repropose, ({'version': 1, 'request_id': 'x1'},))):
            with self.assertRaises(Fault) as caught:
                call(self.store, other, draft['id'], *args)
            self.assertEqual(caught.exception.code, 'draft_not_found')
        with self.assertRaises(Fault) as caught:
            drafts.search(self.store, self.keys['reader'])
        self.assertEqual(caught.exception.code, 'forbidden')

    def event_scope(self):
        return self.store.desk_state(self.owner)['scope']

    def test_source_forget_withdraws_archived_and_lapsed_drafts(self):
        lapsed = self.propose('draft-a', 'Lapsed text from the schedule.')
        archived = self.propose('draft-b', 'Archived text from the schedule.')
        drafts.archive(self.store, self.owner, archived['id'], {'version': 1})
        self.now[0] += 901
        source = self.store.principal(self.keys['source'], {'source'})['id']
        receipt = lifecycle.forget_source(self.store, self.owner, source)
        self.assertEqual(sorted(receipt['drafts_withdrawn']), ['draft-a', 'draft-b'])
        listed = {d['id']: d for d in self.find(archived='include')['drafts']}
        self.assertEqual({(d['status'], d['text'], d['withdrawn']) for d in listed.values()}, {('withdrawn', None, 'source_forgotten')})
        self.assertEqual(self.find(q='schedule', archived='include')['matched'], 0)
        with self.store.connection() as db:
            stored = ' '.join(r[0] for r in db.execute('SELECT parameters FROM actions'))
        self.assertNotIn('schedule', stored)
        for draft in (lapsed, archived):
            self.assertEqual(self.fault(drafts.repropose, self.store, self.owner, draft['id'], {'version': 3 if draft is archived else 2, 'request_id': 'again-' + draft['id']}),
                             'draft_withdrawn')
        # Unarchiving does not bring the text back.
        self.assertIsNone(drafts.unarchive(self.store, self.owner, archived['id'], {'version': 3})['text'])

    def test_console_projection_marks_lapsed(self):
        from alfred.drafts import draft_status
        draft = self.propose(); self.now[0] += 901
        with self.store.connection() as db:
            row = db.execute('SELECT * FROM actions WHERE id=?', (draft['id'],)).fetchone()
            self.assertEqual(draft_status(db, row, self.store.now()), 'lapsed')


class ConversationDraftTests(unittest.TestCase):
    """Drafts proposed from a conversation answer outlive the conversation."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.clock = [1000]
        self.store = KnowledgeStore(self.root / 'desk.sqlite', clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=2000000)
        self.source = self.store.provision('work', 'source', 'source', ttl=2000000)
        grant_all(self.store, self.owner)
        self.vault = self.root / 'vault'; self.vault.mkdir()
        (self.vault / 'Atlas.md').write_text('# Atlas\nAtlas is awaiting review.\nMina leads Atlas.\n')
        self.scanner = MarkdownVault(self.store, self.source, self.vault); self.scanner.scan()
        self.memory = ReviewedMemory(self.store)
        self.memory.create_entity(self.owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas'})
        note = self.store.knowledge(self.owner)['nodes'][0]
        made = self.memory.propose(self.owner, {'request_id': 's1', 'subject_id': 'atlas', 'predicate': 'status', 'object_id': None,
                                                'value': 'awaiting review', 'valid_from': None, 'valid_until': None,
                                                'evidence': {'note_id': note['id'], 'sha256': note['sha256'], 'revision': note['revision'], 'start_line': 2, 'end_line': 2}})
        self.memory.review(self.owner, made['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        self.claim = made['id']
        self.service = ConversationService(self.store, None, 'work'); self.addCleanup(self.service.stop)
        self.sid = self.service.create(self.owner, {'title': 'Atlas'})['id']
        self.service.submit(self.owner, self.sid, {'question': 'What is the Atlas status?', 'mode': 'sources', 'follow_up': False, 'request_id': 'q1', 'after': 0})
        self.service.process_one()
        turn = self.service.view(self.owner, self.sid)['turns'][0]
        self.draft = self.service.propose_draft(self.owner, self.sid, {'turn_id': turn['id'], 'text': 'Atlas update for Mina.', 'request_id': 'draft-1'})

    def expire_conversation(self):
        self.clock[0] += TTL + 1
        with self.store.transaction() as db:
            self.service.cleanup(db)
        with self.store.connection() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM conversations WHERE id=?', (self.sid,)).fetchone())

    def test_draft_survives_conversation_retention_and_can_be_reproposed(self):
        self.expire_conversation()
        found = drafts.search(self.store, self.owner)['drafts']
        self.assertEqual([(d['id'], d['status'], d['origin']) for d in found], [('draft-1', 'lapsed', 'sources')])
        self.assertTrue(drafts.reopen(self.store, self.owner, 'draft-1')['reproposable'])
        fresh = drafts.repropose(self.store, self.owner, 'draft-1', {'version': 1, 'request_id': 'draft-2'})
        approved = self.store.approve(self.owner, 'draft-2', fresh['fingerprint'])
        self.assertEqual(approved['state'], 'queued')
        self.assertEqual(self.store.tick(self.owner)['state'], 'verified')

    def test_reproposal_is_rechecked_against_changed_source(self):
        self.expire_conversation()
        fresh = drafts.repropose(self.store, self.owner, 'draft-1', {'version': 1, 'request_id': 'draft-2'})
        (self.vault / 'Atlas.md').write_text('# Atlas\nAtlas is cancelled.\nMina leads Atlas.\n'); self.scanner.scan()
        with self.assertRaises(Fault) as caught:
            self.store.approve(self.owner, 'draft-2', fresh['fingerprint'])
        self.assertEqual(caught.exception.code, 'evidence_or_approval_expired')
        self.assertEqual(drafts.reopen(self.store, self.owner, 'draft-1')['repropose_blocked_by'], 'evidence_not_current')

    def test_forgetting_the_source_withdraws_kept_and_reproposed_drafts(self):
        self.expire_conversation()
        drafts.repropose(self.store, self.owner, 'draft-1', {'version': 1, 'request_id': 'draft-2'})
        drafts.archive(self.store, self.owner, 'draft-1', {'version': 1})
        receipt = lifecycle.forget_source(self.store, self.owner, 'source')
        self.assertEqual(sorted(receipt['drafts_withdrawn']), ['draft-1', 'draft-2'])
        # The lapsed original was still undecided, so it is cancelled as well as withdrawn.
        self.assertEqual(receipt['pending_actions_cancelled'], ['draft-1', 'draft-2'])
        listed = {d['id']: d for d in drafts.search(self.store, self.owner, {'archived': 'include'})['drafts']}
        self.assertEqual({d['status'] for d in listed.values()}, {'withdrawn'})
        self.assertNotIn('Mina', json.dumps(listed))
        with self.assertRaises(Fault) as caught:
            drafts.repropose(self.store, self.owner, 'draft-1', {'version': listed['draft-1']['version'], 'request_id': 'draft-3'})
        self.assertEqual(caught.exception.code, 'draft_withdrawn')

    def test_forgetting_the_statement_withdraws_a_reproposed_draft(self):
        self.expire_conversation()
        drafts.repropose(self.store, self.owner, 'draft-1', {'version': 1, 'request_id': 'draft-2'})
        version = next(c for c in self.memory.view(self.owner)['claims'] if c['id'] == self.claim)['version']
        receipt = self.memory.forget(self.owner, self.claim, {'version': version})
        self.assertIn('draft-2', receipt['pending_actions_cancelled'])
        self.assertEqual(sorted(receipt['drafts_withdrawn']), ['draft-1', 'draft-2'])

    def test_restore_replays_the_withdrawal(self):
        self.expire_conversation()
        manifest = lifecycle.backup(self.store, self.owner, self.root / 'backups')
        # An absolute removal holds through a restore; an ordinary one would come back with its drafts.
        lifecycle.forget_source(self.store, self.owner, 'source', absolute=True)
        lifecycle.restore(self.root / 'backups' / manifest['file'], self.root / 'desk.sqlite')
        restored = KnowledgeStore(self.root / 'desk.sqlite', clock=lambda: self.clock[0])
        found = drafts.search(restored, self.owner)['drafts']
        self.assertEqual([(d['id'], d['status'], d['text']) for d in found], [('draft-1', 'withdrawn', None)])

    def test_forgetting_the_conversation_keeps_the_draft(self):
        self.service.forget(self.owner, self.sid)
        self.clock[0] += 901
        self.assertEqual(drafts.search(self.store, self.owner)['drafts'][0]['text'], 'Atlas update for Mina.')
        self.assertTrue(drafts.reopen(self.store, self.owner, 'draft-1')['reproposable'])


class DraftHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.now = [int(time.time())]
        self.keys = init_demo(self.root); self.store = DeskStore(self.root / 'desk.sqlite', clock=lambda: self.now[0])
        self.sup = Supervisor(self.store, self.keys['owner'], self.keys['source'], self.root / 'project'); self.sup.cycle()
        self.server = DeskHTTPServer(self.store, self.sup, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True); self.thread.start()
        self.cookie = self.csrf = None

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.sup.stop()

    def request(self, path, body=None, headers=None):
        h = {'Host': self.server.host}
        if self.cookie: h['Cookie'] = self.cookie
        if body is not None: h.update({'Origin': self.server.origin, 'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf or ''})
        for k, v in (headers or {}).items():
            if v is None: h.pop(k, None)
            else: h[k] = v
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        conn.request('POST' if body is not None else 'GET', path, body=json.dumps(body).encode() if body is not None else None, headers=h)
        r = conn.getresponse(); value = json.loads(r.read()); conn.close()
        return r.status, value

    def login(self, role='owner'):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        conn.request('POST', '/desk/login', body=json.dumps({'key': self.keys[role]}).encode(),
                     headers={'Host': self.server.host, 'Origin': self.server.origin, 'Content-Type': 'application/json'})
        r = conn.getresponse(); data = json.loads(r.read()); self.cookie = r.getheader('Set-Cookie').split(';')[0]; self.csrf = data['csrf']; conn.close()

    def test_whole_socket_flow(self):
        self.assertEqual(self.request('/desk/drafts')[0], 401)
        self.login()
        seq = self.request('/desk/state')[1]['events'][0]['seq']
        status, draft = self.request('/desk/proposals', {'event_seq': seq, 'text': 'Kept sample draft.', 'request_id': 'http-draft'})
        self.assertEqual(status, 200)
        self.now[0] += 901
        status, listing = self.request('/desk/drafts?q=kept&status=lapsed')
        self.assertEqual((status, [d['id'] for d in listing['drafts']]), (200, ['http-draft']))
        self.assertEqual(self.request('/desk/drafts?bogus=1')[0], 400)
        status, opened = self.request('/desk/drafts/http-draft')
        self.assertEqual((status, opened['reproposable']), (200, True))
        # CSRF and Origin still guard every change.
        self.assertEqual(self.request('/desk/drafts/http-draft/archive', {'version': 1}, {'X-CSRF-Token': None})[0], 403)
        self.assertEqual(self.request('/desk/drafts/http-draft/archive', {'version': 1}, {'Origin': 'https://other.example'})[0], 403)
        self.assertEqual(self.request('/desk/drafts/http-draft/archive', {'version': 1})[1]['status'], 'archived')
        self.assertEqual(self.request('/desk/drafts')[1]['drafts'], [])
        self.assertEqual(len(self.request('/desk/drafts?archived=only')[1]['drafts']), 1)
        self.assertEqual(self.request('/desk/drafts/http-draft/unarchive', {'version': 1})[0], 409)
        self.assertEqual(self.request('/desk/drafts/http-draft/unarchive', {'version': 2})[1]['status'], 'lapsed')
        status, fresh = self.request('/desk/drafts/http-draft/repropose', {'version': 3, 'request_id': 'http-draft-2'})
        self.assertEqual((status, fresh['state']), (200, 'proposed'))
        self.assertEqual(self.request('/desk/actions/http-draft-2/approve', {'fingerprint': draft['fingerprint']})[0], 409)
        self.assertEqual(self.request('/desk/actions/http-draft-2/approve', {'fingerprint': fresh['fingerprint']})[0], 200)
        self.assertEqual(self.request('/desk/drafts/http-draft/delete', {})[0], 404)

    def test_reader_cannot_list_drafts(self):
        self.login('reader')
        self.assertEqual(self.request('/desk/drafts')[0], 403)


class RoutineDraftTests(RoutineBase):
    """A draft accepted from a routine nomination keeps its cited commitment condition."""

    def setUp(self):
        super().setUp()
        self.made = self.record(due=ROUTINE_T - 3600, responsible='Coordinator')
        self.configure(propose_drafts=True); self.run_now()
        nomination = next(n for n in self.nominations() if n['kind'] == 'draft')
        self.action = self.routines.accept(self.owner, nomination['id'], {'version': nomination['version'], 'create_follow_up': False})['action']

    def test_lapsed_routine_draft_reproposes_and_rechecks_commitment(self):
        self.clock[0] += 901
        self.assertEqual(drafts.search(self.store, self.owner)['drafts'][0]['status'], 'lapsed')
        fresh = drafts.repropose(self.store, self.owner, self.action['id'], {'version': 1, 'request_id': 'routine-again'})
        self.records.update(self.owner, self.made['id'], {'version': 1, 'status': 'done'})
        self.fault('evidence_or_approval_expired', self.store.approve, self.owner, 'routine-again', fresh['fingerprint'])
        self.fault('evidence_not_current', drafts.repropose, self.store, self.owner, self.action['id'], {'version': 1, 'request_id': 'routine-third'})


if __name__ == '__main__':
    unittest.main()
