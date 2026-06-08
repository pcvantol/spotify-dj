# SpotifyDJ

SpotifyDJ is a Home Assistant custom integration for a SpotifyDJ device.

The Home Assistant integration handles pairing, Spotify OAuth, backend playback commands, OTA firmware updates, device status, and voice/AI integration. Spotify credentials stay in Home Assistant; the ESP sends generic playback commands to the integration.

## Current Version

- Home Assistant integration: `2.9.31`
- Domain: `spotify_dj`
- HACS category: `Integration`
- Device target: SpotifyDJ device
- Firmware mDNS service: `_spotifydj._tcp`
- Device ID format: `spotifydj-lilygo-XXXXXXXXXXXX` for current firmware; older `spotifydj-XXXXXXXXXXXX` IDs remain accepted for compatibility.

## Features

- Pair a SpotifyDJ device with the displayed pairing code or 12-character device suffix.
- Optionally provision WiFi credentials over BLE before normal pairing.
- Provision a per-device bearer token.
- Run Spotify OAuth with PKCE from the Home Assistant config flow.
- Open the Spotify authorization website instead of manually pasting an OAuth result.
- Support a Nabu Casa HTTPS callback at `/api/spotify_dj/spotify/callback`.
- Keep Spotify OAuth credentials in Home Assistant and use them for backend playback commands.
- Control the paired SpotifyDJ device through its HA-native local API.
- Accept raw WAV voice uploads from the ESP and run HA Assist STT in the integration backend.
- Use Home Assistant Assist/TTS settings with safe defaults.
- Process text commands through HA Assist before sending the resulting SpotifyDJ intent to Spotify.
- Use HA-native Assist/TTS routes in active services and entities.
- Track device status, battery, Wi-Fi RSSI, firmware version, and last track.
- Manage firmware updates through a Home Assistant update entity.
- Provide diagnostics with sensitive values redacted.

## Architecture Decisions

SpotifyDJ intentionally separates Home Assistant orchestration from firmware
runtime behavior. These decisions are part of the integration contract:

- **HA-native Assist/STT**: microphone audio is transcribed by this integration through Home Assistant's supported `stt.async_process_audio_stream` helper. SpotifyDJ uses the configured Assist pipeline, falls back to Home Assistant's preferred/default pipeline, then the first pipeline with STT. The ESP uploads raw WAV audio to `POST /api/spotify_dj/voice` using its SpotifyDJ device token; no Home Assistant websocket token is sent to the ESP.
- **No direct external AI/STT/TTS APIs**: active Home Assistant routes use HA Assist and HA TTS only. OpenAI or other direct external AI/STT/TTS clients are not part of the active voice path.
- **Device speaker for DJ responses**: DJ responses are not played through Spotify Connect or a Home Assistant media player. Home Assistant creates a temporary WAV or MP3 URL when possible and posts `text` plus optional `audio_url` to the ESP endpoint `/api/device/dj_response`.
- **HA owns backend playback**: the ESP does not store Spotify OAuth credentials and does not call the Spotify Web API directly. It sends generic playback commands to `POST /api/spotify_dj/command`; Home Assistant translates them to the current backend, currently Spotify.
- **Native playback proxy**: Home Assistant exposes a SpotifyDJ `media_player` for the backend playback session. It does not mean music plays through the ESP speaker; the ESP speaker is reserved for local cues and DJ responses.
- **Refresh-token rotation aware**: Spotify refresh tokens can rotate. Home Assistant stores the latest token and uses it as the canonical source for HA backend playback. Pair/status responses never include Spotify OAuth secrets.
- **OAuth through Home Assistant external step**: Spotify OAuth uses PKCE and the Home Assistant external step flow. The callback remains `/api/spotify_dj/spotify/callback`, with Nabu Casa HTTPS URLs preferred.
- **Pairing over WiFi, BLE only for WiFi credentials**: BLE provisioning writes only WiFi SSID/password to setup-mode devices. Spotify credentials, device tokens and other secrets are never sent over BLE.
- **mDNS first, manual URL as fallback**: the manual device URL is hidden from normal users. Runtime prefers the device-reported `local_url`, exact `_spotifydj._tcp` mDNS matches, then a single visible SpotifyDJ mDNS device. A fallback hostname is only generated from a real 12-character device suffix, not from a 6 digit setup code.
- **Inline advanced options**: firmware repository settings, firmware channel, Spotify source override, manual device URL, max audio bytes and OTA battery settings are revealed through a local “show advanced options” checkbox instead of Home Assistant's deprecated advanced-mode property.
- **Single Home Assistant device**: sensors, buttons, settings, update and playback proxy entities share one stable device identifier so Home Assistant shows one SpotifyDJ device instead of duplicate device entries.
- **Closed firmware, free integration**: firmware source remains proprietary. The Home Assistant integration is distributed separately under MIT for use with SpotifyDJ devices.
- **No secrets in diagnostics/logs**: diagnostics redact keys containing `token`, `password` or `secret`; logs avoid full ESP payloads and do not intentionally log Spotify refresh tokens, WiFi passwords or device tokens.
- **Trademark clarity**: Spotify is a trademark of Spotify AB. SpotifyDJ does not claim affiliation, endorsement or sponsorship by Spotify AB.

