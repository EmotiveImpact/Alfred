"""Plan item 1.5: Obsidian syntax read the way Obsidian reads it (MEM-001, M01).

A synthetic fixture vault (tests/fixtures/obsidian_vault) exercises frontmatter
aliases and tags, wikilinks with display text, headings, nested heading subpaths,
block IDs, embeds, callouts, inline and nested tags, comments and `.obsidian`.
It is copied to a temporary folder and read through the real scanner and SQLite
index. Conflict copies from tools not recognised by name are detected by content.
"""
from pathlib import Path
import shutil
import tempfile
import unittest

from alfred.grounded import retrieve
from alfred.knowledge import KnowledgeStore, MarkdownVault, parse_note, resolve_reference
from alfred.local import Fault
from alfred import sync_conflicts
from grant_helpers import grant_all

FIXTURE = Path(__file__).parent / 'fixtures' / 'obsidian_vault'


class Vault(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.vault = self.root / 'vault'
        shutil.copytree(FIXTURE, self.vault)
        self.store = KnowledgeStore(self.root / 'db', clock=lambda: 1000)
        self.owner = self.store.provision('work', 'owner', 'owner')
        self.source = self.store.provision('work', 'source', 'source')
        grant_all(self.store, self.owner)
        self.scanner = MarkdownVault(self.store, self.source, self.vault)

    def data(self):
        return self.store.knowledge(self.owner)

    def node(self, path):
        return next(n for n in self.data()['nodes'] if n['path'] == path)

    def line(self, path, text):
        """1-based line of the first line containing text, so spans are not hand-counted."""
        lines = (self.vault / path).read_text().splitlines()
        return next(i for i, l in enumerate(lines, 1) if text in l)


class FixtureVaultTests(Vault):
    def setUp(self):
        super().setUp(); self.health = self.scanner.scan()
        self.paths = {n['id']: n['path'] for n in self.data()['nodes']}

    def links(self, origin):
        return [(l['line'], self.paths[l['target']], l['relation'],
                 (l['anchor']['kind'], l['anchor']['name'], l['anchor']['start_line'], l['anchor']['end_line']) if l['anchor'] else None)
                for l in self.data()['links'] if self.paths[l['source']] == origin]

    def test_every_note_is_indexed_and_obsidian_settings_are_not(self):
        self.assertEqual(sorted(self.paths.values()), ['Archive/Old/Plan.md', 'Daily/2026-10-01.md', 'MAP.md',
                                                       'Notes/v1.2 release notes.md', 'People/Jo Example.md', 'Projects/Atlas.md'])
        self.assertFalse(any(p.startswith('.obsidian') for p in self.paths.values()))
        self.assertEqual(self.data()['issues'], [])
        # The only report is the deliberately deprecated singular property.
        self.assertEqual(self.health['errors'], [{'path': 'People/Jo Example.md', 'code': 'deprecated_obsidian_property_ignored'}])

    def test_frontmatter_aliases_and_tags_in_list_and_string_forms(self):
        atlas, jo = self.node('Projects/Atlas.md'), self.node('People/Jo Example.md')
        self.assertEqual(atlas['aliases'], ['Project A', 'Atlas programme'])
        self.assertEqual(jo['aliases'], ['Jo'])
        self.assertEqual(atlas['tags'], ['project', 'active', 'status/green', 'team/ops', 'risk'])
        self.assertEqual(jo['tags'], ['person', 'team/ops'])
        self.assertEqual(self.node('Daily/2026-10-01.md')['tags'], ['daily', 'journal/october'])

    def test_tags_in_code_comments_urls_and_numbers_are_not_tags(self):
        tags = self.node('Projects/Atlas.md')['tags']
        for absent in ('notatag', 'nottag', 'hiddentag', '42', 'fragment'):
            self.assertNotIn(absent, tags)

    def test_daily_note_links_resolve_with_aliases_anchors_and_embeds(self):
        daily, atlas = 'Daily/2026-10-01.md', 'Projects/Atlas.md'
        risks = ('heading', 'Risks', self.line(atlas, '## Risks'), self.line(atlas, '## Notes') - 1)
        expected = [
            (3, atlas, 'links_to', None), (3, atlas, 'links_to', None), (3, atlas, 'links_to', None),
            (4, atlas, 'links_to', risks),
            (4, atlas, 'links_to', ('heading', 'Milestones', self.line(atlas, '### Milestones'), self.line(atlas, '### Budget') - 1)),
            (5, atlas, 'links_to', ('block', 'summary', self.line(atlas, 'Atlas is a fictional'), self.line(atlas, '^summary'))),
            (5, atlas, 'links_to', ('block', 'first-step', self.line(atlas, '^first-step'), self.line(atlas, '^first-step'))),
            (6, atlas, 'links_to', ('block', 'quote-1', self.line(atlas, '> A quoted reminder'), self.line(atlas, 'It spans two lines'))),
            (7, atlas, 'embeds', ('block', 'budget-table', self.line(atlas, '| Item | Owner |'), self.line(atlas, '| Venue |'))),
            (8, atlas, 'embeds', risks),
            (9, 'People/Jo Example.md', 'embeds', None),
            (11, 'Archive/Old/Plan.md', 'links_to', None), (11, atlas, 'links_to', None),
            (12, 'Notes/v1.2 release notes.md', 'links_to', None),
            (13, atlas, 'links_to', risks),
            (14, daily, 'links_to', ('heading', 'Notes', self.line(daily, '## Notes'), 22)),
            (18, 'People/Jo Example.md', 'links_to', None),
        ]
        self.assertEqual(sorted(self.links(daily), key=str), sorted(expected, key=str))

    def test_attachment_embed_is_neither_a_link_nor_an_issue(self):
        self.assertFalse(any('diagram' in i['target'] for i in self.data()['issues']))
        self.assertNotIn(10, [line for line, *_ in self.links('Daily/2026-10-01.md')])

    def test_note_structure_shows_display_text_callouts_and_blocks(self):
        atlas = self.node('Projects/Atlas.md')
        structure = self.store.knowledge_note(self.owner, atlas['id'])['structure']
        self.assertTrue(structure['available'])
        self.assertEqual([(h['name'], h['level']) for h in structure['headings']],
                         [('Atlas', 1), ('Plan', 2), ('Milestones', 3), ('Budget', 3), ('Risks', 2), ('Notes', 2)])
        self.assertEqual([b['name'] for b in structure['blocks']], ['summary', 'first-step', 'budget-table', 'quote-1'])
        self.assertEqual([(c['type'], c['rendered_as'], c['title'], c['fold'], c['depth']) for c in structure['callouts']], [
            ('warning', 'warning', 'Schedule risk', 'none', 1), ('faq', 'question', 'Folded question', 'collapsed', 1),
            ('tip', 'tip', 'Nested tip', 'none', 2), ('custom', 'note', 'Unknown type', 'none', 1)])
        warning = structure['callouts'][0]
        self.assertEqual((warning['start_line'], warning['end_line']),
                         (self.line('Projects/Atlas.md', '[!warning]'), self.line('Projects/Atlas.md', 'holds the earlier version')))
        references = [(r['target'], r['display']) for r in structure['references']]
        # The escaped table pipe gives the same target and display as the plain form.
        self.assertEqual(references, [('Jo Example', 'Jo'), ('Jo', None), ('Jo Example', 'Jo'), ('Archive/Old/Plan', None)])

    def test_links_in_comments_and_code_are_not_followed(self):
        targets = {r['target'] for r in self.store.knowledge_note(self.owner, self.node('Projects/Atlas.md')['id'])['structure']['references']}
        self.assertTrue(targets.isdisjoint({'Hidden link', 'Not a link', 'Also not a link'}))

    def test_map_reaches_every_note_within_two_hops(self):
        health = self.data()['map_health']
        self.assertEqual(health['outside_two_hops'], [])

    def test_alias_search_finds_the_note(self):
        found = [n['path'] for n in self.store.knowledge(self.owner, 'programme')['results']]
        self.assertIn('Projects/Atlas.md', found)


class ParserTests(unittest.TestCase):
    def parse(self, body, path='n.md'):
        return parse_note(path, body.encode())

    def blocks(self, body):
        return [(a['name'], a['start_line'], a['end_line']) for a in self.parse(body)['anchors'] if a['kind'] == 'block']

    def test_frontmatter_tag_forms(self):
        self.assertEqual(self.parse('---\ntags: [a, "#b", c/d]\n---\n')['tags'], ['a', 'b', 'c/d'])
        self.assertEqual(self.parse('---\ntags: solo\n---\n')['tags'], ['solo'])
        self.assertEqual(self.parse('---\ntags:\n  - x\n  - y\n---\n#x #Z\n')['tags'], ['x', 'y', 'Z'])

    def test_inline_tag_rules(self):
        tags = self.parse('Start #one and #two/three, a#nope, #123 #1a #a-b_c #ünï #trail/\n')['tags']
        self.assertEqual(tags, ['one', 'two/three', '1a', 'a-b_c', 'ünï', 'trail'])
        self.assertEqual(self.parse('# Heading\n## Two\n')['tags'], [])

    def test_tag_capacity_is_reported_not_silent(self):
        parsed = self.parse(' '.join('#t%d' % i for i in range(80)) + '\n')
        self.assertEqual(len(parsed['tags']), 64)
        self.assertIn('note_tag_capacity_truncated', parsed['warnings'])

    def test_obsidian_comments_hide_links_and_tags(self):
        parsed = self.parse('Before %%[[Inline hidden]] #a%% after [[Shown]]\n%%\n[[Block hidden]] #b\n%%\n#c\n')
        self.assertEqual([r['target'] for r in parsed['refs']], ['Shown'])
        self.assertEqual(parsed['tags'], ['c'])
        with self.assertRaises(Fault) as caught:
            self.parse('Text %% never closed\n')
        self.assertEqual(caught.exception.code, 'unclosed_obsidian_comment')

    def test_display_text_for_wiki_escaped_and_markdown_links(self):
        parsed = self.parse('[[A|Shown]] [[B\\|Table]] [[C]] [label](D.md) ![[E.png|200]]\n')
        self.assertEqual([r['target'] for r in parsed['refs']], ['A', 'B', 'C', 'E.png', 'D.md'])
        self.assertEqual(parsed['link_text'], ['Shown', 'Table', None, '200', 'label'])
        self.assertEqual([r['relation'] for r in parsed['refs']], ['links_to'] * 3 + ['embeds', 'links_to'])

    def test_callout_forms(self):
        parsed = self.parse('> [!NOTE]\n> body\n\n> [!tip]+ Open\n> x\nafter\n\n>[!Summary] Close\n')
        self.assertEqual([(c['type'], c['rendered_as'], c['title'], c['fold'], c['start_line'], c['end_line']) for c in parsed['callouts']],
                         [('note', 'note', 'Note', 'none', 1, 2), ('tip', 'tip', 'Open', 'expanded', 4, 5),
                          ('summary', 'abstract', 'Close', 'none', 8, 8)])
        self.assertEqual(self.parse('Not > [!note] a callout\n')['callouts'], [])

    def test_block_id_spans(self):
        self.assertEqual(self.blocks('One\nTwo ^para\n'), [('para', 1, 2)])
        self.assertEqual(self.blocks('- a\n- b ^item\n'), [('item', 2, 2)])
        self.assertEqual(self.blocks('> q1\n> q2\n\n^quote\n'), [('quote', 1, 2)])
        self.assertEqual(self.blocks('> q1\n^direct\n'), [('direct', 1, 1)])
        # Two blank lines or a heading above break the association, as in Obsidian.
        self.assertEqual(self.blocks('Para\n\n\n^far\n'), [])
        self.assertEqual(self.blocks('# Heading\n^under\n'), [])
        self.assertEqual(self.blocks('## H\nText ^after-heading\n'), [('after-heading', 2, 2)])
        self.assertEqual(self.blocks('```\ncode\n\nmore\n```\n^code\n'), [('code', 1, 5)])

    def test_m01_fixtures_keep_their_spans(self):
        anchors = self.parse('# Target\n## Section\nEvidence ^proof\n## Other\nOther content')['anchors']
        self.assertEqual([(a['kind'], a['name'], a['start_line'], a['end_line']) for a in anchors],
                         [('heading', 'Target', 1, 5), ('heading', 'Section', 2, 3), ('block', 'proof', 3, 3), ('heading', 'Other', 4, 5)])


class ResolutionTests(unittest.TestCase):
    def notes(self, *items):
        result = []
        for i, (path, body) in enumerate(items):
            parsed = parse_note(path, body.encode())
            result.append({'id': 'n%d' % i, 'path': path, 'aliases': parsed['aliases'], 'anchors': parsed['anchors']})
        return result

    def resolve(self, target, notes, syntax='wiki'):
        identity, state, anchor = resolve_reference('n0', target, syntax, notes)
        return state, anchor and anchor['start_line']

    def test_nested_heading_subpaths(self):
        notes = self.notes(('Origin.md', 'x'), ('N.md', '# N\n## Plan\n### Steps\n## Review\n### Steps\n'))
        self.assertEqual(self.resolve('N#Steps', notes), ('ambiguous_anchor', None))
        self.assertEqual(self.resolve('N#Plan#Steps', notes), ('resolved', 3))
        self.assertEqual(self.resolve('N#Review#Steps', notes), ('resolved', 5))
        self.assertEqual(self.resolve('N#N#Review#Steps', notes), ('resolved', 5))
        self.assertEqual(self.resolve('N#Review#Plan', notes), ('missing_anchor', None))
        self.assertEqual(self.resolve('N#Plan##Steps', notes), ('unsupported_anchor', None))
        self.assertEqual(self.resolve('N#^a#b', notes), ('unsupported_anchor', None))

    def test_partial_paths_and_dotted_names(self):
        notes = self.notes(('Origin.md', 'x'), ('a/sub/Note.md', '# A'), ('b/sub/Note.md', '# B'), ('c/Other.md', '# C'),
                           ('v1.2 notes.md', '# V'))
        self.assertEqual(self.resolve('c/Other', notes)[0], 'resolved')
        self.assertEqual(self.resolve('x/Other', notes)[0], 'missing')
        self.assertEqual(self.resolve('Other', notes)[0], 'resolved')
        self.assertEqual(self.resolve('sub/Note', notes)[0], 'ambiguous')
        self.assertEqual(self.resolve('a/sub/Note', notes)[0], 'resolved')
        self.assertEqual(self.resolve('v1.2 notes', notes)[0], 'resolved')
        self.assertEqual(self.resolve('report.pdf', notes)[0], 'attachment_not_indexed')
        self.assertEqual(self.resolve('scan.docx', notes)[0], 'attachment_not_indexed')
        self.assertEqual(self.resolve('v1.2 notes', notes, 'markdown')[0], 'attachment_not_indexed')

    def test_partial_path_suffix_must_match_whole_folder_names(self):
        notes = self.notes(('Origin.md', 'x'), ('deep/ersub/Note.md', '# A'))
        self.assertEqual(self.resolve('sub/Note', notes)[0], 'missing')


class ContentConflictTests(Vault):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.vault = self.root / 'vault'; self.vault.mkdir()
        self.store = KnowledgeStore(self.root / 'db', clock=lambda: 1000)
        self.owner = self.store.provision('work', 'owner', 'owner')
        self.source = self.store.provision('work', 'source', 'source')
        grant_all(self.store, self.owner)
        self.scanner = MarkdownVault(self.store, self.source, self.vault)
        (self.vault / 'Atlas.md').write_text('# Atlas\nAtlas launches in spring.\n')

    def test_same_content_under_an_extended_name_is_a_conflict_copy(self):
        (self.vault / 'Atlas 2.md').write_text('# Atlas\nAtlas launches in spring.\n')
        (self.vault / 'Atlas (laptop).md').write_text('# Atlas\nAtlas launches in spring.\n')
        health = self.scanner.scan(); data = self.data()
        self.assertEqual([n['path'] for n in data['nodes']], ['Atlas.md'])
        atlas = data['nodes'][0]['id']
        conflicts = {c['path']: c for c in data['sync_conflicts']}
        self.assertEqual(set(conflicts), {'Atlas 2.md', 'Atlas (laptop).md'})
        for c in conflicts.values():
            self.assertEqual((c['original'], c['state'], c['tool'], c['detected_by']), (atlas, 'linked', 'unrecognised_same_content', 'content_hash'))
        self.assertIn({'path': 'Atlas 2.md', 'code': 'sync_conflict_copy', 'original_path': 'Atlas.md', 'detected_by': 'content_hash'}, health['errors'])
        evidence = retrieve(self.store, self.owner, 'Atlas launches spring')['evidence']
        self.assertEqual({e['path'] for e in evidence}, {'Atlas.md'})

    def test_editing_the_copy_makes_it_an_ordinary_note_and_clears_the_conflict(self):
        (self.vault / 'Atlas 2.md').write_text('# Atlas\nAtlas launches in spring.\n')
        self.scanner.scan()
        (self.vault / 'Atlas 2.md').write_text('# Atlas\nAtlas launches in summer.\n')
        self.scanner.scan()
        data = self.data()
        self.assertEqual(sorted(n['path'] for n in data['nodes']), ['Atlas 2.md', 'Atlas.md'])
        self.assertEqual(data['sync_conflicts'], [])

    def test_identical_content_alone_is_not_enough(self):
        for name in ('Beta.md', 'Plan Atlas.md', 'sub/Atlas 2.md'):
            (self.vault / name).parent.mkdir(exist_ok=True)
            (self.vault / name).write_text('# Atlas\nAtlas launches in spring.\n')
        (self.vault / 'Untitled.md').write_text('\n')
        (self.vault / 'Untitled 1.md').write_text('\n')
        self.scanner.scan(); data = self.data()
        self.assertEqual(data['sync_conflicts'], [])
        self.assertEqual(len(data['nodes']), 6)

    def test_named_conflict_takes_precedence_over_content(self):
        (self.vault / 'Atlas.sync-conflict-20261002-101500-ABCDEFG.md').write_text('# Atlas\nAtlas launches in spring.\n')
        self.scanner.scan()
        [conflict] = self.data()['sync_conflicts']
        self.assertEqual((conflict['tool'], conflict['detected_by']), ('syncthing', 'name'))

    def test_forged_content_conflicts_are_rejected_before_storage(self):
        forged = {'path': 'Atlas 2.md', 'original_path': 'Atlas.md', 'tool': sync_conflicts.CONTENT_TOOL, 'markers': 0,
                  'original_present': True, 'sha256': '0' * 64}
        with self.assertRaises(Fault):
            sync_conflicts.checked([forged], {'atlas.md'}, {'atlas.md': '1' * 64})
        for over in ({'path': 'Other.md'}, {'markers': 1}, {'original_present': False}):
            with self.assertRaises(Fault, msg=over):
                sync_conflicts.checked([forged | {'sha256': '1' * 64} | over], {'atlas.md'}, {'atlas.md': '1' * 64})
        self.assertEqual(sync_conflicts.checked([forged | {'sha256': '1' * 64}], {'atlas.md'}, {'atlas.md': '1' * 64})[0]['tool'],
                         sync_conflicts.CONTENT_TOOL)


if __name__ == '__main__':
    unittest.main()
