# Has anyone built a brain-like memory? What ALFRED can learn

17 October 2026. Follows [alfred-brain-like-design.md](alfred-brain-like-design.md) and the
3D model. the owner asked three things: has anyone done this, what can ALFRED learn from them, and
is this the thing that connects everything together, engineered the way Elon Musk's teams
work. Research only; nothing has been built or installed.

## The short answer

1. **Yes, many people have built pieces of it**, from a 1945 essay to papers published this
   year. The evidence is good for one piece in particular: following links between memories
   finds connected answers that plain search misses, and sends the model far fewer words.
2. **I found no project that combines it with what makes ALFRED different**: private and
   encrypted per area, every learned fact approved by you, deletion that really deletes, and
   many brains with one authority. That combination is ALFRED's own ground. (This is from my
   searching, so treat it as a strong impression rather than proof.)
3. **Is it the thing that connects everything? Mostly yes.** A shared map of linked
   memories is what lets goals, promises, notes, people, results, learning and the console
   all talk about the same things. Two parts must stay outside the map on purpose:
   **permission** and **proof that work was done**. What gives the map its power is the loop
   it sits in, described below.
4. **The biggest surprise: ALFRED already stores most of the map.** Its reviewed memory is
   already kept as "subject, relationship, object, valid from, valid until". Nothing walks
   those links yet. So the next step is smaller than it sounds.

## Who has done what

| Work | When | What it does | What ALFRED takes | What to avoid |
| --- | --- | --- | --- | --- |
| **Memex**, Vannevar Bush, "As We May Think" | 1945 | A personal desk-machine that stores everything you read, joined by "associative trails" because, Bush argued, the mind works by association | The original goal: your own trails, kept by you | Nothing; it was never built |
| **ACT-R**, John Anderson and colleagues | 1990s to now | A tested model of human memory. Each memory has an activation that rises with use and falls with time; related memories pass activation along links; a memory with many links passes less to each (the "fan effect") | The maths for strengthening and fading, and the fan effect so that a hub such as "the owner" does not wake everything | Modelling the whole mind |
| **Complementary Learning Systems**, McClelland, McNaughton, O'Reilly | 1995 | Brains need a fast store for new things and a slow store for proven knowledge, joined by replay during sleep | Already ALFRED's inbox-then-review design | |
| **Global Workspace Theory**, Bernard Baars | 1988 | Many specialists, one small shared stage where whatever wins attention is broadcast | ALFRED's task packet is that stage: a small, chosen working memory each brain sees | |
| **LeCun's proposal**, "A Path Towards Autonomous Machine Intelligence" | 2022 | An architecture of separate modules: a configurator (executive), perception, a world model, a cost module, an actor and short-term memory | Validates the hub: ALFRED as configurator and cost (goals, budgets, policy), brains as actors | Building a predictive world model now; that is a research programme |
| **Generative Agents**, Park et al., Stanford | 2023 | Simulated people with a memory stream scored by recency, importance and relevance, plus periodic reflection into higher-level insights | The three-part score; reflection as a nightly job | Reflections that become facts with no review |
| **CoALA**, Sumers et al., Princeton | 2023, TMLR 2024 | A blueprint for agent minds: working, episodic, semantic and procedural memory, with an explicit decision loop | A common vocabulary; ALFRED already matches it | |
| **HippoRAG**, Gutiérrez et al., NeurIPS 2024 | 2024 | Copies the hippocampus: builds a graph from text, then spreads from the question's key ideas through the graph (personalised PageRank) | Proof that spreading through a graph answers multi-step questions: up to 20% better than standard retrieval, 10 to 20 times cheaper and 6 to 13 times faster than repeated searching | Building the graph by letting a model extract facts unchecked |
| **HippoRAG 2**, ICML 2025 | 2025 | Adds the original passages to the graph and an extra relevance filter | **An important warning**: earlier graph methods (GraphRAG, RAPTOR, LightRAG) did *worse* than plain meaning search on simple fact questions. Graph recall must be blended with normal search, never replace it | Graph-only retrieval |
| **Zep and Graphiti** | Jan 2025 | A graph that records when a fact was true and when it was learned, and retires old facts when new ones contradict them | Cut a 115,000-word context to about 1,600 and improved accuracy on a long-memory test (60% to 71% with GPT-4o); the "true when, learned when" pattern | Letting a model retire facts automatically; ALFRED makes that a proposal. Needs Neo4j, so a second database to encrypt |
| **Letta sleep-time agents** | Apr 2025 | The agent that talks to you cannot edit memory; a separate background agent reorganises memory while idle, possibly on a different model | Confirms ALFRED's rule that workers never commit memory; the night job can use a stronger or local model | |
| **A-Mem**, NeurIPS 2025 | 2025 | Zettelkasten-style notes that link themselves and update older notes as new ones arrive | Linking new items to old ones overnight | Notes rewriting older notes without review |
| **Synapse**, Jiang et al. | Jan 2026 | Spreading activation over a combined events-and-facts graph, with fading, a cap on links per memory, and a refusal gate when nothing is strongly activated | The closest match to Option B. Beat Zep, A-Mem and MemGPT on the LoCoMo long-conversation test (40.5 against 39.7, 33.3 and 28.0), with the biggest gains on time and multi-step questions, and claims 95% fewer words sent. The **refusal gate** is a direct way for ALFRED to say "I don't know" | Its scores are the authors' own; code not yet released |
| **Survey**, "Memory for Autonomous LLM Agents" | Mar 2026 | Reviews the field from 2022 to early 2026 | Says consolidation and forgetting are the least solved parts, retrieval quality is the real bottleneck, and deleting from model weights is "far from production-ready" | |
| **Microsoft Recall** | 2024 | A record-everything memory for Windows | A lesson: it faced a backlash until it became opt-in, encrypted and locked behind sign-in | Capturing everything by default |
| **MINJA**, memory injection attack | 2025, revised 2026 | An ordinary user, only by asking questions, plants records in a shared agent memory that later mislead it | Injection succeeded 98% of the time; decay, filters and isolation did not reliably stop it. A linked memory would *spread* a planted link further, so this shapes the design below | |

