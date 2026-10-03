# Later ALFRED conversation: scoped reconciliation

3 October 2026. This is a first-party summary of the visible later conversation, not a verbatim export of every chat and not new vendor research. It supplements, and does not alter, the two preserved [2 October source documents](../2026-10-02/README.md). The [active stage](../../NEXT_STAGE.md) is the execution gate.

## Sources and confidence

- **Owner requests:** clarify the native-versus-web application; preserve always-on cloud operation; investigate renting, partnering and eventual infrastructure ownership; consolidate research into GitHub; separate the next stage so research and groundwork can proceed without rushing into activation; provide a Codex Cloud handoff.
- **Assistant proposals:** Tauri/Rust native shell retaining React and Python; optional always-on VPS Core with local execution nodes; provider and partner shortlist; phased rent-to-control/ownership strategy; Cloud/Private/Sovereign labels. These are not adopted technologies, procurement authority or proven economics.
- **Source-and-evidence audit:** the separate [3 October audit](../../AUDIT_2026-10-03.md), supplied as a Markdown file in this conversation. It reports sampled code/CI review and explicit limitations. Preserve its unconfirmed approval-visibility concern as a test request, not an asserted exploit.
- **Live repository check for this reconciliation:** main `75947b8dd59a3161c862d2533850a032994778e2`, PR #18 merged, no open PRs returned before creating this documentation branch. This fact supersedes pre-merge labels, not partial implementation limits.
- No full export or verified denominator for every ALFRED chat is available. Unseen conversations remain unreviewed.

## What the earlier handoff already captured

`docs/sources/2026-10-02/` preserves the mandate and v1.1 reconciliation. `docs/RECONCILIATION_2026-10-02.md` mapped them into existing and new PRD IDs. `research/INFRASTRUCTURE_2026-10-02.md` covers boxd, Space/SpaceFS, the pCloud analogy, persistent/disposable workers, storage and trusted nodes. `plans/source-coverage.json` records those sources and their gaps.

Do not create duplicate requirements for that work. Extend RUN-001/002/003, SYS-001/002/003, MEM-009/010/013/014 and UX-001/002 as appropriate, while keeping M01-M12 a bounded programme.

## Later additions and their destinations

| Topic | Conversation substance | Classification now | Destination |
|---|---|---|---|
| Desktop application | The owner wants an installed programme, not to discard the approved console. The assistant proposed retaining React/TypeScript/Three.js/GLSL and Python, adding a native shell and selected native services. | Preserve existing implementation: required. Tauri/Rust choice: proposed for research, not adoption. | RUN-001, UX-001, SYS-001/002; NEXT_STAGE B1. |
| Always-on continuity | The owner asked how the native app coexists with cloud operation when the computer is off. The assistant proposed an always-on Core and local clients/workers. | Required outcome to specify under RUN-002. VPS versus home authority, data residency and custody remain decisions. | RUN-001/002, SYS-001/002; NEXT_STAGE B1. |
| Local and remote work | Large local files/GPU/device work should not require uploading everything; remote work should continue and return inspectable results. | Groundwork target, not deployed feature or permission to move data. | RUN-002/003, SYS-003. |
| Persistent agent computers | boxd could supply a machine to create, wake, retain or fork; it must not become ALFRED's memory/job authority. | Retained research candidate. Original alternatives remain in the infrastructure report. | RUN-003; NEXT_STAGE B2. |
| Second-hard-drive experience | On-demand files, bounded cache, explicit offline pins, revision/conflict handling. Live databases are not generic cloud-sync files. | Existing accepted requirement, not a new implementation claim. | SYS-003, MEM-014. |
| Commercial hosting | Prove on rented capacity, negotiate later, consider dedicated capacity/colocation/ownership only where workload economics and operational capacity justify it. | Strategic proposal. No promised migration date, scale threshold or committed capital. | NEXT_STAGE B3; future commercial decision. |
| Deployment modes | ALFRED Cloud, ALFRED Private, ALFRED Sovereign were proposed labels. | Product options; not security, sovereignty or regulatory certifications. | Future product/operations research under SYS-001/002, OPS-001, RUN-001/002. |
| Partners | Named hosting, storage, networking, GPU, sandbox and colocation candidates. | Shortlist to verify, not a relationship or an endorsed supplier contract. | NEXT_STAGE B3. |
| Codebase value | The assistant gave replacement/IP/company-value estimates without a formal diligence process. | Informal speculation, not an appraised valuation, revenue evidence or planning input. | Excluded from engineering acceptance and funding claims. |
| Audit | Main is connected and tested; planning status is stale; approval visibility needs reproduction; strict grants, recovery, private storage and evidence relevance need work. | Observed status plus explicitly labelled review concern/recommendations. | NEXT_STAGE A1-A4 and audit. |
| Current owner instruction | Consolidate, push and hand off another stage that can research and lay groundwork rather than immediately activate everything. | Current execution instruction. | NEXT_STAGE and CODEX_NEXT_STAGE_PROMPT. |

## Important difference from the earlier infrastructure recommendation

The earlier report defaulted to a laptop coordinator until the owner chose an always-on home host or VPS. The later assistant recommendation favoured an always-on Core. Both must remain visible: the outcome is continuity, but the owner has not selected a provider, approved all memory moving to a server, or resolved key recovery.

The next builder must produce that decision explicitly. One authority per job does not require all personal files or all future customers' data on one central server. Document which data is local-only, which metadata/results may be shared and what functionality is unavailable offline. Native packaging is neither the brain nor a prerequisite for a hosted service.

A passphrase unlocked by hand after every reboot and an unattended cloud service create a custody/availability trade-off. A cloud service able to decrypt data is not an end-to-end confidential service against that host. Research the intended threat model; do not solve this by copying keys into images or introducing unexplained automatic recovery.

## Partner and cost discussion to retain without turning it into procurement

Earlier conversation candidates, grouped by role rather than endorsement:

- Hosting: OVHcloud, Scaleway, DigitalOcean and Hetzner.
- Edge/storage: Cloudflare/R2 and Backblaze/B2; storage software alternatives remain in the earlier research.
- GPU/ecosystem: NVIDIA/Inception, Nscale (including the mentioned BT relationship to verify), Nebius and Scaleway.
- Execution: boxd, E2B, NVIDIA OpenShell and local/self-hosted backends.
- Private transport: Tailscale, Headscale, NetBird and WireGuard.
- Possible later colocation: Telehouse and Digital Realty.

The conversation included headline VPS prices, startup-credit ceilings, user-count-based monthly envelopes and hardware-capital ranges. Those figures were not measurements of ALFRED's workload, binding quotes, programme eligibility or total operating costs. They are deliberately not restated as approved budget numbers. The research task must refresh official prices/terms, state region, currency, VAT, discounts and exclusions, and model actual usage. A missed quote or inaccessible licence file is an evidence gap, not permission to guess.

The commercial progression discussed was rent -> negotiate/partner -> reserved or dedicated capacity -> possibly colocated owned hardware -> possibly control selected technology. There is no requirement to own a data centre or acquire a provider. Buying machines, licensing technology and acquiring a company are different decisions. Do not send applications or outreach without approval.

## Audit provenance and limits

The supplied audit was created before this documentation branch. Its statement that it changed nothing was true of that audit. Publishing the audit now does not transform its observations into reproduced tests or certify the application. The API projection concern must be tested against the baseline and current code. The successful main CI is historical verification of the merged tree, not proof of a private or remote deployment.

This reconciliation makes no new implementation claim. It does not mark any existing partial requirement complete. It records later proposals and gates so the next builder can work without relying on inaccessible conversation memory.
