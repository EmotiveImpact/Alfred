"""M10 authorised routines on synthetic data (ATT-001, MEM-004).

Real SQLite, a fictional vault, the real supervisor cycle, the real approval ledger and
real HTTP where the boundary matters. Routines read commitments and nominate; the person
decides. Nothing is delivered outside the app, and nothing becomes an obligation or an
approved action without the person's explicit request.
"""
from pathlib import Path
import http.client
import json
import tempfile
import threading
import unittest
from alfred.local import Fault
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.reviewed_memory import ReviewedMemory
from alfred.executive import ExecutiveRecords
from alfred.policy import IdentityPolicy
from alfred.routines import Routines, next_slot, quiet_until, scheduled_time

DAY, HOUR = 86400, 3600
T = 1_900_000_000  # 2030-03-17 17:46:40 UTC
ATLAS = ('---\ntitle: Atlas\ntype: project\n---\n# Atlas\n\n'
         'Launch review 2030-03-17.\nCrew call 2030-03-18 09:00.\nLaunch window in spring.\nBudget review 2030-03-25.\n')


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.clock = [T]
        self.store = KnowledgeStore(self.root / 'desk.sqlite', clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=2592000)
        self.other = self.store.provision('work', 'owner-two', 'owner', ttl=2592000)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=2592000)
        self.source = self.store.provision('work', 'source', 'source', ttl=2592000)
        (self.root / 'project').mkdir()
        self.vault = self.root / 'vault'; self.vault.mkdir()
        (self.vault / 'Atlas.md').write_text(ATLAS)
        self.sup = KnowledgeSupervisor(self.store, self.owner, self.source, self.root / 'project', vault=self.vault)
        self.sup.vault.scan()
        self.routines = Routines(self.store, self.sup); self.sup.routines = self.routines
        self.memory, self.records = ReviewedMemory(self.store), ExecutiveRecords(self.store)
        self.memory.create_entity(self.owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas'})
        self.seq = 0

    # Helpers --------------------------------------------------------------------

    def fault(self, code, call, *args):
        with self.assertRaises(Fault) as caught:
            call(*args)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def body(self, **over):
        value = {'version': 0, 'enabled': True, 'schedule': {'every_hours': 1}, 'utc_offset_minutes': 0, 'runs_per_day': 24,
                 'nominations_per_run': 10, 'quiet_hours': None, 'interrupt': 'show_now', 'propose_drafts': False}
        value.update(over)
        return value

    def routine(self, kind='commitment-review'):
        return next(r for r in self.routines.view(self.owner)['routines'] if r['kind'] == kind)

    def configure(self, kind='commitment-review', **over):
        return self.routines.configure(self.owner, kind, self.body(version=self.routine(kind)['version'], **over))

    def run_now(self, kind='commitment-review', bearer=None):
        self.seq += 1
        return self.routines.manual(bearer or self.owner, kind, {'request_id': f'run-{self.seq}'})

    def record(self, kind='commitment', title='Book the grade', due=None, **over):
        self.seq += 1
        body = {'request_id': f'r{self.seq}', 'kind': kind, 'title': title, 'detail': '', 'project': 'entity:atlas',
                'due': due, 'rank': None, 'support': None}
        body.update(over)
        return self.records.create(self.owner, body)

    def note(self, title='Atlas'):
        return next(n for n in self.store.knowledge(self.owner)['nodes'] if n['title'] == title)

    def statement(self, line, value, memory_type='commitment', predicate='scheduled_for', accept=True, title='Atlas', subject='atlas'):
        self.seq += 1
        n = self.note(title)
        if subject != 'atlas':
            # Separate subjects: one subject's single-valued 'scheduled for' statements would conflict.
            self.memory.create_entity(self.owner, {'id': subject, 'kind': 'commitment', 'name': subject.replace('-', ' ').capitalize()})
        made = self.memory.capture(self.owner, {'request_id': f'c{self.seq}', 'subject_id': subject, 'predicate': predicate,
                                                'object_id': None, 'value': value, 'valid_from': None, 'valid_until': None,
                                                'evidence': {'note_id': n['id'], 'sha256': n['sha256'], 'revision': n['revision'],
                                                             'start_line': line, 'end_line': line},
                                                'memory_type': memory_type, 'retention_days': None, 'captured_from': {}})
        if accept:
            self.memory.review(self.owner, made['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        return made['id']

    def nominations(self, bearer=None):
        return self.routines.view(bearer or self.owner)['nominations']

    def open_nominations(self):
        return [n for n in self.nominations() if n['state'] == 'open']

    def runs(self):
        return self.routines.view(self.owner)['runs']

    def count(self, table, where='1=1'):
        with self.store.connection() as db:
            return db.execute(f'SELECT count(*) FROM {table} WHERE {where}').fetchone()[0]


class SettingsTests(Base):
    def test_nothing_is_configured_or_run_until_the_person_enables_it(self):
        view = self.routines.view(self.owner)
        self.assertEqual([(r['kind'], r['configured'], r['enabled']) for r in view['routines']],
                         [('commitment-review', False, False), ('morning-brief', False, False)])
        self.record(due=T - HOUR)
        self.clock[0] += 3 * DAY; self.sup.cycle()
        self.assertEqual((self.runs(), self.nominations()), ([], []))
        self.assertEqual((view['delivery'], view['external_effects'], view['model_used']), ('in_app_only', False, False))

    def test_only_allowlisted_kinds_exist(self):
        for kind in ('shell', 'memory-health', 'send-email', ''):
            self.fault('unknown_routine', self.routines.configure, self.owner, kind, self.body())
            self.fault('unknown_routine', self.routines.manual, self.owner, kind, {'request_id': 'x'})

    def test_settings_are_validated_exactly(self):
        bad = [({'command': 'rm -rf'}, 'invalid_fields'), ({'schedule': {'every_hours': 3}}, 'invalid_routine_schedule'),
               ({'schedule': {'every_hours': True}}, 'invalid_routine_schedule'), ({'schedule': {'cron': '* * * * *'}}, 'invalid_routine_schedule'),
               ({'schedule': {'daily_at': '25:00'}}, 'invalid_routine_schedule'), ({'schedule': {'daily_at': '7:30'}}, 'invalid_routine_schedule'),
               ({'utc_offset_minutes': 7}, 'invalid_utc_offset'), ({'utc_offset_minutes': 900}, 'invalid_utc_offset'),
               ({'runs_per_day': 0}, 'invalid_run_budget'), ({'runs_per_day': 25}, 'invalid_run_budget'),
               ({'nominations_per_run': 0}, 'invalid_nomination_budget'), ({'nominations_per_run': 11}, 'invalid_nomination_budget'),
               ({'quiet_hours': {'start': '22:00', 'end': '22:00'}}, 'invalid_quiet_hours'),
               ({'quiet_hours': {'start': '22:00'}}, 'invalid_quiet_hours'), ({'interrupt': 'push_notification'}, 'invalid_interrupt'),
               ({'enabled': 'yes'}, 'invalid_routine_configuration'), ({'version': -1}, 'invalid_version')]
        for over, code in bad:
            body = self.body(**over)
            if 'command' in over:
                body = {**self.body(), **over}
            self.fault(code, self.routines.configure, self.owner, 'commitment-review', body)
        self.fault('interrupt_not_applicable', self.routines.configure, self.owner, 'morning-brief', self.body(interrupt='hold_for_brief'))
        self.fault('drafts_not_applicable', self.routines.configure, self.owner, 'morning-brief', self.body(propose_drafts=True))
        self.assertFalse(self.routine()['configured'])

    def test_changes_are_version_checked(self):
        self.configure()
        self.fault('routine_changed', self.routines.configure, self.owner, 'commitment-review', self.body(version=0))
        self.fault('routine_changed', self.routines.pause, self.owner, 'commitment-review', {'version': 7, 'paused': True})
        self.fault('routine_not_configured', self.routines.pause, self.owner, 'morning-brief', {'version': 0, 'paused': True})
        self.assertEqual(self.configure(runs_per_day=3)['routines'][0]['settings']['runs_per_day'], 3)

    def test_only_the_hosted_owner_authors_routines(self):
        self.fault('forbidden', self.routines.configure, self.reader, 'commitment-review', self.body())
        self.fault('routine_owner_not_hosted', self.routines.configure, self.other, 'commitment-review', self.body())
        self.fault('routine_owner_not_hosted', self.routines.manual, self.other, 'commitment-review', {'request_id': 'x'})
        self.fault('forbidden', self.routines.view, self.source)
        self.configure(); self.record(due=T - HOUR); self.run_now()
        for bearer, reason in ((self.reader, 'owner_only'), (self.other, 'not_hosted')):
            view = self.routines.view(bearer)
            self.assertEqual((view['available'], view['reason'], view['routines'], view['runs'], view['nominations']), (False, reason, [], [], []))
            self.assertNotIn('Book the grade', json.dumps(view))

    def test_schedules_follow_the_chosen_local_time(self):
        settings = {'schedule': {'every_hours': 4}, 'utc_offset_minutes': 60, 'quiet_hours': None}
        # 18:46 local: the next four-hour boundary is 20:00 local, 19:00 UTC.
        self.assertEqual(next_slot(settings, T), T - 46 * 60 - 40 + 2 * HOUR)
        daily = {'schedule': {'daily_at': '07:30'}, 'utc_offset_minutes': -300}
        slot = next_slot(daily, T)
        self.assertEqual((slot + -300 * 60) % DAY, 7 * HOUR + 30 * 60)
        self.assertTrue(T < slot <= T + DAY)
        self.assertEqual(next_slot(daily, slot), slot + DAY)
        quiet = {'utc_offset_minutes': 0, 'quiet_hours': {'start': '17:00', 'end': '07:00'}}
        self.assertEqual(quiet_until(quiet, T), T - (T % DAY) + DAY + 7 * HOUR)
        self.assertIsNone(quiet_until({'utc_offset_minutes': 0, 'quiet_hours': {'start': '07:00', 'end': '17:00'}}, T))
        self.assertEqual(scheduled_time('2030-03-17', 0), T - (T % DAY) + 17 * HOUR)
        self.assertEqual(scheduled_time('2030-03-18 09:00', 60), T - (T % DAY) + DAY + 8 * HOUR)
        for value in ('spring', 'by 2030-03-17', '2030-02-30', '2030-03-17T25:00', '2030-03-171'):
            self.assertIsNone(scheduled_time(value, 0), value)


class RunTests(Base):
    def test_commitment_review_nominates_due_and_overdue_items_with_cited_reasons(self):
        overdue = self.record(title='Book the grade', due=T - HOUR)
        soon = self.record('follow_up', 'Send the crew update', due=T + 3 * HOUR)
        self.record(title='Later', due=T + 3 * DAY)
        done = self.record(title='Finished', due=T - DAY)
        self.records.update(self.owner, done['id'], {'version': 1, 'status': 'done'})
        self.record('decision', 'Choose the opening', due=T - DAY)
        snoozed = self.record(title='Snoozed', due=T - DAY)
        self.records.update(self.owner, snoozed['id'], {'version': 1, 'snoozed_until': T + DAY})
        dated = self.statement(7, '2030-03-17', subject='launch-review')
        self.statement(9, 'spring', subject='launch-window')
        self.statement(10, '2030-03-17', memory_type='episodic', subject='budget-review')
        self.statement(8, '2030-03-18 09:00', accept=False, subject='crew-call')
        self.configure()
        run = self.run_now()
        self.assertEqual(run['status'], 'completed')
        outcome = run['outcome']
        self.assertEqual(outcome['read'], {'executive_records': 4, 'commitment_statements': 2, 'undated_statements': 1,
                                           'statements_not_usable': 1})
        self.assertEqual(outcome['not_nominated']['snoozed'], 1)
        nominated = {(n['cite']['id'], n['rule']) for n in outcome['nominated']}
        self.assertEqual(nominated, {(overdue['id'], 'overdue'), (soon['id'], 'due_within_a_day'), (dated, 'overdue')})
        self.assertEqual(outcome['budget'], {'runs_today': 1, 'runs_per_day': 24, 'nominations_per_run': 10})
        self.assertEqual((outcome['model_used'], outcome['external_effects'], outcome['delivery']), (False, False, 'in_app_only'))
        view = {n['cite']['id']: n for n in self.nominations()}
        self.assertEqual(view[overdue['id']]['reason'], 'Your open commitment is past its due time.')
        self.assertEqual(view[soon['id']]['reason'], 'Your open follow-up is due within a day.')
        self.assertEqual((view[dated]['cite']['source']['start_line'], view[dated]['cite']['subject']['name']), (7, 'Launch review'))
        self.assertEqual((view[overdue['id']]['cite']['version'], view[overdue['id']]['cite']['state']), (1, 'current'))
        self.assertTrue(all(n['surfaced'] and n['kind'] == 'reminder' and not n['external_delivery'] for n in view.values()))
        # Nominating is not an obligation: no executive record, statement or action was created or changed.
        self.assertEqual((self.count('executive_records'), self.count('actions')), (6, 0))
        self.assertEqual(self.count('memory_claims', "state='accepted'"), 3)

    def test_a_commitment_version_is_nominated_once(self):
        made = self.record(due=T - HOUR); self.configure()
        self.run_now()
        again = self.run_now()['outcome']
        self.assertEqual((again['nominated'], again['not_nominated']['already_nominated']), ([], 1))
        self.records.update(self.owner, made['id'], {'version': 1, 'title': 'Book the grade suite'})
        renewed = self.run_now()['outcome']['nominated']
        self.assertEqual([(n['cite']['id'], n['cite']['version']) for n in renewed], [(made['id'], 2)])

    def test_nomination_budget_per_run(self):
        for hours in (1, 2, 3):
            self.record(title=f'Item {hours}', due=T - hours * HOUR)
        self.configure(nominations_per_run=1)
        first = self.run_now()['outcome']
        self.assertEqual((len(first['nominated']), first['not_nominated']['nomination_budget']), (1, 2))
        # Most overdue first.
        self.assertEqual(self.nominations()[0]['cite']['title'], 'Item 3')
        self.assertEqual(len(self.run_now()['outcome']['nominated']), 1)

    def test_run_budget_per_local_day(self):
        self.configure(runs_per_day=2, utc_offset_minutes=60)
        self.assertEqual([self.run_now()['status'] for _ in range(3)], ['completed', 'completed', 'skipped'])
        skipped = self.runs()[0]
        self.assertEqual((skipped['skipped_reason'], skipped['outcome']['budget']['runs_today']), ('budget_exhausted', 2))
        # 18:46 local now: the budget resets at local midnight, 23:00 UTC.
        self.clock[0] = T - T % DAY + 23 * HOUR - 1
        self.assertEqual(self.run_now()['skipped_reason'], 'budget_exhausted')
        self.clock[0] += 2
        self.assertEqual(self.run_now()['status'], 'completed')

    def test_schedule_runs_each_due_slot_once_without_a_catch_up_storm(self):
        self.record(due=T - HOUR); self.configure()
        due = self.routine()['next_due']
        self.clock[0] = due - 1; self.sup.cycle()
        self.assertEqual(self.runs(), [])
        self.clock[0] = due + 10 * HOUR
        for _ in range(4):
            self.sup.cycle()
        runs = self.runs()
        self.assertEqual([(r['trigger'], r['status'], r['outcome']['missed_slots']) for r in runs], [('scheduled', 'completed', 10)])
        self.assertGreater(self.routine()['next_due'], self.clock[0])

    def test_per_routine_pause_records_skipped_slots(self):
        self.record(due=T - HOUR); self.configure()
        self.routines.pause(self.owner, 'commitment-review', {'version': self.routine()['version'], 'paused': True})
        self.clock[0] = self.routine()['next_due']; self.sup.cycle()
        self.assertEqual(self.run_now()['skipped_reason'], 'paused')
        self.assertEqual([r['skipped_reason'] for r in self.runs()], ['paused', 'paused'])
        self.assertEqual(self.nominations(), [])
        self.routines.pause(self.owner, 'commitment-review', {'version': self.routine()['version'], 'paused': False})
        self.clock[0] = self.routine()['next_due']; self.sup.cycle()
        self.assertEqual((self.runs()[0]['status'], len(self.nominations())), ('completed', 1))

    def test_workspace_pause_also_stops_routines(self):
        self.record(due=T - HOUR); self.configure()
        self.sup.set_paused(self.owner, True)
        self.clock[0] = self.routine()['next_due']; self.sup.cycle()
        self.assertEqual(self.run_now()['skipped_reason'], 'workspace_paused')
        self.assertEqual([r['skipped_reason'] for r in self.runs()], ['workspace_paused', 'workspace_paused'])
        self.assertEqual(self.nominations(), [])
        self.assertTrue(self.routines.view(self.owner)['workspace_paused'])

    def test_revocation_stops_runs(self):
        self.record(due=T - HOUR); self.configure()
        self.store.revoke('owner')
        self.clock[0] = self.routine_row('next_due'); self.sup.cycle()
        with self.store.connection() as db:
            rows = db.execute('SELECT status,skipped_reason FROM routine_runs').fetchall()
        self.assertEqual([tuple(r) for r in rows], [('skipped', 'authority_lost')])
        self.assertEqual(self.count('routine_nominations'), 0)
        self.fault('unauthorised', self.routines.manual, self.owner, 'commitment-review', {'request_id': 'after'})

    def routine_row(self, column):
        with self.store.connection() as db:
            return db.execute(f"SELECT {column} FROM routine_settings WHERE kind='commitment-review'").fetchone()[0]

    def test_grants_are_rechecked_at_run_time(self):
        self.record(due=T - HOUR)
        dated = self.statement(7, '2030-03-17')
        self.configure()
        policy = IdentityPolicy(self.store)
        policy.enable(self.owner, policy.view(self.owner)['epoch'])
        outcome = self.run_now()['outcome']
        self.assertEqual((outcome['read']['commitment_statements'], outcome['read']['statements_not_usable']), (0, 1))
        self.assertNotIn(dated, json.dumps(outcome))
        policy.grant(self.owner, 'source', 'read', T + DAY, policy.view(self.owner)['epoch'])
        self.assertEqual([n['cite']['id'] for n in self.run_now()['outcome']['nominated']], [dated])

    def test_outputs_cite_only_what_is_readable_now(self):
        dated = self.statement(7, '2030-03-17'); self.configure(); self.run_now()
        nomination = self.nominations()[0]
        self.assertEqual((nomination['cite']['state'], nomination['cite']['value']), ('current', '2030-03-17'))
        policy = IdentityPolicy(self.store)
        policy.enable(self.owner, policy.view(self.owner)['epoch'])
        view = self.routines.view(self.owner)
        self.assertEqual(view['nominations'][0]['cite'], {'kind': 'statement', 'id': dated, 'version': 2, 'state': 'unavailable'})
        self.assertEqual(view['runs'][0]['outcome']['cited'][0]['resolved'], {'state': 'unavailable'})
        self.assertNotIn('Launch review', json.dumps(view))
        self.fault('nomination_source_changed', self.routines.accept, self.owner, nomination['id'], {'version': 1, 'create_follow_up': False})

    def test_quiet_hours_hold_nominations_and_surface_them_afterwards(self):
        self.record(due=T - HOUR)
        self.configure(quiet_hours={'start': '17:00', 'end': '19:00'})
        run = self.run_now()['outcome']
        end = T - T % DAY + 19 * HOUR
        self.assertEqual((run['held'], run['surface_at']), ({'quiet_hours': 1, 'next_brief': 0}, end))
        held = self.nominations()[0]
        self.assertEqual((held['surfaced'], held['held'], held['delivery']), (False, 'quiet_hours', 'quiet_hours'))
        self.assertEqual((self.routines.summary(self.owner)['nominations'], self.routines.summary(self.owner)['held']), ([], 1))
        self.clock[0] = end
        summary = self.routines.summary(self.owner)
        self.assertEqual(([n['id'] for n in summary['nominations']], summary['held']), ([held['id']], 0))

    def test_hold_for_the_next_brief_and_the_morning_brief(self):
        overdue = self.record(due=T - HOUR)
        self.record('milestone', 'Picture lock')
        second = self.record(title='Second', due=T - 2 * HOUR)
        self.configure(interrupt='hold_for_brief')
        self.assertEqual(self.run_now()['outcome']['held'], {'quiet_hours': 0, 'next_brief': 2})
        self.assertEqual([n['held'] for n in self.nominations()], ['next_brief', 'next_brief'])
        self.assertEqual(self.routines.summary(self.owner)['nominations'], [])
        self.configure('morning-brief', schedule={'daily_at': '07:30'}, nominations_per_run=1)
        brief = self.run_now('morning-brief')
        self.assertEqual(brief['status'], 'completed')
        outcome = brief['outcome']
        self.assertEqual((outcome['read']['held_nominations'], len(outcome['released']), outcome['still_held']), (2, 1, 1))
        self.assertEqual({a['id'] for a in outcome['sections']['attention']}, {overdue['id'], second['id']})
        self.assertTrue(all(a['version'] == 1 and a['rule'] == 'overdue' for a in outcome['sections']['attention']))
        # Only citations and counts are stored, never the titles.
        with self.store.connection() as db:
            stored = db.execute("SELECT outcome FROM routine_runs WHERE kind='morning-brief'").fetchone()[0]
        self.assertNotIn('Book the grade', stored)
        summary = self.routines.summary(self.owner)
        self.assertEqual((len(summary['nominations']), summary['held'], summary['latest_brief']['released']), (1, 1, 1))
        resolved = self.runs()[0]['outcome']['cited'][0]['resolved']
        self.assertEqual(resolved['state'], 'current')
        remaining = [n['id'] for n in self.nominations() if n['held']]
        self.assertEqual((len(remaining), self.run_now('morning-brief')['outcome']['released']), (1, remaining))

    def test_morning_brief_cites_pending_approvals_and_insights(self):
        self.record('priority', 'First', due=T + DAY, rank=1)
        self.record('priority', 'Second', due=T + DAY + HOUR, rank=2)
        (self.root / 'project' / 'call.json').write_text(json.dumps({'document_id': 'call', 'title': 'Call time', 'revision': 1,
                                                                    'observed_at': T - 10, 'expires_at': T + HOUR, 'summary': 'Call time moved.'}))
        self.sup.source.scan()
        seq = self.store.desk_state(self.owner)['events'][0]['seq']
        action = self.store.propose_from_evidence(self.owner, {'event_seq': seq, 'text': 'Crew note', 'request_id': 'a1'})
        self.configure('morning-brief', schedule={'daily_at': '07:30'})
        outcome = self.run_now('morning-brief')['outcome']
        self.assertEqual([a['id'] for a in outcome['sections']['approvals']], [action['id']])
        self.assertEqual([i['rule'] for i in outcome['sections']['insights']], ['top_priorities_deadline_clash'])
        self.assertEqual(self.store.desk_state(self.owner)['actions'][0]['state'], 'proposed')

    def test_failed_run_is_recorded_and_keeps_nothing(self):
        self.record(due=T - HOUR); self.configure()
        original = self.routines._commitment_review

        def broken(db, p, settings, run_id, now):
            original(db, p, settings, run_id, now)
            raise RuntimeError('injected')
        self.routines._commitment_review = broken
        result = self.run_now()
        self.assertEqual((result['status'], result['outcome']['error']), ('failed', 'routine_failed'))
        self.assertEqual(self.count('routine_nominations'), 0)


class NominationTests(Base):
    def setUp(self):
        super().setUp()
        self.made = self.record(due=T - HOUR, responsible='Coordinator')
        self.configure(propose_drafts=True)
        self.run_now()
        self.reminder = next(n for n in self.nominations() if n['kind'] == 'reminder')
        self.draft = next(n for n in self.nominations() if n['kind'] == 'draft')

    def accept(self, nomination, follow_up=False, bearer=None, version=None):
        return self.routines.accept(bearer or self.owner, nomination['id'],
                                    {'version': nomination['version'] if version is None else version, 'create_follow_up': follow_up})

    def test_accepting_a_reminder_is_recorded_without_creating_an_obligation(self):
        before = self.count('executive_records')
        result = self.accept(self.reminder)
        self.assertEqual((result['nomination']['state'], result['nomination']['outcome']), ('accepted', {'follow_up': None}))
        self.assertEqual(self.count('executive_records'), before)
        self.fault('nomination_closed', self.accept, self.reminder, False, None, 2)

    def test_accepting_with_a_follow_up_uses_the_executive_api_once(self):
        result = self.accept(self.reminder, follow_up=True)
        follow_up = next(r for r in self.records.view(self.owner)['records'] if r['id'] == result['follow_up'])
        self.assertEqual((follow_up['kind'], follow_up['title'], follow_up['origin'], follow_up['derived_from'], follow_up['project']),
                         ('follow_up', 'Follow up: Book the grade', 'accepted_recommendation', self.made['id'], 'entity:atlas'))
        again = self.accept(self.reminder, follow_up=True)
        self.assertEqual(again['follow_up'], result['follow_up'])
        self.assertEqual(self.count('executive_records', "kind='follow_up'"), 1)

    def test_statement_reminder_follow_up(self):
        dated = self.statement(7, '2030-03-17'); self.run_now()
        nomination = next(n for n in self.nominations() if n['cite']['id'] == dated)
        result = self.accept(nomination, follow_up=True)
        follow_up = next(r for r in self.records.view(self.owner)['records'] if r['id'] == result['follow_up'])
        self.assertEqual((follow_up['title'], follow_up['origin'], follow_up['project']),
                         ('Follow up: Atlas, scheduled for 2030-03-17', 'user_authored', 'entity:atlas'))

    def test_dismissal_is_recorded_and_final_for_that_version(self):
        result = self.routines.dismiss(self.owner, self.reminder['id'], {'version': 1})
        self.assertEqual((result['nomination']['state'], result['nomination']['decided']), ('dismissed', T))
        self.fault('nomination_closed', self.accept, self.reminder, False, None, 2)
        self.assertEqual(self.run_now()['outcome']['not_nominated']['already_nominated'], 2)
        with self.store.connection() as db:
            kinds = [r[0] for r in db.execute("SELECT kind FROM audit WHERE kind LIKE 'routine.nomination_%'")]
        self.assertEqual(kinds, ['routine.nomination_dismissed'])

    def test_a_changed_commitment_cannot_be_accepted(self):
        self.records.update(self.owner, self.made['id'], {'version': 1, 'due': T + 2 * DAY})
        self.assertEqual(self.nominations()[0]['cite']['state'], 'changed')
        self.fault('nomination_source_changed', self.accept, self.reminder)
        self.fault('nomination_changed', self.accept, self.reminder, False, None, 9)
        self.assertEqual(self.routines.dismiss(self.owner, self.reminder['id'], {'version': 1})['nomination']['state'], 'dismissed')

    def test_another_persons_nomination_looks_unknown(self):
        hidden = self.fault('nomination_not_found', self.accept, self.reminder, False, self.other)
        unknown = self.fault('nomination_not_found', self.routines.accept, self.owner, 'nom-unknown', {'version': 1, 'create_follow_up': False})
        self.assertEqual((hidden.status, unknown.status), (404, 404))
        self.fault('forbidden', self.accept, self.reminder, False, self.reader)
        self.assertEqual(self.nominations()[0]['state'], 'open')

    def test_draft_offer_enters_the_ledger_only_when_accepted_and_is_never_auto_approved(self):
        self.assertEqual(self.count('actions'), 0)
        self.fault('follow_up_only_for_reminders', self.accept, self.draft, True)
        action = self.accept(self.draft)['action']
        self.assertEqual((action['state'], action['capability'], action['effect']), ('proposed', 'message.draft', 'local_draft_only_not_sent'))
        self.assertEqual(action['parameters']['text'],
                         'Coordinator: checking in on "Book the grade", which was due 2030-03-17 16:46. Could you let me know where it stands?')
        for _ in range(3):
            self.clock[0] += 5; self.sup.cycle()
        self.assertEqual((self.store.desk_state(self.owner)['actions'][0]['state'], self.count('outbox'), self.count('drafts')), ('proposed', 0, 0))
        self.fault('approval_mismatch', self.store.approve, self.owner, action['id'], '0' * 64)
        self.assertEqual(self.store.approve(self.owner, action['id'], action['fingerprint'])['state'], 'queued')
        self.sup.cycle()
        self.assertEqual((self.store.desk_state(self.owner)['actions'][0]['state'], self.count('drafts')), ('verified', 1))

    def test_draft_approval_rechecks_the_cited_commitment(self):
        action = self.accept(self.draft)['action']
        self.records.update(self.owner, self.made['id'], {'version': 1, 'status': 'done'})
        self.fault('evidence_or_approval_expired', self.store.approve, self.owner, action['id'], action['fingerprint'])
        with self.store.connection() as db:
            row = db.execute('SELECT * FROM actions WHERE id=?', (action['id'],)).fetchone()
            self.assertFalse(self.store.evidence_valid(db, row))

    def test_dismissing_a_draft_offer_creates_nothing(self):
        self.routines.dismiss(self.owner, self.draft['id'], {'version': 1})
        self.assertEqual((self.count('actions'), self.count('routine_action_sources')), (0, 0))


class HTTPTests(Base):
    def setUp(self):
        super().setUp()
        from alfred.desk_http import DeskHTTPServer
        self.server = DeskHTTPServer(self.store, self.sup, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close)
        self.cookie = self.csrf = None
        self.routines = self.server.routines

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)

    def raw(self, path, data=None, headers=None, method=None):
        headers = dict(headers or {})
        if self.cookie:
            headers.setdefault('Cookie', self.cookie)
        if data is not None:
            headers.setdefault('Content-Type', 'application/json'); headers.setdefault('Origin', self.server.origin)
            if self.csrf:
                headers.setdefault('X-CSRF-Token', self.csrf)
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request(method or ('POST' if data is not None else 'GET'), path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); body = r.read(); c.close()
        return r.status, json.loads(body)

    def login(self, key):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST', '/desk/login', json.dumps({'key': key}), {'Content-Type': 'application/json', 'Origin': self.server.origin})
        r = c.getresponse(); body = json.loads(r.read()); c.close()
        self.cookie = r.getheader('Set-Cookie').split(';')[0]; self.csrf = body['csrf']

    def test_routes_keep_the_loopback_session_and_csrf_guard(self):
        self.assertEqual(self.raw('/desk/routines')[0], 401)
        self.login(self.owner)
        status, view = self.raw('/desk/routines')
        self.assertEqual((status, view['available']), (200, True))
        path = '/desk/routines/commitment-review/configure'
        self.assertEqual(self.raw(path, self.body(), {'X-CSRF-Token': 'wrong'}), (403, {'error': 'csrf_rejected'}))
        self.assertEqual(self.raw(path, self.body(), {'Origin': 'http://evil.example'}), (403, {'error': 'invalid_origin'}))
        self.assertEqual(self.raw(path, self.body(), {'Host': 'localhost:1'}), (403, {'error': 'invalid_host'}))
        self.assertEqual(self.raw('/desk/routines?x=1')[0], 404)
        self.assertEqual(self.raw('/desk/routines/shell/configure', self.body()), (404, {'error': 'not_found'}))
        self.assertEqual(self.raw('/desk/routines/procedures', {}), (404, {'error': 'not_found'}))
        self.assertFalse(self.routine()['configured'])

    def test_configure_run_accept_and_dismiss_over_http(self):
        self.record(due=T - HOUR); self.record(title='Second', due=T - 2 * HOUR)
        self.login(self.owner)
        status, view = self.raw('/desk/routines/commitment-review/configure', self.body())
        self.assertEqual((status, view['routines'][0]['enabled']), (200, True))
        status, run = self.raw('/desk/routines/commitment-review/run', {'request_id': 'now-1'})
        self.assertEqual((status, run['status'], len(run['outcome']['nominated'])), (200, 'completed', 2))
        status, summary = self.raw('/desk/routines/nominations')
        first, second = summary['nominations']
        self.assertEqual(self.raw(f"/desk/routines/nominations/{first['id']}/accept", {'version': 1, 'create_follow_up': True})[0], 200)
        self.assertEqual(self.raw(f"/desk/routines/nominations/{second['id']}/dismiss", {'version': 1})[0], 200)
        self.assertEqual([n['state'] for n in self.nominations()], ['accepted', 'dismissed'])
        self.login(self.reader)
        self.assertEqual(self.raw(f"/desk/routines/nominations/{first['id']}/dismiss", {'version': 2}), (403, {'error': 'forbidden'}))
        self.assertEqual(self.raw('/desk/routines')[1]['nominations'], [])
        self.login(self.other)
        self.assertEqual(self.raw(f"/desk/routines/nominations/{first['id']}/dismiss", {'version': 2}), (404, {'error': 'nomination_not_found'}))

    def test_supervisor_cycle_runs_due_routines(self):
        self.record(due=T - HOUR)
        self.configure()
        self.clock[0] = self.routine()['next_due']
        self.sup.cycle()
        self.assertEqual([(r['trigger'], r['status']) for r in self.runs()], [('scheduled', 'completed')])


if __name__ == '__main__':
    unittest.main()
