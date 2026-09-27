# ALFRED continuation record: Knowledge Desk v0.4

26 September 2026. Read this file, AGENTS.md, docs/KNOWLEDGE.md and docs/ROADMAP.md first.

## Branch and continuity

Use `feat/alfred-knowledge-desk-2026-09-26`, not main as though it contains the application.
Base Desk checkpoint: `a43c4adcbc8ca9c8bf310443fc1fc33734bacd14` on
`feat/alfred-desk-2026-09-25`. That work already added the browser UI, project-file connector,
foreground supervisor and actual browser evidence. Preserve it. Earlier v0.2 handoff
text was stale about the absence of a UI.

The new source graph/index/retrieval is original ALFRED code. It does not execute or merge
the retained third-party agents. All eight pinned archives and their 2,073 files remain
unchanged. The MAPS guide is attributed and assessed, not copied without a verified licence.

Always fetch the current branch head: successful acceptance can add a verification commit
containing the tested integration and screenshots. Its source receipt records exact file
hashes. Do not mistake the pre-integration input commit for the final tested file tree.
No force-push, automatic merge, private-data publication or unrequested deployment.

## Current implementation

Persistent local events and action ledger; scoped local bearer credentials; same-origin
browser sessions and CSRF; JSON project-file scanner; evidence and approval UI; automatic
processing while the launched Desk process is alive; local draft write and read-back.

Knowledge adds a read-only bounded Markdown vault connector, authored note metadata,
explicit link graph, search/type filters, source/backlink inspection, map-health checking
and bounded exact-line retrieval packets. It supports a subset of Obsidian-style links,
not plugins/sync or full Markdown/YAML semantics. No private vault has been accessed.

No live model, semantic embeddings, generated answers, microphone, cloud daemon, external
account/device control, ENDSTATE or Noir integration. Knowledge source packets are not
answers, and graph edges are references rather than verified real-world facts.

## Test and visual receipts

The acceptance workflow runs all original tests, the prior Desk browser regression and
the Knowledge browser flow against a real loopback server, SQLite and fictional files.
It also verifies both source archives. Inspect actual logs and
`docs/evidence/knowledge-v04/`, not just workflow YAML. Initial acceptance passed 302 tests
and all 33 prior browser checks but caught a graph node obscured by the legend; the layout
was corrected and extra cross-source bounds were added before final acceptance.

The optional self-contained HTML under `docs/previews/` uses the actual frontend with a
clearly labelled fictional read-only in-file transport. It is not a hosted server, cannot
perform approvals/effects and contains no sign-in secrets. Check its manifest hash.

## Commands

```sh
python3 -m unittest discover -s tests -v
python3 tools/import_sources.py --verify
python3 tools/extend_sources.py --verify
python3 -m alfred.desk init --data-dir ~/.local/share/alfred/desk-v04-demo
python3 -m alfred.desk access --data-dir ~/.local/share/alfred/desk-v04-demo
python3 -m alfred.desk serve --data-dir ~/.local/share/alfred/desk-v04-demo
```

Use a new data directory for the generated 20-note fictional vault. Init never overwrites.
The explicitly requested access command prints a private local sign-in key, so do not put
its output into chat, logs or screenshots. The service binds to 127.0.0.1 only.

## Next priority

A sourced conversation over bounded knowledge packets, using one contained model/runtime
adapter with explicit provider egress and an evaluation set. In parallel finish key/source
grants, retention/correction and reviewed unattended-service lifecycle. Then add voice
and one test-account connector. Follow the acceptance gates in docs/ROADMAP.md.

This record is not a promise of autonomous work after the conversation ends. No separate
reasoning agents have been launched. GitHub Actions is used for deterministic tests,
copy verification and preservation, with real success/failure receipts.
