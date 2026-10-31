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
ALFRED refuses anything looser. A text secret, like the one `server-secret` writes, has spaces
and line endings at its edges ignored; a binary secret is used exactly as it is. A systemd example:

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

## Forgetting and restoring

Forgetting one statement, record or source has two layers (the owner's rule of 22 October
2026; `alfred/lifecycle.py` and `alfred/memory_bin.py`):

- **Ordinary**, the everyday forget. It leaves everyday ALFRED and a copy waits in the bin for
  30 days, where you can undo it. Restoring an older backup brings it back like everything
  else in that backup, and `restore` lists what came back. A whole source has no bin: your
  files are untouched, so adding the folder again reads them again.
- **Absolute**, a separate choice: "Forget for good" in the console, or `"absolute": true`
  with the identifier typed back as `"confirm"`. It skips the bin, removes any copy already
  there, and every restore removes it again. Older backups still hold a copy until they are
  replaced; step 2 will seal that copy with the area's key.

Retention you chose when capturing a statement, and every revocation, hold like an absolute
forget. Destroying an area is the absolute layer for a whole area: its key goes, so nothing
sealed with it can be read again, in any backup.

## Full-disk encryption check

`python3 -m alfred.keys disk` and the `doctor` report whether the disk under the data folder is
encrypted, using the same check `desk serve` runs at start ([DISK_ENCRYPTION.md](DISK_ENCRYPTION.md)):
FileVault on a Mac, a dm-crypt (LUKS) layer through LVM and RAID on Linux. Statuses are `on`,
`off` (FileVault off), `not_detected` (Linux with no LUKS layer, which includes provider-side
encryption ALFRED cannot see) and `unknown` (anything the check cannot read, and other
operating systems). The doctor warns on anything but `on`; `desk serve --disk-encryption
require` refuses to start without it.

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
first adopted runtime dependency. The owner signed off on adopting it on 30 October 2026,
choosing it over SQLCipher (below).

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

## Step 2: sealing what ALFRED stores (being built)

Step 2 seals the private text in ALFRED's database with the area keys, in five parts. Only the
last one lets you switch a workspace to sealed, so no workspace you use is ever half sealed:

1. The sealing layer and the notes ALFRED reads from your vault (built).
2. Reviewed memory, its forgetting bin, and capture (built).
3. Conversations, executive records, drafts and actions (built).
4. Learning, the agent brain, goals, jobs and their cached files, and what the desk observes
   (built).
5. Switching on: a `seal` command that converts a workspace, refusing to start without the
   key, sealed backups and exports, compaction after forgetting, re-sealing after key
   rotation, and a final scan of the database, its log and its backups for private text
   (built).

Every record stays in the default area. Folder and source rules, which would put notes from a
client's folder in that client's area, come after your choice about answers drawing on
several areas (below), since that choice decides how a record made from several areas is
sealed.