## Repository Layout

- Home Assistant integration: `pcvantol/spotify-dj`
- ESP firmware source: `pcvantol/spotify-dj-app`
- Public firmware releases: `pcvantol/spotify-dj-firmware`

This repository contains the Home Assistant custom integration under `custom_components/spotify_dj`.

Brand images for the Home Assistant frontend are bundled in `custom_components/spotify_dj/brand/`.

The product/marketing onepager is available as a standalone static website in
`website/index.html`. It describes the out-of-the-box experience for
pre-flashed SpotifyDJ devices, the HACS quick start, requirements such as
Spotify Premium, Home Assistant, HA Assist/STT/TTS and 2.4 GHz WiFi, plus the
Spotify trademark/non-affiliation notice. The page can be opened locally in a
browser or hosted as static HTML, for example through GitHub Pages or a separate
product website.

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

`playlist-read-private` is required when Home Assistant lists private or
user-owned playlists for SpotifyDJ backend playback. Existing users who
authorized Spotify before this scope was added must authorize Spotify again.

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
2. If needed, choose one BLE action: write WiFi over Bluetooth, rescan Bluetooth devices, or continue directly to pairing when WiFi was already configured through the device captive portal.
3. After BLE success or captive-portal WiFi setup, wait for the device to restart and show a pairing code.
4. Enter the pairing code shown on the SpotifyDJ device display. This can be the short 6 digit setup code or the 12-character device suffix, for example `90B70990A994`.
5. Choose the SpotifyDJ device UI language (`en` or `nl`); Home Assistant preselects this from the HA language setting when possible.
6. Confirm the HTTPS Home Assistant external URL. SpotifyDJ prefills this from Home Assistant's Network external URL when available and falls back to the Nabu Casa/Home Assistant Cloud remote UI URL.
7. Optionally override the bundled Spotify Client ID under advanced options.
8. Home Assistant opens the Spotify authorization website.
9. Approve access in Spotify.
10. Return to Home Assistant and complete the voice/DJ settings step.

The setup flow no longer shows a manual `oauth_result` field.

BLE WiFi provisioning only writes WiFi credentials to the setup-mode device. It
does not send Spotify credentials, device tokens or other secrets over BLE.

## Voice And DJ Settings

The config flow and options flow include safe defaults for optional voice fields. The Assist pipeline is stored so devices know which HA speech setup to use; SpotifyDJ does not run STT internally.

- Assist pipeline ID
- TTS engine
- TTS language
- TTS voice
- DJ style
- Device UI language for ESP pairing (`en` or `nl`)
- Liked proxy playlist URI
- Firmware repository/channel/options
- OTA battery safety options

