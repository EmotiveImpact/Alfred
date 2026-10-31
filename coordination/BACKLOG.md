# Build backlog: what Claude builds without the owner

17 October 2026. One ordered list of the work in
[research/INTEGRATION_PLAN_2026-10-17.md](../research/INTEGRATION_PLAN_2026-10-17.md) that
needs none of the owner's open decisions. Written against `main` at `d81a5d509`, with the
encryption claim in pull request #26 treated as taken. Claude builds all of it (see "Who
builds it").

## Rules for this list

- **Nothing here needs an open decision.** Work that waits on the owner is listed at the end
  with the decision it waits on, and nobody starts it.
- **A switch that defaults to off** may carry work that would otherwise pre-empt a choice,
  as long as the default changes nothing the owner sees and turning it on stays the owner's
  act.
- **Paths decide ownership.** Each item names its paths. No item touches a live Astra
  claim, and every item stays out of the encryption claim (`coordination/claims/claude-encryption.md`), which the
  "Encryption with both unlock options" thread owns.
- **One item, one pull request**, each on its own `claude/project-thread-att046-<item>` branch (the owner agreed on 17 October), tests first, CI green, a receipt for runtime work. Every
  merge still needs the owner's word. The owner dropped the daily digest on 18 October; Claude asks once, in one plain line, when pull requests are ready.
- **Synthetic data only.** Real notes wait for encryption step 2.

Status words: `queued` (not started), `building`, `review` (pull request open), `merged`,
`waiting` (on another item), `proposed` (no claim yet).

## Who builds it

On 17 October the owner moved all of Astra's work to Claude, because the Codex hand-off
was not working for them. Claude now builds every item below from the "Background build run"
thread. Astra's two claims on `main` (`codex-question-set`, `codex-secret-scrubber`) are
released by this pull request, and no other Astra claim is live. Briefs written for Astra
stay the specification for each item: the first two are in `coordination/briefs/`, and A3 to
A7 are in pull request #27.

Order: the scrubber first (C4 and A7 build on it), then the question set, auto-verify,
meaning search, and the three checks.

On 18 October the owner said yes to merging the 17 October pull requests as their checks
passed. They went in with ordinary merge commits, #28 first because it released the claims
#32 and #38 needed, and each stacked pull request after `main` had been merged into it.

