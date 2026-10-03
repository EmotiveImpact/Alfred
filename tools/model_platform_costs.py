"""Workload-based planning arithmetic. No provider selection, quote or spending.

Only the R2 Standard prices below were rechecked at a current primary source.
Every other rate is an explicit illustrative assumption, replaceable in input.
"""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path

R2_SOURCE = 'https://raw.githubusercontent.com/cloudflare/cloudflare-docs/36706c5fd9c704ca10e440bab9ed0d58521577b9/src/content/docs/r2/pricing.mdx'
RATES = {'input_mtokens_usd': 1.0, 'output_mtokens_usd': 4.0, 'cpu_hour_usd': .06,
         'gpu_hour_usd': 1.5, 'core_month_usd': 48.0, 'monitoring_month_usd': 20.0,
         'other_egress_gb_usd': .09, 'staff_hour_usd': 45.0,
         'r2_gb_month_usd': .015, 'r2_class_a_million_usd': 4.5, 'r2_class_b_million_usd': .36}
WORKLOAD = {'active_users': 10, 'sessions_per_user': 15, 'model_calls_per_session': 3,
            'input_tokens_per_call': 3000, 'output_tokens_per_call': 600,
            'jobs_per_session': 2, 'cpu_seconds_per_job': 60, 'gpu_seconds_per_job': 0,
            'idle_cpu_hours': 24, 'idle_gpu_hours': 0, 'core_instances': 1,
            'stored_gb_per_user': 2, 'backup_copies': 2, 'additional_file_replicas': 0,
            'class_a_requests_per_session': 20, 'class_b_requests_per_session': 100,
            'other_egress_gb_per_user': .1, 'staff_hours': 15,
            'native_signing_annual_usd': 0, 'r2_free_tier': False,
            'credit_usd': 0, 'negotiated_discount': 0, 'tax_fraction': 0,
            'usd_to_reporting_currency': 1.0, 'reporting_currency': 'USD'}


def estimate(workload, rates=RATES):
    """Monthly steady-state: backups are full retained copies, not a change rate."""
    if set(workload) != set(WORKLOAD) or set(rates) != set(RATES):
        raise ValueError('unexpected or missing input fields')
    for key, value in (workload | rates).items():
        if key in ('reporting_currency', 'r2_free_tier'):
            continue
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('rates and workloads must be finite and nonnegative')
    if type(workload['r2_free_tier']) is not bool or not isinstance(workload['reporting_currency'], str):
        raise ValueError('invalid billing options')
    if workload['negotiated_discount'] > 1 or workload['tax_fraction'] > 1 or workload['usd_to_reporting_currency'] <= 0:
        raise ValueError('invalid discount, tax or currency factor')
    w = workload; sessions = w['active_users'] * w['sessions_per_user']; calls = sessions * w['model_calls_per_session']
    jobs = sessions * w['jobs_per_session']
    stored = w['active_users'] * w['stored_gb_per_user']
    free_storage, free_a, free_b = (10, 1_000_000, 10_000_000) if w['r2_free_tier'] else (0, 0, 0)
    billed_storage = math.ceil(max(0, stored * (1 + w['backup_copies'] + w['additional_file_replicas']) - free_storage))
    billed_a = math.ceil(max(0, sessions * w['class_a_requests_per_session'] - free_a) / 1_000_000)
    billed_b = math.ceil(max(0, sessions * w['class_b_requests_per_session'] - free_b) / 1_000_000)
    lines = {
        'model_input': calls * w['input_tokens_per_call'] / 1_000_000 * rates['input_mtokens_usd'],
        'model_output': calls * w['output_tokens_per_call'] / 1_000_000 * rates['output_mtokens_usd'],
        'worker_cpu_active_and_idle': (jobs * w['cpu_seconds_per_job'] / 3600 + w['idle_cpu_hours']) * rates['cpu_hour_usd'],
        'worker_gpu_active_and_idle': (jobs * w['gpu_seconds_per_job'] / 3600 + w['idle_gpu_hours']) * rates['gpu_hour_usd'],
        'core_reserved': w['core_instances'] * rates['core_month_usd'],
        'storage_with_backups_and_replicas': billed_storage * rates['r2_gb_month_usd'],
        'rounded_class_a_requests': billed_a * rates['r2_class_a_million_usd'],
        'rounded_class_b_requests': billed_b * rates['r2_class_b_million_usd'],
        'other_service_egress': w['active_users'] * w['other_egress_gb_per_user'] * rates['other_egress_gb_usd'],
        'monitoring': rates['monitoring_month_usd'], 'native_signing': w['native_signing_annual_usd'] / 12}
    vendor_list = sum(lines.values()); vendor_discounted = vendor_list * (1 - w['negotiated_discount'])
    credited = min(w['credit_usd'], vendor_discounted); staff = w['staff_hours'] * rates['staff_hour_usd']
    total = (vendor_discounted - credited) * (1 + w['tax_fraction']) + staff
    post_credit = vendor_discounted * (1 + w['tax_fraction']) + staff
    return {'workload': w, 'monthly_sessions': sessions, 'monthly_model_calls': calls,
            'monthly_input_mtokens': calls * w['input_tokens_per_call'] / 1_000_000,
            'monthly_output_mtokens': calls * w['output_tokens_per_call'] / 1_000_000,
            'billable_r2': {'gb_month': billed_storage, 'class_a_millions': billed_a, 'class_b_millions': billed_b},
            'vendor_line_items_usd': {k: round(v, 4) for k, v in lines.items()},
            'vendor_list_usd': round(vendor_list, 2), 'vendor_discounted_usd': round(vendor_discounted, 2),
            'credit_applied_usd': round(credited, 2), 'staff_usd': round(staff, 2),
            'monthly_total_usd': round(total, 2), 'post_credit_monthly_total_usd': round(post_credit, 2),
            'monthly_reporting_currency': round(total * w['usd_to_reporting_currency'], 2)}


