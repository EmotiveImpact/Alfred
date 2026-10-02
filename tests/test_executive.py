"""ATT-002 executive records: authored, actor-private, evidence-aware, never inferred obligations.

Synthetic notes, real SQLite, and real HTTP where the boundary matters.
"""
from pathlib import Path
import http.client
import json
import tempfile
import threading
import unittest
from alfred.local import Fault
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.reviewed_memory import ReviewedMemory
from alfred.executive import ExecutiveRecords

DAY = 86400


class ExecutiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name); self.clock = [1_000_000]
        self.store = KnowledgeStore(root / 'desk.sqlite', clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=2592000)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=2592000)
        self.source = self.store.provision('work', 'source', 'source', ttl=2592000)
        self.vault = root / 'vault'; self.vault.mkdir()
        (self.vault / 'Atlas.md').write_text('# Atlas\nLaunch review on Friday.\nBudget sign-off pending.\n')
        self.scanner = MarkdownVault(self.store, self.source, self.vault); self.scanner.scan()
        other_source = self.store.provision('elsewhere', 'other-source', 'source', ttl=2592000)
        self.other_owner = self.store.provision('elsewhere', 'other-owner', 'owner', ttl=2592000)
        other = root / 'other'; other.mkdir(); (other / 'Hidden.md').write_text('# Hidden\nElsewhere.\n')
        MarkdownVault(self.store, other_source, other).scan()
        ReviewedMemory(self.store).create_entity(self.owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas'})
        self.records = ExecutiveRecords(self.store)
        self.seq = 0

    def note(self):
        return self.store.knowledge(self.owner)['nodes'][0]

    def create(self, kind, title='Atlas launch', bearer=None, **over):
        self.seq += 1
        body = {'request_id': f'r{self.seq}', 'kind': kind, 'title': title, 'detail': '', 'project': 'entity:atlas',
                'due': None, 'rank': None, 'support': None}
        body.update(over)
        return self.records.create(bearer or self.owner, body)

    def support(self, line=2):
        n = self.note()
        return {'note_id': n['id'], 'sha256': n['sha256'], 'revision': n['revision'], 'start_line': line, 'end_line': line}

    def test_each_kind_starts_in_its_own_open_state(self):
        states = {k: self.create(k)['status'] for k in ('goal', 'priority', 'commitment', 'decision', 'milestone', 'follow_up')}
        self.assertEqual(states, {'goal': 'active', 'priority': 'open', 'commitment': 'open', 'decision': 'proposed',
                                  'milestone': 'open', 'follow_up': 'open'})
        self.assertTrue(all(not r['authority_granted'] for r in self.records.view(self.owner)['records']))

    def test_request_ids_are_idempotent_and_collide_on_change(self):
        body = {'request_id': 'same', 'kind': 'goal', 'title': 'Ship Atlas', 'detail': 'Line one.\nLine two.', 'project': None,
                'due': None, 'rank': None, 'support': None}
        first = self.records.create(self.owner, body)
        self.assertEqual(self.records.create(self.owner, dict(body))['id'], first['id'])
        with self.assertRaises(Fault) as caught:
            self.records.create(self.owner, {**body, 'title': 'Different'})
        self.assertEqual(caught.exception.code, 'executive_request_collision')

    def test_updates_are_version_checked_and_status_bounded(self):
        made = self.create('decision')
        decided = self.records.update(self.owner, made['id'], {'version': 1, 'status': 'decided'})
        self.assertEqual((decided['status'], decided['version']), ('decided', 2))
        with self.assertRaises(Fault) as caught:
            self.records.update(self.owner, made['id'], {'version': 1, 'status': 'superseded'})
        self.assertEqual(caught.exception.code, 'executive_record_changed')
        with self.assertRaises(Fault):
            self.records.update(self.owner, made['id'], {'version': 2, 'status': 'done'})

    def test_cited_support_is_exact_and_flagged_when_it_changes(self):
        made = self.create('commitment', support=self.support(3))
        self.assertEqual((made['support']['state'], made['support']['quote']), ('current', 'Budget sign-off pending.'))
        (self.vault / 'Atlas.md').write_text('# Atlas\nLaunch review on Friday.\nBudget approved.\n'); self.scanner.scan()
        record = self.records.view(self.owner)['records'][0]
        self.assertEqual((record['support']['state'], record['support']['quote']), ('changed', None))
        self.assertEqual(record['status'], 'open')

    def test_project_link_must_be_visible(self):
        hidden = self.store.knowledge(self.other_owner)['nodes'][0]['id']
        for project in ('note:' + hidden, 'entity:unknown'):
            with self.assertRaises(Fault) as caught:
                self.create('milestone', project=project)
            self.assertEqual(caught.exception.code, 'project_not_available')
        with self.assertRaises(Fault):
            self.create('milestone', project='claim:1')

    def test_progress_counts_recorded_milestones_only(self):
        a = self.create('milestone', title='Design'); self.create('milestone', title='Build')
        dropped = self.create('milestone', title='Abandoned')
        self.records.update(self.owner, a['id'], {'version': 1, 'status': 'done'})
        self.records.update(self.owner, dropped['id'], {'version': 1, 'status': 'dropped'})
        self.create('commitment', title='Not a milestone')
        progress = self.records.view(self.owner)['milestone_progress']
        self.assertEqual(progress, [{'project': 'entity:atlas', 'done': 1, 'total': 2, 'basis': 'recorded_milestones_only'}])

    def test_recommendations_follow_one_stated_rule_and_need_acceptance(self):
        soon = self.create('commitment', title='Send budget', due=self.clock[0] + 2 * DAY)
        self.create('commitment', title='Later work', due=self.clock[0] + 30 * DAY)
        self.create('follow_up', title='No date')
        late = self.create('follow_up', title='Chase venue', due=self.clock[0] - DAY)
        view = self.records.view(self.owner)
        self.assertEqual(sorted(r['title'] for r in view['recommendations']), ['Chase venue', 'Send budget'])
        self.assertTrue(all(r['basis'] == 'recommendation_not_obligation' for r in view['recommendations']))
        self.assertEqual(view['priorities'], [])
        self.assertTrue(next(r for r in view['records'] if r['id'] == late['id'])['overdue'])
        accepted = self.records.accept_recommendation(self.owner, {'request_id': 'acc', 'from_record': soon['id'], 'from_version': 1})
        self.assertEqual((accepted['kind'], accepted['origin'], accepted['derived_from']), ('priority', 'accepted_recommendation', soon['id']))
        view = self.records.view(self.owner)
        self.assertEqual([r['title'] for r in view['recommendations']], ['Chase venue'])
        self.assertEqual([p['title'] for p in view['priorities']], ['Send budget'])
        with self.assertRaises(Fault):
            self.records.accept_recommendation(self.owner, {'request_id': 'stale', 'from_record': late['id'], 'from_version': 9})

    def test_priorities_order_by_rank_then_open_first(self):
        self.create('priority', title='Third', rank=3); first = self.create('priority', title='First', rank=1)
        self.create('priority', title='Unranked')
        self.records.update(self.owner, first['id'], {'version': 1, 'status': 'done'})
        self.assertEqual([p['title'] for p in self.records.view(self.owner)['priorities']], ['Third', 'Unranked', 'First'])

    def test_records_are_actor_private_and_owner_written(self):
        self.create('goal')
        self.assertEqual(self.records.view(self.reader)['records'], [])
        with self.assertRaises(Fault):
            self.create('goal', bearer=self.reader)

    def test_invalid_values_are_rejected(self):
        base = {'request_id': 'bad', 'kind': 'priority', 'title': 'Valid', 'detail': '', 'project': None,
                'due': None, 'rank': None, 'support': None}
        for over in ({'kind': 'wish'}, {'rank': 0}, {'due': -1}, {'title': ''}, {'detail': 'bad\x00'}):
            with self.assertRaises(Fault, msg=over):
                self.records.create(self.owner, {**base, **over})
        self.assertEqual(self.records.view(self.owner)['records'], [])


class ExecutiveHTTPTests(unittest.TestCase):
    def setUp(self):
        from alfred.desk import init_demo
        from alfred.knowledge import KnowledgeSupervisor
        from alfred.desk_http import DeskHTTPServer
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        home = Path(self.tmp.name) / 'demo'; self.keys = init_demo(home)
        self.store = KnowledgeStore(home / 'desk.sqlite')
        sup = KnowledgeSupervisor(self.store, self.keys['owner'], self.keys['source'], home / 'project', vault=home / 'vault'); sup.cycle()
        self.server = DeskHTTPServer(self.store, sup, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), self.thread.join(3)))
        self.cookie = self.csrf = None

    def req(self, path, data=None, csrf=True):
        headers = {'Cookie': self.cookie} if self.cookie else {}
        if data is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': self.server.origin})
            if csrf and self.csrf: headers['X-CSRF-Token'] = self.csrf
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); body = json.loads(r.read()); cookie = r.getheader('Set-Cookie'); c.close()
        return r.status, body, cookie

    def login(self, role='owner'):
        code, data, cookie = self.req('/desk/login', {'key': self.keys[role]}); self.cookie = cookie.split(';')[0]; self.csrf = data['csrf']

    def test_records_reach_the_projection_and_the_panel_together(self):
        self.login()
        film = next(n for n in self.req('/desk/knowledge')[1]['nodes'] if n['title'] == 'Sample film')
        body = {'request_id': 'm1', 'kind': 'milestone', 'title': 'Picture lock', 'detail': '', 'project': 'note:' + film['id'],
                'due': None, 'rank': None, 'support': {'note_id': film['id'], 'sha256': film['sha256'], 'revision': film['revision'],
                                                     'start_line': 8, 'end_line': 8}}
        self.assertEqual(self.req('/desk/executive/records', body, csrf=False)[0], 403)
        code, made, _ = self.req('/desk/executive/records', body)
        self.assertEqual(code, 200)
        self.req('/desk/executive/records', {**body, 'request_id': 'p1', 'kind': 'priority', 'title': 'Confirm crew', 'rank': 1, 'support': None})
        p = self.req('/desk/console/projection')[1]
        node = next(n for n in p['nodes'] if n['id'] == 'exec:' + made['id'])
        self.assertEqual((node['category'], node['origin'], node['kind']), ('operations', 'executive_record', 'milestone'))
        layers = {(e['layer'], e['to']) for e in p['edges'] if e['from'] == node['id']}
        self.assertEqual(layers, {('executive_link', 'note:' + film['id']), ('executive_support', 'note:' + film['id'])})
        self.assertEqual(p['executive']['milestones'], [{'project': 'note:' + film['id'], 'done': 0, 'total': 1}])
        self.assertEqual([x['title'] for x in p['executive']['priorities']], ['Confirm crew'])
        detail = self.req('/desk/console/records/exec:' + made['id'])[1]
        self.assertEqual(detail['support']['state'], 'current')
        code, updated, _ = self.req('/desk/executive/records/' + made['id'], {'version': 1, 'status': 'done'})
        self.assertEqual((code, updated['status']), (200, 'done'))
        self.assertEqual(self.req('/desk/console/projection')[1]['executive']['milestones'][0]['done'], 1)
        self.login('reader')
        self.assertEqual(self.req('/desk/executive')[1]['records'], [])
        self.assertEqual(self.req('/desk/console/records/exec:' + made['id'])[0], 404)
        self.assertEqual(self.req('/desk/executive/records', {**body, 'request_id': 'r2'})[0], 403)


if __name__ == '__main__':
    unittest.main()
