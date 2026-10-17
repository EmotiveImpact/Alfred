# Encryption: keys, unlocking and recovery

17 October 2026. Integration plan phase 1, plan item 1.1 (SYS-002, M05). This page covers
the first of the two phase 1 steps: **the keys and how ALFRED unlocks them**. The second step
seals ALFRED's records, search indexes, exports and backups with these keys. Until it lands,
**nothing ALFRED stores is encrypted yet**, and real private data still waits for it.

Code: [`alfred/keys.py`](../alfred/keys.py). Tests: [`tests/test_keys.py`](../tests/test_keys.py).
Receipt: [`docs/evidence/encryption/RECEIPT.md`](evidence/encryption/RECEIPT.md).

## In brief

ALFRED has one **master key**, and under it one **area key** for each area: personal,
company and each client. Records are sealed with their own area's key. Destroying a client's
key erases that client everywhere, because every copy of its sealed records (in the database,
in backups, on a stolen disk) becomes unreadable.

The master key is never stored in the open. It is locked separately for each **unlock
method**, like a door with several keyholes, and any one of them opens it:

| Method | Where it fits | What it asks of you |
| --- | --- | --- |
| macOS keychain | Your Mac | Nothing: ALFRED opens while you are logged in |
| Passphrase | A Mac or a server | Typing it whenever ALFRED starts |
| Server secret file | A server | Setting up the server's secret store once |
| Recovery key | Anywhere, only when needed | Keeping it safe and offline |

One keyring can hold several methods at once, for example the keychain and a passphrase, so
a lost method is not a lost memory. The recovery key is always there and cannot be removed,
only replaced.

A typed passphrase or recovery key gets three tries each time ALFRED asks. Wrong tries never
lock you out or erase anything: after three, ALFRED stops, and you can simply run it again.
What slows a guesser is the passphrase stretching below, which makes every guess take about
a second. A mistyped recovery key is caught by its built-in check and named as a typing error.

All of this lives in one small file, the **keyring** (`desk-keyring.json` in ALFRED's data
folder). It holds only locked keys. It is kept apart from the database, so a database backup
never carries the keys that open it.

Each area has a name for you, such as "Acme Ltd", which the keyring keeps sealed, and a short
id that is written in the clear beside every value sealed with it. So that the id names no
one, ALFRED makes a neutral one such as `client-3f9a2b1c` unless you choose your own.
`areas` opens the keyring and lists the names; `status` shows only ids and kinds.

## On your Mac

At setup ALFRED makes a random secret and stores it in your login keychain, under the name
`alfred.keyring`. When ALFRED starts, it asks the keychain for that secret, which macOS gives
without a prompt while you are logged in, and opens the master key in memory. When ALFRED
stops, the keys leave memory.

```sh
# Once: a private Python for ALFRED with the pinned encryption library
python3 -m venv ~/.local/share/alfred/python
~/.local/share/alfred/python/bin/pip install --require-hashes --only-binary :all: -r requirements/encryption.txt

# Make the keyring: a keychain unlock plus a recovery key, shown once
~/.local/share/alfred/python/bin/python -m alfred.keys init --unlock keychain --label MacBook

# Areas, each with its own key
~/.local/share/alfred/python/bin/python -m alfred.keys area-add personal --kind personal
~/.local/share/alfred/python/bin/python -m alfred.keys area-add company --kind company
~/.local/share/alfred/python/bin/python -m alfred.keys area-add --kind client --label "Acme Ltd"

# The recovery kit copy of the keyring (see Recovery below)
~/.local/share/alfred/python/bin/python -m alfred.keys backup --to ~/Documents/ALFRED-recovery
```

The keychain's trade-off: any program running as you, while you are logged in, could ask the
keychain for the same secret. That is the price of ALFRED opening by itself, and it is why
the stricter choice is a passphrase typed at each start. Both can be enrolled together.

## On a server

A server has no login keychain, so it uses one of two methods, or both.

**A passphrase typed after each restart.** A rebooted server cannot open ALFRED by itself,
which is the strongest protection while it is switched off or copied, but ALFRED stays
locked until you connect and type it. A passphrase can also be piped in, for example from
`systemd-ask-password`.

**The server's own secret store.** ALFRED reads a secret file that the store puts in place at
start. It never accepts the secret through an environment variable, because environment
variables pass to every program ALFRED starts (a local model, a worker). Supported stores:

- **systemd credentials** (`--credential NAME`). systemd keeps the secret encrypted at rest,
  optionally bound to the server's TPM chip, and decrypts it into memory only for ALFRED's
  service.
