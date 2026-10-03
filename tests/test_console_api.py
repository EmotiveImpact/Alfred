"""Real HTTP acceptance for the console's read-only authorised projection.

Synthetic Markdown only. Checks that the projection is built from the backend
records the bearer may read, that other workspaces and ungranted sources leak no
names or counts, and that source changes and revocation are visible.
"""
from pathlib import Path
import http.client
import json
import tempfile
import threading
import unittest
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor, MarkdownVault
from alfred.desk_http import DeskHTTPServer
from alfred.policy import IdentityPolicy


class ConsoleProjectionHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name); self.home = root / 'demo'; self.keys = init_demo(self.home, legacy_scope=True)
        self.store = KnowledgeStore(self.home / 'desk.sqlite')
        self.sup = KnowledgeSupervisor(self.store, self.keys['owner'], self.keys['source'], self.home / 'project', vault=self.home / 'vault')
        self.sup.cycle()
        dist = root / 'dist'; (dist / 'assets').mkdir(parents=True)
        (dist / 'index.html').write_bytes(b'<!doctype html><html><head><meta name="alfred-mode" content="demo"/></head><body></body></html>')
        (dist / 'assets' / 'index-abc.js').write_text('export {};\n')
        (dist / 'mark.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        (root / 'outside.js').write_text('secret')
        self.server = DeskHTTPServer(self.store, self.sup, port=0, console_dist=dist)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close); self.cookie = self.csrf = None
        self.root = root

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)

    def raw(self, path, data=None, headers=None):
        headers = dict(headers or {})
        if self.cookie: headers.setdefault('Cookie', self.cookie)
        if data is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': self.server.origin})
            if self.csrf: headers['X-CSRF-Token'] = self.csrf
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); body = r.read(); c.close()
        return r, body

    def req(self, path, data=None):
        r, body = self.raw(path, data)
        return r.status, json.loads(body)

    def login(self, key):
        r, body = self.raw('/desk/login', {'key': key}); self.assertEqual(r.status, 200)
        self.cookie = r.getheader('Set-Cookie').split(';')[0]; self.csrf = json.loads(body)['csrf']

    def test_host_health_is_read_only_and_backups_are_owner_only(self):
        self.assertEqual(self.req('/desk/console/health')[0], 401)
        self.login(self.keys['owner'])
        code, health = self.req('/desk/console/health')
        self.assertEqual((code, health['paused'], health['vault']['notes'], health['host']['installedService']), (200, False, 20, False))
        self.assertEqual(health['lifecycle'], {'lastBackup': None, 'journalEntries': 0})
        self.assertEqual(self.req('/desk/pause', {'paused': True})[0], 200)
        self.assertTrue(self.req('/desk/console/health')[1]['paused'])
        self.login(self.keys['reader'])
        reader = self.req('/desk/console/health')[1]
        self.assertEqual((reader['paused'], reader['lifecycle'], reader['role']), (True, None, 'reader'))
        self.assertEqual(self.req('/desk/pause', {'paused': False})[0], 403)

    def projection(self):
        code, data = self.req('/desk/console/projection'); self.assertEqual(code, 200, data)
        return data

    def entity(self, identity, kind, name):
        self.assertEqual(self.req('/desk/memory/entities', {'id': identity, 'kind': kind, 'name': name})[0], 200)

    def claim(self, request, subject, predicate, note, line, obj=None, value=None, accept=True):
        body = {'request_id': request, 'subject_id': subject, 'predicate': predicate, 'object_id': obj, 'value': value,
                'valid_from': None, 'valid_until': None,
                'evidence': {'note_id': note['id'], 'sha256': note['sha256'], 'revision': note['revision'], 'start_line': line, 'end_line': line}}
        code, made = self.req('/desk/memory/proposals', body); self.assertEqual(code, 200, made)
        if accept:
            code, _ = self.req(f"/desk/memory/claims/{made['id']}/review", {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
            self.assertEqual(code, 200)
        return made['id']

    def note(self, title):
        return next(n for n in self.req('/desk/knowledge')[1]['nodes'] if n['title'] == title)

    def test_requires_session(self):
        for path in ('/desk/console/projection', '/desk/console/workspaces', '/desk/console/records/note:abc'):
            self.assertEqual(self.req(path)[0], 401)

    def test_projection_is_real_backend_data_not_fixtures(self):
        self.login(self.keys['owner']); p = self.projection()
        self.assertEqual((p['kind'], p['schemaVersion'], p['workspaceId']), ('authorised_projection', 1, 'demo-production'))
        notes = [n for n in p['nodes'] if n['origin'] == 'authored_note']
        self.assertEqual(len(notes), 20)
        self.assertEqual(p['counts']['notes'], 20)
        self.assertIn('Sample film', {n['label'] for n in notes})
        self.assertNotIn('Velvet Accademy', json.dumps(p))
        self.assertEqual(len([n for n in p['nodes'] if n['origin'] == 'source']), 1)
        refs = [e for e in p['edges'] if e['layer'] == 'note_reference']
        self.assertEqual(len(refs), len(self.req('/desk/knowledge')[1]['links']))
        ids = {n['id'] for n in p['nodes']}
        for e in p['edges']:
            self.assertIn(e['from'], ids); self.assertIn(e['to'], ids); self.assertTrue(e['evidence'])
        self.assertTrue(all(n['workspaceId'] == 'demo-production' for n in p['nodes']))
        self.assertEqual(p['executive']['priorities'], [])
        self.assertEqual(p['model'], {'configured': False, 'name': None, 'allowed': False, 'tools_enabled': False})
        self.assertFalse(p['authorityGranted'])
        film = next(n for n in notes if n['label'] == 'Sample film')
        self.assertEqual(film['category'], 'projects')
        self.assertTrue(film['summary'].startswith('The fictional production'))

    def test_workspaces_come_from_the_credential(self):
        self.login(self.keys['reader']); code, w = self.req('/desk/console/workspaces')
        self.assertEqual(code, 200)
        self.assertEqual(w['workspaces'], [{'id': 'demo-production', 'label': 'Demo production', 'role': 'reader', 'synthetic': True}])

    def test_other_workspace_is_excluded_from_records_counts_and_inspection(self):
        other_owner = self.store.provision('other-workspace', 'other-owner', 'owner', legacy_scope=True)
        other_source = self.store.provision('other-workspace', 'other-source', 'source', legacy_scope=True)
        vault = self.root / 'other-vault'; vault.mkdir()
        (vault / 'Hidden.md').write_text('# Zephyrmarker project\nBelongs to another workspace.\n')
        MarkdownVault(self.store, other_source, vault).scan()
        self.login(self.keys['owner']); p = self.projection()
        self.assertNotIn('Zephyrmarker', json.dumps(p)); self.assertEqual(p['counts']['notes'], 20)
        hidden = self.store.knowledge(other_owner)['nodes'][0]['id']
        self.assertEqual(self.req('/desk/console/records/note:' + hidden), (404, {'error': 'record_not_available'}))
        self.assertEqual(self.req('/desk/console/records/source:other-source')[0], 404)

    def test_ungranted_source_leaks_no_label_count_or_link_under_strict_policy(self):
        hidden_source = self.store.provision('demo-production', 'hidden-source', 'source', legacy_scope=True)
        vault = self.root / 'hidden-vault'; vault.mkdir()
        (vault / 'Secret.md').write_text('# Classifiedmarker\nUngranted synthetic record. [[Sample film]]\n')
        MarkdownVault(self.store, hidden_source, vault, label='Classified label').scan()
        self.login(self.keys['owner']); legacy = self.projection()
        self.assertIn('Classifiedmarker', json.dumps(legacy)); self.assertEqual(legacy['counts']['notes'], 21)
        policy = IdentityPolicy(self.store)
        policy.grant(self.keys['owner'], 'demo-source', 'read', self.store.now() + 3600, policy.view(self.keys['owner'])['epoch'])
        strict = self.projection(); text = json.dumps(strict)
        self.assertNotIn('Classifiedmarker', text); self.assertNotIn('Classified label', text); self.assertNotIn('hidden-source', text)
        self.assertEqual(strict['counts']['notes'], 20)
        self.assertNotEqual(strict['grantRevision'], legacy['grantRevision'])
        secret = next(n['id'] for n in legacy['nodes'] if n['label'] == 'Classifiedmarker')
        self.assertEqual(self.req('/desk/console/records/' + secret)[0], 404)

    def test_reviewed_layers_are_separate_from_authored_links(self):
        self.login(self.keys['owner'])
        self.entity('film', 'project', 'Sample film'); self.entity('producer', 'person', 'Sample producer')
        producer = self.note('Sample producer')
        self.claim('resp', 'film', 'responsible_person', producer, 8, obj='producer')
        self.claim('unreviewed', 'film', 'status', producer, 8, value='planning', accept=False)
        p = self.projection()
        reviewed = [e for e in p['edges'] if e['layer'] == 'reviewed_claim']
        self.assertEqual(len(reviewed), 1)
        self.assertEqual((reviewed[0]['from'], reviewed[0]['to'], reviewed[0]['relation']), ('entity:film', 'entity:producer', 'responsible_person'))
        self.assertEqual(reviewed[0]['evidence'][0]['basis'], 'human_review')
        support = [e for e in p['edges'] if e['layer'] == 'review_support']
        self.assertEqual([(e['from'], e['to']) for e in support], [('entity:film', 'note:' + producer['id'])])
        film = next(n for n in p['nodes'] if n['id'] == 'entity:film')
        self.assertEqual(film['statements']['usable'], 1); self.assertEqual(film['statements']['proposed'], 1)
        self.assertEqual(p['executive']['insights'][0]['entityId'], 'entity:film')
        detail = self.req('/desk/console/records/entity:film')[1]
        states = sorted((s['state'], s['usable']) for s in detail['statements'])
        self.assertEqual(states, [('accepted', True), ('proposed', False)])
        accepted = next(s for s in detail['statements'] if s['usable'])
        self.assertIn('Fictional responsibility', accepted['support']['quote'])

    def test_source_change_invalidates_review_and_changes_revision(self):
        self.login(self.keys['owner'])
        self.entity('film', 'project', 'Sample film'); self.entity('producer', 'person', 'Sample producer')
        producer = self.note('Sample producer')
        self.claim('resp', 'film', 'responsible_person', producer, 8, obj='producer')
        before = self.projection()
        path = self.home / 'vault' / 'people' / 'Sample Producer.md'
        path.write_text(path.read_text().replace('Fictional responsibility', 'Changed responsibility'))
        self.sup.cycle(); after = self.projection()
        self.assertNotEqual(after['dataRevision'], before['dataRevision'])
        self.assertEqual([e for e in after['edges'] if e['layer'] in ('reviewed_claim', 'review_support')], [])
        changed = next(n for n in after['nodes'] if n['id'] == 'note:' + producer['id'])
        self.assertEqual(changed['revision'], str(producer['revision'] + 1))
        statement = self.req('/desk/console/records/entity:film')[1]['statements'][0]
        self.assertEqual((statement['state'], statement['usable'], statement['support']), ('invalidated', False, None))

    def test_revoked_source_disappears_and_revoked_owner_is_signed_out(self):
        self.login(self.keys['owner']); before = self.projection()
        self.store.revoke('demo-source'); after = self.projection()
        self.assertEqual(after['counts']['notes'], 0); self.assertEqual(after['nodes'], [])
        self.assertNotEqual(after['grantRevision'], before['grantRevision'])
        self.store.revoke('demo-owner')
        self.assertEqual(self.req('/desk/console/projection')[0], 401)

    def test_same_name_entities_are_never_merged(self):
        self.login(self.keys['owner'])
        self.entity('producer-a', 'person', 'Sample producer'); self.entity('producer-b', 'person', 'Sample producer')
        p = self.projection()
        self.assertEqual(sorted(n['id'] for n in p['nodes'] if n['label'] == 'Sample producer' and n['origin'] == 'reviewed_entity'),
                         ['entity:producer-a', 'entity:producer-b'])
        self.assertEqual(self.req('/desk/console/records/entity:producer-a')[1]['sameNameEntities'], ['entity:producer-b'])

    def test_reader_does_not_see_owner_private_review_ledger(self):
        self.login(self.keys['owner']); self.entity('film', 'project', 'Sample film')
        self.login(self.keys['reader']); p = self.projection()
        self.assertEqual([n for n in p['nodes'] if n['origin'] == 'reviewed_entity'], [])
        self.assertEqual(self.req('/desk/console/records/entity:film')[0], 404)

    def test_note_inspection_returns_exact_lines(self):
        self.login(self.keys['owner']); film = self.note('Sample film')
        code, detail = self.req('/desk/console/records/note:' + film['id'])
        self.assertEqual(code, 200)
        self.assertEqual((detail['sha256'], detail['revision'], detail['path']), (film['sha256'], str(film['revision']), 'projects/Sample Film.md'))
        self.assertEqual(detail['lines'][5], '# Sample film')
        for bad in ('note:../x', 'note:' + 'g' * 24, 'claim:1', 'entity:', '', 'note:%2e%2e'):
            self.assertEqual(self.req('/desk/console/records/' + bad)[0], 404, bad)

    def test_query_cannot_widen_scope(self):
        self.login(self.keys['owner'])
        self.assertEqual(self.req('/desk/console/projection?scope=other-workspace')[0], 404)

    def test_pending_server_action_is_projected_for_approval_review(self):
        event = self.store.desk_state(self.keys['owner'])['events'][0]
        made = self.store.propose_from_evidence(self.keys['owner'], {'event_seq': event['seq'], 'text': 'Synthetic crew update.', 'request_id': 'console-draft'})
        self.login(self.keys['owner']); approval = self.projection()['approvals'][0]
        self.assertEqual((approval['id'], approval['state'], approval['text'], approval['fingerprint']),
                         ('console-draft', 'proposed', 'Synthetic crew update.', made['fingerprint']))
        self.assertTrue(approval['evidenceCurrent']); self.assertEqual(approval['effect'], 'local_draft_only_not_sent')

    def restricted_inbox_action(self):
        from alfred.inbox import propose
        policy = IdentityPolicy(self.store)
        for capability in ('read', 'inbox.write'):
            policy.grant(self.keys['owner'], 'demo-source', capability, self.store.now() + 3600,
                         policy.view(self.keys['owner'])['epoch'])
        return propose(self.store, self.keys['owner'], {
            'request_id': 'restricted-inbox', 'source': 'demo-source',
            'filename': 'Private-destination-marker.md', 'content': 'Private-draft-marker'})

    def test_restricted_approval_is_absent_for_another_person_in_same_workspace(self):
        action = self.restricted_inbox_action()
        peer = self.store.provision('demo-production', 'other-person', 'reader')
        self.login(self.keys['owner'])
        self.assertEqual(self.projection()['approvals'][0]['fingerprint'], action['fingerprint'])
        self.login(peer)
        projection = self.projection()
        self.assertEqual(projection['counts']['notes'], 0)
        self.assertEqual(projection['approvals'], [])
        state = self.req('/desk/state')[1]
        self.assertEqual(state['actions'], [])
        self.assertEqual(state['counts']['actions'], 0)
        for response in (projection, state):
            encoded = json.dumps(response)
            for marker in ('Private-draft-marker', 'Private-destination-marker', 'restricted-inbox',
                           action['fingerprint'], 'demo-source'):
                self.assertNotIn(marker, encoded)
        self.assertEqual(self.req('/desk/actions/restricted-inbox/approve',
                                  {'fingerprint': action['fingerprint']})[0], 403)

    def test_own_approval_is_withheld_after_source_read_revocation(self):
        action = self.restricted_inbox_action()
        self.login(self.keys['owner'])
        self.assertEqual(len(self.projection()['approvals']), 1)
        policy = IdentityPolicy(self.store)
        policy.grant(self.keys['owner'], 'demo-source', 'read', self.store.now() + 3600,
                     policy.view(self.keys['owner'])['epoch'], revoke=True)
        projection = self.projection()
        self.assertEqual(projection['approvals'], [])
        self.assertEqual(self.req('/desk/state')[1]['actions'], [])
        self.assertNotIn(action['fingerprint'], json.dumps(projection))

    def test_restricted_action_state_and_metadata_are_filtered(self):
        action = self.restricted_inbox_action()
        peer = self.store.provision('demo-production', 'state-reader', 'reader')
        self.login(peer)
        state = self.req('/desk/state')[1]
        self.assertEqual(state['actions'], [])
        self.assertEqual(state['events'], [])
        self.assertEqual(state['documents'], [])
        self.assertEqual(state['counts'], {'events': 0, 'actions': 0, 'drafts': 0})
        for marker in ('demo-source', action['id'], action['fingerprint'],
                       'Private-draft-marker', 'Private-destination-marker'):
            self.assertNotIn(marker, json.dumps(state))

    def test_read_grant_does_not_share_another_persons_approval(self):
        self.restricted_inbox_action()
        policy = IdentityPolicy(self.store)
        invitation = policy.invite(self.keys['owner'], 'demo-source', 'read', self.store.now() + 1800,
                                   policy.view(self.keys['owner'])['epoch'])
        policy.redeem(self.keys['reader'], invitation['code'])
        self.login(self.keys['reader'])
        self.assertEqual(self.projection()['counts']['notes'], 20)
        self.assertEqual(self.projection()['approvals'], [])


    def test_authority_change_during_assembly_returns_conflict_not_stale_data(self):
        self.login(self.keys['owner'])
        original = self.server.memory.view
        def racing(bearer):
            policy = IdentityPolicy(self.store)
            policy.grant(self.keys['owner'], 'demo-source', 'read', self.store.now() + 3600, policy.view(self.keys['owner'])['epoch'])
            return original(bearer)
        self.server.memory.view = racing
        self.assertEqual(self.req('/desk/console/projection'), (409, {'error': 'projection_authority_changed'}))

    def test_console_is_served_same_origin_with_connected_marker(self):
        r, body = self.raw('/console')
        self.assertEqual((r.status, r.getheader('Location')), (308, '/console/'))
        r, body = self.raw('/console/')
        self.assertEqual(r.status, 200)
        self.assertIn(b'content="connected"', body); self.assertNotIn(b'content="demo"', body)
        self.assertIn("script-src 'self'", r.getheader('Content-Security-Policy'))
        r, body = self.raw('/console/assets/index-abc.js')
        self.assertEqual((r.status, r.getheader('Content-Type')), (200, 'text/javascript; charset=utf-8'))
        for bad in ('/console/../outside.js', '/console/assets/../../outside.js', '/console/assets/x.map', '/console/index.html', '/console/assets/%2e%2e/outside.js'):
            self.assertEqual(self.raw(bad)[0].status, 404, bad)
        self.assertEqual(self.raw('/console/', headers={'Host': 'evil.example'})[0].status, 403)

    def test_missing_build_is_reported_honestly(self):
        self.server.console_dist = self.root / 'not-built'
        r, body = self.raw('/console/')
        self.assertEqual((r.status, json.loads(body)), (404, {'error': 'console_not_built'}))


if __name__ == '__main__':
    unittest.main()
