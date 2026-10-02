"""MEM-007: recorded time, valid time, disputes and supersession as a review workflow.

Synthetic notes, real SQLite and a fixed clock. No model. The history keeps identifiers,
states and times only; these tests check that no reviewed value ever reaches it, including
after a forget is replayed on restore.
"""
from pathlib import Path
import hashlib
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock
from alfred.local import Fault
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.reviewed_memory import ReviewedMemory
from alfred.memory_history import MemoryHistory
from alfred.policy import IdentityPolicy
from alfred.grounded import retrieve
from alfred import lifecycle, memory_history

ATLAS = '# Atlas\nAtlas is planning.\nAtlas is filming.\nMina leads Atlas.\nOrla leads Atlas.\n'


class TemporalBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.clock = [1000]
        self.db = self.root / 'desk.sqlite'
        self.store = KnowledgeStore(self.db, clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=900000)
        self.owner2 = self.store.provision('work', 'owner2', 'owner', ttl=900000)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=900000)
        self.source = self.store.provision('work', 'source', 'source', ttl=900000)
        self.other = self.store.provision('work', 'other', 'source', ttl=900000)
        self.elsewhere = self.store.provision('elsewhere', 'elsewhere-owner', 'owner', ttl=900000)
        self.vault = self.root / 'vault'; self.vault.mkdir()
        (self.vault / 'Atlas.md').write_text(ATLAS)
        self.scanner = MarkdownVault(self.store, self.source, self.vault); self.scanner.scan()
        self.memory = ReviewedMemory(self.store); self.history = MemoryHistory(self.memory)
        for identity, kind, name in (('atlas', 'project', 'Atlas'), ('mina', 'person', 'Mina'), ('orla', 'person', 'Orla'),
                                     ('mina-two', 'person', 'Mina')):
            self.memory.create_entity(self.owner, {'id': identity, 'kind': kind, 'name': name})

    def note(self, bearer=None):
        return self.store.knowledge(bearer or self.owner)['nodes'][0]

    def propose(self, request, predicate, line, value=None, obj=None, valid=(None, None), subject='atlas', bearer=None):
        n = self.note(bearer)
        return self.memory.propose(bearer or self.owner, {
            'request_id': request, 'subject_id': subject, 'predicate': predicate, 'object_id': obj, 'value': value,
            'valid_from': valid[0], 'valid_until': valid[1],
            'evidence': {'note_id': n['id'], 'sha256': n['sha256'], 'revision': n['revision'], 'start_line': line, 'end_line': line}})['id']

    def claim(self, identity, bearer=None):
        return next(c for c in self.memory.view(bearer or self.owner)['claims'] if c['id'] == identity)

    def review(self, identity, decision, replaces=None, valid=None, bearer=None):
        body = {'version': self.claim(identity, bearer)['version'], 'decision': decision,
                'replaces_id': replaces, 'replaces_version': self.claim(replaces, bearer)['version'] if replaces else None}
        if valid is not None:
            body.update(valid_from=valid[0], valid_until=valid[1])
        return self.memory.review(bearer or self.owner, identity, body)

    def at(self, moment):
        self.clock[0] = moment

    def entries(self, identity, bearer=None):
        return [(e['state'], e['at'], e['by'], e['origin']) for e in self.history.history(bearer or self.owner, identity)['entries']]

    def raw_history(self, path=None):
        con = sqlite3.connect(path or self.db)
        try:
            return [tuple(r) for r in con.execute('SELECT * FROM memory_claim_history ORDER BY seq')]
        finally:
            con.close()

    def fault(self, code, call, *args):
        with self.assertRaises(Fault) as caught:
            call(*args)
        self.assertEqual(caught.exception.code, code)

    def grant(self, source, revoke=False):
        policy = IdentityPolicy(self.store)
        return policy.grant(self.owner, source, 'read', self.clock[0] + 50000, policy.view(self.owner)['epoch'], revoke=revoke)


