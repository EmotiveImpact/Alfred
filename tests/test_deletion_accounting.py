"""MEM-010, MEM-013, M05: deletion and restore accounting.

One synthetic workspace holds every kind of dependent a subject can have: reviewed
statements with history and a capture, a routine nomination, a saved answer with a
voice playback record, drafts in several ledger states (one set to an arbitrary
'archived' state, so counting stays generic), a desk event and document, a job result
and its cache copy, an executive record citing the note, an export on disk and a
backup. Forget, backup, restore and export run over it, and every receipt and report
is compared with a direct database scan written here, independently of the scanner.

Synthetic data only, real SQLite and the real HTTP boundary. No model.
"""
import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from alfred import deletion, desk, lifecycle
from alfred.conversation import ConversationService
from alfred.executive import ExecutiveRecords
from alfred.export import export
from alfred.jobs import BoundedCache, JobCoordinator, JobWorker, LocalSubprocessBackend
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.local import Fault
from alfred.reviewed_memory import ReviewedMemory
from alfred.routines import Routines
import stored_helpers as stored
from alfred.voice import VoiceLog
from grant_helpers import grant_all, person_of

T = 1_900_000_000  # 2030-03-17 17:46:40 UTC
ATLAS = '# Atlas\nAtlas is awaiting review.\nMina leads Atlas.\nCrew call 2030-03-17.\nLaunch in spring.\n'