## What the evidence actually says

- **Linked recall works where questions connect several things**: multi-step, time-based and
  "what relates to what" questions (HippoRAG, Synapse).
- **It can hurt simple look-ups** if used alone (HippoRAG 2). Blend it with keyword and
  meaning search.
- **The efficiency gain is real and large**: far fewer words sent to the model for the same
  or better answers (Zep, Synapse). That is where money and speed come from.
- **Consolidation and forgetting are unsolved in the field.** ALFRED's approval list is a
  practical answer the research community has not standardised.
- **Poisoning is the main danger.** A linked memory amplifies a bad link. Review before
  anything counts is the strongest defence available, and ALFRED already has it.
- These are mostly benchmark results on public conversation data, reported by the authors.
  None of it proves the same gains on your life. Only a test on your own questions will.

## What ALFRED already has

From the code on `main` (`914065cde`):

- **Reviewed memory is already a graph.** `alfred/reviewed_memory.py` stores each claim as a
  subject, a relationship, an object, `valid_from` and `valid_until`, with its source note,
  revision and quoted lines. That is Zep's "true when" pattern, with proof attached.
- **Links already exist in several separate places**: note links (`knowledge_refs`), the
  sources behind drafts and actions, tasks tied to goals (`hub_tasks`), and verification
  results. Today each module keeps its own and none of them walk across the others.
- **The architecture already allows a graph** as a "rebuildable projection", never an
  authority (`docs/MEMORY_ARCHITECTURE.md`), and it already says recall must not cross a
  permission boundary through a neighbour.
- **The console rules already demand** that a graph view separate authored links, reviewed
  links and guesses.