class RecordedTimeTests(TemporalBase):
    def test_each_transition_is_recorded_with_its_time_and_reviewer(self):
        made = self.propose('s1', 'status', 2, value='planning')
        for moment, decision in ((2000, 'accept'), (3000, 'dispute'), (4000, 'accept'), (5000, 'withdraw')):
            self.at(moment); self.review(made, decision)
        self.assertEqual(self.entries(made), [('proposed', 1000, 'you', 'recorded'), ('accepted', 2000, 'you', 'recorded'),
                                              ('disputed', 3000, 'you', 'recorded'), ('accepted', 4000, 'you', 'recorded'),
                                              ('withdrawn', 5000, 'you', 'recorded')])
        report = self.history.history(self.owner, made)
        self.assertTrue(report['recorded_from_start']); self.assertEqual(report['times_unknown'], 0)
        self.assertFalse(report['values_in_history']); self.assertFalse(report['authority_granted'])
        self.assertNotIn('planning', str(self.raw_history()))

    def test_supersession_records_both_sides_and_the_lineage_chain(self):
        first = self.propose('s1', 'responsible_person', 4, obj='mina'); self.at(2000); self.review(first, 'accept')
        self.at(3000); second = self.propose('s2', 'responsible_person', 5, obj='orla')
        self.at(4000); self.review(second, 'supersede', replaces=first)
        self.at(5000); third = self.propose('s3', 'responsible_person', 4, obj='mina')
        self.at(6000); self.review(third, 'supersede', replaces=second)
        prior = self.history.history(self.owner, first)['entries'][-1]
        self.assertEqual((prior['state'], prior['at'], prior['related_id']), ('superseded', 4000, second))
        middle = self.history.history(self.owner, second)
        self.assertEqual([x['claim_id'] for x in middle['lineage']['replaces']], [first])
        self.assertEqual([x['claim_id'] for x in middle['lineage']['replaced_by']], [third])
        self.assertEqual(middle['entries'][1]['detail'], 'supersede')
        latest = self.history.history(self.owner, third)
        self.assertEqual([x['claim_id'] for x in latest['lineage']['replaces']], [second, first])
        self.assertEqual([x['state'] for x in latest['lineage']['replaces']], ['superseded', 'superseded'])
        self.assertEqual(latest['lineage']['replaces'][0]['object']['name'], 'Orla')
        from types import SimpleNamespace
        from alfred import console_api
        detail = console_api.record(SimpleNamespace(store=self.store, memory=self.memory), self.owner, 'entity:atlas')
        shown = {s['id']: s for s in detail['statements']}
        self.assertEqual((shown[first]['replacedBy'], shown[second]['replacesId'], shown[second]['replacedBy'], shown[third]['replacedBy']),
                         (second, first, third, None))

    def test_invalidation_is_recorded_by_alfred_and_never_revived(self):
        made = self.propose('s1', 'status', 2, value='planning'); self.at(2000); self.review(made, 'accept')
        self.at(3000); (self.vault / 'Atlas.md').write_text(ATLAS.replace('planning', 'paused')); self.scanner.scan()
        self.memory.view(self.owner)
        self.at(4000); (self.vault / 'Atlas.md').write_text(ATLAS); self.scanner.scan()
        self.memory.view(self.owner); self.memory.view(self.owner)
        self.assertEqual(self.entries(made)[-1], ('invalidated', 3000, 'alfred', 'recorded'))
        self.assertEqual([e[0] for e in self.entries(made)].count('invalidated'), 1)
        self.assertEqual(self.claim(made)['state'], 'invalidated')
        self.fault('memory_source_changed', self.review, made, 'accept')

    def test_withheld_and_restored_are_noticed_without_invalidating(self):
        made = self.propose('s1', 'status', 2, value='planning'); self.at(2000); self.review(made, 'accept')
        self.at(3000); self.grant('other')
        self.memory.view(self.owner); self.memory.view(self.owner)
        report = self.history.history(self.owner, made)
        self.assertEqual([(e['state'], e['by'], e['origin']) for e in report['entries']][-1], ('withheld', 'alfred', 'observed'))
        self.assertEqual([e['state'] for e in report['entries']].count('withheld'), 1)
        self.assertEqual((report['claim']['state'], report['claim']['value'], report['claim']['value_hidden']), ('accepted', None, 'withheld'))
        self.at(3500)
        as_of = self.history.as_of(self.owner, 2500)
        self.assertEqual([(x['claim_id'], x['value'], x['value_hidden']) for x in as_of['held']], [(made, None, 'withheld')])
        self.assertNotIn('planning', json.dumps(report) + json.dumps(as_of) + str(self.raw_history()))
        self.at(4000); self.grant('source')
        restored = self.history.history(self.owner, made)
        self.assertEqual([e['state'] for e in restored['entries']], ['proposed', 'accepted', 'withheld', 'restored'])
        self.assertEqual(restored['claim']['value'], 'planning')
        self.assertNotIn('invalidated', [e['state'] for e in restored['entries']])
        self.assertEqual(self.history.as_of(self.owner, 3200)['held'][0]['availability_then'], 'withheld_noticed')

    def test_forgetting_leaves_identifiers_states_and_times_but_no_value(self):
        made = self.propose('s1', 'status', 2, value='planning'); self.at(2000); self.review(made, 'accept')
        self.at(3000); self.memory.forget(self.owner, made, {'version': self.claim(made)['version']})
        self.assertEqual(self.entries(made)[-1], ('forgotten', 3000, 'you', 'recorded'))
        earlier = self.history.as_of(self.owner, 2500)['held'][0]
        self.assertEqual((earlier['claim_id'], earlier['value'], earlier['value_hidden'], earlier['state_now']), (made, None, 'forgotten', 'forgotten'))
        self.assertNotIn('planning', json.dumps(self.history.history(self.owner, made)) + str(self.raw_history()))

    def test_entity_forgetting_and_source_removal_are_recorded(self):
        lead = self.propose('s1', 'responsible_person', 4, obj='mina'); status = self.propose('s2', 'status', 2, value='planning')
        self.at(2000); self.review(lead, 'accept'); self.review(status, 'accept')
        self.at(3000); self.memory.forget_entity(self.owner, 'mina', {})
        self.at(4000); lifecycle.forget_source(self.store, self.owner, 'source')
        rows = {r[3]: r for r in self.raw_history() if r[4] in ('forgotten', 'invalidated')}
        self.assertEqual((rows[lead][4], rows[lead][5], rows[lead][10]), ('forgotten', 3000, 'entity_forgotten'))
        self.assertEqual((rows[status][4], rows[status][5], rows[status][7], rows[status][10]), ('invalidated', 4000, 'alfred', 'source_removed'))
        self.assertNotIn('planning', str(self.raw_history()))

    def test_restore_replays_a_forget_into_history_without_its_value(self):
        made = self.propose('s1', 'status', 2, value='planning'); self.at(2000); self.review(made, 'accept')
        manifest = lifecycle.backup(self.store, self.owner, self.root / 'backups')
        self.at(3000); self.memory.forget(self.owner, made, {'version': self.claim(made)['version']})
        lifecycle.restore(self.root / 'backups' / manifest['file'], self.db, now=3500)
        restored = KnowledgeStore(self.db, clock=lambda: self.clock[0])
        history = MemoryHistory(ReviewedMemory(restored))
        last = history.history(self.owner, made)['entries'][-1]
        self.assertEqual((last['state'], last['at'], last['origin'], last['by']), ('forgotten', 3000, 'replayed', 'you'))
        self.assertNotIn('planning', str(self.raw_history()))
        con = sqlite3.connect(self.db)
        self.assertIsNone(con.execute('SELECT value FROM memory_claims WHERE id=?', (made,)).fetchone()[0]); con.close()

    def test_restore_of_a_backup_older_than_history_migrates_honestly(self):
        made = self.propose('s1', 'status', 2, value='planning'); self.at(2000); self.review(made, 'accept')
        manifest = lifecycle.backup(self.store, self.owner, self.root / 'backups')
        old = self.root / 'backups' / manifest['file']
        con = sqlite3.connect(old); con.executescript('DROP TABLE memory_claim_history; DROP TABLE memory_history_meta;'); con.close()
        meta = old.with_suffix('.json'); value = json.loads(meta.read_text())
        value['sha256'] = hashlib.sha256(old.read_bytes()).hexdigest(); meta.write_text(json.dumps(value))
        self.at(3000); self.memory.forget(self.owner, made, {'version': self.claim(made)['version']})
        lifecycle.restore(old, self.db, now=3500)
        self.at(4000)
        restored = KnowledgeStore(self.db, clock=lambda: self.clock[0])
        entries = MemoryHistory(ReviewedMemory(restored)).history(self.owner, made)['entries']
        self.assertEqual([(e['state'], e['at'], e['time_known'], e['origin']) for e in entries],
                         [('proposed', 1000, True, 'migrated'), ('accepted', 2000, True, 'migrated'), ('forgotten', 4000, False, 'migrated')])
        self.assertNotIn('planning', str(self.raw_history()))

    def test_history_capacity_bounds_reviews_but_never_blocks_forgetting(self):
        made = self.propose('s1', 'status', 2, value='planning')
        with mock.patch.object(memory_history, 'MAX_HISTORY_PER_CLAIM', 3):
            self.review(made, 'accept'); self.review(made, 'dispute')
            self.fault('memory_history_capacity', self.review, made, 'accept')
            self.memory.forget(self.owner, made, {'version': self.claim(made)['version']})
        self.assertEqual(self.entries(made)[-1][0], 'forgotten')