**What part 1 seals.** For every note ALFRED indexes: its folder path, title, text, tags,
aliases, headings and link targets; the vault's label and settings and the errors a scan
reports (which name paths); the path history and sync conflict paths; and the note's stable
id from its front matter. For an import through a connector: its label, its receipts and the
ids of the items it brought in. The SHA-256 fingerprints kept beside them become keyed
fingerprints (HMAC-SHA256 under a key derived from the area's first key), so someone holding
the file cannot check a guess at what a note says, and destroying the area makes them
meaningless too. Front-matter and item ids are keyed the same way, so they still match
exactly. In a sealed workspace every `sha256` value ALFRED keeps or returns for a note, and
the short references in the audit log, are this keyed form.

**What part 2 seals.** In reviewed memory: each record's name (a person, project and so on),
each statement's text, and where a captured statement came from. Every copy in the forgetting
bin, sealed whole, since a copy holds the names and text the forget cleared. Each capture
policy's name and rule, which hold the line prefix or keyword it looks for and the folder it
reads. Three hashes become keyed fingerprints: the hash ALFRED keeps of each statement request
(it covers the statement's text), the note and quote fingerprints a statement keeps (already
keyed in part 1, since they copy the note's), and the hash of each line a capture policy
matched, which is how a rescan knows a line was already offered. The short request and
deferral ids capture derives from that line hash are made from the keyed form. The review
history stays value-free, as before, and a forgotten source's tombstones already keep only a
keyed hash of its path.

**Which area.** A statement, its capture record and its bin copy are in the area of the note
that supports it: `statement_area` in
[`alfred/reviewed_memory.py`](../alfred/reviewed_memory.py) reads the area the note's own text
was sealed under, so part 5's folder rules reach statements through their notes. A statement
whose note is no longer indexed is in the default area. A record's name and the capture
policies are in the workspace's default area (`entity_area`, `policy_area`), and so is a
record's copy in the bin, together with the statements forgotten with it. Until part 5 every
note is in the default area, so today all of reviewed memory is in one area.

**What stays visible in reviewed memory** without the key: how many records and statements
there are, each record's kind and id, each statement's shape (which records it links, its
predicate, valid period, review state, version, times and reviewer credential), the note and
line numbers it cites, each capture's memory type and retention, each policy's settings
(enabled, context label, daily budget), and each bin copy's kind, subject id and dates.

**What part 3 seals.** In conversations: each conversation's title, every question asked and
every answer kept (the excerpts, cited statements and model reading an answer holds), and the
binding a draft keeps of the sources and statements it rests on, including the copy kept once
its conversation has ended. In executive records: each record's title, detail, responsible
label, decision options and rationale, every progress note, and the option label and rationale
in each decision's trail. In actions: the parameters of every proposed action (a draft's text,
a note for the vault's inbox and its file name, a section to append), the proof kept once it
has run (which names the file written), and the text of each local draft. Five hashes become
keyed fingerprints: the hash of each question request and each executive record request
(they cover the question and the record's text), the fingerprint an approval names (it covers
everything an action binds), and the SHA-256 of a local draft and of an answer read aloud.
The fingerprint you approve with is the keyed one; approval and the outbox's readback compare
in that form. Editing a record seals only the fields that changed, and reading seals nothing.

**Which area.** Everything in part 3 is made in ALFRED rather than read from one note, so it
is in the workspace's default area: `conversation_area` in
[`alfred/conversation.py`](../alfred/conversation.py), `record_area` in
[`alfred/executive.py`](../alfred/executive.py) and `action_area` in
[`alfred/local.py`](../alfred/local.py) are the one place each is chosen, so the owner's
answer about answers drawing on several areas changes only those. A read-aloud record is in
its answer's area.

**What stays visible in conversations, records and actions** without the key: how many
conversations, questions, records and actions there are and when each was made, changed or
expires; each question's mode, state and position, and which record it was asked about (by
id); each record's kind, status, due date, rank, version, origin, which project, person and
note lines it links (by id), and which option was chosen (by id); each action's capability,
state and expiry; which conversation, turn, routine nomination or brain proposal an action
came from; and each read-aloud record's length and playback state.

**What part 4 seals.** In jobs: every job's parameters (for a brain task, the whole packet: the
instruction, the goal, the note excerpts and learned statements it was given), every result's
bytes, the copy of a result kept in the job cache on disk, and each worker's label. In the
agent brain: each result's outcome (the brain's answer and work log), every action a brain
proposed, with its reason, citations, provenance label and the owner's confirmation, and every
memory suggestion's statement and citations. In verification: every run's report, which quotes
what the checks found. In goals: each mandate's success test, schedule (which holds the
scheduled task's instruction) and acceptance checks, and the detail of every hub journal entry.
In learning: every proposed and accepted learning's statement, detail and evidence. And what
the desk observes, which part 3 found no part covered: each event's body (its summary and the
rest of what a source reported), and the file names and titles of the documents and links the
desk lists. Ten hashes become keyed fingerprints: a job's fingerprint, the SHA-256 of a
result (which is also its address), a brain task's packet hash, a result envelope's hash, a
proposal's fingerprint, a verification report's hash, a mandate request's hash, the SHA-256 a
harvested learning is keyed by, an event's fingerprint, and the SHA-256 of a desk document's
file. An event's subject and a desk document's id, which a source chooses, are keyed ids, so
they still match exactly.

**Results and their addresses.** A result is named by the SHA-256 of its bytes. In a sealed
workspace the name ALFRED keeps and returns is the keyed form, and the console and web page
only ever echo a name ALFRED gave them, so reading a result, feeding it into another job and
acknowledging a verification run by its hash all work unchanged. A worker still states the
plain SHA-256 of what it returns and is checked against it in memory; that hash never reaches
the database. The job cache keeps the sealed record under the keyed name, so the cache folder
holds no readable result either, and a damaged or swapped copy is refused and read again from
the database.

