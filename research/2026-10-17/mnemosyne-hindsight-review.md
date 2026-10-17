# Mnemosyne and Hindsight for ALFRED

17 October 2026. Read-only review of `mnemosyne-oss/mnemosyne` at `c396ef7` and
`vectorize-io/hindsight` at `5331da2f4`, against ALFRED `main` at `914065cde`. Nothing was
installed or run, and nothing in ALFRED was changed. Companion to
[hy-memory-review.md](hy-memory-review.md).

## Short answer

Both are memory plugins for Hermes itself. They sit in Hermes's official plugin catalogue,
pinned to exact commits, and each one takes over Hermes's single outside-memory slot. That
slot is the one ALFRED plans to fill with its own memory, so neither should be installed
into Hermes for ALFRED.

Both are better projects than Hy-Memory for ALFRED's purposes, and each is useful in a
different way:

- **Mnemosyne** is the closest technical match to ALFRED: one local SQLite file, keyword
  plus vector search, no cloud, MIT licence. It is the best reference to read when ALFRED
  builds its own Hermes memory plug (H5), and a strong candidate for the optional memory
  engine decision (M07).
- **Hindsight** is the most mature and best-evidenced memory engine of the three, and it
  handles evidence and deletion in a way close to ALFRED's rules. It is heavy (a server, a
  Postgres database and a model call for every memory saved), and its Hermes plugin sends
  every conversation turn to Vectorize's cloud by default. Keep it as an M07 candidate only
  if measurements later show ALFRED needs that strength.

Reading their Hermes plugins also showed two more ways a memory plugin can get round
Hermes's write approval, which ALFRED's fence tests should cover.

## At a glance

