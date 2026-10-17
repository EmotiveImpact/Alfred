import ast
import copy
import hashlib
import json
import math
import os
import pickle
import random
import subprocess
import sys
import time
import unittest
from fractions import Fraction
from pathlib import Path
from alfred import semantic
from alfred.local import Fault
from alfred.semantic import (HashingEmbedder, Index, MAX_K, best_per_note, blend, passage_text, passages)

ROOT = Path(__file__).resolve().parents[1]


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class Fixed:
    """A test embedder with hand-written unit vectors, keyed by the exact input text."""
    name, dimensions = 'fixed-test', 2

    def __init__(self, vectors, fail=False):
        self.vectors, self.fail, self.calls = vectors, fail, []

    def embed(self, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise RuntimeError('model unavailable')
        return [self.vectors[t] for t in texts]


class PassageTests(unittest.TestCase):
    def slices(self, text, result):
        for i, p in enumerate(result):
            self.assertEqual(text[p['start']:p['end']], p['text'])
            self.assertEqual(p['sha256'], sha(p['text']))
            self.assertEqual(p['index'], i)
            self.assertEqual(p['text'], p['text'].strip())
        return result

    def test_headings_and_paragraphs(self):
        text = '# Plan\n\nFirst paragraph.\n\nSecond paragraph.\n\n## Risks\n\nSupplier late.\n'
        result = self.slices(text, passages('n1', text))
        self.assertEqual([(p['start'], p['end'], p['start_line'], p['end_line'], p['heading_path'], p['text']) for p in result],
                         [(8, 43, 3, 5, ['Plan'], 'First paragraph.\n\nSecond paragraph.'),
                          (55, 69, 9, 9, ['Plan', 'Risks'], 'Supplier late.')])
        self.assertEqual(set(result[0]), {'note_id', 'index', 'start', 'end', 'start_line', 'end_line',
                                          'heading_path', 'text', 'sha256'})
        self.assertEqual(result[0]['note_id'], 'n1')
        self.assertEqual(result[1]['sha256'], hashlib.sha256(b'Supplier late.').hexdigest())

    def test_heading_levels_closing_hashes_and_non_headings(self):
        text = ('Lead in.\n# A\n## B ##\n### C\ntext c\n## D\ntext d\n# E\n#NoSpace stays text\n'
                '####### seven is text\n    # indented is text\n\ttabbed # text\n')
        result = self.slices(text, passages('n1', text))
        self.assertEqual([(p['heading_path'], p['text']) for p in result],
                         [([], 'Lead in.'), (['A', 'B', 'C'], 'text c'), (['A', 'D'], 'text d'),
                          (['E'], '#NoSpace stays text\n####### seven is text\n    # indented is text\n\ttabbed # text')])

    def test_front_matter_excluded(self):
        text = '---\ntitle: Atlas\ntags: [harbour]\n---\n# Atlas\nBody line.\n'
        result = self.slices(text, passages('n1', text))
        self.assertEqual([(p['start'], p['heading_path'], p['text'], p['start_line']) for p in result],
                         [(text.index('Body'), ['Atlas'], 'Body line.', 6)])
        self.assertFalse(any('harbour' in p['text'] for p in result))
        self.assertEqual(passages('n1', '---\ntitle: Only metadata\n---\n'), [])
        later = 'Intro\n\n---\n\nMore'
        self.assertEqual([p['text'] for p in self.slices(later, passages('n1', later))], ['Intro\n\n---\n\nMore'])

    def test_front_matter_refusals_match_the_note_scanner(self):
        for bad in ('---\ntitle: never closed\n\nBody\n', '---\n' + 'x: y\n' * 80 + '---\nBody\n'):
            with self.subTest(bad=bad[:20]), self.assertRaises(Fault) as caught:
                passages('n1', bad)
            self.assertEqual(caught.exception.code, 'unclosed_or_oversized_frontmatter')
        closed_at_limit = '---\n' + 'x: y\n' * 79 + '---\nBody\n'
        self.assertEqual([p['text'] for p in passages('n1', closed_at_limit)], ['Body'])

    def test_fence_kept_whole_and_headings_inside_ignored(self):
        fence = '```python\n# not a heading\nx = 1\n\nmore = 2\n```'
        text = '# A\n\nSome longer text here.\n\n' + fence + '\n\nAfter the code block ends.\n'
        result = self.slices(text, passages('n1', text, limit=64))
        self.assertEqual([(p['heading_path'], p['text']) for p in result],
                         [(['A'], 'Some longer text here.'), (['A'], fence), (['A'], 'After the code block ends.')])
        packed = self.slices(text, passages('n1', text, limit=200))
        self.assertEqual([p['text'] for p in packed], ['Some longer text here.\n\n' + fence + '\n\nAfter the code block ends.'])

    def test_fence_markers(self):
        text = '~~~~\n## inside\n~~~\nstill inside\n~~~~\n## Out\nprose\n'
        result = self.slices(text, passages('n1', text))
        self.assertEqual([(p['heading_path'], p['text']) for p in result],
                         [([], '~~~~\n## inside\n~~~\nstill inside\n~~~~'), (['Out'], 'prose')])
        for bad in ('```\ncode\n', 'Text\n````\ncode\n```\n'):
            with self.subTest(bad=bad), self.assertRaises(Fault) as caught:
                passages('n1', bad)
            self.assertEqual(caught.exception.code, 'unclosed_code_fence')

    def test_long_fence_split_at_line_ends(self):
        body = ''.join(f'line {i:02} value\n' for i in range(12))
        text = '```\n' + body + '```\n'
        result = self.slices(text, passages('n1', text, limit=64))
        self.assertEqual([(p['start'], p['end']) for p in result], [(0, 59), (60, 115), (116, 175)])
        for p in result:
            self.assertLessEqual(p['end'] - p['start'], 64)
            self.assertTrue(p['end'] == len(text) or text[p['end']] == '\n')
            self.assertTrue(p['start'] == 0 or text[p['start'] - 1] == '\n')
        self.assertEqual(''.join(p['text'] + '\n' for p in result), text)

    def test_long_paragraph_split_on_whitespace(self):
        words = [f'word{i}' for i in range(60)]
        text = '# Long\n' + ' '.join(words) + '\n'
        result = self.slices(text, passages('n1', text, limit=64))
        self.assertGreater(len(result), 5)
        for p in result:
            self.assertLessEqual(p['end'] - p['start'], 64)
            self.assertEqual(p['heading_path'], ['Long'])
        self.assertEqual(' '.join(p['text'] for p in result).split(), words)

    def test_unbroken_run_cut_hard_but_not_before_a_combining_mark(self):
        text = 'x' * 150
        self.assertEqual([len(p['text']) for p in self.slices(text, passages('n1', text, limit=64))], [64, 64, 22])
        accented = 'a' * 63 + 'é' + 'b' * 10
        self.assertEqual([p['text'] for p in self.slices(accented, passages('n1', accented, limit=64))],
                         ['a' * 63, 'é' + 'b' * 10])

    def test_crlf(self):
        text = '# Plan\r\n\r\nFirst line.\r\nSecond line.\r\n\r\n## Next\r\nDone.\r\n'
        result = self.slices(text, passages('n1', text))
        self.assertEqual([(p['heading_path'], p['text'], p['start_line'], p['end_line']) for p in result],
                         [(['Plan'], 'First line.\r\nSecond line.', 3, 4), (['Plan', 'Next'], 'Done.', 7, 7)])
        fenced = '```\r\n# no\r\n```\r\n'
        self.assertEqual([p['text'] for p in self.slices(fenced, passages('n1', fenced))], ['```\r\n# no\r\n```'])

    def test_non_ascii_offsets_are_string_indices(self):
        text = '# Café\n\nNaïve résumé 日本語 🎉.\n'
        [p] = self.slices(text, passages('n1', text))
        self.assertEqual((p['start'], p['heading_path']), (8, ['Café']))
        self.assertEqual(len(text[:8].encode('utf-8')), 9)
        self.assertEqual(p['sha256'], hashlib.sha256('Naïve résumé 日本語 🎉.'.encode('utf-8')).hexdigest())

    def test_empty_and_wordless_notes(self):
        for text in ('', '   \n\n\t', '# Heading only\n## Another\n', '\n---\n\n***\n', '```\n```\n', '🎉 🎉\n'):
            with self.subTest(text=text):
                self.assertEqual(passages('n1', text), [])

    def test_sections_never_share_a_passage(self):
        text = 'a\n# H\nb\n'
        self.assertEqual([(p['heading_path'], p['text']) for p in passages('n1', text)], [([], 'a'), (['H'], 'b')])

    def test_identical_output_across_runs(self):
        text = '---\nkind: note\n---\n# Ops\n\nCheck the harbour budget.\n\n```\ncode\n```\n' + 'long ' * 300
        first = passages('n1', text)
        self.assertEqual(first, passages('n1', text))
        self.assertEqual(hashlib.sha256(json.dumps(first, sort_keys=True).encode()).hexdigest(),
                         hashlib.sha256(json.dumps(passages('n1', text), sort_keys=True).encode()).hexdigest())

    def test_refusals(self):
        for note_id in ('', '../x', 5, None, 'a' * 81):
            with self.subTest(note_id=note_id), self.assertRaises(Fault) as caught:
                passages(note_id, 'text')
            self.assertEqual(caught.exception.code, 'invalid_identifier')
        for text, code in ((b'bytes', 'note_text_required'), (None, 'note_text_required'), ('x' * 65537, 'note_too_large')):
            with self.subTest(code=code), self.assertRaises(Fault) as caught:
                passages('n1', text)
            self.assertEqual(caught.exception.code, code)
        for limit in (True, 63, 8001, 64.0, '100'):
            with self.subTest(limit=limit), self.assertRaises(Fault) as caught:
                passages('n1', 'text', limit=limit)
            self.assertEqual(caught.exception.code, 'invalid_passage_limit')
        self.assertEqual(len(passages('n1', 'x' * 65536, limit=8000)), 9)


class EmbedderTests(unittest.TestCase):
    def test_shape_name_and_normalisation(self):
        e = HashingEmbedder(64)
        self.assertEqual((e.name, e.dimensions), ('alfred-hashing-v1-d64', 64))
        self.assertEqual(HashingEmbedder().dimensions, 256)
        [v, empty, punctuation] = e.embed(['Harbour budget review', '', '... !!'])
        self.assertEqual(len(v), 64)
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in v)), 1.0, places=12)
        self.assertEqual(empty, [0.0] * 64)
        self.assertEqual(punctuation, [0.0] * 64)
        self.assertEqual(e.embed([]), [])

    def test_pinned_vector(self):
        v = HashingEmbedder(16).embed(['Budget'])[0]
        self.assertEqual([(i, round(x, 6)) for i, x in enumerate(v) if x], PINNED_BUDGET_16)

    def test_case_and_unicode_forms_fold_together(self):
        e = HashingEmbedder(64)
        self.assertEqual(e.embed(['Budget'])[0], e.embed(['BUDGET'])[0])
        self.assertEqual(e.embed(['ﬁle'])[0], e.embed(['file'])[0])
        self.assertEqual(e.embed(['café'])[0], e.embed(['café'])[0])

    def test_related_words_overlap(self):
        e = HashingEmbedder(256)
        a, b, c = e.embed(['budget', 'budgets', 'harbour'])
        self.assertGreater(math.sumprod(a, b), 0.3)
        self.assertGreater(math.sumprod(a, b), abs(math.sumprod(a, c)) + 0.2)

    def test_stable_across_processes(self):
        code = ('import hashlib,json;from alfred.semantic import HashingEmbedder,passages;'
                'print(hashlib.sha256(json.dumps([HashingEmbedder(128).embed(["Harbour budget, café 日本"]),'
                'passages("n1","# A\\nHarbour budget")]).encode()).hexdigest())')
        local = hashlib.sha256(json.dumps([HashingEmbedder(128).embed(['Harbour budget, café 日本']),
                                           passages('n1', '# A\nHarbour budget')]).encode()).hexdigest()
        for seed in ('1', '2'):
            env = {k: v for k, v in os.environ.items() if k != 'PYTHONHASHSEED'} | {'PYTHONHASHSEED': seed}
            out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
            self.assertEqual(out.stdout.strip(), local)

    def test_refusals(self):
        for d in (0, 15, 4097, True, 256.0, '256'):
            with self.subTest(d=d), self.assertRaises(Fault) as caught:
                HashingEmbedder(d)
            self.assertEqual(caught.exception.code, 'invalid_dimensions')
        for texts in ('a string', None, ['ok', 3], ('x' * 65537,)):
            with self.subTest(texts=str(texts)[:20]), self.assertRaises(Fault) as caught:
                HashingEmbedder(16).embed(texts)
            self.assertEqual(caught.exception.code, 'invalid_texts')


