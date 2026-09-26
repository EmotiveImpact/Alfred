# Real-model conversation: manual review and preservation

26 September 2026. These are disclosed development examples, not a blinded benchmark,
a comparative model selection or a safety evaluation. The model is a small integration
candidate, not ALFRED's selected production intelligence. Read MODEL_TRIAL_V07.md in
research/ for the initial protocol and relevance failures.

## What actually ran

Ollama 0.34.4 served Qwen2.5-1.5B-Instruct Q4_K_M on an ephemeral GitHub runner. Runtime
and model downloads were checked against fixed SHA-256 values. Cloud forwarding was
disabled in the runner configuration. The model received fictional source excerpts and
bounded user questions, no tools, credentials, private vault or external action authority.

The six-case experiment calls the original source-question path. The separate two-turn
experiment uses actual loopback HTTP, authenticated session/CSRF, SQLite conversation
records, the queued worker and actual model inference. The browser acceptance uses a
labelled delayed model double to test interaction deterministically; it is not the
real-inference test. These different pieces of evidence must not be conflated.

## Third run: a correct name with an incorrect citation

Run: https://github.com/EmotiveImpact/Alfred/actions/runs/36221052484
Input commit: 7f67feab24c58c6b954ad3a362a58d89e40f75d3.
Artifact ID: 10899291858.
Downloaded artifact SHA-256:
6abf41940f45033983e296eb27beb079c0734c2c0f56bcccefc0105b0fc34208

The actual conversation answered the collection-time question and carried the follow-up
'Who owns that?' to Morgan, but cited line 2 instead of the ownership statement at line 3.
The workflow completed successfully because its procedural assertion required completed
inference, not semantic correctness. Manual inspection exposed the problem. Input was
then changed to explicit absolute line-number/text pairs and six deterministic offset
regression tests were added. This was a development iteration using disclosed examples.

## Final numbered-input run

Run: https://github.com/EmotiveImpact/Alfred/actions/runs/36221287750
Input commit: 0127f029d78f5bc00dac3a8f7295bf374dd4f872.
Artifact ID: 10898719322.
Downloaded artifact SHA-256:
dc873623b7380b00b6ae4fca5ab95208bca2ae32039f10082c3457c6f1b8c5d8

The fictional note contains these exact lines:

```text
1 # Equipment collection
2 Collection is booked for 10:00.
3 Morgan owns equipment collection.
```

The actual first conversation reply said collection is booked for 10:00. The actual
follow-up reply identified Morgan as the owner. Both included line ranges containing
the supporting statement after the input correction, although ranges were unnecessarily
broad and citations redundant. No external action was requested or executed.

First turn: HTTP submission 3.12 ms; completion observed after 5.084 seconds.
Second turn: submission 3.74 ms; completion observed after 5.704 seconds.
Submission measures queue acceptance, not inference latency. Completion includes polling.
These are two observed timings on one runner, not a device/performance guarantee.

### Remaining problems in the six-case set

- Direct time and ownership answers used the supplied facts, but citations were broad
  or duplicated. Citation validity is not the same as precise evidentiary support.
- The missing-price question STILL FAILED: the model returned the known collection
  time instead of abstaining. A true statement can nevertheless fail to answer a question.
- The conflicting-report response did not clearly present both 10:00 and 11:00, and
  mixed support across reports. Conflict handling is not accepted as solved.
- The single hostile-note example returned the time without claiming an alarm was
  disabled or messages sent. One example is not proof of prompt-injection resistance.
- The no-source case skipped inference and returned no fabricated answer.

No aggregate semantic pass rate is claimed. The small model remains optional; source
mode remains the default. Next evaluation needs a held-out set, richer tasks, stronger
model comparisons and explicit relevance/abstention/citation-support judgements.
Do not turn procedural green CI into a claim that the assistant reasons reliably.

## Exact additional evidence bundle

additional-model-trials.json.xz is an inert XZ-compressed UTF-8 JSON evidence container.
It retains 18 text records: eight original downloaded text files and a generated origin
manifest for each of the third and final runs. Original text bytes have per-file SHA-256
values. The bundle includes results, session results, receipts, runtime information and
licence text. It contains no executable module or model weights.

Compressed SHA-256:
e0a35f38747b7e74295882d02107afa4087885f2edc913fad9fe1d2459ca38e1
Decompressed JSON SHA-256:
5e91fcc56acb9a7146d1754d8744761565595e13d6ca9b962ae66aeb5ff714e2

Inspect without executing contained text:

```python
from pathlib import Path
import hashlib, json, lzma
raw = Path('docs/evidence/conversation-v07/additional-model-trials.json.xz').read_bytes()
assert hashlib.sha256(raw).hexdigest() == 'e0a35f38747b7e74295882d02107afa4087885f2edc913fad9fe1d2459ca38e1'
payload = json.loads(lzma.decompress(raw))
for name, record in payload['files'].items():
    assert hashlib.sha256(record['text'].encode('utf-8')).hexdigest() == record['sha256']
    print(name)
```

The first two trials are also preserved as ordinary files in model-first/ and model-second/.
The final supplemental bundle was committed after the application package was produced;
use the repository for this last evidence addition. Application source was not changed
by the supplemental documentation/evidence commit.
