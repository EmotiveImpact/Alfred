"""Independent verification of brain results (AGENT_HUB.md step H4).

Synthetic data only. Every brain here is the H1 deterministic SyntheticBrain, some with
their bundle edited after they run (a scripted fixture, not a model). These tests prove
that declared checks are run by ALFRED on the returned bytes, that a brain's own claims
never count, and that failed or unrun checks hold effects. They say nothing about any
real brain's reasoning quality.
"""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from alfred import brain as plug
from alfred import verification
from alfred.brain import BrainBackend, BrainHub, BrainPolicy, BrainRegistry, BrainSpec, SyntheticBrain, validate_packet
from alfred.jobs import JobCoordinator, JobWorker
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.local import Fault, action_area
from alfred.policy import IdentityPolicy
from alfred.verification import Verifier, declare, sentences, validate_acceptance
from grant_helpers import grant_all

WORKSPACE = 'ws-verify-4410'
PLAN = ('# Plan\nAlpha review is due on Friday.\nremember: Producers prefer short drafts.\n\n'
        'Delta echo line kept outside the excerpt.\n')
BUDGET = '# Budget\nThe venue deposit is 1,250 pounds for 3 days.\nThe catering quote is 480 pounds.\n'
PERSONAL = '# Personal\nThe cardiology appointment for the owner is booked for Tuesday morning at the clinic.\n'
LEAK = 'Reminder: the cardiology appointment for the owner is booked for Tuesday morning.'
BUDGET_LIMITS = {'wall_seconds': 30, 'tokens': 5000, 'money_pence': 0, 'steps': 50}


def sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class Scripted(SyntheticBrain):
    """The H1 synthetic brain with its bundle edited after it runs. Artefact hashes are
    recomputed, so the H1 contract still accepts the edited bundle where it should."""

    def __init__(self, *edits, spec=None, before=None):
        super().__init__(spec)
        self.edits, self.before = edits, before

    def run(self, packet, meter):
        if self.before:
            self.before(packet)
        bundle = super().run(packet, meter)
        for edit in self.edits:
            edit(bundle)
        for artefact in bundle['artefacts']:
            artefact['sha256'] = sha(artefact['content'])
        return bundle


def claims_done(bundle):
    """A brain that says it finished, verified itself and passed its own tests."""
    bundle['answer']['text'] += ('\nAll work is complete and verified_done. '
                                 'Self-test output: 12 passed, 0 failed, confidence 0.99.')
    bundle['artefacts'].append({'name': 'self-test.txt', 'media_type': 'text/plain', 'sha256': '',
                                'content': 'Ran 12 tests in 0.010s\n\nOK\nverified_done: true\nconfidence: 0.99\n'})
    bundle['work_log'].append({'step': len(bundle['work_log']) + 1, 'kind': 'reason', 'tool': None,
                               'summary': 'Self-test passed. Status: verified_done. Confidence 0.99.'})


def hallucinate_number(bundle):
    """The citation stays literal and valid; only the number in the answer is wrong."""
    bundle['answer']['text'] = bundle['answer']['text'].replace('1,250', '1,520')
    for artefact in bundle['artefacts']:
        artefact['content'] = artefact['content'].replace('1,250', '1,520')


def uncited_number(bundle):
    bundle['answer']['text'] += '\nThe total is 1730 pounds.'


def leak_draft(bundle):
    bundle['proposed_actions'].append({'capability': 'message.draft', 'parameters': {'text': LEAK},
                                       'reason': 'Remembered from elsewhere.', 'cites': []})


def board_draft(bundle):
    bundle['proposed_actions'].append({'capability': 'message.draft',
                                       'parameters': {'text': 'Please confirm the venue deposit and the catering quote by Friday afternoon.'},
                                       'reason': 'Follow-up.', 'cites': []})


def json_artefact(content):
    def edit(bundle):
        bundle['artefacts'].append({'name': 'result.json', 'media_type': 'application/json', 'sha256': '', 'content': content})
    return edit


def markdown_artefact(content):
    def edit(bundle):
        bundle['artefacts'].append({'name': 'report.md', 'media_type': 'text/markdown', 'sha256': '', 'content': content})
    return edit


def claim_checks_in_bundle(bundle):
    bundle['acceptance'] = {'version': 1, 'declared_by': 'owner', 'ref': None, 'checks': []}


def sample_packet(**changes):
    packet = {'packet_version': 1, 'task_id': 'task-x', 'goal': {'ref': 'goal-1', 'statement': 'A goal.'},
              'scope': 'personal', 'instruction': 'Summarise.',
              'context': [{'id': 'E1', 'note_id': 'a' * 24, 'title': 'Plan', 'revision': 1, 'sha256': 'b' * 64,
                           'start_line': 2, 'end_line': 2, 'text': 'Alpha review is due on Friday.',
                           'basis': plug.EXCERPT_BASIS}],
              'learned': [], 'tools': [], 'budget': dict(BUDGET_LIMITS), 'autonomy': 1}
    packet.update(changes)
    return packet


