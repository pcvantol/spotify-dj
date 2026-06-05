# SpotifyDJ

SpotifyDJ is a Home Assistant custom integration for a SpotifyDJ device.

The Home Assistant integration handles pairing, Spotify OAuth provisioning, OTA firmware updates, device status, and voice/AI integration. The ESP firmware can keep talking to the Spotify API independently after Home Assistant provisions the Spotify credentials.

## Current Version

- Home Assistant integration: `2.6.2`
- Domain: `spotify_dj`
- HACS category: `Integration`
- Device target: SpotifyDJ device
- Firmware mDNS service: `_spotifydj._tcp`
- Device ID format: `spotifydj-XXXXXXXXXXXX`

## Features

- Pair a SpotifyDJ device with a 6 digit code.
- Optionally provision WiFi credentials over BLE before normal pairing.
- Provision a per-device bearer token.
- Run Spotify OAuth with PKCE from the Home Assistant config flow.
- Open the Spotify authorization website instead of manually pasting an OAuth result.
- Support a Nabu Casa HTTPS callback at `/api/spotify_dj/spotify/callback`.
- Provision Spotify `client_id` and `refresh_token` to the ESP.
- Provision optional MQTT broker settings to the SpotifyDJ device.
- Accept recognized text commands from the ESP after HA Assist websocket STT.
- Use Home Assistant Assist/TTS settings with safe defaults.
- Process text commands through HA Assist before sending the resulting SpotifyDJ intent to Spotify.
- Use HA-native Assist/TTS routes in active services and entities.
- Track device status, battery, Wi-Fi RSSI, firmware version, and last track.
- Manage firmware updates through a Home Assistant update entity.
- Provide diagnostics with sensitive values redacted.

## Architecture Decisions

SpotifyDJ intentionally separates Home Assistant orchestration from firmware
runtime behavior. These decisions are part of the integration contract:

- **HA-native Assist**: microphone audio is not transcribed by this integration. The ESP firmware uses Home Assistant's official Assist websocket API for STT and sends recognized text to `POST /api/spotify_dj/voice` with `X-SpotifyDJ-Text`.
- **No direct external AI/STT/TTS APIs**: active Home Assistant routes use HA Assist and HA TTS only. OpenAI or other direct external AI/STT/TTS clients are not part of the active voice path.
- **Device speaker for DJ responses**: DJ responses are not played through Spotify Connect or a Home Assistant media player. Home Assistant creates a temporary PCM WAV URL when possible and posts `text` plus optional `audio_url` to the ESP endpoint `/api/device/dj_response`.
- **ESP owns Spotify runtime playback**: Home Assistant provisions Spotify OAuth metadata, pairing data and optional MQTT settings. The SpotifyDJ device can continue using Spotify APIs independently after provisioning.
- **OAuth through Home Assistant external step**: Spotify OAuth uses PKCE and the Home Assistant external step flow. The callback remains `/api/spotify_dj/spotify/callback`, with Nabu Casa HTTPS URLs preferred.
- **Pairing over WiFi, BLE only for WiFi credentials**: BLE provisioning writes only WiFi SSID/password to setup-mode devices. Spotify credentials, MQTT credentials and device tokens are never sent over BLE.
- **mDNS first, manual URL as fallback**: the manual device URL is hidden from normal users. Setup stores `http://spotifydj-<pair-code>.local` as a fallback, while runtime prefers device-reported `local_url` and `_spotifydj._tcp` mDNS discovery.
- **Advanced-only operational overrides**: firmware repository settings, firmware channel, MQTT settings, Spotify source override, max audio bytes and OTA battery settings are advanced options to keep normal setup small.
- **Single Home Assistant device**: sensors, button and update entities share one stable device identifier so Home Assistant shows one SpotifyDJ device instead of duplicate device entries.
- **Closed firmware, free integration**: firmware source remains proprietary. The Home Assistant integration is distributed separately under MIT for use with SpotifyDJ devices.
- **No secrets in diagnostics/logs**: diagnostics redact keys containing `token`, `password` or `secret`; logs avoid full ESP payloads and do not intentionally log Spotify refresh tokens, MQTT passwords or device tokens.
- **Trademark clarity**: Spotify is a trademark of Spotify AB. SpotifyDJ does not claim affiliation, endorsement or sponsorship by Spotify AB.

## Repository Layout

