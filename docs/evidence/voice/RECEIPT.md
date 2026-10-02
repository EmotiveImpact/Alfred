# VOI-001 receipt: read-aloud with honest states (output only)

2 October 2026, branch `claude/alfred-development-qpgxhg`. Status: **partial**. The commit that
adds this receipt is the tested source; unified CI on that commit is the independent rerun.
**No microphone is requested anywhere**, and listening remains an owner decision (visible
push-to-talk would come first, per the PRD).

## What exists

- In the console's Ask panel, "Read aloud" speaks an answer with the browser's own speech
  synthesis, using **only voices the browser marks as on-device**. An online voice would
  send the text to a speech service off this machine, so it is never used; without an
  on-device voice the console says so and speaks nothing.
- The spoken text is built deterministically from what the answer already shows (question,
  reviewed statements, excerpts as sentences, no bare link names) and ends by saying these
  are the person's notes read aloud, not a generated answer. "What is spoken" shows it
  exactly.
- `alfred/voice.py` keeps the states apart on the server, recording a hash and length of the
  text, never the text or audio:
  - **generated:** the console prepared exactly this text for one of the person's answers;
  - **played, stopped or failed:** the browser's own report of how playback finished,
    labelled as a device report and not proof that anyone heard it;
  - **acknowledged:** the person pressed "I heard this", allowed only after the browser
    reported that playback ended.
- Network voices, other people's answers, withdrawn answers and bad input are refused;
  outcomes are recorded once; routes keep the session and CSRF checks.

## Evidence

| Check | Result |
|---|---|
| `tests/test_voice.py` (3, real HTTP) | separate states, stopped never called played, refusals, no text stored |
| `console/tests/voice.test.ts` (5) | exact spoken text, length bound, on-device voices only with British English preferred, wording |
| `tools/check_voice_browser.py` (12 checks, [report](browser-report.json)) | real speech API with no on-device voice in this build: nothing spoken or recorded ([screenshot](voice-no-local-voice.png)); scripted on-device synthesiser: shown text equals spoken text, played recorded as a device report, separate acknowledgement, stop recorded and not acknowledgeable ([screenshot](voice-played.png)); no microphone request; no foreign requests |

## Not done

- No audio or hardware test: the second browser context uses a scripted synthesiser, so
  nothing here shows real speech quality, timing, interruption or reconnection on a device.
- No listening, wake word or push-to-talk; no microphone permission is ever requested.
- Voices and pronunciation depend on the person's browser and operating system.
