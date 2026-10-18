# Adoption credit check

## In short

ALFRED may borrow code from the research shelf (`third_party/research-shelf/`) and the source
library (`third_party/library/`) only with credit. Each borrowed file has to say where it came
from: the project, the exact file, the exact commit and the licence, plus the notice that licence
asks for. `tools/check_adoptions.py` reads every one of those credits and checks it against the
pinned records of what is on the shelf. A credit that is missing a piece, or that names a project,
commit, file or licence the records do not support, fails the check.

No code has been borrowed yet, so today the check passes and says there is nothing to check.

A pass means the credits are complete and match the records. It is **not** licence clearance and
it is **not** your approval: every adoption still needs the steps in
[the integration plan](../research/INTEGRATION_PLAN_2026-10-17.md) ("How borrowing code works")
and your word, as AGENTS.md requires.

Run it:

    python3 tools/check_adoptions.py

Exit code 0 means clean, 1 means at least one credit problem (one line each, with file and line),
2 means the check could not run: the shelf records could not be read, or none of the source
folders exists.

## Writing a credit

Put the credit at the top of the adapted file, one field per comment line, opening with the
`Adapted from:` line and ending with a blank line (or an empty comment line). In Python:

    # Adapted from: mnemosyne-oss/mnemosyne
    # Path: <the file's path inside that snapshot>
    # Commit: c396ef7447b21fd6f690c3bd48a8a2a7063e11fb
    # Licence: MIT
    # Copyright: <the copyright line exactly as the upstream licence gives it>
    # Changes: Rewritten to ALFRED's conventions; only the ranking helper is kept.

The same block works with `//` comments, inside a `/* ... */` comment, or as the first lines of a
Python module docstring. A long value continues on the next line if that line is indented further
than the field it continues.

| Field | Needed | What the check compares it with |
|---|---|---|
| `Adapted from:` | always | `owner/name` exactly as the catalogue spells it, in either catalogue |
| `Path:` | always | a file the snapshot's manifest lists (a file the snapshot left out is named with the reason) |
| `Commit:` | always | the full 40-character commit the catalogue pins for that project |
| `Licence:` | always | the licence string the catalogue records, exactly (British spelling; `License:` is reported) |
| `Copyright:` | MIT | must quote one or more whole lines of the upstream licence file, NOTICE file or adapted upstream file (comment markers and spacing aside) |
| `Notice:` | Apache-2.0 | the same: it must quote an upstream notice |
| `Changes:` | Apache-2.0 | a statement of what was changed; free text |

A file may carry more than one credit block if it draws on more than one upstream file.

## What fails

- a missing or empty required field, a short commit, an absolute or `..` path, a duplicated or
  unknown field;
- a project that neither catalogue lists (a near miss in letter case names the catalogue spelling);
- a commit other than the pinned one;
- a project recorded only as a reference (`reference_only`): no source was copied, so there is
  nothing pinned to adapt from;
- a project whose recorded licence grants no right to copy: `UNLICENSED` (which is not the
  permissive Unlicense), `NOASSERTION` or `not established`;
- a path the snapshot does not contain;
- a licence that differs from the record;
- a licence this check has no notice rule for. Only MIT and Apache-2.0 have rules today. BSD,
  PostgreSQL, GPL, AGPL, the Unlicense and every other licence fail until you agree what their
  credit must carry and the rule is added here;
- a missing Copyright line for MIT, or a missing Notice or Changes line for Apache-2.0;
- Copyright or Notice text that is not whole lines of the upstream licence, NOTICE or adapted file
  (a fragment such as a bare name or year is not a quote);
- a comment line that starts with the words "adapted from" but is not a complete credit. To credit
  an idea rather than code, use other words, such as "Based on the approach in";
- a file of at least 256 bytes that is byte-identical to a snapshot file but carries no credit.

## Where it looks

It scans ALFRED's own source: `alfred/`, `tools/`, `web/` and `console/src/`. It never scans
`third_party/`, `tests/` or a folder named `third_party`, `node_modules`, `__pycache__` or `.git`
inside those, and it skips binary files and symbolic links. It reads `CATALOGUE.json` and
`manifests/<owner>__<name>.json` in each collection, and for notice text the listed licence,
NOTICE and adapted files in `snapshots/`, all as plain data. Nothing under `third_party/` is
imported, installed or run. The historical selections in `third_party/sources/` and
`third_party/extensions/` are not adoption sources for this check.

## What a pass does not prove

- That the licence permits the use, that it is compatible with how ALFRED will be released, or
  that nested dependencies, models, datasets or services inside the project are cleared.
- That the full licence text ships with ALFRED (MIT and Apache-2.0 both ask for it), that the
  code was rewritten to ALFRED's conventions, or that its network and storage behaviour was
  reviewed.
- That uncredited code was not borrowed. Only byte-identical copies are detected; rewritten code
  with no credit cannot be.
- That the snapshot files match their manifests. `python3 tools/build_research_shelf.py --verify`
  and `python3 tools/build_source_library.py --verify` check that.

Tests: `python3 -m unittest tests.test_check_adoptions`, with synthetic catalogues, manifests and
credits in `tests/fixtures/adoptions/`.