class MigrationTests(TemporalBase):
    def drop_history(self):
        with self.store.connection() as db:
            db.executescript('DROP TABLE memory_claim_history; DROP TABLE memory_history_meta;')

    def test_migration_reconstructs_from_audit_and_marks_unknown_times(self):
        second_vault = self.root / 'second'; second_vault.mkdir()
        (second_vault / 'Borealis.md').write_text('# Borealis\nBorealis is planning.\n')
        second = self.store.provision('work', 'second', 'source', ttl=900000)
        MarkdownVault(self.store, second, second_vault).scan()
        status = self.propose('s1', 'status', 2, value='planning')
        self.at(2000); self.review(status, 'accept'); self.at(3000); self.review(status, 'dispute'); self.at(4000); self.review(status, 'accept')
        lead = self.propose('s2', 'responsible_person', 4, obj='mina'); self.review(lead, 'accept')
        self.at(5000); replacement = self.propose('s3', 'responsible_person', 5, obj='orla'); self.review(replacement, 'supersede', replaces=lead)
        borealis = next(n for n in self.store.knowledge(self.owner)['nodes'] if n['title'] == 'Borealis')
        gone = self.memory.propose(self.owner, {'request_id': 's4', 'subject_id': 'atlas', 'predicate': 'decision', 'object_id': None,
                                                'value': 'go ahead', 'valid_from': None, 'valid_until': None,
                                                'evidence': {'note_id': borealis['id'], 'sha256': borealis['sha256'], 'revision': borealis['revision'],
                                                             'start_line': 2, 'end_line': 2}})['id']
        self.at(6000); self.review(gone, 'accept')
        self.at(7000); lifecycle.forget_source(self.store, self.owner, 'second')
        recorded = {c: self.entries(c) for c in (status, lead, replacement, gone)}
        self.drop_history()
        self.at(9000); memory = ReviewedMemory(self.store); history = MemoryHistory(memory)
        migrated = lambda c: [(e['state'], e['at'], e['time_known'], e['origin']) for e in history.history(self.owner, c)['entries']]
        self.assertEqual(migrated(status), [(s, t, True, 'migrated') for s, t, _, _ in recorded[status]])
        self.assertEqual(migrated(lead)[-1], ('superseded', 5000, True, 'migrated'))
        self.assertEqual(history.history(self.owner, lead)['entries'][-1]['related_id'], replacement)
        # The source removal left no per-statement audit entry, so its time is not invented.
        self.assertEqual(migrated(gone), [('proposed', 5000, True, 'migrated'), ('accepted', 6000, True, 'migrated'),
                                          ('invalidated', 9000, False, 'migrated')])
        self.assertEqual(history.history(self.owner, gone)['entries'][-1]['by'], 'alfred')
        self.assertEqual([x['claim_id'] for x in history.as_of(self.owner, 8000)['uncertain']], [gone])
        self.assertEqual(history.as_of(self.owner, 9000)['not_held']['invalidated'], 1)
        self.assertIn(gone, [x['claim_id'] for x in history.as_of(self.owner, 6500)['uncertain']])
        # Migration runs once, and live recording continues afterwards.
        before = len(self.raw_history()); ReviewedMemory(self.store); self.assertEqual(len(self.raw_history()), before)
        self.at(9500); self.review(status, 'dispute')
        self.assertEqual(history.history(self.owner, status)['entries'][-1]['origin'], 'recorded')

    def test_without_audit_the_last_review_time_is_only_an_upper_bound(self):
        made = self.propose('s1', 'status', 2, value='planning')
        self.at(2000); self.review(made, 'accept'); self.at(3000); self.review(made, 'accept')
        with self.store.connection() as db:
            db.execute('DELETE FROM audit WHERE subject=?', (made,))
        self.drop_history()
        self.at(4000); history = MemoryHistory(ReviewedMemory(self.store))
        self.assertEqual([(e['state'], e['at'], e['time_known']) for e in history.history(self.owner, made)['entries']],
                         [('proposed', 1000, True), ('accepted', 3000, False)])
        self.assertEqual([x['claim_id'] for x in history.as_of(self.owner, 2500)['uncertain']], [made])
        held = history.as_of(self.owner, 3500)['held']
        self.assertEqual([(x['claim_id'], x['since'], x['since_known']) for x in held], [(made, 3000, False)])


