# Network egress audit

## In plain words

ALFRED keeps your private material on your own computer. It is meant to reach the network
only through a few known parts of the code, and almost all of those only ever talk to your
own computer (the "loopback" address, 127.0.0.1), never to the internet.

The danger this check guards against is quiet change: a new piece of code, written by a
person or by an agent, that starts opening connections and that nobody notices. One added
line is enough to send data somewhere it should not go.

The check, `tools/egress_audit.py`, reads all of ALFRED's own Python code, without running
any of it, and finds every place that brings in something able to use the network. Each of
those places has to appear on a reviewed list, `tools/egress_allowlist.json`, with a one-line
reason saying where its connections go. If anything new appears, the check fails until
someone has looked at it and added it to the list. If something on the list stops using the
network, the check also fails until the entry is removed, so the list always matches the
code and cannot quietly go out of date.

What it does not do:

- It is a tripwire, not a firewall. It does not watch ALFRED while it runs and does not
  block any connection.
- It cannot prove that an allowed module really stays on your computer. The written reasons
  and ordinary code review do that.
- It cannot see everything (the full list is under "What it cannot see"). Where it knows it
  is blind, it prints a warning rather than staying silent.

If the check fails on a pull request, it means some code gained or lost a network
connection without the list being updated. That is a question for review, not a broken
build to be waved through.

## Running it

```
python3 tools/egress_audit.py               # audit this repository
python3 tools/egress_audit.py --self-test   # run the built-in synthetic cases
python3 -m unittest tests.test_egress_audit # the full test suite for the audit
```

Options: `--root PATH` audits another checkout, and `--allowlist PATH` uses another list.
Standard library only, Python 3.12 or later, and it never uses the network itself.

| Exit code | Meaning |
|---|---|
| 0 | Clean. Warnings may be printed, but they do not fail the check. |
| 1 | Findings: an unlisted network import, a stale list entry, or a file that could not be audited. |
| 2 | The audit could not run: the list is malformed or unreadable, `alfred/` or `tools/` is missing, or the root is inside a `third_party/` folder. Command-line mistakes also exit 2. |

Each finding is one line on standard error, sorted by file and line, for example:

```
error: alfred/new_feature.py:12: socket is a network import that is not on the allowlist
error: tools/egress_allowlist.json: stale entry: alfred/old.py no longer imports http.client
warning: tools/fetch.py:30: runs curl through subprocess.run; this audit cannot see what another program sends
```

The last line on standard output is the summary, such as `egress audit ok: 107 files
scanned, 39 allowlisted network imports, 0 warnings`.

## What it reads and what it skips

- It reads every `.py` file under `alfred/` (the application) and `tools/` (build, check and
  import scripts). Files are parsed with Python's `ast` module from their bytes, honouring a
  declared source encoding. Nothing is imported or executed; a test plants a file that would
  leave a marker if it ever ran.
- It never reads `third_party/`, the inert source library. Any folder named `third_party`
  is skipped at every depth, an allowlist entry may not point into one, and the audit
  refuses to run from a root that lies inside one.
- It does not follow symbolic links. A linked file or folder is reported as a finding,
  because the audit cannot vouch for what it points to.
- A file that cannot be parsed (a syntax error, bytes that are not valid in its encoding, a
  null byte) is reported as a finding with its line, and the rest of the tree is still
  audited.
- `tests/` is not scanned. 28 test files open `http.client` connections to the loopback
  server they are testing, so scanning them would add noise without adding
  protection; they never ship as part of ALFRED. `console/` is JavaScript and is out of
  scope.

## What counts as a network import

A watched name covers itself and everything below it, so `urllib` covers `urllib.parse`
and `urllib.request`. The list is `WATCHED` in the tool.

- **Standard library:** `socket`, `ssl` (and their low-level `_socket`, `_ssl`), `urllib`,
  `http.client`, `http.server`, `socketserver`, `smtplib`, `ftplib`, `poplib`, `imaplib`,
  `nntplib`, `telnetlib`, `xmlrpc`, `webbrowser`, `wsgiref.simple_server`,
  `multiprocessing.connection`, the asyncio streams (`asyncio.streams`,
  `asyncio.open_connection`, `asyncio.start_server` and their Unix socket versions) and the
  asyncio event loop transports (`create_connection`, `create_server`,
  `create_datagram_endpoint` and their Unix socket versions).
