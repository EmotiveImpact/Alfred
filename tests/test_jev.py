import copy
import unittest
from alfred.jev import MODEL, parse_advice, request_for
from alfred.local import Fault


class JevTests(unittest.TestCase):
    def setUp(self):
        self.response={'model':MODEL,'answers':{'attention':{'type':'choice','choice':'briefing',
            'probabilities':{'briefing':0.8,'review':0.1,'ignore':0.1},'confidence':0.7}}}
    def test_default_egress_denied(self):
        with self.assertRaises(Fault): request_for(objective='Test',summary='Synthetic data')
    def test_request_is_version_pinned(self):
        r=request_for(objective='Test',summary='Synthetic data',allow_cloud=True)
        self.assertEqual(r['model'],MODEL)
    def test_only_minimised_state(self):
        r=request_for(objective='Test',summary='Synthetic data',allow_cloud=True)
        self.assertEqual(set(r['state']),{'objective','event_summary'})
    def test_advice_never_grants_permission(self):
        r=parse_advice(self.response)
        self.assertFalse(r['permission_granted']); self.assertEqual(r['actions_executed'],0)
    def test_confidence_not_relabelled_as_truth(self):
        self.assertIn('provider_confidence',parse_advice(self.response))
        self.assertNotIn('truth_probability',parse_advice(self.response))
    def test_wrong_model_rejected(self):
        self.response['model']='jev-latest'
        with self.assertRaises(Fault): parse_advice(self.response)
    def test_unknown_choice_rejected(self):
        self.response['answers']['attention']['choice']='execute'
        with self.assertRaises(Fault): parse_advice(self.response)
    def test_non_string_choice_rejected(self):
        self.response['answers']['attention']['choice']=[]
        with self.assertRaises(Fault): parse_advice(self.response)
    def test_inconsistent_choice_rejected(self):
        self.response['answers']['attention']['choice']='ignore'
        with self.assertRaises(Fault): parse_advice(self.response)
    def test_invalid_probabilities_rejected(self):
        for bad in (float('nan'),float('inf'),True,-1,2):
            response=copy.deepcopy(self.response); response['answers']['attention']['probabilities']['review']=bad
            with self.subTest(bad=bad),self.assertRaises(Fault): parse_advice(response)
    def test_invalid_total_rejected(self):
        self.response['answers']['attention']['probabilities']['review']=0.5
        with self.assertRaises(Fault): parse_advice(self.response)
    def test_unexpected_output_fields_rejected(self):
        self.response['answers']['attention']['permission']=True
        with self.assertRaises(Fault): parse_advice(self.response)
    def test_invalid_confidence_rejected(self):
        self.response['answers']['attention']['confidence']=float('nan')
        with self.assertRaises(Fault): parse_advice(self.response)
    def test_missing_answer_rejected(self):
        self.response['answers']={}
        with self.assertRaises(Fault): parse_advice(self.response)


if __name__=='__main__': unittest.main()
