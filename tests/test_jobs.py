"""Stage 0 job coordinator tests: synthetic notes, real SQLite and real local subprocesses.

The local subprocess backend is not VM isolation, a remote worker or a sandbox.
These tests prove durable job records, policy rechecks, leases, limits and cache
behaviour on one host. They do not prove containment, remote execution or any
reasoning quality.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from alfred import job_kinds
from alfred.jobs import (BoundedCache, JobCoordinator, JobWorker, LocalSubprocessBackend,
                         WorkerBackend)
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.local import Fault
from alfred.policy import IdentityPolicy

REPOSITORY = Path(__file__).resolve().parents[1]
PLAN = '# Plan\nAlpha bravo charlie.\n\nDelta echo.\n'
SECRET = '# Secret\nHiddenmarker synthetic record.\n'
ALL_KINDS = ['summarise_lines', 'wait', 'word_count']


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class Base(unittest.TestCase):
    real_clock = False

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.clock = [10000]
        self.db_path = self.root / 'ledger.db'
        self.store = self.open_store()
        provision = self.store.provision
        self.owner = provision('work', 'owner', 'owner', ttl=100000)
        self.second = provision('work', 'owner-2', 'owner', ttl=100000)
        self.reader = provision('work', 'reader', 'reader', ttl=100000)
        self.source = provision('work', 'source', 'source', ttl=100000)
        self.hidden = provision('work', 'hidden', 'source', ttl=100000)
        self.foreign = provision('other', 'foreign', 'owner', ttl=100000)
        self.vault = self.root / 'vault'
        self.vault.mkdir()
        (self.vault / 'Plan.md').write_text(PLAN)
        MarkdownVault(self.store, self.source, self.vault).scan()
        hidden = self.root / 'hidden'
        hidden.mkdir()
        (hidden / 'Secret.md').write_text(SECRET)
        MarkdownVault(self.store, self.hidden, hidden).scan()
        self.notes = {n['title']: n['id'] for n in self.store.knowledge(self.owner)['nodes']}
        self.jobs = JobCoordinator(self.store)
        self.jobs.enrol_worker(self.owner, 'local-1', 'Local worker', ALL_KINDS)

    def open_store(self):
        return KnowledgeStore(self.db_path, clock=time.time if self.real_clock else (lambda: self.clock[0]))

    def request(self, key='k1', kind='word_count', parameters=None, inputs=None, side_effect_free=True, **extra):
        inputs = [{'note': self.notes['Plan']}] if inputs is None else inputs
        return {'idempotency_key': key, 'kind': kind, 'parameters': parameters or {}, 'inputs': inputs,
                'side_effect_free': side_effect_free, **extra}

    def fault(self, code, fn, *args, **kwargs):
        with self.assertRaises(Fault) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def kinds(self, job_id, bearer=None):
        return [e['kind'] for e in self.jobs.events(bearer or self.owner, job_id)['events']]

    def grant(self, source='source', *, revoke=False):
        policy = IdentityPolicy(self.store)
        return policy.grant(self.owner, source, 'read', self.store.now() + 50000,
                            policy.view(self.owner)['epoch'], revoke=revoke)

    def leased(self, worker='local-1', bearer=None):
        grant = self.jobs.lease(bearer or self.owner, worker)
        self.assertIsNotNone(grant)
        return grant

    def started(self, **kwargs):
        grant = self.leased(**kwargs)
        self.jobs.start(self.owner, 'local-1', grant['job'], grant['lease'], backend='test')
        return grant

    def wait_for(self, predicate, timeout=15.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.02)
        self.fail('condition not reached in time')

    def background(self, worker):
        stop = threading.Event()
        thread = threading.Thread(target=worker.run, args=(stop,), kwargs={'idle_seconds': 0.02}, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 20)
        self.addCleanup(stop.set)
        return stop, thread


class SubmissionTests(Base):
    def test_idempotent_submit_returns_existing_job(self):
        first = self.jobs.submit(self.owner, self.request())
        again = self.jobs.submit(self.owner, self.request())
        self.assertEqual(first['id'], again['id'])
        self.assertEqual(len(self.jobs.jobs(self.owner)), 1)
        self.assertEqual(self.kinds(first['id']), ['submitted'])

    def test_same_key_with_different_request_collides(self):
        self.jobs.submit(self.owner, self.request())
        self.fault('idempotency_key_collision', self.jobs.submit, self.owner,
                   self.request(kind='summarise_lines', parameters={'max_lines': 2}))
        self.fault('idempotency_key_collision', self.jobs.submit, self.owner, self.request(max_attempts=5))

    def test_key_is_unique_per_actor(self):
        mine = self.jobs.submit(self.owner, self.request())
        theirs = self.jobs.submit(self.second, self.request())
        self.assertNotEqual(mine['id'], theirs['id'])

    def test_only_allowlisted_kinds_and_parameters(self):
        self.fault('unknown_job_kind', self.jobs.submit, self.owner, self.request(kind='shell'))
        self.fault('invalid_parameters', self.jobs.submit, self.owner,
                   self.request(kind='summarise_lines', parameters={'max_lines': 0}))
        self.fault('invalid_parameters', self.jobs.submit, self.owner,
                   self.request(parameters={'command': 'ls'}))
        self.fault('invalid_fields', self.jobs.submit, self.owner, self.request(path='/etc'))

    def test_reader_cannot_submit(self):
        self.fault('forbidden', self.jobs.submit, self.reader, self.request())

    def test_inputs_are_bound_to_current_revision(self):
        job = self.jobs.submit(self.owner, self.request())
        bound = job['inputs'][0]
        self.assertEqual((bound['type'], bound['id'], bound['source'], bound['revision']),
                         ('note', self.notes['Plan'], 'source', 1))
        self.assertEqual(bound['source_sha256'], hashlib.sha256(PLAN.encode()).hexdigest())
        self.fault('input_revision_changed', self.jobs.submit, self.owner,
                   self.request(key='k2', inputs=[{'note': self.notes['Plan'], 'revision': 7}]))

    def test_inputs_denied_at_submission_under_strict_policy(self):
        self.grant('source')
        self.fault('inputs_denied', self.jobs.submit, self.owner, self.request(inputs=[{'note': self.notes['Secret']}]))
        self.fault('inputs_denied', self.jobs.submit, self.owner, self.request(key='k2', inputs=[{'note': 'a' * 24}]))
        self.assertEqual(self.jobs.submit(self.owner, self.request(key='k3'))['state'], 'queued')

    def test_side_effect_free_claim_cannot_understate_a_kind(self):
        effectful = dict(job_kinds.KINDS['word_count'], side_effect_free=False)
        with mock.patch.dict(job_kinds.KINDS, {'word_count': effectful}):
            self.fault('side_effect_claim_not_allowed', self.jobs.submit, self.owner, self.request())
            self.assertFalse(self.jobs.submit(self.owner, self.request(side_effect_free=False))['side_effect_free'])

    def test_events_are_append_only(self):
        job = self.jobs.submit(self.owner, self.request())
        with self.store.connection() as db:
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("UPDATE job_events SET kind='forged' WHERE job_id=?", (job['id'],))
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute('DELETE FROM job_events WHERE job_id=?', (job['id'],))
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute("INSERT INTO job_events VALUES (?,5,'skipped','{}',0)", (job['id'],))


class LeaseTests(Base):
    def test_worker_receives_only_declared_permitted_bytes(self):
        self.jobs.submit(self.owner, self.request())
        grant = self.leased()
        self.assertEqual(set(grant), {'job', 'lease', 'lease_until', 'attempt', 'kind', 'parameters',
                                      'side_effect_free', 'inputs'})
        self.assertEqual(len(grant['inputs']), 1)
        delivered = grant['inputs'][0]
        self.assertEqual(set(delivered), {'name', 'sha256', 'size', 'data'})
        self.assertEqual(delivered['data'], PLAN.encode())
        text = repr(grant)
        for secret in (str(self.db_path), str(self.vault), self.owner, self.source, 'Hiddenmarker'):
            self.assertNotIn(secret, text)

    def test_permission_revoked_after_submission_fails_at_lease(self):
        self.grant('source')
        job = self.jobs.submit(self.owner, self.request())
        self.grant('source', revoke=True)
        self.assertIsNone(self.jobs.lease(self.owner, 'local-1'))
        view = self.jobs.view(self.owner, job['id'])
        self.assertEqual((view['state'], view['reason'], view['attempt']), ('failed', 'inputs_denied', 0))
        self.assertEqual(self.kinds(job['id']), ['submitted', 'dispatch_denied'])

    def test_note_revised_after_submission_fails_as_changed(self):
        job = self.jobs.submit(self.owner, self.request())
        (self.vault / 'Plan.md').write_text(PLAN + 'Foxtrot.\n')
        MarkdownVault(self.store, self.source, self.vault).scan()
        self.assertIsNone(self.jobs.lease(self.owner, 'local-1'))
        self.assertEqual(self.jobs.view(self.owner, job['id'])['reason'], 'inputs_changed')

    def test_revoked_source_credential_fails_at_lease(self):
        job = self.jobs.submit(self.owner, self.request())
        self.store.revoke('source')
        self.assertIsNone(self.jobs.lease(self.owner, 'local-1'))
        self.assertEqual(self.jobs.view(self.owner, job['id'])['reason'], 'inputs_denied')

    def test_revoked_submitter_fails_at_lease(self):
        job = self.jobs.submit(self.second, self.request())
        self.store.revoke('owner-2')
        self.assertIsNone(self.jobs.lease(self.owner, 'local-1'))
        self.assertEqual(self.jobs.view(self.owner, job['id'])['reason'], 'authority_revoked')

    def test_worker_leases_only_kinds_it_declares(self):
        self.jobs.enrol_worker(self.owner, 'counter', 'Counter only', ['word_count'])
        job = self.jobs.submit(self.owner, self.request(kind='wait', parameters={'seconds': 0}))
        self.assertIsNone(self.jobs.lease(self.owner, 'counter'))
        self.assertEqual(self.leased()['job'], job['id'])
        self.fault('invalid_capabilities', self.jobs.enrol_worker, self.owner, 'bad', 'Bad', ['shell'])
        self.fault('invalid_capabilities', self.jobs.enrol_worker, self.owner, 'bad', 'Bad', [{'kind': 'wait'}])

    def test_worker_revocation_stops_leasing_and_completion(self):
        job = self.jobs.submit(self.owner, self.request())
        grant = self.started()
        outcome = self.jobs.revoke_worker(self.owner, 'local-1')
        self.assertEqual(outcome['recovered']['requeued'], [job['id']])
        data = b'{}'
        self.fault('worker_revoked', self.jobs.complete, self.owner, 'local-1', grant['job'], grant['lease'],
                   sha256=hashlib.sha256(data).hexdigest(), data=data)
        self.fault('worker_revoked', self.jobs.heartbeat, self.owner, 'local-1', grant['job'], grant['lease'])
        self.fault('worker_revoked', self.jobs.lease, self.owner, 'local-1')
        self.fault('worker_exists', self.jobs.enrol_worker, self.owner, 'local-1', 'Again', ALL_KINDS)
        self.jobs.enrol_worker(self.owner, 'local-2', 'Replacement', ALL_KINDS)
        self.assertEqual(self.leased('local-2')['attempt'], 2)

    def test_revoked_owner_credential_cannot_lease_heartbeat_or_complete(self):
        self.jobs.submit(self.owner, self.request())
        grant = self.started()
        self.store.revoke('owner')
        data = b'{}'
        self.fault('unauthorised', self.jobs.heartbeat, self.owner, 'local-1', grant['job'], grant['lease'])
        self.fault('unauthorised', self.jobs.complete, self.owner, 'local-1', grant['job'], grant['lease'],
                   sha256=hashlib.sha256(data).hexdigest(), data=data)
        self.fault('unauthorised', self.jobs.lease, self.owner, 'local-1')

    def test_only_the_enrolling_owner_operates_a_worker(self):
        self.jobs.submit(self.owner, self.request())
        self.fault('worker_operator_mismatch', self.jobs.lease, self.second, 'local-1')
        self.fault('forbidden', self.jobs.lease, self.reader, 'local-1')
        self.fault('forbidden', self.jobs.enrol_worker, self.reader, 'mine', 'Reader worker', ALL_KINDS)

    def test_stale_lease_token_rejected(self):
        self.jobs.submit(self.owner, self.request())
        grant = self.leased()
        self.fault('stale_lease', self.jobs.start, self.owner, 'local-1', grant['job'], 'f' * 32, backend='test')
        self.fault('stale_lease', self.jobs.heartbeat, self.owner, 'local-1', grant['job'], None)


class ResultTests(Base):
    def test_artefact_hash_mismatch_rejected_and_recorded(self):
        job = self.jobs.submit(self.owner, self.request())
        grant = self.started()
        data = b'{"claimed":true}'
        self.fault('artefact_hash_mismatch', self.jobs.complete, self.owner, 'local-1', grant['job'], grant['lease'],
                   sha256=hashlib.sha256(b'other bytes').hexdigest(), data=data)
        view = self.jobs.view(self.owner, job['id'])
        self.assertEqual((view['state'], view['result']), ('running', None))
        rejected = self.jobs.events(self.owner, job['id'])['events'][-1]
        self.assertEqual((rejected['kind'], rejected['detail']['actual_sha256']),
                         ('result_rejected', hashlib.sha256(data).hexdigest()))
        done = self.jobs.complete(self.owner, 'local-1', grant['job'], grant['lease'],
                                  sha256=hashlib.sha256(data).hexdigest(), data=data)
        self.assertEqual(done['state'], 'succeeded')
        self.assertEqual(done['result']['basis'], 'worker_claim_bytes_match_sha256_content_not_verified')
        self.assertEqual(self.jobs.artefact(self.owner, done['result']['sha256'])['data'], data)

    def test_non_json_result_refused(self):
        self.jobs.submit(self.owner, self.request())
        grant = self.started()
        data = b'not json'
        self.fault('result_not_json', self.jobs.complete, self.owner, 'local-1', grant['job'], grant['lease'],
                   sha256=hashlib.sha256(data).hexdigest(), data=data)

    def run_job(self, **kwargs):
        job = self.jobs.submit(self.owner, self.request(**kwargs))
        JobWorker(self.jobs, LocalSubprocessBackend(wall_clock=10), self.owner, 'local-1',
                  heartbeat_seconds=0.05).run_once()
        return self.jobs.view(self.owner, job['id'])

    def test_artefact_feeds_a_later_job(self):
        first = self.run_job()
        second = self.run_job(key='k2', kind='summarise_lines', parameters={'max_lines': 3},
                              inputs=[{'artefact': first['result']['sha256']}])
        self.assertEqual(second['state'], 'succeeded')
        output = json.loads(self.jobs.artefact(self.owner, second['result']['sha256'])['data'])
        self.assertEqual(output['inputs'][0]['sha256'], first['result']['sha256'])
        lineage = self.jobs.artefact(self.owner, second['result']['sha256'])['lineage']
        self.assertEqual(lineage['sources'], ['source'])

    def test_reading_and_reusing_a_result_rechecks_its_sources(self):
        self.grant('source')
        done = self.run_job()
        self.assertEqual(self.jobs.artefact(self.owner, done['result']['sha256'])['size'], done['result']['size'])
        # Grants are per person: the reader holds none, so strict policy hides the result from it.
        self.fault('artefact_not_available', self.jobs.artefact, self.reader, done['result']['sha256'])
        self.grant('source', revoke=True)
        self.fault('artefact_not_available', self.jobs.artefact, self.owner, done['result']['sha256'])
        self.fault('inputs_denied', self.jobs.submit, self.owner,
                   self.request(key='k2', inputs=[{'artefact': done['result']['sha256']}]))


class CancellationTests(Base):
    def test_queued_job_is_cancelled_immediately(self):
        job = self.jobs.submit(self.owner, self.request())
        view = self.jobs.cancel(self.owner, job['id'])
        self.assertEqual((view['state'], view['reason'], view['cancel_requested']), ('cancelled', 'cancelled_before_lease', True))
        self.assertIsNone(self.jobs.lease(self.owner, 'local-1'))
        self.assertEqual(self.jobs.cancel(self.owner, job['id'])['state'], 'cancelled')

    def test_cancel_before_start_is_honoured_by_the_worker(self):
        job = self.jobs.submit(self.owner, self.request())
        grant = self.leased()
        self.assertEqual(self.jobs.cancel(self.owner, job['id'])['state'], 'cancel_requested')
        started = self.jobs.start(self.owner, 'local-1', grant['job'], grant['lease'], backend='test')
        self.assertTrue(started['cancel_requested'])
        self.assertEqual(self.jobs.fail(self.owner, 'local-1', grant['job'], grant['lease'], 'cancelled')['state'], 'cancelled')

    def test_running_job_is_stopped_through_the_backend(self):
        backend = LocalSubprocessBackend(wall_clock=60)
        job = self.jobs.submit(self.owner, self.request(kind='wait', parameters={'seconds': 30}))
        worker = JobWorker(self.jobs, backend, self.owner, 'local-1', heartbeat_seconds=0.05, poll_seconds=0.02)
        self.background(worker)
        pid = self.wait_for(lambda: backend.process_id(job['id'] + '.1'))
        self.assertTrue(alive(pid))
        began = time.monotonic()
        self.assertEqual(self.jobs.cancel(self.owner, job['id'])['state'], 'cancel_requested')
        view = self.wait_for(lambda: (v := self.jobs.view(self.owner, job['id']))['finished'] and v)
        self.assertLess(time.monotonic() - began, 10)
        self.assertEqual((view['state'], view['reason']), ('cancelled', 'cancelled'))
        self.wait_for(lambda: not alive(pid))
        self.assertEqual(self.kinds(job['id']), ['submitted', 'leased', 'started', 'cancel_requested', 'cancelled'])

    def test_finished_job_cancellation_is_not_undo(self):
        job = self.jobs.submit(self.owner, self.request())
        grant = self.started()
        data = b'{}'
        self.jobs.complete(self.owner, 'local-1', grant['job'], grant['lease'], sha256=hashlib.sha256(data).hexdigest(), data=data)
        self.fault('cancellation_is_not_undo', self.jobs.cancel, self.owner, job['id'])

    def test_result_after_cancel_request_is_recorded_honestly(self):
        job = self.jobs.submit(self.owner, self.request())
        grant = self.started()
        self.jobs.cancel(self.owner, job['id'])
        data = b'{}'
        view = self.jobs.complete(self.owner, 'local-1', grant['job'], grant['lease'], sha256=hashlib.sha256(data).hexdigest(), data=data)
        self.assertEqual(view['state'], 'succeeded')
        self.assertIn('completed_after_cancel_request', self.kinds(job['id']))


class RecoveryTests(Base):
    def test_expired_lease_requeues_side_effect_free_job_with_bounded_retries(self):
        job = self.jobs.submit(self.owner, self.request(max_attempts=2))
        self.started()
        self.clock[0] += 31
        self.assertEqual(self.jobs.recover(self.owner)['requeued'], [job['id']])
        self.assertEqual(self.leased()['attempt'], 2)
        self.clock[0] += 31
        self.assertIsNone(self.jobs.lease(self.owner, 'local-1'))
        view = self.jobs.view(self.owner, job['id'])
        self.assertEqual((view['state'], view['reason'], view['attempt']), ('failed', 'attempts_exhausted', 2))

    def test_job_with_possible_effects_becomes_effect_unknown_and_is_not_retried(self):
        job = self.jobs.submit(self.owner, self.request(side_effect_free=False))
        self.started()
        self.clock[0] += 31
        self.assertIsNone(self.jobs.lease(self.owner, 'local-1'))
        view = self.jobs.view(self.owner, job['id'])
        self.assertEqual((view['state'], view['reason'], view['needs_reconciliation']),
                         ('effect_unknown', 'lease_expired_with_possible_effect', True))
        self.fault('cancellation_is_not_undo', self.jobs.cancel, self.owner, job['id'])
        self.fault('forbidden', self.jobs.reconcile, self.reader, job['id'], 'effect_did_not_happen')
        reconciled = self.jobs.reconcile(self.owner, job['id'], 'effect_did_not_happen')
        self.assertEqual((reconciled['state'], reconciled['reason']), ('reconciled', 'effect_did_not_happen'))
        self.assertEqual(self.jobs.events(self.owner, job['id'])['events'][-1]['detail']['basis'],
                         'owner_acknowledgement_not_verification')
        self.fault('invalid_state', self.jobs.reconcile, self.owner, job['id'], 'effect_happened')

    def test_worker_failure_of_job_with_effects_is_effect_unknown(self):
        job = self.jobs.submit(self.owner, self.request(side_effect_free=False))
        grant = self.started()
        view = self.jobs.fail(self.owner, 'local-1', grant['job'], grant['lease'], 'process_failed', retryable=True)
        self.assertEqual(view['state'], 'effect_unknown')
        self.assertIsNone(self.jobs.lease(self.owner, 'local-1'))
        self.assertEqual(self.jobs.view(self.owner, job['id'])['attempt'], 1)

    def test_retryable_failure_requeues_side_effect_free_job_within_attempts(self):
        job = self.jobs.submit(self.owner, self.request(max_attempts=2))
        grant = self.started()
        self.assertEqual(self.jobs.fail(self.owner, 'local-1', grant['job'], grant['lease'], 'process_failed', retryable=True)['state'], 'queued')
        grant = self.started()
        self.assertEqual(self.jobs.fail(self.owner, 'local-1', grant['job'], grant['lease'], 'process_failed', retryable=True)['state'], 'failed')
        self.assertIn('retry_scheduled', self.kinds(job['id']))

    def test_new_coordinator_over_same_database_recovers_state(self):
        job = self.jobs.submit(self.owner, self.request(kind='summarise_lines', parameters={'max_lines': 2}))
        self.started()
        before_view, before_events = self.jobs.view(self.owner, job['id']), self.jobs.events(self.owner, job['id'])
        del self.jobs, self.store
        self.store = self.open_store()
        self.jobs = JobCoordinator(self.store)
        self.assertEqual(self.jobs.view(self.owner, job['id']), before_view)
        self.assertEqual(self.jobs.events(self.owner, job['id']), before_events)
        self.clock[0] += 31
        self.assertEqual(self.jobs.recover(self.owner)['requeued'], [job['id']])
        JobWorker(self.jobs, LocalSubprocessBackend(wall_clock=10), self.owner, 'local-1').run_once()
        page = self.jobs.events(self.owner, job['id'], before_view['last_sequence'])
        self.assertEqual([e['kind'] for e in page['events']], ['lease_expired', 'leased', 'started', 'succeeded'])
        self.assertEqual([e['sequence'] for e in page['events']], list(range(before_view['last_sequence'] + 1, before_view['last_sequence'] + 5)))
        output = json.loads(self.jobs.artefact(self.owner, self.jobs.view(self.owner, job['id'])['result']['sha256'])['data'])
        self.assertEqual(output['inputs'][0]['selected'], ['# Plan', 'Alpha bravo charlie.'])


class BackendTests(Base):
    def run_one(self, backend, **kwargs):
        job = self.jobs.submit(self.owner, self.request(**kwargs))
        JobWorker(self.jobs, backend, self.owner, 'local-1', heartbeat_seconds=0.05).run_once()
        return self.jobs.view(self.owner, job['id'])

    def test_interface_is_abstract(self):
        with self.assertRaises(TypeError):
            WorkerBackend()
        self.assertEqual(LocalSubprocessBackend.name, 'local_subprocess')

    def test_wall_clock_limit_kills_a_slow_job(self):
        backend = LocalSubprocessBackend(wall_clock=0.5)
        began = time.monotonic()
        view = self.run_one(backend, kind='wait', parameters={'seconds': 30})
        self.assertLess(time.monotonic() - began, 10)
        self.assertEqual((view['state'], view['reason']), ('failed', 'wall_clock_limit'))

    def test_output_size_limit(self):
        view = self.run_one(LocalSubprocessBackend(output_limit=64))
        self.assertEqual((view['state'], view['reason']), ('failed', 'output_too_large'))

    def test_child_reports_its_own_validation_error(self):
        backend = LocalSubprocessBackend(wall_clock=10)
        backend.submit('direct.1', 'summarise_lines', {'max_lines': 0}, [])
        result = backend.collect('direct.1')
        self.assertEqual((result.ok, result.reason, result.exit_code), (False, 'invalid_parameters', 2))

    def test_backend_refuses_unknown_kinds(self):
        self.fault('unknown_job_kind', LocalSubprocessBackend().submit, 'direct.1', 'shell', {}, [])

    @unittest.skipUnless(Path('/proc/self/environ').exists(), 'needs Linux /proc')
    def test_child_gets_no_environment_path_or_credential(self):
        backend = LocalSubprocessBackend(wall_clock=10)
        backend.submit('direct.1', 'wait', {'seconds': 5}, [{'name': 'input-0', 'data': b'synthetic'}])
        try:
            pid = backend.process_id('direct.1')
            self.assertEqual(Path(f'/proc/{pid}/environ').read_bytes(), b'')
            command = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
            self.assertIn(b'-I', command)
            self.assertNotIn(str(self.db_path).encode(), b' '.join(command))
            self.assertNotIn(self.owner.encode(), b' '.join(command))
            self.assertNotEqual(Path(os.readlink(f'/proc/{pid}/cwd')), REPOSITORY)
        finally:
            backend.cancel('direct.1')
            self.assertEqual(backend.collect('direct.1').reason, 'cancelled')

    def test_guard_refuses_network_files_and_processes_in_the_child(self):
        snippet = (
            'import importlib.util, socket, subprocess\n'
            f'spec = importlib.util.spec_from_file_location("kinds", {str(LocalSubprocessBackend.PROGRAM)!r})\n'
            'kinds = importlib.util.module_from_spec(spec); spec.loader.exec_module(kinds)\n'
            'kinds.install_guard()\n'
            'for attempt in (lambda: socket.socket(), lambda: open("x", "w"), lambda: subprocess.Popen(["true"])):\n'
            '    try:\n'
            '        attempt(); print("allowed")\n'
            '    except PermissionError:\n'
            '        print("refused")\n')
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', snippet], capture_output=True,
                                text=True, env={}, cwd=self.root, timeout=30)
        self.assertEqual(result.stdout.split(), ['refused', 'refused', 'refused'])


CLIENT = r'''
import json, sys, time
from alfred.knowledge import KnowledgeStore
from alfred.jobs import JobCoordinator
config = json.loads(sys.stdin.read())
jobs = JobCoordinator(KnowledgeStore(config['database']))
job = jobs.submit(config['bearer'], config['request'])
cursor, seen, deadline = 0, [], time.monotonic() + 20
while time.monotonic() < deadline:
    page = jobs.events(config['bearer'], job['id'], cursor)
    seen += [event['kind'] for event in page['events']]
    cursor = page['next_cursor']
    if 'started' in seen or page['finished']:
        break
    time.sleep(0.02)
print(json.dumps({'job': job['id'], 'cursor': cursor, 'seen': seen, 'state': page['state']}))
'''


class ReconnectTests(Base):
    real_clock = True

    def test_client_disconnects_and_a_new_client_resumes_from_its_cursor(self):
        worker = JobWorker(self.jobs, LocalSubprocessBackend(wall_clock=30), self.owner, 'local-1',
                           heartbeat_seconds=0.1, poll_seconds=0.02)
        self.background(worker)
        config = {'database': str(self.db_path), 'bearer': self.owner,
                  'request': self.request(kind='wait', parameters={'seconds': 1.5})}
        client = subprocess.run([sys.executable, '-c', CLIENT], input=json.dumps(config), capture_output=True,
                                text=True, cwd=REPOSITORY, timeout=60)
        self.assertEqual(client.returncode, 0, client.stderr)
        gone = json.loads(client.stdout)
        # The submitting client process has exited while the job is still running.
        self.assertEqual((gone['seen'], gone['state']), (['submitted', 'leased', 'started'], 'running'))
        later = JobCoordinator(self.open_store())
        resumed = self.wait_for(lambda: (page := later.events(self.owner, gone['job'], gone['cursor']))['finished'] and page)
        self.assertEqual([e['sequence'] for e in resumed['events']], [gone['cursor'] + 1])
        self.assertEqual((resumed['events'][0]['kind'], resumed['state']), ('succeeded', 'succeeded'))
        full = later.events(self.owner, gone['job'])
        self.assertEqual([e['sequence'] for e in full['events']], [1, 2, 3, 4])
        view = later.view(self.reader, gone['job'])
        output = json.loads(later.artefact(self.reader, view['result']['sha256'])['data'])
        self.assertEqual(output['inputs'][0]['sha256'], hashlib.sha256(PLAN.encode()).hexdigest())


class CacheTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'cache'

    def item(self, label, size=40):
        return (label * size)[:size].encode()

    def test_hard_limit_and_least_recently_used_eviction(self):
        cache = BoundedCache(self.root, 100)
        a, b = cache.put(self.item('a')), cache.put(self.item('b'))
        self.assertEqual(cache.get(a), self.item('a'))
        c = cache.put(self.item('c'))
        self.assertEqual((cache.contains(a), cache.contains(b), cache.contains(c)), (True, False, True))
        usage = cache.usage()
        self.assertEqual((usage['used_bytes'], usage['entries']), (80, 2))
        self.assertLessEqual(usage['used_bytes'], usage['limit_bytes'])
        stored = sum(p.stat().st_size for p in (self.root / 'objects').rglob('*') if p.is_file())
        self.assertEqual(stored, 80)

    def test_pinned_entries_are_never_evicted(self):
        cache = BoundedCache(self.root, 100)
        pinned = cache.put(self.item('p'), pin=True)
        cache.put(self.item('q'))
        cache.put(self.item('r'))
        self.assertTrue(cache.contains(pinned))
        self.fault('cache_full_of_pinned_entries', cache.put, self.item('s', 70), pin=True)
        cache.unpin(pinned)
        cache.put(self.item('t'))
        cache.put(self.item('u'))
        self.assertFalse(cache.contains(pinned))
        self.assertEqual(cache.usage()['pinned_entries'], 0)

    def test_item_larger_than_limit_is_refused(self):
        cache = BoundedCache(self.root, 100)
        self.fault('cache_item_too_large', cache.put, self.item('z', 101))
        self.assertEqual(cache.usage()['entries'], 0)

    def test_corrupted_entry_is_detected_and_removed(self):
        cache = BoundedCache(self.root, 100)
        sha = cache.put(self.item('a'), pin=True)
        path = self.root / 'objects' / sha[:2] / sha
        path.write_bytes(self.item('b'))
        self.fault('cache_entry_corrupt', cache.get, sha)
        self.assertIsNone(cache.get(sha))
        usage = cache.usage()
        self.assertEqual((usage['corrupt_removed'], usage['pinned_missing']), (1, [sha]))

    def test_pins_and_entries_survive_restart_and_a_lower_limit_evicts_unpinned(self):
        cache = BoundedCache(self.root, 100)
        pinned = cache.put(self.item('p'), pin=True)
        loose = cache.put(self.item('l'))
        reopened = BoundedCache(self.root, 50)
        self.assertEqual(reopened.pins(), [pinned])
        self.assertEqual((reopened.contains(pinned), reopened.contains(loose)), (True, False))
        self.fault('cache_pins_exceed_limit', BoundedCache, self.root, 10)

    def test_crash_leftovers_and_missing_files_are_reconciled(self):
        cache = BoundedCache(self.root, 100)
        kept, lost = cache.put(self.item('k')), cache.put(self.item('m'))
        (self.root / 'objects' / lost[:2] / lost).unlink()
        (self.root / 'incoming' / 'partial').write_bytes(b'half')
        orphan = self.root / 'objects' / 'ab' / ('ab' + '0' * 62)
        orphan.parent.mkdir(exist_ok=True)
        orphan.write_bytes(b'orphan')
        reopened = BoundedCache(self.root, 100)
        self.assertEqual((reopened.contains(kept), reopened.contains(lost)), (True, False))
        self.assertFalse(orphan.exists())
        self.assertEqual(list((self.root / 'incoming').iterdir()), [])
        self.assertEqual(reopened.usage()['used_bytes'], 40)

    def test_private_directory_outside_the_repository(self):
        cache = BoundedCache(self.root, 100)
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        sha = cache.put(self.item('a'))
        self.assertEqual((self.root / 'objects' / sha[:2] / sha).stat().st_mode & 0o777, 0o600)
        self.fault('cache_inside_repository', BoundedCache, REPOSITORY / 'cache-should-not-exist', 100)
        self.assertFalse((REPOSITORY / 'cache-should-not-exist').exists())

    def fault(self, code, fn, *args, **kwargs):
        with self.assertRaises(Fault) as caught:
            fn(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)


class CoordinatorCacheTests(Base):
    def test_corrupt_cached_copy_falls_back_to_the_record(self):
        cache = BoundedCache(self.root / 'cache', 4096)
        self.jobs = JobCoordinator(self.store, cache=cache)
        job = self.jobs.submit(self.owner, self.request())
        JobWorker(self.jobs, LocalSubprocessBackend(wall_clock=10), self.owner, 'local-1').run_once()
        sha = self.jobs.view(self.owner, job['id'])['result']['sha256']
        self.assertEqual(self.jobs.artefact(self.owner, sha)['served_from'], 'cache')
        (self.root / 'cache' / 'objects' / sha[:2] / sha).write_bytes(b'tampered')
        served = self.jobs.artefact(self.owner, sha)
        self.assertEqual((served['served_from'], hashlib.sha256(served['data']).hexdigest()), ('database', sha))
        self.assertEqual(cache.usage()['corrupt_removed'], 1)
        self.assertEqual(self.jobs.artefact(self.owner, sha)['served_from'], 'cache')


class ScopeIsolationTests(Base):
    def test_other_workspace_cannot_view_cancel_or_read_events(self):
        job = self.jobs.submit(self.owner, self.request())
        for call in (self.jobs.view, self.jobs.cancel, self.jobs.events):
            self.fault('not_found', call, self.foreign, job['id'])
        self.assertEqual(self.jobs.jobs(self.foreign), [])
        self.assertEqual(self.jobs.view(self.owner, job['id'])['state'], 'queued')

    def test_other_workspace_cannot_lease(self):
        job = self.jobs.submit(self.owner, self.request())
        self.fault('not_found', self.jobs.lease, self.foreign, 'local-1')
        self.jobs.enrol_worker(self.foreign, 'local-1', 'Foreign worker', ALL_KINDS)
        self.assertIsNone(self.jobs.lease(self.foreign, 'local-1'))
        self.assertEqual(self.jobs.view(self.owner, job['id'])['state'], 'queued')
        self.assertEqual([w['scope'] for w in self.jobs.workers(self.foreign)], ['other'])

    def test_other_workspace_cannot_read_or_reuse_a_result(self):
        job = self.jobs.submit(self.owner, self.request())
        JobWorker(self.jobs, LocalSubprocessBackend(wall_clock=10), self.owner, 'local-1').run_once()
        sha = self.jobs.view(self.owner, job['id'])['result']['sha256']
        self.fault('artefact_not_available', self.jobs.artefact, self.foreign, sha)
        self.fault('inputs_denied', self.jobs.submit, self.foreign, self.request(inputs=[{'artefact': sha}]))
        self.fault('inputs_denied', self.jobs.submit, self.foreign, self.request(key='k2'))

    def test_reader_views_but_cannot_cancel_or_revoke(self):
        job = self.jobs.submit(self.owner, self.request())
        self.assertEqual(self.jobs.view(self.reader, job['id'])['id'], job['id'])
        self.fault('forbidden', self.jobs.cancel, self.reader, job['id'])
        self.fault('forbidden', self.jobs.revoke_worker, self.reader, 'local-1')
        self.fault('forbidden', self.jobs.recover, self.reader)


if __name__ == '__main__':
    unittest.main()