class ValidTimeTests(TemporalBase):
    def test_a_proposal_carries_and_validates_its_valid_period(self):
        self.fault('invalid_memory_validity', self.propose, 's1', 'status', 2, 'planning', None, (5000, 5000))
        made = self.propose('s2', 'status', 2, value='planning', valid=(1500, 9000))
        entry = self.history.history(self.owner, made)['entries'][0]
        self.assertEqual(entry['valid_period'], {'from': 1500, 'until': 9000})

    def test_review_sets_the_valid_period_once_while_proposed(self):
        made = self.propose('s1', 'status', 2, value='planning')
        for valid, code in (((9000, 8000), 'invalid_memory_validity'), ((-1, None), 'invalid_timestamp')):
            self.fault(code, self.review, made, 'accept', None, valid)
        self.fault('unexpected_memory_validity', self.review, made, 'dispute', None, (1000, None))
        self.fault('invalid_fields', self.memory.review, self.owner, made, {'version': 1, 'decision': 'accept', 'replaces_id': None,
                                                                            'replaces_version': None, 'valid_from': None})
        self.at(2000); self.review(made, 'accept', valid=(1500, 6000))
        claim = self.claim(made)
        self.assertEqual((claim['valid_from'], claim['valid_until'], claim['usable']), (1500, 6000, True))
        self.assertEqual(self.history.history(self.owner, made)['entries'][1]['valid_period'], {'from': 1500, 'until': 6000})
        self.fault('memory_validity_fixed', self.review, made, 'accept', None, (1500, 7000))
        self.review(made, 'accept', valid=(1500, 6000))  # Restating the same period changes nothing.
        self.assertIsNone(self.history.history(self.owner, made)['entries'][-1]['valid_period'])

    def test_supersession_can_carry_the_replacement_valid_period(self):
        first = self.propose('s1', 'responsible_person', 4, obj='mina'); self.at(2000); self.review(first, 'accept')
        self.at(3000); second = self.propose('s2', 'responsible_person', 5, obj='orla')
        self.at(4000); self.review(second, 'supersede', replaces=first, valid=(5000, None))
        self.assertEqual(self.claim(second)['valid_from'], 5000)
        self.assertFalse(self.claim(second)['usable'])  # Not yet valid: the existing rule still applies.
        self.at(5000); self.assertTrue(self.claim(second)['usable'])

    def test_statements_outside_their_valid_period_keep_the_existing_rules(self):
        made = self.propose('s1', 'status', 2, value='planning', valid=(None, 3000)); self.at(2000); self.review(made, 'accept')
        self.assertTrue(self.claim(made)['usable'])
        self.at(4000)
        self.assertFalse(self.claim(made)['usable'])
        self.assertEqual(retrieve(self.store, self.owner, 'What is the Atlas status planning?')['memory'], [])
        self.assertEqual([x['claim_id'] for x in self.history.as_of(self.owner, 2500)['held']], [made])
        self.assertEqual([x['claim_id'] for x in self.history.as_of(self.owner, 3500)['accepted_outside_valid_period']], [made])
        self.assertEqual([x['claim_id'] for x in self.history.as_of(self.owner, 3500, 2500)['held']], [made])


