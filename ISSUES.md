# DJConnect Issues Backlog

## Open / Needs Field Validation

### PTT STT provider compatibility

- Status: open.
- Area: voice endpoint / Home Assistant STT.
- Symptom: Some HA STT providers may reject WAV metadata or return no recognized text.
- Current mitigation: Integration logs selected provider, WAV metadata, provider result state and Assist event types without logging transcript/audio/secrets.
- Next action: Test the latest HACS release with the actual HA STT provider selected in options.

### Existing installations may need one successful `/status` to self-repair

- Status: open / expected migration behavior.
- Area: pairing/discovery.
- Symptom: Older config entries may still contain a setup-code-derived `device_id`, no real Client API URL, or an ESP-only assumption for app clients.
- Current mitigation: `/pair` and `/status` now persist real model/app-specific device ids and reported `local_url`.
- Next action: Verify existing paired ESP posts `/status`; if not, manually use advanced device URL once or re-pair.

### iOS/macOS pairing and playback need field validation

- Status: open / field validation.
- Area: app clients.
- Symptom: iOS/macOS clients depend on the app-reported Client API URL and must not expose ESP-only firmware/reboot controls.
- Current mitigation: Client type and Client API URL are visible in normal pairing; OTA update and reboot entities are skipped/unavailable for `ios` and `macos`.
- Next action: Test fresh iOS/macOS pairing, re-pairing and PTT playback after HACS install/restart.

### mDNS reliability varies by network

- Status: open / environmental.
- Area: device discovery.
- Symptom: HA may not resolve or browse `.local` names on some networks/VLANs.
- Current mitigation: Runtime uses device-reported URL, exact `_djconnect._tcp`, single visible DJConnect service fallback, and advanced manual URL override.
- Next action: Test on target WiFi/VLAN setup and document any router/mDNS repeater requirements.

### Raspberry Pi pairing-info reachability needs field validation

- Status: open / field validation.
- Area: pairing/discovery.
- Symptom: A Raspberry Pi client may be visible through `_djconnect._tcp` while Home Assistant cannot reach the advertised Client API URL or `/api/device/pairing-info`.
- Current mitigation: Discovery validates `client_type=raspberry_pi` against `djconnect-raspberry-pi-XXXXXXXXXXXX`, uses TXT `local_url` or resolved address/port, probes `/api/device/pairing-info`, pre-fills confirmed metadata, and shows a translated pairing-info reachability error when TXT is visible but the endpoint is not reachable.
- Next action: Test on the real Pi client/network that the advertised Client API URL is reachable from Home Assistant and that pairing-info returns device ID, client type, name, pair code, version and paired state.

### Home Assistant restart is still required after HACS update

- Status: known limitation.
- Area: deployment.
- Symptom: Updated Python code is not reliably loaded until HA restarts.
- Current mitigation: README/release checklist says to restart HA after installing a HACS release.
- Next action: Keep explaining this clearly to users; no code fix expected.

### HA frontend icon/cache behavior

- Status: open / frontend cache dependent.
- Area: branding.
- Symptom: Integration icon/logo may remain white or stale after update.
- Current mitigation: Brand assets exist in `custom_components/djconnect/brand/`; release checklist includes browser/app cache refresh.
- Next action: Re-check HA frontend behavior after HACS install and cache refresh.

## Recently Fixed / Monitor

### Pairing confirmation state

- Status: fixed in latest release line, monitor after install.
- Area: pairing/provisioning.
- Previous symptom: HA could show `paired` because a local token existed while the ESP still showed its pairing code.
- Fix: HA shows `pending` until ESP confirms `ha_pairing_status=paired`, and retries `/api/device/pair` when confirmation is missing.
- Validation: Confirm the ESP leaves the pairing screen and HA status changes from `pending` to `paired`.

### Unknown local URL during Spotify provisioning

- Status: fixed in latest release line, monitor after install.
- Area: provisioning/discovery.
- Previous symptom: `DJConnect device local_url is unknown` during opportunistic Spotify provisioning.
- Fix: Expected reachability/local URL failures defer quietly; real device identity and local URL are restored/persisted from entry data, `/pair` and `/status`.
- Validation: Confirm status repair persists real `local_url` and provisioning succeeds once ESP is reachable.

