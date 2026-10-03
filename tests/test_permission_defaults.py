"""Default-deny installation, legacy migration and cross-service privacy.

These use normal provisioning, not the explicit historical synthetic fixtures.
"""
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from alfred.console_api import projection, health
from alfred.desk import init_demo
from alfred.desk_http import DeskHTTPServer
from alfred.export import collect
from alfred.grounded import retrieve
from alfred.jobs import JobCoordinator
from alfred.knowledge import KnowledgeStore, KnowledgeSupervisor, MarkdownVault
from alfred.local import Fault
from alfred.policy import IdentityPolicy, permitted


class MigrationCLI(unittest.TestCase):
    def test_offline_migration_choices_and_repeat_preserve_no_model_or_write(self):
        for preserve in (False, True):
            with self.subTest(preserve=preserve), tempfile.TemporaryDirectory() as temporary:
                home = Path(temporary) / 'demo'; keys = init_demo(home, legacy_scope=True)
                command = [sys.executable, '-m', 'alfred.desk', 'migrate-grants', '--data-dir', str(home)]
                if preserve:
                    command.append('--preserve-legacy-reads')
                first = subprocess.run(command, capture_output=True, text=True, timeout=15)
                self.assertEqual(first.returncode, 0, first.stderr)
                receipt = json.loads(first.stdout); self.assertTrue(receipt['migrated'])
                self.assertFalse(receipt['model_egress_migrated']); self.assertFalse(receipt['writes_migrated'])
                store = KnowledgeStore(home / 'desk.sqlite')
                with store.transaction() as db:
                    p = store.authenticate(db, keys['owner'], {'owner'})
                    self.assertEqual(permitted(db, p, 'demo-source', store.now(), 'read'), preserve)
                    for capability in ('model', 'inbox.write'):
                        self.assertFalse(permitted(db, p, 'demo-source', store.now(), capability))
                again = subprocess.run(command, capture_output=True, text=True, timeout=15)
                self.assertEqual(again.returncode, 0, again.stderr); self.assertFalse(json.loads(again.stdout)['migrated'])
                self.assertNotIn(keys['owner'], first.stdout + first.stderr + again.stdout + again.stderr)

    def test_running_host_lock_blocks_migration(self):
        import fcntl
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / 'demo'; init_demo(home, legacy_scope=True)
            with (home / 'desk.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = subprocess.run([sys.executable, '-m', 'alfred.desk', 'migrate-grants', '--data-dir', str(home)],
                                        capture_output=True, text=True, timeout=15)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('stop_alfred_before_grant_migration', result.stdout + result.stderr)