- Home Assistant integration: `pcvantol/spotify-dj`
- ESP firmware source: `pcvantol/spotify-dj-app`
- Public firmware releases: `pcvantol/spotify-dj-firmware`

This repository contains the Home Assistant custom integration under `custom_components/spotify_dj`.

Brand images for the Home Assistant frontend are bundled in `custom_components/spotify_dj/brand/`.

## Licensing And Commercial Use

Copyright (c) 2026 Peter van Tol. All rights reserved.

- The SpotifyDJ Home Assistant integration is free software under the MIT License. You may use, copy, modify, publish, distribute, sublicense, and sell the integration under the terms in `LICENSE`.
- SpotifyDJ firmware source code is not part of this repository and is not open source by default.
- SpotifyDJ firmware is proprietary software. The Home Assistant integration may be distributed separately for use with SpotifyDJ devices.
- SpotifyDJ firmware binaries and OTA release assets are covered by `FIRMWARE-LICENSE.md` when they are distributed with SpotifyDJ devices or through official firmware release channels.
- SpotifyDJ hardware can be sourced, white-labeled, sold, and resold separately from this integration, subject to the firmware binary license and any hardware supplier agreements.
- The free Home Assistant integration may be bundled, linked, or recommended with commercial SpotifyDJ devices without changing the closed-source status of the firmware.
- Spotify is a trademark of Spotify AB. SpotifyDJ is not affiliated with, endorsed by, or sponsored by Spotify AB.
- This integration may depend on open-source Python/Home Assistant components. Their licenses remain with their respective authors. See `THIRD_PARTY_NOTICES.md`.

## Install Through HACS

1. Open HACS in Home Assistant.
2. Add `https://github.com/pcvantol/spotify-dj` as a custom repository.
3. Select category `Integration`.
4. Install SpotifyDJ.
5. Restart Home Assistant.
6. Go to **Settings -> Devices & services -> Add integration -> SpotifyDJ**.

## Spotify Developer App

SpotifyDJ includes a default Spotify Client ID. PKCE is used, so no client secret is required. You only need your own Spotify Developer App Client ID if you want to override the bundled app in advanced setup.

SpotifyDJ requests these Spotify OAuth scopes:

- `user-read-playback-state`
- `user-modify-playback-state`
- `user-read-currently-playing`
- `user-library-read`
- `playlist-read-private`
- `playlist-read-collaborative`
- `user-read-recently-played`
- `user-top-read`

`playlist-read-private` is required when the ESP firmware searches `/me/playlists`
for a private or user-owned `SpotifyDJ Liked Proxy` playlist. Existing users who
authorized Spotify before this scope was added must authorize Spotify again and
then run `spotify_dj.provision_spotify_credentials`.

Add this redirect URI to the Spotify app:

```text
https://<your-nabu-casa-id>.ui.nabu.casa/api/spotify_dj/spotify/callback
```

For local-only development you can use a reachable Home Assistant URL instead:

```text
http://homeassistant.local:8123/api/spotify_dj/spotify/callback
```

The redirect URI in Spotify must exactly match the Home Assistant external URL plus `/api/spotify_dj/spotify/callback`.

## Add SpotifyDJ In Home Assistant

1. Choose whether the SpotifyDJ device is already on WiFi or needs BLE WiFi provisioning.
2. If needed, select the `SpotifyDJ xxxx` BLE device and enter WiFi SSID/password.
3. After BLE success, wait for the device to restart and come online over WiFi.
4. Enter the 6 digit pair code shown on the SpotifyDJ device display.
5. Choose the SpotifyDJ device UI language (`en` or `nl`); Home Assistant preselects this from the HA language setting when possible.
6. Enter the HTTPS Home Assistant external URL, preferably the Nabu Casa URL.
7. Optionally override the bundled Spotify Client ID under advanced options.
8. Home Assistant opens the Spotify authorization website.
9. Approve access in Spotify.
10. Return to Home Assistant and complete the voice/DJ settings step.

The setup flow no longer shows a manual `oauth_result` field.

BLE WiFi provisioning only writes WiFi credentials to the setup-mode device. It
does not send Spotify credentials, MQTT credentials or device tokens over BLE.

## Voice And DJ Settings

The config flow and options flow include safe defaults for optional voice fields. The Assist pipeline is stored for ESP provisioning; SpotifyDJ does not stream microphone audio or run STT internally.

