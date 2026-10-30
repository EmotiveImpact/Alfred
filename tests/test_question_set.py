"""The question set harness: format, path guards, scoring, reports and comparison.

Runs only on the invented vault and questions in tests/fixtures/question_set/. The
pinned numbers were worked out by hand from what alfred.grounded.retrieve returns for
that fixture; they describe lexical retrieval on a tiny synthetic set, not quality.
Every test is offline and deterministic.
"""
import contextlib
import io
import json
import os
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from alfred.local import Fault
from tools import question_set as qs
from tools.evaluate_retrieval import fts5_available

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests' / 'fixtures' / 'question_set'
QUESTIONS = FIXTURE / 'questions.json'
VAULT = FIXTURE / 'vault'
FTS5 = fts5_available()
PELLHAM = ['clients/pellham-glassworks/account.md', 'clients/pellham-glassworks/renewal.md']


def fixture_questions():
    return json.loads(QUESTIONS.read_text())


DROP = object()


def question(**fields):
    base = {'id': 'q1', 'category': 'fact', 'question': 'Where is the Grellmouth depot?',
            'expect': ['places/grellmouth-depot.md']}
    base.update(fields)
    return {k: v for k, v in base.items() if v is not DROP}


def question_set(*questions, **top):
    data = {'schema': 'alfred.question-set.v1', 'questions': list(questions) or [question()]}
    data.update(top)
    return {k: v for k, v in data.items() if v is not DROP}


def encode(data):
    return json.dumps(data).encode()


