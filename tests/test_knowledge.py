import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit
from alfred.knowledge import KnowledgeStore, MarkdownVault, parse_note, resolve_target
from alfred.knowledge_context import build_packet
from alfred.knowledge_http import knowledge_get
from alfred.local import Fault


class MarkdownTests(unittest.TestCase):
    def parse(self,body):return parse_note('a.md',body.encode())
    def test_title_heading(self):self.assertEqual(self.parse('# A note')['title'],'A note')
    def test_filename_fallback(self):self.assertEqual(self.parse('text')['title'],'a')
    def test_frontmatter(self):
        n=self.parse('---\ntitle: Title\ntype: project\ntags: [one, two]\naliases: [Alias]\n---\n# Other')
        self.assertEqual((n['title'],n['kind'],n['tags'],n['aliases']),('Title','project',['one','two'],['Alias']))
    def test_multiline_aliases(self):self.assertEqual(self.parse('---\naliases:\n- One\n  - Two\n---\ntext')['aliases'],['One','Two'])
    def test_duplicate_metadata(self):
        with self.assertRaises(Fault):self.parse('---\ntitle: A\ntitle: B\n---')
    def test_unclosed_frontmatter(self):
        with self.assertRaises(Fault):self.parse('---\ntitle: A')
    def test_unknown_type(self):self.assertEqual(self.parse('---\ntype: execute\n---')['kind'],'note')
    def test_exact_hash(self):self.assertEqual(self.parse('# Hi')['sha256'],hashlib.sha256(b'# Hi').hexdigest())
    def test_wiki_lines_aliases_fragments(self):
        n=self.parse('# A\n[[B#Heading|Title]]\n![[C]]')
        self.assertEqual(n['refs'],[{'target':'B#Heading','line':2,'syntax':'wiki','relation':'links_to'},{'target':'C','line':3,'syntax':'wiki','relation':'embeds'}])
    def test_markdown_reference(self):self.assertEqual(self.parse('[A](folder/A%20B.md)')['refs'][0]['target'],'folder/A%20B.md')
    def test_code_ignored(self):self.assertEqual(self.parse('```md\n[[Hidden]]\n```\n`[[Other]]`\n    [[Indented]]')['refs'],[])
    def test_comments_ignored(self):self.assertEqual(self.parse('<!-- [[A]]\n[[B]] -->\n[[C]]')['refs'][0]['target'],'C')
    def test_frontmatter_links_not_inferred(self):self.assertEqual(self.parse('---\nprompt: [[Run]]\n---\n# Note')['refs'],[])
    def test_controls(self):
        with self.assertRaises(Fault):self.parse('bad\x1b')
    def test_binary(self):
        with self.assertRaises(Fault):parse_note('x.md',b'\xff\x00')
    def test_size_cap(self):
        with self.assertRaises(Fault):parse_note('x.md',b'a'*65537)
    def test_link_cap(self):
        with self.assertRaises(Fault):self.parse('\n'.join('[[x]]' for _ in range(129)))
    def test_html_retained_as_text(self):self.assertIn('<script>',self.parse('<script>alert(1)</script>')['body'])


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.vault=self.root/'vault';self.vault.mkdir()
        self.clock=[1000];self.store=KnowledgeStore(self.root/'db.sqlite',clock=lambda:self.clock[0])
        self.owner=self.store.provision('work','owner','owner');self.reader=self.store.provision('work','reader','reader');self.source=self.store.provision('work','source','source')
        self.foreign=self.store.provision('other','foreign','owner')
        self.connector=MarkdownVault(self.store,self.source,self.vault)
    def tearDown(self):self.tmp.cleanup()
    def write(self,path,body):
        p=self.vault/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(body,encoding='utf-8');return p
    def scan(self):return self.connector.scan()
    def data(self,query='',kind=''):return self.store.knowledge(self.owner,query,kind)
    def seeded(self):
        self.write('MAP.md','# Map\n[[Area]]');self.write('Area.md','# Area\n[[Project]]');self.write('Project.md','---\ntype: project\n---\n# Project\nA monochrome opening.');self.scan()
    def test_index_persists(self):
        self.seeded();self.store=KnowledgeStore(self.root/'db.sqlite',clock=lambda:self.clock[0]);self.assertEqual(self.data()['counts']['notes'],3)
    def test_read_only_file_bytes(self):
        p=self.write('a.md','# Original\n[[Missing]]');raw=p.read_bytes();before=p.stat().st_mtime_ns;self.scan();self.data();self.assertEqual((p.read_bytes(),p.stat().st_mtime_ns),(raw,before))
    def test_keyword_search(self):self.seeded();self.assertEqual([r['title'] for r in self.data('monochrome')['results']],['Project'])
    def test_type_filter(self):self.seeded();self.assertEqual(len(self.data(kind='project')['results']),1)
    def test_reader_allowed(self):self.seeded();self.assertEqual(self.store.knowledge(self.reader)['counts']['notes'],3)
    def test_cross_scope_empty(self):self.seeded();self.assertEqual(self.store.knowledge(self.foreign)['nodes'],[])
    def test_cross_scope_note_denied(self):
        self.seeded();identity=self.data()['nodes'][0]['id']
        with self.assertRaises(Fault):self.store.knowledge_note(self.foreign,identity)
    def test_source_cannot_read(self):
        self.seeded()
        with self.assertRaises(Fault):self.store.knowledge(self.source)
    def test_revoked_reader_denied(self):
        self.seeded();self.store.revoke('reader')
        with self.assertRaises(Fault):self.store.knowledge(self.reader)
    def test_revoked_source_hides_notes(self):self.seeded();self.store.revoke('source');self.assertEqual(self.data()['nodes'],[])
    def test_expired_source_hides_notes(self):
        self.seeded()
        with self.store.transaction() as db:db.execute('UPDATE credentials SET expires=999 WHERE id=\'source\'')
        self.assertEqual(self.data()['nodes'],[])
    def test_update_replaces_links(self):
        self.seeded();self.write('Area.md','# Area\n[[New]]');self.scan();data=self.data();self.assertEqual(data['counts']['links'],1);self.assertEqual(data['issues'][0]['target'],'New')
    def test_revision_increments_on_content(self):
        self.write('a.md','# A');self.scan();first=self.data()['nodes'][0];self.write('a.md','# B');self.scan();second=self.data()['nodes'][0];self.assertEqual((first['id'],second['revision']),(second['id'],2))
    def test_unchanged_revision_stable(self):self.seeded();self.scan();self.assertTrue(all(n['revision']==1 for n in self.data()['nodes']))
    def test_deletion_removes_search_body(self):
        self.seeded();p=self.vault/'Project.md';p.unlink();self.scan();self.assertEqual(self.data('monochrome')['results'],[])
        with self.store.connection() as db:self.assertEqual(db.execute('SELECT body FROM knowledge_notes WHERE path=\'Project.md\'').fetchone()[0],'')
    def test_deletion_flags_reference(self):self.seeded();(self.vault/'Project.md').unlink();self.scan();self.assertEqual(self.data()['issues'][0]['status'],'missing')
    def test_rename_old_link_does_not_guess(self):self.seeded();(self.vault/'Project.md').rename(self.vault/'Moved.md');self.scan();self.assertEqual(self.data()['issues'][0]['target'],'Project')
    def test_source_hash_matches_disk(self):
        self.seeded();data=self.data();n=next(n for n in data['nodes'] if n['path']=='Area.md');link=next(l for l in data['links'] if l['source']==n['id']);self.assertEqual(link['source_sha256'],hashlib.sha256((self.vault/'Area.md').read_bytes()).hexdigest())
    def test_map_two_hops(self):self.seeded();self.assertEqual(self.data()['map_health']['outside_two_hops'],[])
    def test_orphan_reported(self):self.seeded();self.write('orphan.md','# Orphan');self.scan();self.assertEqual(len(self.data()['map_health']['outside_two_hops']),1)
    def test_missing_map_reported(self):self.write('a.md','# A');self.scan();self.assertEqual(self.data()['map_health']['missing_map_sources'],['source'])
    def test_ambiguous_names_not_guessed(self):
        self.write('MAP.md','[[Same]]');self.write('one/Same.md','# One');self.write('two/Same.md','# Two');self.scan();self.assertEqual(self.data()['issues'][0]['status'],'ambiguous')
    def test_alias_resolution(self):
        self.write('MAP.md','[[Alias]]');self.write('Actual.md','---\naliases: [Alias]\n---\n# Actual');self.scan();self.assertEqual(self.data()['counts']['links'],1)
    def test_alias_collision(self):
        self.write('MAP.md','[[Alias]]');self.write('a.md','---\naliases: [Alias]\n---');self.write('b.md','---\naliases: [Alias]\n---');self.scan();self.assertEqual(self.data()['issues'][0]['status'],'ambiguous')
    def test_url_encoded_markdown_relative(self):
        self.write('one/a.md','[B](../two/A%20B.md)');self.write('two/A B.md','# B');self.scan();self.assertEqual(self.data()['counts']['links'],1)
    def test_traversal_blocked(self):self.write('MAP.md','[Secret](../secret.md)');self.scan();self.assertEqual(self.data()['issues'][0]['status'],'blocked_path')
    def test_unsafe_scheme_blocked(self):self.write('MAP.md','[Bad](javascript:alert)');self.scan();self.assertEqual(self.data()['issues'][0]['status'],'blocked_scheme')
    def test_external_link_not_followed(self):self.write('MAP.md','[Web](https://example.invalid)');self.scan();self.assertEqual((self.data()['counts']['links'],self.data()['counts']['issues']),(0,0))
    def test_malformed_external_no_crash(self):self.write('MAP.md','[Bad](https://[)');self.scan();self.assertEqual(self.data()['issues'][0]['status'],'malformed_link')
    def test_hidden_obsidian_ignored(self):
        self.write('.obsidian/plugins/payload.md','# SECRET');self.write('good.md','# Public');self.scan();self.assertEqual(self.data('SECRET')['results'],[])
    def test_symlink_file_excluded(self):
        outside=self.root/'secret.md';outside.write_text('# Hidden');os.symlink(outside,self.vault/'link.md');self.scan();self.assertEqual(self.data()['nodes'],[]);self.assertEqual(self.connector.health['status'],'attention')
    def test_symlink_directory_excluded(self):
        d=self.root/'outside';d.mkdir();(d/'secret.md').write_text('# Hidden');os.symlink(d,self.vault/'links');self.scan();self.assertEqual(self.data()['nodes'],[])
    def test_hardlink_excluded(self):
        outside=self.root/'secret.md';outside.write_text('# Hidden');os.link(outside,self.vault/'link.md');self.scan();self.assertEqual(self.data()['nodes'],[])
    def test_root_replaced_hides_old_notes(self):
        self.seeded();self.vault.rename(self.root/'previous');self.vault.mkdir();self.scan();self.assertEqual(self.data()['nodes'],[]);self.assertEqual(self.connector.health['status'],'unavailable')
    def test_pause_stops_scanning(self):
        self.seeded();self.store.set_paused(self.owner,True);self.write('New.md','# New');self.scan();self.assertEqual(self.data()['counts']['notes'],3)
    def test_resume_indexes_change(self):
        self.seeded();self.store.set_paused(self.owner,True);self.write('New.md','# New');self.scan();self.store.set_paused(self.owner,False);self.scan();self.assertEqual(self.data()['counts']['notes'],4)
    def test_invalid_utf8_does_not_keep_old_body(self):
        p=self.write('a.md','# A');self.scan();p.write_bytes(b'\xff');self.scan();self.assertEqual(self.data()['nodes'],[])
    def test_oversize_note_excluded(self):self.write('a.md','x'*65537);self.scan();self.assertEqual(self.data()['nodes'],[])
    def test_read_note_hash_and_text(self):
        self.seeded();n=self.data('monochrome')['results'][0];text=self.store.knowledge_note(self.owner,n['id']);self.assertEqual(text['sha256'],n['sha256']);self.assertIn('monochrome',text['body'])
    def test_packet_is_not_generated_answer(self):
        self.seeded();p=build_packet(self.store,self.owner,'monochrome');self.assertTrue(p['no_answer_generated']);self.assertFalse(p['content_egress']);self.assertEqual(len(p['evidence']),1)
    def test_packet_lines(self):
        self.seeded();e=build_packet(self.store,self.owner,'monochrome')['evidence'][0];raw=self.store.knowledge_note(self.owner,e['id'])['body'].splitlines();self.assertEqual('\n'.join(raw[e['start_line']-1:e['end_line']]),e['excerpt'])
    def test_packet_empty_abstains(self):self.seeded();self.assertEqual(build_packet(self.store,self.owner,'unknown')['evidence'],[])
    def test_packet_scope(self):self.seeded();self.assertEqual(build_packet(self.store,self.foreign,'monochrome')['evidence'],[])
    def test_packet_limit(self):
        for i in range(10):self.write(f'{i}.md','# Search\n'+'search '*1000)
        self.scan();p=build_packet(self.store,self.owner,'search');self.assertLessEqual(len(p['evidence']),5);self.assertLessEqual(sum(len(e['excerpt']) for e in p['evidence']),6000)
    def test_query_limit(self):
        with self.assertRaises(Fault):self.data('x'*161)
    def test_invalid_kind(self):
        with self.assertRaises(Fault):self.data(kind='administrator')
    def test_route_scope_override_denied(self):
        with self.assertRaises(Fault):knowledge_get(self.store,self.owner,urlsplit('/desk/knowledge?scope=other'))
    def test_route_duplicate_query_denied(self):
        with self.assertRaises(Fault):knowledge_get(self.store,self.owner,urlsplit('/desk/knowledge?q=a&q=b'))
    def test_route_valid(self):self.seeded();self.assertEqual(knowledge_get(self.store,self.owner,urlsplit('/desk/knowledge?q=monochrome'))['counts']['matches'],1)
    def test_route_no_write(self):
        with self.assertRaises(Fault):knowledge_get(self.store,self.owner,urlsplit('/desk/knowledge/delete'))
    def test_graph_never_asserts_truth(self):self.seeded();self.assertTrue(all(l['basis']=='explicit_note_reference' for l in self.data()['links']))


if __name__=='__main__':unittest.main()