- Assist pipeline ID
- TTS engine
- TTS language
- TTS voice
- DJ style
- Required Spotify player
- Device UI language for ESP pairing (`en` or `nl`)
- Liked proxy playlist URI
- Firmware repository/channel/options
- OTA battery safety options

The liked proxy playlist can be private. If it is private, make sure Spotify has
been reauthorized with `playlist-read-private`; diagnostics and Home Assistant
repairs show a warning when the stored OAuth scope list is missing required
SpotifyDJ scopes.

Where Home Assistant exposes choices, SpotifyDJ shows populated dropdowns for Assist pipeline, TTS entity, known TTS voices, Spotify media player, Spotify market, DJ style, and firmware channel. Stored custom values remain selectable so existing setups keep working. The Spotify media player is required. Spotify source override, MQTT broker settings, firmware repository settings, firmware channel, manual device URL, max audio bytes, and OTA battery settings are shown only when advanced options are enabled. The manual device URL is normally not needed: SpotifyDJ stores an automatic `http://spotifydj-<pair-code>.local` fallback during setup, resolves the device through `_spotifydj._tcp` mDNS, and then uses the device-reported `local_url` when available.

Advanced MQTT settings can provision these fields to the SpotifyDJ device when `mqtt_host` is set. The MQTT host field defaults to `homeassistant.local`; override it in advanced options if your broker uses a different host name or IP address.

- `mqtt_host`
- `mqtt_port`
- `mqtt_username`
- `mqtt_password`

Leave MQTT fields empty if the firmware does not use MQTT. Existing SpotifyDJ values override the static MQTT defaults. MQTT passwords are redacted from diagnostics.

The options flow uses Home Assistant's read-only config entry API safely, so
opening SpotifyDJ options should not trigger an internal server error on newer
Home Assistant versions.

## Security And Diagnostics

- Pairing is unauthenticated by design, but requires the 6 digit pairing code shown on the SpotifyDJ device.
- After pairing, device endpoints use the per-device bearer token.
- BLE WiFi provisioning sends only SSID/password to the BLE WiFi characteristic; it does not send Spotify credentials, MQTT credentials or device tokens.
- Diagnostics redact keys containing `token`, `password` or `secret`.
- Logs avoid full event payloads and do not intentionally log Spotify refresh tokens, MQTT passwords or device tokens.
- The bundled Spotify Client ID is not a secret; PKCE is used and no client secret is required.

Supported DJ styles are:

- `classic_dutch_radio`
- `calm_evening`
- `festival`
- `minimal`

## Home Assistant Entities

SpotifyDJ creates:

- `sensor.spotifydj_status`
- `sensor.spotifydj_last_command`
- `sensor.spotifydj_battery`
- `sensor.spotifydj_wifi_rssi`
- `sensor.spotifydj_firmware_version`
- `sensor.spotifydj_last_track`
- `button.spotifydj_test_dj_voice`
- `update.spotifydj_firmware`

Entity IDs can differ if Home Assistant has renamed the device or entities.

Use `button.spotifydj_test_dj_voice` after setup to test the configured HA TTS
engine, voice and language with a short DJ response on the SpotifyDJ device
speaker/display. This does not use Spotify Connect or a Home Assistant media
player for DJ response audio.

## Services

SpotifyDJ registers these services:

- `spotify_dj.test_parse`
- `spotify_dj.test_tts`
- `spotify_dj.test_command`
- `spotify_dj.start_spotify_oauth`
- `spotify_dj.provision_spotify_credentials`

Use `spotify_dj.provision_spotify_credentials` after OAuth if you want Home Assistant to send the stored Spotify credentials to the paired SpotifyDJ device again.

`spotify_dj.test_parse` and `spotify_dj.test_command` use this flow:

```text
text -> HA Assist conversation pipeline -> SpotifyDJ intent -> Spotify -> ESP DJ response
```

`spotify_dj.test_command` accepts `text` and optional `play`. With `play: false`, it uses the same command parser path without starting Spotify playback.

If command processing or Spotify playback fails, SpotifyDJ still sends a
friendly DJ response to the ESP device when possible, so the user hears or sees
what went wrong instead of only receiving an HTTP error. This fallback text uses
the SpotifyDJ device language selected during pairing (`en` or `nl`) and
distinguishes Assist pipeline failures from Spotify playback failures.

