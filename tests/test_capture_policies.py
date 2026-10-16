"""Owner-authored automatic capture policies (MEM-004, M04, M10).

Synthetic vaults in temporary folders and real SQLite. Rules are deterministic text
matching; every match becomes a reviewed-memory proposal and nothing is accepted.
"""
from pathlib import Path
import http.client
import json
import tempfile
import threading
import unittest
from alfred.local import Fault
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor, MarkdownVault
from alfred.reviewed_memory import ReviewedMemory
from alfred.capture_policies import CapturePolicies, match_line, content_lines
from alfred import lifecycle

MEETING = '''---
title: Atlas weekly
---
# Atlas weekly
Decision: launch Atlas in the spring window
- [ ] 2026-10-20 send the Atlas budget to finance
- [x] 2026-10-01 book the review room
- Decision: hire one more designer
```
Decision: inside a code fence
```
Notes without a rule.
'''


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.clock = [1_000_000]
        self.store = KnowledgeStore(self.root / 'desk.sqlite', clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=2592000)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=2592000)
        self.source = self.store.provision('work', 'source', 'source', ttl=2592000)
        self.vault = self.root / 'vault'; (self.vault / 'Meetings').mkdir(parents=True)
        (self.vault / 'Meetings' / 'Atlas weekly.md').write_text(MEETING)
        (self.vault / 'Journal.md').write_text('# Journal\nDecision: a personal journal line\n')
        self.scanner = MarkdownVault(self.store, self.source, self.vault); self.scanner.scan()
        self.memory = ReviewedMemory(self.store)
        self.memory.create_entity(self.owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas'})
        self.capture = CapturePolicies(self.store, memory=self.memory)

    def policy(self, identity='decisions', **over):
        body = {'version': 0, 'name': 'Meeting decisions', 'enabled': True, 'context': 'company',
                'match': {'kind': 'line_prefix', 'prefix': 'Decision:'}, 'sources': ['source'],
                'path_prefix': 'Meetings/', 'daily_budget': 10,
                'proposes': {'subject_id': 'atlas', 'predicate': 'decision', 'memory_type': 'semantic', 'retention_days': None}}
        body.update(over)
        return self.capture.author(self.owner, identity, body)

    def commitments(self, **over):
        return self.policy('commitments', **{'name': 'Dated commitments', 'match': {'kind': 'dated_line', 'keyword': None},
                           'proposes': {'subject_id': 'atlas', 'predicate': 'scheduled_for', 'memory_type': 'commitment',
                                        'retention_days': 30}, **over})

    def claims(self):
        return self.memory.view(self.owner)['claims']

    def counts(self, identity='decisions'):
        return next(p for p in self.capture.view(self.owner)['policies'] if p['id'] == identity)['counts']

    def edit(self, text):
        (self.vault / 'Meetings' / 'Atlas weekly.md').write_text(text); self.clock[0] += 5; self.scanner.scan()


class MatchingTests(unittest.TestCase):
    def test_prefix_rule_is_case_insensitive_and_strips_bullets_and_anchors(self):
        rule = {'kind': 'line_prefix', 'prefix': 'Decision:'}
        self.assertEqual(match_line(rule, '- decision: ship it ^abc-1'), 'ship it')
        self.assertEqual(match_line(rule, '  1. Decision:  keep scope  '), 'keep scope')
        self.assertIsNone(match_line(rule, 'We made no Decision: here'))
        self.assertIsNone(match_line(rule, 'Decision:'))

    def test_dated_rule_normalises_date_first_and_skips_ticked_and_invalid_dates(self):
        rule = {'kind': 'dated_line', 'keyword': None}
        self.assertEqual(match_line(rule, '- [ ] Send budget by 2026-10-20 14:30 to finance'), '2026-10-20 14:30 Send budget by to finance')
        self.assertEqual(match_line(rule, '2026-10-20: call Sam'), '2026-10-20 call Sam')
        self.assertIsNone(match_line(rule, '- [x] 2026-10-20 done already'))
        self.assertIsNone(match_line(rule, '2026-02-30 not a day'))
        self.assertIsNone(match_line(rule, 'no date here'))
        self.assertIsNone(match_line(rule, '2026-10-20'))

    def test_dated_rule_keyword_is_a_whole_word(self):
        rule = {'kind': 'dated_line', 'keyword': 'owe'}
        self.assertIsNotNone(match_line(rule, 'I owe Sam the deck 2026-10-20'))
        self.assertIsNone(match_line(rule, 'Owen sends the deck 2026-10-20'))

    def test_frontmatter_and_fenced_code_are_not_read(self):
        lines = dict(content_lines(MEETING))
        self.assertNotIn(2, lines); self.assertNotIn(10, lines)
        self.assertEqual(lines[5], 'Decision: launch Atlas in the spring window')


class AuthoringTests(Base):
    def test_owner_authors_a_versioned_inspectable_policy(self):
        view = self.policy()
        p = view['policies'][0]
        self.assertEqual((p['version'], p['enabled'], p['context'], p['sources']), (1, True, 'company', ['source']))
        self.assertIn('A line starting "Decision:"', p['description'])
        self.assertIn('Nothing is accepted automatically', p['description'])
        self.assertFalse(view['model_used']); self.assertFalse(view['auto_accept'])
        updated = self.policy(version=1, enabled=False)['policies'][0]
        self.assertEqual((updated['version'], updated['enabled']), (2, False))
        with self.store.connection() as db:
            audit = [r['kind'] for r in db.execute("SELECT kind FROM audit WHERE kind LIKE 'capture.%' ORDER BY rowid")]
        self.assertEqual(audit, ['capture.policy_created', 'capture.policy_updated'])

    def test_stale_version_is_refused(self):
        self.policy()
        with self.assertRaises(Fault) as caught:
            self.policy(version=0)
        self.assertEqual((caught.exception.code, caught.exception.status), ('capture_policy_changed', 409))

    def test_reader_cannot_author_run_or_read(self):
        self.policy()
        for call in (lambda: self.capture.author(self.reader, 'x', {}), lambda: self.capture.run(self.reader),
                     lambda: self.capture.view(self.reader)):
            with self.assertRaises(Fault) as caught:
                call()
            self.assertIn(caught.exception.code, ('forbidden', 'invalid_fields'))
        with self.assertRaises(Fault) as caught:
            self.capture.view(self.reader)
        self.assertEqual(caught.exception.status, 403)

    def test_invalid_policies_are_rejected(self):
        bad = [{'context': 'team'}, {'match': {'kind': 'regex', 'pattern': '.*'}}, {'match': {'kind': 'line_prefix', 'prefix': ' x'}},
               {'sources': []}, {'sources': ['source', 'source']}, {'path_prefix': '../x'}, {'path_prefix': '/abs'},
               {'daily_budget': 0}, {'daily_budget': 51}, {'enabled': 'yes'},
               {'proposes': {'subject_id': 'atlas', 'predicate': 'depends_on', 'memory_type': 'semantic', 'retention_days': None}},
               {'proposes': {'subject_id': 'atlas', 'predicate': 'decision', 'memory_type': 'fact', 'retention_days': None}}]
        for over in bad:
            with self.assertRaises(Fault, msg=over):
                self.policy(**over)
        with self.assertRaises(Fault) as caught:
            self.policy(sources=['elsewhere'])
        self.assertEqual(caught.exception.code, 'capture_source_unknown')
        with self.assertRaises(Fault) as caught:
            self.policy(proposes={'subject_id': 'nobody', 'predicate': 'decision', 'memory_type': 'semantic', 'retention_days': None})
        self.assertEqual(caught.exception.code, 'memory_entity_not_found')
        self.assertEqual(self.capture.view(self.owner)['policies'], [])


class RunTests(Base):
    def test_matches_become_bound_proposals_and_nothing_is_accepted(self):
        self.policy()
        result = self.capture.run(self.owner)
        self.assertEqual(len(result['proposed']), 2); self.assertEqual(result['auto_accepted'], 0)
        claims = sorted(self.claims(), key=lambda c: c['source']['start_line'])
        self.assertEqual([c['state'] for c in claims], ['proposed', 'proposed'])
        self.assertFalse(any(c['usable'] for c in claims))
        self.assertEqual([c['value'] for c in claims], ['launch Atlas in the spring window', 'hire one more designer'])
        self.assertEqual([c['source']['start_line'] for c in claims], [5, 8])
        note = next(n for n in self.store.knowledge(self.owner)['nodes'] if n['path'] == 'Meetings/Atlas weekly.md')
        self.assertTrue(all((c['source']['sha256'], c['source']['revision']) == (note['sha256'], note['revision']) for c in claims))
        self.assertTrue(all(c['memory_type'] == 'semantic' for c in claims))
        # The journal line is outside the policy's folder.
        self.assertNotIn('a personal journal line', [c['value'] for c in claims])
        self.assertEqual(self.counts()['open'], 2)

    def test_dated_commitments_propose_scheduled_commitment_statements(self):
        self.commitments()
        self.capture.run(self.owner)
        [claim] = self.claims()
        self.assertEqual((claim['predicate'], claim['value'], claim['memory_type']),
                         ('scheduled_for', '2026-10-20 send the Atlas budget to finance', 'commitment'))
        self.assertEqual(claim['retention_until'], self.clock[0] + 30 * 86400)

    def test_rescan_does_not_repropose(self):
        self.policy(); self.capture.run(self.owner)
        self.scanner.scan(); again = self.capture.run(self.owner)
        self.assertEqual(again['proposed'], []); self.assertEqual(again['not_proposed']['already_proposed'], 2)
        self.assertEqual(len(self.claims()), 2)

    def test_dismissed_is_not_reoffered_until_the_line_changes(self):
        self.policy(); self.capture.run(self.owner)
        first = next(c for c in self.claims() if c['source']['start_line'] == 5)
        self.memory.review(self.owner, first['id'], {'version': first['version'], 'decision': 'withdraw', 'replaces_id': None, 'replaces_version': None})
        # Moving the line (new revision) invalidates both proposals; the dismissed text stays dismissed.
        self.edit('\n' + MEETING)
        result = self.capture.run(self.owner)
        self.assertEqual(result['not_proposed']['dismissed'], 1)
        self.assertEqual([p['line'] for p in result['proposed']], [9])
        self.assertEqual(self.counts()['dismissed'], 1)
        # Changing the dismissed line's text offers it again.
        self.edit(MEETING.replace('spring window', 'summer window'))
        result = self.capture.run(self.owner)
        values = [c['value'] for c in self.claims() if c['state'] == 'proposed']
        self.assertIn('launch Atlas in the summer window', values)

    def test_accept_counts_and_review_is_the_only_way_to_accept(self):
        self.policy(); self.capture.run(self.owner)
        claim = self.claims()[0]
        self.memory.review(self.owner, claim['id'], {'version': claim['version'], 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        counts = self.counts()
        self.assertEqual((counts['proposed'], counts['accepted'], counts['open'], counts['dismissed']), (2, 1, 1, 0))

    def test_forgotten_proposal_is_never_reoffered(self):
        self.policy(); self.capture.run(self.owner)
        claim = self.claims()[0]
        self.memory.forget(self.owner, claim['id'], {'version': claim['version']})
        result = self.capture.run(self.owner)
        self.assertEqual(result['not_proposed']['forgotten'], 1)
        self.assertEqual(self.counts()['forgotten'], 1)

    def test_rule_budget_counts_excess_without_proposing(self):
        self.policy(daily_budget=1)
        result = self.capture.run(self.owner)
        self.assertEqual(len(result['proposed']), 1); self.assertEqual(result['not_proposed']['rule_budget'], 1)
        self.capture.run(self.owner)
        counts = self.counts()
        self.assertEqual((counts['proposed_today'], counts['deferred_today']), (1, 1))
        self.assertEqual(len(self.claims()), 1)
        # The next day's budget proposes the held line.
        self.clock[0] += 86400
        self.assertEqual(len(self.capture.run(self.owner)['proposed']), 1)
        self.assertEqual(len(self.claims()), 2)

    def test_overall_daily_budget_spans_policies(self):
        self.policy(); self.commitments()
        self.capture.configure(self.owner, {'version': 0, 'daily_budget': 2})
        result = self.capture.run(self.owner)
        self.assertEqual(len(result['proposed']), 2); self.assertEqual(result['not_proposed']['daily_budget'], 1)
        view = self.capture.view(self.owner)
        self.assertEqual((view['today']['proposed'], view['today']['deferred']['daily_budget']), (2, 1))
        self.assertEqual(view['last_run']['proposed'], 2)
        with self.assertRaises(Fault):
            self.capture.configure(self.owner, {'version': 0, 'daily_budget': 3})

    def test_disabled_policy_proposes_nothing(self):
        self.policy(enabled=False)
        self.assertEqual(self.capture.run(self.owner)['proposed'], [])
        self.assertEqual(self.claims(), [])

    def test_forgotten_subject_proposes_nothing(self):
        self.policy()
        self.memory.forget_entity(self.owner, 'atlas', {})
        result = self.capture.run(self.owner)
        self.assertEqual((result['proposed'], result['not_proposed']['subject_unavailable']), ([], 2))

    def test_revoked_read_grant_proposes_nothing(self):
        from alfred.policy import IdentityPolicy
        identity = IdentityPolicy(self.store)
        identity.grant(self.owner, 'source', 'read', self.clock[0] + 5000, identity.view(self.owner)['epoch'])
        identity.grant(self.owner, 'source', 'read', self.clock[0] + 5000, identity.view(self.owner)['epoch'], revoke=True)
        self.policy()
        self.assertEqual(self.capture.run(self.owner)['proposed'], [])
        self.assertEqual(self.claims(), [])

    def test_supervisor_cycle_runs_only_on_change(self):
        class Sup:
            scope = 'work'
        sup = Sup(); sup.owner = self.owner
        capture = CapturePolicies(self.store, sup, self.memory)
        self.assertIsNone(capture.cycle())
        self.policy()
        self.assertEqual(len(capture.cycle()['proposed']), 2)
        self.assertIsNone(capture.cycle())
        self.edit(MEETING + 'Decision: one more\n')
        self.assertEqual(len(capture.cycle()['proposed']), 3)
        self.store.set_paused(self.owner, True)
        self.edit(MEETING + 'Decision: while paused\n')
        self.assertIsNone(capture.cycle())


class ScopeTests(Base):
    def test_workspaces_and_owners_are_separate(self):
        home_owner = self.store.provision('home', 'home-owner', 'owner', ttl=2592000)
        home_source = self.store.provision('home', 'home-source', 'source', ttl=2592000)
        other = self.root / 'home'; other.mkdir(); (other / 'Plans.md').write_text('Decision: a private home decision\n')
        MarkdownVault(self.store, home_source, other).scan()
        self.memory.create_entity(home_owner, {'id': 'house', 'kind': 'project', 'name': 'House'})
        self.policy()
        # The home owner sees none of the work policies, and cannot name the work vault.
        self.assertEqual(self.capture.view(home_owner)['policies'], [])
        body = {'version': 0, 'name': 'Home decisions', 'enabled': True, 'context': 'personal',
                'match': {'kind': 'line_prefix', 'prefix': 'Decision:'}, 'sources': ['source'], 'path_prefix': None,
                'daily_budget': 10, 'proposes': {'subject_id': 'house', 'predicate': 'decision', 'memory_type': 'semantic', 'retention_days': None}}
        with self.assertRaises(Fault) as caught:
            self.capture.author(home_owner, 'home', body)
        self.assertEqual(caught.exception.code, 'capture_source_unknown')
        self.capture.author(home_owner, 'home', {**body, 'sources': ['home-source']})
        self.capture.run(self.owner); self.capture.run(home_owner)
        work_values = {c['value'] for c in self.claims()}
        home_values = {c['value'] for c in self.memory.view(home_owner)['claims']}
        self.assertEqual(home_values, {'a private home decision'})
        self.assertNotIn('a private home decision', work_values)
        self.assertEqual(len(self.capture.view(self.owner)['policies']), 1)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        from alfred.desk import init_demo
        from alfred.desk_http import DeskHTTPServer
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'demo'; self.keys = init_demo(self.home)
        (self.home / 'vault' / 'Capture test.md').write_text('# Capture test\nDecision: use the synthetic plan\n')
        self.store = KnowledgeStore(self.home / 'desk.sqlite')
        self.sup = KnowledgeSupervisor(self.store, self.keys['owner'], self.keys['source'], self.home / 'project', vault=self.home / 'vault')
        self.sup.cycle()
        self.server = DeskHTTPServer(self.store, self.sup, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close); self.cookie = self.csrf = None

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)

    def req(self, path, data=None, csrf=True):
        headers = {'Cookie': self.cookie} if self.cookie else {}
        if data is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': self.server.origin})
            if csrf and self.csrf: headers['X-CSRF-Token'] = self.csrf
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); raw = r.read(); cookie = r.getheader('Set-Cookie'); c.close()
        return r.status, json.loads(raw), cookie

    def login(self, role='owner'):
        code, data, cookie = self.req('/desk/login', {'key': self.keys[role]})
        self.assertEqual(code, 200); self.cookie = cookie.split(';')[0]; self.csrf = data['csrf']

    def body(self, **over):
        value = {'version': 0, 'name': 'Decisions', 'enabled': True, 'context': 'personal',
                 'match': {'kind': 'line_prefix', 'prefix': 'Decision:'}, 'sources': ['demo-source'], 'path_prefix': None,
                 'daily_budget': 5, 'proposes': {'subject_id': 'plan', 'predicate': 'decision', 'memory_type': 'semantic', 'retention_days': None}}
        value.update(over); return value

    def test_http_round_trip_with_csrf_and_versions(self):
        self.assertEqual(self.req('/desk/capture')[0], 401)
        self.login()
        self.assertEqual(self.req('/desk/memory/entities', {'id': 'plan', 'kind': 'project', 'name': 'Plan'})[0], 200)
        self.assertEqual(self.req('/desk/capture/policies/decisions', self.body(), csrf=False)[0], 403)
        code, view, _ = self.req('/desk/capture/policies/decisions', self.body())
        self.assertEqual(code, 200, view); self.assertEqual(view['policies'][0]['version'], 1)
        self.assertEqual(self.req('/desk/capture/policies/decisions', self.body())[0], 409)
        self.assertEqual(self.req('/desk/capture?x=1')[0], 404)
        code, result, _ = self.req('/desk/capture/run', {})
        self.assertEqual(code, 200)
        self.assertIn('use the synthetic plan', [c['value'] for c in self.req('/desk/memory')[1]['claims']])
        self.assertTrue(all(c['state'] == 'proposed' for c in self.req('/desk/memory')[1]['claims']))
        view = self.req('/desk/capture')[1]
        self.assertGreaterEqual(view['policies'][0]['counts']['open'], 1)
        self.assertEqual(self.req('/desk/capture/settings', {'version': 0, 'daily_budget': 3})[0], 200)

    def test_reader_is_refused(self):
        self.login('reader')
        self.assertEqual(self.req('/desk/capture')[0], 403)
        self.assertEqual(self.req('/desk/capture/run', {})[0], 403)

    def test_supervisor_cycle_is_wired(self):
        self.login()
        self.req('/desk/memory/entities', {'id': 'plan', 'kind': 'project', 'name': 'Plan'})
        self.req('/desk/capture/policies/decisions', self.body())
        self.sup.cycle()
        values = [c['value'] for c in self.req('/desk/memory')[1]['claims']]
        self.assertIn('use the synthetic plan', values)


if __name__ == '__main__':
    unittest.main()