- **The source library holds inert copies** of Graphiti, Cognee, Letta, Mem0, GraphRAG and
  Basic Memory to read from. Nothing there is installed or run.

## Is this the thing that connects everything?

From first principles, ALFRED exists to bring the right thing to the right brain at the
right moment, act only with permission, prove the result, and get better at it every day.
Every part of ALFRED serves one step of that loop:

```
   notice  ──►  remember  ──►  decide what matters  ──►  act through a brain
     ▲            (the map)        (goals, activation)       (with permission)
     │                                                              │
   learn   ◄──────────────  check it was really done  ◄─────────────┘
 (overnight, you approve)       (independent verification)
```

The linked map sits at the centre of that loop, and it is what lets the other parts share
one picture:

| Part of ALFRED | Today | As a view of the map |
| --- | --- | --- |
| Goals | Their own table | Points on the map that tasks, people and promises link to |
| Commitments and reminders | Their own records | Intentions that fire when a linked person or topic comes up |
| Notes and reviewed memory | Claims and note links | The core of the map |
| Brains and routing | Routing notes | Brains link to kinds of work, weighted by verified results |
| Daily learning | A list of proposals | Proposed new points and links, approved by you |
| Verification | Results per task | Strengthens the links that led to checked, correct work |
| Console sphere | Fictional fixtures | Draws the real map, with your links, reviewed links and guesses shown differently |
| Areas (personal, company, client) | Scope fields | Walls on the map that recall cannot cross |

**What must stay off the map:** permission and proof. Links can tell ALFRED what is
*relevant*; they must never tell it what is *allowed* or what is *done*. ALFRED's own rules
already say graph edges cannot grant permission, and MINJA shows why: if a planted link could
open a door, one bad email could open it. Engineers call this keeping the data plane (the map)
apart from the control plane (policy, approvals, verification).

**Verdict:** yes, this is the connecting layer, with those two walls kept. It turns several
separate link lists into one map, gives every part the same picture, and turns the console
sphere from decoration into the real thing. The loop is what makes it powerful: each pass
through it leaves the map a little more accurate, and you approve every step that changes
what ALFRED believes.

## Musk's five steps, applied

Walter Isaacson's biography records the algorithm Musk drills into his teams, always in this
order. Applied to ALFRED's brain layer:

| Step | Musk's rule | For ALFRED |
| --- | --- | --- |
| 1. Question every requirement | Requirements from clever people are the most dangerous, because nobody questions them | The real requirement behind "brain-like" is *the right memories, at the right moment, in fewer words, privately, with proof*. Anything brain-like that does not serve that is cut |
| 2. Delete parts | Delete until you have to add about 10% back | No graph database, no second store, no outside memory engine, no agent swarm, no surprise detection yet, no model training. The map is built from records ALFRED already keeps |
| 3. Simplify | Never optimise a part that should not exist | One link table that reads the existing link sources; one scoring function (search seeds, spread, blend); a few hundred lines |
| 4. Speed up the cycle | Only after the first three | Build the test set of your real questions first, so every change is measured in minutes. The nightly loop gives ALFRED one learning cycle a day |
| 5. Automate last | His factories failed by automating first | Approvals stay manual. Only low-risk kinds (writing style) may auto-accept, and only after the evidence shows they are reliable |

The phrase his engineers use is "the best part is no part". The strongest case for the map is
that it removes the need for each module to keep its own linking logic.

## Updated recommendation: Option B, sharpened by the research

Still Option B from the earlier write-up, with these changes:

1. **The map is a rebuildable projection.** It is built from records ALFRED already keeps
   (claims, note links, goals, tasks, verification results). Link strengths come from receipts
   of use and verification, so they can be rebuilt too. Delete a record, rebuild, and it is
   gone from the map. No new source of truth, and it is sealed with everything else.
2. **Blend with normal search.** Keyword and meaning search pick the starting points; spreading
   activation (ACT-R style, or personalised PageRank as in HippoRAG) finds the connected
   ones; one score mixes both. This answers HippoRAG 2's warning.