| | Mnemosyne | Hindsight | Hy-Memory (earlier review) |
| --- | --- | --- | --- |
| Who | Open-source community, started April 2026 | Vectorize AI, Inc., started October 2025, with a paid cloud | Tencent, public since 16 October 2026 |
| Licence | MIT (contributors sign a CLA) | MIT, including its integrations | Apache-2.0 |
| History | 1,533 commits, 123 contributors; version 4.0.0 beta 5 | 3,700 commits, 297 contributors | 16 public commits |
| Size | About 62,000 lines, 281 test files | About 176,000 lines in the server, 648 test files | About 75,000 lines plus a 400,000-line app |
| Storage | One SQLite file with FTS5 keyword search and sqlite-vec vectors | PostgreSQL with pgvector (embedded or external) | ChromaDB, Kuzu and SQLite |
| Needs a model to save memories? | No; local embeddings only | Yes, every save uses a model to extract facts | Only in its smarter modes |
| Default network use | None with local embeddings; remote embedding (OpenRouter) only if configured | Hermes plugin defaults to Vectorize's cloud | Example configuration uses DeepSeek and Alibaba |
| Hermes plugin | Yes, in Hermes's catalogue | Yes, in Hermes's catalogue | Via MemHub (an add-on, not in the catalogue) |
| Benchmarks | BEAM 65.2% (on an older version); withdrew an unsupported LongMemEval claim | BEAM 73.4% and LongMemEval 94.6% (as quoted in Mnemosyne's comparison); Hindsight says outside researchers reproduced its LongMemEval result | Self-reported, two days old |

## What each does

**Mnemosyne** keeps three layers in one SQLite file: a short-lived working memory, a
long-term store searched by keyword and vector together, and a knowledge graph of dated
facts that can be ended or marked invalid. It runs on a Raspberry Pi, works with Claude
Code, Cursor and others over MCP, and can sync between machines with the content encrypted
before it leaves your device. Its README is unusually candid about benchmark caveats.

**Hindsight** saves memories by having a model pull out facts, people, dates and links. It
recalls by combining four searches and re-ranking the results. In the background it
builds "observations", beliefs backed by quoted evidence and a count of supporting
memories, and "mental models", standing answers to questions such as "what are this
person's preferences?" that it keeps rewriting. When you delete a memory, every
observation built from it is deleted too. It also has optional scanning that strips
secrets and personal details before saving.

## Why neither goes into Hermes

1. **One slot.** Hermes accepts its built-in memory plus one outside provider
   (`agent/memory_manager.py` in ALFRED's inert Hermes copy). ALFRED's plan takes that slot
   so Hermes only recalls what ALFRED grants for each task.
2. **Both save every turn without asking.** Mnemosyne saves each of your messages and
   picks up identity details automatically (`sync_turn`, default `sync_roles: ["user"]`).
   Hindsight's plugin saves every turn by default (`auto_retain: true`) and never checks
   Hermes's `memory.write_approval`. ALFRED's rule is that facts about people, money,
   commitments and procedures always ask.
3. **Mnemosyne lets the model approve its own staged writes.** With write approval on, its
   save tool stages a write and tells the model to "use `mnemosyne_apply_pending` to
   commit", which is a tool the model itself can call
   (`integrations/hermes/src/mnemosyne_hermes/tools.py`). Hermes's real approval is a person
   typing `/memory approve`. The staging step therefore gives no real protection.
4. **Hindsight's plugin defaults to the cloud**, and its setup step downloads templates
   from the unpinned main branch on GitHub, which undercuts the catalogue's exact-commit
   pin.

## Where each could help

**Mnemosyne, now, as reading material.** ALFRED still has to build its own Hermes memory
plug (H5). Mnemosyne's plug is the most thorough working example of that interface: it
handles session switches, keeps writes tied to the session they came from, and makes
replays safe when two processes race. Under its MIT licence ALFRED could adapt pieces with
the notice kept, through the usual source-library steps.

**Mnemosyne, later, for M07.** ALFRED already uses SQLite and FTS5, and `sqlite-vec` is
already in its source library as an M06 candidate. Mnemosyne shows that stack working as a
full memory system, with mixed keyword and vector scoring and compact binary vectors. It is
the lowest-cost engine to test against M07's rule that provenance, review status and
deletion survive a round trip.

**Hindsight, later and only if measured.** Of the three it best matches ALFRED's evidence
and deletion rules. Two of its ideas fit ALFRED's daily learning without adopting any code:
- *Observations with a proof count*: a learning proposal could show how many separate
  pieces of evidence support it.
- *Mental models*: a standing, reviewed page such as "the owner's writing preferences" that
  ALFRED refreshes and you approve, so task packets carry a short settled summary.

**Mnemosyne's encrypted sync** is also worth reading for M05 and M09, since ALFRED forbids
file-syncing a live SQLite database and still needs a safe way to sync between machines.

## Fence tests to add to H5

These come from reading all three plugins and apply whatever memory ALFRED plugs in:

1. No tool visible to Hermes can commit staged memory or skill writes. Only ALFRED's own
   approval does that.
2. Every turn Hermes hands to its memory plug goes to ALFRED only, and the built-in memory
   stays off, so nothing is saved outside ALFRED's review.
3. Hermes's own tools cannot write into its home's `skills` folder, and every skill folder
   found there at harvest becomes a proposal (from the Hy-Memory review).
4. Installing or setting up a plugin makes no network fetch beyond the pinned commit.

## Effect on your cloud or local choice for Hermes

None directly. If you choose local, Mnemosyne shows a fully local memory stack running on
very modest hardware. If you choose cloud for Hermes's model, that still need not mean
cloud memory, since ALFRED keeps memory on your side either way.

## Sources

- https://github.com/mnemosyne-oss/mnemosyne (commit `c396ef7`), README and
  `integrations/hermes/src/mnemosyne_hermes/`
- https://github.com/vectorize-io/hindsight (commit `5331da2f4`), README,
  `hindsight-docs/docs/developer/observations.mdx`, `hindsight-integrations/hermes/`
- ALFRED inert Hermes copy: `third_party/library/snapshots/NousResearch__hermes-agent`
  (`plugin-catalog/mnemosyne.yaml`, `plugin-catalog/hindsight.yaml`,
  `agent/memory_manager.py`, `hermes_cli/write_approval_commands.py`)
- ALFRED: `docs/AGENT_HUB.md`, `plans/memory-backlog.json` (M06, M07)

## Notes from a setup video the owner shared (17 October)

A walkthrough installing both into Hermes adds these practical points:

- `hermes update` rebuilds Hermes's managed Python environment and removes extra packages,
  so ALFRED's memory plug should be built into the pinned Hermes container image.
- A memory store must run outside Hermes's sandboxed terminal to survive it; ALFRED's
  design already keeps memory outside Hermes.
- The video's setup sets memory scope to global, shares one bank across all agents and
  saves whatever the user says at once. ALFRED deliberately does the opposite on all three.
- Hindsight ran locally with GPT-OSS 20B (about 13 GB) through Ollama in Docker, so a local
  engine of that kind is realistic on a capable machine. The model must support tool calls.
- Hindsight's graph dashboard of memories is a possible console idea, provided it marks
  approved, proposed and speculative items apart (console work is deferred).
