"""Actual process kill/restart against the existing job authority; no remote node."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import unittest
from alfred.jobs import JobCoordinator,JobWorker,LocalSubprocessBackend
from alfred.knowledge import KnowledgeStore,MarkdownVault
from alfred.policy import IdentityPolicy

CHILD = '''
import json,sys,time
from alfred.jobs import JobCoordinator
from alfred.knowledge import KnowledgeStore
p=json.loads(sys.stdin.readline())
store=KnowledgeStore(p['db'],clock=lambda:1000)
jobs=JobCoordinator(store)
job=jobs.lease(p['key'],'test-worker',ttl=1)
assert job
print('leased',flush=True)
time.sleep(60)
'''


class PilotRecovery(unittest.TestCase):
    def test_killed_coordinator_requeues_only_side_effect_free_work(self):
        for safe in (True,False):
            with self.subTest(side_effect_free=safe),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);vault=root/'vault';vault.mkdir()
                (vault/'Plan.md').write_text('# Plan\nSynthetic recovery count.\n')
                store=KnowledgeStore(root/'db',clock=lambda:1000)
                owner=store.provision('work','owner','owner')
                source=store.provision('work','source','source')
                policy=IdentityPolicy(store);policy.grant(owner,'source','read',5000,0)
                MarkdownVault(store,source,vault).scan()
                note=store.knowledge(owner)['nodes'][0]['id']
                jobs=JobCoordinator(store);jobs.enrol_worker(owner,'test-worker','Synthetic worker',['word_count'])
                job=jobs.submit(owner,{'idempotency_key':'recovery','kind':'word_count','parameters':{},
                                       'inputs':[{'note':note}],'side_effect_free':safe})
                process=subprocess.Popen([sys.executable,'-c',CHILD],stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                                         cwd=Path(__file__).resolve().parents[1])
                try:
                    process.stdin.write(json.dumps({'db':str(store.path),'key':owner})+'\n');process.stdin.flush()
                    self.assertTrue(select.select([process.stdout],[],[],5)[0],'child did not reach its lease boundary')
                    self.assertEqual(process.stdout.readline().strip(),'leased')
                    process.kill();self.assertEqual(process.wait(5),-9)
                    restarted=KnowledgeStore(root/'db',clock=lambda:1002)
                    coordinator=JobCoordinator(restarted)
                    recovery=coordinator.recover(owner)
                    if safe:
                        self.assertEqual(recovery['requeued'],[job['id']])
                        JobWorker(coordinator,LocalSubprocessBackend(),owner,'test-worker').run_once()
                        self.assertEqual(coordinator.view(owner,job['id'])['state'],'succeeded')
                        self.assertEqual(len(coordinator.jobs(owner)),1)
                        self.assertEqual(coordinator.view(owner,job['id'])['attempt'],2)
                    else:
                        self.assertEqual(recovery['effect_unknown'],[job['id']])
                        self.assertIsNone(coordinator.lease(owner,'test-worker'))
                        self.assertEqual(coordinator.view(owner,job['id'])['attempt'],1)
                finally:
                    if process.poll() is None:process.kill();process.wait(5)
                    for stream in (process.stdin,process.stdout,process.stderr):stream.close()
