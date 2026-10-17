# Brief for Astra: Fish Audio voice, speaking only

**Waiting for the owner.** This brief has no claim yet, so Astra cannot start it. Claude adds
the claim once the owner has said yes to three things: using Fish Audio, which areas may send
text to it (plan choice 2), and that the owner holds a Fish Audio account whose key stays on
their own computer.

**Paste into Codex cloud once the claim exists** (repository EmotiveImpact/Alfred, branch `main`):

> You are Astra, working on ALFRED alongside Claude. Read AGENTS.md and coordination/README.md,
> then build the task in coordination/briefs/codex-fish-voice.md. Your claim is
> coordination/claims/codex-fish-voice.md: change only the paths it lists, plus that claim
> file. Work on the branch codex/fish-voice and open a pull request to main when every check
> passes. Do not merge.

## Why this exists

ALFRED can read answers aloud today only through the browser's on-device voice, and
`alfred/voice.py` refuses any network voice. Plan phase 6 adds Fish Audio for the areas the
owner allows to use the cloud, and keeps the on-device voice for every other area. ALFRED only
speaks; it never listens. There is no microphone anywhere in this work.

## What to build (planned paths)

- `alfred/speech.py`: a speech provider interface (`name`, `local`, `synthesise(text) ->
  audio bytes and format`) and a policy function that picks a provider per area: Fish Audio
  only for areas the owner has marked cloud-allowed, the on-device voice otherwise, and a
  refusal when neither is allowed.
- `alfred/speech_fish.py`: the Fish Audio adapter, written against its published HTTP API
  using `urllib` only. The key is read at run time from the operating system's keychain or an
  environment variable on the owner's computer, never from the repository, a config file in
  the repository or a log. Requests carry only the text to speak, never the area name, note
  ids or anything else. Timeouts, size limits and clear refusals on every error.
- Records keep the honesty of `alfred/voice.py`: what text was sent where (as a hash and
  length), whether audio came back, and that playback is a device report, not proof of
  hearing.
- Tests with a fake transport only: no network in tests. Cover the area policy, key absence,
  timeouts, oversize text, error replies, and that nothing private beyond the spoken text
  leaves the machine.
- `docs/VOICE_CLOUD.md` and a receipt under `docs/evidence/fish-voice/`.

## Done when

The adapter passes its offline tests, the area policy refuses everything the owner has not
allowed, CI is green, and the pull request lists what the owner must set up on their computer
(the key in the keychain) to hear it.