class DeclarationTests(unittest.TestCase):
    def fault(self, code, fn, *args):
        with self.assertRaises(Fault) as caught:
            fn(*args)
        self.assertEqual(caught.exception.code, code)

    def test_declare_fills_defaults_and_numbers_checks(self):
        acceptance = declare({'checks': [{'kind': 'claims_cited'}, {'kind': 'numbers_cited', 'against': 'quote'},
                                         {'kind': 'artefact_sections', 'artefact': 'notes.md', 'sections': ['Summary']}]})
        self.assertEqual(acceptance, {'version': 1, 'declared_by': 'owner', 'ref': None, 'checks': [
            {'id': 'C1', 'kind': 'claims_cited', 'refs': 'excerpts', 'min_words': 3},
            {'id': 'C2', 'kind': 'numbers_cited', 'against': 'quote', 'targets': ['answer']},
            {'id': 'C3', 'kind': 'artefact_sections', 'artefact': 'notes.md', 'sections': ['Summary'], 'non_empty': True}]})
        packet = sample_packet(acceptance=acceptance)
        self.assertIs(validate_packet(packet), packet)
        self.fault('unknown_check_kind', declare, {'checks': [{'kind': 'brain_says_done'}]})
        self.fault('invalid_check', declare, {'checks': [{'kind': 'claims_cited', 'trust_brain': True}]})
        self.fault('invalid_check', declare, {'checks': [{'kind': 'artefact_sections', 'artefact': 'notes.md'}]})
        self.fault('invalid_acceptance', declare, {'checks': []})
        self.fault('invalid_acceptance', declare, {'checks': [{'kind': 'claims_cited'}] * 9})
        self.fault('invalid_acceptance', declare, {'checks': [{'kind': 'claims_cited'}], 'confidence': 1})

    def test_strict_validation_of_each_kind(self):
        def packet_with(*checks, **changes):
            return sample_packet(acceptance={'version': 1, 'declared_by': 'owner', 'ref': None, 'checks': list(checks)}, **changes)
        good = {'id': 'C1', 'kind': 'claims_cited', 'refs': 'excerpts', 'min_words': 3}
        validate_packet(packet_with(good))
        cases = [
            (dict(good, id='C2'), 'invalid_check_id'),
            (dict(good, refs='anything'), 'invalid_check'),
            (dict(good, min_words=0), 'invalid_check'),
            ({k: v for k, v in good.items() if k != 'refs'}, 'invalid_check'),
            ({'id': 'C1', 'kind': 'numbers_cited', 'against': 'excerpt', 'targets': []}, 'invalid_check'),
            ({'id': 'C1', 'kind': 'artefact_sections', 'artefact': '../x', 'sections': ['A'], 'non_empty': True}, 'invalid_check'),
            ({'id': 'C1', 'kind': 'artefact_sections', 'artefact': 'a.md', 'sections': ['A', 'a'], 'non_empty': True}, 'invalid_check'),
            ({'id': 'C1', 'kind': 'artefact_sections', 'artefact': 'a.md', 'sections': ['A\nB'], 'non_empty': True}, 'control_character'),
            ({'id': 'C1', 'kind': 'artefact_fields', 'artefact': 'a.json', 'fields': ['a..b'], 'non_empty': True}, 'invalid_check'),
            ({'id': 'C1', 'kind': 'no_out_of_scope_content', 'targets': ['drafts'], 'min_words': 2}, 'invalid_check'),
            ({'id': 'C1', 'kind': 'effect_readback'}, 'readback_needs_autonomy_two'),
        ]
        for check, code in cases:
            with self.subTest(check=check):
                self.fault(code, validate_packet, packet_with(check))
        validate_packet(packet_with({'id': 'C1', 'kind': 'effect_readback'}, autonomy=2))
        acceptance = packet_with(good)['acceptance']
        for changed, code in ((dict(acceptance, version=2), 'unsupported_acceptance_version'),
                              (dict(acceptance, declared_by='brain'), 'invalid_acceptance_declarer'),
                              (dict(acceptance, ref='mandate-1'), 'invalid_acceptance'),
                              (dict(acceptance, declared_by='mandate'), 'invalid_identifier'),
                              (dict(acceptance, verified_done=True), 'invalid_acceptance')):
            self.fault(code, validate_packet, sample_packet(acceptance=changed))
        validate_packet(sample_packet(acceptance=dict(acceptance, declared_by='mandate', ref='mandate-weekly')))
        self.fault('invalid_packet_fields', validate_packet, sample_packet(acceptance=acceptance, verified_done=True))

    def test_schema_subset_refuses_what_it_cannot_enforce(self):
        def check(schema):
            return {'id': 'C1', 'kind': 'artefact_schema', 'artefact': 'r.json', 'schema': schema}
        acceptance = {'version': 1, 'declared_by': 'owner', 'ref': None, 'checks': []}
        good = {'type': 'object', 'required': ['owner'], 'additionalProperties': False,
                'properties': {'owner': {'type': 'string', 'minLength': 1}, 'days': {'type': 'integer', 'minimum': 1},
                               'tags': {'type': 'array', 'items': {'enum': ['a', 'b']}, 'maxItems': 3}}}
        validate_acceptance(dict(acceptance, checks=[check(good)]), sample_packet())
        for schema in ({'pattern': '^a'}, {'$ref': '#/x'}, {'anyOf': [{'type': 'string'}]}, {'type': 'decimal'},
                       {'properties': {'a': {'format': 'email'}}}, {}, {'minimum': True}):
            with self.subTest(schema=schema):
                with self.assertRaises(Fault):
                    validate_acceptance(dict(acceptance, checks=[check(schema)]), sample_packet())
        deep = {'type': 'array'}
        for _ in range(10):
            deep = {'items': deep}
        self.fault('schema_too_deep', validate_acceptance, dict(acceptance, checks=[check(deep)]), sample_packet())

    def test_patterns_must_compile_and_flags_are_limited(self):
        def check(**changes):
            return {'version': 1, 'declared_by': 'owner', 'ref': None, 'checks': [
                dict({'id': 'C1', 'kind': 'artefact_pattern', 'artefact': 'a.md', 'pattern': '^# Notes$', 'mode': 'search', 'flags': 'm'}, **changes)]}
        validate_acceptance(check(), sample_packet())
        self.fault('invalid_pattern', validate_acceptance, check(pattern='(unclosed'), sample_packet())
        self.fault('invalid_pattern', validate_acceptance, check(pattern='x' * 201), sample_packet())
        self.fault('invalid_pattern_flags', validate_acceptance, check(flags='x'), sample_packet())
        self.fault('invalid_pattern_flags', validate_acceptance, check(flags='mm'), sample_packet())
        self.fault('invalid_check', validate_acceptance, check(mode='match_anything'), sample_packet())

    def test_acceptance_is_bounded(self):
        sections = [f'Section {i} ' + 'x' * 100 for i in range(16)]
        checks = [{'id': f'C{i}', 'kind': 'artefact_sections', 'artefact': 'a.md', 'sections': sections, 'non_empty': True}
                  for i in range(1, 4)]
        self.fault('acceptance_too_large', validate_acceptance,
                   {'version': 1, 'declared_by': 'owner', 'ref': None, 'checks': checks}, sample_packet())

    def test_sentences_keep_trailing_markers_with_their_sentence(self):
        found = sentences('Alpha review is due on Friday. [E1]\nIt moved. [E2] [L1]\nUncited claim here.\n[E3]')
        self.assertEqual([(s['text'], s['refs']) for s in found],
                         [('Alpha review is due on Friday.', ['E1']), ('It moved.', ['E2', 'L1']),
                          ('Uncited claim here.', ['E3'])])
        self.assertEqual(sentences('Dr. Smith said so. [E1]')[0]['refs'], [])  # conservative split: fails, never passes


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = KnowledgeStore(self.root / 'ledger.db')
        provision = self.store.provision
        self.owner = provision(WORKSPACE, 'owner', 'owner', ttl=100000)
        self.second = provision(WORKSPACE, 'owner-2', 'owner', ttl=100000)
        self.source = provision(WORKSPACE, 'source', 'source', ttl=100000)
        grant_all(self.store, self.owner)
        self.vault = self.root / 'vault'
        self.vault.mkdir()
        for name, body in (('Plan.md', PLAN), ('Budget.md', BUDGET), ('Personal.md', PERSONAL)):
            (self.vault / name).write_text(body)
        self.rescan()
        self.jobs = JobCoordinator(self.store)
        self.jobs.enrol_worker(self.owner, 'brain-1', 'Brain worker', ['brain_task'])
        self.registry = BrainRegistry()
        self.registry.register(SyntheticBrain())
        self.policy = BrainPolicy()
        self.hub = BrainHub(self.store, self.jobs, self.registry, self.policy)
        self.verifier = Verifier(self.hub)

    def rescan(self):
        MarkdownVault(self.store, self.source, self.vault).scan()
        self.notes = {n['title']: n['id'] for n in self.store.knowledge(self.owner)['nodes']}

    def request(self, task_id='task-1', *, note='Plan', needle=None, lines=2, autonomy=1, instruction='Summarise.',
                acceptance=None, brain='synthetic'):
        body = self.store.knowledge_note(self.owner, self.notes[note])['body'].splitlines()
        needle = needle or {'Plan': 'Alpha review', 'Budget': 'venue deposit', 'Personal': 'cardiology'}[note]
        first = next(i for i, line in enumerate(body, 1) if needle in line)
        request = {'task_id': task_id, 'brain': brain, 'goal': {'ref': 'goal-review', 'statement': 'Prepare the review.'},
                   'scope': 'company', 'instruction': instruction,
                   'context': [{'note': self.notes[note], 'start_line': first, 'end_line': first + lines - 1}],
                   'learned': [], 'tools': [], 'budget': dict(BUDGET_LIMITS), 'autonomy': autonomy}
        if acceptance is not None:
            request['acceptance'] = {'checks': acceptance}
        return request

    def run_task(self, request, brain=None):
        """Submit, run on a worker and ingest. Returns (job id, ingested result)."""
        registry = self.registry
        if brain is not None:
            registry = BrainRegistry()
            registry.register(brain)
        submitted = self.hub.submit(self.owner, request)
        worker = JobWorker(self.jobs, BrainBackend(registry, self.policy), self.owner, 'brain-1', poll_seconds=0.01)
        self.assertEqual(worker.run_once(), submitted['job']['id'])
        job_id = submitted['job']['id']
        return job_id, self.hub.ingest(self.owner, job_id)

    def fault(self, code, fn, *args, **kwargs):
        with self.assertRaises(Fault) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def rows(self, sql, *args):
        with self.store.connection() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def check(self, view, check_id):
        return next(c for c in view['last_run']['report']['checks'] if c['id'] == check_id)

    def codes(self, view, check_id):
        return [r['code'] for r in self.check(view, check_id)['reasons']]

    def actions(self):
        return {p['position']: self.rows('SELECT * FROM actions WHERE id=?', p['action_id'])[0]
                for p in self.hub.proposals(self.owner) if p['action_id']}

    def assert_no_effects(self):
        self.assertEqual(self.rows('SELECT * FROM outbox'), [])
        self.assertEqual(self.rows('SELECT * FROM drafts'), [])


