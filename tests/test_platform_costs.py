"""Billing rounding, credit cliffs and workload dimensions affect the decision."""
import unittest
from tools.model_platform_costs import estimate, WORKLOAD


class CostTests(unittest.TestCase):
    def test_rounding_and_optional_free_tier(self):
        w = WORKLOAD | {'active_users': 1, 'sessions_per_user': 1, 'stored_gb_per_user': .5,
                        'class_a_requests_per_session': 1_000_001, 'class_b_requests_per_session': 1}
        self.assertEqual(estimate(w)['billable_r2'], {'gb_month': 2, 'class_a_millions': 2, 'class_b_millions': 1})
        self.assertEqual(estimate(w | {'r2_free_tier': True})['billable_r2'], {'gb_month': 0, 'class_a_millions': 1, 'class_b_millions': 0})

    def test_credit_cannot_subsidise_staff_and_post_credit_cost_is_visible(self):
        base = estimate(WORKLOAD); credited = estimate(WORKLOAD | {'credit_usd': 1_000_000})
        self.assertEqual(credited['monthly_total_usd'], base['staff_usd'])
        self.assertEqual(credited['post_credit_monthly_total_usd'], base['monthly_total_usd'])

    def test_tokens_idle_capacity_and_backups_are_independent_of_headcount(self):
        base = estimate(WORKLOAD)
        changed = estimate(WORKLOAD | {'output_tokens_per_call': 2400, 'idle_gpu_hours': 720, 'backup_copies': 10})
        self.assertEqual(changed['monthly_sessions'], base['monthly_sessions'])
        self.assertEqual(changed['vendor_line_items_usd']['model_output'], base['vendor_line_items_usd']['model_output'] * 4)
        self.assertEqual(changed['vendor_line_items_usd']['worker_gpu_active_and_idle'], 1080)
        self.assertGreater(changed['billable_r2']['gb_month'], base['billable_r2']['gb_month'])

    def test_invalid_rates_are_refused(self):
        for change in ({'idle_gpu_hours': -1}, {'negotiated_discount': 1.01}, {'usd_to_reporting_currency': 0}, {'active_users': float('nan')}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                estimate(WORKLOAD | change)
