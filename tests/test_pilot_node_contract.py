"""Trusted-node groundwork on the existing single SQLite authority.

Two logical worker IDs and actual transaction races on one host. This is not a
second machine, remote transport or isolation certification.
"""
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from alfred.jobs import JobCoordinator
from alfred.knowledge import KnowledgeStore, MarkdownVault
from alfred.local import Fault
from alfred.policy import IdentityPolicy


class NodeContractTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name); self.now = 1000
        self.store = KnowledgeStore(root / 'db', clock=lambda: self.now)
        self.owner = self.store.provision('work', 'owner', 'owner')
        source = self.store.provision('work', 'source', 'source')
        IdentityPolicy(self.store).grant(self.owner, 'source', 'read', 5000, 0)
        vault = root / 'vault'; vault.mkdir(); (vault / 'Plan.md').write_text('# Plan\nSynthetic node contract.\n')
        MarkdownVault(self.store, source, vault).scan()
        self.jobs = JobCoordinator(self.store)
        for worker in ('a', 'b'):
            self.jobs.enrol_worker(self.owner, worker, 'Synthetic ' + worker, ['word_count'])
        self.job = self.jobs.submit(self.owner, {'idempotency_key': 'one-authority', 'kind': 'word_count',
            'parameters': {}, 'inputs': [{'note': self.store.knowledge(self.owner)['nodes'][0]['id']}], 'side_effect_free': True})

    def test_simultaneous_workers_receive_one_lease(self):
        barrier = threading.Barrier(2); outcomes, errors = [], []
        def take(worker):
            try:
                # Two handles to the same durable authority, never two writable replicas.
                coordinator = JobCoordinator(KnowledgeStore(self.store.path, clock=lambda: self.now))
                barrier.wait(5); outcomes.append(coordinator.lease(self.owner, worker))
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=take, args=(w,)) for w in ('a', 'b')]
        for thread in threads: thread.start()
        for thread in threads: thread.join(10)
        self.assertFalse(any(t.is_alive() for t in threads)); self.assertEqual(errors, [])
        self.assertEqual(len(outcomes), 2); self.assertEqual(sum(x is not None for x in outcomes), 1)
        self.assertEqual(self.jobs.view(self.owner, self.job['id'])['attempt'], 1)

    def test_reconnected_worker_cannot_publish_a_stale_attempt(self):
        old = self.jobs.lease(self.owner, 'a', ttl=1); self.now = 1002
        self.jobs.recover(self.owner); new = self.jobs.lease(self.owner, 'b')
        data = b'{"synthetic":true}'; digest = hashlib.sha256(data).hexdigest()
        with self.assertRaises(Fault) as stale:
            self.jobs.complete(self.owner, 'a', old['job'], old['lease'], sha256=digest, data=data)
        self.assertEqual(stale.exception.code, 'stale_lease')
        result = self.jobs.complete(self.owner, 'b', new['job'], new['lease'], sha256=digest, data=data)
        self.assertEqual(result['state'], 'succeeded')
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM artefacts').fetchone()[0], 1)

    def test_cancel_is_reconciled_after_disconnect_without_new_lease(self):
        lease = self.jobs.lease(self.owner, 'a', ttl=1)
        self.jobs.cancel(self.owner, lease['job'])
        self.assertTrue(self.jobs.heartbeat(self.owner, 'a', lease['job'], lease['lease'], ttl=1)['cancel_requested'])
        self.now = 1002; self.jobs.recover(self.owner)
        self.assertIsNone(self.jobs.lease(self.owner, 'b'))
        self.assertEqual(self.jobs.view(self.owner, lease['job'])['state'], 'cancelled')

    def test_forked_worker_identity_has_no_original_lease_authority(self):
        lease = self.jobs.lease(self.owner, 'a')
        with self.assertRaises(Fault) as fork:
            self.jobs.heartbeat(self.owner, 'b', lease['job'], lease['lease'])
        self.assertEqual(fork.exception.code, 'stale_lease')
        self.jobs.revoke_worker(self.owner, 'a')
        with self.assertRaises(Fault) as revoked:
            self.jobs.heartbeat(self.owner, 'a', lease['job'], lease['lease'])
        self.assertEqual(revoked.exception.code, 'worker_revoked')