class OutcomeTests(Base):
    def test_honest_result_meeting_every_declared_check_is_checked(self):
        acceptance = [{'kind': 'claims_cited'}, {'kind': 'numbers_cited', 'targets': ['answer', 'artefacts']},
                      {'kind': 'artefact_sections', 'artefact': 'notes.md', 'sections': ['Synthetic brain notes']},
                      {'kind': 'artefact_pattern', 'artefact': 'notes.md', 'pattern': r'^# Synthetic brain notes$', 'flags': 'm'},
                      {'kind': 'no_out_of_scope_content', 'targets': ['drafts', 'answer', 'artefacts']}]
        job_id, result = self.run_task(self.request(note='Budget', acceptance=acceptance))
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(self.verifier.state(self.owner, job_id)['state'], 'returned')
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual((view['state'], view['verified'], view['checks'], view['runs']), ('checked', True, 'checked', 1), view)
        report = view['last_run']['report']
        self.assertEqual(report['counts'], {'passed': 5, 'failed': 0, 'unverifiable': 0})
        self.assertEqual((report['declared_by'], report['contract'], report['brain_claims_counted']), ('owner', 'accepted', False))
        self.assertEqual(self.check(view, 'C2')['detail']['numbers'], 4)  # 1,250 and 3, in the answer and the artefact
        self.assertEqual(view['last_run']['sha256'], sha(json.dumps(report, sort_keys=True, separators=(',', ':'))))
        self.assertFalse(view['authority_granted'])

    def test_no_declared_checks_means_only_the_owner_can_verify(self):
        job_id, _ = self.run_task(self.request())
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual((view['state'], view['verified'], view['last_run']['report']['declared']), ('returned', False, 0))
        acknowledged = self.verifier.acknowledge(self.owner, job_id, view['last_run']['sha256'])
        self.assertEqual((acknowledged['state'], acknowledged['verified'], acknowledged['acknowledged']['over']),
                         ('acknowledged', True, 'returned'))

    def test_a_brain_claiming_verified_done_is_not_verified(self):
        claimant = Scripted(claims_done)
        job_id, result = self.run_task(self.request(), brain=claimant)
        # The H1 contract accepts it: the claims are ordinary text, a log line and an artefact.
        self.assertEqual(result['status'], 'accepted')
        self.assertIn('verified_done', result['answer']['text'])
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual((view['state'], view['verified']), ('returned', False))
        summary = self.verifier.outcomes(self.owner)
        self.assertEqual(summary['by_brain']['synthetic']['verified'], 0)
        self.assertEqual(summary['results'][0]['checks'], 'returned')
        self.assertFalse(summary['brain_claims_counted'])

    def test_claims_never_help_and_fail_where_they_are_uncited(self):
        sections = {'kind': 'artefact_sections', 'artefact': 'notes.md', 'sections': ['Synthetic brain notes']}
        honest, _ = self.run_task(self.request('honest', acceptance=[sections]))
        claimant, _ = self.run_task(self.request('claimant', acceptance=[sections]), brain=Scripted(claims_done))
        # The claims change nothing: the owner's check decides either way.
        self.assertEqual(self.verifier.verify(self.owner, honest)['state'], 'checked')
        self.assertEqual(self.verifier.verify(self.owner, claimant)['state'], 'checked')
        strict = [{'kind': 'claims_cited'}, {'kind': 'numbers_cited'}]
        job_id, _ = self.run_task(self.request('claimant-strict', acceptance=strict), brain=Scripted(claims_done))
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual((view['state'], view['verified'], view['failed']), ('failed_checks', False, ['C1', 'C2']))
        self.assertEqual(self.codes(view, 'C1'), ['claim_without_citation', 'claim_without_citation'])
        self.assertEqual([r['number'] for r in self.check(view, 'C2')['reasons']], ['12', '0', '0.99'])

    def test_a_verified_done_field_in_the_bundle_is_refused_and_fails(self):
        job_id, result = self.run_task(self.request(acceptance=[{'kind': 'claims_cited'}]),
                                       brain=SyntheticBrain(faults=('claim_extra_field',)))
        self.assertEqual((result['status'], result['reason']), ('refused', 'invalid_bundle_fields'))
        self.assertEqual(self.verifier.state(self.owner, job_id)['state'], 'failed_checks')
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual((view['state'], view['failed']), ('failed_checks', ['C0']))
        self.assertEqual(self.codes(view, 'C0'), ['invalid_bundle_fields'])
        self.assertEqual(self.codes(view, 'C1'), ['bundle_refused'])
        self.fault('nothing_to_acknowledge', self.verifier.acknowledge, self.owner, job_id, view['last_run']['sha256'],
                   accept_failures=True)