def note(text):
    return passages('n', text)


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.vectors = {'east': (1.0, 0.0), 'north east': (0.6, 0.8), 'north': (0.0, 1.0), 'west': (-1.0, 0.0),
                        'query east': (1.0, 0.0), 'still': (0.0, 0.0), 'H\n\neast': (1.0, 0.0), 'H\n\nwest': (-1.0, 0.0)}
        self.embedder = Fixed(self.vectors)
        self.index = Index(self.embedder, scope='personal')

    def add(self, index, note_id, revision, text):
        index.add(note_id, revision, passages(note_id, text))

    def test_hand_checked_cosine_and_order(self):
        for note_id, text in (('d', 'north east'), ('c', 'east'), ('b', 'north'), ('a', 'west')):
            self.add(self.index, note_id, 1, text)
        hits = self.index.search('query east', 10)
        self.assertEqual([(h['note_id'], h['score']) for h in hits], [('c', 1.0), ('d', 0.6), ('b', 0.0), ('a', -1.0)])
        self.assertEqual(set(hits[0]), {'scope', 'embedder', 'note_id', 'revision', 'index', 'start', 'end',
                                        'start_line', 'end_line', 'heading_path', 'sha256', 'score'})
        self.assertEqual((hits[0]['scope'], hits[0]['embedder'], hits[0]['revision'], hits[0]['sha256']),
                         ('personal', 'fixed-test', 1, sha('east')))
        self.assertEqual([h['note_id'] for h in self.index.search('query east', 2)], ['c', 'd'])
        self.assertEqual(self.embedder.calls[-1], ['query east'])

    def test_heading_path_is_embedded_with_the_passage(self):
        vectors = {'Risks\n\nnorth': (0.0, 1.0), 'query east': (1.0, 0.0)}
        index = Index(Fixed(vectors), scope='personal')
        self.add(index, 'n1', 1, '# Risks\nnorth')
        self.assertEqual(index.embedder.calls[0], ['Risks\n\nnorth'])
        self.assertEqual(index.search('query east', 1)[0]['heading_path'], ['Risks'])

    def test_stable_tie_breaking(self):
        self.add(self.index, 'b', 1, 'east\n\n# H\neast')
        self.add(self.index, 'a', 1, 'east')
        hits = self.index.search('query east', 5)
        self.assertEqual([(h['note_id'], h['start']) for h in hits], [('a', 0), ('b', 0), ('b', 10)])

    def test_zero_vectors_never_match(self):
        self.add(self.index, 'z', 1, 'still')
        self.add(self.index, 'c', 1, 'east')
        self.assertEqual(len(self.index), 2)
        self.assertEqual([h['note_id'] for h in self.index.search('query east', 5)], ['c'])
        real = Index(HashingEmbedder(64), scope='personal')
        self.add(real, 'n1', 1, 'harbour budget')
        self.assertEqual(real.search('?!', 5), [])

    def test_k_and_query_refusals(self):
        self.add(self.index, 'c', 1, 'east')
        self.assertEqual(MAX_K, 100)
        self.assertEqual(len(self.index.search('query east', MAX_K)), 1)
        for k in (0, -1, MAX_K + 1, True, 1.0, '3', None):
            with self.subTest(k=k), self.assertRaises(Fault) as caught:
                self.index.search('query east', k)
            self.assertEqual(caught.exception.code, 'invalid_k')
        for query, code in (('', 'query_required'), ('   ', 'query_required'), (None, 'query_required'),
                            (b'east', 'query_required'), ('x' * 2001, 'query_too_long')):
            with self.subTest(code=code), self.assertRaises(Fault) as caught:
                self.index.search(query, 1)
            self.assertEqual(caught.exception.code, code)

    def test_remove(self):
        self.add(self.index, 'c', 1, 'east\n\n# H\neast')
        self.add(self.index, 'd', 1, 'north east')
        self.assertEqual((len(self.index), 'c' in self.index), (3, True))
        self.assertEqual(self.index.remove('c'), 2)
        self.assertEqual(self.index.remove('c'), 0)
        self.assertEqual(('c' in self.index, len(self.index)), (False, 1))
        self.assertEqual([h['note_id'] for h in self.index.search('query east', 5)], ['d'])
        with self.assertRaises(Fault):
            self.index.remove('../c')
        self.add(self.index, 'c', 1, 'east')
        self.assertEqual(self.index.revision('c'), 1)

    def test_re_adding_replaces_the_old_revision(self):
        self.add(self.index, 'n1', 1, 'west\n\n# H\nwest')
        self.add(self.index, 'n1', 2, 'east')
        hits = self.index.search('query east', 5)
        self.assertEqual([(h['note_id'], h['revision'], h['score']) for h in hits], [('n1', 2, 1.0)])
        self.assertEqual((len(self.index), self.index.revision('n1')), (1, 2))
        self.add(self.index, 'n1', 2, 'east')
        self.assertEqual(len(self.index), 1)
        for revision, text, code in ((1, 'east', 'stale_revision'), (2, 'north', 'revision_conflict')):
            with self.subTest(code=code), self.assertRaises(Fault) as caught:
                self.add(self.index, 'n1', revision, text)
            self.assertEqual(caught.exception.code, code)
        self.index.add('n1', 3, [])
        self.assertEqual(('n1' in self.index, len(self.index), self.index.revision('n1')), (False, 0, None))

    def test_failed_add_leaves_the_index_unchanged(self):
        self.add(self.index, 'n1', 1, 'east')
        bad_vectors = ([(1.0,)], [(0.6, 0.6)], [(float('nan'), 0.0)], [(True, False)], [(1.0, 0.0), (1.0, 0.0)], 'xy', [None])
        for vectors in bad_vectors:
            class Bad(Fixed):
                def embed(self, texts, vectors=vectors):
                    return vectors
            index = Index(Bad({}), scope='personal')
            with self.subTest(vectors=vectors), self.assertRaises(Fault) as caught:
                index.add('n', 1, note('west'))
            self.assertEqual(caught.exception.code, 'invalid_embedding')
            self.assertEqual(len(index), 0)
        self.embedder.fail = True
        with self.assertRaises(RuntimeError):
            self.add(self.index, 'n1', 2, 'west')
        self.embedder.fail = False
        self.assertEqual([(h['revision'], h['score']) for h in self.index.search('query east', 5)], [(1, 1.0)])

    def test_passage_validation(self):
        good = passages('n1', 'east\n\nwest\n\n# H\nnorth', limit=64)
        cases = {'other note': [dict(good[0], note_id='n2')],
                 'tampered text': [dict(good[0], text='EAST')],
                 'tampered digest': [dict(good[0], sha256='0' * 64)],
                 'offsets': [dict(good[0], end=good[0]['end'] + 1)],
                 'missing key': [{k: v for k, v in good[0].items() if k != 'sha256'}],
                 'extra key': [dict(good[0], vector=[1.0, 0.0])],
                 'unsorted': [good[1], good[0]],
                 'duplicate': [good[0], dict(good[0], index=1)],
                 'index gap': [good[0], dict(good[1], index=5)],
                 'bad heading': [dict(good[1], heading_path='H')],
                 'bool offset': [dict(good[0], start=False)],
                 'not a list': good[0]}
        for label, value in cases.items():
            with self.subTest(label=label), self.assertRaises(Fault) as caught:
                self.index.add('n1', 1, value)
            self.assertEqual(caught.exception.code, 'invalid_passage')
        for note_id, revision, code in (('../n1', 1, 'invalid_identifier'), ('n1', 0, 'invalid_revision'),
                                        ('n1', True, 'invalid_revision'), ('n1', 2**53 + 1, 'invalid_revision')):
            with self.subTest(code=code), self.assertRaises(Fault) as caught:
                self.index.add(note_id, revision, [])
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(len(self.index), 0)

    def test_scope_walls(self):
        embedder = HashingEmbedder(64)
        personal, client = Index(embedder, scope='personal'), Index(embedder, scope='client-a')
        personal.add('n1', 1, passages('n1', 'Dentist appointment on Friday'))
        client.add('n1', 4, passages('n1', 'Quarterly invoice for the harbour contract'))
        client.add('n2', 1, passages('n2', 'Harbour contract renewal terms'))
        self.assertEqual({(h['scope'], h['note_id'], h['revision']) for h in personal.search('harbour invoice', 10)},
                         {('personal', 'n1', 1)})
        self.assertEqual({(h['scope'], h['note_id']) for h in client.search('dentist appointment', 10)},
                         {('client-a', 'n1'), ('client-a', 'n2')})
        self.assertEqual(personal.remove('n1'), 1)
        self.assertEqual((len(personal), len(client), client.revision('n1')), (0, 2, 4))
        self.assertEqual(Index(embedder, scope='personal').search('dentist', 10), [])
        for scope in ('', '../x', None, 7):
            with self.subTest(scope=scope), self.assertRaises(Fault):
                Index(embedder, scope=scope)
        with self.assertRaises(TypeError):
            Index(embedder)

    def test_embedder_validation(self):
        class Named:
            def __init__(self, name, dimensions): self.name, self.dimensions = name, dimensions
            def embed(self, texts): return []
        for name, dimensions in (('', 2), ('has space', 2), (None, 2), ('ok', 1), ('ok', 4097), ('ok', True), ('ok', 2.0)):
            with self.subTest(name=name, dimensions=dimensions), self.assertRaises(Fault) as caught:
                Index(Named(name, dimensions), scope='personal')
            self.assertEqual(caught.exception.code, 'invalid_embedder')
        with self.assertRaises(Fault):
            Index(object(), scope='personal')

    def test_memory_only(self):
        self.add(self.index, 'c', 1, 'east')
        for attempt in (pickle.dumps, copy.copy, copy.deepcopy):
            with self.subTest(attempt=attempt.__name__), self.assertRaises(TypeError):
                attempt(self.index)
        self.assertEqual(repr(self.index), "<Index scope='personal' embedder='fixed-test' passages=1>")

    def test_capacity(self):
        self.assertEqual(semantic.MAX_PASSAGES, 50000)
        original, semantic.MAX_PASSAGES = semantic.MAX_PASSAGES, 2
        try:
            self.add(self.index, 'c', 1, 'east\n\n# H\neast')
            with self.assertRaises(Fault) as caught:
                self.add(self.index, 'd', 1, 'north east')
            self.assertEqual(caught.exception.code, 'index_capacity')
            self.add(self.index, 'c', 2, 'east')
            self.add(self.index, 'd', 1, 'north east')
            self.assertEqual(len(self.index), 2)
        finally:
            semantic.MAX_PASSAGES = original

    def test_hits_are_copies(self):
        self.add(self.index, 'c', 1, '# H\neast')
        self.index.search('query east', 1)[0]['heading_path'].append('changed')
        self.assertEqual(self.index.search('query east', 1)[0]['heading_path'], ['H'])

    def test_passage_text_rechecks_the_note(self):
        text = '# H\neast'
        self.add(self.index, 'c', 3, text)
        [hit] = self.index.search('query east', 1)
        self.assertEqual(passage_text(hit, 3, text), 'east')
        for revision, current in ((4, text), (3, '# H\nEAST')):
            with self.subTest(revision=revision), self.assertRaises(Fault) as caught:
                passage_text(hit, revision, current)
            self.assertEqual((caught.exception.code, caught.exception.status), ('passage_changed', 409))

    def test_best_per_note(self):
        hits = [{'note_id': 'b'}, {'note_id': 'a'}, {'note_id': 'b'}, {'note_id': 'c'}]
        self.assertEqual(best_per_note(hits), ['b', 'a', 'c'])

    def test_two_thousand_passages_searched_well_within_a_second(self):
        rng = random.Random(7)
        words = ('harbour budget invoice supplier contract schedule review meeting risk crew engine survey '
                 'cargo permit insurance payroll audit dentist garden training travel lease tender').split()
        index = Index(HashingEmbedder(256), scope='personal')
        for n in range(200):
            text = '\n'.join(f'# Section {s}\n' + ' '.join(rng.choice(words) for _ in range(18)) for s in range(10))
            index.add(f'n{n:03}', 1, passages(f'n{n:03}', text))
        self.assertEqual(len(index), 2000)
        started = time.perf_counter()
        hits = index.search('supplier invoice for the harbour contract', 10)
        elapsed = time.perf_counter() - started
        self.assertEqual(len(hits), 10)
        self.assertLess(elapsed, 0.5)


