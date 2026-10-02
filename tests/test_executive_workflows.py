"""ATT-002 and ATT-001 executive workflows on synthetic data.

Responsible labels, decision options, preparation briefs, attention and derived
insights. Real SQLite, real notes from a fictional vault, and real HTTP where the
boundary matters. Nothing here infers an owner, scores an option or stores a brief.
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
from alfred.executive import ExecutiveRecords, SCHEMA
from alfred.policy import IdentityPolicy

DAY = 86400
T = 1_900_000_000


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name); self.clock = [T]
        self.store = KnowledgeStore(root / 'desk.sqlite', clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=2592000)
        self.other = self.store.provision('work', 'owner-two', 'owner', ttl=2592000)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=2592000)
        self.source = self.store.provision('work', 'source', 'source', ttl=2592000)
        self.vault = root / 'vault'; self.vault.mkdir()
        (self.vault / 'Atlas.md').write_text('---\ntitle: Atlas\ntype: project\n---\n# Atlas\n\nLaunch review on Friday.\nBudget sign-off pending.\n')
        (self.vault / 'Borealis.md').write_text('---\ntitle: Borealis\ntype: project\n---\n# Borealis\n\nA second fictional project.\n')
        (self.vault / 'Morgan.md').write_text('---\ntitle: Morgan\ntype: person\n---\n# Morgan\n\nLooks after the Atlas budget.\nResponsible person: Riley.\n')
        self.scanner = MarkdownVault(self.store, self.source, self.vault); self.scanner.scan()
        self.memory = ReviewedMemory(self.store)
        self.memory.create_entity(self.owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas'})
        self.records = ExecutiveRecords(self.store)
        self.seq = 0

    def note(self, title):
        return next(n for n in self.store.knowledge(self.owner)['nodes'] if n['title'] == title)

    def ref(self, title):
        return 'note:' + self.note(title)['id']

    def lines(self, title, first, last=None):
        n = self.note(title)
        return {'note_id': n['id'], 'sha256': n['sha256'], 'revision': n['revision'], 'start_line': first, 'end_line': last or first}

    def at(self, days):
        self.clock[0] = T + int(days * DAY)

    def create(self, kind, title='Atlas launch', bearer=None, **over):
        self.seq += 1
        body = {'request_id': f'r{self.seq}', 'kind': kind, 'title': title, 'detail': '', 'project': 'entity:atlas',
                'due': None, 'rank': None, 'support': None}
        body.update(over)
        return self.records.create(bearer or self.owner, body)

    def fault(self, code, call, *args):
        with self.assertRaises(Fault) as caught:
            call(*args)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def view(self):
        return self.records.view(self.owner)

    def get(self, identity):
        return next(r for r in self.view()['records'] if r['id'] == identity)

    def claim(self, request, subject, predicate, evidence, obj=None, value=None, accept=True):
        made = self.memory.propose(self.owner, {'request_id': request, 'subject_id': subject, 'predicate': predicate,
                                                'object_id': obj, 'value': value, 'valid_from': None, 'valid_until': None,
                                                'evidence': evidence})
        if accept:
            self.memory.review(self.owner, made['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        return made['id']

    def count(self, table):
        with self.store.connection() as db:
            return db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]


class ResponsibleTests(Base):
    def test_label_is_typed_text_and_never_read_from_notes(self):
        plain = self.create('commitment', project=self.ref('Morgan'))
        self.assertEqual((plain['responsible'], plain['responsible_link']), (None, None))
        people = (self.count('credentials'), self.count('identity_devices'))
        made = self.create('commitment', title='Budget', responsible='  Finance   lead ')
        self.assertEqual((made['responsible'], made['responsible_link'], made['authority_granted']), ('Finance lead', None, False))
        self.assertEqual((self.count('credentials'), self.count('identity_devices')), people)
        groups = self.view()['responsible_groups']
        self.assertEqual([(g['label'], g['link'], g['records']) for g in groups['groups']], [('Finance lead', None, [made['id']])])
        self.assertEqual(groups['unassigned_open'], [plain['id']])
        self.assertEqual(groups['basis'], 'your_labels_not_identities')

    def test_link_must_be_an_explicitly_picked_visible_person_record(self):
        self.memory.create_entity(self.owner, {'id': 'morgan-1', 'kind': 'person', 'name': 'Morgan'})
        self.memory.create_entity(self.other, {'id': 'theirs', 'kind': 'person', 'name': 'Theirs'})
        with self.assertRaises(Fault) as caught:
            self.create('commitment', responsible_link='entity:morgan-1')
        self.assertEqual(caught.exception.code, 'responsible_label_required')
        outcomes = {}
        for link in ('entity:atlas', self.ref('Atlas'), 'entity:unknown', 'entity:theirs', 'person:morgan'):
            with self.assertRaises(Fault, msg=link) as caught:
                self.create('commitment', responsible='Morgan', responsible_link=link)
            outcomes[link] = (caught.exception.code, caught.exception.status)
        self.assertEqual(outcomes, {'entity:atlas': ('responsible_not_a_person', 400), self.ref('Atlas'): ('responsible_not_a_person', 400),
                                    # Another person's record and an unknown one are indistinguishable.
                                    'entity:unknown': ('responsible_not_available', 404), 'entity:theirs': ('responsible_not_available', 404),
                                    'person:morgan': ('invalid_responsible_link', 400)})
        note = self.create('commitment', responsible='Budget owner', responsible_link=self.ref('Morgan'))
        entity = self.create('commitment', responsible='Morgan', responsible_link='entity:morgan-1')
        self.assertEqual((note['responsible_state'], note['responsible_name']), ('current', 'Morgan'))
        self.assertEqual((entity['responsible_link'], entity['responsible_state']), ('entity:morgan-1', 'current'))

    def test_namesakes_and_spellings_are_never_combined(self):
        for key in ('morgan-1', 'morgan-2'):
            self.memory.create_entity(self.owner, {'id': key, 'kind': 'person', 'name': 'Morgan'})
        one = self.create('commitment', responsible='Morgan', responsible_link='entity:morgan-1')
        two = self.create('commitment', responsible='Morgan', responsible_link='entity:morgan-2')
        bare = self.create('commitment', responsible='Morgan')
        lower = self.create('commitment', responsible='morgan')
        groups = self.view()['responsible_groups']['groups']
        self.assertEqual(sorted(tuple(g['records']) for g in groups), sorted([(one['id'],), (two['id'],), (bare['id'],), (lower['id'],)]))
        self.assertEqual({g['link'] for g in groups}, {'entity:morgan-1', 'entity:morgan-2', None})
        self.assertEqual(self.get(one['id'])['responsible_link'], 'entity:morgan-1')

    def test_forgotten_or_hidden_link_is_unavailable_and_its_name_is_withheld(self):
        self.memory.create_entity(self.owner, {'id': 'morgan-1', 'kind': 'person', 'name': 'Morgan Example'})
        entity = self.create('commitment', responsible='Budget owner', responsible_link='entity:morgan-1')
        note = self.create('commitment', responsible='Budget owner', responsible_link=self.ref('Morgan'))
        self.memory.forget_entity(self.owner, 'morgan-1', {})
        record = self.get(entity['id'])
        self.assertEqual((record['responsible'], record['responsible_state'], record['responsible_name']), ('Budget owner', 'unavailable', None))
        self.assertNotIn('Morgan Example', json.dumps(self.view()))
        IdentityPolicy(self.store).enable(self.owner, 0)
        record = self.get(note['id'])
        self.assertEqual((record['responsible_state'], record['responsible_name']), ('unavailable', None))

    def test_responsible_changes_are_version_checked_and_owner_only(self):
        made = self.create('commitment', responsible='Finance lead', responsible_link=self.ref('Morgan'))
        self.fault('executive_record_changed', self.records.update, self.owner, made['id'], {'version': 9, 'responsible': 'Ops'})
        cleared = self.records.update(self.owner, made['id'], {'version': 1, 'responsible': None})
        self.assertEqual((cleared['responsible'], cleared['responsible_link'], cleared['version']), (None, None, 2))
        self.fault('responsible_label_required', self.records.update, self.owner, made['id'], {'version': 2, 'responsible_link': self.ref('Morgan')})
        relabelled = self.records.update(self.owner, made['id'], {'version': 2, 'responsible': 'Ops', 'responsible_link': self.ref('Morgan')})
        self.assertEqual((relabelled['responsible'], relabelled['responsible_state']), ('Ops', 'current'))
        self.fault('forbidden', self.records.update, self.reader, made['id'], {'version': 3, 'responsible': 'Reader'})
        self.fault('executive_record_not_found', self.records.update, self.other, made['id'], {'version': 3, 'responsible': 'Other'})

    def test_invalid_labels_are_rejected(self):
        for value, code in (('', 'invalid_text'), ('x' * 81, 'invalid_text'), ('a\x00b', 'control_character'),
                            ('   ', 'invalid_responsible'), (42, 'invalid_responsible')):
            with self.assertRaises(Fault, msg=repr(value)) as caught:
                self.create('commitment', responsible=value)
            self.assertEqual(caught.exception.code, code)


class DecisionTests(Base):
    OPTIONS = [{'label': 'Hire a contractor', 'notes': 'Faster start.', 'pros': ['Starts next week'], 'cons': ['Costs more']},
               {'label': 'Train the team'}]

    def test_options_are_authored_bounded_and_carry_no_score(self):
        made = self.create('decision', options=self.OPTIONS)
        self.assertEqual(made['options'], [
            {'id': 'o1', 'label': 'Hire a contractor', 'notes': 'Faster start.', 'pros': ['Starts next week'], 'cons': ['Costs more']},
            {'id': 'o2', 'label': 'Train the team', 'notes': '', 'pros': [], 'cons': []}])
        self.assertTrue(all(set(o) == {'id', 'label', 'notes', 'pros', 'cons'} for o in made['options']))
        self.assertEqual((made['status'], made['choice'], made['decision_history']), ('proposed', None, []))
        bad = (([{'label': 'Only one'}], 'invalid_decision_options'), ([{'label': str(i)} for i in range(7)], 'invalid_decision_options'),
               ([{'label': 'Same'}, {'label': 'same'}], 'duplicate_option_label'),
               ([{'label': 'A', 'score': 9}, {'label': 'B'}], 'invalid_decision_option'),
               ([{'label': 'A', 'pros': ['1', '2', '3', '4', '5']}, {'label': 'B'}], 'invalid_option_points'),
               ('not a list', 'invalid_decision_options'))
        for options, code in bad:
            with self.assertRaises(Fault, msg=options) as caught:
                self.create('decision', options=options)
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(Fault) as caught:
            self.create('commitment', options=self.OPTIONS)
        self.assertEqual(caught.exception.code, 'options_only_for_decisions')

    def test_a_choice_is_recorded_only_when_the_person_decides(self):
        made = self.create('decision', options=self.OPTIONS)
        decide = self.records.decide
        self.fault('executive_record_changed', decide, self.owner, made['id'], {'version': 2, 'option': 'o2', 'rationale': 'Why.'})
        self.fault('unknown_decision_option', decide, self.owner, made['id'], {'version': 1, 'option': 'o9', 'rationale': 'Why.'})
        self.fault('unknown_decision_option', decide, self.owner, made['id'], {'version': 1, 'option': None, 'rationale': 'Why.'})
        self.fault('rationale_required', decide, self.owner, made['id'], {'version': 1, 'option': 'o2', 'rationale': '  '})
        self.assertIsNone(self.get(made['id'])['choice'])
        self.at(1)
        decided = decide(self.owner, made['id'], {'version': 1, 'option': 'o2', 'rationale': 'Keeps the knowledge in the team.'})
        self.assertEqual(decided['status'], 'decided')
        self.assertEqual(decided['choice'], {'option': 'o2', 'label': 'Train the team', 'rationale': 'Keeps the knowledge in the team.',
                                             'decided_at': T + DAY})
        self.assertEqual([(h['event'], h['option']) for h in decided['decision_history']], [('decided', 'o2')])
        self.fault('decision_reopen_required', self.records.update, self.owner, made['id'], {'version': 2, 'status': 'proposed'})
        self.fault('decision_reopen_required', self.records.set_options, self.owner, made['id'], {'version': 2, 'options': self.OPTIONS})
        self.fault('decision_not_open', decide, self.owner, made['id'], {'version': 2, 'option': 'o1', 'rationale': 'Again.'})

    def test_reopening_is_explicit_and_keeps_the_earlier_choice_in_the_trail(self):
        made = self.create('decision', options=self.OPTIONS)
        self.records.decide(self.owner, made['id'], {'version': 1, 'option': 'o1', 'rationale': 'Speed matters most.'})
        reopened = self.records.reopen(self.owner, made['id'], {'version': 2})
        self.assertEqual((reopened['status'], reopened['choice']), ('proposed', None))
        self.assertEqual([(h['event'], h['option'], h['label']) for h in reopened['decision_history']],
                         [('decided', 'o1', 'Hire a contractor'), ('reopened', 'o1', 'Hire a contractor')])
        self.fault('decision_not_closed', self.records.reopen, self.owner, made['id'], {'version': 3})
        changed = self.records.set_options(self.owner, made['id'], {'version': 3, 'options': self.OPTIONS + [{'label': 'Pause the work'}]})
        self.assertEqual([o['id'] for o in changed['options']], ['o1', 'o2', 'o3'])
        final = self.records.decide(self.owner, made['id'], {'version': 4, 'option': 'o3', 'rationale': 'Budget is frozen.'})
        self.assertEqual((final['choice']['label'], len(final['decision_history'])), ('Pause the work', 3))

    def test_generic_status_changes_respect_options(self):
        withopts = self.create('decision', options=self.OPTIONS)
        self.fault('decision_choice_required', self.records.update, self.owner, withopts['id'], {'version': 1, 'status': 'decided'})
        superseded = self.records.update(self.owner, withopts['id'], {'version': 1, 'status': 'superseded'})
        self.assertEqual((superseded['status'], superseded['choice']), ('superseded', None))
        plain = self.create('decision')
        decided = self.records.update(self.owner, plain['id'], {'version': 1, 'status': 'decided'})
        self.assertEqual(decided['choice'], {'option': None, 'label': None, 'rationale': None, 'decided_at': T})
        back = self.records.update(self.owner, plain['id'], {'version': 2, 'status': 'proposed'})
        self.assertEqual((back['choice'], [h['event'] for h in back['decision_history']]), (None, ['decided', 'reopened']))
        self.fault('options_only_for_decisions', self.records.set_options, self.owner, self.create('milestone')['id'],
                   {'version': 1, 'options': self.OPTIONS})

    def test_decisions_stay_private_to_their_author(self):
        made = self.create('decision', options=self.OPTIONS)
        self.fault('forbidden', self.records.decide, self.reader, made['id'], {'version': 1, 'option': 'o1', 'rationale': 'No.'})
        self.fault('executive_record_not_found', self.records.decide, self.other, made['id'], {'version': 1, 'option': 'o1', 'rationale': 'No.'})
        self.fault('executive_record_not_found', self.records.reopen, self.other, made['id'], {'version': 1})
        self.assertEqual(self.records.view(self.other)['records'], [])


class BriefTests(Base):
    def setUp(self):
        super().setUp()
        self.memory.create_entity(self.owner, {'id': 'morgan', 'kind': 'person', 'name': 'Morgan'})
        self.status = self.claim('c1', 'atlas', 'status', self.lines('Atlas', 8), value='budget sign-off pending')
        self.pending = self.claim('c2', 'atlas', 'scheduled_for', self.lines('Atlas', 7), value='Friday review', accept=False)
        self.owner_claim = self.claim('c3', 'atlas', 'responsible_person', self.lines('Morgan', 7), obj='morgan')

    def decision(self, **over):
        values = {'title': 'Choose the launch date', 'project': self.ref('Atlas'), 'support': self.lines('Atlas', 8),
                  'responsible': 'Finance lead', 'responsible_link': 'entity:morgan', 'due': T + 3 * DAY,
                  'options': [{'label': 'Friday', 'notes': 'Matches the review.'}, {'label': 'Monday'}]}
        values.update(over)
        return self.create('decision', **values)

    def test_brief_assembles_current_cited_material_only(self):
        made = self.decision()
        milestone = self.create('milestone', title='Budget approved', project=self.ref('Atlas'))
        self.records.add_progress(self.owner, milestone['id'], {'version': 1, 'note': 'Draft budget circulated'})
        self.create('commitment', title='Send the budget', project=self.ref('Atlas'), due=T + 2 * DAY)
        self.create('follow_up', title='Chase the venue', project=self.ref('Atlas'))
        closed = self.create('commitment', title='Already done', project=self.ref('Atlas'))
        self.records.update(self.owner, closed['id'], {'version': 1, 'status': 'done'})
        self.create('commitment', title='Elsewhere', project=self.ref('Borealis'))
        brief = self.records.brief(self.owner, made['id'])
        self.assertEqual((brief['kind'], brief['model_used'], brief['stored'], brief['authority_granted']), ('assembled_brief', False, False, False))
        self.assertIn('Not advice and not model output', brief['label'])
        atlas = self.note('Atlas')
        project, cited = brief['linked_notes']
        self.assertEqual((project['role'], project['excerpt'], project['cite']), ('project', 'Launch review on Friday.',
                         {'note': atlas['id'], 'revision': atlas['revision'], 'lines': [7, 7]}))
        self.assertEqual((cited['role'], cited['excerpt'], cited['cite']['lines']), ('cited_support', 'Budget sign-off pending.', [8, 8]))
        self.assertEqual({s['claim_id']: s['why'] for s in brief['statements']},
                         {self.status: 'supported_by_linked_note', self.owner_claim: 'about_linked_record'})
        for s in brief['statements']:
            self.assertEqual(set(s['cite']), {'claim', 'version', 'note', 'revision', 'lines'})
            self.assertEqual(s['basis'], 'user_reviewed_statement_not_verified_fact')
        self.assertNotIn('Friday review', json.dumps(brief['statements']))
        self.assertEqual([r['title'] for r in brief['related']], ['Send the budget', 'Chase the venue'])
        self.assertTrue(all(r['cite'] == {'record': r['id'], 'version': r['version']} for r in brief['related']))
        self.assertEqual((brief['progress']['done'], brief['progress']['total']), (0, 1))
        self.assertEqual(brief['progress']['recent'][0]['note'], 'Draft budget circulated')
        codes = [q['code'] for q in brief['questions']]
        self.assertEqual(codes, ['options_without_notes'])
        self.assertIn('"Monday"', brief['questions'][0]['text'])
        self.assertEqual(brief['record']['id'], made['id'])

    def test_brief_names_what_is_missing(self):
        bare = self.create('decision', project=None)
        codes = [q['code'] for q in self.records.brief(self.owner, bare['id'])['questions']]
        self.assertEqual(codes, ['no_responsible', 'no_due_date', 'no_project', 'no_options'])
        milestone = self.create('milestone', project=None, due=T - DAY)
        brief = self.records.brief(self.owner, milestone['id'])
        self.assertEqual([q['code'] for q in brief['questions']], ['no_responsible', 'overdue', 'no_project'])
        self.assertEqual((brief['progress']['total'], brief['related']), (1, []))
        self.fault('brief_kind_not_supported', self.records.brief, self.owner, self.create('goal')['id'])

    def test_access_is_rechecked_when_the_brief_is_assembled(self):
        made = self.decision(responsible_link=self.ref('Morgan'))
        first = json.dumps(self.records.brief(self.owner, made['id']))
        self.assertIn('Launch review on Friday.', first); self.assertIn('budget sign-off pending', first)
        policy = IdentityPolicy(self.store)
        policy.enable(self.owner, 0)
        brief = self.records.brief(self.owner, made['id'])
        text = json.dumps(brief)
        for hidden in ('Launch review on Friday.', 'Budget sign-off pending.', 'budget sign-off pending', 'Looks after'):
            self.assertNotIn(hidden, text)
        self.assertEqual([(n['role'], n['state'], n['excerpt']) for n in brief['linked_notes']], [('cited_support', 'unavailable', None)])
        self.assertEqual((brief['statements'], brief['related'], brief['progress']), ([], [], None))
        self.assertEqual([q['code'] for q in brief['questions']], ['support_unavailable', 'responsible_link_unavailable', 'project_unavailable',
                                                                   'options_without_notes'])
        policy.grant(self.owner, 'source', 'read', T + 3600, policy.view(self.owner)['epoch'])
        self.assertIn('Launch review on Friday.', json.dumps(self.records.brief(self.owner, made['id'])))

    def test_withheld_and_invalidated_values_never_appear(self):
        made = self.decision(project='entity:atlas', support=None, responsible_link=None)
        brief = self.records.brief(self.owner, made['id'])
        self.assertEqual({s['claim_id'] for s in brief['statements']}, {self.status, self.owner_claim})
        self.assertEqual(brief['statements_not_shown']['awaiting_review'], 1)
        IdentityPolicy(self.store).enable(self.owner, 0)
        brief = self.records.brief(self.owner, made['id'])
        self.assertEqual((brief['statements'], brief['statements_not_shown']['withheld']), ([], 2))
        self.assertNotIn('budget sign-off pending', json.dumps(brief))
        self.assertIn('statements_not_shown', [q['code'] for q in brief['questions']])
        policy = IdentityPolicy(self.store)
        policy.grant(self.owner, 'source', 'read', T + 3600, policy.view(self.owner)['epoch'])
        (self.vault / 'Atlas.md').write_text((self.vault / 'Atlas.md').read_text().replace('Budget sign-off pending.', 'Budget approved.'))
        self.scanner.scan()
        brief = self.records.brief(self.owner, made['id'])
        self.assertEqual([s['claim_id'] for s in brief['statements']], [self.owner_claim])
        self.assertEqual(brief['statements_not_shown']['needing_fresh_review'], 1)
        self.assertNotIn('budget sign-off pending', json.dumps(brief))

    def test_brief_is_computed_on_request_and_never_stored(self):
        made = self.decision()
        tables = ('executive_records', 'executive_progress', 'executive_decisions', 'audit', 'memory_claims')
        before = [self.count(t) for t in tables]
        self.records.brief(self.owner, made['id']); self.records.brief(self.owner, made['id'])
        self.assertEqual([self.count(t) for t in tables], before)
        for bearer in (self.other, self.reader):
            self.fault('executive_record_not_found', self.records.brief, bearer, made['id'])
        self.fault('executive_record_not_found', self.records.brief, self.owner, 'exec-unknown')

    def test_namesakes_are_flagged_and_kept_apart(self):
        self.memory.create_entity(self.owner, {'id': 'atlas-two', 'kind': 'project', 'name': 'atlas'})
        self.claim('c4', 'atlas-two', 'status', self.lines('Borealis', 7), value='a different atlas')
        made = self.decision(project='entity:atlas', support=None, responsible_link=None)
        brief = self.records.brief(self.owner, made['id'])
        self.assertIn('same_name_records', [q['code'] for q in brief['questions']])
        self.assertNotIn('a different atlas', json.dumps(brief['statements']))


class AttentionTests(Base):
    def items(self):
        return {i['record']: i['rules'] for i in self.view()['attention']['items']}

    def test_stated_rules_select_due_overdue_and_stale_items(self):
        soon = self.create('commitment', due=T + 3 * DAY)
        later = self.create('commitment', due=T + 10 * DAY)
        late = self.create('follow_up', due=T - DAY)
        finished = self.create('follow_up', due=T - DAY)
        self.records.update(self.owner, finished['id'], {'version': 1, 'status': 'done'})
        past = self.create('decision', due=T - 2 * DAY)
        self.create('decision', due=T + 5 * DAY)
        milestone = self.create('milestone')
        priority = self.create('priority', due=T - DAY)
        self.assertEqual(self.items(), {soon['id']: ['due_soon'], late['id']: ['overdue'], past['id']: ['decision_past_due'],
                                        priority['id']: ['overdue']})
        rules = [i['rules'][0] for i in self.view()['attention']['items']]
        self.assertEqual(rules, sorted(rules, key=['overdue', 'decision_past_due', 'due_soon', 'stale_milestone'].index))
        self.at(15)
        items = self.items()
        self.assertEqual((items[milestone['id']], items[soon['id']], items[later['id']]), (['stale_milestone'], ['overdue'], ['overdue']))
        self.records.add_progress(self.owner, milestone['id'], {'version': 1, 'note': 'Venue shortlist agreed'})
        self.assertNotIn(milestone['id'], self.items())
        self.at(29.5)
        self.assertEqual(self.items()[milestone['id']], ['stale_milestone'])

    def test_snooze_is_authored_bounded_and_visible(self):
        made = self.create('commitment', due=T + 2 * DAY)
        self.fault('invalid_snooze', self.records.update, self.owner, made['id'], {'version': 1, 'snoozed_until': T - 1})
        self.fault('invalid_snooze', self.records.update, self.owner, made['id'], {'version': 1, 'snoozed_until': T + 367 * DAY})
        snoozed = self.records.update(self.owner, made['id'], {'version': 1, 'snoozed_until': T + 5 * DAY})
        self.assertTrue(snoozed['snoozed'])
        view = self.view()
        self.assertEqual(view['attention']['items'], [])
        self.assertEqual([(i['record'], i['snoozed_until']) for i in view['attention']['snoozed']], [(made['id'], T + 5 * DAY)])
        self.assertEqual(view['recommendations'], [])
        self.at(6)
        view = self.view()
        self.assertEqual(([i['rules'] for i in view['attention']['items']], view['attention']['snoozed']), ([['overdue']], []))
        self.assertEqual([r['from_record'] for r in view['recommendations']], [made['id']])
        cleared = self.records.update(self.owner, made['id'], {'version': 2, 'snoozed_until': None})
        self.assertEqual((cleared['snoozed_until'], cleared['snoozed']), (None, False))

    def test_attention_is_in_app_only_and_states_its_rules(self):
        attention = self.view()['attention']
        self.assertEqual((attention['delivery'], attention['basis']), ('in_app_only', 'computed_on_request_from_your_records'))
        self.assertEqual([r['id'] for r in attention['rules']], ['overdue', 'decision_past_due', 'due_soon', 'stale_milestone'])


class InsightTests(Base):
    def insight(self, rule):
        return [i for i in self.view()['insights']['items'] if i['rule'] == rule]

    def test_one_label_with_overdue_records_in_two_projects(self):
        a = self.create('commitment', title='Atlas invoice', project=self.ref('Atlas'), responsible='Finance lead', due=T - DAY)
        b = self.create('follow_up', title='Borealis invoice', project=self.ref('Borealis'), responsible='Finance lead', due=T - 2 * DAY)
        self.create('commitment', title='Not overdue', project=self.ref('Atlas'), responsible='Finance lead', due=T + DAY)
        before = len(self.view()['records'])
        [found] = self.insight('responsible_overdue_across_projects')
        self.assertEqual({r['id'] for r in found['records']}, {a['id'], b['id']})
        self.assertEqual(sorted(p['name'] for p in found['projects']), ['Atlas', 'Borealis'])
        self.assertEqual((found['basis'], found['stored']), ('derived_from_your_records_not_accepted_fact', False))
        self.assertIn('"Finance lead"', found['statement'])
        self.assertEqual(len(self.view()['records']), before)
        IdentityPolicy(self.store).enable(self.owner, 0)
        self.assertEqual(self.insight('responsible_overdue_across_projects'), [])

    def test_namesake_links_do_not_combine_into_an_insight(self):
        for key in ('m1', 'm2'):
            self.memory.create_entity(self.owner, {'id': key, 'kind': 'person', 'name': 'Morgan'})
        self.create('commitment', project=self.ref('Atlas'), responsible='Morgan', responsible_link='entity:m1', due=T - DAY)
        self.create('commitment', project=self.ref('Borealis'), responsible='Morgan', responsible_link='entity:m2', due=T - DAY)
        self.assertEqual(self.insight('responsible_overdue_across_projects'), [])

    def test_top_priorities_with_clashing_deadlines(self):
        first = self.create('priority', title='First', rank=1, due=T + 5 * DAY)
        second = self.create('priority', title='Second', rank=2, due=T + 6 * DAY)
        self.create('priority', title='Third', rank=3, due=T + 20 * DAY)
        self.create('priority', title='Fourth', rank=4, due=T + 5 * DAY)
        [found] = self.insight('top_priorities_deadline_clash')
        self.assertEqual([r['id'] for r in found['records']], [first['id'], second['id']])
        self.records.update(self.owner, second['id'], {'version': 1, 'due': T + 9 * DAY})
        self.assertEqual(self.insight('top_priorities_deadline_clash'), [])

    def test_project_with_commitments_but_no_recent_milestone(self):
        self.at(-10)
        quiet = self.create('commitment', title='Quiet commitment', project=self.ref('Atlas'))
        self.create('commitment', project=self.ref('Borealis'))
        self.at(5)
        self.create('milestone', project=self.ref('Borealis'))
        self.at(21)
        [found] = self.insight('commitments_without_milestone')
        self.assertEqual(([r['id'] for r in found['records']], found['projects']), ([quiet['id']], [{'ref': self.ref('Atlas'), 'name': 'Atlas'}]))
        self.create('milestone', project=self.ref('Atlas'))
        self.assertEqual(self.insight('commitments_without_milestone'), [])


class SupportStateTests(Base):
    def test_lost_access_reads_as_unavailable_and_an_edit_as_changed(self):
        atlas = self.note('Atlas')['id']
        made = self.create('commitment', support=self.lines('Atlas', 8))
        self.assertEqual(self.get(made['id'])['support']['state'], 'current')
        policy = IdentityPolicy(self.store)
        policy.enable(self.owner, 0)
        self.assertEqual(self.get(made['id'])['support'], {'note_id': atlas, 'start_line': 8, 'end_line': 8, 'quote': None, 'state': 'unavailable'})
        policy.grant(self.owner, 'source', 'read', T + 3600, policy.view(self.owner)['epoch'])
        self.assertEqual(self.get(made['id'])['support']['quote'], 'Budget sign-off pending.')
        (self.vault / 'Atlas.md').unlink(); self.scanner.scan()
        self.assertEqual((self.get(made['id'])['support']['state'], self.get(made['id'])['status']), ('changed', 'open'))


class MigrationTests(unittest.TestCase):
    def test_version_one_records_upgrade_in_place(self):
        with tempfile.TemporaryDirectory() as temp:
            store = KnowledgeStore(Path(temp) / 'desk.sqlite')
            owner = store.provision('work', 'owner', 'owner')
            with store.connection() as db:
                db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA + '\nCOMMIT;')
                db.execute("INSERT INTO executive_records VALUES ('exec-old','work','owner','old','x','decision','Old decision','',"
                           "'decided',NULL,NULL,NULL,NULL,'user_authored',NULL,3,1,1)")
            records = ExecutiveRecords(store)
            [old] = records.view(owner)['records']
            self.assertEqual((old['title'], old['status'], old['version'], old['responsible'], old['snoozed']), ('Old decision', 'decided', 3, None, False))
            self.assertEqual(old['choice'], {'option': None, 'label': None, 'rationale': None, 'decided_at': None})
            ExecutiveRecords(store)
            with store.connection() as db:
                self.assertEqual(db.execute('SELECT version FROM executive_meta').fetchall()[0][0], 2)
                db.execute('UPDATE executive_meta SET version=7')
            with self.assertRaises(Fault) as caught:
                ExecutiveRecords(store)
            self.assertEqual(caught.exception.code, 'unsupported_executive_version')


class WorkflowHTTPTests(unittest.TestCase):
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

    def req(self, path, data=None, csrf=True, origin=None):
        headers = {'Cookie': self.cookie} if self.cookie else {}
        if data is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': origin or self.server.origin})
            if csrf and self.csrf: headers['X-CSRF-Token'] = self.csrf
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); body = json.loads(r.read()); c.close()
        return r.status, body

    def login(self, role='owner'):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST', '/desk/login', json.dumps({'key': self.keys[role]}), {'Content-Type': 'application/json', 'Origin': self.server.origin})
        r = c.getresponse(); data = json.loads(r.read()); self.cookie = r.getheader('Set-Cookie').split(';')[0]; self.csrf = data['csrf']; c.close()

    def node(self, title):
        return next(n for n in self.req('/desk/knowledge')[1]['nodes'] if n['title'] == title)

    def test_workflow_routes_keep_the_desk_boundary(self):
        self.login()
        film, producer = self.node('Sample film'), self.node('Sample producer')
        now = self.store.now()
        body = {'request_id': 'd1', 'kind': 'decision', 'title': 'Opening treatment', 'detail': '', 'project': 'note:' + film['id'],
                'due': now + 3 * DAY, 'rank': None, 'support': None, 'responsible': 'Producer', 'responsible_link': 'note:' + producer['id'],
                'options': [{'label': 'Monochrome', 'notes': 'As the treatment proposes.'}, {'label': 'Colour'}]}
        code, made = self.req('/desk/executive/records', body)
        self.assertEqual((code, made['responsible_state']), (200, 'current'))
        path = f"/desk/executive/records/{made['id']}"
        decision = {'version': 1, 'option': 'o1', 'rationale': 'Matches the brief.'}
        self.assertEqual(self.req(path + '/decide', decision, csrf=False), (403, {'error': 'csrf_rejected'}))
        self.assertEqual(self.req(path + '/decide', decision, origin='http://evil.example')[0], 403)
        self.assertEqual(self.req(path + '/decide')[0], 404)
        self.assertEqual(self.req(path + '/brief', {})[0], 404)
        self.assertEqual(self.req(path + '/unknown', {})[0], 404)
        code, brief = self.req(path + '/brief')
        self.assertEqual((code, brief['kind'], brief['model_used']), (200, 'assembled_brief', False))
        self.assertEqual(brief['linked_notes'][0]['excerpt'], 'The fictional production brings its brief, people and decisions into one view.')
        self.assertEqual(self.req(path + '/decide', decision)[1]['choice']['label'], 'Monochrome')
        self.assertEqual(self.req(path + '/reopen', {'version': 2})[1]['status'], 'proposed')
        self.assertEqual(self.req(path + '/options', {'version': 3, 'options': None})[1]['options'], [])
        milestone = self.req('/desk/executive/records', {**body, 'request_id': 'm1', 'kind': 'milestone', 'title': 'Picture lock',
                                                         'options': None, 'due': None})[1]
        code, progressed = self.req(f"/desk/executive/records/{milestone['id']}/progress", {'version': 1, 'note': 'Rough cut reviewed'})
        self.assertEqual((code, progressed['progress'][0]['note']), (200, 'Rough cut reviewed'))
        commitment = self.req('/desk/executive/records', {**body, 'request_id': 'c1', 'kind': 'commitment', 'title': 'Send the crew update',
                                                          'options': None, 'due': now + 2 * DAY})[1]
        p = self.req('/desk/console/projection')[1]
        node = next(n for n in p['nodes'] if n['id'] == 'exec:' + commitment['id'])
        self.assertTrue(node['summary'].endswith(' · Producer.'))
        self.assertEqual(node['responsible'], 'Producer')
        edges = {(e['layer'], e['to']) for e in p['edges'] if e['from'] == node['id']}
        self.assertIn(('executive_responsible', 'note:' + producer['id']), edges)
        self.assertIn('exec:' + commitment['id'], [a['recordId'] for a in p['executive']['attention']])
        self.assertEqual(p['executive']['attentionCount'], 1)
        detail = self.req('/desk/console/records/exec:' + made['id'])[1]
        self.assertEqual((detail['responsible'], detail['responsibleState'], [o['label'] for o in detail['options']]), ('Producer', 'current', []))
        before = p['dataRevision']
        self.req(f"/desk/executive/records/{commitment['id']}", {'version': 1, 'snoozed_until': now + 5 * DAY})
        after = self.req('/desk/console/projection')[1]
        self.assertNotEqual(after['dataRevision'], before)
        self.assertEqual((after['executive']['attention'], after['executive']['snoozedCount']), ([], 1))
        self.login('reader')
        self.assertEqual(self.req(path + '/brief'), (404, {'error': 'executive_record_not_found'}))
        self.assertEqual(self.req(path + '/reopen', {'version': 4})[0], 403)


if __name__ == '__main__':
    unittest.main()
