"""M06 deterministic retrieval evaluation on the frozen synthetic set.

Asserts only properties that must hold whichever ranking scores better: no
permission leakage, answer keys outside request context, identical questions,
bounded metrics and a stable frozen set. No model or network is used, and no
claim is made that one ranking beats the other.
"""
import json
from pathlib import Path
import unittest
from tools import evaluate_retrieval as ev

ROOT = Path(__file__).resolve().parents[1]
RATE_FIELDS = ('mean_evidence_recall', 'micro_evidence_recall', 'any_hit_rate', 'full_support_rate',
               'first_item_supporting_rate')
SHARE_FIELDS = ('share_of_evidence_items', 'share_of_evidence_items_answerable', 'share_of_excerpt_characters')


def rotated_keys():
    """Deliberately wrong answer keys. Retrieval must not notice the change."""
    ids = [qid for qid, _, _ in ev.QUERIES]
    return {qid: {'label': 'rotated-canary:' + qid, 'support': ev.ANSWER_KEYS[ids[(i + 1) % len(ids)]]['support']}
            for i, qid in enumerate(ids)}


def evidence_paths(audit):
    return {r: [[e['path'] for e in p['evidence']] for p in packets] for r, packets in audit['packets'].items()}


class RetrievalEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.audit = ev.evaluate(repeats=1, warmup=0)
        cls.rotated_report, cls.rotated_audit = ev.evaluate(repeats=1, warmup=0, answer_keys=rotated_keys())
        cls.measured = [r for r, v in cls.report['rankings'].items() if v['status'] == 'measured']

    def test_frozen_set_meets_minimum_size_and_coverage(self):
        self.assertGreaterEqual(len(ev.CORPUS), 60)
        self.assertGreaterEqual(sum(bool(v['support']) for v in ev.ANSWER_KEYS.values()), 30)
        self.assertGreater(len(ev.RESTRICTED), 0)
        for category in ('heading_only', 'linked', 'near_duplicate', 'shared_name', 'unanswerable'):
            self.assertIn(category, self.report['queries']['categories'])
        corpus = self.report['corpus']
        self.assertTrue(corpus['indexed_matches_frozen'])
        self.assertEqual(corpus['link_issues'], 0)
        self.assertGreater(corpus['explicit_links_resolved'], 0)
        self.assertEqual({v['status'] for v in corpus['index_health'].values()}, {'ready'})
        labelled = {p for v in ev.ANSWER_KEYS.values() for p in v['support']}
        self.assertLessEqual(labelled, set(ev.CORPUS), 'every answer key names a granted note')

    def test_both_rankings_measured_when_fts5_is_available(self):
        expected = ['keywords', 'fts5'] if ev.fts5_available() else ['keywords']
        self.assertEqual(self.report['environment']['fts5_available'], ev.fts5_available())
        self.assertEqual(self.measured, expected)

    def test_zero_permission_leakage_for_every_measured_ranking(self):
        self.assertEqual(self.report['policy']['mode'], 'explicit_grants')
        self.assertEqual(self.report['policy']['granted_visible_sources'], [ev.MAIN_SOURCE])
        for ranking in self.measured:
            leakage = self.report['rankings'][ranking]['permission_leakage']
            self.assertEqual(leakage['ungranted_evidence_items'], 0, ranking)
            self.assertEqual(leakage['packets_with_ungranted_identifiers_or_text'], 0, ranking)
            self.assertEqual(leakage['packets_checked'], len(ev.QUERIES))
            self.assertEqual(leakage['ungranted_evidence_items_all_strict_calls'], 0, ranking)
            self.assertEqual(leakage['strict_calls_checked'], len(ev.QUERIES))
            for packet in self.audit['packets'][ranking]:
                self.assertNotIn(ev.RESTRICTED_CANARY, json.dumps(packet))
                self.assertFalse(set(e['path'] for e in packet['evidence']) & set(ev.RESTRICTED))
        self.assertNotIn(ev.RESTRICTED_CANARY, json.dumps(self.report))

    def test_leakage_check_is_not_vacuous(self):
        # Under the legacy whole-workspace policy the ungranted notes do match.
        for ranking in self.measured:
            control = self.report['rankings'][ranking]['legacy_scope_control']
            self.assertGreater(control['queries_with_ungranted_evidence'], 0, ranking)

    def test_answer_keys_never_enter_requests_or_packets(self):
        self.assertFalse(self.report['answer_keys_in_request_context'])
        self.assertFalse(self.report['model_inference'])
        questions = {q for _, _, q in ev.QUERIES}
        expected_calls = len(ev.QUERIES) * len(self.measured) * 2  # legacy control plus one measured pass
        self.assertEqual(len(self.audit['requests']), expected_calls)
        for request in self.audit['requests']:
            self.assertEqual(set(request), set(ev.REQUEST_FIELDS))
            self.assertIn(request['question'], questions)
            self.assertIn(request['ranking'], self.measured)
            self.assertEqual(request['purpose'], 'read')
        for audit in (self.audit, self.rotated_audit):
            text = json.dumps({'requests': audit['requests'], 'packets': audit['packets']})
            self.assertNotIn(ev.ANSWER_KEY_CANARY, text)
            self.assertNotIn('rotated-canary', text)
            for packets in audit['packets'].values():
                for packet in packets:
                    self.assertFalse({'support', 'answer_key', 'answer_keys', 'expected'} & set(packet))

    def test_request_context_check_detects_an_injected_key(self):
        clean = [{'question': ev.QUERIES[0][2], 'ranking': 'keywords', 'purpose': 'read'}]
        self.assertFalse(ev._keys_in_requests(clean, ev.ANSWER_KEYS))
        extra_field = [dict(clean[0], support=list(ev.ANSWER_KEYS['Q01']['support']))]
        self.assertTrue(ev._keys_in_requests(extra_field, ev.ANSWER_KEYS))
        leaked_path = [dict(clean[0], question='Look at ' + ev.ANSWER_KEYS['Q01']['support'][0])]
        self.assertTrue(ev._keys_in_requests(leaked_path, ev.ANSWER_KEYS))

    def test_retrieval_is_identical_whatever_the_answer_keys(self):
        # Rotated keys change scoring but cannot change what retrieve() returned.
        self.assertEqual(evidence_paths(self.audit), evidence_paths(self.rotated_audit))
        self.assertNotEqual(self.report['frozen_set']['answer_keys_sha256'],
                            self.rotated_report['frozen_set']['answer_keys_sha256'])
        self.assertNotEqual(self.report['rankings']['keywords']['recall'],
                            self.rotated_report['rankings']['keywords']['recall'])

    def test_identical_queries_for_every_ranking(self):
        queries = self.report['queries']
        self.assertTrue(queries['identical_across_rankings'])
        self.assertEqual(len(set(queries['sent_sha256'].values())), 1)
        self.assertEqual(set(queries['sent_sha256']), set(self.measured))
        self.assertEqual(queries['count'], len(ev.QUERIES))
        self.assertEqual(sorted(queries['request_fields']), sorted(ev.REQUEST_FIELDS))

    def test_report_fields_exist_and_metrics_are_bounded(self):
        for field in ('schema', 'job', 'environment', 'frozen_set', 'corpus', 'queries', 'policy', 'protocol',
                      'rankings', 'comparison', 'per_query', 'limitations'):
            self.assertIn(field, self.report)
        self.assertEqual(self.report['job'], 'M06')
        self.assertIn('python', self.report['environment'])
        self.assertIn('sqlite', self.report['environment'])
        self.assertIn('not a measurement of any named target hardware', self.report['environment']['latency_basis'])
        for ranking in self.measured:
            metrics = self.report['rankings'][ranking]
            for field in RATE_FIELDS:
                self.assertTrue(0 <= metrics['recall'][field] <= 1, (ranking, field))
            for field in SHARE_FIELDS:
                self.assertTrue(0 <= metrics['irrelevant_context'][field] <= 1, (ranking, field))
            for group in metrics['recall']['by_category'].values():
                self.assertTrue(0 <= group['mean_evidence_recall'] <= 1)
                self.assertTrue(0 <= group['any_hit_rate'] <= 1)
            routes = metrics['irrelevant_context']['by_route']
            for route in routes.values():
                self.assertTrue(0 <= route['irrelevant_items'] <= route['items'])
            self.assertEqual(sum(v['items'] for v in routes.values()),
                             sum(e['results'][ranking]['evidence_items'] for e in self.report['per_query']))
            self.assertTrue(0 <= metrics['volume']['mean_evidence_items'] <= 5)
            latency = metrics['latency_ms']
            self.assertEqual(latency['samples'], len(ev.QUERIES))
            self.assertTrue(0 < latency['min'] <= latency['p50'] <= latency['p95'] <= latency['max'])
            self.assertTrue(metrics['deterministic_across_repeats'])
        for entry in self.report['per_query']:
            for result in entry['results'].values():
                self.assertTrue(result['recall'] is None or 0 <= result['recall'] <= 1)
                self.assertLessEqual(result['evidence_items'], 5)

    def test_frozen_set_hash_is_stable_across_runs(self):
        first, second = self.report['frozen_set'], self.rotated_report['frozen_set']
        for field in ('corpus_sha256', 'queries_sha256'):
            self.assertEqual(first[field], second[field])
            self.assertRegex(first[field], r'^[0-9a-f]{64}$')
        self.assertEqual(first, ev.frozen_hashes())
        self.assertEqual(ev.frozen_hashes(), ev.frozen_hashes())
        self.assertTrue(self.rotated_report['corpus']['indexed_matches_frozen'])

    def test_committed_report_matches_the_frozen_set(self):
        committed = json.loads((ROOT / 'docs/evidence/memory-m06/report.json').read_text())
        self.assertEqual(committed['frozen_set'], ev.frozen_hashes())
        self.assertEqual(committed['schema'], ev.SCHEMA)


class Fts5UnavailableTests(unittest.TestCase):
    def test_missing_fts5_is_reported_not_hidden(self):
        report, audit = ev.evaluate(repeats=1, warmup=0, fts5=False)
        self.assertFalse(report['environment']['fts5_available'])
        self.assertEqual(report['rankings']['fts5']['status'], 'not_measured')
        self.assertEqual(report['rankings']['fts5']['reason'], 'fts5_unavailable_in_sqlite_build')
        self.assertIsNone(report['comparison'])
        self.assertEqual(report['rankings']['keywords']['status'], 'measured')
        self.assertEqual({r['ranking'] for r in audit['requests']}, {'keywords'})


if __name__ == '__main__':
    unittest.main()
