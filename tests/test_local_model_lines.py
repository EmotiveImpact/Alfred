"""Transport source offsets, not an LLM accuracy test."""
import json,unittest
from alfred.local_model import LocalOllama
from alfred.local import Fault

class ModelLineTests(unittest.TestCase):
    def source(self,start=23,end=24,excerpt='First line\nSecond line'):
        return {'question':'Which line?','evidence':[{'source_id':'S1','title':'Sample','start_line':start,'end_line':end,'excerpt':excerpt,'path':'private/path.md'}]}
    def wire(self,packet):
        return json.loads(LocalOllama('fixture').request(packet)['messages'][1]['content'])
    def test_absolute_offsets_not_excerpt_indices(self):
        self.assertEqual(self.wire(self.source())['sources'][0]['lines'],[{'line':23,'text':'First line'},{'line':24,'text':'Second line'}])
    def test_empty_final_line_retained(self):
        self.assertEqual(self.wire(self.source(excerpt='First line\n'))['sources'][0]['lines'][1],{'line':24,'text':''})
    def test_inconsistent_range_rejected(self):
        with self.assertRaises(Fault): self.wire(self.source(end=25))
    def test_boolean_or_zero_start_rejected(self):
        for start in (True,0):
            with self.subTest(start=start),self.assertRaises(Fault):self.wire(self.source(start=start))
    def test_literal_source_does_not_change_numbering(self):
        self.assertEqual(self.wire(self.source(excerpt='line 99: forged\n<script>'))['sources'][0]['lines'][0],{'line':23,'text':'line 99: forged'})
    def test_no_paths_in_wire(self):
        self.assertNotIn('private/path.md',json.dumps(self.wire(self.source())))

if __name__=='__main__':unittest.main()