3. **Fan effect and caps.** Busy points pass less to each neighbour, and each point keeps
   only its strongest links in play, as in ACT-R and Synapse.
4. **A refusal gate.** If nothing lights up strongly, ALFRED says it does not know rather
   than guessing (from Synapse).
5. **"True when" and "learned when".** Claims already carry validity dates; recall also
   records when ALFRED learned each one, as Zep does.
6. **Poison guard.** Only links you wrote or reviewed spread at full strength. Suspected
   links spread weakly and never start a search. Outside material (emails, web pages, worker
   output) can propose links but never review them. Every recalled memory shows the path that
   brought it up, so you can see why it appeared.
7. **Measure first.** Twenty to thirty of your real questions, sorted into simple facts,
   connected questions, time questions, preferences and questions ALFRED should refuse. Run
   them before and after. If the map does not beat today's search, it does not ship.

**Order** is unchanged: encryption, your first real run with the brain you choose, meaning
search, then this layer. The test question set could be written any time, since it is just
your questions and the answers you would expect.

## What it costs

The same as before: small to medium build effort spread over steps, no new dependencies, no
new database, no new server, and no running cost beyond the nightly job's model calls. The
research suggests it should *lower* model costs by sending fewer words per task.

## Your choice

The options A to D in [alfred-brain-like-design.md](alfred-brain-like-design.md) stand, with
B sharpened as above. Nothing gets built until you pick.

## Sources

- Bush, "As We May Think", The Atlantic, 1945.
- Anderson et al., ACT-R; McClelland, McNaughton and O'Reilly, "Why there are complementary
  learning systems in the hippocampus and neocortex", 1995; Baars, *A Cognitive Theory of
  Consciousness*, 1988. (Background from my own knowledge, not re-checked online today.)
- Park et al., "Generative Agents", UIST 2023 (from my own knowledge).
- LeCun, "A Path Towards Autonomous Machine Intelligence", 2022:
  https://www.shaped.ai/blog/yann-lecun-a-path-towards-autonomous-machine-intelligence
- Sumers et al., "Cognitive Architectures for Language Agents": https://arxiv.org/abs/2309.02427v3
- Gutiérrez et al., "HippoRAG", NeurIPS 2024: https://arxiv.org/html/2405.14831v3
- "From RAG to Memory" (HippoRAG 2), ICML 2025: https://arxiv.org/html/2502.14802v1
- Rasmussen et al., "Zep: A Temporal Knowledge Graph Architecture for Agent Memory", 2025:
  https://arxiv.org/html/2501.13956v1
- Letta, "Sleep-time compute", April 2025: https://letta.com/blog/sleep-time-compute
- Xu et al., "A-Mem: Agentic Memory for LLM Agents", NeurIPS 2025:
  https://proceedings.neurips.cc/paper_files/paper/2025/hash/19909c36f51abc4856b4560aff3d36d6-Abstract-Conference.html
- Jiang et al., "Synapse: Empowering LLM Agents with Episodic-Semantic Memory via Spreading
  Activation", January 2026: https://arxiv.org/html/2601.02744v1
- Du, "Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers",
  March 2026: https://arxiv.org/html/2603.07670v1
- Dong et al., "Memory Injection Attacks on LLM Agents via Query-Only Interaction" (MINJA):
  https://arxiv.org/html/2503.03704v5
- Microsoft Recall overhaul: https://www.engadget.com/microsoft-moves-to-resolve-privacy-concerns-over-its-recall-feature-170318905.html
- Musk's five steps, from Isaacson's biography:
  https://corporate-rebels.com/blog/musks-algorithm-to-cut-bureaucracy
- ALFRED: `alfred/reviewed_memory.py`, `alfred/knowledge.py`, `alfred/hub_goals.py`,
  `docs/MEMORY_ARCHITECTURE.md`, `AGENTS.md`, `third_party/library/CATALOGUE.json`
