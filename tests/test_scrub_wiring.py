"""Secret scrubbing wired into brain packets and harvest (backlog C4).

A packet's free text is scrubbed before it is hashed, stored or sent, so the recorded
hash, the job's stored packet and what the brain receives are the same scrubbed text.
Harvested worker text is scrubbed before it becomes a proposal. Only kinds and counts of
what was blanked are kept. Every fake credential is built at run time from pieces.
"""
import hashlib
import json
import sqlite3
import unittest

from alfred import brain as plug
from alfred.brain import BrainBackend, BrainHub, BrainRegistry, SyntheticBrain, check_bundle, packet_sha256, validate_packet
from alfred.jobs import JobWorker
from alfred.knowledge import MarkdownVault
from alfred.reviewed_memory import ReviewedMemory
from test_brain_plug import Base as BrainBase, sample_bundle, sample_packet
from test_learning import Base as LearningBase, BrainMixin
import stored_helpers as stored

GH = 'gh' + 'p_' + 'Zq7Rk2' * 6
AWS = 'AK' + 'IA' + 'Q7XM' * 4
PASSWORD = 'Harbour' + '-42-' + 'lantern'
SECRETS = (GH, AWS, PASSWORD)
KEYS = f'# Keys\nThe deploy token is {GH} for now.\npassword: {PASSWORD}\nThe rota is unchanged.\n'
SCRUBBED = 'The deploy token is [redacted:github_token] for now.\npassword: [redacted:password]\nThe rota is unchanged.'
INSTRUCTION = f'Check key {AWS} is rotated.'
COUNTS = {'aws_access_key_id': 1, 'github_token': 1, 'password': 1}
# The vault's own index keeps the note as written until notes are scrubbed on read
# (docs/SECRET_SCRUBBING.md, step 4, which waits on encryption step 2).
NOTE_TABLES = {'knowledge_notes'}


def tables_holding(db_path, needles):
    db = sqlite3.connect(db_path)
    try:
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        found = set()
        for name in names:
            for row in db.execute(f'SELECT * FROM "{name}"'):
                blob = ' '.join(v.decode('utf-8', 'replace') if isinstance(v, bytes) else str(v) for v in row)
                if any(n in blob for n in needles):
                    found.add(name)
        return found
    finally:
        db.close()


