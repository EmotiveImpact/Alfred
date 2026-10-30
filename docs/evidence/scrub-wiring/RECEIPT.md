# Receipt: scrubbing wired into brain packets and harvest (backlog C4)

Tested commit: `a1ff980e7` on `claude/project-thread-att046-scrub-wiring` (the code and tests),
with `e65ad64fb` (docs only) on top. The branch is based on the secret scrubber branch
(pull request #32) at `704ca6054`. This receipt is committed after both.

| Command | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -p "test_scrub_wiring.py"` | 13 tests, OK |
| `python3 -m unittest discover -s tests -p "test_brain_plug.py"` | 46 tests, OK (unchanged) |
| `python3 -m unittest discover -s tests -p "test_learning.py"` | 39 tests, OK (unchanged) |
| `test_hub_goals.py`, `test_hub_integrate.py`, `test_verification.py`, `test_scrub.py` | 36, 17, 36 and 25 tests, OK (unchanged) |
| `python3 -m unittest discover -s tests` | 1,465 tests, OK, 225 s |
| `python3 tools/check_claims.py --base origin/main --branch claude/project-thread-att046-scrub-wiring` | 4 claim errors, all paths in Astra's `codex-secret-scrubber` claim, which is still active on `main`. Three come from the base branch (pull request #32) and one from this branch's docs commit (`docs/SECRET_SCRUBBING.md`). |
| The same check on a throwaway merge of this branch with `origin/claude/project-thread-att046` (which releases that claim), against that branch | `claims ok` |
| `git diff --check` over both commits | clean |

What the new tests pin (`tests/test_scrub_wiring.py`, fake credentials built at run time):

- A packet carrying a fake GitHub token, AWS key id and labelled password leaves scrubbed:
  the brain, the stored job and `packet_sha256` all hold `[redacted:<kind>]`, and the hash
  differs from the unscrubbed packet's. The task records
  `{"aws_access_key_id":1,"github_token":1,"password":1}` and one `brain.packet_scrubbed`
  audit entry. Resubmitting is idempotent.
- A brain citing the scrubbed excerpt is accepted; quoting the original secret is refused.
- The backend accepts the scrubbed excerpt against the real note bytes, refuses a forged
  one (`excerpt_not_in_bound_revision`) and refuses the unscrubbed one
  (`secret_shaped_value_in_packet`). No brain ran.
- An excerpt's `sha256` is still the stored note revision's hash.
- A clean packet is byte-identical to the hand-built pre-change packet, with the same hash,
  `{}` recorded and no scrub audit entry.
- Goal and learned statements are scrubbed. `validate_packet` refuses a secret left in any
  free-text field.
- After a run and ingest, the only table holding any of the fake secrets is
  `knowledge_notes` (the note index, which waits on encryption step 2).
- An older database without `brain_tasks.scrubbed` gains it when opened, and old tasks
  still ingest.
- Harvest: staged and artefact text with fake credentials is proposed blanked, with kinds
  and counts only; no table holds the staged secrets; an accepted record travels in a packet;
  clean harvests are unchanged; the 43-character bearer-shape refusal is kept.

Limits: synthetic data only, no network, no model. Task results returned by a brain are not
yet scrubbed before they are stored (step 3), and notes are not scrubbed into the index
(step 4). A clean scrub does not mean a text holds no secrets.
