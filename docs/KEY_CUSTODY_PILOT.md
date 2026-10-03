# Key custody decision proposal — PILOT-GROUNDWORK

Date: 3 October 2026. Status: proposed, owner choice pending. SYS-001/002,
MEM-009/010/013 and RUN-001/002. No cryptographic dependency was adopted; the
current SQLite, journal, source caches, exports and backups are not application
encrypted. Synthetic tests do not open the private-data gate.

Recommend **interactive local custody for the first private pilot**, after a
recorded choice, established-library implementation and explicit owner go-ahead.
Use a random per-workspace data-encryption key with authenticated encryption and
versioned formats, wrapped using a maintained OS key store or a well-reviewed
password/recovery-key facility. Do not derive encryption from ALFRED bearer
tokens, write cryptographic primitives or advertise encrypted vault files as
end-to-end confidentiality for a running service that holds the key.

| Choice | Unlock / availability | Trust and failure implication |
|---|---|---|
| OS key store, interactive local session | User signs in/unlocks; unavailable after locked boot until approved unlock | OS/account administrators and a compromised authorised process may access plaintext. Platform-specific backup/recovery/credential rotation must be designed. |
| Password/recovery-key wrapped workspace key | Deliberate unlock; no automatic continuity after restart | Password strength/KDF and recovery custody matter; losing all wraps loses data. Recovery material stays outside the repository and service logs. |
| Home/VPS service-accessible key | Unattended restart and continuity | Host administrators/service compromise can decrypt allowed scopes. Disk encryption alone does not change that. Owner must accept the precise host/provider/scopes and backup/key exposure. |
| Client-only decrypting key with ciphertext Core | Core cannot run unrestricted plaintext reasoning/indexing while clients are asleep | Changes the product's always-on capability and indexing design. It is a real trade-off, not a provider setting that supplies both properties automatically. |

Define separately: OS disk encryption; application database/page encryption;
journal encryption; cache/artefact encryption; backup encryption and export
encryption/recipients. A database-only library does not protect journals,
plaintext sources, WAL/temp files, screenshots, readable exports or provider
snapshots. User-owned Markdown stays under its separate source/drive policy.
Backups need a tested independent decrypting/recovery path; lost or revoked
service credentials must not automatically destroy all recovery wraps.

Suggested implementation evaluation after the choice: maintained SQLCipher or
an established equivalent for SQLite, platform keystore bindings, authenticated
encryption for journal/cache/backup formats, and explicit readable-export warnings.
Exact dependency versions, licences, platform build availability and key/format
migration need review before adoption. No choice of algorithm/library is accepted
by this proposal. Treat encryption dependency and format migrations as a focused
application PR with rollback/restore evidence, not a hidden setup adjustment.

Threats considered: stolen powered-off device/disk/backup; leaked snapshot or
export; unintended provider/admin access; compromised renderer; unauthorised
worker; legitimate credential later revoked; key loss; interrupted key rotation;
restoring old encrypted data or pre-revocation keys. OS key storage and encryption
do not prevent authorised-process exfiltration or reverse external effects.

Required synthetic acceptance before any private pilot:

- Scan database/WAL/journal/cache/backup/temp artefacts for canaries while locked;
  confirm unlock is required, without mistaking a byte scan for a security proof.
- Wrong key, altered ciphertext, truncated journal and missing wraps fail closed;
  existing permission, source revision and final access checks still apply.
- Kill during mutation, backup and key rotation; recover with documented keys
  without dropping durable forget/revocation intent or accepting stale grants.
- Restore a backup taken before deletion/revocation, replay the authenticated
  journal, and demonstrate that current application access stays withdrawn.
- Test deliberate readable export, retained-copy accounting and explicit recipient
  custody. Report all retained WAL/history/backups/media copies honestly.
- Separate application credential rotation from data-key rotation and key loss;
  exercise device/worker revocation, recovery-key custody and signed update keys.

The current fsynced plaintext journal and startup replay improve local recovery;
they are not tamper-authenticated against an administrator who controls the files.
VACUUM or deleting current rows cannot prove secure erasure of SSDs, snapshots,
old backups, moved exports or memory. Retention and key retirement must report
these limits without treating cryptographic erasure as a guarantee across copies
whose keys/ciphertexts are not under application control.

Exact decision needed: choose the first pilot's Core location; interactive versus
unattended unlock; server-readable scopes; key/recovery custodians and loss policy;
which encrypted components/targets must work; and the intended pilot data set.
After that choice is recorded, evaluate named maintained implementations on those
targets, produce the encryption/migration PR, and obtain the separate private-data
approval. Until then, independent synthetic product/platform work may continue.
