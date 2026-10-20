# Upstream research library: actual files plus reproducible full clones

## Decision
This is **not just a list**. The PR includes pinned, inert *selected source files* from six external projects under `third_party/research-v2/` so code can be studied immediately and reviewed in the diff. The source pointers are recorded in `UPSTREAMS.json`. **These are not full Git clones**, because full upstream history and large binary/model files have deliberately not been imported through this connector. A clone-at-pinned-SHA workflow is provided below for explicit use in a suitably networked, isolated research workspace. Do not mislabel partial snapshots as full clones.

## New snapshot inventory
- [espressif/esp-csi](https://github.com/espressif/esp-csi/tree/8633d67152db2808f141cc1595970aa9cf406045), `8633d67152db2808f141cc1595970aa9cf406045`. Wi-Fi channel-state information and presence detection. 3/3 selected files archived; licence classification: Apache-2.0.
- [esphome/bluetooth-proxies](https://github.com/esphome/bluetooth-proxies/tree/6387b836d61375b273065501a31fe936225eb620), `6387b836d61375b273065501a31fe936225eb620`. Room-scale trusted-device and BLE proxy infrastructure. 3/3 selected files archived; licence classification: Apache-2.0.
- [dscripka/openWakeWord](https://github.com/dscripka/openWakeWord/tree/368c03716d1e92591906a84949bc477f3a834455), `368c03716d1e92591906a84949bc477f3a834455`. Local wake word and speech activation. 4/4 selected files archived; licence classification: Apache-2.0 code; included pretrained models CC BY-NC-SA 4.0.
- [pyannote/pyannote-audio](https://github.com/pyannote/pyannote-audio/tree/b749285c5cdd4636b2edc7f766f1352c8dde9369), `b749285c5cdd4636b2edc7f766f1352c8dde9369`. Speech activity, speaker diarisation and overlap. 3/3 selected files archived; licence classification: MIT source; model weights and gated models separately licensed.
- [blakeblackshear/frigate](https://github.com/blakeblackshear/frigate/tree/1a8644fed5f842c4d9c1b53129bab787c9db2180), `1a8644fed5f842c4d9c1b53129bab787c9db2180`. Local camera detection, zones and event metadata. 3/3 selected files archived; licence classification: MIT source; trademarks and model weights separate.
- [AlexxIT/go2rtc](https://github.com/AlexxIT/go2rtc/tree/c245815e75e2a5fd60b4290f12bfc04e55a984d3), `c245815e75e2a5fd60b4290f12bfc04e55a984d3`. Camera feed transport and streaming. 2/2 selected files archived; licence classification: MIT.

## Already archived by ALFRED
Do **not** duplicate `NousResearch/hermes-agent`, `home-assistant/core`, `livekit/agents`, `pipecat-ai/pipecat` or other material indexed in [the existing catalogue](../../third_party/library/README.md). The old full text library is neither installed nor a runtime dependency.

## Reproducible deeper checkout (manual research workstation, not ALFRED runtime)
Run only when an operator intentionally prepares an external research workspace, with Git installed and a network connection. Example:
```sh
mkdir -p external-alfred-v2-research && cd external-alfred-v2-research
git clone --filter=blob:none https://github.com/espressif/esp-csi.git esp-csi
git -C esp-csi checkout --detach 8633d67152db2808f141cc1595970aa9cf406045
```
Run the same pattern using each `repository` and `source_commit` in [UPSTREAMS.json](UPSTREAMS.json). Full clones are **separate from the ALFRED source tree**, never imported as running dependencies, and are not performed by this PR.

## Provenance and risk rules
- All original path names are preserved below `third_party/research-v2/<owner>__<repo>/`. Each machine-readable entry lists the upstream Git blob SHA and commit used for that selection.
- Root code licences permit copying subject to their notices, but the root grant does not clear models, training data, brand, trademarks, third-party dependencies, compiled assets or cloud service usage.
- openWakeWord source is Apache-2.0 while included pretrained wake-word models use a **non-commercial** CC licence. No model binaries were imported.
- pyannote model downloads and gated pipelines may have distinct weights/access terms; no model binaries were imported.
- No external file becomes an ALFRED instruction, workflow, plugin, API credential or installed dependency.
- Future researchers should consider copying more individual implementation-relevant text once licences, security and data egress are assessed.