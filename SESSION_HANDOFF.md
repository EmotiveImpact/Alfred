# ALFRED continuation: Conversation v0.7

26 September 2026. Read AGENTS.md, docs/CONVERSATIONS.md, docs/ROADMAP.md and
research/MODEL_TRIAL_V07.md. Current branch `feat/alfred-conversation-2026-09-26`;
verified v0.6 predecessor `f5a3be2f093ae38a669de6f07ff1c9609c175ba2`.
Fetch the actual current ref and inspect its acceptance evidence before continuing.

The user said the look still is not right but to keep moving. Treat the visual identity
as provisional, not approved final. Preserve the existing noir full-screen OS/dock and
underlying backend. This increment is conversation/intelligence work, not another redesign.

alfred/conversation.py implements actor-private bounded sessions, durable turns, queued
worker execution, fresh-source context, expiry/forget and note-bound draft proposals.
Source mode is default. Follow-ups use previous user questions, not generated claims as
facts. New topic resets are explicit. This is not semantic omniscience or global memory.
No tools are granted to the model. Existing approval/outbox validation handles drafts.

web/conversation.js/css add Ask > Conversation alongside the retained Source search.
The same-origin session/CSRF boundary is preserved. No browser persistence. Threads are
stored in the local alpha SQLite database, not encrypted at application level. Default
24-hour retention is active-row deletion, not secure erase of WAL/backups/exported data.

Actual Qwen2.5-1.5B Q4_K_M inference now exists as a six-case CPU development experiment.
First run 36219850026 failed the response contract. Second run 36220144429 produced five
reference-valid replies, but the price question still received irrelevant facts. Green
workflow is not semantic success. Both raw runs and licences remain in evidence. No
final model selected. Do not claim general reliability, prompt-injection immunity or
actual model use in the fixture-based browser acceptance. Read each receipt's scope.

Changes must be tested and pushed, never left only locally. Full source archive remains
2,073 exact inert third-party files; do not execute or mutate quarantine. Do not reapply
older frontend patchers. No force push, automatic merge or deployment. Main remains
separate. Runtime keys and real client/personal data stay out of this public repository.

Next: stronger-model held-out reasoning evaluation; typed claims with review/provenance;
identity/grants/retention; one account connector; measured voice. No microphone, real
account/device access, ENDSTATE or Noir integration was added by this increment. Local
host must be running for automatic scans/routines/conversation jobs. No chat-background
agent or remote always-on service has been installed.