**Which area.** A job or brain task can draw on notes of several areas, so everything in part
4 is in the workspace's default area: `job_area` in [`alfred/jobs.py`](../alfred/jobs.py),
`brain_area` in [`alfred/brain.py`](../alfred/brain.py) (which verification uses too),
`goal_area` in [`alfred/hub_goals.py`](../alfred/hub_goals.py), `learning_area` in
[`alfred/learning.py`](../alfred/learning.py) and `event_area` in
[`alfred/local.py`](../alfred/local.py) are the one place each is chosen. A source reports
events to ALFRED rather than ALFRED reading them from one note, so the desk's observations are
in the default area too.

**What stays visible in jobs, the brain, goals, learning and the desk** without the key: how
many of each there are and when each was made, leased, finished or decided; each job's kind,
state, reason code, attempts, idempotency key and the notes and results it was bound to (note
ids, sources, revisions, the note's keyed hash and the keyed address of an earlier result);
each result's size, media type and lineage (the same ids); every job event's kind and detail
(worker ids, codes, sizes and keyed hashes); each worker's id and capabilities; each brain
task's brain, scope class, autonomy, task id and how many values were scrubbed from it; each
proposal's capability and disposition; each verification's state, outcome codes and which
check ids failed; each mandate's goal, deadline, autonomy, brains, tools, budget and state,
and every hub task, control, heartbeat, meter reading and attention item (codes and numbers);
each learning's kind, category, key (a code, or a keyed hash for a harvested one), counts and
decision; each event's kind, basis, route and times, and each desk document's revision and
status. The briefs about public upstream projects that daily learning keeps are copied from
the public catalogue and stay plain.

**Switching a workspace on (part 5).** With ALFRED stopped and the keyring made
(`python3 -m alfred.keys --data-dir <folder> init`), one command converts a plain workspace:

```sh
python3 -m alfred.desk --data-dir <folder> seal
```

It unlocks the keyring as ALFRED would at start, adds the default area if the keyring has
none, and then, in one transaction: seals every value the register names; replaces every plain
fingerprint with its keyed form, together with every copy of it ALFRED made (in job inputs and
lineage, job events, a result's address in several tables, answers, packets, action
parameters and the audit log's short references); keys the ids a source chose and makes again
the ids ALFRED derives from them; and rewrites the append-only tables (job events, the hub
journal, verification runs) once, putting their protection back before it commits. The job
cache, whose files are named by plain hashes, is emptied in the same step and fills again,
sealed, as results are read. Before committing it opens every sealed value again, checks that
no plain fingerprint or short form of one is left anywhere in the database, and checks every
foreign key; anything wrong rolls the whole conversion back, so the workspace is either still
plain or wholly sealed. Then the database is compacted (`VACUUM`) and its write-ahead log
emptied, so no plain copy is left in either file, and the backups ALFRED registered are
converted and compacted the same way, their manifests rewritten to say they are sealed.

A marker file beside the database says a conversion has started and not finished. While it is
there ALFRED will not start (`sealing_incomplete`); running `seal` again finishes the work,
since each step checks what is already done. `seal` refuses while any job is queued or running
(`work_in_flight`), because a worker checks hashes it was given; let the work finish or cancel
it first. What a worker was sent and what it returned are kept exactly as they were, sealed,
since a result is named by the hash of its own bytes.

**Starting a sealed workspace.** Every desk command except `init` reads first whether the
workspace is sealed. If it is, ALFRED unlocks the keyring (the keychain on your Mac, the
server's secret file, or the passphrase typed at the prompt) before anything else opens the
database, or stops with `workspace_locked` and a line saying why. It never opens a sealed
workspace without its keys. A plain workspace starts as before, and the demo and the tests keep
an unsealed mode with synthetic data.

**Backups and exports.** A backup of a sealed workspace is a copy of the sealed database, and
its manifest says so (`sealed`, `encrypted`, the keyring's id). An export from a sealed
workspace is sealed unless you add `--plain`: each file is sealed with the keyring and listed
in a plain `SEALED.json` and `SHA256SUMS`. `python3 -m alfred.desk --data-dir <folder>
open-export --sealed-export <export> --export-dir <new folder>` checks and opens it with the
keyring. With `--plain` ALFRED warns that anyone who gets the files can read them.

**Absolute delete.** An absolute forget of a statement, a record or a source, and a restore
that applies one again, compacts the database and empties its write-ahead log once the forget
has committed, so the removed text is no longer in the file's free pages or its log. A sealed
workspace also overwrites deleted values as it goes (SQLite's `secure_delete`). This is done
in a plain workspace too, as the two-layer delete promises.

**Rotating an area's key.**

```sh
python3 -m alfred.desk --data-dir <folder> rotate-area --area personal
```

adds a new key version, seals every value of that area again under it, in the workspace and in
its registered backups, compacts them, and only then deletes the older key versions from the
keyring. A copy made before rotating can no longer be opened (`key_version_retired`). If it is
interrupted, ALFRED will not start until the same command is run again, which finishes it.
Fingerprints keep their key, which is derived from the area's first key and kept on its own,
so every check that compares them still works.

**The final scan.** [`tests/test_sealing_switch_on.py`](../tests/test_sealing_switch_on.py)
builds each invented workspace of parts 1 to 4 plain, with a backup, switches it on with
`seal` (the desk's own command for the desk's workspace), reads every view and exports it, and
then scans the database, its write-ahead log, shared memory and journals, the job cache,
the backups and the export for every invented word, every id a source chose and every plain
SHA-256 the plain workspace held, whole or as 16, 24, 32, 40 or 64 character prefixes. Every
table the register names held something to find. One plain hash is allowed to remain: an
access key's (`credentials.digest`), which ALFRED checks a presented key against; the key is
random, so its hash says nothing about what you wrote. The same file runs the at-rest tests of
parts 1 to 4 again on converted workspaces, and compares a converted workspace with the same
one sealed from the start, row by row.

**Rescanning.** A value whose text has not changed keeps the sealed form already stored, so
rescanning an unchanged vault seals nothing and writes no new ciphertext; an edited note
seals only its changed text and its new history entry. Each value is sealed under its own
key derived from the area key, so even a very large number of rescans stays far inside what
the cipher allows for one key.

**What stays visible** without the key: how many notes and links there are, when each was
indexed, its revision and status, its kind (note, project, person and so on), its random id,
which area it belongs to, and roughly how long each piece of text is.

**How a sealed workspace behaves.** The database records which keyring sealed it. ALFRED
refuses to open it without that keyring (`workspace_locked`) or with another one
(`wrong_keyring`), and refuses to treat a plain workspace already in use as sealed
(`workspace_not_sealed`); the `seal` command converts one. A database
that holds sealed values but has lost its sealing record is refused whichever way it is opened
(`sealing_record_damaged`), so plain text can never be written beside sealed text. Restoring
from a backup makes the same checks. Search checks a reader's grants before opening anything
and never writes the open text back. A bounded cache (64 MiB) keeps opened text while ALFRED
runs; a destroyed area stops opening at once, cached or not, and forgetting a source empties
the cache.

**For developers.** [`alfred/sealing.py`](../alfred/sealing.py) lists every table that holds
private text in `TABLES`, with the columns naming a row, the sealed columns and the
fingerprint columns. Code reading such a table passes each row through `store.opened(...)`;
code writing one seals with `store.sealed(...)`; code keeping a hash of private text passes
the plain SHA-256 through `store.sealer.fingerprint(...)`. Sealed values differ every time,
so a sealed column is compared and sorted in Python, never in SQL. In a plain workspace all
of these return what they were given. `python tests/sealed_suite.py` runs every application
test with each workspace sealed by a synthetic keyring, child processes included; CI runs it
on every change, and [`tests/test_sealing.py`](../tests/test_sealing.py) checks that a sealed
workspace's database, write-ahead log and shared memory hold none of its notes' words, paths
or plain fingerprints; [`tests/test_sealing_memory.py`](../tests/test_sealing_memory.py) does
the same for reviewed memory, the bin and capture, in two areas, and
[`tests/test_sealing_records.py`](../tests/test_sealing_records.py) for conversations,
executive records, drafts and actions, and
[`tests/test_sealing_work.py`](../tests/test_sealing_work.py) for jobs, their cache folder, the
brain, verification, goals, learning and the desk's observations.

## Honest limits

- **Sealing is a step you take.** A workspace stays plain until you run `seal`. Before you
  do, make a recovery-kit backup of the keyring and test that it opens: a sealed workspace
  cannot be read without it.
- **What was written before sealing.** Exports you wrote before sealing, and backups or copies
  kept anywhere other than the folder ALFRED registered them in, stay plain; `seal` says so and
  leaves them to you. ALFRED will not restore a plain backup into a sealed workspace
  (`workspace_not_sealed`): restore it into a plain one and seal that.
- **Requests repeated across sealing.** A hash ALFRED made over a whole request or record
  before sealing (a statement request, an action's fingerprint, a job's fingerprint, an event's
  fingerprint, a brain task's packet hash) is keyed as it was made. A request made before
  sealing and sent again afterwards with the same id is refused as a collision; send it with a
  new id.
- **Work from before sealing.** A brain task run before sealing keeps the packet it was sent,
  with the plain note hashes in it, sealed. A draft such a task proposed cannot be confirmed
  after sealing (`sources_changed`), because the notes it cites are now named by keyed hashes;
  run the task again. Its result, verification and acknowledgement still work.
- **Rotation keeps fingerprints.** Rotating an area's key seals its text again but does not
  change its keyed fingerprints, which keep a key of their own. Someone holding a leaked older
  key could still check a guess against that area's fingerprints in a stolen copy, until the
  area is made again from its notes. Keyring copies made before a rotation (your recovery-kit
  backup) still hold the deleted key versions until you replace them; `rotate-area` reminds you.
- **Compaction is not secure erasure.** It removes forgotten text from the database's free
  pages and log, not from the disk's spare blocks, filesystem snapshots or Time Machine copies;
  full-disk encryption covers those. If another program holds the database for more than five
  seconds, the compaction after an absolute forget is skipped, and the next absolute forget,
  restore or `seal` catches up; `seal` and `rotate-area` instead stop with their marker in place
  and finish when run again.
- **One hash stays plain.** Each access key's SHA-256 is kept as it is, so ALFRED can check a
  key; the key itself is random and lives in the access-key file beside the database.
- **Work done for you is in the default area.** A job, a brain task's packet and result, its
  proposals and suggestions, a verification report, a goal's mandate and journal, a learning
  and what the desk observes are sealed in the default area, even when a task was given a
  client's notes and its packet, result and report quote them. Destroying that client's area
  then does not erase those quotes; they stay until the job's result is deleted with its
  source, or the records are forgotten. A task still sees only the areas it is granted. Nothing
  crosses areas today, since every note is in the default area; folder rules, which come after
  that choice, would make it possible. This belongs to the open choice about answers drawing on several areas: a record
  sealed so that it needs every area it used would close it here too.
- **Answers, drafts and actions are in the default area.** A question, its answer, a draft and
  an action are sealed in the default area even when the answer quotes or cites a client's
  notes, so destroying that client's area does not erase them. They stay readable to ALFRED
  until they lapse, are forgotten, or the conversation ends; a source forgotten through ALFRED
  still withdraws the answers and drafts that cite it, as before. Nothing crosses areas today,
  since every note is in the default area; folder rules, which come after that choice, would
  make it possible. This is the
  open choice about answers drawing on several areas: an answer sealed so that it needs every
  area it used would close this.
- **A record's name is in the default area.** You name a record yourself rather than drawing
  it from one note, so destroying a client area does not erase a record's name, even when
  every statement about it came from that client's notes.
- **A record's copy in the bin can span areas.** Forgetting a record puts one copy in the bin,
  holding the record and the statements forgotten with it, sealed in the record's area. If
  those statements came from another area's notes, destroying that area does not reach their
  text in the copy until it leaves the bin (30 days at most), and undoing the forget fails
  while their area is gone. Nothing crosses areas today, since every note is in the default
  area; folder rules, which come after that choice, would make it possible. These points belong
  to the open choice about answers drawing on several areas, and change once you make it.
- **Identifiers stay readable.** Statement, bin, conversation and question ids are random,
  and the console makes random record and draft ids; a program that chose meaningful record,
  capture policy or action ids through the API, or meaningful request, task, job idempotency,
  worker or event ids, would leave those ids readable. A desk document's own id is keyed, and
  so is the event id ALFRED derives from it.
- **Sync conflict rows** are bound to their vault rather than to one conflict, so someone able
  to write to the database could swap two conflict paths of the same vault. They still cannot
  read them.
- **Older text can be put back.** A sealed value is bound to its table, column and row but not
  to the note's revision, so someone able to write to the database could put back a note's
  text from an earlier copy of it. They still cannot read it, and the next scan of the vault
  replaces it. The same holds for a statement's text, a record's name and a bin copy, which
  could be put back from an earlier copy of the same row; a statement whose note has changed
  since is invalidated at the next look, as always. So could an answer, a record's text or a
  draft's text that ALFRED has since cleared or withdrawn, from an earlier copy of the same
  row, and so could a mandate's success test, a learning's text or an event's summary that
  forgetting a source has since redacted.
- **Moving a note to another area** will change its keyed fingerprints and keyed ids, which
  are made per area. Folder and source rules for areas, which come after the choice about
  answers drawing on several areas, have to carry a note's identity across such a move.
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