- **Docker or Kubernetes secrets** (`--secret-file /run/secrets/NAME`), mounted with mode 0400.
- **A HashiCorp Vault agent** or similar, rendering the secret to a memory-backed file
  (`--secret-file PATH`).

The file must be a regular file of at least 32 bytes that only its owner (or root) can read;
ALFRED refuses anything looser. A systemd example:

```sh
python3 -m alfred.keys server-secret --output /root/alfred-unlock          # a fresh 48-byte secret, mode 600
systemd-creds encrypt --name=alfred-unlock /root/alfred-unlock /etc/credstore.encrypted/alfred-unlock
python3 -m alfred.keys init --unlock secret-file --credential alfred-unlock --secret-file /root/alfred-unlock --label server
shred -u /root/alfred-unlock                                                # the plain copy goes
# In ALFRED's service unit:  LoadCredentialEncrypted=alfred-unlock
```

**Cloud key vaults** (AWS KMS, Google Cloud KMS, Azure Key Vault) are not built. Each needs
its provider's library, network access and credentials, which is an adoption decision of its
own. The design leaves room: `keys.register` adds a new unlock method without changing the
keyring format, and a vault agent writing a secret file works today.

### What running on a server changes

- **Sealing protects copies, not a running ALFRED.** A stolen disk, the provider's snapshots
  and backups show nothing without the key. While ALFRED runs, the key is in the server's
  memory, so whoever controls the running server (the hosting company, or an intruder with
  administrator access) could in principle read it. On your own Mac that is only you.
- **Passphrase or secret store.** A passphrase keeps a rebooted server locked until you type
  it. A secret store restarts unattended, but anyone who controls the server can unlock it
  too; it still protects disks and backups taken away from the server.
- **Reaching it.** ALFRED listens only on its own machine (loopback), on purpose, and must not
  be exposed to the open internet. Using it on a server needs a private route, such as an SSH
  tunnel or a private network like Tailscale or WireGuard. That is separate work.
- **One place at a time.** There is no sync between machines yet, so your memory runs on the
  Mac or on a server, not both at once. Moving it is a copy of the data plus the recovery kit.
- **Disk encryption.** Cloud providers usually encrypt their disks outside the server, where
  ALFRED cannot see it; the doctor reports that as not detected. Check the provider's settings.

## Recovery

At setup ALFRED shows a **recovery key** once: 40 characters in eight groups of five, such as
`7K2QD-...`. ALFRED keeps no copy. Write it on paper or keep it in a password manager, away
from the machine.

The recovery key opens the keyring file, so the **recovery kit** has two parts:

1. **The recovery key**, the one secret to keep safe.
2. **A copy of the keyring** from `python3 -m alfred.keys backup --to FOLDER`. The copy keeps
   only the recovery key's lock, so nothing else opens it, and it can sit anywhere: a USB
   stick, iCloud, an email to yourself.

To open ALFRED on a new Mac or a server, copy the data across, then:

```sh
python3 -m alfred.keys restore --from alfred-keyring-....json    # asks for the recovery key
python3 -m alfred.keys add-unlock keychain --label "New MacBook"  # or passphrase, or secret-file
```

Make a new keyring copy after adding or destroying an area, and delete older copies after a
short while (see the limits below). `new-recovery` replaces the recovery key if it may have
been seen; the old one then stops opening the current keyring, though not older copies.

If the recovery key and every other unlock method are lost together, the memory cannot be
recovered. That is what makes it private.

## Destroying an area

```sh
python3 -m alfred.keys areas                                          # find the area's id
python3 -m alfred.keys area-destroy client-3f9a2b1c --confirm client-3f9a2b1c
```

This deletes the area's keys from the keyring and records that the area was destroyed.
Everything sealed with them, in the live database, in database backups and in exports, can
no longer be read, and the name cannot be reused. A keyring copy taken before the destruction
still holds the keys, so the erasure is complete once those copies are deleted, including
Time Machine's copies of the data folder. For that reason you may exclude `desk-keyring.json`
from Time Machine (`tmutil addexclusion`) and rely on the recovery kit copy instead.

## Full-disk encryption check

`python3 -m alfred.keys disk` and the `doctor` report whether the disk under the data folder is
encrypted: FileVault on a Mac (`fdesetup status`), a dm-crypt (LUKS) layer on Linux, found
through `/sys`. Statuses are `on`, `off` (FileVault off), `not_detected` (Linux with no LUKS
layer, which includes provider-side encryption ALFRED cannot see) and `unknown` (overlay,
network or other file systems, other operating systems). The doctor warns on anything but
`on`; it does not yet refuse to start, which comes with sealing in step 2.

