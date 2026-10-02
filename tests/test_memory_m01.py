"""M01 acceptance against synthetic files and the real SQLite/read pipeline."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alfred.knowledge import KnowledgeStore, MarkdownVault, parse_note, note_id
from alfred.grounded import check_sources
from alfred.local import Fault
from alfred.reviewed_memory import ReviewedMemory


class M01Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.vault = self.root / 'vault'
        self.vault.mkdir()
        self.store = KnowledgeStore(self.root / 'db', clock=lambda:1000)
        self.owner = self.store.provision('work', 'owner', 'owner')
        self.source = self.store.provision('work', 'source', 'source')
        self.scanner = MarkdownVault(self.store, self.source, self.vault)

    def write(self, path, body):
        file = self.vault / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(body, encoding='utf-8')
        return file

    def data(self):
        return self.store.knowledge(self.owner)

    def scan(self):
        return self.scanner.scan()

    def node(self, path):
        return next(n for n in self.data()['nodes'] if n['path']==path)

    def adopt_ids(self):
        # Explicit adoption before the first selected-vault binding.
        with self.store.transaction() as db:
            db.execute('DELETE FROM knowledge_vaults')
        self.scanner = MarkdownVault(self.store, self.source, self.vault, id_key='alfred_id')

    def history(self, identity):
        with self.store.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM knowledge_history WHERE id=? ORDER BY revision', (identity,))]

    def test_closed_app_read_never_writes_vault(self):
        file = self.write('one.md', '# One\n[[two#Section]]')
        self.write('two.md', '# Two\n## Section\nEvidence')
        before = {p.relative_to(self.vault): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.vault.rglob('*.md')}
        with patch('subprocess.Popen', side_effect=AssertionError('No editor or plugin process')):
            self.scan()
        after = {p.relative_to(self.vault): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.vault.rglob('*.md')}
        self.assertEqual(before, after)
        self.assertEqual(self.data()['counts']['links'], 1)
        self.assertEqual(file.read_text(), '# One\n[[two#Section]]')
        self.assertFalse((self.vault / '.alfred').exists())

    def test_selected_vault_id_survives_restart_and_label_change(self):
        self.write('a.md', '# A'); self.scan()
        first = self.node('a.md')
        restarted = KnowledgeStore(self.root / 'db', clock=lambda:1000)
        scanner = MarkdownVault(restarted, self.source, self.vault, label='Renamed display label')
        self.assertEqual(scanner.scan()['status'], 'ready')
        self.assertEqual(scanner.vault_id, first['vault_id'])
        self.assertEqual(self.node('a.md')['id'], first['id'])
        self.assertEqual(self.node('a.md')['revision'], first['revision'])

    def test_root_folder_rename_with_explicit_selection_preserves_identity(self):
        self.write('a.md', '# A'); self.scan(); first = self.node('a.md')
        moved = self.root / 'moved'; self.vault.rename(moved)
        MarkdownVault(self.store, self.source, moved).scan()
        self.assertEqual(self.node('a.md')['vault_id'], first['vault_id'])
        self.assertEqual(self.node('a.md')['id'], first['id'])

    def test_replacement_root_after_restart_is_unavailable(self):
        self.write('a.md', '# A'); self.scan()
        self.vault.rename(self.root / 'original'); self.vault.mkdir()
        self.write('a.md', '# Impostor')
        restarted = MarkdownVault(KnowledgeStore(self.root / 'db', clock=lambda:1000), self.source, self.vault)
        self.assertEqual(restarted.scan()['status'], 'unavailable')
        self.assertEqual(restarted.health['errors'][0]['code'], 'vault_root_replaced')
        self.assertEqual(self.data()['nodes'], [])

    def test_missing_selection_visible_before_first_scan(self):
        second = self.store.provision('work', 'second', 'source')
        scanner = MarkdownVault(self.store, second, self.root / 'absent')
        self.assertEqual(scanner.health['status'], 'unavailable')
        source = next(s for s in self.data()['sources'] if s['source']=='second')
        self.assertEqual(source['status'], 'unavailable')
        self.assertIsNotNone(source['vault_id'])

    def test_temporarily_lost_root_is_not_note_deletion(self):
        self.write('a.md', '# A'); self.scan(); before = self.node('a.md')
        self.vault.rename(self.root / 'absent'); self.scan()
        self.assertEqual(self.data()['nodes'], [])
        self.assertEqual(self.history(before['id'])[-1]['status'], 'ready')
        with self.assertRaises(Fault): self.store.knowledge_note(self.owner, before['id'])
        (self.root / 'absent').rename(self.vault); self.scan()
        after = self.node('a.md')
        self.assertEqual(after['id'], before['id'])
        self.assertEqual(after['revision'], before['revision']+1)

    def test_proven_rename_keeps_id_and_advances_revision(self):
        original = self.write('a.md', '# A\nEvidence'); self.scan(); before = self.node('a.md')
        original.rename(self.vault / 'b.md'); self.scan(); after = self.node('b.md')
        self.assertEqual(after['id'], before['id'])
        self.assertEqual(after['sha256'], before['sha256'])
        self.assertEqual(after['revision'], before['revision']+1)
        self.assertEqual([h['path'] for h in self.history(after['id'])], ['a.md','b.md'])
        self.assertFalse(check_sources(self.store,self.owner,[{'note_id':before['id'],'sha256':before['sha256'],'revision':before['revision']}])['current_index_match'])

    def test_rename_after_restart_has_catalogue_proof(self):
        original = self.write('a.md', '# A'); self.scan(); before = self.node('a.md')
        original.rename(self.vault / 'b.md')
        MarkdownVault(KnowledgeStore(self.root / 'db', clock=lambda:1000), self.source, self.vault).scan()
        self.assertEqual(self.node('b.md')['id'], before['id'])

    def test_renamed_note_and_reused_old_path_keep_distinct_histories(self):
        original=self.write('a.md','# A'); self.scan(); before=self.node('a.md')
        original.rename(self.vault/'b.md'); self.write('a.md','# Replacement'); self.scan()
        self.assertEqual(self.node('b.md')['id'],before['id'])
        self.assertNotEqual(self.node('a.md')['id'],before['id'])
        self.assertEqual(self.node('b.md')['revision'],before['revision']+1)

    def test_two_files_swapping_paths_keep_filesystem_identities(self):
        a=self.write('a.md','# A'); b=self.write('b.md','# B'); self.scan()
        first,second=self.node('a.md'),self.node('b.md')
        temporary=self.root/'swap'; a.rename(temporary); b.rename(a); temporary.rename(b); self.scan()
        self.assertEqual(self.node('b.md')['id'],first['id'])
        self.assertEqual(self.node('a.md')['id'],second['id'])

    def test_edited_move_and_reused_old_path_cannot_transfer_history(self):
        original=self.write('a.md','# A'); self.scan(); before=self.node('a.md')
        original.rename(self.vault/'b.md'); self.write('b.md','# Edited'); self.write('a.md','# Replacement'); self.scan()
        self.assertNotIn(before['id'],[n['id'] for n in self.data()['nodes']])
        self.assertIn({'path':'b.md','code':'rename_identity_unproven'},self.data()['sources'][0]['errors'])

    def test_atomic_save_at_current_path_preserves_identity(self):
        self.write('a.md', '# A'); self.scan(); before = self.node('a.md')
        replacement = self.root / 'staged'; replacement.write_text('# Revised')
        replacement.replace(self.vault / 'a.md'); self.scan()
        self.assertEqual(self.node('a.md')['id'], before['id'])
        self.assertEqual(self.node('a.md')['revision'], 2)

    def test_copy_is_not_a_rename(self):
        self.write('a.md', '# Same'); self.scan(); before = self.node('a.md')
        self.write('b.md', '# Same'); self.scan()
        self.assertNotEqual(self.node('b.md')['id'], before['id'])
        self.assertEqual(self.node('a.md')['id'], before['id'])

    def test_unproved_copy_delete_is_explicitly_distinct(self):
        original = self.write('a.md', '# Same'); self.scan(); before = self.node('a.md')
        self.write('b.md', '# Same'); original.unlink(); self.scan()
        self.assertNotEqual(self.node('b.md')['id'], before['id'])
        self.assertIn({'path':'b.md','code':'rename_identity_unproven'},self.data()['sources'][0]['errors'])
        self.assertEqual(self.history(before['id'])[-1]['status'], 'missing')

    def test_edited_rename_without_proof_does_not_guess(self):
        original = self.write('a.md', '# A'); self.scan(); before = self.node('a.md')
        original.rename(self.vault / 'b.md'); self.write('b.md', '# B'); self.scan()
        self.assertNotEqual(self.node('b.md')['id'], before['id'])

    def test_adopted_id_supports_edited_move_and_restore(self):
        self.adopt_ids(); original = self.write('a.md', '---\nalfred_id: project-1\n---\n# A')
        self.scan(); before = self.node('a.md')
        original.rename(self.vault / 'b.md'); self.write('b.md', '---\nalfred_id: project-1\n---\n# B'); self.scan()
        self.assertEqual(self.node('b.md')['id'], before['id'])
        (self.vault / 'b.md').unlink(); self.scan()
        self.write('c.md', '---\nalfred_id: project-1\n---\n# B'); self.scan()
        self.assertEqual(self.node('c.md')['id'], before['id'])
        self.assertEqual(self.node('c.md')['revision'], 4)

    def test_frontmatter_id_requires_adoption(self):
        self.write('a.md', '---\nalfred_id: x\n---\n# A')
        self.write('b.md', '---\nalfred_id: x\n---\n# B'); self.scan()
        self.assertEqual(len(self.data()['nodes']), 2)
        self.assertIn('stable_id_not_adopted', [e['code'] for e in self.scanner.health['errors']])

    def test_duplicate_adopted_ids_withhold_source_atomically(self):
        self.adopt_ids(); self.write('a.md', '---\nalfred_id: x\n---\n# A'); self.scan(); before = self.node('a.md')
        self.write('b.md', '---\nalfred_id: x\n---\n# B'); self.scan()
        self.assertEqual(self.scanner.health['errors'], [{'code':'duplicate_stable_note_id'}])
        self.assertEqual(self.data()['nodes'], [])
        self.assertEqual(len(self.history(before['id'])), 1)
        (self.vault / 'b.md').unlink(); self.scan()
        self.assertEqual(self.node('a.md')['id'], before['id'])

    def test_changing_adopted_id_cannot_steal_history(self):
        self.adopt_ids(); self.write('a.md', '---\nalfred_id: x\n---\n# A'); self.scan()
        self.write('a.md', '---\nalfred_id: y\n---\n# A'); self.scan()
        self.assertEqual(self.scanner.health['errors'][0]['code'], 'stable_note_id_changed')
        self.assertEqual(self.data()['nodes'], [])

    def test_removing_adopted_id_is_rejected(self):
        self.adopt_ids(); self.write('a.md', '---\nalfred_id: x\n---\n# A'); self.scan()
        self.write('a.md', '# A'); self.scan()
        self.assertEqual(self.scanner.health['errors'][0]['code'], 'stable_note_id_changed')

    def test_rename_cannot_hide_removed_adopted_id(self):
        self.adopt_ids(); original=self.write('a.md','---\nalfred_id: x\n---\n# A'); self.scan()
        original.rename(self.vault/'b.md'); self.write('b.md','# A'); self.scan()
        self.assertEqual(self.scanner.health['errors'][0]['code'],'stable_note_id_changed')
        self.assertEqual(self.data()['nodes'],[])

    def test_historical_id_cannot_rebind_to_occupied_note(self):
        self.adopt_ids()
        self.write('a.md', '---\nalfred_id: a\n---\n# A'); self.write('b.md', '# B'); self.scan()
        (self.vault / 'a.md').unlink(); self.write('b.md', '---\nalfred_id: a\n---\n# B'); self.scan()
        self.assertEqual(self.scanner.health['errors'][0]['code'], 'stable_note_id_rebound')

    def test_case_colliding_paths_rejected(self):
        self.write('Same.md', '# A'); self.write('same.md', '# B'); self.scan()
        self.assertEqual(self.scanner.health['errors'][0]['code'], 'duplicate_note_path')
        self.assertEqual(self.data()['nodes'], [])

    def test_projection_rebuild_preserves_ids_history_revisions(self):
        self.write('a.md', '# A\n[[b#Section]]'); self.write('b.md', '# B\n## Section\nEvidence'); self.scan()
        before = [(n['id'],n['revision']) for n in self.data()['nodes']]
        with self.store.transaction() as db:
            for table in ('knowledge_notes','knowledge_refs','knowledge_anchors'):
                db.execute('DELETE FROM '+table)
        self.scan()
        self.assertEqual([(n['id'],n['revision']) for n in self.data()['nodes']], before)
        self.assertEqual(self.data()['links'][0]['anchor']['start_line'], 2)
        self.assertTrue(all(len(self.history(identity))==1 for identity,_ in before))

    def test_same_external_id_in_distinct_vaults_remains_distinct(self):
        self.adopt_ids(); self.write('a.md', '---\nalfred_id: x\n---\n# A'); self.scan(); first=self.node('a.md')
        source = self.store.provision('work','second','source'); other=self.root/'other'; other.mkdir()
        (other/'a.md').write_text('---\nalfred_id: x\n---\n# A')
        scanner=MarkdownVault(self.store,source,other,id_key='alfred_id'); scanner.scan()
        nodes=self.data()['nodes']; self.assertEqual(len(nodes),2)
        self.assertNotEqual(nodes[0]['id'],nodes[1]['id'])
        self.assertNotEqual(first['vault_id'],scanner.vault_id)

    def test_explicit_exclusion_withholds_subtree(self):
        with self.store.transaction() as db: db.execute('DELETE FROM knowledge_vaults')
        self.scanner=MarkdownVault(self.store,self.source,self.vault,exclude_folders=['Private'])
        self.write('Private/secret.md','# SECRET'); self.write('PrivateSimilar/public.md','# Public')
        self.write('.obsidian/plugins/payload.md','# Plugin'); self.write('node_modules/payload.md','# Dependency')
        self.scan(); self.assertEqual([n['path'] for n in self.data()['nodes']],['PrivateSimilar/public.md'])
        with self.store.connection() as db:
            self.assertNotIn('SECRET',str([tuple(r) for r in db.execute('SELECT * FROM knowledge_notes')]))

    def test_selection_changes_are_explicitly_rejected(self):
        self.write('a.md','# A'); self.scan()
        scanner=MarkdownVault(self.store,self.source,self.vault,exclude_folders=['Private'])
        self.assertEqual(scanner.scan()['errors'][0]['code'],'vault_selection_changed')
        self.assertEqual(self.data()['nodes'],[])

    def test_unsafe_exclusions_and_root_traversal_rejected(self):
        for exclusion in ['../secret','/absolute','a/../b','a\\b']:
            with self.subTest(exclusion=exclusion), self.assertRaises(Fault):
                MarkdownVault(self.store,self.source,self.vault,exclude_folders=[exclusion])
        with self.assertRaises(Fault): MarkdownVault(self.store,self.source,self.vault/'..'/'vault')

    def test_database_inside_vault_rejected(self):
        store=KnowledgeStore(self.vault/'runtime.db')
        source=store.provision('work','inside','source')
        with self.assertRaises(Fault) as error: MarkdownVault(store,source,self.vault)
        self.assertEqual(error.exception.code,'database_must_be_outside_vault')

    def test_unsafe_note_path_from_scanner_excluded(self):
        self.write('a\\b.md','# Unsafe'); self.scan()
        self.assertEqual(self.data()['nodes'],[])
        self.assertEqual(self.scanner.health['errors'][0]['code'],'unsafe_note_path')

    def test_direct_pipeline_rejects_unsafe_and_duplicate_paths_atomically(self):
        good=parse_note('a.md',b'# A'); good['modified']=0
        other=self.store.provision('work','direct','source')
        self.store.replace_notes(other,'Direct',[good],[])
        for notes in ([good,dict(good)], [dict(good,path='../outside.md')]):
            with self.assertRaises(Fault):self.store.replace_notes(other,'Direct',notes,[])
        self.assertEqual(len([n for n in self.data()['nodes'] if n['source']=='direct']),1)

    def test_partial_frontmatter_withholds_prior_body_as_unavailable(self):
        self.write('a.md','# A'); self.scan(); before=self.node('a.md')
        self.write('a.md','---\nalfred_id:'); self.scan()
        self.assertEqual(self.data()['nodes'],[])
        self.assertEqual(self.history(before['id'])[-1]['status'],'unavailable')
        self.write('a.md','# A revised'); self.scan()
        self.assertEqual(self.node('a.md')['id'],before['id'])
        self.assertEqual(self.node('a.md')['revision'],3)

    def test_incomplete_code_and_comments_fail_honestly(self):
        for body,code in [('```md\nunfinished','unclosed_code_fence'),('<!-- unfinished','unclosed_html_comment')]:
            with self.subTest(body=body),self.assertRaises(Fault) as error:parse_note('a.md',body.encode())
            self.assertEqual(error.exception.code,code)

    def test_changed_during_read_is_withheld(self):
        file=self.write('a.md','# A'); self.scan(); before=self.node('a.md'); original_read=os.read; changed=[False]
        def mutate(fd,size):
            raw=original_read(fd,size)
            if raw==b'# A' and not changed[0]:
                changed[0]=True; file.write_text('# Changed during read')
            return raw
        with patch('alfred.knowledge.os.read',side_effect=mutate):self.scan()
        self.assertEqual(self.data()['nodes'],[])
        self.assertIn('note_changed_during_read',[e['code'] for e in self.scanner.health['errors']])
        self.assertEqual(self.history(before['id'])[-1]['status'],'unavailable')

    def test_file_replaced_during_read_fails_scan(self):
        file=self.write('a.md','# A'); self.scan(); original_read=os.read; changed=[False]
        def replace(fd,size):
            raw=original_read(fd,size)
            if raw==b'# A' and not changed[0]:
                changed[0]=True; staged=self.root/'staged'; staged.write_text('# New'); staged.replace(file)
            return raw
        with patch('alfred.knowledge.os.read',side_effect=replace):self.scan()
        self.assertEqual(self.scanner.health['status'],'unavailable')
        self.assertEqual(self.data()['nodes'],[])

    def test_mid_scan_content_change_invalidates_whole_snapshot(self):
        a=self.write('a.md','# A'); self.write('z.md','# Z'); self.scan(); original_read=os.read; changed=[False]
        def late_change(fd,size):
            raw=original_read(fd,size)
            if raw==b'# Z' and not changed[0]: changed[0]=True; a.write_text('# A changed')
            return raw
        with patch('alfred.knowledge.os.read',side_effect=late_change):self.scan()
        self.assertEqual(self.scanner.health['errors'],[{'code':'vault_changed_during_scan'}])
        self.assertEqual(self.data()['nodes'],[])

    def test_read_error_distinguished_from_missing_file(self):
        self.write('a.md','# A'); self.scan(); before=self.node('a.md'); original_open=os.open
        def denied(path,*args,**kwargs):
            if path=='a.md':raise PermissionError('synthetic')
            return original_open(path,*args,**kwargs)
        with patch('alfred.knowledge.os.open',side_effect=denied):self.scan()
        self.assertEqual(self.history(before['id'])[-1]['status'],'unavailable')
        self.assertEqual(self.data()['nodes'],[])

    def test_deleted_and_recreated_path_without_id_is_distinct(self):
        self.write('a.md','# A'); self.scan(); before=self.node('a.md')
        (self.vault/'a.md').unlink(); self.scan(); self.write('a.md','# A'); self.scan()
        self.assertNotEqual(self.node('a.md')['id'],before['id'])
        self.assertEqual(self.history(before['id'])[-1]['status'],'missing')

    def test_validated_heading_and_block_edges_have_target_provenance(self):
        self.write('MAP.md','[[Target#Section|Displayed]]\n![[Target#^proof]]\n[Local](Target.md#Section)')
        self.write('Target.md','# Target\n## Section\nEvidence ^proof\n## Other\nOther content'); self.scan()
        links=self.data()['links']; self.assertEqual(len(links),3)
        target=self.node('Target.md')
        for link in links:
            self.assertEqual(link['target_sha256'],target['sha256'])
            self.assertEqual(link['target_revision'],target['revision'])
            self.assertEqual(link['anchor']['end_line'],3)
        self.assertEqual(links[1]['anchor']['kind'],'block')
        self.assertEqual(links[1]['anchor']['start_line'],3)

    def test_invalid_duplicate_and_unsupported_anchors_never_become_file_edges(self):
        self.write('a.md','[[b#Missing]]\n[[b#Duplicate]]\n[[b#^twice]]\n[[b#Parent#Child]]\n[[b#]]')
        self.write('b.md','# B\n## Duplicate\n## Duplicate\nOne ^twice\nTwo ^twice'); self.scan()
        self.assertEqual(self.data()['links'],[])
        self.assertEqual([i['status'] for i in self.data()['issues']],
                         ['missing_anchor','ambiguous_anchor','ambiguous_anchor','unsupported_anchor','unsupported_anchor'])

    def test_fenced_commented_inline_and_frontmatter_anchors_are_not_evidence(self):
        self.write('a.md','[[b#Hidden]]\n[[b#^hidden]]')
        self.write('b.md','---\ntitle: Hidden\n---\n```md\n# Hidden\nOne ^hidden\n```\n<!-- # Hidden -->\n`# Hidden`'); self.scan()
        self.assertEqual(self.data()['links'],[])
        self.assertTrue(all(i['status']=='missing_anchor' for i in self.data()['issues']))

    def test_self_anchors_and_alias_anchors(self):
        self.write('a.md','# A\n[[#A]]\n[[Alias#Section]]')
        self.write('b.md','---\naliases: [Alias]\n---\n# B\n## Section\nEvidence'); self.scan()
        self.assertEqual(len(self.data()['links']),2)
        self.assertIn('b.md',[n['path'] for n in self.store.knowledge(self.owner,'Alias')['results']])

    def test_alias_collision_is_ambiguous_before_anchor_resolution(self):
        self.write('a.md','[[Alias#Section]]')
        for path in ['b.md','c.md']: self.write(path,'---\naliases: [Alias]\n---\n## Section')
        self.scan(); self.assertEqual(self.data()['issues'][0]['status'],'ambiguous')

    def test_encoded_hash_filename_and_heading(self):
        self.write('a.md','[Name](A%23B.md#Some%20Heading)')
        self.write('A#B.md','## Some Heading\nEvidence'); self.scan()
        self.assertEqual(len(self.data()['links']),1)
        self.assertEqual(self.data()['links'][0]['anchor']['name'],'Some Heading')

    def test_encoded_traversal_and_malformed_unicode_are_rejected(self):
        self.write('a.md','[Unsafe](%2e%2e/secret.md)\n[Bad](%FF.md)\n[Backslash](%5csecret.md)')
        self.scan(); self.assertEqual(self.data()['links'],[])
        self.assertEqual([i['status'] for i in self.data()['issues']],['blocked_path','malformed_link','blocked_path'])

    def test_lost_source_cannot_support_reviewed_claim(self):
        self.write('a.md','# A\nA is in planning.'); self.scan(); note=self.node('a.md')
        memory=ReviewedMemory(self.store); memory.create_entity(self.owner,{'id':'a','kind':'project','name':'A'})
        proposal=memory.propose(self.owner,{'request_id':'test','subject_id':'a','predicate':'status','object_id':None,
            'value':'planning','valid_from':None,'valid_until':None,
            'evidence':{'note_id':note['id'],'sha256':note['sha256'],'revision':note['revision'],'start_line':2,'end_line':2}})
        memory.review(self.owner,proposal['id'],{'version':1,'decision':'accept','replaces_id':None,'replaces_version':None})
        self.vault.rename(self.root/'lost'); self.scan()
        claim=memory.view(self.owner)['claims'][0]
        self.assertEqual(claim['state'],'invalidated'); self.assertFalse(claim['usable'])

    def test_failed_scan_keeps_last_complete_snapshot_timestamp(self):
        self.write('a.md','# A'); self.scan(); source=self.data()['sources'][0]
        self.store.clock=lambda:1010
        self.vault.rename(self.root/'lost'); self.scan(); lost=self.data()['sources'][0]
        self.assertEqual(lost['checked'],1010)
        self.assertEqual(lost['last_complete_scan'],source['last_complete_scan'])
        self.assertEqual(lost['last_confirmed_snapshot'],source['last_confirmed_snapshot'])
        self.assertEqual(lost['status'],'unavailable')

    def test_mid_scan_source_revocation_never_exposes_content(self):
        self.write('a.md','# A'); self.scan(); original_read=os.read; revoked=[False]
        def revoke(fd,size):
            raw=original_read(fd,size)
            if raw==b'# A' and not revoked[0]:
                revoked[0]=True; self.store.revoke('source')
            return raw
        with patch('alfred.knowledge.os.read',side_effect=revoke):self.scan()
        self.assertEqual(self.data()['nodes'],[])
        self.assertEqual(self.data()['sources'],[])
        self.assertEqual(self.scanner.health['status'],'unavailable')

    def test_selected_source_cannot_bypass_catalogue_binding(self):
        note=parse_note('a.md',b'# A'); note['modified']=0
        with self.assertRaises(Fault) as error:self.store.replace_notes(self.source,'Other',[note],[])
        self.assertEqual(error.exception.code,'vault_selection_required')

    def test_invalid_adopted_id_withholds_note(self):
        self.adopt_ids(); self.write('a.md','---\nalfred_id: ../../outside\n---\n# A'); self.scan()
        self.assertEqual(self.scanner.health['errors'][0]['code'],'invalid_stable_note_id')
        self.assertEqual(self.data()['nodes'],[])

    def test_v1_migration_preserves_legacy_evidence_ids_and_revisions(self):
        note=parse_note('a.md',b'# A'); identity=note_id('source','a.md')
        with self.store.transaction() as db:
            db.execute('UPDATE knowledge_meta SET version=1')
            for table in ('knowledge_vaults','knowledge_identity','knowledge_history','knowledge_anchors'):
                db.execute('DROP TABLE '+table)
            db.execute('DROP TABLE knowledge_notes')
            db.execute('CREATE TABLE knowledge_notes(scope TEXT,source TEXT,id TEXT,path TEXT,title TEXT,kind TEXT,tags TEXT,aliases TEXT,body TEXT,sha256 TEXT,revision INTEGER,modified INTEGER,indexed INTEGER,status TEXT,PRIMARY KEY(scope,source,id),UNIQUE(scope,source,path))')
            db.execute('INSERT INTO knowledge_notes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('work','source',identity,'a.md','A','note','[]','[]','# A',note['sha256'],7,1000,1000,'ready'))
            db.execute('INSERT OR REPLACE INTO knowledge_sources VALUES (?,?,?,?,?,?,?)',('work','source','Legacy',1000,'ready','[]','old'))
        self.store=KnowledgeStore(self.root/'db',clock=lambda:1000)
        self.write('a.md','# A'); self.scanner=MarkdownVault(self.store,self.source,self.vault); self.scan()
        self.assertEqual(self.node('a.md')['id'],identity)
        self.assertEqual(self.node('a.md')['revision'],7)
        self.assertEqual(self.history(identity)[0]['revision'],7)
        KnowledgeStore(self.root/'db')  # migration/reopening is idempotent
        self.assertEqual(self.store.knowledge_note(self.owner,identity)['body'],'# A')


if __name__=='__main__':unittest.main()
