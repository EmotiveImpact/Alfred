"""Synthetic ALFRED authority and recovery contracts; real transport has its own check."""
from pathlib import Path
import json
import os
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch
from alfred.knowledge import KnowledgeStore
from alfred.local import Fault, canonical
from alfred.policy import IdentityPolicy
from alfred.lifecycle import forget_source, backup, restore
from alfred.livelens import LiveLensTools, connect, installed, load_configuration, route


class FixtureClient:
    """Only the network boundary is substituted in these ledger tests."""
    jobs = {}; writes = 0; hook = None; timeout_after_write = False; tokens = []

    def __init__(self, url, token, timeout):
        self.tokens.append(token)

    def capabilities(self):
        if type(self).hook:
            callback, type(self).hook = type(self).hook, None
            callback()
        return {'workspace': 'team'}

    def sessions(self):
        return {'sessions': [{'id': 'session'}, {'id': 'hidden'}]}

    def create_job(self, body):
        type(self).writes += 1
        result = dict(body, state='queued', privateSourceConfiguration='MUST_NOT_PERSIST')
        self.jobs[body['id']] = result
        if self.timeout_after_write:
            raise RuntimeError('synthetic timeout after acceptance')
        return result

    def job(self, identifier):
        return self.jobs[identifier]

    def stop_job(self, identifier):
        type(self).writes += 1
        self.jobs[identifier]['stopRequested'] = True
        return self.jobs[identifier]


class LiveLensTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.clock = 1800000000
        self.store = KnowledgeStore(self.home / 'desk.sqlite', clock=lambda: self.clock)
        self.owner = self.store.provision('scope', 'owner', 'owner', ttl=2592000)
        self.reader = self.store.provision('scope', 'reader', 'reader', ttl=2592000)
        self.other = self.store.provision('elsewhere', 'other', 'owner', ttl=2592000)
        self.source = self.store.provision('scope', 'specialist-livelens', 'source', ttl=2592000)
        self.policy = IdentityPolicy(self.store)
        self.token = 'x' * 43
        self.config = {'schemaVersion': 1, 'scope': 'scope', 'workspace': 'team',
                       'sourceCredential': 'specialist-livelens', 'baseUrl': 'http://127.0.0.1:1',
                       'sources': [{'id': 'fixture', 'sessionIds': ['session'], 'recorderSourceId': 'fixture_source'}],
                       'maxDurationSeconds': 6, 'timeoutSeconds': .1}
        self.tools = LiveLensTools(self.store, self.config, token_provider=lambda: self.token)
        FixtureClient.jobs = {}; FixtureClient.writes = 0; FixtureClient.hook = None
        FixtureClient.timeout_after_write = False; FixtureClient.tokens = []
        self.mock = patch('alfred.livelens_gateway.LiveLensClient', FixtureClient)
        self.mock.start(); self.addCleanup(self.mock.stop)

    def grant(self, capability, revoke=False):
        return self.policy.grant(self.owner, 'specialist-livelens', capability,
                                 self.clock + 3600, self.policy.view(self.owner)['epoch'], revoke=revoke)

    def grants(self, control=True):
        self.grant('connector.read'); self.grant('read')
        if control:
            self.grant('collection.control')

    def proposal(self, **parameters):
        self.grants()
        value = {'sourceId': 'fixture', 'sessionId': 'session', 'jobId': 'job', 'maxDurationSeconds': 6, 'segmentSeconds': 2}
        value.update(parameters)
        return self.tools.propose(self.owner, {'operation': 'start_recording', 'parameters': value, 'reason': 'Fictional approved capture'})

    def approved(self):
        action = self.proposal()
        self.tools.approve(self.owner, action['id'], {'fingerprint': action['fingerprint']})
        return action

    def denied(self, code, callback):
        with self.assertRaises(Fault) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_legacy_and_read_grant_do_not_enable_network_or_control(self):
        self.denied('livelens_source_denied', lambda: self.tools.discovery(self.owner))
        self.grant('read')
        self.denied('livelens_source_denied', lambda: self.tools.discovery(self.owner))
        self.grant('connector.read')
        self.assertFalse(self.tools.discovery(self.owner)['permissions']['collectionControl'])
        self.assertEqual(FixtureClient.tokens, [])
        self.denied('livelens_source_denied', lambda: self.tools.propose(self.owner,
            {'operation': 'stop_recording', 'parameters': {'sourceId': 'fixture', 'jobId': 'job'}, 'reason': 'Stop'}))

    def test_actor_scope_role_and_source_parameters_are_closed(self):
        self.grants()
        self.denied('livelens_not_available', lambda: self.tools.discovery(self.other))
        self.denied('forbidden', lambda: self.tools.propose(self.reader,
            {'operation': 'stop_recording', 'parameters': {'sourceId': 'fixture', 'jobId': 'job'}, 'reason': 'Stop'}))
        self.denied('invalid_fields', lambda: self.tools.read(self.owner,
            {'operation': 'sessions', 'parameters': {'sourceId': 'fixture'}, 'actor': 'owner'}))
        self.denied('livelens_source_denied', lambda: self.proposal(sessionId='hidden'))
        self.denied('invalid_livelens_duration', lambda: self.proposal(maxDurationSeconds=True))
        with self.assertRaises(Fault):
            LiveLensTools(self.store, dict(self.config, sourceCredential='demo-source'), token_provider=lambda: self.token)

    def test_exact_approval_and_duplicate_dispatch_do_not_repeat_effect(self):
        action = self.proposal()
        self.denied('livelens_action_requires_approval_or_reconciliation', lambda: self.tools.dispatch(self.owner, action['id'], {'fingerprint': action['fingerprint']}))
        self.denied('livelens_fingerprint_mismatch', lambda: self.tools.approve(self.owner, action['id'], {'fingerprint': 'wrong'}))
        self.tools.approve(self.owner, action['id'], {'fingerprint': action['fingerprint']})
        outcome = self.tools.dispatch(self.owner, action['id'], {'fingerprint': action['fingerprint']})
        self.assertEqual(outcome['state'], 'completed'); self.assertFalse(outcome['acceptanceIsCaptureCompletion'])
        self.assertNotIn('privateSourceConfiguration', outcome['receipt']['result'])
        self.tools.dispatch(self.owner, action['id'], {'fingerprint': action['fingerprint']})
        self.assertEqual(FixtureClient.writes, 1)
        with self.store.connection() as db:
            self.assertNotIn('MUST_NOT_PERSIST', db.execute('SELECT receipt FROM livelens_actions').fetchone()[0])

    def test_expiry_policy_epoch_and_configuration_invalidate_approval(self):
        action = self.proposal(); self.clock += 600
        self.denied('livelens_approval_expired', lambda: self.tools.approve(self.owner, action['id'], {'fingerprint': action['fingerprint']}))
        self.clock -= 600; self.grant('model')
        self.denied('livelens_approval_changed', lambda: self.tools.approve(self.owner, action['id'], {'fingerprint': action['fingerprint']}))
        changed = LiveLensTools(self.store, dict(self.config, timeoutSeconds=.2), token_provider=lambda: self.token)
        self.denied('livelens_approval_changed', lambda: changed.approve(self.owner, action['id'], {'fingerprint': action['fingerprint']}))

    def test_revocation_during_capabilities_blocks_write_and_data_delivery(self):
        action = self.approved()
        FixtureClient.hook = lambda: self.grant('collection.control', revoke=True)
        self.denied('livelens_source_denied', lambda: self.tools.dispatch(self.owner, action['id'], {'fingerprint': action['fingerprint']}))
        self.assertEqual(FixtureClient.writes, 0)
        self.grant('collection.control')
        self.assertEqual(self.tools.view(self.owner, action['id'])['state'], 'uncertain')
        FixtureClient.hook = lambda: self.grant('read', revoke=True)
        self.denied('livelens_source_denied', lambda: self.tools.read(self.owner, {'operation': 'sessions', 'parameters': {'sourceId': 'fixture'}}))

    def test_pause_during_capabilities_blocks_actual_write(self):
        action = self.approved()
        FixtureClient.hook = lambda: self.store.set_paused(self.owner, True)
        self.assertEqual(self.tools.dispatch(self.owner, action['id'], {'fingerprint': action['fingerprint']})['state'], 'uncertain')
        self.assertEqual(FixtureClient.writes, 0)

    def test_timeout_after_acceptance_reconciles_stable_id_without_second_write(self):
        action = self.approved(); FixtureClient.timeout_after_write = True
        result = self.tools.dispatch(self.owner, action['id'], {'fingerprint': action['fingerprint']})
        self.assertEqual(result['state'], 'uncertain')
        self.denied('livelens_action_requires_approval_or_reconciliation', lambda: self.tools.dispatch(self.owner, action['id'], {'fingerprint': action['fingerprint']}))
        self.assertEqual(self.tools.reconcile(self.owner, action['id'], {})['state'], 'completed')
        self.assertEqual(FixtureClient.writes, 1)
        self.assertEqual(FixtureClient.jobs['job']['maxDurationSeconds'], 6)

    def test_reconciliation_refuses_job_parameter_conflict(self):
        action = self.approved(); FixtureClient.timeout_after_write = True
        self.tools.dispatch(self.owner, action['id'], {'fingerprint': action['fingerprint']})
        FixtureClient.jobs['job']['maxDurationSeconds'] = 3
        self.denied('livelens_reconciliation_conflict', lambda: self.tools.reconcile(self.owner, action['id'], {}))
        self.assertEqual(self.tools.view(self.owner, action['id'])['state'], 'uncertain')

    def test_rotated_private_runtime_token_is_used_on_next_read(self):
        self.grants(False)
        self.tools.read(self.owner, {'operation': 'sessions', 'parameters': {'sourceId': 'fixture'}})
        self.token = 'y' * 43
        self.tools.read(self.owner, {'operation': 'sessions', 'parameters': {'sourceId': 'fixture'}})
        self.assertEqual(FixtureClient.tokens, ['x' * 43, 'y' * 43])
        self.store.revoke('owner')
        self.denied('unauthorised', lambda: self.tools.discovery(self.owner))

    def test_source_forget_and_restore_replay_remove_action_records(self):
        self.approved()
        manifest = backup(self.store, self.owner, self.home / 'backups')
        outcome = forget_source(self.store, self.owner, 'specialist-livelens')
        self.assertEqual(outcome['livelens_action_records_deleted'], 1)
        restore(self.home / 'backups' / manifest['file'], self.store.path, now=self.clock)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM livelens_actions').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT revoked FROM credentials WHERE id=?', ('specialist-livelens',)).fetchone()[0], 1)
        self.denied('livelens_source_denied', lambda: self.tools.discovery(self.owner))

    def test_private_installation_reconnect_defaults_to_read_only_and_fresh_token(self):
        token = self.home / 'livelens.token'; token.write_text(self.token); token.chmod(0o600)
        config = self.home / 'connection.json'; config.write_text(canonical(dict(self.config, tokenFile=str(token)))); config.chmod(0o600)
        result = connect(self.store, self.owner, self.home, config, collection=True)
        self.assertTrue(result['collectionControlGranted'])
        self.assertTrue(installed(self.store, self.home).discovery(self.owner)['permissions']['collectionControl'])
        connect(self.store, self.owner, self.home, config)
        service = installed(self.store, self.home)
        self.assertFalse(service.discovery(self.owner)['permissions']['collectionControl'])
        token.write_text('z' * 43)
        service.read(self.owner, {'operation': 'sessions', 'parameters': {'sourceId': 'fixture'}})
        self.assertEqual(FixtureClient.tokens[-1], 'z' * 43)
        token.chmod(0o644)
        self.denied('private_livelens_file_required', lambda: load_configuration(config))
        token.chmod(0o600); target = self.home / 'unsafe.json'; target.symlink_to(config)
        self.denied('private_livelens_file_required', lambda: load_configuration(target))

    def test_unconfigured_discovery_is_truthful_and_controls_unavailable(self):
        self.assertEqual(route(None, '/desk/livelens', False, self.owner, {}),
                         {'configured': False, 'tools': [], 'automaticMonitoring': False})
        self.denied('livelens_not_configured', lambda: route(None, '/desk/livelens/read', True, self.owner, {}))

    def test_cli_selected_plain_markdown_vault_cannot_hold_config_token_or_input(self):
        from alfred.desk import init_demo
        from alfred.placement import PlacementFault
        home = self.home / 'cli'; init_demo(home)
        vault = self.home / 'plain-notes'; vault.mkdir()
        token = self.home / 'token'; token.write_text(self.token); token.chmod(0o600)
        config = self.home / 'config.json'
        value = dict(self.config, scope='demo-production', tokenFile=str(token))
        config.write_text(canonical(value)); config.chmod(0o600)
        in_vault = vault / 'config.json'; in_vault.write_text(canonical(value)); in_vault.chmod(0o600)
        command = [sys.executable, '-m', 'alfred.desk', 'livelens-connect', '--data-dir', str(home), '--vault', str(vault)]
        result = subprocess.run(command + ['--livelens-config', str(in_vault)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1); self.assertIn('data_directory_inside_vault', result.stdout)
        vault_token = vault / 'token'; vault_token.write_text(self.token); vault_token.chmod(0o600)
        config.write_text(canonical(dict(value, tokenFile=str(vault_token))))
        result = subprocess.run(command + ['--livelens-config', str(config)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1); self.assertIn('data_directory_inside_vault', result.stdout)
        config.write_text(canonical(value))
        result = subprocess.run(command + ['--livelens-config', str(config)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        body = vault / 'read.json'; body.write_text('{"operation":"sessions","parameters":{"sourceId":"fixture"}}'); body.chmod(0o600)
        result = subprocess.run([sys.executable, '-m', 'alfred.desk', 'livelens', '--data-dir', str(home),
                                 '--vault', str(vault), '--tool', 'read', '--tool-input', str(body)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1); self.assertIn('data_directory_inside_vault', result.stdout)

    def test_explicit_source_renewal_does_not_reactivate_revoked_or_forgotten_source(self):
        token = self.home / 'token'; token.write_text(self.token); token.chmod(0o600)
        config = self.home / 'connection.json'; config.write_text(canonical(dict(self.config, tokenFile=str(token)))); config.chmod(0o600)
        with self.store.transaction() as db:
            db.execute('UPDATE credentials SET expires=? WHERE id=?', (self.clock, 'specialist-livelens'))
        self.denied('livelens_source_renewal_required', lambda: connect(self.store, self.owner, self.home, config))
        connect(self.store, self.owner, self.home, config, renew_source=True)
        self.assertTrue(installed(self.store, self.home).discovery(self.owner)['permissions']['read'])
        self.store.revoke('specialist-livelens')
        self.denied('livelens_source_not_available', lambda: connect(self.store, self.owner, self.home, config, renew_source=True))

    def test_target_installation_home_is_checked_before_registration_mutation(self):
        from alfred.placement import PlacementFault
        vault = self.home / 'notes'; vault.mkdir()
        token = self.home / 'token'; token.write_text(self.token); token.chmod(0o600)
        config = self.home / 'connection.json'; config.write_text(canonical(dict(self.config, tokenFile=str(token)))); config.chmod(0o600)
        epoch = self.policy.view(self.owner)['epoch']
        with self.assertRaises(PlacementFault):
            connect(self.store, self.owner, vault, config, vaults=(vault,))
        self.assertEqual(self.policy.view(self.owner)['epoch'], epoch)
        self.assertFalse((vault / 'livelens-config.json').exists())


if __name__ == '__main__':
    unittest.main()
