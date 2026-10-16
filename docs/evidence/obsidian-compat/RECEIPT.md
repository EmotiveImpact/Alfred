# Plan item 1.5 receipt: Obsidian compatibility and safe note writing

16 October 2026. Branch `feat/obsidian-compat-2026-10-16`, started from main `75947b8dd`.
Tested commit: `f1043dcd1` (code, tests, fixture and docs). This receipt is added in the commit
after it and changes no code. Status: **implemented on a branch** against synthetic data only.
Not merged, not deployed, not exercised by the owner or by the Obsidian app. Requirements
MEM-001, MEM-002, MEM-011 and MEM-014; memory jobs M01 and M04.

## What was built

| Plan item 1.5 asks for | Where | Evidence |
|---|---|---|
| Frontmatter aliases and tags read as Obsidian reads them | `alfred/knowledge.py` `parse_note` | List and string forms; `#` dropped from frontmatter tags; deprecated singular `alias`/`tag`/`cssclass` ignored with a warning. `tests/test_obsidian_compat.py` `test_frontmatter_aliases_and_tags_in_list_and_string_forms`, `test_frontmatter_tag_forms` |
| `[[link\|alias]]` | `parse_note`, `note_structure` | Target and display text separated, table-escaped pipe handled; display text shown in `knowledge_note(...)['structure']`. `test_display_text_for_wiki_escaped_and_markdown_links`, `test_note_structure_shows_display_text_callouts_and_blocks` |
| Headings and block anchors (`^id`) | `parse_note`, `resolve_reference` | Nested subpaths `[[N#Parent#Child]]`; trailing IDs span whole paragraphs; standalone `^id` after quotes, tables, lists and code blocks. `test_block_id_spans`, `test_nested_heading_subpaths`, fixture link test |
| Embeds `![[...]]` | `parse_note`, `resolve_reference` | Note, heading and block embeds are validated `embeds` edges; attachment embeds are neither edges nor issues. `test_attachment_embed_is_neither_a_link_nor_an_issue` |
| Callouts `> [!note]` | `parse_note` | Type, Obsidian style (aliases and unknown types), title, fold, nesting depth and span. `test_callout_forms` |
| Tags: inline, nested, frontmatter | `parse_note` | `#a/b`, Unicode, numeric-only excluded, not read in code, comments, links or URLs; bounded with a warning. `test_inline_tag_rules`, `test_tags_in_code_comments_urls_and_numbers_are_not_tags`, `test_tag_capacity_is_reported_not_silent` |
| `.obsidian` ignored | unchanged M01 exclusion | Fixture holds `.obsidian/app.json` and `.obsidian/snippets.md`; neither is indexed. `test_every_note_is_indexed_and_obsidian_settings_are_not` |
| `vault.append_section`: diff at approval, idempotent retry, read-back, refuses if changed, never rewrites human text | `alfred/vault_append.py`, `MarkdownVault.read_note`/`append_to_note`, `KnowledgeStore` write hooks, route `POST /desk/vault/append-proposals` | `tests/test_vault_append.py` (28 tests): separate `vault.append` grant; exact diff in the approval view; pure insertion asserted byte for byte; same request never appends twice (before and after rescan, after crash and reconcile, and at the writer); human edit after approval, an indexed edit before approval or dispatch, and an editor save landing between read and rename all refuse and leave the person's text; symlinked, hard-linked and replaced-root targets refused; revoked grant, pause and source forgetting stop dispatch; HTTP route needs sign-in, Origin and CSRF |
| Conflict copies from unrecognised tools detected by content hash | `alfred/sync_conflicts.py` `content_copies`, scanner | Same bytes, same folder, name extended by a short suffix: recorded with tool `unrecognised_same_content`, `detected_by: content_hash`, kept out of index and retrieval; editing the copy clears it; unrelated names, other folders and empty notes are not matched; forged entries rejected before storage. `ContentConflictTests` (5 tests) |

Acceptance: the synthetic fixture vault `tests/fixtures/obsidian_vault` exercises every syntax
above; `FixtureVaultTests` asserts every resulting link, anchor span, tag, alias and callout with
zero link issues. Writes refuse under a concurrent edit (`ConcurrentEditTests`). The plan text
says "the fixture vault from the Obsidian help site"; that content was not copied (licence and
public-repository rule). The fixture is written for this repository, every name fictional.

Small additive edits to shared modules: `policy.CAPABILITIES` gains `vault.append` (not
invitable); `lifecycle` cancels pending `vault.append_section` actions on source forgetting;
`desk_http` gains one route; `inbox.py` gains reporting constants with unchanged values. Two
existing tests that list every capability gained the `vault.append: False` entry. One M01
expectation changed: `[[b#Parent#Child]]` against a note without that heading is now
`missing_anchor` instead of `unsupported_anchor`, because nested subpaths are supported.

## Commands and results at `f1043dcd1`

- `python3 -m unittest tests.test_obsidian_compat tests.test_vault_append`: 53 tests pass.
- `python3 -m unittest discover -s tests`: 1166 tests pass (baseline main `75947b8dd`: 1113).
- `python3 -m alfred.demo`: exits 0.
- No console code changed, so no console build or browser run was needed or claimed.

## Limits

- Not the Obsidian app's parser or renderer. Rich inline markup inside heading text, headings
  inside quotes or callouts, footnotes, frontmatter links, Dataview, Canvas and Bases content
  and attachment parsing are not read. `[[Some.Note]]` with a short alphanumeric suffix is
  still taken as an attachment.
- No acceptance with a real vault edited by Obsidian; the plan's Gate 1 exit (owner pilot on one
  machine) is still open.
- The final signature check and the rename in `append_to_note` are two system calls; an editor
  save in that instant can still be lost. An atomic exchange (`renameat2`) would close it.
- "Appended and read back" is not "synchronised": a sync client may later deliver an older
  version. The append is one heading, one block; no edits, moves or deletions of existing text.
- The proposed diff, with a few lines of note context, is kept in the local action record, as
  inbox actions keep their text; forgetting a source cancels pending actions but does not yet
  redact completed action parameters.
- The console does not yet render append proposals or their diff; approval works through the
  existing desk action route and the action view carries `diff`.
- Content-hash conflict detection needs byte-identical copies; a copy already edited on another
  device is indexed as a separate note, as before. Obsidian's own "Make a copy" is reported as a
  conflict until it is edited.
