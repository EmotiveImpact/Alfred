# Sensor evidence and practical options
18 October 2026. These are engineering hypotheses and source-backed candidates, not tested ALFRED integrations.

| Method | Useful observation | Can it identify a person? | Important failures | Preferred V2 stance |
| --- | --- | --- | --- | --- |
| ESP32 CSI / 802.11bf sensing | Change in channel, presence or motion proxy | No reliable identity; room counts are experimental and environment-specific | Walls, pets, static occupants, multipath, calibration, device positioning | Exploratory pilot for occupied/unknown; don't claim accurate people count |
| BLE proxy / trusted beacon | A *device* may be nearby | Only identifies a deliberately paired device; not the wearer | Randomised MACs, device left behind, dead battery, relay/spoofing, signal leakage | Room presence hint, never second factor |
| Camera NVR / local inference | Detected objects, people, tracking zones, possible count | Optional face system may propose identity subject to separate lawful basis and opt-in | Occlusion, lighting, angles, false recognition, frame loss, bystanders | Local-only metadata first; no identity on launch |
| Microphone wake/VAD | Wake phrase, speech window, speaker change | Diarisation labels speakers, not names; voice matching can be spoofed | Overlap, noise, replay, cloned voices, accents, distant speech | Opt-in local activation and conversation awareness |
| Phone/watch | Local signed-in user session and nearby device; explicit approval | Device cryptographic account/session identity can authenticate interactions | Theft, lost or shared devices, offline state, notification suppression | Signed approval and private output target, not passive presence proof |
| Digital integrations | Logged communication/calendar/security events | Source grants determine trusted records, not speaker in room | Phishing, stale data, replay, missed webhooks | Always-monitoring engine without room microphone |

### Research sources and engineering implications
- [Espressif ESP-CSI](https://github.com/espressif/esp-csi): CSI samples and examples for sensing. The project's own descriptions address non-contact environmental changes. Its example cloud export must never be switched on by inclusion in this research.
- [IEEE 802.11bf WLAN Sensing](https://standards.ieee.org/ieee/802.11bf/11574/): published sensing standard, **not** a proof of people-counting performance on any arbitrary Wi-Fi router.
- [ESPHome Bluetooth Proxies](https://github.com/esphome/bluetooth-proxies) provide tested hardware configurations for BLE relay; not a biometric identity system. Randomised addresses complicate tracking.
- [Frigate](https://github.com/blakeblackshear/frigate) offers local camera object detection, zones and events. Optional face recognition requires special review and independent error evaluation; do not assume it is safe for authorisation.
- [go2rtc](https://github.com/AlexxIT/go2rtc) offers transport and re-streaming, not person-count truth.
- [pyannote.audio](https://github.com/pyannote/pyannote-audio) supports diarisation; model files and hosted services need their own licences and data-egress review.
- [openWakeWord](https://github.com/dscripka/openWakeWord) source code is Apache 2.0, while **included pretrained models are non-commercial CC BY-NC-SA 4.0**. Do not bundle/adopt those pretrained models into a commercial ALFRED without an independent rights review.
- [Apple LocalAuthentication](https://developer.apple.com/documentation/localauthentication) allows iPhone authentication with OS-protected biometrics; app receives authentication outcome, not iris/face templates. Watch interaction is device/OS-specific, not a guarantee of an always-on arbitrary app wake-word listener.

### Pilot comparisons
- Phase A: 1 room, 0/1/2/3+ participants, seated/moving, door open/closed, pets, Wi-Fi on/off, deliberate sensor outages. Report precision/recall for **presence** and exact-count/confusion matrix separately. Establish non-invasive ground truth with consent.
- Phase B: camera-only versus CSI-only versus paired BLE versus fusion; compare abstain/unknown rate, not just accuracy. Avoid identifying participants by Wi-Fi fingerprint.
- Phase C: several rooms, occupancy transitions, shared walls, stale/mislabelled zones and site connectivity interruptions. No cross-building extrapolation without observed data.
- Phase D: discretion decisions with false-quiet and false-private outcomes. **Speaking private information when another person is present** is the high-cost failure. 
- Phase E: opt-in speech handling with overlap, noise, TV, impersonated wake word, replay and refusal tests. Measure false accepts and false rejects across varied speakers and conditions.

### Source maturity
A standards document establishes standardisation, not ALFRED readiness. A public repository establishes available upstream source, not tested runtime compatibility, real-world accuracy, commercial model rights or privacy compliance.