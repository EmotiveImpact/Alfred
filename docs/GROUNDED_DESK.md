# ALFRED Desk 0.5: source-first questions

Development increment, 26 September 2026. Continue from the existing Knowledge Desk,
not from an empty repository or the earlier in-memory prototype.

## What this increment adds

Ask Alfred is a new view inside the existing browser Desk. A short natural-language
question is reduced to keywords, ranked against permitted Markdown notes and expanded
through a bounded number of explicit outgoing links. Up to five source excerpts are
returned, with exact complete lines, source paths, SHA-256 hashes and revisions.

The default returns **source excerpts**, not a fabricated conversational answer. A
not-found result does not establish that the answer does not exist outside the current
index. Selection is deterministic, not semantic search or a trained relevance model.

The browser can open the original indexed source, export a Markdown evidence packet
and recheck whether cited revisions still match. Detected changes/deletions/revocation
clear the old result. This compares the **indexed snapshot**, not the physical file at
every instant. The source scanner must be running for new filesystem changes to appear.
The original vault is read-only throughout. Nothing is sent or made into a saved memory.

## Local model option

The original Ollama adapter is optional, explicitly configured at process start and
available only to the owner in the supervisor's workspace. No model is downloaded or
installed by ALFRED. Readers can inspect sources but cannot send them to the model.
No model request is made unless the owner selects local-model mode and submits a question.

```sh
python3 -m alfred.desk init
python3 -m alfred.desk access
python3 -m alfred.desk serve
```

The above uses source mode only. For an already installed, independently operated local
Ollama model, the opt-in command is:

```sh
python3 -m alfred.desk serve --local-model YOUR_INSTALLED_MODEL --model-port 11434
```

Use synthetic notes while evaluating this alpha. The endpoint is fixed to 127.0.0.1,
with the configured port and /api/chat path. Remote URLs, proxy routing, redirects and
cloud-named models are not accepted. However, an independently managed local server
could forward requests elsewhere: the operator must disable cloud forwarding and review
its own configuration. A loopback connection is not proof of on-device inference.

The request includes only the question, selected titles, source IDs, line numbers and
excerpts. It does not include bearer credentials, workspace IDs or local filesystem
paths. It offers no tools. The output must match a bounded answer/citation schema.
Unknown citation IDs, out-of-range lines, tool requests and malformed data are rejected.
The maximum request is 48,000 bytes; response envelope 16,384 bytes; timeout six seconds.
These are development caps, not measured model latency targets. Slow/cold local models
may time out and leave the source-only result available.

**Reference integrity is not semantic entailment.** A model can cite a real passage and
still misunderstand it. Generated text is labelled interpretation, never verified fact.
The current tests use a fake model response and a real loopback HTTP fixture. Actual
Ollama inference, answer quality, latency, resource use and adversarial LLM behaviour
have not been established by this delivery.

Official API and schema references inspected on 26 September 2026:
- https://docs.ollama.com/api/chat
- https://docs.ollama.com/capabilities/structured-outputs

## Test and visual evidence

The new acceptance workflow applies reviewed integration hooks before tests, runs all
first-party unit tests, verifies both inert source archives, exercises the prior Desk
and Knowledge browser flows and checks the new question interface through a real
browser, local HTTP server, SQLite database and fictional Markdown files.

The first run exposed a connection-close error in the local adapter; it was fixed rather
than disabling the round-trip test. Read the actual successful run and source receipt
before asserting a final test count. No third-party agent runtime is executed.

Actual screenshots and test receipts are preserved in docs/evidence/grounded-v05 after
successful acceptance. The offline preview is generated from the same frontend and
fictional backend fixtures. Its three example questions are precomputed by the actual
retrieval code; arbitrary questions require the local application. It is not a hosted
assistant, authenticated service or live model demonstration.

## Known limits

Local POSIX development target only. No production encryption/key management or mature
multi-tenant isolation. No full Obsidian syntax/plugin compatibility, bidirectional sync,
semantic entity resolution or embedding search. No external accounts, voice capture,
security-device control or ENDSTATE/Noir connection. No action authority is added by the
question path. A source export is a portable copy, not a canonical memory write-back.

The next milestones are recorded in MEMORY_ARCHITECTURE.md and the root roadmap.
