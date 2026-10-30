# Public repository hygiene check

This repository is public. Credentials, home-directory paths and personal email addresses
must never land in it. `tools/check_public_hygiene.py` reads every file Git tracks and fails
when one of them holds something of that shape. It is backlog item A7.

```sh
python3 tools/check_public_hygiene.py              # check this repository
python3 tools/check_public_hygiene.py --suggest    # draft exceptions for what it found
python3 tools/check_public_hygiene.py --root PATH --allowlist FILE
```

| Exit status | Meaning |
| --- | --- |
| 0 | Nothing found, or everything found is a reviewed exception, and no exception is stale |
| 1 | At least one finding that is not a reviewed exception, or at least one stale exception |
| 2 | It could not run: a usage error, the folder is not in a Git repository, Git is missing, or the allowlist cannot be read or is malformed |

## What it reads

- **Only files Git tracks** (`git ls-files`). Untracked and ignored files are never opened.
  It reads the copy in the working folder, so it also sees changes not yet committed.
- **It skips:**
  - everything under `third_party/` at the top of the repository (a folder called
    `third_party` deeper down is still checked);
  - binary files: a NUL byte in the first 8 KB, or contents that are not valid UTF-8;
  - submodules, and tracked files missing from the working folder.
- **Symbolic links** are checked by the text of their target and are never followed, so a
  link cannot make it read a file outside the repository, and a link that points into
  someone's home folder is still caught.

The last lines of the output count what was scanned and what was skipped. The counts hold
no values.

## What it looks for

- **Credentials:** every kind the secret scrubber finds (`alfred.scrub`, listed in
  [SECRET_SCRUBBING.md](SECRET_SCRUBBING.md)). The check calls the scrubber; it does not
  keep its own copy of the patterns.
- **`home_path`:** a home folder with a name in it:
  - `/home/<name>` and `/Users/<name>`, where the path starts (not inside a longer path such
    as `/var/home/...` or a web address);
  - `C:\Users\<name>` with any drive letter, either slash, doubled backslashes as in code or
    JSON, and any capitalisation of `Users`.
- **`email`:** an address with a dotted domain, such as name, at sign, `example.org`.

**Placeholders name no one, so they pass:**
- anything that does not start with a letter, digit or underscore, such as `<name>`,
  `{user}`, `$USER`, `${USER}`, `%USERNAME%`, `*` and `...`;
- `~/...`, `$HOME/...`, `${HOME}` and `%USERPROFILE%`;
- these generic names, in any capitalisation: `user`, `username`, `name`, `yourname`,
  `your-name`, `your_name`, `you`, `me`, `someone`, `example`, and the shared system folders
  `Shared`, `Public` and `Default`.

Any other name is reported, including the accounts of build machines and containers. If a
path like that is genuinely generic, add a reviewed exception rather than another
placeholder name.

**Not addresses:** `@property`, `@types/node`, `react@18.3.1`, an address with no dot in its
domain (`user` at `localhost`), and text already blanked as `[redacted:email]`.

An address or path inside a credential (for example, in a database address with a password)
is reported once, as the credential.

## What it prints

One line per finding: file, line, kind, and the first 12 characters of the SHA-256 digest of
the matched text. For example:

```text
tests/test_example.py:42: email 1f2e3d4c5b6a
```

**It never prints the matched text.** Its error messages name a field or an entry by its
number, never a value. The tests check this by running the command on invented values of
every kind and searching what it printed.

A digest cannot be turned back into the text, but someone who guesses a short value can
confirm the guess against it. That adds nothing for a value already committed to a public
repository, which is the only thing this check reads. Treat a value it finds as already
public: change the credential, then remove it.

## Adding a reviewed exception

Some findings are deliberate: an invented address in a test, a test sentinel, a commit
identity for an automated workflow. These go in `tools/public_hygiene_allowlist.json`:

```json
{
  "about": "What this file is.",
  "entries": [
    {"file": "tests/test_example.py", "kind": "email", "sha256": "<64 hex characters>",
     "reason": "Invented address on the reserved example.org domain in synthetic test data."}
  ]
}
```

1. Run `python3 tools/check_public_hygiene.py --suggest`. It prints draft entries for every
   finding not yet allowed, with the full digest and an empty reason.
2. Open each file at the line the normal run reports and look at the text yourself.
3. If it is real (a credential, a real person's address, a path from your own computer), do
   not add an exception. Remove it from the file, and change the credential if it was one.
4. If it is deliberate, copy its entry into the allowlist and write a truthful reason of at
   least 10 characters saying why it is safe. A draft with its reason still empty is
   refused, so an unread draft cannot be pasted in.

One entry covers every occurrence of that exact text in that one file, wherever it moves in
the file. The same text in another file needs its own entry.

**Stale exceptions fail.** An entry that no longer matches anything (the text changed, or
the file was removed) makes the check fail, so the list cannot fill up with exceptions
nobody needs. Delete the entry.

**A malformed allowlist stops the check** with exit status 2. The allowlist is malformed if
it:
- is not valid JSON, or repeats a key inside one object;
- has an unknown key;
- has an entry without exactly `file`, `kind`, `sha256` and `reason`;
- has a file path that is not relative to the repository;
- has an unknown kind, a digest that is not 64 lower-case hexadecimal characters, or a
  reason that is too short;
- has the same file, kind and digest twice.

The committed allowlist was reviewed entry by entry: invented addresses on reserved
example domains, commit identities of automated workflows, the scrubber's own description
text and test templates, test sentinels and a deliberately wrong CSRF token.

## What it cannot catch

A clean result does not mean the repository holds nothing private.

- **Credentials:** everything in [What it cannot
  catch](SECRET_SCRUBBING.md#what-it-cannot-catch) for the scrubber applies here too, such
  as a password in plain words, an unlabelled random string, or a value split across lines.
- **History:** only the current files are read. Something committed and later removed is
  still in the Git history, and commit messages and author details are not checked.
- **What it skips:** binary files, images, PDFs and archives, and everything under
  `third_party/`.
- **File names:** these are not checked, and are printed as they are.
- **Paths:**
  - a Windows name with a space is caught only up to the space;
  - `~name/`, `/root/` and other machine paths, such as temporary folders, are not looked
    for.
- **Personal data in prose:** real names, phone numbers, postal addresses, and addresses
  with non-ASCII characters or written as "name at domain".

## Cost

The whole repository (about 560 files outside `third_party/`, and about 99,500 listed and
skipped under it) takes about one second. The tests feed 1 MB of hostile input to the home
path and address patterns, and require each to finish within a second.

## Continuous integration

The unified CI (`.github/workflows/alfred-ci.yml`, job `core-and-sources`) runs
`python3 tools/check_public_hygiene.py` on every push and pull request, in the step that also
runs the egress audit and the adoption check. A finding outside the reviewed exceptions, or a
stale exception, fails the job. Its tests run with the rest of `tests/` in the same job. Run it
by hand before pushing, and add an exception only after reading the match, as above.
