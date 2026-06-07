# SpotifyDJ Issues Backlog

## Open / Needs Field Validation

### PTT STT provider compatibility

- Status: open.
- Area: voice endpoint / Home Assistant STT.
- Symptom: Some HA STT providers may reject WAV metadata or return no recognized text.
- Current mitigation: Integration logs selected provider, WAV metadata, provider result state and Assist event types without logging transcript/audio/secrets.
- Next action: Test `v2.9.10` with the actual HA STT provider selected in options.

### Existing installations may need one successful `/status` to self-repair

- Status: open / expected migration behavior.
- Area: pairing/discovery.
- Symptom: Older config entries may still contain a setup-code-derived `device_id` or no real `local_url`.
- Current mitigation: `/pair` and `/status` now persist real `spotifydj-XXXXXXXXXXXX` and reported `local_url`.
- Next action: Verify existing paired ESP posts `/status`; if not, manually use advanced device URL once or re-pair.

### mDNS reliability varies by network

- Status: open / environmental.
- Area: device discovery.
- Symptom: HA may not resolve or browse `.local` names on some networks/VLANs.
- Current mitigation: Runtime uses device-reported URL, exact `_spotifydj._tcp`, single visible SpotifyDJ service fallback, and advanced manual URL override.
- Next action: Test on target WiFi/VLAN setup and document any router/mDNS repeater requirements.

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
- Current mitigation: Brand assets exist in `custom_components/spotify_dj/brand/`; release checklist includes browser/app cache refresh.
- Next action: Re-check HA frontend behavior after HACS install and cache refresh.

## Recently Fixed / Monitor

### Startup re-pair attempt on already paired devices

- Status: fixed in `v2.9.10`, monitor after install.
- Area: pairing/provisioning.
- Previous symptom: HA startup logged `ESP pairing failed HTTP 502` although the device was already paired.
- Fix: Startup provisioning skips `/api/device/pair` when a device token already exists.
- Validation: Confirm no startup re-pair attempt in HA logs after restart.

### Unknown local URL during Spotify provisioning

- Status: fixed in `v2.9.10`, monitor after install.
- Area: provisioning/discovery.
- Previous symptom: `SpotifyDJ device local_url is unknown` during opportunistic Spotify provisioning.
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
- Fix: JSON/text-only `/api/spotify_dj/voice` requests are direct DJ-response tests.
- Validation: Confirm web test returns a ready DJ response and optional TTS audio URL.

### Options flow internal server error

- Status: fixed, monitor.
- Area: options flow.
- Previous symptom: Assigning Home Assistant read-only `config_entry` property caused HTTP 500.
- Fix: Options flow uses its own attribute instead of assigning `config_entry`.
- Validation: Open options flow after each release.

### OTA wrong device target

- Status: fixed, monitor.
- Area: firmware update.
- Previous symptom: ESP rejected OTA when HA sent generic `spotifydj-device` as target.
- Fix: OTA payload uses manifest `device`, currently `lilygo-t-embed-s3`.
- Validation: Confirm OTA payload and update entity attributes against firmware release `firmware_manifest.json`.

### HA TTS unsupported audio type

- Status: fixed/handled, monitor.
- Area: DJ response TTS.
- Previous symptom: HA TTS returned MP3 while integration expected WAV only.
- Fix: Temporary TTS URLs support WAV and MP3; unknown types become text-only fallback.
- Validation: Confirm ESP firmware supports MP3 and plays returned `audio_url`.

## Regression Watchlist

- Config flow must not expose manual `oauth_result`.
- Config flow must not require normal users to fill local device URL.
- Config/options flow must not require `spotify_player`.
- Website onepager must not imply official Spotify affiliation, endorsement or sponsorship.
- Website onepager must stay aligned with current setup requirements and local API architecture.
- `stt_engine` must remain visible and configurable.
- No direct external AI/STT/TTS calls should be used by active routes.
- No secret values should appear in logs or diagnostics.
- All entities should remain grouped under one HA device.
- `number.spotifydj_volume` must not publish out-of-range values such as `-1`.
- Spotify OAuth scopes must keep `playlist-read-private`.
- Pairing must reject mismatched pairing codes.
- BLE provisioning must remain WiFi-only.