class NumberTests(Base):
    def test_numeric_hallucination_is_caught(self):
        honest, _ = self.run_task(self.request('honest', note='Budget', acceptance=[{'kind': 'numbers_cited'}]))
        self.assertEqual(self.verifier.verify(self.owner, honest)['state'], 'checked')
        job_id, result = self.run_task(self.request('wrong', note='Budget', acceptance=[{'kind': 'numbers_cited'}]),
                                       brain=Scripted(hallucinate_number))
        # H1 alone accepts it: the citation is to a sent excerpt and its quote is literal.
        self.assertEqual(result['status'], 'accepted')
        self.assertIn('1,520 pounds', result['answer']['text'])
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual((view['state'], view['verified']), ('failed_checks', False))
        self.assertEqual(self.check(view, 'C1')['reasons'],
                         [{'code': 'number_not_in_cited_text', 'sentence': 1, 'number': '1,520', 'refs': ['E1']}])

    def test_against_quote_and_artefacts(self):
        acceptance = [{'kind': 'numbers_cited', 'against': 'quote', 'targets': ['answer', 'artefacts']}]
        job_id, _ = self.run_task(self.request(note='Budget', acceptance=acceptance), brain=Scripted(hallucinate_number))
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual(self.codes(view, 'C1'), ['number_not_in_cited_text', 'number_not_in_sent_material'])

    def test_uncited_number_fails(self):
        job_id, _ = self.run_task(self.request(note='Budget', acceptance=[{'kind': 'numbers_cited'}]), brain=Scripted(uncited_number))
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual(self.check(view, 'C1')['reasons'], [{'code': 'number_without_citation', 'sentence': 2, 'number': '1730'}])