def call(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        status = qs.main(argv)
    return status, out.getvalue(), err.getvalue()


class Scratch(unittest.TestCase):
    """Each test gets a folder outside the repository, removed afterwards."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='alfred-question-set-test-')).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.assertFalse(self.tmp.is_relative_to(ROOT), 'the temporary folder must be outside the repository')

    def outside_copy(self):
        """The fixture copied outside the repository, as the owner's real files would be."""
        shutil.copytree(VAULT, self.tmp / 'vault')
        shutil.copyfile(QUESTIONS, self.tmp / 'questions.json')
        return self.tmp / 'questions.json', self.tmp / 'vault'

    def write_questions(self, data, name='questions.json'):
        path = self.tmp / name
        path.write_bytes(encode(data))
        return path


class FormatTests(unittest.TestCase):
    def refused(self, data, code):
        raw = data if isinstance(data, bytes) else encode(data)
        with self.assertRaises(qs.QuestionSetError) as caught:
            qs.parse_question_set(raw)
        self.assertEqual(caught.exception.code, code)
        message = str(caught.exception)
        self.assertNotIn('\n', message)
        self.assertTrue(message)
        return message

    def test_fixture_is_valid_and_summarised_by_category(self):
        questions = qs.load_question_set(QUESTIONS)
        self.assertEqual(len(questions), 12)
        self.assertEqual(qs.category_counts(questions),
                         {'fact': 3, 'connected': 3, 'time': 2, 'preference': 2, 'refuse': 2})
        self.assertEqual(len({q['id'] for q in questions}), 12)

    def test_minimal_question_set_is_accepted_and_normalised(self):
        [q] = qs.parse_question_set(encode(question_set(question(avoid=['people/corin-dask.md'], note='x'))))
        self.assertEqual(q, {'id': 'q1', 'category': 'fact', 'question': 'Where is the Grellmouth depot?',
                             'expect': ['places/grellmouth-depot.md'], 'avoid': ['people/corin-dask.md']})
        # A byte order mark, as some editors save, is accepted.
        [r] = qs.parse_question_set(b'\xef\xbb\xbf' + encode(question_set(question(category='refuse', expect=DROP))))
        self.assertEqual(r['expect'], [])
        self.assertEqual(r['avoid'], [])

    def test_file_level_refusals(self):
        self.refused(b'{"schema": ', 'questions_not_json')
        self.refused(b'\xff\xfe{}', 'questions_not_utf8')
        self.refused(b'{"schema": "alfred.question-set.v1", "schema": "x", "questions": []}', 'duplicate_field')
        self.refused(encode([question()]), 'not_an_object')
        self.refused(encode(question_set(extra=1)), 'unknown_field')
        self.refused(encode(question_set(schema=DROP)), 'wrong_schema')
        self.refused(encode(question_set(schema='alfred.question-set.v2')), 'wrong_schema')
        self.refused(encode(question_set(schema=1)), 'wrong_schema')
        self.refused(encode(question_set(note=5)), 'wrong_type')
        self.refused(encode({'schema': 'alfred.question-set.v1'}), 'questions_not_list')
        self.refused(encode({'schema': 'alfred.question-set.v1', 'questions': {}}), 'questions_not_list')
        self.refused(encode({'schema': 'alfred.question-set.v1', 'questions': []}), 'no_questions')
        many = [question(id='q' + str(i)) for i in range(qs.MAX_QUESTIONS + 1)]
        self.refused(encode(question_set(*many)), 'too_many_questions')

    def test_question_level_refusals(self):
        cases = [
            ('not an object', 'question_not_object'),
            (question(colour='blue'), 'unknown_field'),
            (question(id=DROP), 'invalid_id'),
            (question(id=7), 'invalid_id'),
            (question(id=''), 'invalid_id'),
            (question(id='has space'), 'invalid_id'),
            (question(id='-leading'), 'invalid_id'),
            (question(id='x' * 65), 'invalid_id'),
            (question(category=DROP), 'invalid_category'),
            (question(category='opinion'), 'invalid_category'),
            (question(category=['fact']), 'invalid_category'),
            (question(question=DROP), 'wrong_type'),
            (question(question=42), 'wrong_type'),
            (question(question=''), 'empty_question'),
            (question(question='   '), 'empty_question'),
            (question(question='ab'), 'question_not_askable'),
            (question(question='Where\tis it?'), 'question_not_askable'),
            (question(question='depot ' * 101), 'question_not_askable'),
            (question(question=' '.join('word' + str(i) for i in range(33))), 'question_not_askable'),
            (question(expect=DROP), 'missing_expect'),
            (question(expect='places/grellmouth-depot.md'), 'wrong_type'),
            (question(expect=True), 'wrong_type'),
            (question(expect=[]), 'empty_expect'),
            (question(expect=[3]), 'invalid_path'),
            (question(expect=['/places/grellmouth-depot.md']), 'invalid_path'),
            (question(expect=['../places/grellmouth-depot.md']), 'invalid_path'),
            (question(expect=['places/./grellmouth-depot.md']), 'invalid_path'),
            (question(expect=['places//grellmouth-depot.md']), 'invalid_path'),
            (question(expect=['places\\grellmouth-depot.md']), 'invalid_path'),
            (question(expect=['C:/places/grellmouth-depot.md']), 'invalid_path'),
            (question(expect=['places/grellmouth-depot.txt']), 'invalid_path'),
            (question(expect=['places/grellmouth-depot']), 'invalid_path'),
            (question(expect=['']), 'invalid_path'),
            (question(expect=['places/a.md', 'places/a.md']), 'duplicate_path'),
            (question(expect=['n' + str(i) + '.md' for i in range(qs.MAX_PATHS + 1)]), 'too_many_paths'),
            (question(category='refuse', expect=['places/grellmouth-depot.md']), 'expect_on_refuse'),
            (question(category='refuse', expect=[]), 'expect_on_refuse'),
            (question(avoid='clients/x.md'), 'wrong_type'),
            (question(avoid=[None]), 'invalid_path'),
            (question(avoid=['b.md', 'b.md']), 'duplicate_path'),
            (question(avoid=['places/grellmouth-depot.md']), 'expect_avoid_overlap'),
            (question(note=['x']), 'wrong_type'),
            (question(note='x' * (qs.MAX_NOTE + 1)), 'note_too_long'),
        ]
        for value, code in cases:
            with self.subTest(code=code, value=str(value)[:60]):
                self.refused(question_set(value), code)

    def test_duplicate_ids_are_refused_and_named_by_position(self):
        message = self.refused(question_set(question(), question(id='q2'), question()), 'duplicate_id')
        self.assertIn('question 3', message)
        self.assertIn('q1', message)

    def test_refusal_messages_never_repeat_question_text(self):
        secret = 'Where does the invented courier Ilsa Morrow keep the spare key?'
        for value, code in ((question(question=secret, expect=[]), 'empty_expect'),
                            (question(question=secret, colour=1), 'unknown_field'),
                            (question(question=secret, category='opinion'), 'invalid_category'),
                            (question(question=secret + ' x' * 300), 'question_not_askable')):
            message = self.refused(question_set(value), code)
            self.assertNotIn(secret, message)
            self.assertNotIn('Ilsa', message)

    def test_unknown_field_names_are_quoted_and_bounded(self):
        message = self.refused(question_set(question(**{'x' * 300: 1})), 'unknown_field')
        self.assertLess(len(message), 200)

    def test_refuse_question_may_name_notes_to_avoid(self):
        [q] = qs.parse_question_set(encode(question_set(question(category='refuse', expect=DROP,
                                                                 avoid=['clients/x.md']))))
        self.assertEqual(q['avoid'], ['clients/x.md'])


class ValidateCommandTests(Scratch):
    def test_validate_prints_a_value_free_summary(self):
        status, out, err = call(['validate', str(QUESTIONS)])
        self.assertEqual(status, 0)
        self.assertEqual(err, '')
        self.assertEqual(out, 'Valid alfred.question-set.v1 file with 12 questions:\n'
                              '  fact 3\n  connected 3\n  time 2\n  preference 2\n  refuse 2\n')
        for q in fixture_questions()['questions']:
            self.assertNotIn(q['question'], out)
            self.assertNotIn(q['id'], out)

    def test_validate_reports_one_line_errors(self):
        path = self.write_questions(question_set(question(), question()))
        status, out, err = call(['validate', str(path)])
        self.assertEqual(status, 1)
        self.assertEqual(out, '')
        self.assertEqual(err.count('\n'), 1)
        self.assertTrue(err.startswith('error (duplicate_id): '))
        status, _, err = call(['validate', str(self.tmp / 'missing.json')])
        self.assertEqual(status, 1)
        self.assertTrue(err.startswith('error (questions_unreadable): '))
        self.assertNotIn(str(self.tmp), err)

    def test_oversized_file_is_refused_before_parsing(self):
        path = self.tmp / 'big.json'
        path.write_bytes(b' ' * (qs.MAX_FILE_BYTES + 1))
        with self.assertRaises(qs.QuestionSetError) as caught:
            qs.load_question_set(path)
        self.assertEqual(caught.exception.code, 'questions_too_large')


class PathGuardTests(Scratch):
    def run_refused(self, argv, code):
        with mock.patch.object(qs, 'KnowledgeStore', side_effect=AssertionError('no store may be built')):
            status, out, err = call(argv)
        self.assertEqual(status, 1, err)
        self.assertEqual(out, '')
        self.assertEqual(err.count('\n'), 1, err)
        self.assertTrue(err.startswith('error (' + code + '): '), err)
        self.assertNotIn(str(ROOT), err)
        self.assertNotIn(str(self.tmp), err)

    def test_repository_paths_are_refused_without_synthetic(self):
        questions, vault = self.outside_copy()
        out = self.tmp / 'report.json'
        self.run_refused(['run', str(QUESTIONS), '--vault', str(vault), '--output', str(out)],
                         'questions_inside_repository')
        self.run_refused(['run', str(questions), '--vault', str(VAULT), '--output', str(out)],
                         'vault_inside_repository')
        inside = ROOT / 'question-set-report.json'
        self.run_refused(['run', str(questions), '--vault', str(vault), '--output', str(inside)],
                         'output_inside_repository')
        self.assertFalse(inside.exists())
        self.assertFalse(out.exists())

    def test_a_link_from_outside_into_the_repository_is_still_refused(self):
        _, vault = self.outside_copy()
        link = self.tmp / 'linked.json'
        link.symlink_to(QUESTIONS)
        self.run_refused(['run', str(link), '--vault', str(vault), '--output', str(self.tmp / 'r.json')],
                         'questions_inside_repository')
        linked_vault = self.tmp / 'linked-vault'
        linked_vault.symlink_to(VAULT, target_is_directory=True)
        self.run_refused(['run', str(self.tmp / 'questions.json'), '--vault', str(linked_vault),
                          '--output', str(self.tmp / 'r.json')], 'vault_inside_repository')

    def test_output_may_not_replace_the_questions_or_sit_in_the_vault(self):
        questions, vault = self.outside_copy()
        before = questions.read_bytes()
        for synthetic in ([], ['--synthetic']):
            self.run_refused(['run', str(questions), '--vault', str(vault), '--output', str(questions)] + synthetic,
                             'output_is_questions')
            alias = self.tmp / 'alias.json'
            alias.unlink(missing_ok=True)
            alias.symlink_to(questions)
            self.run_refused(['run', str(questions), '--vault', str(vault), '--output', str(alias)] + synthetic,
                             'output_is_questions')
            hard = self.tmp / 'hard.json'
            hard.unlink(missing_ok=True)
            os.link(questions, hard)
            self.run_refused(['run', str(questions), '--vault', str(vault), '--output', str(hard)] + synthetic,
                             'output_is_questions')
            self.run_refused(['run', str(questions), '--vault', str(vault),
                              '--output', str(vault / 'report.json')] + synthetic, 'output_inside_vault')
            self.run_refused(['run', str(questions), '--vault', str(vault),
                              '--output', str(vault / 'people' / 'report.json')] + synthetic, 'output_inside_vault')
        self.assertEqual(questions.read_bytes(), before)
        self.assertFalse((vault / 'report.json').exists())
        # The fixture itself, with --synthetic: the vault still cannot receive the report.
        self.run_refused(['run', str(QUESTIONS), '--vault', str(VAULT), '--output', str(VAULT / 'report.json'),
                          '--synthetic'], 'output_inside_vault')
        self.run_refused(['run', str(QUESTIONS), '--vault', str(VAULT), '--output', str(QUESTIONS),
                          '--synthetic'], 'output_is_questions')

    def test_output_never_overwrites_something_that_is_not_a_report(self):
        questions, vault = self.outside_copy()
        precious = self.tmp / 'notes.json'
        precious.write_text('{"mine": true}\n')
        self.run_refused(['run', str(questions), '--vault', str(vault), '--output', str(precious)],
                         'output_not_a_report')
        self.assertEqual(precious.read_text(), '{"mine": true}\n')
        self.run_refused(['run', str(questions), '--vault', str(vault), '--output', str(self.tmp)],
                         'output_is_directory')
        self.run_refused(['run', str(questions), '--vault', str(vault),
                          '--output', str(self.tmp / 'absent' / 'r.json')], 'output_folder_missing')

    def test_missing_inputs_are_refused(self):
        questions, vault = self.outside_copy()
        out = str(self.tmp / 'r.json')
        self.run_refused(['run', str(self.tmp / 'nope.json'), '--vault', str(vault), '--output', out],
                         'questions_unreadable')
        self.run_refused(['run', str(questions), '--vault', str(self.tmp / 'nope'), '--output', out],
                         'vault_not_a_folder')
        self.run_refused(['run', str(questions), '--vault', str(questions), '--output', out],
                         'vault_not_a_folder')

    def test_invalid_questions_are_refused_before_any_store_is_built(self):
        _, vault = self.outside_copy()
        bad = self.write_questions(question_set(question(), question()), 'bad.json')
        self.run_refused(['run', str(bad), '--vault', str(vault), '--output', str(self.tmp / 'r.json')],
                         'duplicate_id')

    def test_the_same_files_outside_the_repository_run_without_synthetic(self):
        questions, vault = self.outside_copy()
        out = self.tmp / 'report.json'
        status, _, _ = call(['run', str(questions), '--vault', str(vault), '--output', str(out)])
        self.assertEqual(status, qs.EXIT_LEAK)
        report = json.loads(out.read_text())
        self.assertFalse(report['synthetic'])
        self.assertEqual(report['rankings']['keywords']['overall']['found'], 13)
        # Rerunning onto an earlier report is allowed.
        status, _, _ = call(['run', str(questions), '--vault', str(vault), '--output', str(out)])
        self.assertEqual(status, qs.EXIT_LEAK)

    def test_the_library_call_guards_its_inputs_too(self):
        questions, vault = self.outside_copy()
        for args, code in (((QUESTIONS, vault), 'questions_inside_repository'),
                           ((questions, VAULT), 'vault_inside_repository')):
            with self.assertRaises(qs.QuestionSetError) as caught:
                qs.run_question_set(*args, rankings=('keywords',))
            self.assertEqual(caught.exception.code, code)
        report = qs.run_question_set(questions, vault, rankings=('keywords',))
        self.assertFalse(report['synthetic'])
        with self.assertRaises(qs.QuestionSetError) as caught:
            qs.run_question_set(questions, vault, rankings=('bm25',))
        self.assertEqual(caught.exception.code, 'unsupported_ranking')

    def test_the_vault_is_only_read(self):
        questions, vault = self.outside_copy()

        def snapshot():
            return sorted((str(p.relative_to(vault)), p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                          for p in vault.rglob('*'))
        before = snapshot()
        status, _, _ = call(['run', str(questions), '--vault', str(vault), '--output', str(self.tmp / 'r.json')])
        self.assertEqual(status, qs.EXIT_LEAK)
        self.assertEqual(snapshot(), before)

    def test_an_empty_vault_is_refused(self):
        questions, _ = self.outside_copy()
        empty = self.tmp / 'empty'
        empty.mkdir()
        status, _, err = call(['run', str(questions), '--vault', str(empty), '--output', str(self.tmp / 'r.json')])
        self.assertEqual(status, 1)
        self.assertTrue(err.startswith('error (vault_empty): '))
        self.assertFalse((self.tmp / 'r.json').exists())


KEYWORDS_OVERALL = {'questions': 12, 'expected': 14, 'found': 13, 'recall': 0.9286, 'complete': 9,
                    'refuse_questions': 2, 'refused': 1, 'leaks': 1, 'leaked_notes': 2, 'passed': 9,
                    'sources': 51, 'excerpt_words': 1311}
FTS5_OVERALL = {'questions': 12, 'expected': 14, 'found': 14, 'recall': 1.0, 'complete': 10,
                'refuse_questions': 2, 'refused': 1, 'leaks': 1, 'leaked_notes': 2, 'passed': 10,
                'sources': 50, 'excerpt_words': 1293}


def bucket(questions, expected, found, complete, refuse, refused, leaks, leaked, passed, sources, words):
    recall = round(found / expected, 4) if expected else None
    return {'questions': questions, 'expected': expected, 'found': found, 'recall': recall, 'complete': complete,
            'refuse_questions': refuse, 'refused': refused, 'leaks': leaks, 'leaked_notes': leaked,
            'passed': passed, 'sources': sources, 'excerpt_words': words}


KEYWORDS_CATEGORIES = {
    'fact': bucket(3, 3, 3, 3, 0, 0, 1, 2, 2, 14, 292),
    'connected': bucket(3, 6, 5, 2, 0, 0, 0, 0, 2, 15, 452),
    'time': bucket(2, 3, 3, 2, 0, 0, 0, 0, 2, 10, 210),
    'preference': bucket(2, 2, 2, 2, 0, 0, 0, 0, 2, 8, 222),
    'refuse': bucket(2, 0, 0, 0, 2, 1, 0, 0, 1, 4, 135),
}
FTS5_CATEGORIES = {
    'fact': bucket(3, 3, 3, 3, 0, 0, 1, 2, 2, 14, 292),
    'connected': bucket(3, 6, 6, 3, 0, 0, 0, 0, 3, 15, 448),
    'time': bucket(2, 3, 3, 2, 0, 0, 0, 0, 2, 10, 228),
    'preference': bucket(2, 2, 2, 2, 0, 0, 0, 0, 2, 7, 190),
    'refuse': bucket(2, 0, 0, 0, 2, 1, 0, 0, 1, 4, 135),
}
# id: (found, expected, sources, excerpt words) under keywords, then under fts5.
PER_QUESTION = {
    'fact-depot-hours': ((1, 1, 5, 127), (1, 1, 5, 127)),
    'fact-orrin-renewal': ((1, 1, 4, 66), (1, 1, 4, 66)),
    'fact-scanner-lead-time': ((1, 1, 5, 99), (1, 1, 5, 99)),
    'connected-heron-supplier': ((2, 2, 5, 146), (2, 2, 5, 165)),
    'connected-heron-lead': ((2, 2, 5, 158), (2, 2, 5, 158)),
    'connected-pilot-count': ((1, 2, 5, 148), (2, 2, 5, 125)),
    'time-budget-change': ((2, 2, 5, 126), (2, 2, 5, 126)),
    'time-shipment-date': ((1, 1, 5, 84), (1, 1, 5, 102)),
    'preference-weekly-review': ((1, 1, 5, 135), (1, 1, 5, 135)),
    'preference-running-shoes': ((1, 1, 3, 87), (1, 1, 2, 55)),
    'refuse-telescope': ((0, 0, 0, 0), (0, 0, 0, 0)),
    'refuse-quarrow-office': ((0, 0, 4, 135), (0, 0, 4, 135)),
}


class FixtureRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rankings = ('keywords', 'fts5') if FTS5 else ('keywords',)
        cls.report = qs.run_question_set(QUESTIONS, VAULT, rankings=rankings, synthetic=True)
        cls.text = qs.render_report(cls.report)
        cls.by_id = {r: {q['id']: q for q in v['questions']} for r, v in cls.report['rankings'].items()}

    def test_report_frame(self):
        r = self.report
        self.assertEqual(r['schema'], 'alfred.question-set-report.v1')
        self.assertEqual(r['question_set_schema'], 'alfred.question-set.v1')
        self.assertEqual(r['vault'], {'status': 'ready', 'notes': 15, 'issues': {}, 'paths_not_in_vault': 0})
        self.assertEqual(r['questions'], {'total': 12, 'categories': {'fact': 3, 'connected': 3, 'time': 2,
                                                                      'preference': 2, 'refuse': 2}})
        self.assertFalse(r['question_text_included'])
        self.assertTrue(r['synthetic'])
        self.assertEqual(r['limits'], {'sources': 5, 'excerpt_characters': 6000})
        self.assertEqual(r['environment']['fts5_available'], FTS5)
        self.assertEqual(list(r['rankings']), ['keywords', 'fts5'] if FTS5 else ['keywords'])
        self.assertTrue(self.text.endswith('}\n'))
        self.assertEqual(json.loads(self.text), r)

    def test_keywords_scores_are_pinned(self):
        ranking = self.report['rankings']['keywords']
        self.assertEqual(ranking['overall'], KEYWORDS_OVERALL)
        self.assertEqual(ranking['categories'], KEYWORDS_CATEGORIES)
        self.check_questions('keywords', 0)

    @unittest.skipUnless(FTS5, 'this SQLite build has no FTS5')
    def test_fts5_scores_are_pinned(self):
        ranking = self.report['rankings']['fts5']
        self.assertEqual(ranking['overall'], FTS5_OVERALL)
        self.assertEqual(ranking['categories'], FTS5_CATEGORIES)
        self.check_questions('fts5', 1)

    def check_questions(self, ranking, column):
        entries = self.report['rankings'][ranking]['questions']
        self.assertEqual([q['id'] for q in entries], [q['id'] for q in fixture_questions()['questions']])
        for entry in entries:
            found, expected, sources, words = PER_QUESTION[entry['id']][column]
            with self.subTest(ranking=ranking, id=entry['id']):
                self.assertEqual((entry['found'], entry['expected'], entry['sources'], entry['excerpt_words']),
                                 (found, expected, sources, words))
                self.assertEqual(len(entry['returned']), sources)
                self.assertEqual(entry['not_in_vault'], [])
                self.assertEqual(entry['recall'], round(found / expected, 4) if expected else None)

    def test_the_keyword_miss_names_the_missing_note(self):
        entry = self.by_id['keywords']['connected-pilot-count']
        self.assertEqual(entry['missed'], ['people/nell-vantrick.md'])
        self.assertEqual(entry['returned'], ['daily/2026-05-14.md', 'projects/heron.md',
                                             'clients/orrin-textiles/account.md', 'clients/orrin-textiles/renewal.md',
                                             'meetings/2026-03-heron-review.md'])
        self.assertFalse(entry['passed'])
        if FTS5:
            self.assertEqual(self.by_id['fts5']['connected-pilot-count']['missed'], [])
            self.assertTrue(self.by_id['fts5']['connected-pilot-count']['passed'])

    def test_the_deliberate_leak_is_caught(self):
        for ranking, entries in self.by_id.items():
            with self.subTest(ranking=ranking):
                leak = entries['fact-orrin-renewal']
                self.assertTrue(leak['leak'])
                self.assertEqual(leak['leaked'], PELLHAM)
                self.assertEqual(leak['found'], 1)
                self.assertFalse(leak['passed'])
                self.assertEqual(leak['returned'], ['clients/orrin-textiles/renewal.md',
                                                    'clients/orrin-textiles/account.md'] + PELLHAM[::-1])
                # An avoid list that is respected is not a leak.
                clean = entries['fact-depot-hours']
                self.assertFalse(clean['leak'])
                self.assertEqual(clean['leaked'], [])
                self.assertTrue(clean['passed'])
                self.assertEqual(sum(q['leak'] for q in entries.values()), 1)

    def test_refusal_scoring(self):
        for ranking, entries in self.by_id.items():
            with self.subTest(ranking=ranking):
                good, bad = entries['refuse-telescope'], entries['refuse-quarrow-office']
                self.assertTrue(good['returned_nothing'])
                self.assertTrue(good['passed'])
                self.assertEqual((good['returned'], good['recall'], good['expected']), ([], None, 0))
                self.assertFalse(bad['returned_nothing'])
                self.assertFalse(bad['passed'])
                self.assertEqual(bad['returned'], ['projects/heron.md', 'meetings/2026-03-heron-review.md',
                                                   'people/corin-dask.md', 'people/nell-vantrick.md'])

    def test_report_holds_no_question_text_note_text_or_machine_paths(self):
        data = fixture_questions()
        for q in data['questions']:
            self.assertNotIn(q['question'], self.text)
            if 'note' in q:
                self.assertNotIn(q['note'], self.text)
        self.assertNotIn(data['note'], self.text)
        for line in ('The loading bay is open from 6am to 2pm on weekdays.', 'Corin Dask runs Brindle Instruments',
                     'Plot 14', 'sixty days', '46,000'):
            self.assertNotIn(line, self.text)
        self.assertNotIn(str(ROOT), self.text)
        self.assertNotIn(tempfile.gettempdir() + '/', self.text)
        self.assertNotIn('"question"', self.text)
        for entries in self.by_id.values():
            for entry in entries.values():
                self.assertNotIn('question', entry)
                self.assertNotIn('note', entry)

    def test_include_text_adds_only_the_question_text(self):
        report = qs.run_question_set(QUESTIONS, VAULT, rankings=('keywords',), include_text=True, synthetic=True)
        self.assertTrue(report['question_text_included'])
        texts = {q['id']: q['question'] for q in fixture_questions()['questions']}
        for entry in report['rankings']['keywords']['questions']:
            self.assertEqual(entry.pop('question'), texts[entry['id']])
        report['question_text_included'] = False
        plain = {k: v for k, v in self.report.items()}
        plain['rankings'] = {'keywords': self.report['rankings']['keywords']}
        plain['environment'] = report['environment']
        self.assertEqual(report, plain)
        rendered = qs.render_report(qs.run_question_set(QUESTIONS, VAULT, rankings=('keywords',), include_text=True, synthetic=True))
        for q in fixture_questions()['questions']:
            self.assertNotIn(q.get('note', 'no note text'), rendered)


class CommandRunTests(Scratch):
    def run_fixture(self, *extra, name='report.json'):
        out = self.tmp / name
        status, stdout, stderr = call(['run', str(QUESTIONS), '--vault', str(VAULT), '--output', str(out),
                                       '--synthetic'] + list(extra))
        return status, stdout, stderr, out

    def test_run_writes_the_report_and_reports_the_leak_loudly(self):
        status, out, err, path = self.run_fixture('--ranking', 'keywords')
        self.assertEqual(status, qs.EXIT_LEAK)
        self.assertEqual(out, 'Report written for 12 questions (vault: 15 notes, status ready).\n'
                              'keywords: recall 0.9286 (13 of 14 expected notes), complete 9/10, refused 1/2, '
                              'leaks 1, passed 9/12, excerpt words 1311\n')
        self.assertEqual(err, 'LEAK: fact-orrin-renewal brought up 2 notes it must avoid (keywords).\n')
        report = json.loads(path.read_text())
        self.assertTrue(report['synthetic'])
        self.assertEqual(list(report['rankings']), ['keywords'])
        self.assertEqual(list(self.tmp.iterdir()), [path], 'no temporary file is left beside the report')

    @unittest.skipUnless(FTS5, 'this SQLite build has no FTS5')
    def test_both_rankings_and_the_default(self):
        status, out, err, path = self.run_fixture('--ranking', 'both')
        self.assertEqual(status, qs.EXIT_LEAK)
        self.assertEqual(out.splitlines()[1:], [
            'keywords: recall 0.9286 (13 of 14 expected notes), complete 9/10, refused 1/2, leaks 1, passed 9/12, '
            'excerpt words 1311',
            'fts5: recall 1.0 (14 of 14 expected notes), complete 10/10, refused 1/2, leaks 1, passed 10/12, '
            'excerpt words 1293'])
        self.assertEqual(err.splitlines(), ['LEAK: fact-orrin-renewal brought up 2 notes it must avoid (keywords).',
                                            'LEAK: fact-orrin-renewal brought up 2 notes it must avoid (fts5).'])
        self.assertEqual(list(json.loads(path.read_text())['rankings']), ['keywords', 'fts5'])
        status, _, _, default = self.run_fixture(name='default.json')
        self.assertEqual(list(json.loads(default.read_text())['rankings']), ['keywords'])
        status, _, _, only = self.run_fixture('--ranking', 'fts5', name='fts5.json')
        self.assertEqual(json.loads(only.read_text())['rankings']['fts5']['overall'], FTS5_OVERALL)

    def test_two_runs_give_byte_identical_reports(self):
        ranking = 'both' if FTS5 else 'keywords'
        _, _, _, first = self.run_fixture('--ranking', ranking, name='first.json')
        _, _, _, second = self.run_fixture('--ranking', ranking, name='second.json')
        self.assertEqual(first.read_bytes(), second.read_bytes())
        _, _, _, third = self.run_fixture('--ranking', ranking, '--include-text', name='third.json')
        _, _, _, fourth = self.run_fixture('--ranking', ranking, '--include-text', name='fourth.json')
        self.assertEqual(third.read_bytes(), fourth.read_bytes())
        self.assertNotEqual(first.read_bytes(), third.read_bytes())

    def test_unavailable_fts5_is_a_clear_refusal(self):
        with mock.patch.object(qs, 'fts5_available', return_value=False):
            for ranking in ('fts5', 'both'):
                status, out, err, path = self.run_fixture('--ranking', ranking)
                self.assertEqual(status, 1)
                self.assertTrue(err.startswith('error (fts5_unavailable): '))
                self.assertFalse(path.exists())
            status, _, _, path = self.run_fixture('--ranking', 'keywords')
            self.assertEqual(status, qs.EXIT_LEAK)
            self.assertFalse(json.loads(path.read_text())['environment']['fts5_available'])

    def test_paths_missing_from_the_vault_are_reported_not_hidden(self):
        questions, vault = self.outside_copy()
        data = fixture_questions()
        data['questions'][0]['expect'] = ['places/grellmouth-depot.md', 'places/typo.md']
        data['questions'][2]['avoid'] = ['people/nobody.md']
        questions.write_text(json.dumps(data))
        out = self.tmp / 'report.json'
        status, stdout, err = call(['run', str(questions), '--vault', str(vault), '--output', str(out)])
        self.assertEqual(status, qs.EXIT_LEAK)
        self.assertIn('warning: 2 note paths named in expect or avoid are not in the vault; '
                      'see not_in_vault in the report.\n', err)
        report = json.loads(out.read_text())
        self.assertEqual(report['vault']['paths_not_in_vault'], 2)
        entries = {q['id']: q for q in report['rankings']['keywords']['questions']}
        self.assertEqual(entries['fact-depot-hours']['not_in_vault'], ['places/typo.md'])
        self.assertEqual(entries['fact-depot-hours']['recall'], 0.5)
        self.assertEqual(entries['fact-scanner-lead-time']['not_in_vault'], ['people/nobody.md'])

    def test_vault_issues_are_counted_by_code_only(self):
        questions, vault = self.outside_copy()
        (vault / 'odd.md').write_text('---\nkind: spreadsheet\n---\n# Odd\n\nAn invented odd note.\n')
        out = self.tmp / 'report.json'
        status, stdout, _ = call(['run', str(questions), '--vault', str(vault), '--output', str(out)])
        self.assertEqual(status, qs.EXIT_LEAK)
        self.assertIn('(vault: 16 notes, status attention)', stdout)
        report = json.loads(out.read_text())
        self.assertEqual(report['vault']['issues'], {'unknown_kind_treated_as_note': 1})

    def test_no_network_is_used(self):
        def refuse(*args, **kwargs):
            raise AssertionError('network use attempted')
        with mock.patch.object(socket, 'socket', refuse), mock.patch.object(socket, 'create_connection', refuse), \
                mock.patch.object(socket, 'getaddrinfo', refuse):
            status, _, _, path = self.run_fixture('--ranking', 'both' if FTS5 else 'keywords')
        self.assertEqual(status, qs.EXIT_LEAK)
        self.assertTrue(path.exists())


class TemporaryStoreTests(Scratch):
    def setUp(self):
        super().setUp()
        self.store_root = self.tmp / 'store-root'
        self.store_root.mkdir()
        patcher = mock.patch.object(tempfile, 'tempdir', str(self.store_root))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_store_is_deleted_after_success(self):
        seen = []
        real = qs.KnowledgeStore

        def spy(path, **kwargs):
            seen.append(Path(path))
            return real(path, **kwargs)
        with mock.patch.object(qs, 'KnowledgeStore', spy):
            qs.run_question_set(QUESTIONS, VAULT, rankings=('keywords',), synthetic=True)
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0].is_relative_to(self.store_root))
        self.assertEqual(list(self.store_root.iterdir()), [])

    def test_store_is_deleted_when_retrieval_raises(self):
        with mock.patch.object(qs, 'retrieve', side_effect=RuntimeError('invented failure')):
            with self.assertRaises(RuntimeError):
                qs.run_question_set(QUESTIONS, VAULT, rankings=('keywords',), synthetic=True)
        self.assertEqual(list(self.store_root.iterdir()), [])

    def test_store_is_deleted_and_nothing_written_when_retrieval_refuses(self):
        out = self.tmp / 'report.json'
        with mock.patch.object(qs, 'retrieve', side_effect=Fault('question_too_complex')):
            status, stdout, err = call(['run', str(QUESTIONS), '--vault', str(VAULT), '--output', str(out),
                                        '--synthetic'])
        self.assertEqual(status, 1)
        self.assertEqual(stdout, '')
        self.assertEqual(err, 'error (retrieval_failed): question 1 (fact-depot-hours) could not be asked '
                              'under the keywords ranking (question_too_complex).\n')
        self.assertFalse(out.exists())
        self.assertEqual(list(self.store_root.iterdir()), [])

    def test_an_unreadable_vault_is_refused_and_the_store_deleted(self):
        unavailable = {'status': 'unavailable', 'errors': [{'code': 'vault_directory_capacity'}], 'notes': 0}
        with mock.patch.object(qs.MarkdownVault, 'scan', return_value=unavailable):
            with self.assertRaises(qs.QuestionSetError) as caught:
                qs.run_question_set(QUESTIONS, VAULT, rankings=('keywords',), synthetic=True)
        self.assertEqual(caught.exception.code, 'vault_unavailable')
        self.assertEqual(str(caught.exception), 'the vault could not be read (vault_directory_capacity).')
        self.assertEqual(list(self.store_root.iterdir()), [])

    def test_store_is_deleted_when_the_vault_scan_fails(self):
        with mock.patch.object(qs.MarkdownVault, 'scan', side_effect=OSError('invented')):
            with self.assertRaises(OSError):
                qs.run_question_set(QUESTIONS, VAULT, rankings=('keywords',), synthetic=True)
        self.assertEqual(list(self.store_root.iterdir()), [])


