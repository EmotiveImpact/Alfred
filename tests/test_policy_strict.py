"""Strict grants by default (SYS-001, MEM-009, M02).

A new credential reads nothing until the owner grants it; the owner administers people
and per-source grants over HTTP (version-checked and journalled); losing a grant
withholds mid-request; and every device of one person shares one review history.
Synthetic demo workspace only, real SQLite and real loopback HTTP.
"""
from contextlib import closing
from pathlib import Path
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from alfred import lifecycle
from alfred.desk import init_demo
from alfred.desk_http import DeskHTTPServer
from alfred.grounded import ask, retrieve
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor, MarkdownVault
from alfred.local import Fault
from alfred.memory_history import MemoryHistory
from alfred.policy import IdentityPolicy, permitted
from alfred.reviewed_memory import ReviewedMemory
from grant_helpers import as_pre_strict_database


class DefaultPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.db = self.root / 'desk.sqlite'
        self.store = KnowledgeStore(self.db)
        self.owner = self.store.provision('work', 'owner', 'owner')
        self.reader = self.store.provision('work', 'reader', 'reader')
        self.source = self.store.provision('work', 'source', 'source')
        vault = self.root / 'vault'; vault.mkdir(); (vault / 'Plan.md').write_text('# Plan\nA synthetic plan.\n')
        MarkdownVault(self.store, self.source, vault).scan()
        self.policy = IdentityPolicy(self.store)

    def allowed(self, bearer, capability='read'):
        with self.store.connection() as db:
            return permitted(db, self.store.authenticate(db, bearer, {'owner', 'reader'}), 'source', self.store.now(), capability)

    def test_a_new_workspace_grants_nothing_to_anyone_the_owner_included(self):
        self.assertEqual(self.policy.view(self.owner)['mode'], 'explicit_grants')
        for bearer in (self.owner, self.reader):
            self.assertFalse(self.allowed(bearer)); self.assertFalse(self.allowed(bearer, 'model'))
            self.assertEqual(self.store.knowledge(bearer)['nodes'], [])
        self.assertEqual(self.policy.view(self.reader)['sources'], [])  # not even a label

    def test_a_new_reader_sees_nothing_until_granted_and_the_owner_grant_is_not_shared(self):
        self.policy.grant(self.owner, 'source', 'read', self.store.now() + 3600, self.policy.view(self.owner)['epoch'])
        self.assertEqual(len(self.store.knowledge(self.owner)['nodes']), 1)
        self.assertEqual(self.store.knowledge(self.reader)['nodes'], [])
        late = self.store.provision('work', 'late-reader', 'reader')  # a key issued after the grant
        self.assertEqual(self.store.knowledge(late)['nodes'], [])
        reader = self.store.principal(self.reader)['person_id']
        self.policy.grant(self.owner, 'source', 'read', self.store.now() + 3600, self.policy.view(self.owner)['epoch'], person=reader)
        self.assertEqual(len(self.store.knowledge(self.reader)['nodes']), 1)
        self.assertEqual(self.store.knowledge(late)['nodes'], [])

    def test_only_a_workspace_that_predates_strict_by_default_is_recorded_legacy_once(self):
        as_pre_strict_database(self.db)
        upgraded = KnowledgeStore(self.db)
        self.assertEqual(IdentityPolicy(upgraded).view(self.reader)['mode'], 'legacy_scope')
        with upgraded.connection() as db:
            self.assertTrue(permitted(db, upgraded.authenticate(db, self.reader, {'reader'}), 'source', upgraded.now()))
        # A workspace created after the upgrade, in the same database, is strict.
        fresh = upgraded.provision('later', 'later-owner', 'owner'); upgraded.provision('later', 'later-source', 'source')
        KnowledgeStore(self.db)  # reopening never re-runs the upgrade
        self.assertEqual(IdentityPolicy(upgraded).view(fresh)['mode'], 'explicit_grants')
        with upgraded.connection() as db:
            self.assertFalse(permitted(db, upgraded.authenticate(db, fresh, {'owner'}), 'later-source', upgraded.now()))

    def test_another_person_may_hold_only_read_and_model_and_only_if_enrolled_here(self):
        reader = self.store.principal(self.reader)['person_id']
        epoch = lambda: self.policy.view(self.owner)['epoch']
        for capability in ('inbox.write', 'connector.read', 'sync'):
            with self.assertRaises(Fault) as caught:
                self.policy.grant(self.owner, 'source', capability, self.store.now() + 60, epoch(), person=reader)
            self.assertEqual(caught.exception.code, 'invalid_capability')
        stranger = self.store.provision('elsewhere', 'stranger', 'reader')
        for person in (self.store.principal(stranger)['person_id'], 'person-' + '0' * 24, 'reader'):
            with self.assertRaises(Fault) as caught:
                self.policy.grant(self.owner, 'source', 'read', self.store.now() + 60, epoch(), person=person)
            self.assertEqual(caught.exception.code, 'person_not_available')
        with self.assertRaises(Fault) as caught:
            self.policy.grant(self.reader, 'source', 'read', self.store.now() + 60, epoch(), person=reader)
        self.assertEqual(caught.exception.code, 'forbidden')


class StrictHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'demo'; self.keys = init_demo(self.home)
        self.store = KnowledgeStore(self.home / 'desk.sqlite')
        self.sup = KnowledgeSupervisor(self.store, self.keys['owner'], self.keys['source'], self.home / 'project', vault=self.home / 'vault')
        self.sup.cycle()
        self.server = DeskHTTPServer(self.store, self.sup, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), self.thread.join(3)))
        self.sessions = {}

    def req(self, who, path, data=None, csrf=True):
        cookie, token = self.sessions.get(who, (None, None))
        headers = {'Cookie': cookie} if cookie else {}
        if data is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': self.server.origin})
            if csrf and token:
                headers['X-CSRF-Token'] = token
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); body = json.loads(r.read()); set_cookie = r.getheader('Set-Cookie'); c.close()
        if set_cookie and r.status == 200 and 'csrf' in body:
            self.sessions[who] = (set_cookie.split(';')[0], body['csrf'])
        return r.status, body

    def login(self, who, key=None):
        self.assertEqual(self.req(who, '/desk/login', {'key': key or self.keys[who]})[0], 200)

    def notes(self, who):
        return self.req(who, '/desk/console/projection')[1]['counts']['notes']

    def epoch(self):
        return self.req('owner', '/desk/identity')[1]['epoch']

    def enrol(self, label='Fictional producer', device='Fictional laptop'):
        status, offer = self.req('owner', '/desk/identity/enrolments', {'label': label, 'epoch': self.epoch()})
        self.assertEqual(status, 200, offer)
        status, joined = self.req(label, '/desk/identity/pairing/redeem', {'code': offer['code'], 'label': device})
        self.assertEqual(status, 200, joined)
        return offer, joined

    def test_demo_init_grants_its_owner_explicitly_and_its_reader_nothing(self):
        self.login('owner'); self.login('reader')
        self.assertEqual(self.notes('owner'), 20)
        self.assertEqual(self.notes('reader'), 0)
        self.assertEqual(self.req('reader', '/desk/identity')[1]['sources'], [])
        with closing(sqlite3.connect(self.home / 'desk.sqlite')) as db, db:
            created = [r[0] for r in db.execute("SELECT subject FROM audit WHERE kind='grant.created' ORDER BY seq")]
        self.assertEqual(created, ['demo-source', 'demo-source'])  # read and model, each in the audit log

    def test_enrol_list_grant_and_revoke_a_person_over_http(self):
        self.login('owner')
        # Enrolment is owner-only, CSRF-protected and version-checked.
        self.assertEqual(self.req('owner', '/desk/identity/enrolments', {'label': 'X', 'epoch': self.epoch()}, csrf=False)[0], 403)
        self.assertEqual(self.req('owner', '/desk/identity/enrolments', {'label': 'X', 'epoch': self.epoch() + 1})[1]['error'], 'policy_changed')
        offer, joined = self.enrol()
        self.assertEqual((offer['role'], offer['grants'], joined['role'], joined['new_person']), ('reader', [], 'reader', True))
        # The code is single use and indistinguishable from an unknown one afterwards.
        self.assertEqual(self.req('again', '/desk/identity/pairing/redeem', {'code': offer['code'], 'label': 'Another'})[0], 404)
        who = 'Fictional producer'
        self.assertEqual(self.notes(who), 0)  # a new reader sees nothing until granted
        self.assertEqual(self.req(who, '/desk/identity')[1]['person_id'], offer['person_id'])
        # Only the owner lists people; a person is labelled by the owner, never by device names.
        self.assertEqual(self.req(who, '/desk/identity/people')[0], 403)
        people = self.req('owner', '/desk/identity/people')[1]
        listed = {p['label']: p for p in people['people']}
        self.assertEqual(set(listed), {'You', 'Fictional producer', 'Unnamed person'})  # the demo reader is unnamed
        self.assertEqual((listed[who]['grants'], listed[who]['roles'], listed[who]['devices']), ([], ['reader'], 1))
        self.assertNotIn('Fictional laptop', json.dumps(people))
        self.assertEqual(people['shareable'], ['model', 'read'])
        path = f"/desk/identity/people/{offer['person_id']}/grants"
        body = {'source': 'demo-source', 'capability': 'read', 'days': 7, 'revoke': False}
        self.assertEqual(self.req('owner', path, {**body, 'epoch': self.epoch()}, csrf=False)[0], 403)
        self.assertEqual(self.req(who, path, {**body, 'epoch': self.epoch()})[0], 403)
        self.assertEqual(self.req('owner', path, {**body, 'capability': 'inbox.write', 'epoch': self.epoch()})[1]['error'], 'invalid_capability')
        self.assertEqual(self.req('owner', path, {**body, 'revoke': 'no', 'epoch': self.epoch()})[0], 400)
        stale = self.epoch()
        status, after = self.req('owner', path, {**body, 'epoch': stale})
        self.assertEqual(status, 200)
        granted = next(p for p in after['people'] if p['person_id'] == offer['person_id'])['grants']
        self.assertEqual([(g['source'], g['capability']) for g in granted], [('demo-source', 'read')])
        self.assertEqual(self.notes(who), 20)
        self.assertEqual(self.req('owner', path, {**body, 'epoch': stale})[1]['error'], 'policy_changed')
        self.assertEqual(self.req('owner', '/desk/identity/people/person-' + 'f' * 24 + '/grants', {**body, 'epoch': self.epoch()})[0], 404)
        self.assertEqual(self.req('owner', path, {**body, 'revoke': True, 'epoch': self.epoch()})[0], 200)
        self.assertEqual(self.notes(who), 0)
        # Journalled: the revocation is in the lifecycle journal, so a restore cannot undo it.
        journal = lifecycle.entries(lifecycle.journal_path(self.store))
        self.assertIn({'kind': 'grant_revoked', 'person': offer['person_id'], 'subject': 'demo-source', 'capability': 'read'},
                      [{k: e[k] for k in ('kind', 'person', 'subject', 'capability')} for e in journal if e['kind'] == 'grant_revoked'])
        with closing(sqlite3.connect(self.home / 'desk.sqlite')) as db, db:
            kinds = [r[0] for r in db.execute("SELECT kind FROM audit WHERE kind LIKE 'person.%' OR subject LIKE ? ORDER BY seq",
                                               (f"%{offer['person_id']}",))]
        self.assertEqual(kinds, ['person.enrolment_offered', 'person.enrolled', 'grant.created', 'grant.revoked'])

    def test_a_restore_does_not_bring_back_a_revoked_person_grant(self):
        self.login('owner')
        offer, joined = self.enrol()
        path = f"/desk/identity/people/{offer['person_id']}/grants"
        self.req('owner', path, {'source': 'demo-source', 'capability': 'read', 'days': 7, 'revoke': False, 'epoch': self.epoch()})
        manifest = lifecycle.backup(self.store, self.keys['owner'], self.home / 'backups')
        self.req('owner', path, {'source': 'demo-source', 'capability': 'read', 'days': 7, 'revoke': True, 'epoch': self.epoch()})
        lifecycle.restore(self.home / 'backups' / manifest['file'], self.home / 'desk.sqlite')
        restored = KnowledgeStore(self.home / 'desk.sqlite')
        self.assertEqual(restored.knowledge(joined['key'])['nodes'], [])

    def test_losing_a_grant_withholds_mid_request(self):
        policy = IdentityPolicy(self.store)
        owner = self.keys['owner']
        revoke = lambda capability: policy.grant(owner, 'demo-source', capability, self.store.now() + 1,
                                                 policy.view(owner)['epoch'], revoke=True)

        class Model:
            model = 'fixture-not-an-llm'
            def __init__(self): self.calls = 0
            def generate(self, packet):
                self.calls += 1; revoke('model')  # the grant is lost while the model is working
                return {'answerable': False, 'claims': []}
        model = Model()
        with self.assertRaises(Fault) as caught:
            ask(self.store, owner, {'question': 'Sample film', 'mode': 'local_model'}, model, 'demo-production')
        self.assertEqual((caught.exception.code, model.calls), ('sources_changed_during_question', 1))
        # Without a model: the read grant is lost after retrieval and before the answer returns.
        original = retrieve
        def race(*args, **kwargs):
            packet = original(*args, **kwargs); revoke('read'); return packet
        with patch('alfred.grounded.retrieve', race), self.assertRaises(Fault) as caught:
            ask(self.store, owner, {'question': 'Sample film', 'mode': 'sources'})
        self.assertEqual(caught.exception.code, 'sources_changed_during_question')
        self.assertEqual(retrieve(self.store, owner, 'Sample film')['evidence'], [])

    def test_pairing_a_device_shows_the_same_review_history(self):
        owner = self.keys['owner']
        self.login('owner')
        status, offer = self.req('owner', '/desk/identity/pairing', {'role': 'owner'})
        status, paired = self.req('tablet', '/desk/identity/pairing/redeem', {'code': offer['code'], 'label': 'Fictional tablet'})
        self.assertEqual(status, 200)
        tablet = paired['key']
        memory = ReviewedMemory(self.store); history = MemoryHistory(memory)
        note = next(n for n in self.store.knowledge(owner)['nodes'] if n['title'] == 'Sample producer')
        for identity, kind, name in (('film', 'project', 'Sample film'), ('producer', 'person', 'Sample producer')):
            memory.create_entity(owner, {'id': identity, 'kind': kind, 'name': name})
        made = memory.propose(owner, {'request_id': 'r1', 'subject_id': 'film', 'predicate': 'responsible_person', 'object_id': 'producer',
                                      'value': None, 'valid_from': None, 'valid_until': None,
                                      'evidence': {'note_id': note['id'], 'sha256': note['sha256'], 'revision': note['revision'],
                                                   'start_line': 8, 'end_line': 8}})['id']
        memory.review(owner, made, {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        on_owner, on_tablet = memory.view(owner), memory.view(tablet)
        self.assertEqual(on_tablet['claims'], on_owner['claims'])
        self.assertEqual([e['id'] for e in on_tablet['entities']], ['film', 'producer'])
        self.assertTrue(on_tablet['claims'][0]['usable'])  # reviewed on another device of the same person
        self.assertEqual([(e['state'], e['by']) for e in history.history(tablet, made)['entries']],
                         [('proposed', 'you_on_another_device'), ('accepted', 'you_on_another_device')])
        # A decision on the tablet is part of the same history, attributed to the tablet.
        memory.review(tablet, made, {'version': 2, 'decision': 'dispute', 'replaces_id': None, 'replaces_version': None})
        self.assertEqual([(e['state'], e['by']) for e in history.history(owner, made)['entries']][-1], ('disputed', 'you_on_another_device'))
        self.assertEqual(self.req('tablet', '/desk/identity')[1]['device_reviews_shared'], True)
        with closing(sqlite3.connect(self.home / 'desk.sqlite')) as db, db:
            self.assertEqual(db.execute('SELECT reviewer FROM memory_claims WHERE id=?', (made,)).fetchone()[0],
                             self.store.principal(tablet)['id'])
        # Another person's ledger stays private: the demo reader sees none of it.
        self.assertEqual(memory.view(self.keys['reader'])['claims'], [])

    def test_ledgers_written_per_credential_move_to_the_person_once(self):
        owner = self.keys['owner']
        memory = ReviewedMemory(self.store)
        memory.create_entity(owner, {'id': 'film', 'kind': 'project', 'name': 'Sample film'})
        credential = self.store.principal(owner)['id']
        with closing(sqlite3.connect(self.home / 'desk.sqlite')) as db, db:  # as an earlier version stored it
            db.execute("UPDATE memory_entities SET actor=? WHERE id='film'", (credential,))
        ReviewedMemory(self.store)
        with closing(sqlite3.connect(self.home / 'desk.sqlite')) as db, db:
            self.assertEqual(db.execute("SELECT actor FROM memory_entities WHERE id='film'").fetchone()[0],
                             self.store.principal(owner)['person_id'])

    def test_explicit_pairing_never_merges_an_established_review_history(self):
        owner = self.keys['owner']
        second = self.store.provision('demo-production', 'second-owner', 'owner')
        ReviewedMemory(self.store).create_entity(second, {'id': 'mine', 'kind': 'project', 'name': 'Private project'})
        policy = IdentityPolicy(self.store)
        view, other = policy.view(owner), policy.view(second)
        with self.assertRaises(Fault) as caught:
            policy.pair(owner, second, view['person_id'], other['device_id'])
        self.assertEqual(caught.exception.code, 'established_person_cannot_be_paired')


if __name__ == '__main__':
    unittest.main()
