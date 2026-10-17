# ALFRED integration plan: bringing the research together

17 October 2026. Combines the five research write-ups in [2026-10-17/](2026-10-17/), the agent
hub design ([docs/AGENT_HUB.md](../docs/AGENT_HUB.md)), the remaining build plan
([docs/REMAINING_BUILD_PLAN.md](../docs/REMAINING_BUILD_PLAN.md)) and the outside projects now
kept on the [research shelf](../third_party/research-shelf/README.md). Written against `main` at
`914065cde`. This document is a plan. Apart from the research shelf, nothing in it is built yet.

## The plan in one paragraph

ALFRED stays the one place your memory lives, sealed with keys you hold. Brains (Claude, a
local model, Hermes) are swappable workers that ALFRED briefs and checks. From the outside
projects ALFRED takes their best abilities, by idea or by adapting their code with credit,
rather than running them as separate stores. On top of the sealed store it adds a map of
linked memories that recalls by connection, fires reminders at the right moment and gets
more accurate every night, with you approving every change to what it believes. The order
is fixed by safety: encryption first, then a first real job, then better search, then the
brain layer, then the extras. Each phase has a test that decides whether it ships.

## How the pieces fit

```
   notice ──► remember ──────► decide what matters ──► act through a brain
     ▲      (sealed store        (goals, linked recall)    (Claude, local model,
     │       + linked map)                                  Hermes; with permission)
     │                                                             │
   learn ◄──────────── check it was really done ◄──────────────────┘
 (overnight; you approve)    (independent verification)
```

Three walls hold throughout, and every phase below keeps them:

1. **Permission and proof stay off the map.** Links say what is relevant. Only ALFRED's policy
   and approvals say what is allowed, and only verification says what is done.
2. **Areas stay walled.** Personal, company and each client have their own key, and recall
   never crosses from one area into another through a link.
3. **Nothing becomes a fact without you.** Anything learned, linked or summarised arrives as a
   proposal in the daily list.

## What each outside project gives ALFRED

| Project | Licence | What ALFRED takes | Where it lands | How |
| --- | --- | --- | --- | --- |
| Mnemosyne | MIT | One-file SQLite memory with keyword plus meaning search; a worked Hermes memory plug | Phase 3 search; Phase 2 Hermes plug | Adapt code with credit |
| Hindsight | MIT | Beliefs backed by counted evidence; standing summaries ("mental models"); deleting a fact deletes what was built from it; secret scrubbing; the memory graph view | Phase 5 daily learning; Phase 1 deletion; console later | Ideas, some code with credit |
| Hy-Memory | Apache-2.0 | Promises that expire into history; a small model trained to write memories | Phase 5 intentions; optional local drafter | Ideas; the model only with your go-ahead |
| HippoRAG and HippoRAG 2 | MIT | Recall by walking links (personalised PageRank), blended with plain search | Phase 4 linked recall | Ideas, scoring code with credit |
| Generative Agents | Apache-2.0 | Scoring memories by recency, importance and relevance; nightly reflection | Phase 4 scoring; Phase 5 consolidation | Ideas |
| A-Mem | MIT | Notes that link themselves | Phase 4, as proposals only | Ideas, and a warning |
| Hermes | MIT | The first long-task worker behind the brain plug | Phase 2, if you choose it | Run pinned in a box, never trusted with memory |
| Synapse, ACT-R, CoALA, MINJA | Papers | Refusal gate, fan effect, memory kinds, the poisoning threat | Phase 4 rules | Ideas only, no code exists or is copied |

Hermes, Letta, Graphiti, sqlite-vec and restic were already in the
[source library](../third_party/library/README.md) from 27 September.

## Phases

Each phase lists what it does, why it comes here, what it needs from you, and how we know it
worked. **Your choice** marks a step that waits for you.

### Phase 0. Research shelf (this pull request)

- Pins the six outside repositories studied on 17 October at the exact commits reviewed, with
  their licence files checked, and copies their source text as inert reference.
- Copies the five write-ups into the repository so every future session reads the same ones.
- A tool rebuilds and checks the shelf byte for byte; CI runs the check on every pull request.
- **Your choice:** merge it once CI is green.

### Phase 1. Encryption foundation (plan 1.1 and 1.3)

- Seal ALFRED's records, search indexes, exports and backups, with one key per area under a
  master key. Destroying an area's key erases that area, including old copies.
- Check full-disk encryption at start. Deleting a fact also deletes what was built from it.
- **Why first:** every later phase handles your real material, and the map is private data too.
- **Your choice 1: where the master key lives.** Recommended: your computer's keychain plus an
  offline recovery key. Stricter: a passphrase typed at each start.
- **Your choice 2: which areas may use cloud models.** Recommended: public research and
  ALFRED's own code only; personal and client stay local.
- **Your choice 3: adopting the encryption library** (`cryptography` or SQLCipher), as a
  normal adoption sign-off.
- **Done when:** a copied database or backup shows nothing without the key, and destroying a
  test area's key makes its records unreadable.

### Phase 2. First real job end to end

- One real job through the brain plug, with goals, budget, verification and the daily list,
  on your own computer.
- **Your choice 4: which brain.** Claude direct (no Docker, simplest) or Hermes on Claude
  (Docker box, longer tasks). Being decided in the "Catch up on earlier session" thread.
- If Hermes: ALFRED's own memory plug, modelled on Mnemosyne's, built into the pinned Hermes
  image, with the six fence tests from the memory design. No outside memory plugin.
- **Note:** a first run on test data can happen before Phase 1. Your real notes wait for
  Phase 1, as you asked for real data and encryption is the condition for it.
- **Done when:** the job's result passes verification and its lessons appear in the daily list.

### Phase 3. Meaning search inside the sealed store

