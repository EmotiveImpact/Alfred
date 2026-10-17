# ALFRED memory: the best setup that keeps encryption

17 October 2026. A proposal built on the three engine reviews in this folder and on
ALFRED `main` at `914065cde`. Nothing has been installed or changed.

## The answer in brief

Make ALFRED the only place your memory lives, sealed with keys you hold, and build the best
abilities of Mnemosyne, Hindsight and Hy-Memory into it. Their code is open-licence (MIT or
Apache-2.0), so ALFRED can borrow both their ideas and, with credit, their code. Outside
engines stay allowed, but only in a **sealed, throwaway** form, and only if tests show they
beat ALFRED's own version. You keep all three projects' strengths and lose no encryption.

This changes my earlier "all three as engines behind ALFRED" suggestion. In that version,
each engine kept its own permanent database, and neither engine can encrypt one.

## What is true about encryption today

- **ALFRED does not encrypt yet.** Plan item 1.1 in `docs/REMAINING_BUILD_PLAN.md` designs
  it (`alfred/crypto.py`, sealed fields, encrypted backups and exports), and it waits on
  your decision about where the key lives. Real private data waits on it too.
- **Neither Mnemosyne nor Hindsight encrypts its own database.** Mnemosyne's
  `docs/security.md` says local data is protected by file permissions and recommends
  full-disk encryption; it encrypts only what it syncs to another machine. Hindsight's
  server code contains no encryption at all and stores everything in PostgreSQL, which has
  no built-in file encryption. Hy-Memory has none either.