The liked proxy playlist can be private. If it is private, make sure Spotify has
been reauthorized with `playlist-read-private`; diagnostics and Home Assistant
repairs show a warning when the stored OAuth scope list is missing required
SpotifyDJ scopes.

Where Home Assistant exposes choices, SpotifyDJ shows populated dropdowns for Assist pipeline, TTS entity, known TTS voices, Spotify market, DJ style, and firmware channel. Stored custom values remain selectable so existing setups keep working. Backend playback is handled by Home Assistant through the SpotifyDJ playback proxy; ESP device settings use the local device command API. Spotify source override, firmware repository settings, firmware channel, manual device URL, max audio bytes, and OTA battery settings are shown only after enabling the inline advanced-options checkbox. The manual device URL is normally not needed: SpotifyDJ resolves the device through `_spotifydj._tcp` mDNS, uses the device-reported `local_url` when available, and only builds `http://spotifydj-[device-suffix].local` when the configured ID contains a real 12-character device suffix.

The options flow also includes an action selector. Use `Reauthorize Spotify` to
refresh OAuth from the integration page, `Retry pairing with current code` to
push a fresh device token to the existing ESP, or `Re-pair with new pairing
code` when the ESP shows a new code.


## Security And Diagnostics

- Pairing is unauthenticated by design, but requires the pairing code or 12-character device suffix shown on the SpotifyDJ device.
- After pairing, device endpoints use the per-device bearer token.
- Home Assistant keeps pairing status `pending` until the ESP confirms `ha_pairing_status=paired`; a local token alone is not treated as confirmed pairing.
- BLE WiFi provisioning sends only SSID/password to the BLE WiFi characteristic; it does not send Spotify credentials, device tokens or other secrets.
- Diagnostics redact keys containing `token`, `password` or `secret`.
- Logs avoid full event payloads and do not intentionally log Spotify refresh tokens, WiFi passwords or device tokens.
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

Spotify OAuth credentials stay in Home Assistant. They are never provisioned to the ESP device; the old ESP `/api/device/provision_spotify` endpoint is no longer used.

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
- `spotify_dj.test_tts`: send a DJ response text to the SpotifyDJ device; Home Assistant tries to generate a temporary WAV or MP3 URL, otherwise the ESP shows text only.
- `spotify_dj.test_command`: test the complete ESP text-command route with `text` and `play`; set `play: false` to avoid starting Spotify playback while still sending the DJ response.
- `spotify_dj.start_spotify_oauth`: generate a Spotify PKCE authorization URL for manual reauthorization/debugging.

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
dj_text -> HA TTS backend -> temporary WAV/MP3 URL -> POST /api/device/dj_response -> ESP speaker/display
```

DJ response failure handling:

| Failure | ESP/user feedback |
| --- | --- |
| HA Assist pipeline cannot process the command | Localized DJ response asks the user to check the selected Assist pipeline. |
| Spotify playback cannot start | Localized DJ response asks the user to check Spotify playback device availability. |
| HA TTS cannot generate WAV or MP3 | ESP receives text-only DJ response without `audio_url`. |
| HA TTS returns unknown audio | ESP receives text-only DJ response without `audio_url`; this is logged only as a debug fallback. |
| ESP `/api/device/dj_response` fails | Voice command returns a controlled `command_failed` JSON response and keeps the original Assist/Spotify error in runtime state. |
| Temporary audio URL is unknown or expired | `GET /api/spotify_dj/tts/{token}.wav` or `.mp3` returns `404` or `410`; trigger the DJ response again. |

Home Assistant posts this payload to the paired SpotifyDJ device:

```json
{
  "text": "Here we go.",
  "audio_url": "http://homeassistant.local:8123/api/spotify_dj/tts/<token>.mp3"
}
```

`audio_url` is optional. If HA TTS cannot produce WAV or MP3 audio, SpotifyDJ
sends only `text` and the ESP displays the response without speech. The ESP
decides whether the temporary URL is WAV, MP3 or unknown based on content type
and/or file header. SpotifyDJ does not send Opus or M4A URLs.

During pairing, SpotifyDJ sends only non-secret device settings to the ESP, such
as `device_token`, `ha_url`, `assist_pipeline_id`, `device_language` and
`language`. Spotify OAuth credentials stay in Home Assistant and are used only by
the HA playback backend. Pair/status payloads must not contain
`refresh_token`, `spotify_refresh_token`, `client_id` or a `spotify` OAuth
object.

Spotify refresh tokens can rotate after OAuth. SpotifyDJ stores newly returned refresh tokens immediately and treats that latest stored value as canonical for HA backend playback. If the ESP later reports `spotify_configured=false`, Home Assistant treats this as a compatibility/status hint, not as a request to send OAuth credentials to the ESP.

Provisioning fields sent to the ESP can include:

```json
{
  "device_token": "<per-device-token>",
  "ha_url": "https://example.ui.nabu.casa",
  "assist_pipeline_id": "...",
  "device_language": "nl",
  "language": "nl",
  "backend_available": true
}
```

The ESP should prefer `device_language` over `language` and store it as
`provision.language`.

## Home Assistant HTTP Endpoints

The integration exposes these endpoints:

```text
POST /api/spotify_dj/pair
POST /api/spotify_dj/voice
POST /api/spotify_dj/command
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

