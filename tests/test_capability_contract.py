"""OPS-002 contract tests with a synthetic adapter. No real specialist product is involved."""
import tempfile
import unittest
from pathlib import Path
from alfred.local import Fault
from alfred.desk_store import DeskStore
from alfred.capabilities import (SpecialistBridge, SyntheticExerciseAdapter, validate_manifest)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.clock = [1_000_000]
        self.store = DeskStore(Path(self.tmp.name) / 'desk.db', clock=lambda: self.clock[0])
        self.owner = self.store.provision('exercise', 'owner', 'owner', legacy_scope=True)
        self.feed = self.store.provision('exercise', 'specialist-synthetic-exercise', 'source', legacy_scope=True)
        self.adapter = SyntheticExerciseAdapter(self.clock[0])

    def bridge(self, adapter=None, bearer=None):
        return SpecialistBridge(self.store, bearer or self.feed, adapter or self.adapter)

    def events(self):
        return {e['subject']: e for e in self.store.desk_state(self.owner)['events']}

    def test_synthetic_feed_keeps_original_times_and_simulation_labels(self):
        outcomes = self.bridge().sync()
        self.assertTrue(all(o['accepted'] for o in outcomes))
        events = self.events()
        self.assertEqual(events['exercise-site-a']['observed_at'], self.clock[0] - 600)
        self.assertTrue(all(e['basis'] == 'simulated' for e in events.values()))
        self.assertTrue(all('simulation' in e['summary'] for e in events.values()))
        self.assertTrue(all(e['reason'] == 'analysis_not_observation' for e in events.values()))

    def test_replayed_or_simulated_data_cannot_be_called_an_observation(self):
        bad = SyntheticExerciseAdapter(self.clock[0], observations=[
            {'record_id': 'x', 'kind': 'status', 'observed_at': self.clock[0] - 10, 'basis': 'observed', 'health': 'ok', 'summary': 'Claims to be live.', 'evidence': []}])
        self.assertEqual(self.bridge(bad).sync()[0]['reason'], 'simulation_mislabelled_as_observation')
        self.assertEqual(self.events(), {})

    def test_an_assessment_is_never_an_observation(self):
        live = SyntheticExerciseAdapter(self.clock[0], mode='live', observations=[
            {'record_id': 'x', 'kind': 'assessment', 'observed_at': self.clock[0] - 10, 'basis': 'observed', 'health': 'ok', 'summary': 'An opinion.', 'evidence': []}])
        self.assertEqual(self.bridge(live).sync()[0]['reason'], 'assessment_is_not_observation')

    def test_future_and_malformed_observations_are_rejected_individually(self):
        mixed = SyntheticExerciseAdapter(self.clock[0], observations=[
            {'record_id': 'future', 'kind': 'status', 'observed_at': self.clock[0] + 60, 'basis': 'simulated', 'health': 'ok', 'summary': 'Later.', 'evidence': []},
            {'record_id': 'extra', 'kind': 'status', 'observed_at': self.clock[0] - 60, 'basis': 'simulated', 'health': 'ok', 'summary': 'Ok.', 'evidence': [], 'secret': 'x'},
            {'record_id': 'good', 'kind': 'report', 'observed_at': self.clock[0] - 60, 'basis': 'simulated', 'health': 'ok', 'summary': 'Fine.', 'evidence': []}])
        outcomes = self.bridge(mixed).sync()
        self.assertEqual([o['accepted'] for o in outcomes], [False, False, True])
        self.assertEqual(list(self.events()), ['good'])

    def test_stale_observations_are_recorded_as_expired_not_current(self):
        old = SyntheticExerciseAdapter(self.clock[0], observations=[
            {'record_id': 'old', 'kind': 'status', 'observed_at': self.clock[0] - 7200, 'basis': 'simulated', 'health': 'ok', 'summary': 'Old.', 'evidence': []}])
        self.assertEqual(self.bridge(old).sync()[0]['reason'], 'expired')

    def test_duplicates_are_idempotent(self):
        bridge = self.bridge(); bridge.sync()
        self.assertTrue(all(o['reason'] == 'duplicate' for o in bridge.sync()))

    def test_actions_are_declared_but_never_enabled(self):
        bridge = self.bridge()
        states = {c['id']: c['state'] for c in bridge.capabilities()}
        self.assertEqual(states, {'read_status': 'available_read_only', 'request_check': 'declared_not_enabled'})
        with self.assertRaises(Fault) as caught:
            bridge.invoke('request_check', {})
        self.assertEqual(caught.exception.code, 'action_not_enabled')

    def test_a_product_cannot_write_as_another_product(self):
        other = self.store.provision('exercise', 'specialist-other', 'source', legacy_scope=True)
        with self.assertRaises(Fault) as caught:
            self.bridge(bearer=other)
        self.assertEqual(caught.exception.code, 'adapter_credential_mismatch')

    def test_live_simulation_is_refused_outside_a_simulation_workspace(self):
        live_store = DeskStore(Path(self.tmp.name) / 'live.db', clock=lambda: self.clock[0])
        live_store.provision('real', 'owner', 'owner', simulation=False)
        feed = live_store.provision('real', 'specialist-synthetic-exercise', 'source', simulation=False)
        outcomes = SpecialistBridge(live_store, feed, self.adapter).sync()
        self.assertTrue(all(o['reason'] == 'simulation_not_live' for o in outcomes))

    def test_manifest_rules(self):
        good = self.adapter.manifest()
        self.assertIs(validate_manifest(good), good)
        broken = [
            {**good, 'contract_version': 2},
            {**good, 'mode': 'production'},
            {**good, 'product': {**good['product'], 'independent': False}},
            {**good, 'identity': {**good['identity'], 'stable': False}},
            {**good, 'capabilities': [{**good['capabilities'][0], 'effect': 'external'}]},
            {**good, 'capabilities': [{**good['capabilities'][1], 'approval': 'not_required'}]},
            {**good, 'capabilities': [good['capabilities'][0], good['capabilities'][0]]},
            {**good, 'freshness_seconds': 10},
        ]
        for manifest in broken:
            with self.assertRaises(Fault):
                validate_manifest(manifest)


if __name__ == '__main__':
    unittest.main()
