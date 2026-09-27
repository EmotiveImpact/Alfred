# Selected source review

25 September 2026. This is a bounded implementation review, not a full audit of every
copied file. File copies are broader than the files actually read closely.

## Jarvis HUD / Hermes session bridge

Repository: eadmin2/jarvis_ai
Commit: `88998de8369e9d36f6d434b5e01feb93fcf1c33f`

Inspected architecture document:
https://github.com/eadmin2/jarvis_ai/blob/88998de8369e9d36f6d434b5e01feb93fcf1c33f/docs/ARCHITECTURE.md
Git blob: `9e9283a8e48052e5aa7d18819498062fa0e190b9`.

Inspected server source **lines 1 to 240 only**, not the entire server:
https://github.com/eadmin2/jarvis_ai/blob/88998de8369e9d36f6d434b5e01feb93fcf1c33f/server/server.py
Git blob: `f9526d98ee20b87d6670df8f2cdb1a1ca4738e64`.

Useful patterns: the architecture describes one persisted Hermes session across voice
and text, incremental transcription, streamed response/tool/approval events and
sentence-oriented audio. It treats interruption and what was actually played as session
concerns. ALFRED should carry those concerns into its interface contracts rather than
build unrelated voice and text memories. Claimed latency is upstream documentation,
not a measurement made in this work.

Important adaptation: the documented HUD token gate distinguishes browser-origin
WebSockets from native clients without Origin. That LAN/personal-client assumption
must not be inherited as universal ALFRED device authentication. Pair and authenticate
all device types; validate workspace authority outside browser headers.

The viewed source loads Hermes/project environment material and includes transcript and
response text in timing structures. A product deployment therefore needs deliberate
secret separation and diagnostic retention controls before real client data enters it.
Pattern-based redaction alone is not a guarantee. The current review does not establish
that every path leaks data or that the complete application is insecure.

A stop request/acknowledgement is not proof that every external effect was cancelled.
Do not map voice cancellation to 'nothing happened'. Media/HUD broadcasts also need
workspace and audience policy. Test compatibility against the exact chosen Hermes
session API rather than assuming the latest pins are already interoperable.

## nanobot tool registry

Repository: HKUDS/nanobot
Commit: `9756468a8cb475dbf685f64837c0e0ecdac9ad10`

https://github.com/HKUDS/nanobot/blob/9756468a8cb475dbf685f64837c0e0ecdac9ad10/nanobot/agent/tools/registry.py
Git blob: `d4c2f2ebfd010d45afe5065e1a5da5b850d4a991`.

The inspected registry caches deterministically ordered tool definitions, separates
built-ins from MCP entries, requires exact execution names while allowing name
suggestions, and prepares/casts/validates structured arguments before execution. These
are useful registry ergonomics. Compatibility coercion should not silently broaden an
ALFRED action after approval; canonicalise and validate before hashing the proposal.

The registry's execution method invokes the selected tool after preparation. That
method alone is not evidence of ALFRED-style external actor/scope/effect authority. This
is a statement about the inspected file, not a claim that nanobot has no other controls.
Keep credential possession and permission enforcement out of an unconstrained agent.

## nanobot turn-scoped goal permission

https://github.com/HKUDS/nanobot/blob/9756468a8cb475dbf685f64837c0e0ecdac9ad10/nanobot/agent/goal_permission.py
Git blob: `64f1176848c895e7d211727e2e26376151caaa0a`.

The source uses a ContextVar with a false default and a context manager that resets its
token in a finally block. This illustrates explicit scoped permission and cleanup even
on failure. ALFRED's durable grants need stronger authenticated provenance, expiry,
revocation and cross-process enforcement, but the scoped lifecycle is worth preserving.

## OpenClaw and Hermes security documentation

https://docs.openclaw.ai/gateway/security
https://hermes-agent.nousresearch.com/docs/user-guide/security

These were documentation reviews, not full source audits. OpenClaw states the trust
boundary assumed by a gateway; respect it when designing separate personal/client
contexts. Hermes describes approval and non-interactive behaviour; test those routes
rather than inferring them from the interactive interface. Neither project's published
controls amount to a validation of the proposed ALFRED composition.

## Adoption rule

No reviewed upstream module is imported into ALFRED's runtime in this branch. To reuse
one later: identify exact source and licence, copy into a reviewed adapter area, preserve
notices, record modifications, constrain effects/egress, add contract tests, run in an
isolated synthetic environment and document results. Keep the inert upstream snapshot
unchanged as the comparison baseline.