- **Other libraries:** `aiohttp`, `anthropic`, `boto3`, `botocore`, `grpc`, `httpcore`,
  `httplib2`, `httpx`, `openai`, `paramiko`, `playwright`, `pycurl`, `requests`, `selenium`,
  `tornado`, `twisted`, `urllib3`, `websocket`, `websockets`. None of these is an ALFRED
  runtime dependency, and only Playwright is used at all (by the browser checks, from their
  own environment). They are watched so that adopting one is also a reviewed network
  decision.

Parsers count too. `urllib.parse` opens no connection, but it is part of a package that
can, so it is listed with a reason that says "parser only". This keeps a later change from
`urllib.parse` to `urllib.request` from passing unnoticed: the list names the exact
submodule, and allowing `urllib.parse` does not allow `urllib.request`.

The audit recognises these forms: `import x`, `import x.y`, `import x as z`,
`from x import y`, `from x import y as z`, several modules in one statement, star imports,
imports anywhere in a file (inside functions, classes, `try`, `if` and `with` blocks), use
through a parent package (`import http` then `http.client.HTTPConnection`),
`from urllib import parse` (recorded as `urllib.parse`), and `importlib.import_module(...)`
or `__import__(...)` with a literal name, including aliases of either. Relative imports
(`from . import x`) are ALFRED's own modules and are not network imports. Text inside
strings and comments is ignored, so a denylist such as `('socket.', ...)` in
`alfred/job_kinds.py` is not mistaken for an import.

## Warnings

Warnings mark things the audit knows it cannot follow. They are printed but do not fail the
check, because some have legitimate uses; each one should still be read.

- **Another program doing the networking.** A call to `subprocess` (`run`, `Popen`, `call`,
  `check_call`, `check_output`, `getoutput`, `getstatusoutput`), `os` (`system`, `popen`, the
  `exec` and `spawn` families, `posix_spawn`) or `asyncio.create_subprocess_exec` and
  `create_subprocess_shell` that names a network program literally: `curl`, `wget`, `ssh`,
  `scp`, `sftp`, `rsync`, `nc`, `ncat`, `netcat`, `socat`, `telnet`, `ftp`, `lftp`,
  `aria2c`, `gh`, `pip`, `pip3`, `npm`, `npx`, or `git` with `clone`, `fetch`, `pull`,
  `push`, `ls-remote` or `submodule`.
- **A module name built at run time.** `importlib.import_module(name)` or `__import__(name)`
  where `name` is not a literal string.

No warning fires on the current tree.

## What it cannot see

- A module name built at run time (warned about, but not resolved), code run through
  `exec`, `eval` or `runpy`, files loaded by path, and native code reached through `ctypes`
  or a compiled extension.
- A network program run through a wrapper function or a variable. For example,
  `tools/build_research_shelf.py` runs `git fetch` against GitHub through its own `git()`
  helper, so the audit cannot see it. It is an owner-run tool that copies pinned public
  repositories into the research shelf.
- Network use one step removed. A file that calls an allowlisted ALFRED module is not
  flagged itself: the browser checks start `alfred.desk_http.DeskHTTPServer`, and
  `tools/evaluate_real_model.py` uses `alfred.local_model`. The allowlisted module is the
  reviewed gateway.
- An asyncio event loop is recognised only in a file that imports asyncio; a loop object
  passed in from another file is not.
- Files other than `.py`, and folders other than `alfred/` and `tools/`.
- Whether the allowlisted code really stays on loopback or on the named hosts. That is what
  the reasons and code review are for.

## The allowlist

`tools/egress_allowlist.json` holds `schema` (always 1), a short `about` note and
`entries`. Each entry has exactly three fields:

- `module`: the file's path from the repository root, under `alfred/` or `tools/`;
- `imports`: the watched names it uses, spelled exactly as the audit reports them;
- `reason`: one line saying where the connection goes (loopback only, or which hosts) or
  that it is a parser only, and who runs it.

The audit refuses a malformed list with exit code 2: not valid JSON, unknown or missing
fields, a module path that is absolute, contains `..`, is not a `.py` file, lies outside
`alfred/` and `tools/` or inside `third_party/`, the same module twice, the same import
twice, an import that is not a watched network module, or a reason that is empty or longer
than one line. The tests also keep the shipped list sorted by module and by import, and
require every listed module to be named in this document.

### Current entries

These were checked against the code at the time of writing; the reason in the JSON file is
the one the audit holds.

