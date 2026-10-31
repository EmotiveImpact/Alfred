"""Sealing jobs, the agent brain, verification, goals, learning and what the desk observes
(encryption step 2, part 4).

Synthetic keys, an invented vault and an invented project document only, with the
deterministic SyntheticBrain; no model runs. A sealed workspace keeps a job's parameters, its
result's bytes and their cached copy on disk, a worker's label, a brain's answer, proposals and
memory suggestions, a verification report, a mandate's success test, schedule and checks, the
hub journal's detail, a learning's statement, detail and evidence, and the desk's own
observations (what a source reported, and the names and titles of the documents and links the
desk lists) sealed, with keyed fingerprints in place of plain SHA-256 hashes. A job or task can
draw on notes of several areas, so all of this is in the workspace's default area.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from alfred import brain as plug
from alfred import sealing, verification
from alfred.brain import BrainHub, BrainPolicy, BrainRegistry, SyntheticBrain
from alfred.executive import ExecutiveRecords
from alfred.hub_goals import GoalHub
from alfred.jobs import BoundedCache, JobCoordinator, JobWorker
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor
from alfred.local import Fault, fingerprint
from alfred.routines import Routines
from grant_helpers import grant_all
import stored_helpers as stored
from test_sealing import keyring

DAY = 86400
T = 1_900_000_000
# Words that appear only in this invented vault, document and work, so finding one in a file means it leaked.
PRIVATE = ('Corvenholt', 'Dunmarrow', 'Hollowmere', 'Ivelthorn', 'Jessamark', 'Kestrelby', 'Larkspurrow', 'Mirewhistle',
           'Grimsharrow', 'Orrinsgate')
PLAN = '# Plan\nHollowmere review is due on Friday.\nremember: Ivelthorn prefers short drafts.\n'
BRIEF = {'document_id': 'corvenholt-brief', 'title': 'Corvenholt crew brief', 'revision': 1, 'observed_at': T - 10,
         'expires_at': T + 6 * DAY, 'summary': 'Dunmarrow call moved to Friday.'}
OTHER = {'document_id': 'orrinsgate-rota', 'title': 'Orrinsgate rota', 'revision': 1, 'observed_at': T - 10,
         'expires_at': T + 6 * DAY, 'summary': 'Orrinsgate rota is unchanged.'}
SUCCESS = 'Mirewhistle approves the review deck.'
SECTIONS = {'kind': 'artefact_sections', 'artefact': 'notes.md', 'sections': ['Synthetic brain notes']}
TASK_BUDGET = {'wall_seconds': 10, 'tokens': 60, 'money_pence': 0, 'steps': 50}
NONE = {'tokens': None, 'money_pence': None, 'wall_seconds': None, 'tasks': None}
SEALED_PREFIX = 'alfred-seal:1:'


def budget(total=None):
    return {'daily': dict(NONE), 'total': {**NONE, **(total or {})}, 'warn_percent': 80, 'utc_offset_minutes': 0}


class ClientStore(KnowledgeStore):
    """Every source in one client area, as a folder rule (part 5) would place it."""
    def source_area(self, db, scope, source):
        return 'client-a'


class SealedWorkBase(unittest.TestCase):
    store_class = KnowledgeStore

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'desk.sqlite'
        self.keyring = keyring(self.root, 'personal', 'client-a')
        sealing.attach(self.path, sealing.Sealed(self.keyring))
        self.addCleanup(sealing.detach, self.path)
        self.clock = [T]
        self.store = self.store_class(self.path, clock=lambda: self.clock[0])
        self.owner = self.store.provision('work', 'owner', 'owner', ttl=30 * DAY)
        self.source = self.store.provision('work', 'source', 'source', ttl=30 * DAY)
        grant_all(self.store, self.owner)
        # What the desk observes: two documents in the project folder.
        (self.root / 'project').mkdir()
        for name, value in (('brief.json', BRIEF), ('rota.json', OTHER)):
            (self.root / 'project' / name).write_text(json.dumps(value))
        self.vault = self.root / 'vault'
        self.vault.mkdir()
        (self.vault / 'Plan.md').write_text(PLAN)
        self.sup = KnowledgeSupervisor(self.store, self.owner, self.source, self.root / 'project', vault=self.vault)
        self.sup.vault.scan()
        self.sup.source.scan()
        self.note = next(n for n in self.store.knowledge(self.owner)['nodes'] if n['title'] == 'Plan')
        # Jobs with a cache on disk, the brain, the goal hub and its verifier.
        self.cache_root = self.root / 'job-cache'
        self.jobs = JobCoordinator(self.store, cache=BoundedCache(self.cache_root, 1 << 20))
        self.jobs.enrol_worker(self.owner, 'brain-1', 'Kestrelby worker', ['brain_task'])
        registry = BrainRegistry()
        registry.register(SyntheticBrain())
        self.brains = BrainHub(self.store, self.jobs, registry, BrainPolicy(permitted_tools=('calculator',)))
        self.hub = GoalHub(self.store, self.brains, self.owner)
        self.records = ExecutiveRecords(self.store)
        self.goal = self.records.create(self.owner, {'request_id': 'goal-1', 'kind': 'goal', 'title': 'Larkspurrow review', 'detail': '',
                                                     'project': None, 'due': None, 'rank': None, 'support': None})
        self.hub.set_budget(self.owner, 'overall', None, {'version': 0, 'budget': budget({'tasks': 100})})
        self.mandate_body = {'request_id': 'mandate-1', 'goal': self.goal['id'], 'scope_class': 'company',
                             'deadline': T + 20 * DAY, 'success_test': SUCCESS, 'autonomy': {'research': 1, 'drafting': 2},
                             'brains': ['synthetic'], 'assigned_brain': 'synthetic', 'tools': ['calculator'],
                             'budget': budget({'tasks': 50}), 'acceptance': [SECTIONS],
                             'schedule': {'when': {'every_hours': 1}, 'utc_offset_minutes': 0,
                                          'task': self.template('Summarise Jessamark.')}}
        self.mandate = self.hub.create_mandate(self.owner, self.mandate_body)
        # Two tasks run by a worker: one proposes a draft, and both suggest a memory.
        self.job = self.run_task('task-1', work='drafting', autonomy=2, instruction='Summarise the plan.\ndraft: Grimsharrow reminder.')
        self.second = self.run_task('task-2', instruction='Summarise the plan again.')
        self.hub.verifier.verify(self.owner, self.job)
        # Learning: an artefact of the result is harvested and accepted, and the daily run reads the journal.
        self.routines = Routines(self.store, self.sup)
        self.sup.routines = self.routines
        self.learning = self.routines.learning
        self.learning.catalogue = self.root / 'no-library' / 'CATALOGUE.json'
        self.learning.upstream_file = self.root / 'upstream-latest.json'
        self.notes = self.envelope(self.job)['bundle']['artefacts'][0]
        made = self.learning.harvest(self.owner, {'job': self.job, 'artefacts': [
            {'name': self.notes['name'], 'sha256': self.notes['sha256'], 'content': self.notes['content'], 'as': 'procedure'}]})
        self.learned = self.learning.accept(self.owner, made['proposed'][0]['proposal'], {'version': 1})['record']
        version = next(r for r in self.routines.view(self.owner)['routines'] if r['kind'] == 'daily-learning')['version']
        self.routines.configure(self.owner, 'daily-learning', {
            'version': version, 'enabled': True, 'schedule': {'daily_at': '21:00'}, 'utc_offset_minutes': 0, 'runs_per_day': 24,
            'nominations_per_run': 10, 'quiet_hours': None, 'interrupt': 'show_now', 'propose_drafts': False})
        self.clock[0] += 15
        self.routines.manual(self.owner, 'daily-learning', {'request_id': 'learn-1'})

    # Helpers ------------------------------------------------------------------

    def template(self, instruction, **over):
        return {'work': 'research', 'instruction': instruction, 'learned': [], 'tools': [], 'budget': dict(TASK_BUDGET),
                'autonomy': 1, 'context': [{'note': self.note['id'], 'start_line': 2, 'end_line': 3}], **over}

    def run_task(self, request_id, **over):
        submitted = self.hub.submit_task(self.owner, self.mandate['id'], {'request_id': request_id, 'brain': None,
                                                                         **self.template(over.pop('instruction'), **over)})
        worker = JobWorker(self.jobs, self.hub.backend(), self.owner, 'brain-1', poll_seconds=0.01, heartbeat_seconds=0.05)
        self.assertEqual(worker.run_once(), submitted['job']['id'])
        self.clock[0] += 5
        self.hub.cycle()
        return submitted['job']['id']

    def envelope(self, job_id):
        address = self.jobs.view(self.owner, job_id)['result']['sha256']
        return json.loads(self.jobs.artefact(self.owner, address)['data'])

    def stored_bytes(self):
        found = b''
        for suffix in ('', '-wal', '-shm', '-journal'):
            part = Path(str(self.path) + suffix)
            if part.exists():
                found += part.read_bytes()
        for part in sorted(self.cache_root.rglob('*')):
            if part.is_file():
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

    def reads(self):
        """Every view this part's records reach the owner through."""
        return [lambda: self.store.desk_state(self.owner), lambda: self.jobs.view(self.owner, self.job),
                lambda: self.envelope(self.job), lambda: self.jobs.workers(self.owner),
                lambda: self.brains.result(self.owner, self.job), lambda: self.brains.proposals(self.owner),
                lambda: self.brains.suggestions(self.owner), lambda: self.brains.drafts(self.owner),
                lambda: self.hub.verifier.runs(self.owner, self.job), lambda: self.hub.result(self.owner, self.job),
                lambda: self.hub.view(self.owner), lambda: self.learning.view(self.owner),
                lambda: self.learning.select_learned(self.owner)]


