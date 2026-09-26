# ALFRED memory: MAPS, Obsidian and an evidence-backed graph

26 September 2026. This is an original synthesis and implementation plan, not a claim
that the linked guide or Obsidian supplies a complete ALFRED runtime.

## The useful idea in the MAPS guide

Source inspected: https://github.com/pavrus117/ai-os-maps-guide/blob/main/README.md
Inspected README Git blob: 630ddc88fd525af7373c8f77989f9bfbc9815245.

MAPS separates Memory, Agent, Pulse and Screen. Its strongest contribution here is the
operating discipline: a small navigable map, authoritative source files, bounded routines
with records, and a dashboard that presents rather than secretly owns important state.
The guide is a set of prompts and recommendations, not an installable cross-device AI
runtime. Its author's token/latency anecdote is not an ALFRED benchmark.

We adopt the principles where they fit, not the whole configuration. In particular:
- Keep compact signposts and broken-link checks. ALFRED already indexes MAP.md and flags
  missing targets and notes outside its two-hop map.
- Keep one authoritative record for a given decision, with source links elsewhere.
  Conflicting reports may both be legitimate evidence; never erase disagreement simply
  to force every real-world fact into a single note.
- Keep deterministic processing before model calls, bounded work, explicit outcomes and
  a rebuildable screen/index. A dashboard button goes through authenticated authority.
- Do not remove login/CSRF merely because a dashboard is on a private network.
- Do not copy personal/client transcripts into this public repository or blindly sync
  private context between machines using a shared Git folder.
- Do not inherit a provider's subscription assumptions, prices or model access without
  checking the actual service terms for the intended integration.
- Do not treat 'never delete' as universal: consent, retention and deletion requirements
  need a scoped lifecycle, including derived summaries and backups.

The guide has not been copied wholesale into ALFRED. No confirmed reuse licence is
asserted here for its prompts/assets. This document attributes the idea and records
original decisions; the previous licensed upstream snapshots remain unchanged.

## What Obsidian contributes

Obsidian stores Markdown files in a local vault and maintains a rebuildable metadata
cache. Its graph represents notes and their internal links. These are appropriate
human-readable inputs to Alfred, without requiring Obsidian to become its database.
Official sources:
- https://help.obsidian.md/Files+and+folders/How+Obsidian+stores+data
- https://help.obsidian.md/Plugins/Graph+view

Recommended boundary:

```text
Human-owned Markdown / Obsidian vault
       | read-only, explicitly selected folder
       v
Scoped source catalogue + revision/hash index
       |                         |
       v                         v
Note-reference graph       Searchable source passages
       |                         |
       +------ authorised retrieval packet ------+
                                                  |
                              optional tool-free interpretation
                                                  |
                                      evidence + source inspection
```

The source files remain readable without Alfred. The index and visual graph can be
rebuilt. A write to a note, a plugin's instruction, a new link or an alleged 'owner'
property cannot grant account access or execution authority.

Current code supports a bounded Markdown subset, not all Obsidian behaviour. It does not
load .obsidian plugins/settings, follow arbitrary filesystem links or enable third-party
code. Frontmatter can describe title, kind, tags and aliases; it is not executable policy.
Heading/block link fragments identify a file but are not currently anchor-validated.

## Two graphs, not one misleading picture

### Implemented: the source-reference graph

A node represents a note. An edge means a particular line explicitly linked to another
note. It retains the source revision/hash and relation links_to or embeds. This makes
navigation, backlinks, health checks and bounded context expansion useful now.

It does NOT mean that a mentioned person owns a project, a claim is corroborated, a task
is complete or a forecast is happening. The current graph must be labelled accordingly.

### Next: an entity-and-claim graph

Build this separately, as a projection over evidence rather than replacing sources.
Suggested node classes: person, organisation, project, asset, decision, commitment, event
and source. Suggested relations: assigned_to, depends_on, supersedes, reported_by and
supported_by. Every non-trivial relation needs provenance and an explicit basis.

A proposed claim record should include:

```text
claim_id / workspace / subject_id / predicate / object_or_value
source_reference / source_revision / exact_line_range / content_hash
basis: authored | observed | reported | model_proposed
valid_from / valid_until / observed_at / retrieved_at
status: proposed | accepted | disputed | superseded | withdrawn
reviewer / review_time / replacement_claim / evidence_set
```

These fields are a proposed contract, not all implemented tables. The next migration
must be reviewed against the existing event/draft ledger. Begin with explicit author
metadata and manually accepted claims; add model extraction only as a proposal queue.
Entity matching must not merge two people because their names happen to match. Keep
stable IDs and require an explicit resolution path for ambiguous identities.

A model-extracted 'Ada owns Project X' is initially a proposed interpretation. Acceptance
by a user records that user's judgement; it still does not prove the external world is
correct. Conflicting sources remain visible with their different times and scopes.

## Retrieval that earns its complexity

The v0.5 path uses bounded keyword ranking plus explicit outgoing one-hop links. It
returns at most five sources and 6,000 excerpt characters. The optional model can only
interpret those sources, not traverse the host or call arbitrary tools.

Next compare keyword-only, graph-expanded and hybrid retrieval on a saved question set.
Measure answer-supporting source recall, irrelevant context, broken references, leakage,
latency and token volume. Add full-text indexing or embeddings only when they improve
that evidence. No graph database is necessary for the current scale: relational node,
edge and claim tables are sufficient to implement and test the relationships.

An attractive force graph is a view, not the proof that retrieval or reasoning improved.
We should be able to name the source route for an answer and reproduce that route after
restart. A changed source invalidates its dependent projection and future answer packets.

## Memory lifecycle and privacy

Keep the original separation: personal, company and client/operational contexts have
independent grants and retention. A universal-looking interface does not create a
universal permission boundary. Specialist engines receive only a scoped evidence packet.

Separate editable preference memory from original observations, temporary working
context, procedures and derived summaries. Every generated summary needs lineage to
its sources and a revision/expiry rule. A source deletion or revocation must propagate
to current indexes, snippets, embeddings and answer caches. Backup retention needs a
separate explicit policy. Immutable audit is not a reason to keep all private content.

The alpha is not encrypted at the application layer. Use synthetic data. Do not connect
sensitive client notes merely because a local demo appears functional. Screen capture,
voice recording, cloud egress and sharing need separate authorisation and visible state.

## Pulse: what already runs, and what does not

The launched local Desk supervisor scans the configured sample-project and vault folders,
records relevant changes and processes already approved local drafts. It can be paused.
It does not keep running after the host process or machine stops. Signing out hides the
workspace but does not itself stop the separately running process.

The next routine registry should record routine ID, workspace, purpose, host, schedule,
allowed capabilities, inputs, last successful run, next due time, timeout and cost/run
ceilings. A lease and idempotency key prevent duplicate execution after restart. Failed
runs need backoff and visible status. Keep user-initiated, scheduled and event-triggered
work distinct in the ledger. No unbounded 'keep thinking until done' loop.

An always-on home/private host is a later deployment choice. It requires its own service
management, authentication, secret handling, backups and operational monitoring. Nothing
in this delivery has been deployed to the user's devices or made autonomous in the cloud.

## Next acceptance-gated work

1. Validate a real local model with the same evidence questions, explicit uncertainty,
   failed cases and measured latency. The existing adapter tests do not establish quality.
2. Implement reviewed typed claim proposals with evidence lineage and conflict handling.
3. Extend identity, key rotation, retention and source/capability revocation before real
   private data. Preserve the existing proposal/approval/result checks.
4. Add a durable bounded routine registry, plus user-visible pause and run records.
5. Compare one contained runtime and one official read-only account connector, rather
   than installing all archived agents. Browser and external effects need separate gates.
6. Add measured push-to-talk and later device/specialist integrations without changing
   the source/permission boundary. Operational scenarios remain simulated first.

The nearest usable goal remains: a question about authorised work, relevant sources,
a plainly labelled interpretation, an exact approved action and a result that survives
failure. MAPS and Obsidian strengthen the memory layer; they do not replace the rest.