| Module | Imports | Why |
|---|---|---|
| `alfred/desk_http.py` | `http.server`, `urllib.parse` | The loopback desk server. Binds 127.0.0.1 only and checks Host and Origin; `urllib.parse` only splits request paths and query strings. |
| `alfred/httpd.py` | `http.server` | The original local server. Binds 127.0.0.1 only and rejects any other Host header. |
| `alfred/local_model.py` | `http.client` | Opt-in local model adapter, off by default. Connects only to 127.0.0.1 on a configured port for a local Ollama; no cloud endpoint, redirect or credential. |
| `alfred/grounded.py` | `urllib.parse` | Parser only: `quote()` escapes text for a local link. |
| `alfred/knowledge.py` | `urllib.parse` | Parser only: `unquote()` and `urlsplit()` read Markdown link targets inside the vault. |
| `alfred/knowledge_http.py` | `urllib.parse` | Parser only: `parse_qs()` reads query strings already received by the loopback desk server. |
| `tools/check_memory_plan.py` | `urllib.parse` | Parser only: `urlsplit()` and `unquote()` resolve Markdown links in the plan. |
| `tools/build_source_library.py` | `urllib.error`, `urllib.parse`, `urllib.request` | Owner-run source library refresh. Downloads pinned public repositories from api.github.com and codeload.github.com only; `--verify`, as CI runs it, is offline. |
| `tools/import_selected.py` | `urllib.error`, `urllib.parse`, `urllib.request` | Owner-run source import. Downloads pinned files from api.github.com and raw.githubusercontent.com only; run by the owner or the import-research workflow. |
| `tools/import_sources.py` | `urllib.request` | Owner-run source import. Downloads pinned archives from codeload.github.com only and refuses a redirect elsewhere; `--verify`, as CI runs it, is offline. |
| `tools/evaluate_conversation_model.py` | `http.client` | Model experiment. Talks to the loopback desk server on 127.0.0.1, which reaches a local Ollama; run only by the model evaluation workflow or the owner. |
| `tools/check_routines_browser.py` | `http.server`, `playwright.sync_api` | Browser check. Serves the built console from a 127.0.0.1 static server beside the loopback desk server and drives headless Chromium through Playwright; run by CI and the owner only. |
| Browser checks (list below) | `playwright.sync_api` | Drive headless Chromium through Playwright against the loopback desk server on 127.0.0.1; run by CI and the owner only. |
| Preview checks (list below) | `playwright.sync_api` | Open a built static preview from a `file://` path in headless Chromium through Playwright, with no server; run by CI and the owner only. |

Browser checks: `tools/check_capture_browser.py`, `tools/check_console_connected_browser.py`,
`tools/check_conversation_browser.py`, `tools/check_desk_browser.py`,
`tools/check_executive_browser.py`, `tools/check_grounded_browser.py`,
`tools/check_hub_goals_browser.py`, `tools/check_hub_integrate_browser.py`,
`tools/check_knowledge_browser.py`, `tools/check_learning_browser.py`,
`tools/check_memory_browser.py`, `tools/check_memory_context_browser.py`,
`tools/check_os_browser.py`, `tools/check_recovery_browser.py`,
`tools/check_sync_conflict_browser.py`, `tools/check_temporal_review_browser.py`,
`tools/check_voice_browser.py`.

Preview checks: `tools/check_conversation_preview.py`, `tools/check_grounded_preview.py`,
`tools/check_memory_preview.py`, `tools/check_os_preview.py`.

A browser is itself able to reach the network, which is why Playwright is watched even
though every page these checks open is local.

### Adding, changing or removing an entry

1. First ask whether the new code can go through a module that is already allowed, such as
   the loopback desk server, instead of opening its own connection.
2. Run the audit. The finding names the file and the exact import to list.
3. Add or extend the entry in `tools/egress_allowlist.json`, keeping entries sorted by
   module and imports sorted, with a reason that says where connections go and who runs
   the code. Update the table above in the same change.
4. Say in the pull request why the network use is needed. The change is reviewed like any
   other, and the owner approves the merge.
5. When code stops using a network module, remove it from the entry (or remove the entry).
   The audit fails until you do.

Changing the watched names (`WATCHED`), the warning lists or the skipped folders is a
change to the audit itself and needs its tests updated first.

## In CI

The tool is not yet a separate CI step; wiring it in is a follow-up. The step to add is:

```
python3 tools/egress_audit.py --self-test
python3 tools/egress_audit.py
```

Until then, `tests/test_egress_audit.py` already audits the real tree against the shipped
list, so the existing `python3 -m unittest discover -s tests` run in CI fails on an
unlisted or stale network import.
