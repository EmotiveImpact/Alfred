"""Validate the requirement-to-delivery and source-coverage registers.

Checks completeness and internal consistency only: every PRD requirement is
registered once, states use the declared vocabulary, claimed implementations cite
evidence that exists, and origins trace to recorded sources. It cannot judge
whether a capability really works; the cited tests and receipts do that.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLAIMED = {'implemented_on_branch', 'accepted_implementation'}


def validate(register: dict, coverage: dict, prd_ids: set[str], backlog: dict, exists=lambda p: True) -> list[str]:
    errors: list[str] = []
    vocabulary = register.get('vocabulary', {})
    entries = register.get('requirements', [])
    ids = [e.get('id') for e in entries]
    if len(ids) != len(set(ids)):
        errors.append('Duplicate register IDs')
    if set(ids) != prd_ids:
        missing, extra = sorted(prd_ids - set(ids)), sorted(set(ids) - prd_ids)
        errors.append(f'Register and PRD differ: missing {missing}, unknown {extra}')
    sources = {s['id']: s for s in coverage.get('sources', [])}
    jobs = {j['id']: j for j in backlog.get('jobs', [])}
    graph = {}
    for e in entries:
        rid = e.get('id')
        for field in ('decision', 'implementation', 'integration', 'merge', 'deployment'):
            if e.get(field) not in vocabulary.get(field, []):
                errors.append(f'{rid}: invalid {field} {e.get(field)!r}')
        if e.get('implementation') in CLAIMED and not e.get('acceptance_evidence'):
            errors.append(f'{rid}: implementation claim without acceptance evidence')
        for path in e.get('acceptance_evidence', []):
            if not exists(path):
                errors.append(f'{rid}: missing evidence {path}')
        if e.get('implementation') == 'not_started' and e.get('integration') != 'not_applicable':
            errors.append(f'{rid}: unstarted work cannot be integrated')
        if e.get('implementation') != 'not_started' and e.get('integration') == 'not_applicable':
            errors.append(f'{rid}: started work needs an integration state')
        if e.get('merge') == 'merged_to_main' and e.get('implementation') == 'not_started':
            errors.append(f'{rid}: nothing to merge')
        if e.get('deployment') != 'not_deployed':
            errors.append(f'{rid}: deployment claims are not supported by this register')
        if not e.get('origin') or any(o not in sources for o in e['origin']):
            errors.append(f'{rid}: origin must cite recorded sources')
        for job in e.get('memory_jobs', []):
            if job not in jobs or rid not in jobs[job].get('requirements', []):
                errors.append(f'{rid}: memory job {job} does not list this requirement')
        graph[rid] = e.get('depends_on', [])
        if any(d not in ids or d == rid for d in graph[rid]):
            errors.append(f'{rid}: unknown or self dependency')
    for job in jobs.values():
        for rid in job.get('requirements', []):
            entry = next((e for e in entries if e.get('id') == rid), None)
            if entry is not None and job['id'] not in entry.get('memory_jobs', []):
                errors.append(f'{rid}: register omits memory job {job["id"]}')
    for source in coverage.get('sources', []):
        if any(d not in ids for d in source.get('destinations', [])):
            errors.append(f'{source["id"]}: destination is not a registered requirement')
    state, cyclic = {}, False
    def visit(node):
        nonlocal cyclic
        if state.get(node) == 1:
            cyclic = True; return
        if state.get(node) == 2 or node not in graph:
            return
        state[node] = 1
        for child in graph[node]:
            visit(child)
        state[node] = 2
    for node in graph:
        visit(node)
    if cyclic:
        errors.append('Cyclic requirement dependencies')
    if any(s.get('outcome') == 'complete_reconciliation' for s in coverage.get('sources', [])):
        errors.append('No source may claim complete reconciliation of all chats')
    return errors


def check(root: Path) -> dict:
    register = json.loads((root / 'plans/requirement-register.json').read_text())
    coverage = json.loads((root / 'plans/source-coverage.json').read_text())
    backlog = json.loads((root / 'plans/memory-backlog.json').read_text())
    prd_ids = set(re.findall(r'^\| ([A-Z]+-\d{3}) \|', (root / 'docs/PRD.md').read_text(), re.MULTILINE))
    errors = validate(register, coverage, prd_ids, backlog, lambda p: (root / p).resolve().is_relative_to(root.resolve()) and (root / p).is_file())
    if errors:
        raise ValueError('\n'.join(errors))
    count = lambda field: {v: sum(e[field] == v for e in register['requirements']) for v in register['vocabulary'][field]}
    return {'scope': 'register consistency only, not capability proof', 'requirements': len(register['requirements']),
            'implementation': count('implementation'), 'integration': count('integration'), 'merge': count('merge'),
            'deployment': count('deployment'), 'sources': len(coverage['sources']),
            'owner_decisions_needed': sorted(e['id'] for e in register['requirements'] if e.get('owner_decision_needed'))}


class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.vocab = {'decision': ['accepted'], 'implementation': ['not_started', 'partial', 'implemented_on_branch'],
                      'integration': ['not_applicable', 'backend_connected'], 'merge': ['not_merged', 'branch_only', 'merged_to_main'],
                      'deployment': ['not_deployed']}
        self.entry = {'id': 'MEM-001', 'decision': 'accepted', 'implementation': 'partial', 'integration': 'backend_connected',
                      'merge': 'branch_only', 'deployment': 'not_deployed', 'origin': ['SRC-A'], 'memory_jobs': ['M01'],
                      'depends_on': [], 'acceptance_evidence': []}
        self.register = {'vocabulary': self.vocab, 'requirements': [self.entry]}
        self.coverage = {'sources': [{'id': 'SRC-A', 'destinations': ['MEM-001']}]}
        self.backlog = {'jobs': [{'id': 'M01', 'requirements': ['MEM-001']}]}
    def errors(self, **kw):
        return validate(self.register, self.coverage, kw.get('prd', {'MEM-001'}), self.backlog, kw.get('exists', lambda p: True))
    def test_valid(self): self.assertEqual(self.errors(), [])
    def test_missing_prd_requirement(self): self.assertTrue(self.errors(prd={'MEM-001', 'MEM-002'}))
    def test_unknown_state(self): self.entry['merge'] = 'shipped'; self.assertTrue(self.errors())
    def test_claim_needs_evidence(self): self.entry['implementation'] = 'implemented_on_branch'; self.assertTrue(self.errors())
    def test_evidence_must_exist(self):
        self.entry.update(implementation='implemented_on_branch', acceptance_evidence=['nope.md'])
        self.assertTrue(self.errors(exists=lambda p: False))
    def test_unstarted_cannot_be_integrated(self): self.entry['implementation'] = 'not_started'; self.assertTrue(self.errors())
    def test_deployment_not_claimable(self): self.vocab['deployment'].append('deployed'); self.entry['deployment'] = 'deployed'; self.assertTrue(self.errors())
    def test_origin_must_be_recorded(self): self.entry['origin'] = ['SRC-UNKNOWN']; self.assertTrue(self.errors())
    def test_job_mapping_both_ways(self): self.entry['memory_jobs'] = []; self.assertTrue(self.errors())
    def test_dependency_cycle(self):
        other = dict(self.entry, id='MEM-002', memory_jobs=[], depends_on=['MEM-001']); self.entry['depends_on'] = ['MEM-002']
        self.register['requirements'].append(other); self.assertIn('Cyclic requirement dependencies', self.errors(prd={'MEM-001', 'MEM-002'}))
    def test_no_complete_reconciliation_claim(self):
        self.coverage['sources'][0]['outcome'] = 'complete_reconciliation'; self.assertTrue(self.errors())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        unittest.main(argv=['check_requirement_register'], verbosity=2)
    print(json.dumps(check(ROOT), indent=2))


if __name__ == '__main__':
    main()