If HA Assist returns a generic smart-home answer such as "I cannot play music",
SpotifyDJ does not use that sentence as the DJ announcement. It keeps the
Spotify search intent based on the original command and falls back to the
SpotifyDJ DJ response text unless Assist returns explicit `spotify_dj` data.

Developer action overview:

- `spotify_dj.test_parse`: test only the HA Assist conversation parser and return the SpotifyDJ intent; no playback and no DJ response delivery.
- `spotify_dj.test_tts`: send a DJ response text to the SpotifyDJ device; Home Assistant tries to generate a temporary PCM WAV URL, otherwise the ESP shows text only.
- `spotify_dj.test_command`: test the complete ESP text-command route with `text` and `play`; set `play: false` to avoid starting Spotify playback while still sending the DJ response.
- `spotify_dj.start_spotify_oauth`: generate a Spotify PKCE authorization URL for manual reprovisioning/debugging.
- `spotify_dj.provision_spotify_credentials`: resend stored Spotify credentials, Assist metadata and optional MQTT settings to the paired SpotifyDJ device.

Developer actions return response data where Home Assistant supports it. Enable
debug logging for `custom_components.spotify_dj` when you want to inspect the
selected TTS engine, OAuth redirect URI, DJ response result, or
command-processing result. Spotify refresh tokens and device tokens are not
logged.

Example developer action data:

```yaml
action: spotify_dj.test_command
data:
  text: "Play Pearl Jam"
  play: false
```

Example DJ response test:

```yaml
action: spotify_dj.test_tts
data:
  text: "Here we go. SpotifyDJ is paired, the voice works, and I am ready for your next track."
```

DJ response audio flow:

```text
dj_text -> HA TTS backend -> temporary PCM WAV URL -> POST /api/device/dj_response -> ESP speaker/display
```

DJ response failure handling:

| Failure | ESP/user feedback |
| --- | --- |
| HA Assist pipeline cannot process the command | Localized DJ response asks the user to check the selected Assist pipeline. |
| Spotify playback cannot start | Localized DJ response asks the user to check Spotify playback device availability. |
| HA TTS cannot generate PCM WAV | ESP receives text-only DJ response without `audio_url`. |
| HA TTS returns non-WAV audio | ESP receives text-only DJ response without `audio_url`. |
| ESP `/api/device/dj_response` fails | Voice command returns a controlled `command_failed` JSON response and keeps the original Assist/Spotify error in runtime state. |
| Temporary WAV URL is unknown or expired | `GET /api/spotify_dj/tts/{token}.wav` returns `404` or `410`; trigger the DJ response again. |

Home Assistant posts this payload to the paired SpotifyDJ device:

```json
{
  "text": "Here we go.",
  "audio_url": "http://homeassistant.local:8123/api/spotify_dj/tts/<token>.wav"
}
```

`audio_url` is optional. If HA TTS cannot produce a WAV file, SpotifyDJ sends
only `text` and the ESP displays the response without speech. The ESP supports
PCM WAV playback via its own speaker pipeline; SpotifyDJ does not send MP3,
Opus or M4A URLs.

During pairing, SpotifyDJ includes Spotify OAuth credentials when they are
already stored in Home Assistant. For firmware compatibility the pairing payload
contains `refresh_token` and `spotify_refresh_token` both inside the `spotify`
object and as top-level aliases. The same pair/status payloads include
`device_language` and `language` with value `en` or `nl`, so the ESP can store it
as `provision.language` and show its UI in the selected language. Devices that
pair before Spotify OAuth completes can read the same Spotify credential aliases
from the next `/api/spotify_dj/status` response, or receive them through
`spotify_dj.provision_spotify_credentials`.

Provisioning fields sent to the ESP can include:

```json
{
  "device_token": "<per-device-token>",
  "ha_url": "https://example.ui.nabu.casa",
  "assist_pipeline_id": "...",
  "device_language": "nl",
  "language": "nl",
  "mqtt": {
    "host": "mqtt.local",
    "port": 1883,
    "username": "spotifydj",
    "password": "..."
  },
  "spotify": {
    "client_id": "...",
    "refresh_token": "...",
    "spotify_client_id": "...",
    "spotify_refresh_token": "..."
  },
  "spotify_client_id": "...",
  "spotify_refresh_token": "..."
}
```

The ESP should prefer `device_language` over `language` and store it as
`provision.language`.

## Home Assistant HTTP Endpoints

The integration exposes these endpoints:

```text
POST /api/spotify_dj/pair
POST /api/spotify_dj/voice
POST /api/spotify_dj/status
POST /api/spotify_dj/event
GET  /api/spotify_dj/tts/{token}.wav
GET  /api/spotify_dj/spotify/callback
```

The ESP should send status updates to:

```text
POST /api/spotify_dj/status
```

Authenticated device requests use the provisioned bearer token and can include `X-SpotifyDJ-Device-ID`.

BLE setup-mode devices are matched by service UUID:

```text
7f705000-9f8f-4f1a-9b5f-570071fd0001
```

WiFi credentials are written as UTF-8 JSON to characteristic
`7f705001-9f8f-4f1a-9b5f-570071fd0001`; status is read from
`7f705002-9f8f-4f1a-9b5f-570071fd0001`.

The voice endpoint accepts recognized speech text only:

```text
POST /api/spotify_dj/voice
Header: X-SpotifyDJ-Text: Play Pearl Jam
```

JSON is also supported:

```json
{
  "text": "Play Pearl Jam"
}
```

The ESP handles microphone audio with Home Assistant's official Assist websocket API (`/api/websocket`, `assist_pipeline/run`) and then sends the recognized text to SpotifyDJ. Legacy `audio/wav` uploads return a controlled JSON `missing_text` error instead of running STT inside this integration.

## ESP Device Endpoints

Home Assistant expects the firmware to expose:

```text
POST /api/device/ota
POST /api/device/provision_spotify
POST /api/device/dj_response
GET  /api/device/info
```

The integration uses the device `local_url` from pairing/status when provided. If the field is empty, it automatically resolves the `_spotifydj._tcp` mDNS service for the paired device and then falls back to `http://<device_id>.local`. During setup, an empty advanced manual URL is stored as `http://spotifydj-<pair-code>.local`.

## Firmware OTA Releases

Firmware builds come from the private `spotify-dj-app` repo and are published to the public `spotify-dj-firmware` repo.

Firmware source remains closed unless a separate written agreement says otherwise. Firmware binaries and OTA assets are distributed under the SpotifyDJ Firmware Binary License in `FIRMWARE-LICENSE.md`.

Expected release asset name:

```text
spotifydj-device-vX.Y.Z.bin
```

Expected manifest:

```text
firmware_manifest.json
```

Example manifest:

```json
{
  "version": "2.6.2",
  "device": "spotifydj-device",
  "asset": "spotifydj-device-v2.6.2.bin",
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "min_ha_integration": "2.6.2"
}
```

The firmware version is injected through PlatformIO build flags from the Git tag.

Recommended firmware source release helper:

```bash
./release.sh 2.6.2
```

In the private `spotify-dj-app` repository, the firmware release script should
validate the semantic version, update firmware version metadata, run the
PlatformIO build, rename the firmware binary to `spotifydj-device-vX.Y.Z.bin`,
calculate SHA256, update `firmware_manifest.json`, commit, tag and push.

Preview the firmware release flow without changing files:

```bash
./release.sh 2.6.2 --dry-run
```

When publishing to the public firmware repository, use the firmware script's
public-repo option if available:

```bash
./release.sh 2.3.0 --publish-firmware-repo ../spotify-dj-firmware
```

The public `spotify-dj-firmware` repository should contain only the release
binary, `firmware_manifest.json`, release metadata and non-secret documentation.
Do not publish firmware source code, NVS secrets, device tokens, Spotify refresh
tokens or Home Assistant tokens.

## HACS Release Workflow

Use this checklist for every Home Assistant integration release.

Pre-release checklist:

- Confirm the working tree only contains intended changes.
- Update `custom_components/spotify_dj/manifest.json` to the target version.
- Update `custom_components/spotify_dj/const.py` to the same target version.
- Update `README.md` current version, examples, endpoints and HACS instructions.
- Update `CHANGELOG.md` as a single current-version changelog.
- Keep `AGENTS.md` aligned with the current version and release expectations.
- Verify `custom_components/spotify_dj/brand/` contains `icon.png`, `icon@2x.png` and `logo.png`.
- Verify `LICENSE` covers the Home Assistant integration and `FIRMWARE-LICENSE.md` covers firmware binaries.
- Run the lightweight tests:

```bash
python3 -m unittest discover -s tests
```

Tag and publish:

One-liner:

```bash
./release.sh 2.3.0
```