class BlendTests(unittest.TestCase):
    def test_pinned_example(self):
        result = blend(['a', 'b', 'c'], ['c', 'd', 'a'])
        self.assertEqual([(r['id'], r['sources'], r['keyword_rank'], r['meaning_rank']) for r in result],
                         [('a', ['keyword', 'meaning'], 1, 3), ('c', ['keyword', 'meaning'], 3, 1),
                          ('b', ['keyword'], 2, None), ('d', ['meaning'], None, 2)])
        self.assertEqual([r['score'] for r in result],
                         [float(Fraction(1, 61) + Fraction(1, 63))] * 2 + [float(Fraction(1, 62))] * 2)
        self.assertEqual(set(result[0]), {'id', 'score', 'sources', 'keyword_rank', 'meaning_rank'})

    def test_both_lists_beat_one_and_k_changes_weight(self):
        self.assertEqual([r['id'] for r in blend(['x', 'y'], ['y'])], ['y', 'x'])
        self.assertEqual([r['id'] for r in blend(['p', 'q', 'r'], ['r'], k=1)], ['r', 'p', 'q'])
        self.assertEqual(blend(['p'], [], k=1)[0]['score'], 0.5)

    def test_one_or_no_lists(self):
        self.assertEqual(blend([], []), [])
        self.assertEqual([(r['id'], r['sources']) for r in blend((), ('m1', 'm2'))], [('m1', ['meaning']), ('m2', ['meaning'])])

    def test_refusals(self):
        for keyword, meaning, k, code in ((['a', 'a'], [], 60, 'duplicate_ranked_id'),
                                          ([], ['b', 'c', 'b'], 60, 'duplicate_ranked_id'),
                                          ('ab', [], 60, 'invalid_ranked_list'), ([], None, 60, 'invalid_ranked_list'),
                                          ({'a'}, [], 60, 'invalid_ranked_list'),
                                          ([''], [], 60, 'invalid_ranked_id'), ([3], [], 60, 'invalid_ranked_id'),
                                          (['x' * 201], [], 60, 'invalid_ranked_id'),
                                          ([str(i) for i in range(1001)], [], 60, 'ranked_list_too_long'),
                                          (['a'], [], 0, 'invalid_rrf_k'), (['a'], [], True, 'invalid_rrf_k'),
                                          (['a'], [], 60.0, 'invalid_rrf_k'), (['a'], [], 1001, 'invalid_rrf_k')):
            with self.subTest(code=code, k=k), self.assertRaises(Fault) as caught:
                blend(keyword, meaning, k=k)
            self.assertEqual(caught.exception.code, code)


class BoundaryTests(unittest.TestCase):
    def test_module_has_no_disk_network_or_model_access(self):
        tree = ast.parse((ROOT / 'alfred' / 'semantic.py').read_text(encoding='utf-8'))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split('.')[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add('.' * node.level + (node.module or ''))
        self.assertLessEqual(imported, {'__future__', 'bisect', 'fractions', 'functools', 'hashlib', 'heapq', 'math',
                                        're', 'typing', 'unicodedata', '.local'})
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        self.assertFalse(names & {'open', 'exec', 'eval', '__import__', 'compile', 'breakpoint'})


# 'budget': the word slot holds 1/sqrt(2); six trigram slots hold (1/sqrt(6))/sqrt(2) each.
PINNED_BUDGET_16 = [(4, 0.288675), (6, -0.288675), (7, -0.288675), (8, 0.288675), (9, 0.288675), (11, -0.707107), (14, -0.288675)]

if __name__ == '__main__':
    unittest.main()