class Workspace(unittest.TestCase):
    """A workspace with every kind of dependent for the Atlas note and its statements."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.clock = [T]
        self.db = self.root / 'desk.sqlite'
        self.store = KnowledgeStore(self.db, clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=2592000)
        self.reader = self.store.provision('work', 'reader', 'reader', ttl=2592000)
        self.source = self.store.provision('work', 'source', 'source', ttl=2592000)
        grant_all(self.store, self.owner)
        project = self.root / 'project'; project.mkdir()
        (project / 'schedule.json').write_text(json.dumps({
            'document_id': 'schedule', 'title': 'Call time has changed', 'revision': 1, 'observed_at': T - 30,
            'expires_at': T + 3600, 'summary': 'The synthetic call moved from 09:30 to 10:00.'}))
        self.vault = self.root / 'vault'; self.vault.mkdir()
        (self.vault / 'Atlas.md').write_text(ATLAS)
        self.sup = KnowledgeSupervisor(self.store, self.owner, self.source, project, vault=self.vault)
        self.sup.cycle()
        self.note = next(n for n in self.store.knowledge(self.owner)['nodes'] if n['path'] == 'Atlas.md')
        self.memory = ReviewedMemory(self.store)
        self.memory.create_entity(self.owner, {'id': 'atlas', 'kind': 'project', 'name': 'Atlas'})
        self.memory.create_entity(self.owner, {'id': 'mina', 'kind': 'person', 'name': 'Mina'})
        self.status = self.accept('s1', 'status', 2, value='awaiting review')
        self.lead = self.accept('s2', 'responsible_person', 3, obj='mina')
        made = self.memory.capture(self.owner, {**self.claim_body('c1', 'scheduled_for', 4, value='2030-03-17'),
                                                'memory_type': 'commitment', 'retention_days': None,
                                                'captured_from': {'note_id': self.note['id']}})
        self.memory.review(self.owner, made['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        self.commitment = made['id']
        # A routine nominates a reminder citing the commitment statement.
        self.routines = Routines(self.store, self.sup); self.sup.routines = self.routines
        self.routines.configure(self.owner, 'commitment-review', {
            'version': 0, 'enabled': True, 'schedule': {'every_hours': 1}, 'utc_offset_minutes': 0, 'runs_per_day': 24,
            'nominations_per_run': 10, 'quiet_hours': None, 'interrupt': 'show_now', 'propose_drafts': False})
        self.routines.manual(self.owner, 'commitment-review', {'request_id': 'run-1'})
        # A saved answer, a playback record and drafts in several ledger states.
        self.service = ConversationService(self.store, None, 'work'); self.addCleanup(self.service.stop)
        self.sid = self.service.create(self.owner, {'title': 'Atlas'})['id']
        self.service.submit(self.owner, self.sid, {'question': 'What is the Atlas status?', 'mode': 'sources', 'follow_up': False,
                                                   'request_id': 'q1', 'after': 0})
        self.service.process_one()
        self.turn = self.service.view(self.owner, self.sid)['turns'][0]
        self.assertIn(self.status, [m['claim_id'] for m in self.turn['result']['packet']['memory']])
        VoiceLog(self.store).generated(self.owner, {'turn_id': self.turn['id'], 'text_sha256': 'a' * 64, 'characters': 12,
                                                    'voice_local': True})
        self.drafts = [self.service.propose_draft(self.owner, self.sid, {'turn_id': self.turn['id'], 'text': f'Atlas update {i}.',
                                                                         'request_id': f'draft-{i}'})['id'] for i in range(3)]
        done = next(a for a in self.store.desk_state(self.owner)['actions'] if a['id'] == self.drafts[1])
        self.store.approve(self.owner, done['id'], done['fingerprint']); self.store.tick(self.owner)
        with self.store.transaction() as db:
            # Another change may add archived drafts; any ledger state must be counted.
            db.execute("UPDATE actions SET state='archived' WHERE id=?", (self.drafts[2],))
        # A job result from the note, mirrored into the cache.
        self.cache = BoundedCache(self.root / 'job-cache', 1 << 20)
        jobs = JobCoordinator(self.store, cache=self.cache)
        jobs.enrol_worker(self.owner, 'local-1', 'Local worker', ['summarise_lines'])
        job = jobs.submit(self.owner, {'idempotency_key': 'j1', 'kind': 'summarise_lines', 'parameters': {'max_lines': 2},
                                       'inputs': [{'note': self.note['id']}], 'side_effect_free': True})
        JobWorker(jobs, LocalSubprocessBackend(wall_clock=10), self.owner, 'local-1').run_once()
        self.result = jobs.view(self.owner, job['id'])['result']['sha256']
        jobs.artefact(self.owner, self.result)
        ExecutiveRecords(self.store).create(self.owner, {
            'request_id': 'e1', 'kind': 'commitment', 'title': 'Send the synthetic brief', 'detail': '', 'project': None,
            'due': None, 'rank': None, 'support': {'note_id': self.note['id'], 'sha256': self.note['sha256'],
                                                    'revision': self.note['revision'], 'start_line': 5, 'end_line': 5}})
        self.export_dir = self.root / 'export-1'
        export(self.store, self.owner, self.export_dir)
        self.backup = lifecycle.backup(self.store, self.owner, self.root / 'backups')
        self.clock[0] += 60

    def claim_body(self, request, predicate, line, value=None, obj=None):
        return {'request_id': request, 'subject_id': 'atlas', 'predicate': predicate, 'object_id': obj, 'value': value,
                'valid_from': None, 'valid_until': None,
                'evidence': {'note_id': self.note['id'], 'sha256': self.note['sha256'], 'revision': self.note['revision'],
                             'start_line': line, 'end_line': line}}

    def accept(self, request, predicate, line, value=None, obj=None):
        made = self.memory.propose(self.owner, self.claim_body(request, predicate, line, value, obj))
        self.memory.review(self.owner, made['id'], {'version': 1, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        return made['id']

    def version(self, identity):
        return next(c for c in self.memory.view(self.owner)['claims'] if c['id'] == identity)['version']

    # The direct scan: plain SQL and file checks, written without the scanner.

    def count(self, sql, *args, store=None):
        with (store or self.store).connection() as db:
            return db.execute(sql, args).fetchone()[0]

    def binned(self, identity, store=None):
        """Copies in the bin that name the identifier, read opened so a sealed workspace counts the same."""
        return sum(f'"{identity}"' in r['snapshot'] for r in stored.rows(store or self.store, 'memory_bin', 'SELECT id,snapshot FROM memory_bin'))

    def unredacted(self, source, store=None):
        """The source's desk observations still holding their summary or title, read opened so a
        sealed workspace counts the same."""
        store = store or self.store
        bodies = stored.rows(store, 'events', 'SELECT seq,body FROM events WHERE source=?', (source,))
        titles = stored.rows(store, 'desk_documents', 'SELECT scope,source,document_id,title FROM desk_documents WHERE source=?', (source,))
        titles += stored.rows(store, 'desk_links', 'SELECT seq,title FROM desk_links WHERE seq IN (SELECT seq FROM events WHERE source=?)', (source,))
        return (sum(json.loads(r['body'])['summary'] != lifecycle.REMOVED for r in bodies)
                + sum(r['title'] != lifecycle.REMOVED for r in titles))

    def exports_holding(self, claims):
        held = 0
        for directory in self.root.glob('export-*'):
            ids = {s['id'] for s in json.loads((directory / 'statements.json').read_text())['statements']}
            held += bool(ids & set(claims))
        return held

    def direct_statement(self, claim, store=None):
        c = lambda sql, *a: self.count(sql, *a, store=store)
        turn, drafts = self.turn['id'], self.drafts
        marks = ','.join('?' * len(drafts))
        return {
            'statements': (c('SELECT count(*) FROM memory_claims WHERE id=?', claim),
                           c('SELECT count(*) FROM memory_claims WHERE id=? AND (value IS NOT NULL OR object_id IS NOT NULL)', claim)),
            'captures': (c('SELECT count(*) FROM memory_capture WHERE claim_id=?', claim), 0),
            'bin_copies': (self.binned(claim, store),) * 2,
            'answers': (c('SELECT count(*) FROM conversation_turns WHERE id=?', turn),
                        c('SELECT count(*) FROM conversation_turns WHERE id=? AND result IS NOT NULL', turn)),
            'voice_playbacks': (c('SELECT count(*) FROM voice_playbacks WHERE turn_id=?', turn), 0),
            'drafts': (c(f'SELECT count(*) FROM actions WHERE id IN ({marks})', *drafts),
                       c(f'SELECT count(*) FROM drafts WHERE action_id IN ({marks})', *drafts)),
            'routine_nominations': (c("SELECT count(*) FROM routine_nominations WHERE cite_kind='statement' AND cite_id=?", claim), 0),
            'history_rows': (c('SELECT count(*) FROM memory_claim_history WHERE claim_id=?', claim), 0),
            'audit_rows': (c('SELECT count(*) FROM audit WHERE subject=?', claim), 0),
            'lifecycle_receipts': (c('SELECT count(*) FROM lifecycle_receipts WHERE subject=?', claim), 0),
            'exports_on_disk': (self.exports_holding([claim]),) * 2,
            'backups': (len(list((self.root / 'backups').glob('*.sqlite'))),) * 2,
        }

    def direct_source(self, source='source', store=None):
        c = lambda sql, *a: self.count(sql, *a, store=store)
        note = self.note['id']
        claims = (self.status, self.lead, self.commitment)
        index = sum(c(f'SELECT count(*) FROM {t} WHERE source=?', source) for t in deletion.INDEX_TABLES)
        cache = (self.root / 'job-cache' / 'objects' / self.result[:2] / self.result).is_file()
        return {
            'statements': (c('SELECT count(*) FROM memory_claims WHERE note_id=?', note),
                           c('SELECT count(*) FROM memory_claims WHERE note_id=? AND (value IS NOT NULL OR object_id IS NOT NULL)', note)),
            'source_index': (index, index),
            'bin_copies': (self.binned(note, store),) * 2,
            'tombstones': (c('SELECT count(*) FROM memory_tombstones WHERE source=?', source), 0),
            'evidence_events': (c('SELECT count(*) FROM events WHERE source=?', source) + c('SELECT count(*) FROM desk_documents WHERE source=?', source)
                                + c('SELECT count(*) FROM desk_links WHERE seq IN (SELECT seq FROM events WHERE source=?)', source),
                                self.unredacted(source, store)),
            'answers': (c('SELECT count(*) FROM conversation_turns WHERE id=?', self.turn['id']),
                        c('SELECT count(*) FROM conversation_turns WHERE id=? AND result IS NOT NULL', self.turn['id'])),
            'drafts': (c(f"SELECT count(*) FROM actions WHERE id IN ({','.join('?' * 3)})", *self.drafts),
                       c(f"SELECT count(*) FROM drafts WHERE action_id IN ({','.join('?' * 3)})", *self.drafts)),
            'executive_citations': (c("SELECT count(*) FROM executive_records WHERE json_extract(support,'$.note_id')=?", note), 0),
            'job_artefacts': (c('SELECT count(*) FROM artefacts WHERE sha256=?', self.result),) * 2,
            'jobs': (c("SELECT count(*) FROM jobs WHERE inputs LIKE ?", f'%"source": "{source}"%')
                     or c("SELECT count(*) FROM jobs WHERE inputs LIKE ?", f'%"source":"{source}"%'), 0),
            'cache_copies': (int(cache),) * 2,
            'history_rows': (c(f"SELECT count(*) FROM memory_claim_history WHERE claim_id IN ({','.join('?' * 3)})", *claims), 0),
            'exports_on_disk': (self.exports_holding(claims),) * 2,
        }

    def assert_agrees(self, held, direct, label):
        for name, (count, holding) in direct.items():
            with self.subTest(label=label, category=name):
                self.assertEqual((held[name]['count'], held[name]['holding_value']), (count, holding))

    def assert_receipt_matches_report(self, receipt, report):
        self.assertEqual(set(receipt['accounting']), set(report['held']))
        for name, row in receipt['accounting'].items():
            with self.subTest(category=name):
                self.assertEqual(row['after'], {'count': report['held'][name]['count'],
                                                'holding_value': report['held'][name]['holding_value']})


class ForgetReceiptTests(Workspace):
    def test_fixture_holds_every_kind_of_dependent(self):
        report = deletion.report(self.store, self.owner, 'source', 'source', cache_dir=self.cache.root)
        for name in ('statements', 'captures', 'source_index', 'evidence_events', 'answers', 'voice_playbacks', 'drafts',
                     'routine_nominations', 'executive_citations', 'job_artefacts', 'jobs', 'cache_copies', 'history_rows',
                     'exports_on_disk', 'backups'):
            with self.subTest(category=name):
                self.assertGreater(report['held'][name]['count'], 0)
        self.assertEqual(report['held']['drafts']['by_state'], {'archived': 1, 'proposed': 1, 'verified': 1})
        self.assertEqual(report['not_checked'], [])
        self.assert_agrees(report['held'], self.direct_source(), 'before')

    def test_statement_forget_receipt_and_report_agree_with_a_direct_scan(self):
        before = self.direct_statement(self.status)
        receipt = self.memory.forget(self.owner, self.status, {'version': self.version(self.status)})
        report = deletion.report(self.store, self.owner, 'statement', self.status)
        after = self.direct_statement(self.status)
        self.assert_agrees({k: {'count': v['before']['count'], 'holding_value': v['before']['holding_value']}
                            for k, v in receipt['accounting'].items()},
                           {k: v for k, v in before.items() if k not in ('audit_rows', 'lifecycle_receipts')}, 'receipt before')
        self.assert_receipt_matches_report(receipt, report)
        self.assert_agrees(report['held'], after, 'report')
        # The value is gone; the answer is withdrawn but its question stays; drafts are counted in every state.
        self.assertEqual(after['statements'], (1, 0))
        self.assertEqual(after['answers'], (1, 0))
        self.assertEqual(receipt['accounting']['drafts']['by_state'], {'archived': 1, 'cancelled': 1, 'verified': 1})
        self.assertEqual(receipt['pending_actions_cancelled'], [self.drafts[0]])
        self.assertEqual(receipt['statements_forgotten'], 1)
        # Value-free history is kept by default, and the old export and backup are named, not deleted.
        self.assertEqual(receipt['history'], 'value_free_rows_kept')
        self.assertGreater(after['history_rows'][0], 0)
        self.assertEqual([e['directory'] for e in receipt['accounting']['exports_on_disk']['exports']], [str(self.export_dir)])
        self.assertTrue((self.export_dir / 'manifest.json').is_file())
        # An ordinary forget keeps a copy in the bin for undo, and the receipt counts it.
        self.assertEqual(receipt['still_holding_value'], {'bin_copies': 1, 'drafts': 1, 'exports_on_disk': 1, 'backups': 1})
        self.assertEqual((after['bin_copies'], receipt['layer']), ((1, 1), 'ordinary'))
        self.assertNotIn('awaiting review', json.dumps(receipt) + json.dumps(report))
        self.assertEqual(receipt, lifecycle.receipts(self.store, self.owner)['receipts'][0])

    def test_source_forget_receipt_and_report_agree_with_a_direct_scan(self):
        receipt = lifecycle.forget_source(self.store, self.owner, 'source', cache=self.cache)
        report = deletion.report(self.store, self.owner, 'source', 'source', cache_dir=self.cache.root)
        self.assert_receipt_matches_report(receipt, report)
        direct = self.direct_source()
        self.assert_agrees(report['held'], direct, 'after')
        self.assertEqual(direct['statements'], (3, 0))
        self.assertEqual((direct['source_index'], direct['job_artefacts'], direct['cache_copies']), ((0, 0), (0, 0), (0, 0)))
        self.assertEqual(direct['evidence_events'][1], 0)
        self.assertEqual(receipt['accounting']['job_artefacts']['before'], {'count': 1, 'holding_value': 1})
        self.assertEqual(receipt['accounting']['cache_copies']['before'], {'count': 1, 'holding_value': 1})
        self.assertEqual(receipt['cached_results_removed'], 1)
        self.assertGreaterEqual(receipt['dependents_found'], 20)
        stored = lifecycle.receipts(self.store, self.owner)['receipts'][0]
        self.assertEqual(stored['accounting']['cache_copies']['after'], {'count': 0, 'holding_value': 0})

    def test_entity_forget_counts_its_statements_and_name(self):
        receipt = self.memory.forget_entity(self.owner, 'mina', {})
        self.assertEqual(receipt['accounting']['entity_name'], {'before': {'count': 1, 'holding_value': 1},
                                                                'after': {'count': 0, 'holding_value': 0}, 'where': ['memory_entities']})
        self.assertEqual(receipt['accounting']['statements']['after'], {'count': 1, 'holding_value': 0})
        self.assertEqual((receipt['entities_removed'], receipt['statements_forgotten']), (1, 1))
        self.assert_receipt_matches_report(receipt, deletion.report(self.store, self.owner, 'entity', 'mina'))
        self.assertEqual(self.count('SELECT count(*) FROM memory_claims WHERE id=? AND object_id IS NULL AND value IS NULL', self.lead), 1)

    def test_purge_is_explicit_journalled_and_replayed(self):
        with self.assertRaises(Fault):
            self.memory.forget(self.owner, self.status, {'version': self.version(self.status), 'purge_history': 'yes'})
        receipt = self.memory.forget(self.owner, self.status, {'version': self.version(self.status), 'purge_history': True,
                                                               'absolute': True, 'confirm': self.status})
        self.assertEqual(receipt['history'], 'purged')
        self.assertGreater(receipt['history_rows_purged'], 0)
        self.assertEqual(receipt['accounting']['history_rows']['after']['count'], 0)
        self.assertEqual(self.count('SELECT count(*) FROM memory_claim_history WHERE claim_id=?', self.status), 0)
        self.assertTrue(lifecycle.entries(lifecycle.journal_path(self.store))[-1]['purge_history'])
        result = lifecycle.restore(self.root / 'backups' / self.backup['file'], self.db)
        restored = KnowledgeStore(self.db, clock=lambda: self.clock[0])
        self.assertEqual(self.count('SELECT count(*) FROM memory_claim_history WHERE claim_id=?', self.status, store=restored), 0)
        self.assertGreater(result['removed_again']['totals']['history_rows_purged'], 0)

    def test_report_is_owner_only_and_never_shows_values(self):
        with self.assertRaises(Fault) as caught:
            deletion.report(self.store, self.reader, 'source', 'source')
        self.assertEqual(caught.exception.code, 'forbidden')
        with self.assertRaises(Fault):
            deletion.report(self.store, self.owner, 'person', 'source')
        report = deletion.report(self.store, self.owner, 'entity', 'atlas')
        self.assertFalse(report['values_included'] or report['secure_erasure'])
        self.assertNotIn('awaiting review', json.dumps(report))
        # Another person's statements are private: the reader's view of the same entity id is empty.
        reader_owner = self.store.provision('work', 'second-owner', 'owner', ttl=2592000)
        self.assertEqual(deletion.report(self.store, reader_owner, 'statement', self.status)['held']['statements']['count'], 0)


class RestoreAccountingTests(Workspace):
    def test_restore_reports_what_the_journal_removed_again(self):
        # Absolute forgets are applied again on restore; ordinary ones come back (tests/test_two_layer_delete.py).
        self.memory.forget(self.owner, self.status, {'version': self.version(self.status), 'absolute': True, 'confirm': self.status})
        self.memory.forget_entity(self.owner, 'mina', {'absolute': True, 'confirm': 'mina'})
        lifecycle.forget_source(self.store, self.owner, 'source', cache=self.cache, absolute=True)
        self.store.revoke('reader')
        result = lifecycle.restore(self.root / 'backups' / self.backup['file'], self.db, cache=self.cache)
        again = result['removed_again']
        kinds = [(e['kind'], e['subject']) for e in again['entries']]
        self.assertEqual(kinds, [('claim_forgotten', self.status), ('entity_forgotten', 'mina'),
                                 ('source_forgotten', 'source'), ('credential_revoked', 'reader')])
        first = again['entries'][0]['removed']
        self.assertEqual((first['statements_forgotten'], first['conversation_answers_withdrawn'], first['pending_actions_cancelled']), (1, 1, 1))
        self.assertEqual(again['entries'][1]['removed'], {'statements_forgotten': 1, 'entities_removed': 1})
        source = again['entries'][2]['removed']
        self.assertEqual((source['notes_removed'], source['reviewed_statements_invalidated'], source['job_results_deleted']), (1, 1, 1))
        self.assertEqual(again['entries'][3]['removed'], {'credentials_revoked': 1})
        self.assertEqual(again['totals']['statements_forgotten'], 2)
        # The restored copy has replayed receipts, so the report still finds what forgetting unlinked.
        restored = KnowledgeStore(self.db, clock=lambda: self.clock[0])
        with restored.connection() as db:
            replayed = [json.loads(r[0]) for r in db.execute(
                "SELECT receipt FROM lifecycle_receipts WHERE receipt LIKE '%replayed_on_restore%'")]
        self.assertEqual({r['kind'] for r in replayed}, {'claim_forgotten', 'entity_forgotten', 'source_forgotten'})
        report = deletion.report(restored, self.owner, 'statement', self.status)
        self.assert_agrees(report['held'], self.direct_statement(self.status, store=restored), 'restored statement')
        report = deletion.report(restored, self.owner, 'source', 'source', cache_dir=self.cache.root)
        self.assert_agrees(report['held'], self.direct_source(store=restored), 'restored source')
        self.assertEqual(report['held']['answers']['holding_value'], 0)
        # Forgetting again after restore returns the replayed receipt rather than failing.
        self.assertEqual(ReviewedMemory(restored).forget(self.owner, self.status, {'version': 1})['origin'], 'replayed_on_restore')

    def test_restore_of_a_backup_taken_after_the_forget_removes_nothing_again(self):
        self.memory.forget(self.owner, self.status, {'version': self.version(self.status), 'absolute': True, 'confirm': self.status})
        later = lifecycle.backup(self.store, self.owner, self.root / 'backups')
        result = lifecycle.restore(self.root / 'backups' / later['file'], self.db)
        self.assertEqual((result['removed_again']['entries'], result['removed_again']['totals']), ([], {}))
        self.assertEqual(result['journal_entries_replayed'], 1)


class ExportHistoryTests(Workspace):
    def test_export_includes_review_history_and_routine_settings(self):
        files = {p.name: p for p in self.export_dir.iterdir()}
        history = json.loads(files['review-history.json'].read_text())
        manifest = json.loads(files['manifest.json'].read_text())
        with self.store.connection() as db:
            rows = db.execute('SELECT claim_id,state,at FROM memory_claim_history WHERE actor=? ORDER BY seq',
                              (person_of(self.store, self.owner),)).fetchall()
        self.assertEqual([(e['statement_id'], e['state'], e['at']) for e in history['entries']], [tuple(r) for r in rows])
        self.assertEqual(manifest['counts']['review_history_entries'], len(rows))
        self.assertEqual(history['basis'], 'alfred_review_records_without_values')
        self.assertNotIn('awaiting review', files['review-history.json'].read_text())
        routines = json.loads(files['routines.json'].read_text())
        self.assertEqual([r['kind'] for r in routines['routines']], ['commitment-review'])
        self.assertEqual(routines['routines'][0]['settings']['runs_per_day'], 24)
        self.assertEqual(manifest['counts']['routine_settings'], 1)
        self.assertIn('Review history: proposed', (self.export_dir / 'statements.md').read_text())

    def test_forgotten_statements_history_stays_out_of_later_exports(self):
        self.memory.forget(self.owner, self.status, {'version': self.version(self.status)})
        export(self.store, self.owner, self.root / 'export-2')
        history = json.loads((self.root / 'export-2' / 'review-history.json').read_text())
        manifest = json.loads((self.root / 'export-2' / 'manifest.json').read_text())
        self.assertNotIn(self.status, {e['statement_id'] for e in history['entries']})
        self.assertGreater(manifest['excluded']['history_entries_of_left_out_statements'], 0)
        # The register knows both exports; only the first still holds the statement.
        self.assertEqual(len(deletion.exports(self.db)), 2)
        report = deletion.report(self.store, self.owner, 'statement', self.status)
        self.assertEqual([e['directory'] for e in report['held']['exports_on_disk']['exports']], [str(self.export_dir)])

    def test_an_export_removed_from_disk_is_no_longer_counted(self):
        import shutil
        shutil.rmtree(self.export_dir)
        held = deletion.report(self.store, self.owner, 'statement', self.status)['held']['exports_on_disk']
        self.assertEqual((held['count'], held['no_longer_on_disk']), (0, 1))

    def test_register_is_private_and_holds_no_values(self):
        path = deletion.exports_path(self.db)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertNotIn('awaiting review', path.read_text())


class DeletionReportBoundaryTests(unittest.TestCase):
    def setUp(self):
        from alfred.desk import init_demo
        from alfred.desk_http import DeskHTTPServer
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        mask = os.umask(0o077); os.umask(mask); self.addCleanup(os.umask, mask)
        self.home = self.root / 'demo'; self.keys = init_demo(self.home)
        self.store = KnowledgeStore(self.home / 'desk.sqlite')
        sup = KnowledgeSupervisor(self.store, self.keys['owner'], self.keys['source'], self.home / 'project', vault=self.home / 'vault')
        sup.cycle()
        self.server = DeskHTTPServer(self.store, sup, port=0)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True); thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(3)))
        self.cookie = self.csrf = None

    def req(self, path, data=None):
        headers = {'Cookie': self.cookie} if self.cookie else {}
        if data is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': self.server.origin})
            if self.csrf: headers['X-CSRF-Token'] = self.csrf
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        c.request('POST' if data is not None else 'GET', path, json.dumps(data) if data is not None else None, headers)
        r = c.getresponse(); body = json.loads(r.read()); cookie = r.getheader('Set-Cookie'); c.close()
        return r.status, body, cookie

    def login(self, role):
        _, data, cookie = self.req('/desk/login', {'key': self.keys[role]}); self.cookie = cookie.split(';')[0]; self.csrf = data['csrf']

    def test_http_report_is_owner_only_and_agrees_with_the_receipt(self):
        self.assertEqual(self.req('/desk/deletion-report/source/demo-source')[0], 401)
        self.login('reader')
        self.assertEqual(self.req('/desk/deletion-report/source/demo-source')[0], 403)
        self.login('owner')
        self.assertEqual(self.req('/desk/deletion-report/person/demo-source')[0], 404)
        code, before, _ = self.req('/desk/deletion-report/source/demo-source')
        self.assertEqual((code, before['held']['source_index']['count'] > 0), (200, True))
        self.assertEqual(self.req('/desk/sources/demo-source/forget', {'confirm': 'demo-source', 'purge_history': 'no'})[0], 400)
        code, receipt, _ = self.req('/desk/sources/demo-source/forget', {'confirm': 'demo-source', 'purge_history': True})
        self.assertEqual((code, receipt['history']), (200, 'purged'))
        code, after, _ = self.req('/desk/deletion-report/source/demo-source')
        for name, row in receipt['accounting'].items():
            self.assertEqual(row['after'], {'count': after['held'][name]['count'], 'holding_value': after['held'][name]['holding_value']}, name)
        self.assertEqual(after['held']['source_index']['count'], 0)

    def run_desk(self, *arguments):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['alfred.desk', *arguments]), contextlib.redirect_stdout(output):
            try:
                desk.main(); code = 0
            except SystemExit as exc:
                code = exc.code
        return code, output.getvalue()

    def test_command_line_report(self):
        code, output = self.run_desk('deletion-report', '--data-dir', str(self.home), '--subject-kind', 'source', '--subject', 'demo-source')
        self.assertEqual(code, 0, output)
        self.assertIn('Deletion report for source demo-source', output)
        self.assertIn('source_index:', output)
        code, output = self.run_desk('deletion-report', '--data-dir', str(self.home), '--subject-kind', 'source',
                                     '--subject', 'demo-source', '--json')
        self.assertEqual((code, json.loads(output)['kind']), (0, 'deletion_report'))
        code, output = self.run_desk('deletion-report', '--data-dir', str(self.home))
        self.assertEqual((code, 'subject_required' in output), (1, True))


if __name__ == '__main__':
    unittest.main()