The voice endpoint accepts raw WAV audio from the paired ESP device:

```text
POST /api/spotify_dj/voice
POST /api/spotify_dj/command
Authorization: Bearer <device_token>
Header: X-SpotifyDJ-Device-ID: spotifydj-lilygo-XXXXXXXXXXXX
Content-Type: audio/wav
```

The integration runs HA Assist/STT internally, processes the recognized text,
starts Spotify playback, creates a DJ response, and returns text plus an
optional temporary WAV/MP3 `audio_url`:

```json
{
  "success": true,
  "text": "Daar gaan we...",
  "dj_text": "Daar gaan we...",
  "audio_url": "http://homeassistant.local:8123/api/spotify_dj/tts/token.mp3",
  "audio_type": "mp3"
}
```

JSON/text-only requests remain supported for ESP web tests and diagnostics
through `X-SpotifyDJ-Text` or `{ "text": "Test" }`. They simulate the DJ
response path directly and do not parse a Spotify playback command. Raw WAV PTT
uploads continue through STT, command parsing, Spotify playback and DJ response.

Home Assistant must have an STT provider configured. SpotifyDJ first checks its
own `stt_engine` option, for example `stt.openai_stt` selected or entered in
the integration options. Home Assistant populates this as a dropdown when it can
list `stt.*` entities; otherwise SpotifyDJ keeps it as a free-text field so the
entity id can still be entered manually. If `stt_engine` is empty, SpotifyDJ resolves the selected
Assist pipeline's STT engine, or if no pipeline is stored, Home Assistant's
preferred/default Assist pipeline such as Home Assistant Cloud STT. If a stored
pipeline was removed, SpotifyDJ falls back to the preferred/default pipeline.
If no pipeline STT provider can be resolved, it falls back to the first
available Home Assistant `stt.*` entity, for example `stt.openai_stt`. As a
then resolves direct STT providers through Home Assistant's supported
`stt.async_get_speech_to_text_engine` API and calls the provider audio stream
processor. As a final fallback it uses Home Assistant's official
`assist_pipeline.async_pipeline_from_audio_stream` helper from stage `stt` to
`stt`, which lets Home Assistant resolve the default pipeline internally. At
startup and for WAV uploads the integration logs the selected STT/TTS provider
metadata without tokens or API keys. If no STT provider is found,
`/api/spotify_dj/voice` returns `503` with the checked option keys.

## ESP -> HA Command Endpoint

Firmware sends backend playback commands to Home Assistant instead of storing Spotify credentials locally:

```text
POST /api/spotify_dj/command
```