### STT WAV bit-rate metadata

- Status: fixed after provider rejection report, included in latest release line.
- Area: voice endpoint / STT.
- Previous symptom: Provider rejected metadata with stream bit rate like `256000` instead of WAV bits per sample.
- Fix: STT metadata now uses bits per sample, e.g. `16`, derived from WAV sample width.
- Validation: Confirm provider no longer logs unsupported metadata for 16-bit PCM WAV.

### Text-only voice test triggering Spotify command parsing

- Status: fixed, monitor.
- Area: voice endpoint / developer test.
- Previous symptom: Web test text request looked up a device named `Test` or attempted Spotify playback.
- Fix: JSON/text-only `/api/djconnect/voice` requests are direct DJ-response tests.
- Validation: Confirm web test returns a ready DJ aankondiging and optional TTS audio URL.

### Options flow internal server error

- Status: fixed, monitor.
- Area: options flow.
- Previous symptom: Assigning Home Assistant read-only `config_entry` property caused HTTP 500.
- Fix: Options flow uses its own attribute instead of assigning `config_entry`.
- Validation: Open options flow after each release.

### OTA wrong device target

- Status: fixed, monitor.
- Area: firmware update.
- Previous symptom: ESP rejected OTA when HA sent generic `djconnect-device` as target.
- Fix: OTA payload uses manifest `device`, currently `lilygo-t-embed-s3`.
- Validation: Confirm OTA payload and update entity attributes against firmware release `firmware_manifest.json`.

### HA TTS unsupported audio type

- Status: fixed/handled, monitor.
- Area: DJ aankondiging TTS.
- Previous symptom: HA TTS returned MP3 while integration expected WAV only.
- Fix: Temporary TTS URLs support WAV and MP3; unknown types become text-only fallback.
- Validation: Confirm ESP firmware supports MP3 and plays returned `audio_url`.

### Spotify refresh-token race after iOS/macOS PTT

- Status: fixed in 3.1.8, monitor after install.
- Area: Spotify backend / voice playback.
- Previous symptom: After one PTT DJ announcement from iOS/macOS, HA could create a false Spotify reauthorization repair because concurrent Spotify calls refreshed with the same old refresh token.
- Fix: Spotify access-token refresh is serialized per runtime, cached token is rechecked under the lock, and `invalid_grant` retries once when another call already rotated the refresh token.
- Validation: Trigger several PTT requests from iOS/macOS after HA restart and confirm no false “Spotify autorisatie verlopen of ingetrokken” repair appears.

### Spotify artist queue offset error

- Status: fixed in 3.1.8, monitor after install.
- Area: Spotify backend / queue playback.
- Previous symptom: Selecting a queue item from an artist context could send `context_uri + offset` to Spotify and return `Can't have offset for context type: ARTIST`, which was visible as a DJ announcement.
- Fix: Artist-context queue item playback now starts the selected track URI directly instead of using an invalid artist offset payload.
- Validation: Start an artist, open queue/up-next, select a track and confirm Spotify starts it without an API 400 message on the device.

## Regression Watchlist

- Config flow must not expose manual `oauth_result`.
- Config flow must show `client_type` and Client API URL in normal pairing; iOS/macOS users need it, ESP users usually leave it empty.
- Config/options flow must not require `spotify_player`.
- OTA update and reboot entities must not be active/available for `client_type=ios`, `client_type=macos` or `client_type=raspberry_pi`.
- App-like client discovery must not create setup-code-only duplicates when a stable `djconnect-ios-*`, `djconnect-macos-*` or `djconnect-raspberry-pi-*` ID is known.
- External product website must not imply official Spotify affiliation, endorsement or sponsorship.
- External product website must stay aligned with current setup requirements and local API architecture.
- `stt_engine` must remain visible and configurable.
- No direct external AI/STT/TTS calls should be used by active routes.
- No secret values should appear in logs or diagnostics.
- All entities should remain grouped under one HA device.
- `number.djconnect_volume` must not publish out-of-range values such as `-1`.
- Spotify OAuth scopes must keep `playlist-read-private`.
- Pairing must reject mismatched pairing codes.
- BLE provisioning must remain WiFi-only.
