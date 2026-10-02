"""The INT-002 answer-support evaluation runs as part of the suite, so a regression shows up as a failed case."""
import unittest
from tools.evaluate_answers import CASES, evaluate


class AnswerEvaluationTests(unittest.TestCase):
    def test_every_published_case_passes_with_its_denominators(self):
        report = evaluate()
        self.assertEqual(report['failed_cases'], [])
        self.assertEqual(report['denominators']['cases'], len(CASES))
        self.assertEqual(report['mode'], 'sources_only_no_model')
        self.assertTrue(report['limitations'])


if __name__ == '__main__':
    unittest.main()