Required headers are `Authorization: Bearer <device_token>`, `X-SpotifyDJ-Device-ID` and `Content-Type: application/json`. Supported commands include `status`, `devices`, `queue`, `playlists`, `pause`, `play`, `next`, `previous`, `start_liked_proxy`, `start_playlist`, `set_play_mode`, `set_output` and `set_volume`. Responses are generic JSON shapes with `playback`, `devices`, `queue` or `playlists`, so future backends such as Sonos or Home Assistant media players can be added without firmware changes. Logs never include device tokens, Spotify tokens or backend credentials.

## Native Home Assistant Entities

The integration exposes native Home Assistant entities for device status, firmware OTA, screen/device settings, DJ response tests and backend playback control. The `media_player.spotifydj_playback_proxy` entity represents the current music backend session, not the ESP speaker. Music plays on the selected Spotify/output device; the SpotifyDJ speaker is used for local cues and DJ/voice responses.

## ESP Device Endpoints

Home Assistant expects the firmware to expose:

```text
POST /api/device/ota
POST /api/device/dj_response
POST /api/device/command
GET /api/device/info
GET /api/device/pairing-info
POST /api/device/reboot
POST /api/device/forget
GET  /api/device/info
```

The integration uses the device `local_url` from pairing/status when provided. If the field is empty, it resolves the `_spotifydj._tcp` mDNS service for the paired device. When the setup code is only 6 digits, SpotifyDJ can also use the single visible SpotifyDJ mDNS service on the network. Fallback hostnames are only generated for real 12-character device suffixes, including current `spotifydj-lilygo-90B70990A994` IDs and older `spotifydj-90B70990A994` IDs. `spotifydj-[6-digit-code].local` is intentionally ignored.

