"""Synthetic offline tests for the agent claims checker. Uses temporary Git repositories only."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

path = Path(__file__).with_name('check_claims.py')
spec = importlib.util.spec_from_file_location('check_claims', path)
claims = importlib.util.module_from_spec(spec); spec.loader.exec_module(claims)


def claim(cid, agent, paths, status='active'):
    lines = ['---', 'id: ' + cid, 'agent: ' + agent, 'status: ' + status,
             'task: Synthetic task', 'claimed: 2026-10-17', 'paths:']
    lines += ['  - ' + p for p in paths]
    return '\n'.join(lines + ['---', '', 'Notes for the other agent.', ''])


def git(*args, cwd):
    return subprocess.run(('git',) + args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class ParseTests(unittest.TestCase):
    def test_reads_fields_and_paths(self):
        c = claims.parse_claim(claim('codex-scrub', 'codex', ['alfred/scrub.py', 'tests/fixtures/scrub/']),
                               'codex-scrub.md')
        self.assertEqual(c['agent'], 'codex')
        self.assertEqual(c['paths'], ['alfred/scrub.py', 'tests/fixtures/scrub/'])
        self.assertIn('Notes for the other agent.', c['notes'])

    def test_rejects_bad_claims(self):
        bad = {
            'missing front matter': ('id: x\n', 'x.md'),
            'name differs from id': (claim('codex-a', 'codex', ['a.py']), 'codex-b.md'),
            'unknown agent': (claim('robot-a', 'robot', ['a.py']), 'robot-a.md'),
            'id lacks agent prefix': (claim('a', 'codex', ['a.py']), 'a.md'),
            'unknown status': (claim('codex-a', 'codex', ['a.py'], status='maybe'), 'codex-a.md'),
            'no paths': (claim('codex-a', 'codex', []), 'codex-a.md'),
            'absolute path': (claim('codex-a', 'codex', ['/etc/passwd']), 'codex-a.md'),
            'parent path': (claim('codex-a', 'codex', ['../a.py']), 'codex-a.md'),
            'duplicate key': (claim('codex-a', 'codex', ['a.py']).replace('task:', 'agent: codex\ntask:'), 'codex-a.md'),
        }
        for label, (text, name) in bad.items():
            with self.subTest(label), self.assertRaises(claims.ClaimError):
                claims.parse_claim(text, name)


class OverlapTests(unittest.TestCase):
    def test_pattern_overlap(self):
        yes = [('a.py', 'a.py'), ('alfred/', 'alfred/scrub.py'), ('alfred/scrub.py', 'alfred/'),
               ('tests/test_scrub*.py', 'tests/test_scrub.py'), ('tests/', 'tests/test_*.py'),
               ('docs/a/', 'docs/a/b/')]
        no = [('a.py', 'b.py'), ('alfred/', 'alfredo/x.py'), ('tests/test_scrub*.py', 'tests/test_core.py'),
              ('docs/a/', 'docs/ab/')]
        for a, b in yes:
            with self.subTest(a=a, b=b):
                self.assertTrue(claims.overlaps(a, b))
        for a, b in no:
            with self.subTest(a=a, b=b):
                self.assertFalse(claims.overlaps(a, b))

    def test_live_claims_must_not_overlap(self):
        live = [claims.parse_claim(claim('claude-enc', 'claude', ['alfred/core.py']), 'claude-enc.md'),
                claims.parse_claim(claim('codex-x', 'codex', ['alfred/']), 'codex-x.md')]
        self.assertTrue(any('overlap' in e for e in claims.validate(live)))
        finished = [live[0], claims.parse_claim(claim('codex-x', 'codex', ['alfred/'], 'done'), 'codex-x.md')]
        self.assertEqual(claims.validate(finished), [])

    def test_astra_cannot_claim_shared_or_shelf_paths(self):
        for p in ('AGENTS.md', 'CHANGELOG.md', '.github/workflows/x.yml', 'plans/', 'third_party/research-shelf/',
                  'coordination/README.md', 'tools/check_claims.py', 'coordination/claims/codex-x.md', '*.md'):
            with self.subTest(p):
                c = claims.parse_claim(claim('codex-x', 'codex', [p]), 'codex-x.md')
                self.assertTrue(any('shared' in e for e in claims.validate([c])))


class ChangeTests(unittest.TestCase):
    def setUp(self):
        self.base = [claims.parse_claim(claim('codex-scrub', 'codex', ['alfred/scrub.py', 'tests/test_scrub.py']),
                                        'codex-scrub.md'),
                     claims.parse_claim(claim('claude-enc', 'claude', ['alfred/core.py']), 'claude-enc.md')]

    def errors(self, branch, changed, head=None):
        return claims.check_changes(changed, branch, self.base, self.base if head is None else head)

    def test_astra_inside_its_claim_passes(self):
        self.assertEqual(self.errors('codex/scrub', ['alfred/scrub.py', 'tests/test_scrub.py',
                                                     'coordination/claims/codex-scrub.md']), [])

    def test_astra_outside_its_claim_fails(self):
        for p in ('alfred/core.py', 'alfred/other.py', 'AGENTS.md', 'coordination/claims/claude-enc.md',
                  'coordination/claims/codex-new.md'):
            with self.subTest(p):
                self.assertTrue(self.errors('codex/scrub', [p]))

    def test_astra_cannot_self_claim_in_its_own_pr(self):
        head = self.base + [claims.parse_claim(claim('codex-more', 'codex', ['alfred/other.py']), 'codex-more.md')]
        self.assertTrue(self.errors('codex/scrub', ['alfred/other.py'], head))

    def test_claude_must_leave_astra_paths_alone(self):
        self.assertTrue(self.errors('claude/enc', ['alfred/scrub.py']))
        self.assertEqual(self.errors('claude/enc', ['alfred/core.py', 'AGENTS.md',
                                                    'coordination/claims/codex-next.md']), [])

    def test_claim_added_in_the_same_pr_still_protects(self):
        head = self.base + [claims.parse_claim(claim('codex-q', 'codex', ['tools/question_set.py']), 'codex-q.md')]
        self.assertTrue(self.errors('claude/other', ['tools/question_set.py'], head))

    def test_finished_claims_release_their_paths(self):
        done = [claims.parse_claim(claim('codex-scrub', 'codex', ['alfred/scrub.py'], 'done'), 'codex-scrub.md')]
        self.assertEqual(claims.check_changes(['alfred/scrub.py'], 'claude/x', done, done), [])
        self.assertTrue(claims.check_changes(['alfred/scrub.py'], 'codex/scrub', done, done))

    def test_other_branches_are_not_policed(self):
        self.assertEqual(self.errors('edem/tweak', ['alfred/scrub.py', 'AGENTS.md']), [])


class GitTests(unittest.TestCase):
    def test_reads_claims_and_changes_from_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git('init', '-q', '-b', 'main', cwd=root)
            folder = root / 'coordination/claims'; folder.mkdir(parents=True)
            (folder / 'codex-scrub.md').write_text(claim('codex-scrub', 'codex', ['alfred/scrub.py']))
            git('add', '-A', cwd=root)
            git('-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'base', cwd=root)
            base = git('rev-parse', 'HEAD', cwd=root)
            (root / 'alfred').mkdir(); (root / 'alfred/core.py').write_text('x = 1\n')
            git('add', '-A', cwd=root)
            git('-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'head', cwd=root)
            self.assertEqual([c['id'] for c in claims.claims_at(root, base)], ['codex-scrub'])
            self.assertEqual(claims.changed_files(root, base), ['alfred/core.py'])
            self.assertEqual(claims.main(['--root', str(root), '--base', base, '--branch', 'codex/scrub']), 1)
            self.assertEqual(claims.main(['--root', str(root), '--base', base, '--branch', 'claude/enc']), 0)
            self.assertEqual(claims.main(['--root', str(root)]), 0)

    def test_repository_claims_are_valid(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(claims.main(['--root', str(root)]), 0)


if __name__ == '__main__':
    unittest.main()