class PermissionDefaults(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1000
        self.store = KnowledgeStore(self.root / 'db',clock=lambda:self.now)
        self.owner = self.store.provision('work','owner','owner')
        self.reader = self.store.provision('work','reader','reader')
        self.source = self.store.provision('work','private-source','source')
        self.vault = self.root / 'vault'; self.vault.mkdir()
        (self.vault / 'Secret.md').write_text('# Restrictedmarker\nRestrictedmarker plan has a private deadline.\n')
        MarkdownVault(self.store,self.source,self.vault,label='Restricted label').scan()
        self.policy = IdentityPolicy(self.store)

    def allowed(self,key,capability='read',source='private-source'):
        with self.store.transaction() as db:
            p=self.store.authenticate(db,key,{'owner','reader'})
            return permitted(db,p,source,self.now,capability)

    def grant(self,key,capability='read',revoke=False):
        return self.policy.grant(key,'private-source',capability,self.now+3600,
                                 self.policy.view(key)['epoch'],revoke=revoke)

    def test_new_sources_and_people_default_to_no_access(self):
        for key in (self.owner,self.reader):
            for cap in ('read','model','inbox.write','sync','connector.read'):
                self.assertFalse(self.allowed(key,cap))
            self.assertEqual(self.store.knowledge(key)['nodes'],[])
            self.assertEqual(retrieve(self.store,key,'Restrictedmarker')['evidence'],[])
        self.grant(self.owner)
        self.assertTrue(self.allowed(self.owner)); self.assertFalse(self.allowed(self.reader))
        newcomer=self.store.provision('work','new-owner','owner')
        self.assertFalse(self.allowed(newcomer))
        self.store=KnowledgeStore(self.root/'db',clock=lambda:self.now)
        self.assertTrue(self.allowed(self.owner)); self.assertFalse(self.allowed(newcomer))

    def test_read_does_not_grant_model_write_or_sync(self):
        self.grant(self.owner)
        self.assertTrue(retrieve(self.store,self.owner,'Restrictedmarker')['evidence'])
        self.assertEqual(retrieve(self.store,self.owner,'Restrictedmarker',purpose='model')['evidence'],[])
        for cap in ('model','inbox.write','sync','connector.read'):
            self.assertFalse(self.allowed(self.owner,cap))

    def test_revocation_filters_projection_health_jobs_export_and_questions(self):
        self.grant(self.owner)
        (self.root/'project').mkdir()
        sup=KnowledgeSupervisor(self.store,self.owner,self.source,self.root/'project',vault=self.vault)
        sup.cycle()
        server=DeskHTTPServer(self.store,sup,port=0)
        self.addCleanup(server.server_close)
        jobs=JobCoordinator(self.store); server.jobs=jobs
        self.assertEqual(projection(server,self.owner)['counts']['notes'],1)
        self.grant(self.owner,revoke=True)
        responses=(projection(server,self.owner),health(server,self.owner),collect(self.store,self.owner),
                   retrieve(self.store,self.owner,'plan deadline'),self.store.desk_state(self.owner))
        for response in responses:
            self.assertNotIn('Restrictedmarker',json.dumps(response))
            self.assertNotIn('Restricted label',json.dumps(response))
        self.assertEqual(health(server,self.owner)['vault']['notes'],0)
        self.assertEqual(jobs.jobs(self.owner),[])
        if server.routines is not None:
            self.assertEqual(server.routines.view(self.owner)['nominations'],[])

    def legacy(self):
        """Create an old-shaped store: no migration tables or strict policy row."""
        with self.store.connection() as db:
            db.execute('DROP TABLE source_legacy_access')
            db.execute('DROP TABLE source_policy_migrations')
            db.execute('DELETE FROM source_policy')
        self.store=KnowledgeStore(self.root/'db',clock=lambda:self.now)
        self.policy=IdentityPolicy(self.store)

    def test_legacy_snapshot_is_compatible_but_cannot_grow_on_reopen(self):
        self.legacy()
        self.assertTrue(self.allowed(self.owner)); self.assertTrue(self.allowed(self.reader,'model'))
        new=self.store.provision('work','new-reader','reader')
        new_source=self.store.provision('work','new-source','source')
        self.assertFalse(self.allowed(new))
        self.assertFalse(self.allowed(self.owner,source='new-source'))
        self.store=KnowledgeStore(self.root/'db',clock=lambda:self.now)
        self.assertTrue(self.allowed(self.owner)); self.assertFalse(self.allowed(new))
        self.assertFalse(self.allowed(self.owner,source='new-source'))

    def test_explicit_legacy_migration_preserves_only_recorded_read_grants(self):
        self.legacy()
        new=self.store.provision('work','later-owner','owner')
        receipt=self.policy.migrate_legacy(self.owner,0,preserve_reads=True)
        self.assertEqual(receipt['read_grants_added'],2)
        for key in (self.owner,self.reader):
            self.assertTrue(self.allowed(key)); self.assertFalse(self.allowed(key,'model'))
        self.assertFalse(self.allowed(new))
        second=self.policy.migrate_legacy(self.owner,self.policy.view(self.owner)['epoch'],preserve_reads=True)
        self.assertFalse(second['migrated'])

    def test_deny_migration_revocation_and_expiry_fail_closed(self):
        self.legacy()
        self.policy.migrate_legacy(self.owner,0,preserve_reads=False)
        self.assertFalse(self.allowed(self.owner))
        self.grant(self.owner)
        self.now+=3600
        self.assertFalse(self.allowed(self.owner))
        self.now=1000; self.grant(self.owner)
        self.store.revoke('owner')
        with self.store.connection() as db:
            self.assertFalse(permitted(db,{'id':'owner','scope':'work'},'private-source',self.now))

    def test_synthetic_legacy_escape_is_rejected_for_non_synthetic_workspaces(self):
        with self.assertRaises(Fault):
            self.store.provision('real','real-owner','owner',simulation=False,legacy_scope=True)

    def test_demo_is_strict_with_explicit_selected_source_grants(self):
        keys=init_demo(self.root/'demo')
        store=KnowledgeStore(self.root/'demo/desk.sqlite')
        policy=IdentityPolicy(store)
        self.assertEqual(policy.view(keys['owner'])['mode'],'explicit_grants')
        self.assertEqual({g['capability'] for g in policy.view(keys['owner'])['grants']},{'read','model'})
        self.assertEqual({g['capability'] for g in policy.view(keys['reader'])['grants']},{'read'})
        store.provision('demo-production','added-source','source')
        self.assertFalse(next(s for s in policy.view(keys['owner'])['sources'] if s['source']=='added-source')['permitted']['read'])