def report():
    scenarios = {'synthetic_pilot': WORKLOAD,
                 '100_active': WORKLOAD | {'active_users': 100, 'staff_hours': 40, 'core_instances': 2},
                 '1000_active': WORKLOAD | {'active_users': 1000, 'staff_hours': 160, 'core_instances': 2}}
    base = scenarios['100_active']
    sensitivities = {'double_sessions': base | {'sessions_per_user': base['sessions_per_user'] * 2},
                     'four_times_output': base | {'output_tokens_per_call': base['output_tokens_per_call'] * 4},
                     'gpu_idle_720h': base | {'idle_gpu_hours': 720},
                     'ten_full_backups': base | {'backup_copies': 10},
                     'illustrative_credit_1000': base | {'credit_usd': 1000},
                     'illustrative_discount_20pct': base | {'negotiated_discount': .2},
                     'illustrative_gbp_tax': base | {'tax_fraction': .2, 'usd_to_reporting_currency': .75, 'reporting_currency': 'GBP'}}
    return {'checked_on': '2026-10-03', 'provider_selected': False, 'rates': RATES,
            'rate_evidence': {'r2_standard': {'status': 'verified_list_price', 'source': R2_SOURCE,
                            'free_tier_applied_in_base': False, 'egress_from_r2_itself_usd': 0},
                             'other_rates': 'illustrative assumptions, not vendor list prices or quotes',
                             'credits_discounts_currency_tax': 'scenario assumptions, no eligibility or live FX established'},
            'limits': ['Not a quote, capacity benchmark, approved budget or product valuation.',
                       'All backups modelled in one R2 account; separate providers and accounts need separate billing.',
                       'CPU and GPU idle reservations are additional to active hours; do not double-charge reserved active capacity.',
                       'Credits assumed fully eligible only in labelled sensitivity; tax on vendor costs only.',
                       'Staff cost is explicit; commercial rent, legal, compliance, support escalation and margins are unpriced.'],
            'scenarios': {k: estimate(deepcopy(w)) for k, w in scenarios.items()},
            'sensitivity_100_active': {k: estimate(deepcopy(w)) for k, w in sensitivities.items()}}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True)
    parser.add_argument('--input', help='JSON with complete workload and rates overrides; no network')
    args = parser.parse_args()
    if args.input:
        values = json.loads(Path(args.input).read_text()); value = estimate(values['workload'], values['rates'])
    else:
        value = report()
    Path(args.output).write_text(json.dumps(value, indent=2) + '\n')
    print('Wrote planning arithmetic to', args.output)


if __name__ == '__main__':
    main()