## How it works

- **Keys.** Master and area keys are 32 random bytes from the operating system.
- **Sealing.** AES-256-GCM with a random 12-byte nonce, under a key made for that one value
  from the area key and a random 16-byte salt (HKDF-SHA256). An area key can therefore seal
  any number of values without reaching AES-GCM's limit on random nonces under one key, and
  the area key itself is only ever used to derive keys. Every sealed value is bound to the
  keyring, its area, the area key version and a caller context such as table, column and row
  (`seal(area, value, context)`), so a value moved to another row or area fails to open.
  Sealed text looks like `alfred-seal:1:AREA:VERSION:...`.
- **Unlock slots.** Each slot stores the master key sealed under a slot key, derived with
  HKDF-SHA256 from the method's secret, a per-slot salt and the slot's identity. Keychain and
  server secrets are 32 or more random bytes. Passphrases are first stretched with scrypt
  (N=2^17, r=8, p=1: 128 MiB and about a second), with limits so a tampered keyring cannot ask
  for more. The recovery key is 184 random bits with a 16-bit check that catches typing errors.
- **Area keys** are sealed under a key derived from the master key, bound to the area and
  version. Rotation adds a version for new seals; older versions stay until step 2 seals their
  values again.
- **Area names** are sealed under a key derived from the master key and bound to the area's
  id, so they are unreadable without unlocking and cannot be swapped between areas.
- **Integrity.** The whole keyring carries an HMAC-SHA256 seal under a master-derived key, so
  any change (a hidden destruction, swapped keys, a redirected keychain item) is refused on
  unlock. Every change rereads the file under a lock and refuses if another command changed it.
- **Files.** Mode 0600, in a folder ALFRED creates as 0700, written whole to a temporary file and moved into
  place in one step, never through a symbolic link. The live keyring is refused in sync
  folders, Git working trees and vaults, like the database.

## Adoption record: `cryptography`

Python's standard library has no AES, so sealing needs one outside library. This is ALFRED's
first adopted runtime dependency, and the owner's sign-off on it is pending.

| | |
| --- | --- |
| Package | [`cryptography`](https://pypi.org/project/cryptography/) 50.0.2, released 30 September 2026, by the Python Cryptographic Authority |
| Needs | `cffi` 2.1.1 (MIT-0) and `pycparser` 3.0 (BSD-3-Clause) |
| Licence | Apache-2.0 or BSD-3-Clause, files kept in the installed package; its wheels include OpenSSL, under Apache-2.0 |
| Pinning | [`requirements/encryption.txt`](../requirements/encryption.txt): exact versions with every published file's SHA-256, installed with `--require-hashes --only-binary :all:` |
| Used for | `AESGCM` only. HKDF, HMAC and scrypt come from the standard library |
| Network and data | None: the library makes no network calls and stores nothing |
| Containment | Imported only inside `alfred/keys.py`, only when sealing or opening. Without it every other part of ALFRED runs, and key commands refuse with `encryption_library_missing` |
| Evidence | `tests/test_keys.py`; CI installs the pinned file and runs the whole suite with it |
| Alternative considered | SQLCipher: encrypts the whole database file with one key. Per-area erasure would need one database per area, and it needs a special SQLite build on the Mac |

## Honest limits

- **Nothing is sealed yet.** This step makes and manages the keys. Records, indexes, exports
  and backups are sealed in step 2.
- **Untested on a real Mac and server.** The keychain is tested through a stand-in for Apple's
  `security` tool and FileVault through a stand-in for `fdesetup`. They should be run once on
  your Mac before real data goes in.
- **Old keyring copies.** A destroyed area, a replaced recovery key or a removed passphrase
  stays usable in any keyring copy made before the change, until that copy is deleted.
- **No master key rotation yet.** If a keyring copy and one of its unlock secrets were both
  stolen, recovering fully means new area keys and sealing everything again, which step 2
  provides.
- **Memory.** While unlocked, keys are in ALFRED's memory. Python cannot promise to wipe every
  copy; closing clears the master key's buffer and forgets the area keys. Full-disk
  encryption and locking the machine when idle are the defence.
- **Deleted files on SSDs.** Overwritten keyring files may linger in a disk's spare blocks.
  Full-disk encryption covers that.
- **Obsidian notes** stay ordinary files so Obsidian can open them; full-disk encryption is
  their protection.