def make_report(rankings, notes=15):
    """A small hand-built report, independent of retrieval, for pinning compare output."""
    out = {}
    for name, entries in rankings.items():
        questions = []
        for qid, category, expected, found, leak, nothing, words in entries:
            passed = (nothing if category == 'refuse' else found == expected) and not leak
            questions.append({'id': qid, 'category': category, 'expected': expected, 'found': found,
                              'recall': round(found / expected, 4) if expected else None, 'leak': leak,
                              'leaked': ['x.md'] if leak else [], 'returned_nothing': nothing,
                              'sources': 0 if nothing else 1, 'passed': passed, 'excerpt_words': words})
        out[name] = {'questions': questions}
    report = {'schema': 'alfred.question-set-report.v1', 'vault': {'notes': notes}, 'rankings': {}}
    for name, value in out.items():
        report['rankings'][name] = qs.summarise(value['questions']) | {'questions': value['questions']}
    return report


OLD = make_report({'keywords': [
    ('a', 'fact', 2, 1, False, False, 40), ('b', 'fact', 1, 1, True, False, 30),
    ('c', 'refuse', 0, 0, False, True, 0), ('d', 'time', 1, 0, False, False, 25)]})
NEW = make_report({'hybrid': [
    ('a', 'fact', 2, 2, False, False, 35), ('b', 'fact', 1, 1, False, False, 30),
    ('c', 'refuse', 0, 0, False, False, 12), ('e', 'preference', 1, 1, False, False, 9)]}, notes=16)


