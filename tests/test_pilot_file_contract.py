"""A bounded opt-in model, not cloud-provider or FUSE acceptance."""
from pathlib import Path
import tempfile
import unittest
from alfred.jobs import BoundedCache
from alfred.local import Fault
from prototypes.pilot_file_tier import SyntheticFileTier


class FileContractTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.cache = BoundedCache(Path(tmp.name) / 'cache', 64)
        self.grants = {'read': True, 'write': True}; self.epoch = 1
        def authority(purpose):
            if not self.grants[purpose]:
                raise Fault('source_not_granted', 403)
            return self.epoch
        self.authority = authority
        self.files = SyntheticFileTier(self.cache, authority, synthetic=True)
        self.first = self.files.publish('plan', b'synthetic:planning')

    def test_opt_in_and_synthetic_budget_are_required(self):
        with self.assertRaises(Fault):
            SyntheticFileTier(self.cache, self.authority)
        for data in (b'private-looking input', b'synthetic:' + b'x' * 4096):
            with self.assertRaises(Fault):
                self.files.publish('unbounded', data)

    def test_on_demand_pin_does_not_turn_into_access_authority(self):
        self.assertEqual(self.files.read_requests, 0)
        self.files.read('plan', pin=True)
        self.assertEqual(self.files.read_requests, 1)
        self.assertEqual(self.files.read('plan', offline=True)[1], b'synthetic:planning')
        self.grants['read'] = False
        with self.assertRaises(Fault):
            self.files.read('plan', offline=True)

    def test_revision_conflict_and_stale_offline_copy(self):
        self.files.read('plan', pin=True)
        self.files.publish('plan', b'synthetic:ready', expected_revision=1)
        with self.assertRaises(Fault) as missing:
            self.files.read('plan', offline=True)
        self.assertEqual(missing.exception.code, 'offline_copy_missing')
        with self.assertRaises(Fault) as conflict:
            self.files.publish('plan', b'synthetic:wrong', expected_revision=1)
        self.assertEqual(conflict.exception.code, 'file_revision_conflict')

    def test_mid_fetch_revocation_does_not_cache_or_deliver_bytes(self):
        def revoke():
            self.grants['read'] = False; self.epoch += 1
        with self.assertRaises(Fault):
            self.files.read('plan', after_fetch=revoke)
        self.assertEqual(self.cache.usage()['used_bytes'], 0)

    def test_delete_removes_all_local_revisions_and_prevents_resurrection(self):
        self.files.read('plan', pin=True)
        self.files.publish('plan', b'synthetic:ready', expected_revision=1); self.files.read('plan', pin=True)
        receipt = self.files.delete('plan', expected_revision=2)
        self.assertEqual(receipt['cache_revisions_removed'], 2)
        self.assertEqual(self.cache.usage()['used_bytes'], 0)
        self.assertEqual(self.cache.pins(), [])
        with self.assertRaises(Fault):
            self.files.read('plan')
        with self.assertRaises(Fault) as removed:
            self.files.publish('plan', b'synthetic:revive', expected_revision=3)
        self.assertEqual(removed.exception.code, 'file_tombstoned')

    def test_pinned_capacity_is_not_silently_evicted(self):
        self.files.read('plan', pin=True)
        self.files.publish('other', b'synthetic:' + b'x' * 48)
        with self.assertRaises(Fault) as full:
            self.files.read('other', pin=True)
        self.assertEqual(full.exception.code, 'cache_full_of_pinned_entries')
        self.assertEqual(self.files.read('plan', offline=True)[1], b'synthetic:planning')
