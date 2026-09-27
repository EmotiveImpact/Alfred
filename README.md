# ALFRED

Personal and operational intelligence, under your authority.

## Current increment: reviewed memory v0.8

Working branch: `feat/alfred-reviewed-memory-2026-09-26`, extending the verified v0.7
conversation build. Main is not merged and no hosted deployment is implied. The noir OS
shell remains provisional; this increment develops capability rather than replacing it.

**New:** separate reviewed entities/statements with exact note provenance, acceptance,
dispute, withdrawal and supersession; explicit conflicting values; source invalidation;
Memory UI and export; limited evidence checks in model reply paths; owner-confirmed
Pulse report pruning that retains compact retry receipts and recent rate counters.

[Reviewed memory and run guide](docs/REVIEWED_MEMORY.md) ·
[Evidence-check limitations](docs/EVIDENCE_REVIEW.md) · [Roadmap](docs/ROADMAP.md) ·
[Continuation](SESSION_HANDOFF.md)

```sh
python3 -m alfred.desk init --data-dir ~/.local/share/alfred/os-v08-demo
python3 -m alfred.desk access --data-dir ~/.local/share/alfred/os-v08-demo
python3 -m alfred.desk serve --data-dir ~/.local/share/alfred/os-v08-demo
```

Keep the printed local access key private. Use a data directory outside the repository.
The service is loopback-only and must not be exposed to the internet. Open Memory >
Reviewed memory after signing in. Existing notes remain canonical and read-only.

After acceptance, the current read-only preview and developer ZIP are under
`docs/previews/memory-v08/`. The preview uses the actual frontend with fictional in-file
data; it cannot create claims, run a model, execute drafts or change routines.

### Boundaries

Review is human judgement, not verified truth or permission. The new graph is inspectable
and exportable but not automatically used as model evidence. Evidence checks only reject
specific literal problems; they do not establish entailment or general reliability.
A new live-model comparison was blocked before execution. No new model benchmark is
claimed. The earlier v0.7 actual inference and failures remain historical evidence.

No real accounts, voice, devices, ENDSTATE or Noir are connected. A launched local host
is needed for scans, approved drafts, reports and queued conversations. No service was
installed on the user's machine. SQLite remains unencrypted at application level and
credential identity/retention need further work. Synthetic data only at this stage.

The 2,073 pinned upstream files remain unchanged, inert research material. A root licence
does not clear every dependency, voice, model or asset. No source files in that archive
are executed or installed by this increment. The first-party package omits that archive.

### Verification

```sh
python3 -m unittest discover -s tests -v
python3 tools/import_sources.py --verify
python3 tools/extend_sources.py --verify
```

The source verifiers require the full GitHub branch. Inspect the actual acceptance run
and `docs/evidence/memory-v08/` for results, not the mere presence of a workflow file.

---

## Previous release notes (historical v0.7)

# ALFRED

Personal and operational intelligence, under your authority.

## Current increment: conversation continuity v0.7

Working branch: `feat/alfred-conversation-2026-09-26`, extending the v0.6 personal OS
checkpoint `f5a3be2f093ae38a669de6f07ff1c9609c175ba2`. Main is not the application
until the pull-request stack is actually reviewed and merged. No deployment is implied.
The current appearance is provisional, not a locked or approved final visual identity.

This is a runnable local development application, not the complete personal intelligence
or a native operating system. Preserve the broader personal, work and authorised
operational vision as the capabilities mature.

## What works

The existing local service supplies authenticated workspaces, current project reports,
source inspection, acknowledgements, exact action approvals, verified local drafts,
read-only Markdown indexing, explicit note-reference graphs, source questions, and two
bounded opt-in Pulse report routines. The black personal shell, dock, launcher and focus
presentation are retained rather than rebuilt in this increment.

Conversation mode adds private saved threads, explicit follow-up context, bounded queued
processing, fresh-source retrieval, source invalidation and an editable draft-proposal
path into the existing approval system. Model work does not block the local HTTP loop.
An answer is not authority to execute. The only draft effect is a local database write;
**nothing is sent externally**.

Source mode works without models or API keys and returns source passages, not invented
AI replies. Optional local Ollama inference requires deliberate operator configuration.
Real Qwen2.5-1.5B Q4_K_M inference has been exercised on a small disclosed synthetic set,
with a material relevance/abstention failure recorded. That model is a development test
fixture for the integration, not a selected production brain or a validated safety system.
See [the actual trial record](research/MODEL_TRIAL_V07.md).

## Run locally

Python 3.10+ on a POSIX development machine. CI uses Linux Python 3.12.3; runtime code
has no third-party Python package requirement. Browser testing has separate test tooling.

```sh
python3 -m alfred.desk init --data-dir ~/.local/share/alfred/os-v07-demo
python3 -m alfred.desk access --data-dir ~/.local/share/alfred/os-v07-demo
python3 -m alfred.desk serve --data-dir ~/.local/share/alfred/os-v07-demo
```

Open the printed `http://127.0.0.1:8765` address on that machine. The access command
reveals a private local key in your terminal. Do not share, log or commit it. Keep runtime
data outside the public source repository. Init never overwrites existing data.

Open **Ask**, then **Conversation**. Source passages are the default. To use an already
installed, deliberately managed local model, consult [the conversation guide](docs/CONVERSATIONS.md).
ALFRED does not download model weights or configure a private vault automatically.

## Inspect the delivery

- [Conversation behaviour and limitations](docs/CONVERSATIONS.md).
- [Actual code, browser and model evidence](docs/evidence/conversation-v07/).
- [Standalone read-only preview](docs/previews/conversation-v07/ALFRED-OS-v07.html).
- [Runnable first-party developer package](docs/previews/conversation-v07/ALFRED-OS-v07-Developer-Package.zip).
- [Current roadmap](docs/ROADMAP.md), [memory architecture](docs/MEMORY_ARCHITECTURE.md)
  and [continuation record](SESSION_HANDOFF.md).

The standalone preview uses the actual frontend with fictional in-file data and selected
precomputed source-retrieval examples. It cannot run inference, save conversations,
approve work or connect accounts. It is not a hosted backend or a fake live AI demo.
The developer package excludes quarantined third-party archives and private runtime data.

## Verification

```sh
python3 -m unittest discover -s tests -v
python3 tools/import_sources.py --verify
python3 tools/extend_sources.py --verify
```

The last two commands require the full GitHub branch's retained upstream source, not the
smaller developer package. The 2,073 retained files across eight pins remain unchanged,
inert references, not eight combined or installed runtimes. Preserve copyright/licence
notices; root licences are not blanket dependency/model/asset clearance.

Read actual test output and source receipts in the evidence directory. A workflow file,
queued run or model response with syntactically valid citations is not proof of success
or semantic correctness. Browser responsiveness testing uses an explicitly labelled
delayed model double; real inference has separate unedited trial receipts.

## Development boundaries

Local HTTP only; do not expose the stdlib service publicly. No microphone, cloud model,
external account/device control, ENDSTATE or Noir connection. The host must remain running
for scanning, conversation jobs and opted-in Pulse routines. No operating-system daemon,
remote agent or cross-device synchronisation is installed.

Conversations are private to the creating access key and expire after 24 hours. Forget
removes active conversation rows and invalidates unexecuted linked proposals, but does
not undo completed drafts/audit history or securely erase SQLite/WAL/backups. This is not
application-encrypted storage or a mature device identity/retention system. Synthetic
notes only until the privacy and deployment gates are met.

No autonomous use-of-force authority or unrestricted security control. Never commit
private client data, credentials, recordings or operational material to this public repo.