class AsOfTests(TemporalBase):
    def scenario(self):
        first = self.propose('s1', 'status', 2, value='planning'); self.at(2000); self.review(first, 'accept')
        self.at(3000); second = self.propose('s2', 'status', 3, value='filming', valid=(3500, None))
        self.at(4000); self.review(second, 'supersede', replaces=first)
        self.at(5000)
        return first, second

    def test_as_of_answers_from_recorded_history_and_valid_time(self):
        first, second = self.scenario()
        before = self.history.as_of(self.owner, 1500)
        self.assertEqual((before['held'], before['not_held']['proposed'], before['not_yet_recorded']), ([], 1, 1))
        self.assertEqual([(x['value'], x['since'], x['state_now'], x['replaced_by']) for x in self.history.as_of(self.owner, 2500)['held']],
                         [('planning', 2000, 'superseded', second)])
        after = self.history.as_of(self.owner, 4500)
        self.assertEqual([x['value'] for x in after['held']], ['filming']); self.assertEqual(after['not_held']['superseded'], 1)
        self.assertEqual([x['value'] for x in self.history.as_of(self.owner, 4500, 3200)['accepted_outside_valid_period']], ['filming'])
        self.assertEqual((after['kind'], after['basis'], after['model_used'], after['authority_granted']),
                         ('historical_report', memory_history.BASIS, False, False))
        self.assertIn('not a statement about what was true in the world', after['label'])

    def test_as_of_is_deterministic_and_clamps_to_now(self):
        self.scenario()
        strip = lambda r: {k: v for k, v in r.items() if k != 'generated_at'}
        self.assertEqual(strip(self.history.as_of(self.owner, 4500)), strip(self.history.as_of(self.owner, 4500)))
        future = self.history.as_of(self.owner, 10 ** 9)
        self.assertEqual((future['at'], future['clamped_to_now']), (5000, True))
        self.fault('invalid_timestamp', self.history.as_of, self.owner, -5)

    def test_as_of_applies_the_single_value_rule_to_what_was_held_then(self):
        mina = self.propose('s1', 'responsible_person', 4, obj='mina'); orla = self.propose('s2', 'responsible_person', 5, obj='orla')
        self.at(2000); self.review(mina, 'accept'); self.review(orla, 'accept')
        self.assertEqual(self.claim(mina)['conflicts'], [orla])
        held = {x['claim_id']: x for x in self.history.as_of(self.owner, 2500)['held']}
        self.assertEqual((held[mina]['conflicts_then'], held[orla]['conflicts_then']), ([orla], [mina]))
        self.at(3000); self.memory.forget(self.owner, orla, {'version': self.claim(orla)['version']})
        held = {x['claim_id']: x for x in self.history.as_of(self.owner, 2500)['held']}
        self.assertEqual((held[mina]['conflicts_then'], held[mina]['possible_conflicts_then']), ([], [orla]))

    def test_namesakes_stay_separate_in_history_and_supersession(self):
        mina = self.propose('s1', 'status', 4, value='leads Atlas', subject='mina')
        namesake = self.propose('s2', 'status', 4, value='leads Atlas', subject='mina-two')
        self.at(2000); self.review(mina, 'accept'); self.review(namesake, 'accept')
        held = self.history.as_of(self.owner, 2500)['held']
        self.assertEqual(sorted(x['subject']['id'] for x in held), ['mina', 'mina-two'])
        self.assertEqual(held[0]['conflicts_then'] + held[1]['conflicts_then'], [])
        self.at(3000); replacement = self.propose('s3', 'status', 5, value='leads Orla', subject='mina-two')
        self.fault('memory_replacement_mismatch', self.review, replacement, 'supersede', mina)

    def test_current_answers_are_unchanged_and_reports_write_no_review(self):
        first, second = self.scenario()
        packet = retrieve(self.store, self.owner, 'What is the Atlas status filming planning?')
        self.assertEqual([m['claim_id'] for m in packet['memory']], [second])
        versions = {c['id']: c['version'] for c in self.memory.view(self.owner)['claims']}
        self.history.as_of(self.owner, 2500); self.history.history(self.owner, first)
        self.assertEqual({c['id']: c['version'] for c in self.memory.view(self.owner)['claims']}, versions)

    def test_other_people_and_workspaces_see_nothing(self):
        first, _ = self.scenario()
        for bearer in (self.owner2, self.reader, self.elsewhere):
            self.fault('memory_claim_not_found', self.history.history, bearer, first)
            report = self.history.as_of(bearer, 4500)
            self.assertEqual((report['held'], report['uncertain'], report['without_history']), ([], [], 0))
        self.fault('memory_claim_not_found', self.history.history, self.owner, 'claim-unknown')
        self.fault('invalid_identifier', self.history.history, self.owner, '../x')