SEALED_COLUMNS = (('events', 'body'), ('desk_documents', 'filename'), ('desk_documents', 'title'), ('desk_links', 'filename'),
                  ('desk_links', 'title'), ('jobs', 'parameters'), ('workers', 'label'), ('artefacts', 'body'),
                  ('brain_results', 'outcome'), ('brain_proposals', 'parameters'), ('brain_proposals', 'reason'),
                  ('brain_proposals', 'cites'), ('brain_proposals', 'provenance'), ('brain_suggestions', 'statement'),
                  ('brain_suggestions', 'cites'), ('verification_runs', 'report'), ('hub_mandates', 'success_test'),
                  ('hub_mandates', 'schedule'), ('hub_mandates', 'acceptance'), ('hub_journal', 'detail'),
                  ('learning_proposals', 'statement'), ('learning_proposals', 'detail'), ('learning_proposals', 'evidence'),
                  ('learning_records', 'statement'), ('learning_records', 'detail'), ('learning_records', 'evidence'))


class SealedWorkAtRestTests(SealedWorkBase):
    def test_everything_still_opens_sealed(self):
        # What follows is read from sealed values, not from text kept plain beside them.
        for table, column in SEALED_COLUMNS:
            values = [r['v'] for r in self.raw(f'SELECT {column} AS v FROM {table} WHERE {column} IS NOT NULL')]
            self.assertTrue(values and all(v.startswith(SEALED_PREFIX) for v in values), (table, column))
        # The desk's observations.
        events = {e['subject']: e for e in self.store.desk_state(self.owner)['events']}
        brief = events['corvenholt-brief']
        self.assertEqual((brief['summary'], brief['title'], brief['filename'], brief['status']),
                         ('Dunmarrow call moved to Friday.', 'Corvenholt crew brief', 'brief.json', 'current'))
        self.assertEqual(brief['source_sha256'], stored.digest(self.store, (self.root / 'project' / 'brief.json').read_bytes()))
        self.assertEqual(self.store.evidence(self.owner, brief['seq'])['summary'], 'Dunmarrow call moved to Friday.')
        # A scan of unchanged files recognises them by their keyed hashes and imports nothing.
        self.sup.source.scan()
        self.assertEqual(len(self.store.desk_state(self.owner)['events']), 2)
        # The job, its result, its cached copy and its worker.
        job = self.jobs.view(self.owner, self.job)
        self.assertIn('draft: Grimsharrow reminder.', job['parameters']['packet']['instruction'])
        envelope = self.envelope(self.job)
        self.assertIn('Hollowmere review is due on Friday.', envelope['bundle']['answer']['text'])
        self.assertEqual([w['label'] for w in self.jobs.workers(self.owner)], ['Kestrelby worker'])
        # The brain's result, proposals and memory suggestions.
        self.assertEqual(self.brains.result(self.owner, self.job)['status'], 'accepted')
        drafted = [p for p in self.brains.proposals(self.owner) if p['job'] == self.job]
        self.assertEqual([p['parameters'] for p in drafted], [{'text': 'Grimsharrow reminder.'}])
        self.assertEqual({s['statement'] for s in self.brains.suggestions(self.owner)}, {'Ivelthorn prefers short drafts.'})
        # Verification: the automatic run and the owner's, and acknowledging by the hash ALFRED returned.
        runs = self.hub.verifier.runs(self.owner, self.job)
        self.assertEqual([r['initiated'] for r in runs], ['automatic', 'owner'])
        self.assertEqual(runs[-1]['report']['checks'][0]['kind'], 'artefact_sections')
        acknowledged = self.hub.verifier.acknowledge(self.owner, self.job, runs[-1]['sha256'], accept_failures=True)
        self.assertEqual((acknowledged['state'], acknowledged['last_run']['sha256']), ('acknowledged', runs[-1]['sha256']))
        # The mandate and its journal.
        goal = next(g for g in self.hub.view(self.owner)['goals'] if g['id'] == self.mandate['id'])
        self.assertEqual((goal['success_test'], goal['schedule']['task']['instruction'], goal['acceptance'][0]['kind']),
                         (SUCCESS, 'Summarise Jessamark.', 'artefact_sections'))
        created = [json.loads(r['detail']) for r in stored.rows(self.store, 'hub_journal', 'SELECT * FROM hub_journal ORDER BY seq')
                   if r['event'] == 'mandate.created']
        self.assertEqual(created[0]['success_test'], SUCCESS)
        # Replaying the mandate request is recognised by its keyed hash.
        self.assertEqual(self.hub.create_mandate(self.owner, self.mandate_body)['id'], self.mandate['id'])
        # The learning harvested from the result, and the same text is recognised as already learned.
        record = next(r for r in self.learning.view(self.owner)['records'] if r['id'] == self.learned['id'])
        self.assertEqual(record['statement'], self.learned['statement'])
        self.assertIn('Hollowmere', json.dumps(record))
        again = self.learning.harvest(self.owner, {'job': self.job, 'artefacts': [
            {'name': self.notes['name'], 'sha256': self.notes['sha256'], 'content': self.notes['content'], 'as': 'procedure'}]})
        self.assertEqual(again['proposed'], [])

    def test_no_private_text_or_plain_fingerprint_at_rest(self):
        for read in self.reads():
            read()
        raw = self.stored_bytes()
        leaked = [form for word in PRIVATE for form in {word, word.lower(), word.upper()} if form.encode('utf-8') in raw]
        self.assertFalse(leaked, f'private text in the stored files: {leaked}')
        # The plain SHA-256 hashes of what was observed, asked, returned, checked and learned.
        events = {e['subject']: e for e in self.store.desk_state(self.owner)['events']}
        plain = [fingerprint({'id': events[value['document_id']]['id'], 'subject': value['document_id'], 'kind': 'briefing.changed',
                              'basis': 'reported', 'observed_at': value['observed_at'], 'expires_at': value['expires_at'],
                              'summary': value['summary']}) for value in (BRIEF, OTHER)]
        plain += [hashlib.sha256(path.read_bytes()).hexdigest() for path in (self.root / 'project').iterdir()]
        plain += [hashlib.sha256(value['document_id'].encode()).hexdigest() for value in (BRIEF, OTHER)]
        for job_id in (self.job, self.second):
            job = self.jobs.view(self.owner, job_id)
            data = self.jobs.artefact(self.owner, job['result']['sha256'])['data']
            plain += [plug.packet_sha256(job['parameters']['packet']), hashlib.sha256(data).hexdigest()]
            plain += [a['sha256'] for a in json.loads(data)['bundle']['artefacts']]
            plain += [verification._sha(verification._compact(run['report'])) for run in self.hub.verifier.runs(self.owner, job_id)]
        plain += [hashlib.sha256(json.dumps(self.mandate_body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()]
        found = [d[:n] for d in plain for n in (16, 24, 32, 40, 64) if d[:n].encode() in raw]
        self.assertFalse(found, 'plain fingerprints in the stored files')
        # The cached copy on disk is the sealed record, not the result's bytes.
        objects = [p for p in (self.cache_root / 'objects').rglob('*') if p.is_file()]
        self.assertTrue(objects)
        self.assertTrue(all(p.read_bytes().startswith(SEALED_PREFIX.encode()) for p in objects))

    def test_reading_seals_nothing(self):
        sealed = self.counting_seals()
        for read in self.reads():
            read()
        self.assertEqual(sealed, [])

    def test_a_result_read_from_the_cache_opens_and_a_damaged_copy_is_refused(self):
        with self.store.connection() as db:
            db.execute("UPDATE artefacts SET body='x'")
        # The database copy no longer opens; the cached copy, a sealed record on disk, still does.
        address = self.jobs.view(self.owner, self.job)['result']['sha256']
        served = self.jobs.artefact(self.owner, address)
        self.assertEqual(served['served_from'], 'cache')
        self.assertIn('Hollowmere', served['data'].decode())
        for part in (self.cache_root / 'objects').rglob('*'):
            if part.is_file():
                part.write_bytes(part.read_bytes()[:-4] + b'AAAA')
        self.assertEqual(self.fault(lambda: self.envelope(self.job)), ('artefact_corrupt', 500))

    def test_an_event_body_moved_to_another_event_does_not_open(self):
        with self.store.connection() as db:
            rows = db.execute('SELECT seq,body FROM events ORDER BY seq').fetchall()
            db.execute('UPDATE events SET body=? WHERE seq=?', (rows[0]['body'], rows[1]['seq']))
        self.assertEqual(self.fault(lambda: self.store.desk_state(self.owner))[0], 'seal_does_not_match')

    def test_job_parameters_moved_to_another_job_do_not_open(self):
        with self.store.connection() as db:
            value = db.execute('SELECT parameters FROM jobs WHERE id=?', (self.job,)).fetchone()[0]
            db.execute('UPDATE jobs SET parameters=? WHERE id=?', (value, self.second))
        self.assertEqual(self.fault(lambda: self.jobs.view(self.owner, self.second))[0], 'seal_does_not_match')

    def test_a_brain_outcome_moved_to_another_result_does_not_open(self):
        with self.store.connection() as db:
            value = db.execute('SELECT outcome FROM brain_results WHERE job_id=?', (self.job,)).fetchone()[0]
            db.execute('UPDATE brain_results SET outcome=? WHERE job_id=?', (value, self.second))
        self.assertEqual(self.fault(lambda: self.brains.result(self.owner, self.second))[0], 'seal_does_not_match')

    def test_destroying_the_area_erases_the_work(self):
        self.keyring.destroy_area('personal')
        for read in self.reads():
            self.assertEqual(self.fault(read), ('area_destroyed', 410))


class WorkAreaTests(SealedWorkBase):
    """Jobs, brain records, verification, goals, learnings and the desk's observations stay in
    the default area even when every note a task reads is in a client's area."""
    store_class = ClientStore

    def areas(self, table, column):
        return {sealing.area_of(r['v']) for r in self.raw(f'SELECT {column} AS v FROM {table} WHERE {column} IS NOT NULL')}

    def test_work_stays_in_the_default_area(self):
        self.assertEqual(self.areas('knowledge_notes', 'body'), {'client-a'})
        for table, column in SEALED_COLUMNS:
            self.assertEqual(self.areas(table, column), {'personal'}, (table, column))
        sealer = self.store.sealer
        job = self.jobs.view(self.owner, self.job)
        data = self.jobs.artefact(self.owner, job['result']['sha256'])['data']
        self.assertEqual(job['result']['sha256'], sealer.fingerprint('personal', hashlib.sha256(data).hexdigest()))
        task = self.raw('SELECT packet_sha256 FROM brain_tasks WHERE job_id=?', (self.job,))[0]
        self.assertEqual(task['packet_sha256'], sealer.fingerprint('personal', plug.packet_sha256(job['parameters']['packet'])))
        brief = (self.root / 'project' / 'brief.json').read_bytes()
        self.assertIn(sealer.fingerprint('personal', hashlib.sha256(brief).hexdigest()),
                      {r['sha256'] for r in self.raw('SELECT sha256 FROM desk_documents')})


class RegisterTests(unittest.TestCase):
    def test_part_four_tables_are_registered(self):
        expected = {'events': ('fingerprint',), 'desk_documents': ('sha256',), 'desk_links': ('sha256',),
                    'desk_action_evidence': ('event_fingerprint',), 'jobs': ('fingerprint',), 'workers': (),
                    'artefacts': ('sha256',), 'brain_tasks': ('packet_sha256',), 'brain_results': ('envelope_sha256',),
                    'brain_proposals': ('fingerprint',), 'brain_suggestions': (), 'verification_runs': ('report_sha256',),
                    'verification_results': ('last_run_sha256',), 'learning_proposals': (), 'learning_records': (),
                    'hub_mandates': ('request_hash',), 'hub_journal': ()}
        for table, fingerprints in expected.items():
            self.assertEqual(sealing.TABLES[table][2], fingerprints, table)
        self.assertEqual(sealing.KEYED_IDS['events'], ('subject',))
        self.assertEqual(sealing.KEYED_IDS['desk_documents'], ('document_id',))


if __name__ == '__main__':
    unittest.main()
