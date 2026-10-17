# Hy-Memory and ALFRED: second review

17 October 2026. Read-only review of `Tencent-Hunyuan/Hy-Memory` at commit `20b92d8`, its
model card and papers, against ALFRED `main` at `914065cde`. Nothing was installed or run,
and nothing in ALFRED was changed.

## Short answer

Hy-Memory should not become Hermes's memory, and ALFRED should not run MemHub beside
Hermes. It is worth keeping for three narrower jobs, all later and all behind ALFRED's
review: a candidate for the planned semantic memory adapter (M07), a possible local model
that drafts items for the daily learning list, and a source of design ideas. Reading it
also turned up one gap in the Hermes fence plan that is worth fixing now.

## Corrections to my first answer

My first reply relied on the repository's front page and got three things wrong.

- **Size and history.** It went public on 16 October with 16 commits, not one. The SDK is
  about 75,000 lines of Python with 103 test files, and the MemHub desktop product adds
  about 400,000 lines. It is a serious codebase, though only one day old in public.
- **Hermes support.** MemHub already installs into Hermes: it adds an MCP recall server to
  `~/.hermes/config.yaml` and drops a skill into `~/.hermes/skills`
  (`memhub/packages/host-bridge/src/recall-installer.ts`, written against Hermes v0.21.0).
- **It has a governance layer.** MemHub keeps source evidence before any model work, keeps
  separate permissions for reading a source, sending content to a model and letting a host
  recall, and treats a lost or timed-out write as "unknown" rather than retrying blindly.
  Much of that matches ALFRED's own rules closely.

## What it is

| Part | What it does |
| --- | --- |
| Hy Memory SDK (`hy-memory` on PyPI, 2.0.3) | Python library. Extracts facts from chats, work tasks and coding sessions, stores them in local ChromaDB, Kuzu and SQLite, and searches them. Three modes: `lite` (no AI model, vector search only), `pro` (a model extracts and reconciles facts), `ultra` (adds overnight pattern-finding). |
| MemHub | Local-first desktop app and CLI that imports your history from Claude Code, Cursor, Codex, Hermes and others into one memory, then lets those tools recall from it. macOS and Linux only. |
| Hy-Memory-30B-A3B | A model trained only to write memories. About 30B parameters, 3B active per token, so it can run locally on a well-equipped Mac through community quantisations (Ollama, llama.cpp). |

**Licence.** Apache-2.0 for the code and, per the `LICENSE` text and the model card, the
weights. That is clean for ALFRED. PyPI release 2.0.1 carries older licence metadata, so
any pin should be 2.0.2 or later. Its dependencies (ChromaDB, Kuzu, optional Neo4j and
others) carry their own terms and would need the usual source-library review.

**Maturity.** It has peer-reviewed research behind it (an EMNLP 2026 paper and a benchmark
submitted to ICLR 2027), but the public code is one day old. On that day alone the team
removed MemHub's per-task permission layer and its global consent switch
(`CHANGELOG.md`, "Removed MemHub's task-scoped HyPermission store wrappers"), while
`memhub/docs/ARCHITECTURE.md` still describes that consent switch. The security policy has
no response commitment yet.

**Benchmark claims.** The memory-writing model scores 55.49 against 54.62 for Claude Opus 5,
averaged across four memory frameworks. These are Tencent's own figures on fixed 20%
samples of the benchmarks, published two days ago, and results are mixed per benchmark
(Claude Opus 5 leads on LoCoMo in two of the frameworks).

## Where it conflicts with ALFRED

1. **Hermes has one external memory slot, and ALFRED takes it.** Hermes's
   `agent/memory_manager.py` accepts the built-in provider plus at most one external
   provider. ALFRED's plan (docs/AGENT_HUB.md, "Redirect its memory and learning") fills that
   slot with ALFRED's own per-task provider and refuses plugins that would add another
   memory store. MemHub's MCP route into Hermes would be exactly that second store.