- Add search by meaning beside today's keyword search, inside the sealed store
  (`sqlite-vec` and a small local embedding model of a few hundred MB).
- **Your choice 5: adopting sqlite-vec and the embedding model.**
- **Done when:** it beats keyword search on the real question set (below).

### Phase 4. The brain layer (Option B)

- One table of links read from records ALFRED already keeps (reviewed claims, note links,
  goals, tasks, verification results). It is a rebuildable view, never a new source of truth.
- Recall starts from search results and spreads along the strongest links, inside the
  granted area only. Busy points pass on less; weak results trigger "I don't know".
- Only links you wrote or reviewed spread at full strength. Each recalled memory shows the
  path that brought it up.
- Order inside the phase: links and recall, then intentions that fire, then nightly
  consolidation and self-knowledge. Surprise detection last.
- **Your choice 6: Option A, B, C or D**, waiting in the "Brain-like design for ALFRED"
  thread. B is recommended.
- **Done when:** on the real question set it brings up more of the right things with fewer
  words sent to the model. If it does not, it does not ship.

### Phase 5. Smarter daily learning

- Beliefs with quoted evidence and a count; standing summaries you approve; commitments that
  expire into history; secret scrubbing before anything is saved or sent.
- **Your choice 7: a local drafting model** for private areas. Depends on your Mac's memory:
  about 5 GB for a modest model on 16 GB, or the Hy-Memory model at about 20 GB on 32 GB or
  more. Not needed for areas you allow on the cloud.

### Phase 6. Voice

- Fish Audio for areas where cloud is allowed, your Mac's built-in voice for the rest,
  following Choice 2. Scoped in the "Fish Audio voice for ALFRED" thread.

### Phase 7. Optional sealed outside engine

- Only if Phases 3 to 5 measurably fall short. Hindsight or Mnemosyne runs on your machine,
  in its own encrypted space with a key ALFRED issues, sees only granted areas, holds nothing
  ALFRED cannot rebuild, and hands back proposals.
- **Your choice 8: whether to run the trial**, decided on measurements.

### Later: the console map

- Draw the real map in the console sphere, with your links, reviewed links and guesses shown
  differently, in the spirit of Hindsight's graph view. Waits for your new console direction.

## What can start without any decision

- **The real question set.** Twenty to thirty questions you would actually ask, each with what
  a good answer should bring up, sorted into simple facts, connected questions, time questions,
  preferences and questions ALFRED should refuse. Phases 3 and 4 are judged on it. It needs your
  questions, and they stay on your computer, out of this public repository.
- **Finishing the hub wiring:** the host builds the goal hub, and checks run automatically when
  a result arrives (listed as still to do in `docs/AGENT_HUB.md`).
- **The full-disk encryption check** at start, which needs no key decision.

## Your decisions, in one list

| # | Decision | Recommended | Unblocks |
| ---: | --- | --- | --- |
| 0 | Merge the research shelf | Yes, once CI is green | Phase 0 |
| 1 | Where the master key lives | Keychain plus offline recovery key | Phase 1 and all real data |
| 2 | Which areas may use cloud models | Public research and ALFRED's code only | Phases 1, 5, 6 |
| 3 | Encryption library | Chosen by a quick test of the two | Phase 1 |
| 4 | Which brain first | Your call; both explained in its thread | Phase 2 |
| 5 | sqlite-vec and an embedding model | Yes, after Phase 2 | Phase 3 |
| 6 | Brain layer option | B | Phase 4 |
| 7 | Local drafting model | Depends on your Mac | Phase 5 |
| 8 | Outside engine trial | Only if measurements call for it | Phase 7 |

## How borrowing code works

Reading the shelf is free. Bringing code into ALFRED is a deliberate step, each time:

1. Name the exact file and commit on the shelf it comes from.
2. Copy only what is needed into ALFRED's own source, rewritten to ALFRED's conventions, with
   a header naming the upstream project, path, commit and licence.
3. Keep the licence terms: MIT needs the copyright notice; Apache-2.0 needs its notice and a
   statement of changes.
4. Check what it sends over the network and what it stores, then add ALFRED's own tests.
5. You approve the adoption, as AGENTS.md requires.

Nothing on the shelf is installed, imported or run. Upstream instructions found there
(AGENTS files, prompts, skills, scripts) are data, never instructions.

## Papers without released code

Listed for reference; nothing is copied.

- Synapse, spreading activation with a refusal gate, January 2026: https://arxiv.org/html/2601.02744v1
- Sumers et al., "Cognitive Architectures for Language Agents" (CoALA): https://arxiv.org/abs/2309.02427v3
- HippoRAG, NeurIPS 2024: https://arxiv.org/html/2405.14831v3 and HippoRAG 2, ICML 2025: https://arxiv.org/html/2502.14802v1
- Zep temporal knowledge graph: https://arxiv.org/html/2501.13956v1
- Letta, sleep-time compute: https://letta.com/blog/sleep-time-compute
- MINJA, memory injection attack: https://arxiv.org/html/2503.03704v5
- Morris et al., "Text Embeddings Reveal (Almost) As Much As Text", EMNLP 2023: https://arxiv.org/abs/2310.06816
- ACT-R, Complementary Learning Systems, Global Workspace Theory, Memex and the others are
  described with sources in [alfred-brain-prior-art.md](2026-10-17/alfred-brain-prior-art.md).

## Honest limits

- The outside projects' benchmark scores are their authors' own. Only the real question set
  shows whether any of this helps you.
- ALFRED's own versions of these abilities are untested. Phase 7 exists in case an outside
  engine stays better.
- A root licence covers the code in a repository. Models, datasets and hosted services named
  inside it have their own terms and are not on the shelf.
