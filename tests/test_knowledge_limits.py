import tempfile
from pathlib import Path
import unittest
from alfred.knowledge import KnowledgeStore,parse_note
from alfred.knowledge_context import build_packet
from alfred.local import Fault


class KnowledgeLimitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=KnowledgeStore(Path(self.temp.name)/'db.sqlite')
        self.owner=self.store.provision('work','owner','owner')
        self.source=self.store.provision('work','source','source');self.second=self.store.provision('work','second','source')
    def tearDown(self):self.temp.cleanup()
    def notes(self,count):
        values=[]
        for i in range(count):
            note=parse_note(f'{i}.md',b'# Note\n[[Missing]]');note['modified']=0;values.append(note)
        return values
    def test_combined_source_view_is_bounded(self):
        self.store.replace_notes(self.source,'A',self.notes(200),[]);self.store.replace_notes(self.second,'B',self.notes(100),[])
        with self.assertRaises(Fault) as e:self.store.knowledge(self.owner)
        self.assertEqual(e.exception.code,'knowledge_view_capacity')
    def test_oversize_source_rejected_atomically(self):
        self.store.replace_notes(self.source,'A',self.notes(1),[])
        with self.assertRaises(Fault):self.store.replace_notes(self.source,'A',self.notes(257),[])
        self.assertEqual(len(self.store.knowledge(self.owner)['nodes']),1)
    def test_rebuild_reuses_identity_and_revision(self):
        notes=self.notes(3);self.store.replace_notes(self.source,'A',notes,[]);before=self.store.knowledge(self.owner)['nodes'];self.store.replace_notes(self.source,'A',notes,[])
        self.assertEqual([(n['id'],n['revision']) for n in before],[(n['id'],n['revision']) for n in self.store.knowledge(self.owner)['nodes']])
    def test_packets_reject_blank_query(self):
        with self.assertRaises(Fault):build_packet(self.store,self.owner,' ')
    def test_source_unavailability_removes_body_access(self):
        self.store.replace_notes(self.source,'A',self.notes(1),[]);identity=self.store.knowledge(self.owner)['nodes'][0]['id'];self.store.knowledge_unavailable(self.source,'source_lost')
        with self.assertRaises(Fault):self.store.knowledge_note(self.owner,identity)
    def test_graph_has_no_cross_source_guessing(self):
        a=parse_note('a.md',b'# A\n[[Target]]');a['modified']=0;b=parse_note('Target.md',b'# Target');b['modified']=0
        self.store.replace_notes(self.source,'A',[a],[]);self.store.replace_notes(self.second,'B',[b],[])
        data=self.store.knowledge(self.owner);self.assertEqual(data['links'],[]);self.assertEqual(data['issues'][0]['status'],'missing')


if __name__=='__main__':unittest.main()