class PacketScrubTests(BrainBase):
    def setUp(self):
        super().setUp()
        (self.vault / 'Keys.md').write_text(KEYS)
        MarkdownVault(self.store, self.source, self.vault).scan()
        self.notes = {n['title']: n['id'] for n in self.store.knowledge(self.owner)['nodes']}

    def keys_request(self, task_id='task-keys', **over):
        context = [{'note': self.notes['Keys'], 'start_line': 2, 'end_line': 4}]
        return self.request(task_id, context=context, instruction=INSTRUCTION, **over)

    def note_inputs(self, title):
        body = self.store.knowledge_note(self.owner, self.notes[title])['body']
        return [{'name': 'input-0', 'sha256': 'x', 'size': 1, 'data': body.encode('utf-8')}]

    def test_packet_leaves_scrubbed_and_the_hash_covers_the_scrubbed_text(self):
        submitted = self.hub.submit(self.owner, self.keys_request())
        self.assertEqual(submitted['scrubbed'], COUNTS)
        job_id = submitted['job']['id']
        self.assertEqual(self.worker().run_once(), job_id)
        given = self.seen[-1]
        self.assertEqual(given['context'][0]['text'], SCRUBBED)
        self.assertEqual(given['instruction'], 'Check key [redacted:aws_access_key_id] is rotated.')
        stored = self.jobs.view(self.owner, job_id)['parameters']['packet']
        self.assertEqual(stored, given)
        task = self.rows('SELECT * FROM brain_tasks WHERE job_id=?', job_id)[0]
        self.assertEqual(task['packet_sha256'], packet_sha256(given))
        self.assertEqual(submitted['packet_sha256'], packet_sha256(given))
        self.assertEqual(json.loads(task['scrubbed']), COUNTS)
        self.assertEqual(task['scrubbed'], '{"aws_access_key_id":1,"github_token":1,"password":1}')
        raw = json.loads(json.dumps(given))
        raw['context'][0]['text'], raw['instruction'] = '\n'.join(KEYS.splitlines()[1:4]), INSTRUCTION
        self.assertNotEqual(packet_sha256(raw), task['packet_sha256'])
        self.assertFalse(any(s in json.dumps(self.seen) for s in SECRETS))
        audit = self.rows("SELECT kind,subject FROM audit WHERE kind='brain.packet_scrubbed'")
        self.assertEqual(audit, [{'kind': 'brain.packet_scrubbed', 'subject': job_id}])
        # The same request again is the same scrubbed packet, so the same job.
        self.assertEqual(self.hub.submit(self.owner, self.keys_request())['job']['id'], job_id)

    def test_a_brain_citing_the_scrubbed_excerpt_passes_and_one_quoting_the_secret_fails(self):
        job_id = self.run_task(self.keys_request())
        self.assertEqual(self.hub.ingest(self.owner, job_id)['status'], 'accepted')
        packet = self.seen[-1]
        cite = lambda quote: sample_bundle(answer={'text': 'Token noted. [E1]', 'citations': [{'ref': 'E1', 'quote': quote}]})
        self.assertIsNone(check_bundle(packet, cite('token is [redacted:github_token] for now')))
        self.assertEqual(check_bundle(packet, cite(f'token is {GH} for now')), 'citation_quote_not_literal')

    def test_excerpt_binding_compares_against_the_scrubbed_slice_and_refuses_forgery(self):
        packet = self.hub.build_packet(self.owner, self.keys_request())
        self.assertEqual(packet['context'][0]['text'], SCRUBBED)
        inputs = self.note_inputs('Keys')
        self.assertIsNone(BrainBackend._check_excerpts(packet, inputs))
        backend = BrainBackend(self.registry, self.policy)
        forged = json.loads(json.dumps(packet))
        forged['context'][0]['text'] = SCRUBBED.replace('for now', 'for later')
        self.fault('excerpt_not_in_bound_revision', backend.submit, 'h1', 'brain_task',
                   {'brain': 'synthetic', 'packet': forged}, inputs)
        # The unscrubbed slice can never be sent, even straight to the backend.
        raw = json.loads(json.dumps(packet))
        raw['context'][0]['text'] = '\n'.join(KEYS.splitlines()[1:4])
        self.fault('secret_shaped_value_in_packet', backend.submit, 'h2', 'brain_task',
                   {'brain': 'synthetic', 'packet': raw}, inputs)
        self.assertEqual(self.seen, [])

    def test_excerpt_sha256_is_the_bound_note_revision_not_the_excerpt(self):
        packet = self.hub.build_packet(self.owner, self.keys_request())
        note = self.store.knowledge_note(self.owner, self.notes['Keys'])
        self.assertEqual((packet['context'][0]['sha256'], packet['context'][0]['revision']), (note['sha256'], note['revision']))
        self.assertEqual(note['sha256'], stored.digest(self.store, KEYS))

    def test_a_clean_packet_is_byte_identical_to_before(self):
        request = self.request('task-clean')
        note = self.store.knowledge_note(self.owner, self.notes['Plan'])
        first = request['context'][0]['start_line']
        expected = {'packet_version': 1, 'task_id': 'task-clean', 'goal': request['goal'], 'scope': 'company',
                    'instruction': 'Summarise the plan.',
                    'context': [{'id': 'E1', 'note_id': note['id'], 'title': 'Plan', 'revision': note['revision'],
                                 'sha256': note['sha256'], 'start_line': first, 'end_line': first + 1,
                                 'text': 'Alpha review is due on Friday.\nremember: Producers prefer short drafts.',
                                 'basis': plug.EXCERPT_BASIS}],
                    'learned': [], 'tools': [], 'budget': request['budget'], 'autonomy': 2}
        self.assertEqual(plug._compact(self.hub.build_packet(self.owner, request)), plug._compact(expected))
        submitted = self.hub.submit(self.owner, request)
        self.assertEqual((submitted['packet_sha256'], submitted['scrubbed']), (packet_sha256(expected), {}))
        task = self.rows('SELECT scrubbed FROM brain_tasks WHERE job_id=?', submitted['job']['id'])[0]
        self.assertEqual(task['scrubbed'], '{}')
        self.assertEqual(self.rows("SELECT * FROM audit WHERE kind='brain.packet_scrubbed'"), [])

    def test_goal_and_learned_statements_are_scrubbed(self):
        memory = ReviewedMemory(self.store)
        memory.create_entity(self.owner, {'id': 'producers', 'kind': 'organisation', 'name': 'Producers'})
        note = self.store.knowledge_note(self.owner, self.notes['Plan'])
        line = self.line_range('Plan', 'remember:')
        claim = memory.propose(self.owner, {'request_id': 'r1', 'subject_id': 'producers', 'predicate': 'status',
                                            'object_id': None, 'value': f'password: {PASSWORD}', 'valid_from': None,
                                            'valid_until': None,
                                            'evidence': {'note_id': note['id'], 'sha256': note['sha256'], 'revision': note['revision'],
                                                         'start_line': line, 'end_line': line}})['id']
        version = next(c for c in memory.view(self.owner)['claims'] if c['id'] == claim)['version']
        memory.review(self.owner, claim, {'version': version, 'decision': 'accept', 'replaces_id': None, 'replaces_version': None})
        request = self.request('task-learned', learned=[claim])
        request['goal'] = {'ref': 'goal-keys', 'statement': f'Rotate {GH} today.'}
        submitted = self.hub.submit(self.owner, request)
        self.assertEqual(submitted['scrubbed'], {'github_token': 1, 'password': 1})
        packet = self.jobs.view(self.owner, submitted['job']['id'])['parameters']['packet']
        self.assertEqual(packet['goal']['statement'], 'Rotate [redacted:github_token] today.')
        self.assertEqual(packet['learned'][0]['statement'], 'Producers status password: [redacted:password]')

    def test_validate_packet_refuses_any_secret_left_in_free_text(self):
        excerpt = sample_packet()['context'][0]
        for packet in (sample_packet(instruction=INSTRUCTION),
                       sample_packet(goal={'ref': 'goal-1', 'statement': f'Use {GH}.'}),
                       sample_packet(context=[dict(excerpt, title=f'password: {PASSWORD}')]),
                       sample_packet(context=[dict(excerpt, text=f'token {GH}')]),
                       sample_packet(learned=[{'id': 'L1', 'claim_id': 'claim-1', 'version': 1,
                                               'statement': f'password: {PASSWORD}', 'basis': plug.LEARNED_BASIS}])):
            self.fault('secret_shaped_value_in_packet', validate_packet, packet)
        scrubbed = sample_packet(instruction='Check key [redacted:aws_access_key_id] is rotated.')
        self.assertIs(validate_packet(scrubbed), scrubbed)

    def test_nothing_stored_or_logged_holds_the_secret(self):
        job_id = self.run_task(self.keys_request())
        self.hub.ingest(self.owner, job_id)
        # A sealed workspace keeps even the note's own text sealed, so no table holds it in the clear.
        self.assertEqual(tables_holding(self.db_path, SECRETS), set() if self.store.sealer.sealed else NOTE_TABLES)

    def test_an_older_database_gains_the_scrubbed_column(self):
        job_id = self.run_task(self.request('task-old'))
        with self.store.connection() as db:
            db.execute('ALTER TABLE brain_tasks DROP COLUMN scrubbed')
            self.assertNotIn('scrubbed', {r[1] for r in db.execute('PRAGMA table_info(brain_tasks)')})
        hub = BrainHub(self.store, self.jobs, self.registry, self.policy)
        self.assertIsNone(self.rows('SELECT scrubbed FROM brain_tasks WHERE job_id=?', job_id)[0]['scrubbed'])
        self.assertEqual(hub.ingest(self.owner, job_id)['status'], 'accepted')
        submitted = hub.submit(self.owner, self.keys_request())
        self.assertEqual(json.loads(self.rows('SELECT scrubbed FROM brain_tasks WHERE job_id=?',
                                              submitted['job']['id'])[0]['scrubbed']), COUNTS)
        BrainHub(self.store, self.jobs, self.registry, self.policy)  # Reopening is a no-op.


