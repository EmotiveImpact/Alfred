# ALFRED V2 architecture and boundary contracts

## Runtime topology (proposed)
```text
Authorised home/office/site sources
  ├── local CSI Wi-Fi sensors (presence confidence only)
  ├── opt-in BLE/proximity observations (device-nearby, not person-proof)
  ├── local camera analytics (counts/zones, optional regulated face matching)
  ├── opt-in audio front end (wake, VAD, diarisation)
  └── permitted digital event connectors (calls, calendars, infrastructure)
            │ per-site scoped gateway; no direct authority; consent and retention
            ▼
   ALFRED Event Ingress + time/source integrity
            │ normalize, freshness TTL, provenance, deduplicate
            ▼
   Environmental Context / Discretion Engine
            │ unknown/occupied/probably private; no identified-person certainty
            ├──────────────► Privacy routing (earphones, phone, silent notification)
            └──────────────► Attention / escalation proposals
                                  │
ALFRED Python CORE ◄───────────────┘
  ├── memory/scope/grants
  ├── goals, priorities and budgets
  ├── command authority and exact-action approvals
  ├── independent verification / receipt ledger
  └── BrainHub task contracts
           ├── Hermes (planned H5, isolated replaceable worker)
           ├── Claude/OpenAI worker (if approved)
           └── local model (if approved)
   Only ALFRED authorises capabilities; workers return proposals.
                                  │
                 approved outbox / connectors
                                  │
                 actual effect receipt / reconciliation
```

## Observation envelope v1 (design, not current API)
A sensor adapter may submit `event_id`, `source_id`, `site_id`, `zone_id`, `observed_at`, `received_at`, `expires_at`, `event_kind`, `evidence_type`, `value`, `confidence`, `uncertainty`, `retention_class`, `consent_policy_id`, `sensor_health`, `privacy_scope`, `integrity_signature` and `correlation_id`. For example `event_kind=person_count_estimate`, `value={min:1,max:3}`. Keep sensor count ranges and source confidence distinct from a hard fact. A paired watch announces `device_nearby` only, never `owner_confirmed`.

Enforce: authenticated sender, site/zone grants, monotonic/preserved timestamps, conservative TTL, rate limits, replay refusal, encrypted transit, device revocation, source-class isolation and local audit of the decision. `unknown` is a first-class state. One compromised camera cannot nominate itself as commander.

## Discretion decision contract
Inputs: user preference, currently authenticated client session, content sensitivity classification, site policy, authorised room observations and each observation's freshness. Outputs: `speak_allowed`, `route` (speaker/earpiece/phone/watch/silent), `reason_codes`, `confidence_summary`, `requires_user_confirmation`, `expires_at`. Unknown occupancy plus sensitive content defaults to private route. ALFRED must make all high-risk decisions deterministically via policy; the model may propose wording but cannot override a discreet-route refusal.

## Speech and conversation
State transitions: `off -> opt_in_armed -> local_wake_detected -> visible_listening -> speaking -> idle`; PTT goes straight from `off/idle -> visible_listening` after user action. Expired/unpaired devices refuse instructions. VAD distinguishes speech from silence, diarisation separates turns, addressee detection guesses whether ALFRED was addressed, and speech content is interpreted only after these stages. All can be wrong; provide user corrections and visible recording/collection indicators. Speaker diarisation is **not** a biometric authorisation token.

## Authority for actions
An intent becomes typed `proposed_action` with exact parameters, origin, provenance and expiry. ALFRED alone checks actor session, mandate, resources, cross-scope permissions, risk and independent approval binding. Routine read-only work may execute under existing explicit grants. Financial transactions, deleting private records, access grants, sending externally or safety-critical changes require separately verified confirmation from a signed-in trusted surface with a passkey/device authenticator as appropriate; liveness and voice likeness alone cannot authorise. Recheck immediately before dispatch. Record attempted, accepted, disputed, sent, read-back, failed and unknown states distinctly. Avoid automatic retry after unknown effects.

## Background operations and overnight event loop
Background monitoring is server-/host-side, not predicated on iOS microphone background execution. Sources submit narrow events. Rules triage into informational/attention/urgent with deduplication, bounded evaluation, escalation policy and DND/critical notification capability check. Deliver via eligible device push channels (not guaranteed wake-up); collect explicit receipt and acknowledgement, and provide fallback escalation only by owner-approved channels. No automatic emergency-services calling without explicit design and jurisdictional review.

## Multi-site and mobility
A site gateway controls cameras/sensors locally; ALFRED receives a minimum necessary redacted event. Site pairing, ownership, consent, lease, clock sync, offline queue expiry and removal are explicit. Raw audio/video is excluded by default. Sensitive processing stays local, with cloud processing individually opted in. A site cannot reach another site's resources because it sent a plausible event. Only approved connectors can bridge operational domains.

## Non-goals for this PR
No hardware deployment, live video/audio collection, camera access, face enrolment, identity database, OS watch app, active wake-word daemon, incident autopilot, production Hermes installation or ENDSTATE/8 Ball integration. Those need dedicated design + owner decisions.