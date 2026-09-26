import unittest
from alfred.evidence_review import assess_interpretation

class EvidenceReviewTests(unittest.TestCase):
    def claim(self,statement='Delivery is at 14:25.',quote='Delivery is at 14:25.',**changes):
        return {'text':statement,'basis':'model_interpretation_not_verified_fact',
                'citations':[{'source_id':'S1','start_line':2,'end_line':2,'quote':quote,**changes}]}
    def review(self,claims=None,q='When is delivery?'):
        return assess_interpretation([self.claim()] if claims is None else claims,{'question':q})
    def test_literal_number_passes(self):self.assertEqual(len(self.review()[0]),1)
    def test_unquoted_number_withheld(self):self.assertEqual(self.review([self.claim('Delivery at 19:50.')])[0],[])
    def test_no_false_entailment_claim(self):self.assertFalse(self.review()[1]['semantic_entailment_verified'])
    def test_does_not_claim_truth(self):self.assertFalse(self.review()[1]['real_world_truth_verified'])
    def test_missing_price_withholds_unrelated_time(self):self.assertEqual(self.review(q='What is the delivery price?')[0],[])
    def test_how_much_withholds_without_money(self):self.assertEqual(self.review(q='How much is delivery?')[0],[])
    def test_money_symbol_in_cited_text(self):self.assertEqual(len(self.review([self.claim('The fee is £25.','The fee is £25.')],q='What is the fee?')[0]),1)
    def test_currency_word(self):self.assertEqual(len(self.review([self.claim('25 pounds.','Delivery costs 25 pounds.')],q='How much does it cost?')[0]),1)
    def test_free_is_money_evidence(self):self.assertEqual(len(self.review([self.claim('Delivery is free.','Delivery is free.')],q='What is delivery cost?')[0]),1)
    def test_unrelated_money_not_semantic_proof(self):
        claims,report=self.review([self.claim('The answer is unknown.','Catering costs £25.')],q='What is delivery cost?')
        self.assertEqual(len(claims),1);self.assertFalse(report['semantic_entailment_verified'])
    def test_duplicate_citations_removed(self):
        c=self.claim();c['citations']*=2;claims,report=self.review([c]);self.assertEqual(len(claims[0]['citations']),1);self.assertEqual(report['issues'][0]['code'],'duplicate_citations_removed')
    def test_broad_citation_warns(self):
        claims,report=self.review([self.claim(end_line=7)]);self.assertEqual(len(claims),1);self.assertFalse(report['issues'][0]['blocking'])
    def test_abstention_kept(self):self.assertEqual(self.review([],q='What is the fee?')[0],[])
    def test_current_question_controls_type(self):
        claims,report=assess_interpretation([self.claim()],{'question':'When is delivery?','conversation_questions':['What is the price?']});self.assertEqual(len(claims),1)
    def test_number_in_different_source_not_sufficient(self):
        c=self.claim('Delivery at 19:50.');claims,_=assess_interpretation([c],{'question':'When?','evidence':[{'excerpt':'Other event at 19:50.'}]});self.assertEqual(claims,[])
    def test_one_bad_claim_withholds_whole_interpretation(self):self.assertEqual(self.review([self.claim(),self.claim('It costs 99.')])[0],[])
    def test_unsupported_value_not_in_report(self):
        _,report=self.review([self.claim('Secret guessed number 123456789.')]);self.assertNotIn('123456789',str(report))
    def test_two_supplied_numbers_allowed(self):self.assertEqual(len(self.review([self.claim('Times differ: 14:25 and 16:30.','The two reports say 14:25 and 16:30.')])[0]),1)
if __name__=='__main__':unittest.main()