| # | Item | Paths | Depends on | Status |
| ---: | --- | --- | --- | --- |
| A2 | Secret scrubber module, not yet wired in | `alfred/scrub.py`, `tests/test_scrub.py`, `docs/SECRET_SCRUBBING.md`, `docs/evidence/secret-scrubbing/` | C1 | merged (PR #32) |
| A1 | Real question set harness: runs a question file against a search and scores it | `tools/question_set.py`, `tests/test_question_set.py`, `tests/fixtures/question_set/`, `docs/QUESTION_SET.md`, `docs/evidence/question-set/` | C1 | merged (PR #38) |
| A3 | Checks run automatically when a brain's result arrives | `alfred/hub_goals.py`, `alfred/verification.py` and their tests (brief in PR #27) | none | merged (PR #33) |
| A4 | Meaning search groundwork: passages, embedder interface, in-memory index, blending | `alfred/semantic.py` and its tests (brief in PR #27); no wiring into search | none | merged (PR #37) |
| A5 | Network egress audit: a tool that fails when a module outside an allowlist imports a network library | new `tools/`, `tests/`, `docs/` files (brief in PR #27) | none | merged (PR #34) |
| A6 | Adoption header check: code copied from the shelf must name upstream project, path, commit and licence, matching the shelf manifest | new `tools/`, `tests/`, `docs/` files (brief in PR #27) | none | merged (PR #35) |
| A7 | Public hygiene check: credential-shaped literals, machine paths and email addresses in tracked files, using the scrubber's patterns | new `tools/`, `tests/`, `docs/` files (brief in PR #27) | A2 | merged (PR #39) |

| # | Item | Paths | Depends on | Status |
| ---: | --- | --- | --- | --- |
| C1 | This backlog and the claim release | `coordination/` | none | merged (PR #28) |
| C2 | The host builds the goal hub, behind a switch that defaults to off | `alfred/hub_host.py`, `alfred/desk.py` (one hook in `serve`), `tests/test_hub_host.py`, `docs/evidence/hub-host/`, `docs/AGENT_HUB.md` | none | merged (PR #29) |
| C7 | Fix B-030: a question asked before the capability answer left the Ask page's model option disabled (found by CI on this pull request) | `web/ask.js`, `tools/check_memory_context_browser.py`, `BUGS_AND_FIXES.md` | none | merged (PR #30) |
| C3 | Show who started each verification run (automatic or owner) in the console goals panel | `console/src/integration/goals.ts`, the goals panel browser check, `docs/AGENT_HUB.md` | A3 | merged (PR #40) |
| C4 | Scrub secrets from brain packets before they leave and from harvested text before it is proposed | `alfred/brain.py`, `alfred/learning.py` (harvest only), their tests | A2 | merged (PR #36) |
| C5 | Run A5 to A7 in CI | `.github/workflows/` | A5 to A7 | merged (PR #42) |
| C6 | Mark claims done, update `CHANGELOG.md`, `SESSION_HANDOFF.md`, `docs/INDEX.md` and `docs/AGENT_HUB.md` after each merge | shared files | each merge | ongoing |
| C10 | Agent drafts panel in the console: every agent draft with where it came from, approve, dismiss, and confirm or replace an address a note planted by typing it yourself | `alfred/brain.py`, `alfred/provenance.py` (`replace`), `alfred/hub_goals.py` (three routes), `console/src/integration/agentDrafts.ts`, `console/src/components/AgentDraftsPanel.tsx`, `tests/test_agent_drafts.py`, `tools/check_agent_drafts_browser.py`, `docs/AGENT_DRAFTS.md`, `docs/evidence/agent-drafts/` | C9 | merged (PR #48) |
| C11 | Fix a race found by C10's browser check: `BrainHub.submit` creates the job, then binds it to its mandate in a second transaction, so a brain worker that claims the job in between refuses it at dispatch with `mandate_required` and the task is lost. Bind in the job's own transaction | `alfred/jobs.py` (`submit`), `alfred/brain.py` (`submit`), a test | none | merged (PR #49, [B-032](../BUGS_AND_FIXES.md)) |
| C8 | Full-disk encryption check when the host starts (master plan phase 1): `--disk-encryption warn` by default, `require` refuses to start | `alfred/disk_encryption.py`, `alfred/desk.py` (one call in `serve`), `tests/test_disk_encryption.py`, `docs/DISK_ENCRYPTION.md`, `docs/evidence/disk-encryption/` | none | merged (PR #41) |
| C9 | Provenance gate (master plan phase 2, the CaMeL idea): label each brain proposal with where its contents came from, and refuse one steered by an address or link found only in a note (`enforce` by default, `watch` and `off` too) | `alfred/provenance.py`, `alfred/brain.py`, `tests/test_provenance_gate.py`, `tests/test_brain_plug.py`, `docs/PROVENANCE_GATE.md`, `docs/evidence/provenance-gate/` | none | merged (PR #44) |

C2 in one paragraph: `desk serve --hub synthetic` builds the `BrainHub` and `GoalHub` over
the host's own job coordinator, registers only the deterministic `SyntheticBrain`, attaches
the hub to the HTTP server so `/desk/hub` answers, and runs the hub's supervisor cycle on
the host's loop. Without the flag nothing changes: `/desk/hub` keeps answering
`hub_not_configured`. No real brain is registered, because which brain comes first is the
owner's choice.

## Waiting on the owner (nobody starts these)

| Work | Waits on |
| --- | --- |
| Sealing records, indexes, exports and backups; deleting what was built from a deleted fact (the full-disk check moved to C8 by agreement with that thread) | Encryption thread (PR #26, then step 2) |
| Wiring meaning search into ALFRED's search and storing vectors | Encryption step 2 (search modules are in its claim); adopting `sqlite-vec` and an embedding model (decision 5) |
| A real brain behind the plug, the first real job, a Hermes memory plug | Claude direct or Hermes (decision 4) |
| Linked memories, spreading recall, intentions that fire, self-knowledge, surprise | Brain layer option A to D (decision 6) |
| Standing summaries and drafted beliefs | A local drafting model (decision 7); which areas may use cloud AI (decision 2) |
| Fish Audio voice (brief written, unclaimed) | Fish Audio and decision 2 |
| Outside engine trial | Decision 8, on measurements |
| Console rework | The owner's new console direction |