- **Search indexes count as private text.** Researchers have shown that the original
  wording can often be rebuilt from an embedding ("Text Embeddings Reveal (Almost) As Much
  As Text", EMNLP 2023). So a meaning-search index is as sensitive as the notes it came
  from, and it must be encrypted too.

So running the engines as permanent stores would leave plaintext copies of your memory,
and of its search indexes, outside ALFRED's encryption. That was the risk I flagged.

## Options considered

| Option | Encryption | Deletion | ALFRED in control | Memory quality | Effort |
| --- | --- | --- | --- | --- | --- |
| 1. Plug Mnemosyne or Hindsight straight into Hermes (the video's setup) | Lost: plaintext stores, Hindsight cloud by default | Partial | No | Good | Low |
| 2. ALFRED plus both as permanent engines behind it | Only full-disk encryption for two of three stores | Three separate paths | Yes | Best | High |
| 3. ALFRED absorbs their best abilities, one sealed store | Kept in full | One path | Yes | Good, to be measured | Medium |
| **4. Option 3, plus sealed throwaway engines only where tests justify them** | **Kept in full** | **One path, plus key destruction for helpers** | **Yes** | **Best available** | **Medium, rising only if earned** |

Option 4 is the recommendation.

## The design: one sealed memory in four layers

**Layer 0: the whole disk.** Full-disk encryption (FileVault on a Mac, BitLocker on
Windows, LUKS on Linux) stays on, and ALFRED checks it at start and refuses to run
without it. This protects everything when the machine is off, including your Obsidian
notes. Those notes stay as normal files so Obsidian can open them, so this layer is their
protection.

**Layer 1: ALFRED seals its own records.** Everything ALFRED stores about you is encrypted
inside its database: reviewed statements, conversation packets, note excerpts, job
results, exports, backups and the search indexes and embeddings. A copied database or
backup shows nothing without the key. This is plan 1.1, with one improvement:

- *A key per scope.* Personal, company and each client get their own key, all locked by
  one master key. A task granted only "company" can be given only company material. When a
  client engagement ends, destroying that client's key makes every copy unreadable,
  including old database pages and backups. That gives the plan a real erasure route,
  which it currently lists as out of scope. One condition: keys must be backed up apart from
  the data, with a short retention, so a destroyed key does not survive in an old backup.

There are two ways to keep the search indexes sealed, and a quick test will pick the
simpler one. Either encrypt the whole database file (SQLCipher), which needs a check that
the `sqlite-vec` search extension loads under it, or build the indexes in memory each time
ALFRED unlocks, from sealed records and sealed embeddings. At personal scale that takes
seconds.

**Layer 2: helpers leave nothing behind.**
- Hermes writes full transcripts to its own `state.db`, and no setting stops it
  (`docs/AGENT_HUB.md`). Its per-task home should therefore live in memory only (a RAM
  disk), so transcripts never reach the disk and deleting the home is real. Encrypted swap
  is needed for this; macOS has it by default.
- Any outside engine runs sealed (rules below).
- Local model servers are set not to keep prompts.

**Layer 3: what leaves the machine.** Encryption cannot protect text sent to a cloud model,
because the model has to read it. The protection there is a rule you set per scope: private
scopes use a local model, and cloud models are allowed only for scopes you mark (for
example public research or coding on ALFRED's public repository). Sync and backups leave
only as ciphertext. `restic`, already in ALFRED's source library, encrypts backups by
default.

## The abilities ALFRED takes from each project

| Ability | Borrowed from | How it lands in ALFRED | Needs |
| --- | --- | --- | --- |
| Fast search by meaning as well as by keyword, mixed with importance | Mnemosyne (hybrid ranking, compact vectors) | `sqlite-vec` inside ALFRED's sealed store, measured against today's keyword search (M06, M07) | A small local embedding model (a few hundred MB) |
| Evidence-backed beliefs with a count of supporting evidence | Hindsight (observations) | Daily learning proposes them with quoted evidence and a proof count; you approve | A local model to draft |
| Standing summaries, such as "how the owner likes drafts written" | Hindsight (mental models) | A reviewed page ALFRED refreshes and you approve; task packets carry it | Same local model |
| Deleting a fact deletes everything built from it | Hindsight | ALFRED's forget receipt covers derived proposals and summaries (plan 1.3) | Nothing new |
| Scrubbing secrets and personal details before saving | Hindsight (Memory Defense) | A check before anything is sealed or sent to a model | Nothing new |
| Plans and promises that expire into history | Hy-Memory (intentions) | Commitments (M10) gain an expiry that turns them into history | Nothing new |
| A small model trained to write memories | Hy-Memory-30B-A3B | Optional local drafter for daily learning, tried only with your go-ahead | A capable machine |
| A worked example of a Hermes memory plug | Mnemosyne's Hermes plugin | Reference for ALFRED's own plug (H5) | Nothing new |

Everything learned still arrives as a proposal in your daily list. Nothing becomes a fact
without you.

## Rules for a sealed outside engine

If tests show Hindsight (or Mnemosyne) clearly beats ALFRED's built-in version, it can run
on these terms:

1. It runs only while ALFRED is unlocked, on your machine, with a local model. It never uses
   Hindsight Cloud for a private scope.
2. Its data sits in its own encrypted space with its own key, issued by ALFRED.
3. It sees only the scopes the job is granted, and only approved material.
4. It holds nothing ALFRED cannot rebuild, so wiping it means destroying its key.
5. What it produces arrives as proposals in your daily list.
6. Workers such as Hermes never talk to it directly.

Mnemosyne fits these terms easily, since it can even run entirely in memory. Hindsight fits
with more effort: Docker, PostgreSQL in an encrypted space, and a local model of 13 GB or
more. Rebuilding it means re-reading everything through that model, which is slow, so its key
would be destroyed when a whole scope goes rather than for each small deletion.

## Fence tests for Hermes's plug (H5)

1. No tool Hermes can see may commit staged memory or skill writes.
2. Every turn goes to ALFRED only; Hermes's built-in memory is off, and no outside memory
   plugin is installed.
3. Hermes's tools cannot write into its `skills` folder; every skill found there at harvest
   becomes a proposal.
4. Setup makes no network fetch beyond the pinned commit.
5. Hermes's home lives in memory, and nothing from a task remains on disk afterwards.
6. Material from a private scope never reaches a cloud model unless you allowed that scope.

ALFRED's plug is built into the pinned Hermes container, because a Hermes update wipes
anything installed beside it.

## Build order

| Step | What | Waits on |
| --- | --- | --- |
| 1 | Encryption foundation: plan 1.1 with per-scope keys, the full-disk check and sealed backups | Your key decision; adopting the `cryptography` library or SQLCipher |
| 2 | ALFRED's Hermes plug with the six fence tests; first real job on test data | Your Hermes model choice. Test data only, so this can run in parallel with step 1 |
| 3 | Meaning search inside the sealed store, measured against keyword search | Steps 1 and 2; adopting `sqlite-vec` and an embedding model |
| 4 | Smarter daily learning: observations, standing summaries, expiring intentions | A local model for drafting |
| 5 | Optional: a sealed Hindsight or Mnemosyne trial | Steps 3 and 4 falling short in tests, and your go-ahead |

Real private data starts only after step 1.

## Decisions for you, in order

1. **Where the master key lives.** My recommendation: in your computer's keychain, unlocked
   by your login, so routines can run when you are away, plus a recovery key kept offline,
   such as printed or in your password manager. If both are lost, the memory cannot be
   recovered. The stricter alternative is typing a passphrase each time ALFRED starts. That is
   safer if someone gets into your logged-in machine, but nothing runs after a restart until
   you type it.
2. **Which scopes may use cloud models.** Recommendation: none of personal or client;
   public research and ALFRED's own public code may.
3. **Hermes's first run.** Because it uses test data only, cloud is safe for that first
   run. Private work later follows the scope rule above.

## Honest limits

- ALFRED's own versions of these abilities are untested; Hindsight may still be better at
  deep questions. Step 5 exists for that.
- Anything in use is readable in memory while ALFRED is unlocked. That is true of every
  system, and full-disk encryption plus locking when idle is the defence.
- Your Obsidian notes are protected by full-disk encryption only, so Obsidian can keep
  opening them.
- Destroying a scope key erases that scope in old backups only once the short key-backup
  window has passed.
- Each new library or model is a deliberate adoption under ALFRED's rules: exact version,
  licence, network use and tests.

## Sources

- ALFRED: `docs/REMAINING_BUILD_PLAN.md` (1.1, 1.3), `docs/MEMORY_SECURITY.md`,
  `docs/AGENT_HUB.md`, `plans/memory-backlog.json` (M05 to M07, M10)
- Mnemosyne `docs/security.md` (commit `c396ef7`); Hindsight `hindsight-api-slim` and
  `hindsight-docs/docs/developer/storage.md` (commit `5331da2f4`)
- Morris et al., "Text Embeddings Reveal (Almost) As Much As Text", EMNLP 2023:
  https://arxiv.org/abs/2310.06816
- Earlier reviews: [hy-memory-review.md](hy-memory-review.md),
  [mnemosyne-hindsight-review.md](mnemosyne-hindsight-review.md)
