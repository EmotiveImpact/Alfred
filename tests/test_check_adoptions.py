"""Offline tests for tools/check_adoptions.py, the adoption credit check.

Every project, commit, path and notice here is invented. The synthetic research shelf and source
library live in tests/fixtures/adoptions/ and are copied into a temporary repository for each
test. The last test reads the real catalogues and manifests as data only; nothing under
third_party/ is imported or run.
"""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools import check_adoptions as ca

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).with_name('fixtures') / 'adoptions'
HEADERS = FIXTURES / 'headers'
MIT = (HEADERS / 'mit_complete.py').read_text(encoding='utf-8')
APACHE = (HEADERS / 'apache_complete.ts').read_text(encoding='utf-8')
TIDY = 'a1' * 20
GRAPH = 'b2' * 20


class AdoptionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(FIXTURES / 'shelf', self.root / 'third_party/research-shelf')
        shutil.copytree(FIXTURES / 'library', self.root / 'third_party/library')
        for folder in ca.SOURCES:
            (self.root / folder).mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def findings(self, text, rel='alfred/adapted.py'):
        self.write(rel, text)
        result = ca.scan(self.root)
        self.assertEqual(result.manifest_errors, [])
        return [str(f) for f in result.findings]

    def run_main(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ca.main(['--root', str(self.root)])
        return code, out.getvalue(), err.getvalue()


class CompleteCreditTests(AdoptionCase):
    def test_complete_mit_credit_passes(self):
        self.write('alfred/adapted.py', MIT)
        result = ca.scan(self.root)
        self.assertEqual(result.findings, [])
        self.assertEqual([str(c) for c in result.credits],
                         ['alfred/adapted.py:1  example-labs/tidy-memory src/tidy/store.py at a1a1a1a1a1a1 (MIT, research shelf)'])

    def test_complete_apache_credit_with_continued_notice_passes(self):
        self.write('console/src/rank.ts', APACHE)
        result = ca.scan(self.root)
        self.assertEqual(result.findings, [])
        self.assertEqual([str(c) for c in result.credits],
                         ['console/src/rank.ts:1  sample-works/graph-kit graph/rank.ts at b2b2b2b2b2b2 (Apache-2.0, research shelf)'])

    def test_credit_inside_a_module_docstring_passes(self):
        self.write('tools/adapted.py', (HEADERS / 'mit_docstring.py').read_text(encoding='utf-8'))
        result = ca.scan(self.root)
        self.assertEqual(result.findings, [])
        self.assertEqual(len(result.credits), 1)

    def test_block_comment_credit_passes(self):
        css = ('/* Adapted from: sample-works/graph-kit\n'
               ' * Path: graph/rank.ts\n'
               ' * Commit: ' + GRAPH + '\n'
               ' * Licence: Apache-2.0\n'
               ' * Notice: Graph Kit Copyright 2024 Sample Works Ltd.\n'
               ' * Changes: Only the ordering rule is kept, as a style. */\n'
               '.rank { order: 1; }\n')
        self.assertEqual(self.findings(css, 'web/rank.css'), [])

    def test_two_credits_in_one_file_are_both_checked(self):
        block = ''.join(MIT.splitlines(True)[:6]).replace('src/tidy/store.py', 'src/tidy/gone.py')
        second = len(MIT.splitlines()) + 2
        self.write('alfred/adapted.py', MIT + '\n' + block)
        result = ca.scan(self.root)
        self.assertEqual([str(f) for f in result.findings],
                         [f'alfred/adapted.py:{second + 1}: src/tidy/gone.py is not in the research shelf snapshot of '
                          'example-labs/tidy-memory'])
        self.assertEqual([c.line for c in result.credits], [1])


class MissingFieldTests(AdoptionCase):
    def test_each_required_field_is_reported_when_missing(self):
        cases = {
            'Path': '# Path: src/tidy/store.py\n',
            'Commit': '# Commit: ' + TIDY + '\n',
            'Licence': '# Licence: MIT\n',
        }
        for field, line in cases.items():
            with self.subTest(field):
                self.assertEqual(self.findings(MIT.replace(line, '')),
                                 ['alfred/adapted.py:1: credit is missing ' + field])

    def test_empty_value_counts_as_missing(self):
        self.assertEqual(self.findings(MIT.replace('# Path: src/tidy/store.py', '# Path:')),
                         ['alfred/adapted.py:1: credit is missing Path'])

    def test_missing_project_is_reported(self):
        self.assertEqual(self.findings(MIT.replace('Adapted from: example-labs/tidy-memory', 'Adapted from:')),
                         ['alfred/adapted.py:1: credit is missing the upstream project after "Adapted from:"'])

    def test_several_missing_fields_are_each_reported(self):
        text = MIT.replace('# Commit: ' + TIDY + '\n', '').replace('# Licence: MIT\n', '')
        self.assertEqual(self.findings(text), ['alfred/adapted.py:1: credit is missing Commit',
                                               'alfred/adapted.py:1: credit is missing Licence'])

    def test_mit_needs_its_copyright_notice(self):
        self.assertEqual(self.findings(MIT.replace('# Copyright: Copyright (c) 2025 Example Labs\n', '')),
                         ['alfred/adapted.py:1: MIT requires a Copyright line carrying the upstream copyright notice'])

    def test_apache_needs_its_notice(self):
        text = APACHE.replace('// Notice: Graph Kit\n//   Copyright 2024 Sample Works Ltd.\n', '')
        self.assertEqual(self.findings(text, 'console/src/rank.ts'),
                         ['console/src/rank.ts:1: Apache-2.0 requires a Notice line carrying the upstream notice'])

    def test_apache_needs_a_statement_of_changes(self):
        text = APACHE.replace("// Changes: Ported to the console's types and renamed the export.\n", '')
        self.assertEqual(self.findings(text, 'console/src/rank.ts'),
                         ['console/src/rank.ts:1: Apache-2.0 requires a Changes line stating what was changed'])


class MalformedCreditTests(AdoptionCase):
    def test_loose_adapted_from_comment_fails(self):
        text = '# adapted from the tidy-memory store, roughly\n\ndef rank(items):\n    return items\n'
        self.assertEqual(self.findings(text),
                         ['alfred/adapted.py:1: credit line must read "Adapted from: owner/name"; '
                          'describe the source of an idea in other words'])

    def test_project_must_be_owner_slash_name(self):
        self.assertEqual(self.findings(MIT.replace('example-labs/tidy-memory', 'https://github.com/example-labs/tidy-memory')),
                         ['alfred/adapted.py:1: "https://github.com/example-labs/tidy-memory" is not an upstream project name; '
                          'write owner/name as the catalogue does'])

    def test_short_commit_fails(self):
        self.assertEqual(self.findings(MIT.replace(TIDY, TIDY[:12])),
                         ['alfred/adapted.py:3: Commit must be the full 40-character lower-case hash, not "a1a1a1a1a1a1"'])

    def test_unsafe_path_fails(self):
        for bad in ('../secrets.py', '/src/tidy/store.py', 'src\\tidy\\store.py', 'src/./store.py'):
            with self.subTest(bad):
                self.assertEqual(self.findings(MIT.replace('src/tidy/store.py', bad)),
                                 [f'alfred/adapted.py:2: Path must be a relative path inside the upstream project, not "{bad}"'])

    def test_american_spelling_of_licence_is_named(self):
        self.assertEqual(self.findings(MIT.replace('# Licence: MIT', '# License: MIT')),
                         ['alfred/adapted.py:1: credit is missing Licence',
                          'alfred/adapted.py:4: unknown credit field "License"; ALFRED spells it Licence'])

    def test_unknown_field_fails(self):
        self.assertEqual(self.findings(MIT.replace('# Changes:', '# Author: Example Labs\n# Changes:')),
                         ['alfred/adapted.py:6: unknown credit field "Author"; '
                          'end the credit with a blank line if this line is not part of it'])

    def test_duplicate_field_fails(self):
        self.assertEqual(self.findings(MIT.replace('# Licence: MIT\n', '# Licence: MIT\n# Licence: MIT\n')),
                         ['alfred/adapted.py:5: Licence appears twice in this credit'])


class ManifestMatchTests(AdoptionCase):
    def test_unknown_project_fails(self):
        self.assertEqual(self.findings(MIT.replace('example-labs/tidy-memory', 'example-labs/other-thing')),
                         ['alfred/adapted.py:1: example-labs/other-thing is not pinned in the research shelf or the source library'])

    def test_project_with_the_wrong_letter_case_names_the_catalogue_spelling(self):
        self.assertEqual(self.findings(MIT.replace('example-labs/tidy-memory', 'Example-Labs/Tidy-Memory')),
                         ['alfred/adapted.py:1: Example-Labs/Tidy-Memory is not pinned in the research shelf or the source '
                          'library; the catalogue spells it example-labs/tidy-memory'])

    def test_wrong_commit_fails(self):
        other = 'c3' * 20
        self.assertEqual(self.findings(MIT.replace(TIDY, other)),
                         [f'alfred/adapted.py:3: commit {other} is not the pinned commit of example-labs/tidy-memory '
                          f'(the research shelf pins {TIDY})'])

    def test_path_absent_from_the_snapshot_fails(self):
        self.assertEqual(self.findings(MIT.replace('src/tidy/store.py', 'src/tidy/missing.py')),
                         ['alfred/adapted.py:2: src/tidy/missing.py is not in the research shelf snapshot of example-labs/tidy-memory'])

    def test_path_left_out_of_the_snapshot_names_the_reason(self):
        self.assertEqual(self.findings(MIT.replace('src/tidy/store.py', 'data/sample.db')),
                         ['alfred/adapted.py:2: data/sample.db was left out of the research shelf snapshot of '
                          'example-labs/tidy-memory (binary/media/model/database/archive asset)'])

    def test_licence_mismatch_fails(self):
        self.assertEqual(self.findings(MIT.replace('# Licence: MIT', '# Licence: Apache-2.0')),
                         ['alfred/adapted.py:4: Licence "Apache-2.0" does not match "MIT", which the research shelf '
                          'records for example-labs/tidy-memory'])

    def test_copyright_must_be_found_upstream(self):
        text = MIT.replace('Copyright (c) 2025 Example Labs', 'Copyright (c) 2024 Someone Else')
        self.assertEqual(self.findings(text),
                         ['alfred/adapted.py:5: Copyright "Copyright (c) 2024 Someone Else" is not in the upstream licence, '
                          'notice or adapted file at the pinned commit'])

    def test_copyright_must_quote_whole_upstream_lines(self):
        for partial in ('Example Labs', 'Copyright', 'c', '2025 Example Labs'):
            with self.subTest(partial):
                text = MIT.replace('Copyright: Copyright (c) 2025 Example Labs', 'Copyright: ' + partial)
                self.assertEqual(self.findings(text),
                                 [f'alfred/adapted.py:5: Copyright "{partial}" is not in the upstream licence, '
                                  'notice or adapted file at the pinned commit'])

    def test_notice_may_quote_a_comment_in_the_adapted_upstream_file(self):
        text = APACHE.replace('// Notice: Graph Kit\n//   Copyright 2024 Sample Works Ltd.\n',
                              '// Notice: Synthetic upstream file for tests/test_check_adoptions.py. Inert text, never run.\n')
        self.assertEqual(self.findings(text, 'console/src/rank.ts'), [])

    def test_apache_notice_must_be_found_upstream(self):
        text = APACHE.replace('//   Copyright 2024 Sample Works Ltd.', '//   Copyright 2023 Sample Works Ltd.')
        self.assertEqual(self.findings(text, 'console/src/rank.ts'),
                         ['console/src/rank.ts:5: Notice "Graph Kit Copyright 2023 Sample Works Ltd." is not in the upstream '
                          'licence, notice or adapted file at the pinned commit'])

    def test_credit_problems_after_the_project_is_known_are_all_reported(self):
        text = MIT.replace('src/tidy/store.py', 'src/tidy/missing.py').replace('# Licence: MIT', '# Licence: Apache-2.0')
        self.assertEqual(self.findings(text), [
            'alfred/adapted.py:2: src/tidy/missing.py is not in the research shelf snapshot of example-labs/tidy-memory',
            'alfred/adapted.py:4: Licence "Apache-2.0" does not match "MIT", which the research shelf records for '
            'example-labs/tidy-memory'])


class LicenceClearanceTests(AdoptionCase):
    def credit(self, project, commit, licence, path='tool.py'):
        return (f'# Adapted from: {project}\n# Path: {path}\n# Commit: {commit}\n# Licence: {licence}\n'
                '# Copyright: Copyright (c) 2025 Nobody\n# Notice: none\n# Changes: none\n\nx = 1\n')

    def test_reference_only_project_fails(self):
        self.assertEqual(self.findings(self.credit('quiet-co/closed-notes', 'c3' * 20, 'MIT')),
                         ['alfred/adapted.py:1: quiet-co/closed-notes is reference only in the source library: no source '
                          'was copied, so there is nothing pinned to adapt from'])

    def test_unlicensed_project_fails_even_when_the_header_says_unlicense(self):
        expected = ('alfred/adapted.py:4: the source library records the licence of {} as "UNLICENSED (package declaration)", '
                    'which grants no right to copy it (UNLICENSED is not the Unlicense)')
        for project, commit in (('quiet-co/headless-client', 'd4' * 20), ('odd-hands/unlicensed-pkg', 'e5' * 20)):
            for claimed in ('Unlicense', 'UNLICENSED (package declaration)'):
                with self.subTest(project=project, claimed=claimed):
                    self.assertEqual(self.findings(self.credit(project, commit, claimed)), [expected.format(project)])

    def test_licence_not_established_fails_even_if_copied(self):
        self.assertEqual(self.findings(self.credit('odd-hands/no-assertion', 'f6' * 20, 'NOASSERTION')),
                         ['alfred/adapted.py:4: the source library records the licence of odd-hands/no-assertion as '
                          '"NOASSERTION", which is not cleared for adoption'])

    def test_licence_without_an_agreed_notice_rule_fails(self):
        self.assertEqual(self.findings(self.credit('plain-tools/free-bits', '07' * 20, 'Unlicense')),
                         ['alfred/adapted.py:4: this check has no notice rule for Unlicense yet; the owner must agree one '
                          'before code under it is adopted'])


class CopyDetectionTests(AdoptionCase):
    def test_byte_identical_copy_without_a_credit_fails(self):
        upstream = FIXTURES / 'shelf/snapshots/example-labs__tidy-memory/src/tidy/store.py'
        self.assertEqual(self.findings(upstream.read_text(encoding='utf-8'), 'alfred/store.py'),
                         ['alfred/store.py:1: identical to src/tidy/store.py in the research shelf snapshot of '
                          'example-labs/tidy-memory but has no "Adapted from" credit'])

    def test_tiny_identical_files_are_not_treated_as_copies(self):
        upstream = FIXTURES / 'shelf/snapshots/example-labs__tidy-memory/src/tidy/version.py'
        self.assertLess(upstream.stat().st_size, ca.MIN_COPY_BYTES)
        self.assertEqual(self.findings(upstream.read_text(encoding='utf-8'), 'alfred/version.py'), [])

    def test_third_party_and_tests_are_never_scanned(self):
        self.write('third_party/research-shelf/snapshots/example-labs__tidy-memory/extra.py', '# adapted from nowhere\n')
        self.write('tests/test_example.py', '# adapted from nowhere\n')
        self.write('alfred/third_party/vendored.py', '# adapted from nowhere\n')
        result = ca.scan(self.root)
        self.assertEqual(result.findings, [])
        self.assertEqual(result.scanned, 0)


class ManifestErrorTests(AdoptionCase):
    def errors_after(self, rel, change):
        path = self.root / rel
        change(path)
        result = ca.scan(self.root)
        code, out, err = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn('adoption check could not run', out)
        return result.manifest_errors

    def edit_json(self, change):
        def apply(path):
            data = json.loads(path.read_text(encoding='utf-8'))
            change(data)
            path.write_text(json.dumps(data), encoding='utf-8')
        return apply

    def test_invalid_json_is_reported_with_its_position(self):
        errors = self.errors_after('third_party/library/CATALOGUE.json', lambda p: p.write_text('{\n  "repositories": [\n}\n'))
        self.assertEqual(errors, ['third_party/library/CATALOGUE.json: not valid JSON (line 3, column 1: Expecting value)'])

    def test_missing_catalogue_is_reported(self):
        errors = self.errors_after('third_party/research-shelf/CATALOGUE.json', Path.unlink)
        self.assertEqual(errors, ['third_party/research-shelf/CATALOGUE.json: missing'])

    def test_catalogue_without_repositories_is_reported(self):
        errors = self.errors_after('third_party/library/CATALOGUE.json', self.edit_json(lambda d: d.pop('repositories')))
        self.assertEqual(errors, ['third_party/library/CATALOGUE.json: repositories must be a list'])

    def test_bad_catalogue_entries_are_reported(self):
        def change(data):
            data['repositories'][0]['commit'] = 'c3c3'
            data['repositories'][1].pop('licence')
            data['repositories'][2]['repository'] = 'no-slash'
            data['repositories'][3]['source_copied'] = 'yes'
            data['repositories'].append(dict(data['repositories'][4]))
        errors = self.errors_after('third_party/library/CATALOGUE.json', self.edit_json(change))
        self.assertEqual(errors, [
            'third_party/library/CATALOGUE.json: repositories[0].commit must be a 40-character lower-case hash',
            'third_party/library/CATALOGUE.json: repositories[1].licence must be a non-empty string',
            'third_party/library/CATALOGUE.json: repositories[2].repository must be owner/name',
            'third_party/library/CATALOGUE.json: repositories[3].source_copied must be true or false',
            'third_party/library/CATALOGUE.json: repositories[5] lists plain-tools/free-bits a second time',
        ])

    def test_missing_manifest_for_a_copied_project_is_reported(self):
        errors = self.errors_after('third_party/research-shelf/manifests/sample-works__graph-kit.json', Path.unlink)
        self.assertEqual(errors, ['third_party/research-shelf/manifests/sample-works__graph-kit.json: missing, '
                                  'but the catalogue lists sample-works/graph-kit as copied'])

    def test_bad_manifest_files_are_reported(self):
        def change(data):
            data['files'][0]['path'] = '../../outside'
            data['files'][1]['git_blob_sha1'] = 'nope'
            data['excluded'] = 'everything'
        errors = self.errors_after('third_party/research-shelf/manifests/example-labs__tidy-memory.json',
                                   self.edit_json(change))
        self.assertEqual(errors, [
            'third_party/research-shelf/manifests/example-labs__tidy-memory.json: files[0].path must be a relative path '
            'inside the snapshot',
            'third_party/research-shelf/manifests/example-labs__tidy-memory.json: files[1].git_blob_sha1 must be a '
            '40-character lower-case hash',
            'third_party/research-shelf/manifests/example-labs__tidy-memory.json: excluded must be a list',
        ])

    def test_unsafe_licence_path_is_reported(self):
        errors = self.errors_after('third_party/research-shelf/CATALOGUE.json',
                                   self.edit_json(lambda d: d['repositories'][0].update(licence_path='/etc/passwd')))
        self.assertEqual(errors, ['third_party/research-shelf/CATALOGUE.json: repositories[0].licence_path must be a '
                                  'relative path inside the snapshot'])


class CommandTests(AdoptionCase):
    def test_nothing_adopted_passes_and_says_so(self):
        self.write('alfred/core.py', '"""Synthetic module with no adopted code."""\n')
        code, out, err = self.run_main()
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(out.splitlines(), [
            'Scanned 1 file in alfred/, tools/, web/, console/src/ against 5 copied snapshots '
            '(research shelf 2, source library 3); 2 reference-only entries cannot be adapted from.',
            'No adopted code yet: no file carries an "Adapted from" credit and none is a byte-identical copy of a '
            'snapshot file, so there is nothing to check.',
            'adoptions ok',
        ])

    def test_clean_credits_are_listed_with_their_limits(self):
        self.write('alfred/adapted.py', MIT)
        self.write('console/src/rank.ts', APACHE)
        code, out, err = self.run_main()
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(out.splitlines()[1:], [
            'ok  alfred/adapted.py:1  example-labs/tidy-memory src/tidy/store.py at a1a1a1a1a1a1 (MIT, research shelf)',
            'ok  console/src/rank.ts:1  sample-works/graph-kit graph/rank.ts at b2b2b2b2b2b2 (Apache-2.0, research shelf)',
            '2 credits match the pinned manifests. A matching credit is not licence clearance or owner approval.',
            'adoptions ok',
        ])

    def test_findings_are_sorted_one_per_line_and_exit_one(self):
        self.write('web/z.js', '// adapted from somewhere\n')
        self.write('alfred/b.py', MIT.replace(TIDY, TIDY[:7]))
        self.write('alfred/a.py', MIT.replace('example-labs/tidy-memory', 'example-labs/other-thing'))
        first = self.run_main()
        self.assertEqual(first, self.run_main())
        code, out, err = first
        self.assertEqual(code, 1)
        self.assertEqual(err.splitlines(), [
            'error: alfred/a.py:1: example-labs/other-thing is not pinned in the research shelf or the source library',
            'error: alfred/b.py:3: Commit must be the full 40-character lower-case hash, not "a1a1a1a"',
            'error: web/z.js:1: credit line must read "Adapted from: owner/name"; '
            'describe the source of an idea in other words',
        ])
        self.assertEqual(out.splitlines()[-1], '3 adoption errors')

    def test_missing_source_folders_are_noted(self):
        shutil.rmtree(self.root / 'web')
        code, out, err = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn('note: web/ is not present, so it was not scanned', out.splitlines())

    def test_no_source_folders_at_all_is_an_error(self):
        for folder in ca.SOURCES:
            shutil.rmtree(self.root / folder)
        code, out, err = self.run_main()
        self.assertEqual(code, 2)
        self.assertEqual(err.splitlines(), ['error: none of alfred/, tools/, web/, console/src/ exists under the root'])

    def test_binary_files_are_skipped(self):
        (self.root / 'web/logo.png').write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00adapted from')
        result = ca.scan(self.root)
        self.assertEqual((result.findings, result.scanned), ([], 0))


class RealRepositoryTests(unittest.TestCase):
    def test_the_repository_passes(self):
        result = ca.scan(REPO)
        self.assertEqual(result.manifest_errors, [])
        self.assertEqual([str(f) for f in result.findings], [])
        self.assertGreater(result.scanned, 0)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ca.main(['--root', str(REPO)])
        self.assertEqual((code, err.getvalue()), (0, ''))
        if not result.credits:
            self.assertIn('No adopted code yet', out.getvalue())


if __name__ == '__main__':
    unittest.main()
