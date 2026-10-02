"""Validate authored memory plans and local links. No network or model execution.

This checks document/backlog consistency, not semantic correctness, licensing,
application security or whether any planned capability has been implemented.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def validate_plan(plan: dict, requirements: set[str], sources: set[str]) -> list[str]:
    errors: list[str] = []
    if plan.get('schema_version') != 1 or plan.get('scope') not in {'planning-only','implementation-tracking'}:
        errors.append('Unexpected backlog schema/scope')
    expected_runtime = plan.get('scope') == 'implementation-tracking'
    if plan.get('runtime_changes') is not expected_runtime:
        errors.append('Runtime-change flag disagrees with backlog scope')
    jobs = plan.get('jobs', [])
    ids = [j.get('id') for j in jobs]
    if len(ids) != len(set(ids)) or any(not isinstance(i, str) or not re.fullmatch(r'M\d{2}', i) for i in ids):
        errors.append('Duplicate or malformed job IDs')
    known = set(ids)
    graph = {}
    covered = set()
    for job in jobs:
        jid = job.get('id')
        dependencies = job.get('depends_on', [])
        graph[jid] = dependencies
        if any(d not in known or d == jid for d in dependencies):
            errors.append(f'{jid}: unknown/self dependency')
        reqs = set(job.get('requirements', []))
        covered |= reqs
        if not reqs or not reqs.issubset(requirements):
            errors.append(f'{jid}: unknown/missing requirement')
        if not set(job.get('candidates', [])).issubset(sources):
            errors.append(f'{jid}: unknown repository candidate')
        if not job.get('acceptance') or not all(isinstance(x, str) and x.strip() for x in job['acceptance']):
            errors.append(f'{jid}: acceptance evidence is unspecified')
        if job.get('status') not in {'planned', 'in_progress', 'blocked', 'implemented'}:
            errors.append(f'{jid}: unknown status')
        if job.get('status') == 'implemented' and not job.get('evidence'):
            errors.append(f'{jid}: implementation status needs evidence references')
    if covered != requirements:
        errors.append('PRD requirements are not completely mapped')
    if not set(plan.get('private_pilot_requires', [])).issubset(known):
        errors.append('Unknown private pilot gate')
    visiting, done = set(), set()
    def visit(node):
        if node in visiting:
            return False
        if node in done or node not in graph:
            return True
        visiting.add(node)
        if any(not visit(child) for child in graph[node]):
            return False
        visiting.remove(node)
        done.add(node)
        return True
    if any(not visit(node) for node in graph):
        errors.append('Cyclic job dependencies')
    return errors


def check(root: Path) -> dict:
    plan = json.loads((root / 'plans/memory-backlog.json').read_text())
    registry = json.loads((root / 'research/memory-sources.json').read_text())
    prd = (root / 'docs/PRD.md').read_text()
    requirements = set(re.findall(r'^\| ([A-Z]+-\d{3}) \|', prd, re.MULTILINE))
    entries = registry['pinned_reviews'] + registry['documentation_reviews']
    source_ids = {e['id'] for e in entries}
    # Whole-product requirements tracked outside the M series are covered by the
    # requirement register (tools/check_requirement_register.py), not by M jobs.
    register = root / 'plans/requirement-register.json'
    outside = set()
    if register.is_file():
        outside = {r['id'] for r in json.loads(register.read_text())['requirements'] if not r['memory_jobs']}
    errors = validate_plan(plan, requirements - outside, source_ids)
    if len(source_ids) != len(entries) or len({e['repository'] for e in entries}) != len(entries):
        errors.append('Duplicate repository records')
    if registry['upstream_code_executed'] is not False:
        errors.append('Research register says upstream code executed')
    new_count = registry.get('new_upstream_files_copied')
    if type(new_count) is not int or new_count < 0:
        errors.append('Invalid copied-source count')
    shelf = registry.get('preserved_source_shelf', [])
    if len({x.get('repository') for x in shelf}) != len(shelf) or any(type(x.get('files')) is not int or x.get('files', -1) < 1 for x in shelf):
        errors.append('Invalid preserved source shelf')
    shelf_total = sum(x['files'] for x in shelf) if shelf else 0
    if shelf_total != registry.get('extension_source_files_total'):
        errors.append('Extension source total differs from shelf')
    new_total = sum(x['files'] for x in shelf if x.get('added_on') == registry.get('reviewed_on'))
    if new_total != new_count:
        errors.append('New copied-source count differs from dated shelf')
    if registry.get('original_source_files_total', 0) + shelf_total != registry.get('all_preserved_source_files_total'):
        errors.append('All-archive source total differs')
    for item in registry['pinned_reviews']:
        for key in ('commit', 'licence_blob'):
            if not re.fullmatch(r'[0-9a-f]{40}', item[key]):
                errors.append(f'{item["id"]}: malformed {key}')
    files = plan['documents'] + ['plans/memory-backlog.json', 'research/memory-sources.json', 'tools/check_memory_plan.py']
    hashes, link_count = {}, 0
    for name in files:
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            errors.append(f'Missing/outside document: {name}')
            continue
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if path.suffix != '.md':
            continue
        for target in re.findall(r'\]\(([^\s)]+)\)', path.read_text()):
            parts = urlsplit(target)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            destination = (path.parent / unquote(parts.path)).resolve()
            link_count += 1
            if not destination.is_relative_to(root.resolve()) or not destination.exists():
                errors.append(f'{name}: unresolved local link {target}')
    for job in plan['jobs']:
        for evidence in job.get('evidence', []):
            path = (root / evidence).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                errors.append(f'{job["id"]}: missing local evidence')
    if errors:
        raise ValueError('\n'.join(errors))
    return {'scope': 'backlog/source-shelf consistency only', 'requirements': len(requirements), 'jobs': len(plan['jobs']),
            'repository_references': len(entries), 'pinned_reviews': len(registry['pinned_reviews']),
            'preserved_extension_repositories': len(registry.get('preserved_source_shelf', [])),
            'preserved_extension_files': registry.get('extension_source_files_total', 0),
            'preserved_all_source_files': registry.get('all_preserved_source_files_total', 0),
            'local_links_checked': link_count, 'runtime_changed': plan['runtime_changes'], 'model_run': False, 'sha256': hashes}


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'schema_version': 1, 'scope': 'planning-only', 'runtime_changes': False,
                     'private_pilot_requires': ['M01'], 'jobs': [
                         {'id': 'M01', 'status': 'planned', 'depends_on': [], 'requirements': ['MEM-001'],
                          'candidates': ['source'], 'acceptance': ['A real negative test']}]}
    def errors(self, plan=None):
        return validate_plan(self.plan if plan is None else plan, {'MEM-001'}, {'source'})
    def test_valid(self):
        self.assertEqual(self.errors(), [])
    def test_implementation_tracking(self):
        self.plan.update(scope='implementation-tracking',runtime_changes=True)
        self.plan['jobs'][0].update(status='implemented',evidence=['tests/test_memory_m01.py'])
        self.assertEqual(self.errors(),[])
    def test_planning_cannot_claim_runtime(self):
        self.plan['runtime_changes']=True; self.assertTrue(self.errors())
    def test_implementation_cannot_hide_runtime(self):
        self.plan['scope']='implementation-tracking'; self.assertTrue(self.errors())
    def test_duplicate(self):
        self.plan['jobs'].append(deepcopy(self.plan['jobs'][0])); self.assertTrue(self.errors())
    def test_unknown_requirement(self):
        self.plan['jobs'][0]['requirements'] = ['MEM-999']; self.assertTrue(self.errors())
    def test_unknown_candidate(self):
        self.plan['jobs'][0]['candidates'] = ['not-reviewed']; self.assertTrue(self.errors())
    def test_unknown_dependency(self):
        self.plan['jobs'][0]['depends_on'] = ['M99']; self.assertTrue(self.errors())
    def test_cycle(self):
        other = deepcopy(self.plan['jobs'][0]); other['id'] = 'M02'; other['depends_on'] = ['M01']
        self.plan['jobs'][0]['depends_on'] = ['M02']; self.plan['jobs'].append(other)
        self.assertIn('Cyclic job dependencies', self.errors())
    def test_completion_needs_evidence(self):
        self.plan['jobs'][0]['status'] = 'implemented'; self.assertTrue(self.errors())
    def test_unknown_status(self):
        self.plan['jobs'][0]['status'] = 'magically-done'; self.assertTrue(self.errors())
    def test_acceptance_required(self):
        self.plan['jobs'][0]['acceptance'] = []; self.assertTrue(self.errors())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PlanTests))
        raise SystemExit(0 if result.wasSuccessful() else 1)
    print(json.dumps(check(ROOT), indent=2))


if __name__ == '__main__':
    main()
