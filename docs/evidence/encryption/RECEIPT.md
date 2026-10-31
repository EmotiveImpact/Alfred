# Encryption step 1 receipt: keys and unlocking (plan 1.1, integration plan phase 1)

17 October 2026. Branch `claude/project-thread-9npowk`, started from `main` at `8233a4588`
(the PR #24 merge), with `main` at `d81a5d509` (the PR #25 merge, two-agent claims) merged in
at `91b8d5450`. Tested revision: `4fac4cedd` (three tries for a typed passphrase or recovery key);
the commit carrying this receipt changes only this file. Synthetic secrets only. Nothing under `third_party/`
was read, imported or executed, and no model ran.

Requirements: SYS-002 (private storage, secrets, exports, backups and restore), memory job
M05. Owner decision, 17 October 2026: support both a Mac and a server, the keychain on the
Mac and a passphrase or the server's own secret store on a server, all behind one offline
recovery key, with a key per area as in `research/2026-10-17/alfred-memory-optimum.md`. The
encryption library (integration plan choice 3): the owner chose `cryptography` over SQLCipher
on 30 October 2026.

## What was built

- **`alfred/keys.py`.** A keyring file, `desk-keyring.json` beside the database, holding a
  master key locked once per unlock method and one key per area locked by the master key.
  Four unlock methods: `Keychain` (macOS login keychain through `/usr/bin/security`, secret
  passed on standard input and read back to confirm), `Passphrase` (scrypt N=2^17, r=8, p=1,
  at least 12 characters), `SecretFile` (a path, or a systemd credential name resolved in
  `$CREDENTIALS_DIRECTORY`; regular file, owner or root only, no group or other access, 32
  bytes or more) and `RecoveryKey` (184 random bits, 40 Crockford base32 characters with a
  16-bit check, shown once). `register` adds further methods without a format change.
- **Areas.** `add_area` (personal, company or client, the brain plug's scope classes; the
  area's name sealed, its id neutral such as `client-3f9a2b1c` unless one is given),
  `rotate_area` (new version for new seals, old versions still open) and `destroy_area`
  (keys removed, area recorded as destroyed, name never reused). `seal` and `open` use
  AES-256-GCM bound to keyring, area, version and caller context, each value under its own
  key derived (HKDF-SHA256) from the area key and a random 16-byte salt.
- **Integrity and safety.** HMAC-SHA256 over the whole keyring under a master-derived key;
  strict structural checks before any use, with scrypt limits so a tampered file cannot
  demand excess memory; changes reread the file under an exclusive lock and refuse when
  another writer changed it; whole-file writes through a private temporary file; symbolic
  links refused; mode 0600.
- **Recovery kit.** `backup` writes a copy keeping only the recovery slot, resealed;
  `restore` opens such a copy with the recovery key and puts it in place.
- **Unlock order.** `unlock` tries a server secret file, then the keychain (on a Mac), then a
  typed passphrase; the recovery key is used only when asked for.
- **Disk check.** `disk_encryption` reports FileVault through `fdesetup status` and dm-crypt
  (LUKS) by walking `/sys/dev/block` down through device-mapper layers.
- **Command line.** `python3 -m alfred.keys` with `init`, `status`, `check`, `add-unlock`,
  `remove-unlock`, `new-recovery`, `areas`, `area-add`, `area-rotate`, `area-destroy`, `backup`,
  `restore`, `server-secret` and `disk`. `init` and `restore` refuse the same places as the
  database (sync folders, Git working trees, vaults).
- **Doctor.** New `disk_encryption` check (warn unless on) and, when a keyring exists, a
  `keyring` check that reads its layout without unlocking; the keyring joins the permission
  checks and `placement`'s list of live files.
- **Dependency.** `requirements/encryption.txt` pins `cryptography` 50.0.2, `cffi` 2.1.1 and
  `pycparser` 3.0 with every published file hash. The three workflows that run the
  application tests install it with `--require-hashes --only-binary :all:` into a fresh
  virtual environment; unified CI records `pip freeze` as an artefact.

## Tests

- `tests/test_keys.py`, 45 tests: HKDF against RFC 5869 case 1; recovery key format, typing
  tolerance and that the check catches every single-character change; the keyring file holds
  no key, passphrase or recovery key in any encoding; each method opens the same master key;
  wrong passphrase and recovery key refused; production scrypt cost recorded; short
  passphrases refused; no overwrite and no symlink; tampering (hidden destruction, swapped
  area keys, redirected keychain item, inflated scrypt cost, damaged fields) refused;
  concurrent writers refused; closing clears the master key; seal and open bound to area and
  context; each value under its own derived key, which the bare area key does not open, and a
  shortened value refused; values of any size (a 200 KB value) seal and open; per-area keys distinct; area
  names sealed, never in the file or `status`, and
  refused when swapped between areas; neutral area ids; destroying an area defeats even the recovery key, while a
  copy made before still opens it (the stated limit); rotation; keychain secret never in
  arguments and withdrawn on removal; secret files by path, systemd credential and
  Kubernetes-style symlink, and refusals for loose permissions, short content, a pipe and a
  missing file; recovery key cannot be removed and is replaced whole; automatic unlock order;
  three tries for a typed passphrase or recovery key (a wrong or mistyped answer asks again,
  a fourth answer is never read, wrong tries lock nothing, piped input that runs out stops,
  other refusals stop at once), in the library and on the command line for `check` with a
  passphrase, the recovery key, automatic unlocking and `restore`;
  a registered extra method; backup and restore onto a second machine; disk checks for LUKS
  under LVM, a plain disk, virtual file systems, FileVault on and off; doctor checks; and
  the command line end to end with a server secret, including the recovery key piped in.
- `tests/test_recovery.py`: the fresh-workspace doctor test now sets aside the new
  `disk_encryption` check, whose status depends on the machine.
- Whole suite with the pinned library in a fresh virtual environment (Python 3.13.16):
  1,472 tests, all passing (`python -m unittest discover -s tests`, 204 seconds at
  `4fac4cedd`).
- `tools/check_memory_plan.py` and `tools/check_requirement_register.py`, with self-tests: pass.
- `tools/test_claims.py` and `tools/check_claims.py --base origin/main --branch
  claude/project-thread-9npowk` (no path Astra has claimed is changed): pass.

## Not exercised

- The real macOS keychain and `fdesetup`: tested through stand-ins. To be run once on the
  owner's Mac before real data.
- Real systemd credentials, Docker or Kubernetes secret mounts and Vault agents: tested as
  files with the same permissions and layout.
- A real LUKS device: tested with a synthetic `/sys` tree. This container's overlay file
  system reports `unknown`, as designed.
- Sealing in storage: nothing ALFRED stores is encrypted yet. That is step 2, with the host
  refusing to open a sealed workspace without its key.

## Limits

As listed in [docs/ENCRYPTION.md](../../ENCRYPTION.md#honest-limits): older keyring copies
keep what was later destroyed or replaced until deleted; no master key rotation yet; keys are
in memory while unlocked and Python cannot guarantee wiping them; SSD remnants rely on
full-disk encryption.