2. **The model decides what is true, with no review step.** The reconciler
   (`hy_memory/agent/reconciler.py`) lets the model add, merge, supersede or hide facts. A
   memory is either active or hidden; there is no "proposed, waiting for the owner" state.
   ALFRED's rule is that facts about people, money, commitments and procedures always ask.
3. **Deletion leaves copies.** `client.delete` copies the deleted text into a history
   store, and if the graph clean-up fails it logs a warning and still reports the item as
   deleted (`hy_memory/client.py`, `async_delete`). ALFRED's M05 needs a deletion receipt
   that covers every copy.
4. **Default settings send data abroad.** The example configuration sends text to
   DeepSeek's API and embeddings to Alibaba's DashScope. Both can be pointed at a local
   endpoint, but the defaults are cloud services. The SDK also leaves ChromaDB's anonymous
   usage telemetry on (Chroma's documented opt-out is `anonymized_telemetry=False`).
5. **MemHub reads your other AI tools' history.** With your permission it imports Claude
   Code, Cursor and similar logs. That is legitimate for its purpose, but it is a second
   capture route outside ALFRED's grants (M02), so it does not belong next to ALFRED.

## Where it could help

**1. A candidate for M07, the optional semantic memory adapter.** `plans/memory-backlog.json`
already plans one decision on whether an outside engine adds measured benefit, with
candidates Graphiti, Cognee, Mem0, Basic Memory, LightRAG and GraphRAG. Hy-Memory belongs on
that list. Its `lite` mode (no model, local storage) is the fair starting point. It would
have to pass M07's own test, that provenance, review status and deletion survive a round
trip, and the history-copy issue above would need fixing or wrapping first. M07 waits on
M02, M05 and M06, so this is not urgent.

**2. A local model that drafts learnings.** ALFRED's daily learning job (H3) is
deterministic today and has no model. A model that only *drafts* items for the one-tap
daily list, never accepting them, is the safe use of a memory writer, and one that runs on
your own machine keeps personal text local. Hy-Memory-30B-A3B is purpose-built for that and
Apache-licensed. Trying it would be a new model evaluation, which needs your go-ahead and
must not reuse or reroute the blocked live-model comparison.

**3. Ideas worth borrowing, written ALFRED's way.**
- *Intentions*: plans and promises that expire on a date and then become ordinary history.
  This fits M10 (commitments and attention).
- *Deleting a correction restores the previous fact.* A sensible rule ALFRED should decide
  on deliberately for its own supersession chains.
- *Four separate permissions*: read a source, keep syncing it, send its content to a
  model, let a host recall it. A useful checklist for M02 grants.
- *Diff chain*: for coding memory, store how code changed, not just the latest version.

## A gap in the Hermes fence that this review found

MemHub's installer notes that a skill folder placed by hand into `~/.hermes/skills` loads as
enabled, and that `hermes skills audit` does not check it. ALFRED's own inert Hermes copy
confirms this: `do_audit` in `hermes_cli/skills_hub.py` only scans skills recorded in the
hub lock file. ALFRED relies on Hermes's `skills.write_approval` to stage skill writes, but
Hermes could bypass that by writing a skill folder directly with its file tools. It would
then run, unreviewed, for the rest of that task.

Suggested addition to H5's fence tests: Hermes's file and terminal tools cannot write inside
its own home's `skills` folder, and at harvest every skill folder found there becomes a
proposal, however it got there. The fresh home per task already stops it carrying over
between tasks.

## Effect on the cloud or local choice for Hermes

None directly. If you lean towards local, the memory-writing model is one more reason local
could work well later for extraction. The choice for Hermes's first run is still yours.

## Sources

- Repository: https://github.com/Tencent-Hunyuan/Hy-Memory (commit `20b92d8`)
- Model card: https://huggingface.co/tencent/Hy-Memory-30B-A3B
- Writer paper: https://arxiv.org/abs/2610.22196
- System paper: https://arxiv.org/abs/2606.09483
- Chroma telemetry: https://docs.trychroma.com/telemetry
- ALFRED: `docs/AGENT_HUB.md`, `plans/memory-backlog.json`, inert Hermes copy under
  `third_party/library/snapshots/NousResearch__hermes-agent`