When the ESP status payload reports `spotify_configured=false`, Home Assistant treats that as a compatibility/status hint. Spotify OAuth credentials stay in Home Assistant and are not returned in status responses.

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
  "version": "2.9.31",
  "device": "lilygo-t-embed-s3",
  "asset": "spotifydj-device-v2.9.31.bin",
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "size": 2113136,
  "min_ha_integration": "2.9.31"
}
```

The binary asset name is the public distribution name. The manifest `device`
field is the ESP OTA target and is sent unchanged to `POST /api/device/ota`.
For the current SpotifyDJ firmware this target is `lilygo-t-embed-s3`; sending
the generic asset prefix as the OTA device target will be rejected by the ESP as
`Wrong device target`.

The firmware version is injected through PlatformIO build flags from the Git tag.

Recommended firmware source release helper:

```bash
./release.sh 2.9.31
```

In the private `spotify-dj-app` repository, the firmware release script should
validate the semantic version, update firmware version metadata, run the
PlatformIO build, rename the firmware binary to `spotifydj-device-vX.Y.Z.bin`,
calculate SHA256, update `firmware_manifest.json`, commit, tag and push.

Preview the firmware release flow without changing files:

```bash
./release.sh 2.9.31 --dry-run
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
- Keep `website/index.html` aligned with the current out-of-the-box setup,
  requirements and legal/trademark wording.
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
git commit -m "Release SpotifyDJ v2.9.31"
git tag v2.9.31
git push origin main
git push origin v2.9.31
gh release create v2.9.31 --title "SpotifyDJ v2.9.31" --notes-file CHANGELOG.md
```

Optional release cleanup helper:

```bash
./cleanup_old_releases.sh --keep 1
./cleanup_old_releases.sh --keep 1 --execute
```

The cleanup helper keeps the newest semantic-version GitHub release/tag by
default and deletes older `vX.Y.Z` releases/tags only when `--execute` is used.

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
- Update `firmware_manifest.json` with `version`, `device`, `asset`, `sha256`, `size` and `min_ha_integration`.
- Keep the asset prefix `spotifydj-device`; use manifest `device` such as `lilygo-t-embed-s3` as the OTA target.
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
- If OTA cannot start, make sure the device has reported `local_url` or can be reached as `http://[device_id].local`.
- If OTA is blocked, check battery level, USB power, and the OTA battery options.
- If the firmware update entity reports a GitHub rate limit, wait for GitHub's API limit to reset; SpotifyDJ keeps the entity loaded and records the temporary error in its attributes.
- If Spotify playback fails, reauthorize Spotify in Home Assistant and check that the selected backend has an active playback target.
- If Spotify returns `invalid_grant` or `Refresh token revoked`, Spotify revoked the stored OAuth token. Open Home Assistant Repairs and choose `Fix` for the SpotifyDJ authorization issue to run Spotify OAuth again.
- If an options-flow Spotify OAuth callback reports an empty failure after Spotify approved access, update to this release or newer; the callback now keeps the stored token even when the options dialog was already closed.
- If the ESP logs `HA playback HTTP 503` immediately after pairing, update to this release or newer; playback backend failures are now returned as JSON without invalidating HA pairing.
- If provisioning says `local_url is unknown`, make sure the device advertises `_spotifydj._tcp` mDNS or temporarily enable advanced options and enter the manual device URL, for example `http://spotifydj-lilygo-90B70990A994.local`.
- If Home Assistant added the integration but the ESP still shows a pairing code, check `sensor.spotifydj_ha_pairingstatus`: `pending` means HA has a local token but the ESP has not confirmed `/api/device/pair` yet. Verify the device URL/mDNS reachability and wait for the next pairing retry or re-pair from the config flow.
- If the ESP briefly shows Home Assistant paired and then returns to a pairing code after the first command, update to this release or newer; SpotifyDJ now accepts the real `spotifydj-lilygo-XXXXXXXXXXXX` device ID after setup-code based direct pairing.
- If the pairing token is stale, open SpotifyDJ options and choose `Retry pairing with current code`. If the device shows a new code, choose `Re-pair with new pairing code`.
- If brightness, speaker volume or timeout entities stay at defaults, make sure the ESP firmware sends these settings in its periodic Home Assistant status payload; SpotifyDJ accepts common aliases such as `brightness`, `cue_volume`, `screen_dim_timeout` and `turn_off_after_ms`.
- If `/api/spotify_dj/voice` returns `No STT provider configured`, select an STT engine in SpotifyDJ options, configure an Assist pipeline with STT such as Home Assistant Cloud STT, or clear the stale SpotifyDJ pipeline option so the integration can use Home Assistant's preferred/default Assist pipeline.
- If WiFi/pairing works but Spotify does not, reauthorize Spotify in Home Assistant; pair/status payloads must not contain Spotify OAuth secrets.
- If Home Assistant cannot find a private `SpotifyDJ Liked Proxy` playlist, reauthorize Spotify so the refresh token includes `playlist-read-private`.
- If a PTT command cannot start Spotify playback, the ESP should receive a friendly DJ response; check that Spotify is authorized in Home Assistant and that the backend has a reachable playback target.
- If `/api/spotify_dj/voice` returns `missing_text`, send raw WAV audio for PTT or a developer test text through `X-SpotifyDJ-Text`.
- If `spoken=false`, HA did not provide a compatible WAV/MP3 URL or the ESP could not play it; the text response should still be displayed.
- If HA TTS returns MP3, SpotifyDJ can send the MP3 `audio_url` to ESP firmware that supports MP3 DJ response playback.
- If Home Assistant reports `Invalid value for number.spotifydj_volume: -1.0`, update to this release or newer; SpotifyDJ treats unknown device volume as unavailable instead of publishing an out-of-range value.
- If the ESP reports `401` for `/api/device/dj_response`, pair the device again so the device token is refreshed.
- If `/api/spotify_dj/tts/{token}.wav` or `.mp3` returns `404` or `410`, the token is unknown or expired; trigger the DJ response again.
- If the ESP cannot download the temporary audio URL, make sure the Home Assistant internal URL is reachable from the SpotifyDJ device network.
- Diagnostics are available from the Home Assistant integration page and redact token/password/secret fields.