class ArtefactTests(Base):
    def verify_with(self, edit, *acceptance, task_id='task-1'):
        job_id, result = self.run_task(self.request(task_id, acceptance=list(acceptance)), brain=Scripted(edit))
        self.assertEqual(result['status'], 'accepted')
        return self.verifier.verify(self.owner, job_id)

    def test_fields_and_schema(self):
        content = json.dumps({'owner': 'Producers', 'due': {'day': 'Friday'}, 'days': 3, 'tags': ['a']})
        schema = {'type': 'object', 'required': ['owner', 'due', 'days'], 'additionalProperties': False,
                  'properties': {'owner': {'type': 'string', 'minLength': 1}, 'due': {'type': 'object', 'required': ['day']},
                                 'days': {'type': 'integer', 'minimum': 1, 'maximum': 7},
                                 'tags': {'type': 'array', 'items': {'enum': ['a', 'b']}}}}
        fields = {'kind': 'artefact_fields', 'artefact': 'result.json', 'fields': ['owner', 'due.day']}
        shaped = {'kind': 'artefact_schema', 'artefact': 'result.json', 'schema': schema}
        self.assertEqual(self.verify_with(json_artefact(content), fields, shaped)['state'], 'checked')
        wrong = json.dumps({'owner': '', 'due': {}, 'days': 9, 'tags': ['c'], 'extra': True})
        view = self.verify_with(json_artefact(wrong), fields, shaped, task_id='task-2')
        self.assertEqual(self.check(view, 'C1')['reasons'], [{'code': 'field_empty', 'field': 'owner'},
                                                              {'code': 'field_missing', 'field': 'due.day'}])
        self.assertEqual([(r['code'], r['path']) for r in self.check(view, 'C2')['reasons']],
                         [('schema_min_length', '/owner'), ('schema_required', '/due/day'), ('schema_maximum', '/days'),
                          ('schema_enum', '/tags/0'), ('schema_additional_property', '/extra')])
        view = self.verify_with(json_artefact('{"owner": "a", "owner": "b"}'), fields, task_id='task-3')
        self.assertEqual(self.codes(view, 'C1'), ['artefact_not_json'])
        view = self.verify_with(lambda b: None, fields, task_id='task-4')
        self.assertEqual(self.codes(view, 'C1'), ['artefact_missing'])

    def test_sections_present_and_filled(self):
        report = '# Report\n\n## Summary\nDue Friday.\n\n## Risks\n\n## Next steps\n```\n## Not a heading\n```\n'
        check = {'kind': 'artefact_sections', 'artefact': 'report.md', 'sections': ['summary', 'Risks', 'Owners', 'Next steps']}
        view = self.verify_with(markdown_artefact(report), check)
        self.assertEqual(self.check(view, 'C1')['reasons'], [{'code': 'section_empty', 'section': 'Risks'},
                                                              {'code': 'section_missing', 'section': 'Owners'}])
        relaxed = dict(check, sections=['Summary', 'Risks'], non_empty=False)
        self.assertEqual(self.verify_with(markdown_artefact(report), relaxed, task_id='task-2')['state'], 'checked')

    def test_pattern_match_and_no_match(self):
        match = {'kind': 'artefact_pattern', 'artefact': 'notes.md', 'pattern': r'Alpha review is due on \w+day\.'}
        self.assertEqual(self.verify_with(lambda b: None, match)['state'], 'checked')
        view = self.verify_with(lambda b: None, dict(match, mode='fullmatch'), task_id='task-2')
        self.assertEqual(self.codes(view, 'C1'), ['pattern_not_matched'])

    def test_a_pattern_that_cannot_finish_is_unverifiable_never_passed(self):
        self.verifier = Verifier(self.hub, pattern_seconds=0.5)
        runaway = {'kind': 'artefact_pattern', 'artefact': 'report.md', 'pattern': r'^(a+)+$'}
        view = self.verify_with(markdown_artefact('a' * 40 + '!'), runaway, {'kind': 'claims_cited'})
        self.assertEqual(self.check(view, 'C1')['status'], 'unverifiable')
        self.assertEqual(self.codes(view, 'C1'), ['pattern_timeout'])
        self.assertEqual(self.check(view, 'C2')['status'], 'passed')
        self.assertEqual((view['state'], view['verified'], view['last_run']['outcome']), ('returned', False, 'returned'))


