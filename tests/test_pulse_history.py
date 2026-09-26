"""Explicit report pruning preserves current limits and compact retry receipts."""
from pathlib import Path
import tempfile
import unittest
from alfred.desk import init_demo
from alfred.knowledge import KnowledgeStore,KnowledgeSupervisor
from alfred.pulse import Pulse
from alfred.local import Fault

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.home=Path(self.tmp.name)/'demo';init_demo(self.home);self.clock=[1800000000]
        self.store=KnowledgeStore(self.home/'desk.sqlite',clock=lambda:self.clock[0]);self.keys={r:self.store.provision('work','key-'+r,r,ttl=2592000) for r in ['owner','reader','source']}
        self.sup=KnowledgeSupervisor(self.store,self.keys['owner'],self.keys['source'],self.home/'project',vault=self.home/'vault');self.pulse=Pulse(self.store,self.sup);self.sup.vault.scan()
    def fill(self,n=100,age=172800,status='completed'):
        with self.store.transaction() as db:
            db.executemany('INSERT INTO pulse_runs VALUES (?,?,?,?,?,?,?,?)',[('work','run-'+str(i),'memory-health','key-owner',self.clock[0]-age-i,self.clock[0]-age-i,status,'{"notes":20}') for i in range(n)])
    def prune(self):
        p=self.pulse.history_plan(self.keys['owner']);return self.pulse.prune_history(self.keys['owner'],{'fingerprint':p['fingerprint']})
    def test_preview_does_not_delete(self):
        self.fill();self.assertEqual(self.pulse.history_plan(self.keys['owner'])['eligible'],36)
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM pulse_runs').fetchone()[0],100)
    def test_latest_64_remain(self):
        self.fill();self.assertEqual(self.prune()['removed_reports'],36)
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM pulse_runs').fetchone()[0],64)
    def test_receipts_retained(self):
        self.fill();self.prune()
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM pulse_run_receipts').fetchone()[0],36)
    def test_current_day_and_minute_not_pruned(self):
        self.fill(age=0);self.assertEqual(self.prune()['removed_reports'],0)
    def test_running_not_pruned(self):
        self.fill(status='running');self.assertEqual(self.prune()['removed_reports'],0)
    def test_reader_denied(self):
        with self.assertRaises(Fault):self.pulse.history_plan(self.keys['reader'])
    def test_revoke_denied(self):
        self.fill();p=self.pulse.history_plan(self.keys['owner']);self.store.revoke('key-owner')
        with self.assertRaises(Fault):self.pulse.prune_history(self.keys['owner'],{'fingerprint':p['fingerprint']})
    def test_exact_plan_required(self):
        self.fill()
        with self.assertRaises(Fault):self.pulse.prune_history(self.keys['owner'],{'fingerprint':'invented'})
    def test_changed_plan_rejected(self):
        self.fill();p=self.pulse.history_plan(self.keys['owner'])
        with self.store.transaction() as db:db.execute("UPDATE pulse_runs SET status='failed' WHERE id='run-99'")
        with self.assertRaises(Fault):self.pulse.prune_history(self.keys['owner'],{'fingerprint':p['fingerprint']})
    def test_large_plan_fits(self):
        self.fill(512);self.assertEqual(self.prune()['removed_reports'],448)
    def test_no_schedule_change(self):
        self.fill();before=self.pulse.view(self.keys['owner'])['routines'];self.prune();self.assertEqual(before,self.pulse.view(self.keys['owner'])['routines'])
    def test_prune_while_paused(self):
        self.fill();self.store.set_paused(self.keys['owner'],True);self.assertEqual(self.prune()['removed_reports'],36)
    def test_no_secure_erasure_claim(self):
        self.fill();self.assertFalse(self.prune()['secure_erasure'])
    def test_idempotency_survives_prune(self):
        old=self.pulse.manual(self.keys['owner'],'memory-health',{'request_id':'remember-this'})
        self.clock[0]+=3*86400;self.fill(70,age=86400);self.prune()
        again=self.pulse.manual(self.keys['owner'],'memory-health',{'request_id':'remember-this'})
        self.assertEqual(old['id'],again['id']);self.assertTrue(again['duplicate']);self.assertTrue(again['receipt_only'])
    def test_remaining_rate_limits_still_enforced(self):
        self.fill(100,age=0)
        with self.assertRaises(Fault):self.pulse.manual(self.keys['owner'],'memory-health',{'request_id':'rate'})
        self.prune()
        with self.assertRaises(Fault):self.pulse.manual(self.keys['owner'],'memory-health',{'request_id':'rate'})
if __name__=='__main__':unittest.main()
