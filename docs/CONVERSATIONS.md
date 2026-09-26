# ALFRED Conversation v0.7

26 September 2026. This continues the provisional v0.6 personal OS, not another redesign.
The user has NOT accepted the visual identity as final. Build useful intelligence first.

## What is implemented

Ask now includes Conversation and the retained Source search. A conversation is stored
in the local database, scoped to the authenticated workspace AND access credential.
Another owner in the same workspace cannot read its thread. New conversation creates a
separate context; a saved thread can be reopened after a browser reload or host restart.

A question is queued on a bounded worker, so model processing does not occupy the HTTP
request that submitted it. The frontend polls for completion and remains navigable.
This is asynchronous final-response delivery, not token streaming. A failed/interrupted
turn is explicit; it is not quietly retried against a model after restart.

Source passages remain the default. No model is needed for those. Local model is a
separate owner-only choice, available only when the operator has configured a local
server. It receives source excerpts and at most three previous USER questions. It has
no tools, access tokens, vault paths or authority to perform an action.

## Follow-ups are bounded context, not universal understanding

With Continue this context enabled, the last three user questions since the most recent
explicit new-topic boundary can help orient keyword retrieval. Their words are combined
with the current question within the existing 500-character retrieval bound; the current
question is not truncated to make room for history. The actual model also receives the
current question separately, plus the bounded prior user questions.

Previous generated answers are deliberately NOT reused as source facts. Retrieval still
uses keyword ranking and limited explicit note-link expansion. There are no embeddings,
general pronoun resolution, automatic entity merging or cross-workspace memory here.
Uncheck Continue this context to start a new topic within a thread. Start a new conversation
for stronger separation. The chosen retrieval query is recorded in the result metadata.

## From conversation to accountable work

A completed source-backed turn can produce an owner-edited local draft proposal. The
proposal binds exact text, source IDs/revisions/hashes, actor, workspace and expiry.
The existing approval interface is shown. Creating that proposal does not approve it,
send it or create the final draft. Explicit approval is still a second action.

After approval the existing outbox worker checks the note revisions and source authority
again before writing and reading back the local SQLite draft. Changed/deleted/revoked
sources or a forgotten/expired parent conversation block work that has not executed.
Forgetting a conversation does NOT undo an already created draft or its audit record.
This is not email delivery, autonomous planning, general tool use or account access.

## Retention and failure behaviour

Default retention is 24 hours from thread creation. Maximum 24 conversations per access
credential, 40 turns per conversation, eight queued turns and six starts per credential
per rolling minute. Only one pending turn per conversation is admitted. Request IDs make
identical API retries idempotent; changed payloads using the same ID are rejected. The
caller must supply the last observed turn count, preventing stale-tab append races.

The explicit Forget action removes active conversation/turn rows and their pending-action
source links. The worker sweeps expired or revoked conversations periodically while the
host is alive, and list/create calls also perform cleanup. On a stopped host, expiry still
blocks reads; physical row cleanup waits until the host next runs. Deletion is not secure
erasure of SQLite pages/WAL/backups, exports, previous disclosures or already created drafts.
No database encryption or mature device pairing is added in this increment.

Stored results keep references and generated text but not duplicate source excerpts or
citation quotes. Reading a thread rechecks source grants and revisions and reconstructs
excerpts from the current index. Stale generated results are cleared on that read.
This does not erase already delivered text from a person's memory or an exported file.
The filesystem index can lag a change until the next successful source scan.

If the host stops after a turn was queued or started, it becomes interrupted on restart.
A cancelled/forgotten thread can cause in-progress model output to be discarded; it does
not guarantee immediate termination of compute inside a separately managed model server.
Model call deadlines are finite. Provider exceptions are not reflected with their secret
text. A citation check proves reference integrity, not semantic entailment or relevance.

## Real model experiment

The pinned experiment used Ollama 0.34.4 and Qwen2.5-1.5B-Instruct Q4_K_M on a GitHub-hosted
CPU runner, using only six disclosed fictional cases. The runtime and model byte hashes
were checked before use. Nothing was installed on the owner's machine.

First run: five inference attempts were all rejected because the model returned a false
answerable flag alongside populated claims. The wire contract was changed to claims-only
with an empty list as the single abstention representation. The adapter derives the
public boolean. Legacy inconsistent explicit-boolean responses are still rejected.

Second run: five responses passed structural/reference validation; the no-source case
skipped inference. Manual inspection found that the missing-price question still received
irrelevant time/responsibility facts instead of abstention. The conflict answer listed
both reports, but did not explain the disagreement beyond listing the two times.
These are documented weaknesses, not a passed six-case semantic evaluation. The small
model is NOT selected as Alfred's final brain. Source mode remains the default.
Read research/MODEL_TRIAL_V07.md and the unmodified first/second result files.

## Running

Use the existing private test-data directory or initialise a new one outside the repo:

```sh
python3 -m alfred.desk init --data-dir ~/.local/share/alfred/os-v07-demo
python3 -m alfred.desk access --data-dir ~/.local/share/alfred/os-v07-demo
python3 -m alfred.desk serve --data-dir ~/.local/share/alfred/os-v07-demo
```

The access command intentionally reveals the private local key only in your terminal.
Navigate Ask > Conversation. Source mode works without model installation/API keys.
For an already configured and independently reviewed local Ollama:

```sh
python3 -m alfred.desk serve --data-dir ~/.local/share/alfred/os-v07-demo --local-model YOUR_LOCAL_MODEL --model-timeout 60
```

Use the actual model name installed on that machine. This command does not download it.
The configured server must disable cloud forwarding independently. Loopback does not
sandbox that process. Review model licences and hardware constraints. The legacy one-shot
model route rejects long-deadline configurations and points to Conversation instead.

## Preview and acceptance

The standalone v0.7 preview includes an example two-turn thread produced by actual source
retrieval. It is read-only fictional data, with create/send/forget and model execution
unavailable. It is NOT evidence of a deployed server or of live inference. Real browser
acceptance uses the actual local HTTP/database and a clearly named delayed model fixture
for responsiveness tests. Real inference is tested separately with its own receipts.

The developer package contains first-party source and evidence, not model binaries,
weights, access keys, private runtime databases or upstream quarantine. All retained
upstream files remain in the full GitHub branch unchanged and inert.
