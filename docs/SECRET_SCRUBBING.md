# Secret scrubbing

`alfred/scrub.py` finds credentials in text and blanks them before ALFRED saves the text or
sends it to a model. It is integration plan phase 5 ("secret scrubbing before anything is
saved or sent") and backlog item A2. The module is built and tested, but nothing calls it
yet. "Where it will be called" below is the follow-up.

## What it does

```python
from alfred.scrub import find_secrets, scrub

cleaned, findings = scrub(text)
```

- `scrub(text)` returns the text with every secret replaced by `[redacted:<kind>]`, and the
  findings.
- `find_secrets(text)` returns only the findings, in order.
- A finding is `Finding(kind, start, end, reason)`. It gives the offsets into the original
  text and a fixed description. It never holds the secret, and neither does its `repr`, so
  a finding can be logged, stored or shown to the owner.
- Overlapping findings become one: its span covers them all, and its kind is the most
  specific of theirs (the earlier in the table below). For example, a GitHub token written
  as `api_key = "..."` becomes one `github_token` finding.
- Scrubbing twice changes nothing more, because a `[redacted:...]` marker is never a finding.
- Anything that is not `str` (including `bytes`) raises `TypeError`, so a caller cannot pass
  the wrong thing and get unscrubbed output back.

## What it catches

| Kind | What |
| --- | --- |
| `private_key` | PEM private key blocks (plain, RSA, EC, DSA, OpenSSH, encrypted, PGP). This includes blocks inside JSON with escaped newlines, and blocks cut off before their END line, where the BEGIN line and the key lines after it are blanked. |
| `anthropic_key` | Anthropic API keys (`sk-ant-` and a long random run) |
| `openai_key` | OpenAI API keys (`sk-`, `sk-proj-`, `sk-svcacct-`, `sk-admin-` and a long random run) |
| `github_token` | GitHub personal, OAuth, user, server and refresh tokens, and fine-grained tokens |
| `gitlab_token` | GitLab personal, deploy, runner, trigger and CI build tokens |
| `slack_webhook` | Slack webhook addresses. Anyone holding the address can post. |
| `slack_token` | Slack bot, user, app, refresh and configuration tokens |
| `stripe_key` | Stripe secret and restricted keys (live and test), and webhook signing secrets |
| `google_api_key` | Google API keys |
| `google_oauth` | Google OAuth client secrets and access tokens |
| `npm_token` | npm access tokens |
| `aws_access_key_id` | AWS access key ids, by their published four-letter prefixes |
| `aws_secret_access_key` | A 40-character AWS secret key, but only where a label such as `aws_secret_access_key` names it |
| `azure_storage_key` | The `AccountKey=` value in an Azure storage connection string |
| `jwt` | JSON web tokens (three dot-separated base64url parts, the first two starting `eyJ`) |
| `authorization_header` | The credential in an `Authorization: Bearer`, `Basic`, `Token`, `Digest` or `Bot` header, in any case and quoting, or a random run after `Bearer` |
| `url_password` | The password in a URL's `user:password@` part, for any scheme. The user name and host are kept. |
| `password` | A value labelled `password`, `passwd`, `pwd` or `passphrase`, including names such as `db_password` |
| `secret_assignment` | A value labelled `secret`, `client_secret`, `secret_key`, `private_key`, `api_key`, `access_token`, `auth_token` or `token`, including names such as `OPENAI_API_KEY` |

For the provider kinds, only the token itself is blanked. For the header, URL and labelled
kinds, only the value is blanked, so `password: [redacted:password]` still shows what was
there.

## What it leaves alone

The tests pin each of these:

- **Ordinary text:**
  - prose and Markdown, including links without passwords
  - versions, dates and times
- **Strings that look random but are not secret:**
  - commit hashes, SHA-256, SHA-1 and MD5 digests (ALFRED stores these everywhere)
  - UUIDs, and ALFRED's own ids such as `job-` or `mandate-` followed by hex
  - Stripe publishable keys, which are public
- **Prose that names a secret without giving one**, such as "Keep your password in the
  keychain", "The secret: plan ahead" or "Token: see below".
- **Code and templates that name a secret without holding one:**
  - `password = os.environ[...]`, `api_key = get_key(name)`, `login(password=password)`
  - `{'password': password}`, `self.secret`, `max_tokens=500`
  - placeholders: `${DB_PASSWORD}`, `<your key here>`, `'***'`, `None`, empty strings

The rules for a labelled value:
- **Quoted values:** a quoted value of four or more characters is a secret unless it is a
  placeholder.
- **Unquoted values after a password label:** these are secrets unless they look like
  code: a call, a subscript, an attribute, a bare variable name after `=`, or a value after
  a quoted dictionary key.
- **Unquoted values after the other labels:** these must also mix letters and digits,
  because "Token: see below" is prose.

## What it cannot catch

These are known gaps, so no caller should assume clean output means no secrets:

- **Secrets without a recognisable shape:**
  - a password written as plain words with no label, for example "the door code is
    harbour four"
  - a short unquoted password made only of letters after `=` (`password=letmein`), which
    reads the same as code passing a variable. With `:` it is caught.
  - a high-entropy string with no known prefix and no label. There is no entropy guessing,
    because ALFRED's digests and ids would trip it constantly.
  - an AWS secret key on its own, without its label
- **Secrets in a form it does not read:**
  - a value on the line after its label (a YAML block value)
  - secrets that are encoded, split across lines, or inside images and attachments
- **Formats outside the table above**, which need a new kind and its tests.

## Cost

Every pattern starts with a literal, so the regular expression engine can skip ahead to
it. The few checks on the character before a match are done in Python rather than with
look-behinds that would stop that skipping. No pattern can backtrack more than a bounded
run of one character class. PEM blocks are matched by finding all END lines once and
pairing each BEGIN with the next one, rather than with a lazy match that rescans the text
for every BEGIN.

The tests run `scrub` on 1 MB each of twelve kinds of hostile input, and require each to
finish within a second. Examples include BEGIN lines with no END, floods of every token
prefix, labels without values, and URL fragments with no `@`. On the development container
the slowest takes about 0.14 s. 1 MB of genuine fake secrets takes about 0.07 s.

## Where it will be called

This is the follow-up, backlog item C4 and onward. Every call must scrub before the text is
hashed, quoted or stored. Otherwise a stored hash or citation would point at text that no
longer exists.

1. **Brain packets** (`alfred/brain.py`, when the packet is built): the excerpts and
   instruction are scrubbed before they leave for any brain. The findings are recorded on
   the task as kinds and counts, never values.
2. **Harvested text** (`alfred/learning.py`, the harvest step): text a run harvests is
   scrubbed before it is proposed as something learned.
3. **Task results** returned by a brain, before they are stored.
4. **Notes** as they are read from the vault into the index. This waits on encryption
   step 2, because those storage modules are in the encryption claim.
5. **The public hygiene check** (backlog A7) reuses these patterns to fail CI when a
   tracked file contains a credential-shaped literal.