class CompareTests(Scratch):
    def save(self, report, name):
        path = self.tmp / name
        path.write_text(qs.render_report(report))
        return path

    def test_compare_output_is_pinned(self):
        old, new = self.save(OLD, 'old.json'), self.save(NEW, 'new.json')
        status, out, err = call(['compare', str(old), str(new)])
        self.assertEqual((status, err), (1, 'error (no_common_ranking): the reports share no ranking; name one '
                                            'from each with --old-ranking and --new-ranking.\n'))
        status, out, err = call(['compare', str(old), str(new), '--old-ranking', 'keywords',
                                 '--new-ranking', 'hybrid'])
        self.assertEqual((status, err), (0, ''))
        self.assertEqual(out.splitlines(), [
            'Comparing old keywords with new hybrid.',
            'Note: the two reports cover different questions, so totals are not like for like.',
            'vault notes: 15 -> 16',
            'overall: recall 0.5 -> 1.0 (+0.5), complete 1/3 -> 3/3, refused 1/1 -> 0/1, leaks 1 -> 0, '
            'passed 1/4 -> 3/4, excerpt words 95 -> 86 (-9)',
            'fact: recall 0.6667 -> 1.0 (+0.3333), complete 1/2 -> 2/2, leaks 1 -> 0, passed 0/2 -> 2/2, '
            'excerpt words 70 -> 65 (-5)',
            'time: recall 0.0 -> n/a, complete 0/1 -> 0/0, leaks 0 -> 0, passed 0/1 -> 0/0, excerpt words 25 -> 0 (-25)',
            'preference: recall n/a -> 1.0, complete 0/0 -> 1/1, leaks 0 -> 0, passed 0/0 -> 1/1, '
            'excerpt words 0 -> 9 (+9)',
            'refuse: refused 1/1 -> 0/1, leaks 0 -> 0, passed 1/1 -> 0/1, excerpt words 0 -> 12 (+12)',
            'changed questions:',
            '  a: recall 0.5 -> 1.0',
            '  b: leak gone',
            '  c: no longer refused',
            'only in old: d',
            'only in new: e',
        ])

    def test_same_ranking_names_are_paired_and_unchanged_reports_say_so(self):
        path = self.save(OLD, 'old.json')
        status, out, err = call(['compare', str(path), str(path)])
        self.assertEqual((status, err), (0, ''))
        self.assertEqual(out.splitlines()[0], 'Comparing old keywords with new keywords.')
        self.assertEqual(out.splitlines()[1], 'vault notes: 15 -> 15')
        self.assertIn('overall: recall 0.5 -> 0.5, complete 1/3 -> 1/3', out)
        self.assertTrue(out.endswith('changed questions: none\n'))

    def test_a_new_leak_and_a_new_refusal_are_named(self):
        old = make_report({'keywords': [('b', 'fact', 1, 1, False, False, 3), ('c', 'refuse', 0, 0, False, False, 4)]})
        new = make_report({'keywords': [('b', 'time', 1, 1, True, False, 3), ('c', 'refuse', 0, 0, False, True, 0)]})
        status, out, _ = call(['compare', str(self.save(old, 'o.json')), str(self.save(new, 'n.json'))])
        self.assertEqual(status, 0)
        self.assertIn('  b: category fact -> time; leak appeared\n  c: now refused\n', out)

    @unittest.skipUnless(FTS5, 'this SQLite build has no FTS5')
    def test_compare_the_two_rankings_of_the_fixture(self):
        _, _, _ = call(['run', str(QUESTIONS), '--vault', str(VAULT), '--output', str(self.tmp / 'r.json'),
                        '--synthetic', '--ranking', 'both'])
        path = str(self.tmp / 'r.json')
        status, out, err = call(['compare', path, path, '--old-ranking', 'keywords', '--new-ranking', 'fts5'])
        self.assertEqual((status, err), (0, ''))
        self.assertEqual(out.splitlines(), [
            'Comparing old keywords with new fts5.',
            'vault notes: 15 -> 15',
            'overall: recall 0.9286 -> 1.0 (+0.0714), complete 9/10 -> 10/10, refused 1/2 -> 1/2, leaks 1 -> 1, '
            'passed 9/12 -> 10/12, excerpt words 1311 -> 1293 (-18)',
            'fact: recall 1.0 -> 1.0, complete 3/3 -> 3/3, leaks 1 -> 1, passed 2/3 -> 2/3, excerpt words 292 -> 292',
            'connected: recall 0.8333 -> 1.0 (+0.1667), complete 2/3 -> 3/3, leaks 0 -> 0, passed 2/3 -> 3/3, '
            'excerpt words 452 -> 448 (-4)',
            'time: recall 1.0 -> 1.0, complete 2/2 -> 2/2, leaks 0 -> 0, passed 2/2 -> 2/2, excerpt words 210 -> 228 (+18)',
            'preference: recall 1.0 -> 1.0, complete 2/2 -> 2/2, leaks 0 -> 0, passed 2/2 -> 2/2, '
            'excerpt words 222 -> 190 (-32)',
            'refuse: refused 1/2 -> 1/2, leaks 0 -> 0, passed 1/2 -> 1/2, excerpt words 135 -> 135',
            'changed questions:',
            '  connected-pilot-count: recall 0.5 -> 1.0',
        ])
        for q in fixture_questions()['questions']:
            self.assertNotIn(q['question'], out)

    def test_compare_refusals(self):
        good = self.save(OLD, 'old.json')
        cases = [
            (self.tmp / 'absent.json', 'report_unreadable'),
            (self.write_questions(question_set(), 'questions.json'), 'not_a_report'),
            (self.write_questions([1, 2], 'list.json'), 'not_a_report'),
            (self.write_questions({'schema': 'alfred.question-set-report.v1', 'rankings': []}, 'm.json'),
             'report_malformed'),
            (self.write_questions({'schema': 'alfred.question-set-report.v1',
                                   'rankings': {'keywords': {'questions': [{'no': 'id'}]}}}, 'n.json'),
             'report_malformed'),
        ]
        broken = self.tmp / 'broken.json'
        broken.write_text('{')
        cases.append((broken, 'not_a_report'))
        for path, code in cases:
            with self.subTest(code=code, path=path.name):
                status, out, err = call(['compare', str(good), str(path)])
                self.assertEqual((status, out), (1, ''))
                self.assertTrue(err.startswith('error (' + code + '): '), err)
                self.assertEqual(err.count('\n'), 1)
        status, _, err = call(['compare', str(good), str(good), '--old-ranking', 'fts5'])
        self.assertEqual(status, 1)
        self.assertTrue(err.startswith('error (ranking_not_in_report): '))
        status, _, err = call(['compare', str(good), str(good), '--old-ranking', 'keywords',
                               '--new-ranking', 'hybrid'])
        self.assertEqual(status, 1)
        self.assertTrue(err.startswith('error (ranking_not_in_report): '), err)
        # Naming one side only pairs it with the same name on the other side.
        status, out, err = call(['compare', str(good), str(good), '--new-ranking', 'keywords'])
        self.assertEqual((status, err), (0, ''))
        self.assertTrue(out.startswith('Comparing old keywords with new keywords.\n'))


if __name__ == '__main__':
    unittest.main()
