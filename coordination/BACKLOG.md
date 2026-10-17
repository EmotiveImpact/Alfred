# Build backlog: what Claude and Astra build without the owner

17 October 2026. One ordered list of the work in
[research/INTEGRATION_PLAN_2026-10-17.md](../research/INTEGRATION_PLAN_2026-10-17.md) that
needs none of the owner's open decisions, split so Claude and Astra never touch the same
files. Written against `main` at `d81a5d509`, with the claims in draft pull requests #26
(encryption) and #27 (Astra's next claims) treated as taken.

## Rules for this list

- **Nothing here needs an open decision.** Work that waits on the owner is listed at the end
  with the decision it waits on, and nobody starts it.
- **A switch that defaults to off** may carry work that would otherwise pre-empt a choice,
  as long as the default changes nothing the owner sees and turning it on stays the owner's
  act.
- **Paths decide ownership.** Each item names its paths. An Astra item becomes buildable
  only when its claim is on `main`. A Claude item never touches a live Astra claim, and
  stays out of the encryption claim (`coordination/claims/claude-encryption.md`), which the
  "Encryption with both unlock options" thread owns.
- **One item, one pull request**, tests first, CI green, a receipt for runtime work. Every
  merge still needs the owner's word; Claude batches ready pull requests into one digest.
- **Synthetic data only.** Real notes wait for encryption step 2.

Status words: `queued` (not started), `building`, `review` (pull request open), `merged`,
`waiting` (on another item), `proposed` (no claim yet).

## Astra (Codex cloud)

Astra's claims and briefs are written in the "Working alongside Astra in Codex" thread. The
first four run in parallel because their paths are disjoint.

| # | Item | Claim | Depends on | Status |
| ---: | --- | --- | --- | --- |
| A1 | Real question set harness: runs a question file against a search and scores it | `codex-question-set` | none | queued |
| A2 | Secret scrubber module, not yet wired in | `codex-secret-scrubber` | none | queued |
| A3 | Checks run automatically when a brain's result arrives | `codex-hub-auto-verify` (PR #27) | none | queued |
| A4 | Meaning search groundwork: passages, embedder interface, in-memory index, blending | `codex-meaning-search` (PR #27) | none | queued |
| A5 | Network egress audit: a tool that fails when a module outside an allowlist imports a network library | `codex-egress-audit` (PR #27) | none | queued |
| A6 | Adoption header check: code copied from the shelf must name upstream project, path, commit and licence, matching the shelf manifest | `codex-adoption-check` (PR #27) | none | queued |
| A7 | Public hygiene check: credential-shaped literals, machine paths and email addresses in tracked files, using the scrubber's patterns | `codex-public-hygiene` (PR #27) | A2 | waiting |

A5 to A7 are self-contained tools with their own new files (`tools/`, `tests/`, `docs/`),
claimed and briefed by the Astra thread in PR #27. Claude wires each into CI after it merges
(C5), because `.github/` is shared.

## Claude (Claude Code)

| # | Item | Paths | Depends on | Status |
| ---: | --- | --- | --- | --- |
| C1 | This backlog | `coordination/BACKLOG.md`, `coordination/README.md`, `coordination/claims/claude-hub-host.md` | none | review |
| C2 | The host builds the goal hub, behind a switch that defaults to off | `alfred/hub_host.py`, `alfred/desk.py` (one hook in `serve`), `tests/test_hub_host.py`, `docs/evidence/hub-host/`, `docs/AGENT_HUB.md` | none | building |
| C3 | Show who started each verification run (automatic or owner) in the web desk | `web/` hub view, `docs/AGENT_HUB.md` | A3 merged | waiting |
| C4 | Scrub secrets from brain packets before they leave and from harvested text before it is proposed | `alfred/brain.py`, `alfred/learning.py` (harvest only), their tests | A2 merged | waiting |
| C5 | Run A5 to A7 in CI | `.github/workflows/` | each of A5 to A7 merged | waiting |
| C6 | Mark claims done, update `CHANGELOG.md`, `SESSION_HANDOFF.md`, `docs/INDEX.md` and `docs/AGENT_HUB.md` after each merge | shared files | each merge | ongoing |

C2 in one paragraph: `desk serve --hub synthetic` builds the `BrainHub` and `GoalHub` over
the host's own job coordinator, registers only the deterministic `SyntheticBrain`, attaches
the hub to the HTTP server so `/desk/hub` answers, and runs the hub's supervisor cycle on
the host's loop. Without the flag nothing changes: `/desk/hub` keeps answering
`hub_not_configured`. No real brain is registered, because which brain comes first is the
owner's choice.

## Waiting on the owner (nobody starts these)

| Work | Waits on |
| --- | --- |
| Sealing records, indexes, exports and backups; the full-disk check; deleting what was built from a deleted fact | Encryption thread (PR #26, then step 2) |
| Wiring meaning search into ALFRED's search and storing vectors | Encryption step 2 (search modules are in its claim); adopting `sqlite-vec` and an embedding model (decision 5) |
| A real brain behind the plug, the first real job, a Hermes memory plug | Claude direct or Hermes (decision 4) |
| Linked memories, spreading recall, intentions that fire, self-knowledge, surprise | Brain layer option A to D (decision 6) |
| Standing summaries and drafted beliefs | A local drafting model (decision 7); which areas may use cloud AI (decision 2) |
| Fish Audio voice (brief written, unclaimed) | Fish Audio and decision 2 |
| Outside engine trial | Decision 8, on measurements |
| Console rework | The owner's new console direction |