The script updates the integration version in `manifest.json`, `const.py`,
`README.md`, `CHANGELOG.md` and `AGENTS.md` before staging and committing.

Preview without executing git/gh commands:

```bash
./release.sh 2.3.0 --dry-run
```

Manual equivalent:

```bash
git add .
git commit -m "Release SpotifyDJ v2.6.2"
git tag v2.6.2
git push origin main
git push origin v2.6.2
gh release create v2.6.2 --title "SpotifyDJ v2.6.2" --notes-file CHANGELOG.md
```

Home Assistant / HACS verification:

1. Open HACS in Home Assistant.
2. Open SpotifyDJ.
3. Choose **Redownload** or refresh HACS update information.
4. Select and install the new release from HACS.
5. Restart Home Assistant.
6. Go to **Settings -> Devices & services**.
7. Add SpotifyDJ again, or remove and re-add the SpotifyDJ integration if needed.
8. Complete pairing and Spotify OAuth in the SpotifyDJ config flow.
9. Open SpotifyDJ options and verify there is no internal server error.
10. Verify the integration icon/logo appears after browser/app cache refresh.
11. Run `spotify_dj.test_parse`, `spotify_dj.test_command` and `spotify_dj.test_tts`.
12. Verify device status, last command, last track and firmware update entities.

Firmware release cross-check, when publishing firmware as well:

- Build firmware from the private `spotify-dj-app` repository.
- Prefer the private firmware repo one-liner: `./release.sh X.Y.Z`.
- Use `./release.sh X.Y.Z --dry-run` before publishing when in doubt.
- Publish binaries to the public `spotify-dj-firmware` repository.
- Name the release asset `spotifydj-device-vX.Y.Z.bin`.
- Update `firmware_manifest.json` with `version`, `asset`, `sha256` and `min_ha_integration`.
- Confirm OTA discovers the new firmware through the Home Assistant update entity.

## Tests

Run the lightweight unit tests with:

```bash
python3 -m unittest discover -s tests
```

These tests use local stubs for Home Assistant imports and focus on pure SpotifyDJ helpers, OAuth URL building, Assist response mapping, and config-flow translation coverage.

## Troubleshooting

- If Spotify login does not return to Home Assistant, verify the Spotify redirect URI exactly matches the Nabu Casa or external Home Assistant URL.
- If the config flow does not load, restart Home Assistant and check that HACS installed `custom_components/spotify_dj`.
- If the integration icon stays white or generic, update/re-download the HACS integration, restart Home Assistant, and refresh the browser/app cache. Home Assistant 2026.3+ reads custom integration brand images from `custom_components/spotify_dj/brand/`.
- If opening SpotifyDJ options returns an internal server error, update to this release or newer; older builds assigned HA's read-only `config_entry` property.
- If OTA cannot start, make sure the device has reported `local_url` or can be reached as `http://<device_id>.local`.
- If OTA is blocked, check battery level, USB power, and the OTA battery options.
- If provisioning fails, pair the SpotifyDJ device first and run `spotify_dj.provision_spotify_credentials` again.
- If WiFi/MQTT provisioning works but Spotify does not, pair again after OAuth or run `spotify_dj.provision_spotify_credentials`; pair/status payloads should include both top-level `spotify_refresh_token` and `spotify.refresh_token`.
- If the ESP cannot find a private `SpotifyDJ Liked Proxy` playlist, reauthorize Spotify so the refresh token includes `playlist-read-private`, then run `spotify_dj.provision_spotify_credentials`.
- If a PTT command cannot start Spotify playback, the ESP should receive a friendly DJ response; check that the configured Spotify media player is available and has an active Spotify Connect target.
- If `/api/spotify_dj/voice` returns `missing_text`, update the ESP firmware to run HA Assist websocket STT and send `X-SpotifyDJ-Text`.
- If `spoken=false`, HA did not provide a compatible WAV URL or the ESP could not play it; the text response should still be displayed.
- If the ESP reports `401` for `/api/device/dj_response`, pair the device again so the device token is refreshed.
- If `/api/spotify_dj/tts/{token}.wav` returns `404` or `410`, the token is unknown or expired; trigger the DJ response again.
- If the ESP cannot download the WAV URL, make sure the Home Assistant internal URL is reachable from the SpotifyDJ device network.
- Diagnostics are available from the Home Assistant integration page and redact token/password/secret fields.