class TemporalHTTPTests(unittest.TestCase):
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
        if origin:
            headers['Origin'] = origin
        if data is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': origin or self.server.origin})
            if csrf and self.csrf: headers['X-CSRF-Token'] = self.csrf
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); body = json.loads(r.read()); cookie = r.getheader('Set-Cookie'); c.close()
        return r.status, body, cookie

    def login(self, role):
        _, data, cookie = self.req('/desk/login', {'key': self.keys[role]}); self.cookie = cookie.split(';')[0]; self.csrf = data['csrf']

    def test_review_history_and_as_of_over_http(self):
        self.assertEqual(self.req('/desk/memory/as-of/1')[0], 401)
        self.login('owner')
        self.req('/desk/memory/entities', {'id': 'film', 'kind': 'project', 'name': 'Sample film'})
        n = next(x for x in self.req('/desk/knowledge')[1]['nodes'] if x['title'] == 'Sample film')
        body = {'request_id': 'h1', 'subject_id': 'film', 'predicate': 'status', 'object_id': None, 'value': 'in pre-production',
                'valid_from': None, 'valid_until': None,
                'evidence': {'note_id': n['id'], 'sha256': n['sha256'], 'revision': n['revision'], 'start_line': 8, 'end_line': 8}}
        made = self.req('/desk/memory/proposals', body)[1]['id']
        decision = {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None, 'valid_from': 1000, 'valid_until': None}
        self.assertEqual(self.req(f'/desk/memory/claims/{made}/review', decision, csrf=False)[0], 403)
        self.assertEqual(self.req(f'/desk/memory/claims/{made}/review', decision)[0], 200)
        code, history, _ = self.req(f'/desk/memory/claims/{made}/history')
        self.assertEqual((code, [e['state'] for e in history['entries']]), (200, ['proposed', 'accepted']))
        self.assertEqual(history['entries'][1]['valid_period'], {'from': 1000, 'until': None})
        now = self.store.now()
        code, report, _ = self.req(f'/desk/memory/as-of/{now}')
        self.assertEqual((code, [x['claim_id'] for x in report['held']]), (200, [made]))
        self.assertEqual(self.req(f'/desk/memory/as-of/{now}/valid/500')[1]['accepted_outside_valid_period'][0]['claim_id'], made)
        record = self.req('/desk/console/records/entity:film')[1]['statements'][0]
        from alfred.console_api import _iso
        self.assertEqual((record['replacedBy'], record['recordedAt']), (None, _iso(history['entries'][0]['at'])))
        for path, code in ((f'/desk/memory/as-of/{now}?x=1', 404), ('/desk/memory/as-of/abc', 404), ('/desk/memory/as-of/', 404),
                           (f'/desk/memory/claims/{made}/history?valid=1', 404), ('/desk/memory/claims/../history', 404)):
            self.assertEqual(self.req(path)[0], code, path)
        self.assertEqual(self.req(f'/desk/memory/as-of/{now}', origin='http://example.invalid')[0], 403)
        self.assertEqual(self.req(f'/desk/memory/claims/{made}/history', {})[0], 404)
        self.login('reader')
        self.assertEqual(self.req(f'/desk/memory/claims/{made}/history'), (404, {'error': 'memory_claim_not_found'}, None))
        self.assertEqual(self.req(f'/desk/memory/as-of/{now}')[1]['held'], [])


if __name__ == '__main__':
    unittest.main()