class UnverifiableTests(Base):
    def test_unreadable_result_is_unverifiable(self):
        job_id, _ = self.run_task(self.request(acceptance=[{'kind': 'claims_cited'}]))
        policy = IdentityPolicy(self.store)
        policy.grant(self.owner, 'source', 'read', self.store.now() + 1, policy.view(self.owner)['epoch'], revoke=True)
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual(self.check(view, 'C1')['status'], 'unverifiable')
        self.assertEqual(self.codes(view, 'C1'), ['result_not_available'])
        self.assertEqual((view['state'], view['verified']), ('returned', False))

    def test_a_check_that_crashes_is_unverifiable(self):
        class Broken(Verifier):
            def _numbers_cited(self, check, ctx):
                raise RuntimeError('broken check')
        job_id, _ = self.run_task(self.request(acceptance=[{'kind': 'numbers_cited'}]))
        view = Broken(self.hub).verify(self.owner, job_id)
        self.assertEqual((self.check(view, 'C1')['status'], self.codes(view, 'C1')), ('unverifiable', ['check_could_not_run']))
        self.assertFalse(view['verified'])

    def test_an_answer_with_no_claim_establishes_nothing(self):
        def terse(bundle):
            bundle['answer'] = {'text': 'Done.', 'citations': []}
        job_id, _ = self.run_task(self.request(acceptance=[{'kind': 'claims_cited'}]), brain=Scripted(terse))
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual((self.check(view, 'C1')['status'], view['state']), ('unverifiable', 'returned'))

    def test_a_stopped_job_was_never_returned(self):
        job_id, result = self.run_task(self.request(acceptance=[{'kind': 'claims_cited'}]), brain=SyntheticBrain(faults=('crash',)))
        self.assertEqual(result['status'], 'stopped')
        self.fault('result_not_returned', self.verifier.verify, self.owner, job_id)
        self.assertEqual(self.verifier.state(self.owner, job_id)['state'], 'not_returned')
        self.assertEqual(self.verifier.outcomes(self.owner)['by_brain']['synthetic']['not_returned'], 1)

    def test_not_ingested(self):
        submitted = self.hub.submit(self.owner, self.request())
        self.fault('not_ingested', self.verifier.verify, self.owner, submitted['job']['id'])


class ChecksBelongToAlfredTests(Base):
    def test_the_brain_cannot_remove_or_supply_checks(self):
        seen = []

        def strip(packet):
            seen.append(copy.deepcopy(packet))
            packet.pop('acceptance')
        job_id, result = self.run_task(self.request(acceptance=[{'kind': 'numbers_cited'}]),
                                       brain=Scripted(uncited_number, before=strip))
        self.assertEqual(seen[0]['acceptance']['checks'][0]['kind'], 'numbers_cited')  # the brain is told the checks
        self.assertEqual(result['status'], 'accepted')
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual((view['state'], self.codes(view, 'C1')), ('failed_checks', ['number_without_citation']))
        job_id, result = self.run_task(self.request('supplied', acceptance=[{'kind': 'numbers_cited'}]),
                                       brain=Scripted(claim_checks_in_bundle))
        self.assertEqual((result['status'], result['reason']), ('refused', 'invalid_bundle_fields'))
        self.assertEqual(self.verifier.verify(self.owner, job_id)['state'], 'failed_checks')

    def test_records_are_private_and_runs_are_append_only(self):
        job_id, _ = self.run_task(self.request(acceptance=[{'kind': 'claims_cited'}]))
        view = self.verifier.verify(self.owner, job_id)
        self.fault('not_found', self.verifier.verify, self.second, job_id)
        self.fault('not_found', self.verifier.state, self.second, job_id)
        self.fault('not_found', self.verifier.acknowledge, self.second, job_id, view['last_run']['sha256'])
        self.assertEqual(self.verifier.outcomes(self.second)['results'], [])
        with self.assertRaises(sqlite3.DatabaseError):
            with self.store.transaction() as db:
                db.execute("UPDATE verification_runs SET outcome='checked'")
        self.assertEqual([r['position'] for r in self.verifier.runs(self.owner, job_id)], [1])

    def test_failure_is_sticky(self):
        check = [{'kind': 'no_out_of_scope_content'}]
        job_id, _ = self.run_task(self.request(acceptance=check, autonomy=1), brain=Scripted(leak_draft))
        first = self.verifier.verify(self.owner, job_id)
        self.assertEqual(first['state'], 'failed_checks')
        (self.vault / 'Personal.md').write_text('# Personal\nNothing to see.\n')
        self.rescan()
        second = self.verifier.verify(self.owner, job_id)
        self.assertEqual((second['last_run']['outcome'], second['state'], second['checks']), ('checked', 'failed_checks', 'failed_checks'))
        self.assertEqual(self.verifier.outcomes(self.owner)['results'][0]['checks'], 'failed_checks')