class LeakyBrain(SyntheticBrain):
    """A brain whose notes artefact carries a credential it was never sent (invented or leaked)."""

    def run(self, packet, meter):
        bundle = super().run(packet, meter)
        artefact = bundle['artefacts'][0]
        artefact['content'] += f'\nDeploy with {GH} and password: {PASSWORD}\n'
        artefact['sha256'] = hashlib.sha256(artefact['content'].encode('utf-8')).hexdigest()
        return bundle


class HarvestScrubTests(LearningBase, BrainMixin):
    def setUp(self):
        super().setUp()
        self.brains()
        self.job = self.brain_result()['job']

    def staged(self, target, content, name='skill'):
        return {'target': target, 'name': name, 'sha256': hashlib.sha256(content.encode()).hexdigest(), 'content': content}

    def test_staged_credentials_are_blanked_before_they_are_proposed(self):
        content = f'Use {GH} to deploy. password: {PASSWORD}'
        made = self.learning.harvest_staged(self.owner, {'job': self.job, 'staged': [
            self.staged('memory', content, f'deploy {GH}')]})
        self.assertEqual(made['scrubbed'], {'github_token': 2, 'password': 1})
        proposal = self.proposals()[0]
        self.assertEqual(proposal['statement'], 'Use [redacted:github_token] to deploy. password: [redacted:password]')
        self.assertEqual(proposal['detail']['name'], 'deploy [redacted:github_token]')
        self.assertEqual(proposal['detail']['scrubbed'], {'github_token': 2, 'password': 1})
        # The artefact's hash still names the content the worker supplied; the key follows it.
        self.assertEqual(proposal['detail']['sha256'], hashlib.sha256(content.encode()).hexdigest())
        self.assertEqual(tables_holding(self.root / 'desk.sqlite', SECRETS), set())
        # Accepted, the record carries the blanked statement into a packet without refusal.
        record = self.learning.accept(self.owner, proposal['id'], {'version': 1})['record']['id']
        packet = self.hub.build_packet(self.owner, self.request(learned=[record]))
        self.assertEqual(packet['learned'][0]['statement'], proposal['statement'])

    def test_a_result_artefact_carrying_a_credential_is_proposed_blanked(self):
        registry = BrainRegistry(); registry.register(LeakyBrain())
        submitted = self.hub.submit(self.owner, self.request())
        JobWorker(self.jobs, BrainBackend(registry, self.policy), self.owner, 'brain-1', poll_seconds=0.01).run_once()
        self.clock[0] += 5
        self.assertEqual(self.hub.ingest(self.owner, submitted['job']['id'])['status'], 'accepted')
        job = self.jobs.view(self.owner, submitted['job']['id'])
        artefact = json.loads(self.jobs.artefact(self.owner, job['result']['sha256'])['data'])['bundle']['artefacts'][0]
        made = self.learning.harvest(self.owner, {'job': submitted['job']['id'], 'artefacts': [
            {'name': artefact['name'], 'sha256': artefact['sha256'], 'content': artefact['content'], 'as': 'procedure'}]})
        self.assertEqual(made['scrubbed'], {'github_token': 1, 'password': 1})
        statement = self.proposals()[0]['statement']
        self.assertTrue(statement.endswith('\nDeploy with [redacted:github_token] and password: [redacted:password]\n'))
        self.assertFalse(any(s in json.dumps(self.proposals()) for s in SECRETS))
        with self.store.connection() as db:
            stored = [r[0] for r in db.execute('SELECT statement FROM learning_proposals')]
        self.assertEqual(stored, [statement])

    def test_clean_harvest_is_unchanged(self):
        content = 'The owner likes short drafts.'
        made = self.learning.harvest_staged(self.owner, {'job': self.job, 'staged': [self.staged('memory', content, 'style')]})
        self.assertEqual(made['scrubbed'], {})
        proposal = self.proposals()[0]
        self.assertEqual(proposal['statement'], content)
        self.assertEqual(set(proposal['detail']), {'brain', 'job', 'name', 'sha256', 'source', 'basis'})

    def test_credential_shaped_refusal_is_kept(self):
        token = 'A' * 43
        self.fault('credential_shaped_value_in_harvest', self.learning.harvest_staged, self.owner,
                   {'job': self.job, 'staged': [self.staged('memory', f'Key {token} and {GH} here.')]})
        self.assertEqual(self.proposals(), [])


if __name__ == '__main__':
    unittest.main()