class EffectGateTests(Base):
    DRAFT = 'draft: Thank the producers.'

    def test_declared_checks_must_run_before_a_draft_can_be_approved(self):
        job_id, result = self.run_task(self.request(autonomy=2, instruction=self.DRAFT, acceptance=[{'kind': 'claims_cited'}]))
        self.assertEqual(result['proposals'], {'pending_approval': 1})
        action = self.actions()[0]
        self.fault('evidence_or_approval_expired', self.store.approve, self.owner, action['id'], action['fingerprint'])
        self.assertEqual(self.verifier.verify(self.owner, job_id)['state'], 'checked')
        self.assertEqual(self.store.approve(self.owner, action['id'], action['fingerprint'])['state'], 'queued')
        self.assertEqual(self.store.tick(self.owner)['state'], 'verified')

    def test_out_of_scope_draft_fails_and_is_held_until_acknowledged(self):
        job_id, result = self.run_task(self.request(autonomy=2, instruction=self.DRAFT,
                                                    acceptance=[{'kind': 'no_out_of_scope_content'}]), brain=Scripted(leak_draft))
        self.assertEqual(result['proposals'], {'pending_approval': 2})
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual(view['state'], 'failed_checks')
        self.assertEqual(self.check(view, 'C1')['reasons'],
                         [{'code': 'out_of_scope_content', 'target': 'draft', 'position': 1,
                           'note': self.notes['Personal'], 'line': 2}])
        for action in self.actions().values():
            self.fault('evidence_or_approval_expired', self.store.approve, self.owner, action['id'], action['fingerprint'])
        self.assert_no_effects()
        self.fault('failed_checks_need_explicit_acceptance', self.verifier.acknowledge, self.owner, job_id, view['last_run']['sha256'])
        acknowledged = self.verifier.acknowledge(self.owner, job_id, view['last_run']['sha256'], accept_failures=True)
        self.assertEqual((acknowledged['state'], acknowledged['acknowledged']['over'], acknowledged['acknowledged']['failed_accepted']),
                         ('acknowledged', 'failed_checks', ['C1']))
        # Acknowledgement grants nothing by itself: each draft still needs its exact approval.
        self.assert_no_effects()
        honest = self.actions()[0]
        self.assertEqual(self.store.approve(self.owner, honest['id'], honest['fingerprint'])['state'], 'queued')

    def test_text_sent_in_scope_is_not_flagged(self):
        def quote_excerpt(bundle):
            bundle['proposed_actions'].append({'capability': 'message.draft', 'reason': 'Quote.', 'cites': ['E1'],
                                               'parameters': {'text': 'As noted: The venue deposit is 1,250 pounds for 3 days.'}})
        job_id, _ = self.run_task(self.request(note='Budget', autonomy=2, acceptance=[{'kind': 'no_out_of_scope_content', 'min_words': 5}]),
                                  brain=Scripted(quote_excerpt))
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual(view['state'], 'checked', view)
        self.assertEqual(self.check(view, 'C1')['detail']['notes_compared'], 3)

    def test_a_failure_found_after_approval_stops_dispatch(self):
        job_id, _ = self.run_task(self.request(autonomy=2, acceptance=[{'kind': 'no_out_of_scope_content'}]), brain=Scripted(board_draft))
        self.assertEqual(self.verifier.verify(self.owner, job_id)['state'], 'checked')
        action = self.actions()[0]
        self.store.approve(self.owner, action['id'], action['fingerprint'])
        (self.vault / 'Board.md').write_text('# Board\nPlease confirm the venue deposit and the catering quote by Friday afternoon.\n')
        self.rescan()
        self.assertEqual(self.verifier.verify(self.owner, job_id)['state'], 'failed_checks')
        self.assertEqual(self.store.tick(self.owner)['state'], 'blocked')
        self.assertEqual(self.rows('SELECT * FROM drafts'), [])

    def test_readback_waits_for_the_effect_then_checks_it(self):
        acceptance = [{'kind': 'claims_cited'}, {'kind': 'effect_readback'}]
        job_id, _ = self.run_task(self.request(autonomy=2, instruction=self.DRAFT, acceptance=acceptance))
        first = self.verifier.verify(self.owner, job_id)
        self.assertEqual((first['state'], first['verified']), ('returned', False))
        self.assertEqual(self.check(first, 'C2')['reasons'],
                         [{'code': 'effect_not_executed', 'position': 0, 'action_state': 'proposed'}])
        action = self.actions()[0]
        self.store.approve(self.owner, action['id'], action['fingerprint'])
        self.assertEqual(self.store.tick(self.owner)['state'], 'verified')
        second = self.verifier.verify(self.owner, job_id)
        self.assertEqual((second['state'], second['verified'], second['runs']), ('checked', True, 2))
        self.assertEqual(self.check(second, 'C2')['detail'], {'effects': 1, 'read_back': 1})

    def test_readback_mismatch_fails_and_ends_an_acknowledgement(self):
        job_id, _ = self.run_task(self.request(autonomy=2, instruction=self.DRAFT, acceptance=[{'kind': 'effect_readback'}]))
        first = self.verifier.verify(self.owner, job_id)
        self.assertEqual(self.verifier.acknowledge(self.owner, job_id, first['last_run']['sha256'])['state'], 'acknowledged')
        action = self.actions()[0]
        self.store.approve(self.owner, action['id'], action['fingerprint'])
        self.store.tick(self.owner)
        with self.store.transaction() as db:
            # Changed the way ALFRED writes a draft in this workspace (sealed or plain), so only the text differs.
            row = self.store.sealed('drafts', action_area(db), {**db.execute('SELECT scope,action_id FROM drafts').fetchone(),
                                                                'body': 'Thank the producers. P.S. something else.'})
            db.execute('UPDATE drafts SET body=?', (row['body'],))
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual((view['state'], view['verified'], self.codes(view, 'C1')), ('failed_checks', False, ['readback_mismatch']))
        self.assertIsNone(view['acknowledged'])
        kinds = [r['kind'] for r in self.rows("SELECT kind FROM audit WHERE kind LIKE 'verification.%' ORDER BY seq")]
        self.assertEqual(kinds, ['verification.run_returned', 'verification.acknowledged',
                                 'verification.acknowledgement_lapsed', 'verification.run_failed_checks'])

    def test_readback_with_no_effect_fails(self):
        job_id, _ = self.run_task(self.request(autonomy=2, acceptance=[{'kind': 'effect_readback'}]))
        view = self.verifier.verify(self.owner, job_id)
        self.assertEqual((view['state'], self.codes(view, 'C1')), ('failed_checks', ['no_effect_proposed']))

    def test_packet_without_checks_keeps_h1_approval(self):
        self.run_task(self.request(autonomy=2, instruction=self.DRAFT))
        action = self.actions()[0]
        self.assertEqual(self.store.approve(self.owner, action['id'], action['fingerprint'])['state'], 'queued')


class AcknowledgementTests(Base):
    def test_binding_and_idempotence(self):
        job_id, _ = self.run_task(self.request(acceptance=[{'kind': 'claims_cited'}]), brain=Scripted(uncited_number))
        self.fault('not_verified_yet', self.verifier.acknowledge, self.owner, job_id, 'a' * 64)
        first = self.verifier.verify(self.owner, job_id)
        second = self.verifier.verify(self.owner, job_id)
        self.assertNotEqual(first['last_run']['sha256'], second['last_run']['sha256'])
        # Bound to the latest run the owner saw, not an older one.
        self.fault('acknowledgement_mismatch', self.verifier.acknowledge, self.owner, job_id, first['last_run']['sha256'],
                   accept_failures=True)
        self.fault('invalid_run_sha256', self.verifier.acknowledge, self.owner, job_id, 'not-a-hash')
        self.fault('invalid_accept_failures', self.verifier.acknowledge, self.owner, job_id, second['last_run']['sha256'],
                   accept_failures='yes')
        done = self.verifier.acknowledge(self.owner, job_id, second['last_run']['sha256'], accept_failures=True)
        self.assertEqual(self.verifier.acknowledge(self.owner, job_id, second['last_run']['sha256']), done)
        # A further run that finds nothing new keeps the acknowledgement.
        self.assertEqual(self.verifier.verify(self.owner, job_id)['state'], 'acknowledged')


class RoutingQueryTests(Base):
    def test_outcomes_by_brain_come_from_checks_and_acknowledgements_only(self):
        spec = BrainSpec(id='synthetic-b', label='Second synthetic brain', locality='local', version='1',
                         scopes=frozenset({'company'}), tools=frozenset(), max_autonomy=2)
        self.registry.register(SyntheticBrain(spec))
        numbers = [{'kind': 'numbers_cited'}]
        good, _ = self.run_task(self.request('a-good', note='Budget', acceptance=numbers))
        bad, _ = self.run_task(self.request('a-bad', note='Budget', acceptance=numbers), brain=Scripted(hallucinate_number))
        claimant, _ = self.run_task(self.request('b-claim', brain='synthetic-b'), brain=Scripted(claims_done, spec=spec))
        stopped, _ = self.run_task(self.request('b-crash', brain='synthetic-b'),
                                   brain=SyntheticBrain(spec, faults=('crash',)))
        unrun, _ = self.run_task(self.request('a-unrun', acceptance=numbers))
        for job_id in (good, bad, claimant):
            self.verifier.verify(self.owner, job_id)
        result = verification.outcomes(self.store, self.owner)
        self.assertEqual(result['by_brain'], {
            'synthetic': {'results': 3, 'checked': 1, 'failed_checks': 1, 'returned': 1, 'not_returned': 0,
                          'acknowledged': 0, 'verified': 1},
            'synthetic-b': {'results': 2, 'checked': 0, 'failed_checks': 0, 'returned': 1, 'not_returned': 1,
                            'acknowledged': 0, 'verified': 0}})
        rows = {r['job']: r for r in result['results']}
        self.assertEqual((rows[unrun]['checks'], rows[unrun]['runs']), ('returned', 0))
        self.assertEqual(rows[stopped]['contract'], 'stopped')
        only_b = self.verifier.outcomes(self.owner, brain='synthetic-b')
        self.assertEqual({r['brain'] for r in only_b['results']}, {'synthetic-b'})


if __name__ == '__main__':
    unittest.main()
