# DJConnect

<p align="center">
  <img src="https://raw.githubusercontent.com/pcvantol/djconnect/main/assets/djconnect/djconnect-logo.svg" alt="DJConnect" width="760">
</p>

DJConnect. Muziekbediening met karakter.

DJConnect is a Home Assistant custom integration for ESP32, iOS, macOS and Raspberry Pi DJConnect clients. Ask for music, let Home Assistant handle Spotify playback, and hear a personal DJ announcement back on the DJConnect device.

Website: [https://djconnect.pages.dev](https://djconnect.pages.dev)

The Home Assistant integration handles pairing, Spotify OAuth, backend playback commands, OTA firmware updates, device status, and voice/AI integration. Spotify credentials stay in Home Assistant; the ESP sends generic playback commands to the integration.

## Current Version

- Home Assistant integration: `3.1.22`
- Domain: `djconnect`
- HACS category: `Integration`
- Device target: DJConnect device
- Firmware mDNS service: `_djconnect._tcp`
- Device ID formats: `djconnect-lilygo-t-embed-s3-XXXXXXXXXXXX` and `djconnect-esp32-s3-box-3-XXXXXXXXXXXX`.
- Legacy `djconnect-XXXXXXXXXXXX` device IDs are not accepted.

## Features

- Pair a DJConnect device with the displayed pairing code or 12-character device suffix.
- Optionally provision WiFi credentials over BLE before normal pairing.
- Provision a per-device bearer token.
- Run Spotify OAuth with PKCE from the Home Assistant config flow.
- Open the Spotify authorization website instead of manually pasting an OAuth result.
- Support a Nabu Casa HTTPS callback at `/api/djconnect/spotify/callback`.
- Keep Spotify OAuth credentials in Home Assistant and use them for backend playback commands.
- Control the paired DJConnect device through its HA-native local API.
- Accept raw WAV voice uploads from the ESP and run HA Assist STT in the integration backend.
- Use Home Assistant Assist/TTS settings with safe defaults.
- Process text commands through HA Assist before sending the resulting DJConnect intent to Spotify.
- Use HA-native Assist/TTS routes in active services and entities.
- Track client status, firmware/client version, last command, last track and backend playback state.
- Track ESP-only battery, Wi-Fi RSSI, screen/LED state and firmware updates only for ESP32 clients.
- Provide diagnostics with sensitive values redacted.

## Architecture Decisions

DJConnect intentionally separates Home Assistant orchestration from firmware
runtime behavior. These decisions are part of the integration contract:

- **HA-native Assist/STT**: microphone audio is transcribed by this integration through Home Assistant's supported `stt.async_process_audio_stream` helper. DJConnect uses the configured Assist pipeline, falls back to Home Assistant's preferred/default pipeline, then the first pipeline with STT. The ESP uploads raw WAV audio to `POST /api/djconnect/voice` using its DJConnect device token; no Home Assistant websocket token is sent to the ESP.
- **No direct external AI/STT/TTS APIs**: active Home Assistant routes use HA Assist and HA TTS only. OpenAI or other direct external AI/STT/TTS clients are not part of the active voice path.
- **Device speaker for DJ announcements**: DJ announcements are not played through Spotify Connect or a Home Assistant media player. Home Assistant creates a temporary WAV or MP3 URL when possible and posts `text` plus optional `audio_url` to the ESP endpoint `/api/device/dj_response`.
- **HA owns backend playback**: the ESP does not store Spotify OAuth credentials and does not call the Spotify Web API directly. It sends generic playback commands to `POST /api/djconnect/command`; Home Assistant translates them to the current backend, currently Spotify.
- **Native playback proxy**: Home Assistant exposes a DJConnect `media_player` for the backend playback session. It does not mean music plays through the ESP speaker; the ESP speaker is reserved for local cues and DJ announcements.
- **Refresh-token rotation aware**: Spotify refresh tokens can rotate. Home Assistant stores the latest token and uses it as the canonical source for HA backend playback. Pair/status responses never include Spotify OAuth secrets.
- **Access-token cache**: Home Assistant caches short-lived Spotify access tokens and refreshes them on demand. A normal one-hour Spotify access-token expiry should not open a Repair flow; only a rejected/revoked refresh token should.
- **OAuth through Home Assistant external step**: Spotify OAuth uses PKCE and the Home Assistant external step flow. The callback remains `/api/djconnect/spotify/callback`, with Nabu Casa HTTPS URLs preferred.
- **Pairing over WiFi, BLE only for WiFi credentials**: BLE provisioning writes only WiFi SSID/password to setup-mode devices. Spotify credentials, device tokens and other secrets are never sent over BLE.
- **mDNS first, Client API URL as fallback**: ESP runtime prefers the device-reported `local_url`, exact `_djconnect._tcp` mDNS matches, then a single visible DJConnect mDNS device. During setup, Home Assistant also browses `_djconnect._tcp` for iOS/macOS/Raspberry Pi app-like clients, validates `client_type` against the stable device ID, probes `/api/device/pairing-info`, and can prefill the Client API URL, client type, device name and pairing code from authoritative pairing-info. Manual Client API URL entry remains available when discovery or pairing-info reachability fails.
- **Inline advanced options**: max audio bytes and OTA battery settings are revealed through a local “show advanced options” checkbox instead of Home Assistant's deprecated advanced-mode property. Firmware device selection is automatic through the public multi-device manifest; users can choose the OTA firmware channel, `stable` or `beta`, in options.
- **Single Home Assistant device**: sensors, buttons, settings, update and playback proxy entities share one stable device identifier so Home Assistant shows one DJConnect device instead of duplicate device entries.
- **Closed firmware, free integration**: firmware source remains proprietary. The Home Assistant integration is distributed separately under MIT for use with DJConnect devices.
- **No secrets in diagnostics/logs**: diagnostics redact keys containing `token`, `password` or `secret`; logs avoid full ESP payloads and do not intentionally log Spotify refresh tokens, WiFi passwords or device tokens.
- **Trademark clarity**: Spotify is a trademark of Spotify AB. DJConnect does not claim affiliation, endorsement or sponsorship by Spotify AB.

## Repository Layout

- Home Assistant integration: `3.1.22`
- ESP firmware source: `pcvantol/djconnect-app`
- Public firmware releases: `pcvantol/djconnect-firmware`
- Canonical cross-repo sync prompts: [`SYNC_PROMPTS.md`](SYNC_PROMPTS.md)

This repository contains the Home Assistant custom integration under `custom_components/djconnect`.

Brand images for the Home Assistant frontend are bundled in `custom_components/djconnect/brand/`.
The product/marketing website is maintained outside this integration repository.
Cross-repo sync prompts are consolidated into `SYNC_PROMPTS.md`; do not re-add old loose prompt files.

## Licensing And Commercial Use

Copyright (c) 2026 Peter van Tol. All rights reserved.

- The DJConnect Home Assistant integration is free software under the MIT License. You may use, copy, modify, publish, distribute, sublicense, and sell the integration under the terms in `LICENSE`.
- DJConnect firmware source code is not part of this repository and is not open source by default.
- DJConnect firmware is proprietary software. The Home Assistant integration may be distributed separately for use with DJConnect devices.
- DJConnect firmware binaries and OTA release assets are covered by `FIRMWARE-LICENSE.md` when they are distributed with DJConnect devices or through official firmware release channels.
- DJConnect hardware can be sourced, white-labeled, sold, and resold separately from this integration, subject to the firmware binary license and any hardware supplier agreements.
- The free Home Assistant integration may be bundled, linked, or recommended with commercial DJConnect devices without changing the closed-source status of the firmware.
- Spotify is a trademark of Spotify AB. DJConnect is not affiliated with, endorsed by, or sponsored by Spotify AB.
- This integration may depend on open-source Python/Home Assistant components. Their licenses remain with their respective authors. See `THIRD_PARTY_NOTICES.md`.

## Install Through HACS

Before installing, make sure you have:

- Home Assistant with HACS installed.
- A Spotify Premium account.
- A configured Home Assistant Assist pipeline with working STT and TTS.
- A DJConnect ESP device, DJConnect iOS/macOS app or Raspberry Pi client on the same local network as Home Assistant during pairing.
- For ESP devices: 2.4 GHz WiFi.
- For Spotify OAuth: an external HTTPS Home Assistant URL, preferably Nabu Casa.

1. Open HACS in Home Assistant.
2. Add `https://github.com/pcvantol/djconnect` as a custom repository.
3. Select category `Integration`.
4. Install DJConnect.
5. Restart Home Assistant.
6. Go to **Settings -> Devices & services -> Add integration -> DJConnect**.

HACS deeplink:

```text
https://my.home-assistant.io/redirect/hacs_repository/?owner=pcvantol&repository=djconnect&category=integration
```

## Spotify Developer App

DJConnect includes a default Spotify Client ID. PKCE is used, so no client secret is required. You only need your own Spotify Developer App Client ID if you want to override the bundled app in advanced setup.

Spotify Premium is required because DJConnect asks Home Assistant to control Spotify playback devices through Spotify's playback APIs. Spotify OAuth credentials remain in Home Assistant; DJConnect devices and apps never receive the Spotify refresh token or playback credentials.

DJConnect requests these Spotify OAuth scopes:

- `user-read-playback-state`
- `user-modify-playback-state`
- `user-read-currently-playing`
- `user-library-read`
- `playlist-read-private`
- `playlist-read-collaborative`
- `user-read-recently-played`
- `user-top-read`

`playlist-read-private` is required when Home Assistant lists private or
user-owned playlists for DJConnect backend playback. Existing users who
authorized Spotify before this scope was added must authorize Spotify again.

Add this redirect URI to the Spotify app:

```text
https://<your-nabu-casa-id>.ui.nabu.casa/api/djconnect/spotify/callback
```

For local-only development you can use a reachable Home Assistant URL instead:

```text
http://homeassistant.local:8123/api/djconnect/spotify/callback
```

The redirect URI in Spotify must exactly match the Home Assistant external URL plus `/api/djconnect/spotify/callback`.

## Add DJConnect In Home Assistant

1. Choose whether the DJConnect device is already on WiFi or needs BLE WiFi provisioning.
2. If needed, choose one BLE action: write WiFi over Bluetooth, rescan Bluetooth devices, or continue directly to pairing when WiFi was already configured through the device captive portal.
3. After BLE success or captive-portal WiFi setup, wait for the device to restart and show a pairing code.
4. Enter the pairing code shown on the DJConnect device display. This can be the short 6 digit setup code or the 12-character device suffix, for example `90B70990A994`.
5. Confirm the HTTPS Home Assistant external URL. DJConnect prefills this from Home Assistant's Network external URL when available and falls back to the Nabu Casa/Home Assistant Cloud remote UI URL.
6. Optionally override the bundled Spotify Client ID under advanced options.
7. Home Assistant opens the Spotify authorization website.
8. Approve access in Spotify.
9. Return to Home Assistant and complete the voice/DJ settings step.

The setup flow no longer shows a manual `oauth_result` field.

BLE WiFi provisioning only writes WiFi credentials to the setup-mode device. It
writes JSON with `ssid` and `password` keys only; `ssid` is required and
`password` may be empty for open networks. The JSON may be fragmented across
multiple BLE writes and does not send Spotify credentials, device tokens or
other secrets over BLE.

## Voice And DJ Settings

The config flow and options flow include safe defaults for optional voice fields. The Assist pipeline is stored so devices know which HA speech setup to use; DJConnect does not run STT internally.

- Assist pipeline ID
- TTS engine
- TTS language
- TTS voice, populated from the selected TTS entity when Home Assistant exposes voices. If the TTS engine changes and the stored voice is not supported by the new engine, DJConnect resets the voice to `Default`.
- DJ announcement prompt, a free-form instruction for the text spoken on the device
- ESP device UI language is selected automatically from the Home Assistant language during ESP pairing. iOS, macOS and Raspberry Pi clients determine their own language locally.
- Default playlist URI
- Spotify source override, optional visible Spotify device name or device ID
- Firmware updates through the public multi-device manifest
- OTA battery safety options

The default playlist can be private. If it is private, make sure Spotify has
been reauthorized with `playlist-read-private`; diagnostics and Home Assistant
repairs show a warning when the stored OAuth scope list is missing required
DJConnect scopes.

Where Home Assistant exposes choices, DJConnect shows populated dropdowns for Assist pipeline, TTS entity, known TTS voices, Spotify market and firmware channel. Stored custom values remain selectable so existing setups keep working. Backend playback is handled by Home Assistant through the DJConnect playback proxy; ESP device settings use the local device command API. The DJ announcement prompt, Spotify source override, firmware channel, client type and Client API URL are shown in the normal flow so the spoken device response, preferred Spotify Connect output, OTA track and app pairing URL can be adjusted directly. In options, the configured Client API URL is shown read-only; use re-pairing to change it. Max audio bytes and OTA battery settings are shown only after enabling the inline advanced-options checkbox. Firmware OTA device selection is automatic: DJConnect reads the public multi-device firmware manifest and selects the matching `firmwares[]` entry from ESP status/info, falling back to LilyGO only before the ESP has reported a model. For ESP devices, the Client API URL is normally not needed: DJConnect resolves the device through `_djconnect._tcp` mDNS, uses the device-reported `local_url` when available, and only builds a model-specific hostname such as `http://djconnect-lilygo-t-embed-s3-[device-suffix].local` when the configured ID contains a real 12-character device suffix.

The options flow also includes an action selector. Use `Reauthorize Spotify` to
refresh OAuth from the integration page, `Retry pairing with current code` to
push a fresh device token to the existing ESP, or `Re-pair with new pairing
code` when the ESP shows a new code.


## Security And Diagnostics

- Pairing is unauthenticated by design, but requires the pairing code or 12-character device suffix shown on the DJConnect device.
- After pairing, device endpoints use the per-device bearer token.
- Pairing/status metadata must include `client_type`; ESP firmware sends `esp32`, app clients send `ios` or `macos`, and the future Raspberry Pi client sends `raspberry_pi`. App/client device IDs use `djconnect-ios-XXXXXXXXXXXX`, `djconnect-macos-XXXXXXXXXXXX` or `djconnect-raspberry-pi-XXXXXXXXXXXX`, where the suffix is the first 12 alphanumeric characters of the stable install ID.
- Home Assistant keeps pairing status `pending` until the ESP confirms `ha_pairing_status=paired`; a local token alone is not treated as confirmed pairing.
- Home Assistant calls `POST /api/device/pair` only during initial pairing, explicit re-pair/token rotation, or stale-pairing recovery. Normal status, playback and settings updates never trigger a new direct pair callback.
- BLE WiFi provisioning sends only SSID/password to the BLE WiFi characteristic; it does not send Spotify credentials, device tokens or other secrets.
- Diagnostics redact keys containing `token`, `password` or `secret`.
- Logs avoid full event payloads and do not intentionally log Spotify refresh tokens, WiFi passwords or device tokens.
- The bundled Spotify Client ID is not a secret; PKCE is used and no client secret is required.

## Home Assistant Entities

DJConnect creates backend/playback entities for all client types:

- `sensor.djconnect_status`
- `sensor.djconnect_last_command`
- `sensor.djconnect_firmware_version`
- `sensor.djconnect_last_track`
- `sensor.djconnect_queue`
- `sensor.djconnect_playlists`
- `sensor.djconnect_outputs`
- `sensor.djconnect_sound_output`
- `sensor.djconnect_playback_available`
- `sensor.djconnect_spotify_status`
- `sensor.djconnect_ha_pairing_status`
- `select.djconnect_sound_output`
- `media_player.djconnect_playback_proxy`
- `button.djconnect_test_dj_voice`
- `button.djconnect_refresh_up_next`
- `button.djconnect_refresh_device_info`

ESP32 clients additionally get ESP-hardware entities:

- `sensor.djconnect_battery`
- `sensor.djconnect_wifi_rssi`
- `sensor.djconnect_screen_state`
- `sensor.djconnect_led_state`
- `number.djconnect_brightness`
- `number.djconnect_screen_timeout`
- `number.djconnect_speaker_volume`
- ESP device setting selects such as language, auto-off, theme and log level
- `update.djconnect_firmware`
- `button.djconnect_reboot_device`

iOS, macOS and Raspberry Pi clients do not get ESP-only battery, Wi-Fi RSSI,
screen/LED, screen brightness/timeout, speaker volume, device language,
auto-off, theme/log-level, OTA or reboot entities.

Entity IDs can differ if Home Assistant has renamed the device or entities.

Use `button.djconnect_test_dj_voice` after setup to test the configured HA TTS
engine, voice and language with a short DJ announcement on the DJConnect device
speaker/display. This does not use Spotify Connect or a Home Assistant media
player for DJ announcement audio.

Use `button.djconnect_refresh_up_next` to refresh the backend queue/up-next list
from Spotify/Home Assistant. Use `button.djconnect_refresh_device_info` for the
local ESP device info/status refresh. The sound-output select also refreshes
Spotify output devices when Home Assistant updates the entity, so available
outputs do not depend on a prior manual `devices` command.

## Services

DJConnect registers these services:

- `djconnect.test_parse`
- `djconnect.test_tts`
- `djconnect.test_command`
- `djconnect.start_spotify_oauth`

Spotify OAuth credentials stay in Home Assistant. They are never provisioned to the ESP device; the old ESP `/api/device/provision_spotify` endpoint is no longer used.

`djconnect.test_parse` and `djconnect.test_command` use this flow:

```text
text -> HA Assist conversation pipeline -> DJConnect intent -> Spotify -> ESP DJ announcement
```

`djconnect.test_command` accepts `command_text` and optional `play`. The legacy `text` key is still accepted for existing YAML/scripts. With `play: false`, it uses the same command parser path without starting Spotify playback.
`djconnect.test_parse` also accepts `command_text`; `djconnect.test_tts` accepts `dj_response_text` and keeps legacy `text` as a compatibility alias.

If command processing or Spotify playback fails, DJConnect still sends a
friendly DJ announcement to the ESP device when possible, so the user hears or sees
what went wrong instead of only receiving an HTTP error. This fallback text uses
the ESP32 language provisioned during pairing, or the client/default language
for app-like clients, and distinguishes Assist pipeline failures from Spotify
playback failures.
When HA Assist provides a DJ announcement, DJConnect asks it to include one
short fun fact about the artist and/or the song. After Spotify resolves and
starts the request, DJConnect prefers the resolved track, artist, album or
playlist metadata and the configured DJ announcement prompt to generate the spoken
device response, so the device response is specific to what actually started
playing.

If HA Assist returns a generic smart-home answer such as "I cannot play music",
DJConnect does not use that sentence as the DJ announcement. It keeps the
Spotify search intent based on the original command and falls back to the
DJConnect DJ announcement text unless Assist returns explicit `djconnect` data.
Plain voice/search commands such as "ik wil Pearl Jam starten" are resolved
through Spotify Search before playback starts. Text searches are intentionally
restricted to Spotify artists, so a spoken artist request starts the artist
context instead of picking an arbitrary track or album result. If Spotify
reports that no active playback device exists, DJConnect refreshes available
Spotify devices, selects the configured Spotify source when possible, transfers
playback there and retries the command once.

Developer action overview:

- `djconnect.test_parse`: test only the HA Assist conversation parser and return the DJConnect intent; no playback and no DJ announcement delivery.
- `djconnect.test_tts`: send a DJ announcement text to the DJConnect device; Home Assistant tries to generate a temporary WAV or MP3 URL, otherwise the ESP shows text only.
- `djconnect.test_command`: test the complete ESP text-command route with `command_text` and `play`; set `play: false` to avoid starting Spotify playback while still sending the DJ announcement.
- `djconnect.start_spotify_oauth`: generate a Spotify PKCE authorization URL for manual reauthorization/debugging.

Developer actions return response data where Home Assistant supports it. Enable
debug logging for `custom_components.djconnect` when you want to inspect the
selected TTS engine, OAuth redirect URI, DJ announcement result, or
command-processing result. Spotify refresh tokens and device tokens are not
logged.
For PTT/voice debugging, inspect the attributes on `sensor.djconnect_status` or
`sensor.djconnect_last_command`: `last_stt_text` shows the text recognized by
STT, `last_spotify_search` shows the Spotify Search query/type, selected result
and a small candidate list, and `last_resolved_media` shows the media metadata
used for the spoken DJ announcement.

Example developer action data:

```yaml
action: djconnect.test_command
data:
  command_text: "Play Pearl Jam"
  play: false
```

Example DJ announcement test:

```yaml
action: djconnect.test_tts
data:
  dj_response_text: "Here we go. DJConnect is paired, the voice works, and I am ready for your next track."
```

DJ announcement audio flow:

```text
dj_text -> HA TTS backend -> temporary WAV/MP3 URL -> POST /api/device/dj_response -> ESP speaker/display
```

DJ announcement failure handling:

| Failure | ESP/user feedback |
| --- | --- |
| HA Assist pipeline cannot process the command | Localized DJ announcement asks the user to check the selected Assist pipeline. |
| Spotify playback cannot start | Localized DJ announcement asks the user to check Spotify playback device availability. |
| HA TTS cannot generate WAV or MP3 | ESP receives text-only DJ announcement without `audio_url`. |
| HA TTS returns unknown audio | ESP receives text-only DJ announcement without `audio_url`; this is logged only as a debug fallback. |
| ESP `/api/device/dj_response` fails | Voice command returns a controlled `command_failed` JSON response and keeps the original Assist/Spotify error in runtime state. |
| Temporary audio URL is unknown or expired | `GET /api/djconnect/tts/{token}.wav` or `.mp3` returns `404` or `410`; trigger the DJ announcement again. |

Home Assistant posts this payload to the paired DJConnect device:

```json
{
  "text": "Here we go.",
  "audio_url": "http://homeassistant.local:8123/api/djconnect/tts/<token>.mp3"
}
```

`audio_url` is optional. If HA TTS cannot produce WAV or MP3 audio, DJConnect
sends only `text` and the ESP displays the response without speech. The ESP
decides whether the temporary URL is WAV, MP3 or unknown based on content type
and/or file header. DJConnect does not send Opus or M4A URLs.

During pairing, DJConnect sends only non-secret client settings, such as
`device_token`, `ha_local_url`, `assist_pipeline_id` and `client_type`.
For ESP32 clients only, Home Assistant also sends `device_language` and
`language`; iOS, macOS and Raspberry Pi clients always determine their own UI
language locally. `client_type` identifies the paired DJConnect client runtime;
current values are `esp32`, `ios`, `macos` and `raspberry_pi`, with `esp32` as
the default for ESP firmware. Device-to-Home Assistant traffic
always uses `ha_local_url`; cloud/Nabu Casa URLs are not sent to devices and
are only used by the Spotify OAuth config/repair flow. Spotify OAuth
credentials stay in Home Assistant and are used only by the HA playback backend.
Pair/status payloads must not contain `ha_url`, `refresh_token`,
`ha_remote_url`, `spotify_refresh_token`, `client_id` or a `spotify` OAuth object.
`ha_local_url` is resolved from Home Assistant's internal/network URL or LAN
source IP and must never be a `*.ui.nabu.casa` URL. When Home Assistant reports
`homeassistant.local` but a LAN source IP is available, DJConnect sends the LAN
IP URL instead. If no LAN URL can be discovered, `http://homeassistant.local:8123`
is the final local fallback.

Spotify refresh tokens can rotate after OAuth. DJConnect stores newly returned refresh tokens immediately and treats that latest stored value as canonical for HA backend playback. If the ESP later reports `spotify_configured=false`, Home Assistant treats this as a compatibility/status hint, not as a request to send OAuth credentials to the ESP.

Spotify access tokens are short-lived and normally expire after about an hour. DJConnect caches the access token in Home Assistant until shortly before expiry, refreshes it on demand, and retries once if Spotify returns an API `401` for an expired access token. A Home Assistant Repair issue should only appear when Spotify rejects the refresh token itself, for example `invalid_grant` or `Refresh token revoked`.

Provisioning fields sent to the ESP can include:

```json
{
  "device_token": "<per-device-token>",
  "ha_local_url": "http://192.168.1.x:8123",
  "assist_pipeline_id": "...",
  "client_type": "esp32",
  "device_language": "nl",
  "language": "nl",
  "backend_available": true
}
```

`ha_local_url` must be present. ESP32 firmware should prefer `device_language`
over `language` and store it as `provision.language`. App-like clients should
ignore HA language provisioning because their language is client-owned.

## Home Assistant HTTP Endpoints

The integration exposes these endpoints:

```text
POST /api/djconnect/pair
POST /api/djconnect/voice
POST /api/djconnect/command
POST /api/djconnect/status
POST /api/djconnect/event
GET  /api/djconnect/tts/{token}.wav
GET  /api/djconnect/spotify/callback
```

The ESP should send status updates to:

```text
POST /api/djconnect/status
```

Authenticated device requests use the provisioned bearer token and can include `X-DJConnect-Device-ID`.
Status and pairing payloads use canonical `client_type` metadata so Home
Assistant can distinguish ESP32 devices from iOS/macOS app clients and the future Raspberry Pi client.
ESP JSON payloads must include `client_type`.

BLE setup-mode devices are matched by service UUID:

```text
7f705000-9f8f-4f1a-9b5f-570071fd0001
```

WiFi credentials are written as UTF-8 JSON to characteristic
`7f705001-9f8f-4f1a-9b5f-570071fd0001`; status is read from
`7f705002-9f8f-4f1a-9b5f-570071fd0001`. The write payload is
`{"ssid":"MyWiFi","password":"wifi-password"}` and may be split over multiple
BLE writes for firmware-side reassembly.

The voice endpoint accepts raw WAV audio from the paired ESP device:

```text
POST /api/djconnect/voice
POST /api/djconnect/command
Authorization: Bearer <device_token>
Header: X-DJConnect-Device-ID: djconnect-lilygo-t-embed-s3-XXXXXXXXXXXX
Content-Type: audio/wav
```

The integration runs HA Assist/STT internally, processes the recognized text,
starts Spotify playback, creates a DJ announcement, and returns text plus an
optional temporary WAV/MP3 `audio_url`:

```json
{
  "success": true,
  "text": "Daar gaan we...",
  "dj_text": "Daar gaan we...",
  "audio_url": "http://homeassistant.local:8123/api/djconnect/tts/token.mp3",
  "audio_type": "mp3"
}
```

JSON/text-only requests remain supported for ESP web tests and diagnostics
through `X-DJConnect-Text` or `{ "text": "Test" }`. They simulate the DJ
response path directly and do not parse a Spotify playback command. Raw WAV PTT
uploads continue through STT, command parsing, Spotify playback and DJ announcement.

Home Assistant must have an STT provider configured. DJConnect first checks its
own `stt_engine` option, for example `stt.openai_stt` selected or entered in
the integration options. Home Assistant populates this as a dropdown when it can
list `stt.*` entities; otherwise DJConnect keeps it as a free-text field so the
entity id can still be entered manually. If `stt_engine` is empty, DJConnect resolves the selected
Assist pipeline's STT engine, or if no pipeline is stored, Home Assistant's
preferred/default Assist pipeline such as Home Assistant Cloud STT. If a stored
pipeline was removed, DJConnect falls back to the preferred/default pipeline.
If no pipeline STT provider can be resolved, it falls back to the first
available Home Assistant `stt.*` entity, for example `stt.openai_stt`. As a
then resolves direct STT providers through Home Assistant's supported
`stt.async_get_speech_to_text_engine` API and calls the provider audio stream
processor. As a final fallback it uses Home Assistant's official
`assist_pipeline.async_pipeline_from_audio_stream` helper from stage `stt` to
`stt`, which lets Home Assistant resolve the default pipeline internally. At
startup and for WAV uploads the integration logs the selected STT/TTS provider
metadata without tokens or API keys. If no STT provider is found,
`/api/djconnect/voice` returns `503` with the checked option keys.

## ESP -> HA Command Endpoint

Firmware sends backend playback commands to Home Assistant instead of storing Spotify credentials locally:

```text
POST /api/djconnect/command
```

Required headers are `Authorization: Bearer <device_token>`, `X-DJConnect-Device-ID` and `Content-Type: application/json`. Supported commands include `status`, `devices`, `queue`, `playlists`, `pause`, `play`, `next`, `previous`, `seek_relative`, `start_liked_proxy`, `start_playlist`, `play_context_at`, `set_shuffle`, `set_repeat`, `set_output` and `set_volume`. `seek_relative` accepts an integer millisecond offset for Apple app skip-forward/skip-back controls; positive values seek forward and negative values seek backward. `set_shuffle` accepts a boolean value; `set_repeat` accepts `off`, `track` or `context`; `play_context_at` accepts a context URI and track offset URI for Up Next playback. Responses are generic JSON shapes with `playback`, `devices`, `queue` or `playlists`, so future backends such as Sonos or Home Assistant media players can be added without firmware changes. `queue` responses include top-level `context_uri` / `contextUri` when known and per-item artwork aliases such as `album_image_url` and `image_url`; `playlists` responses include playlist artwork aliases such as `image_url`, `album_image_url` and `media_image_url`. Logs never include device tokens, Spotify tokens or backend credentials.

HA and ESP firmware must share the same `major.minor` protocol version. Patch
versions may differ, so HA `3.0.x` can talk to ESP `3.0.y`, but HA `3.1.x`
rejects ESP `3.0.y` and vice versa. When a mismatch is detected on
`/api/djconnect/status`, `/api/djconnect/command`, `/api/djconnect/voice` or
`/api/djconnect/event`, Home Assistant returns HTTP `426` with
`error: "version_mismatch"` and includes both major/minor values in the JSON
response.

## Native Home Assistant Entities

The integration exposes native Home Assistant entities for device status, DJ announcement tests and backend playback control. ESP32 clients additionally get firmware OTA, reboot and ESP hardware state such as battery, Wi-Fi RSSI and screen/LED status. iOS, macOS and Raspberry Pi clients only get client/runtime and backend/playback entities, so Home Assistant does not show irrelevant ESP hardware sensors for app-like clients. The `media_player.djconnect_playback_proxy` entity represents the current music backend session, not the ESP speaker. Music plays on the selected Spotify/output device; the DJConnect speaker/client is used for local cues and DJ/voice responses.
DJConnect persists the last known ESP status in the Home Assistant config entry,
so ESP battery, firmware, pairing status, screen/LED state and sound output
remain visible after a Home Assistant restart or integration reload while
waiting for the next authenticated ESP `/api/djconnect/status` post.

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

The integration uses the device `local_url` from pairing/status when provided. During setup it discovers visible `_djconnect._tcp` clients and can prefill pairing fields for iOS, macOS, Raspberry Pi and ESP devices. If the stored field is empty at runtime, it resolves the `_djconnect._tcp` mDNS service for the paired device. When the setup code is only 6 digits, DJConnect can also use the single visible DJConnect mDNS service on the network. Fallback hostnames are only generated for real 12-character device suffixes as model-specific hostnames, for example `djconnect-lilygo-t-embed-s3-90B70990A994.local`. `djconnect-[6-digit-code].local` and legacy `djconnect-90B70990A994.local` fallbacks are intentionally ignored.

When the ESP status payload reports `spotify_configured=false`, Home Assistant treats that as a compatibility/status hint. Spotify OAuth credentials stay in Home Assistant and are not returned in status responses.

## Firmware OTA Releases

Firmware builds come from the private `djconnect-app` repo and are published to the public `djconnect-firmware` repo.

Firmware source remains closed unless a separate written agreement says otherwise. Firmware binaries and OTA assets are distributed under the DJConnect Firmware Binary License in `FIRMWARE-LICENSE.md`.

Expected release assets:

```text
djconnect-lilygo-t-embed-s3-vX.Y.Z.bin
djconnect-esp32-s3-box-3-vX.Y.Z.bin
```

Expected manifest:

```text
firmware_manifest.json
```

Example manifest:

```json
{
  "version": "3.1.22",
  "version_tag": "v3.1.22",
  "channel": "stable",
  "min_ha_integration": "3.1.22",
  "firmwares": [
    {
      "board": "t_embed_cc1101",
      "device": "lilygo-t-embed-s3",
      "asset": "djconnect-lilygo-t-embed-s3-v3.1.22.bin",
      "url": "https://github.com/pcvantol/djconnect-firmware/releases/download/v3.1.22/djconnect-lilygo-t-embed-s3-v3.1.22.bin",
      "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      "size": 2113136
    },
    {
      "board": "esp32_s3_box3",
      "device": "esp32-s3-box-3",
      "asset": "djconnect-esp32-s3-box-3-v3.1.22.bin",
      "url": "https://github.com/pcvantol/djconnect-firmware/releases/download/v3.1.22/djconnect-esp32-s3-box-3-v3.1.22.bin",
      "sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
      "size": 2113136
    }
  ]
}
```

The firmware channel option controls which GitHub firmware release track is used:
`stable` reads GitHub's latest non-prerelease firmware release, while `beta`
reads the newest prerelease from `pcvantol/djconnect-firmware`.

The manifest-level `version` / `version_tag` is used for update comparison.
Home Assistant selects the matching `firmwares[]` entry for the configured ESP
device type and sends that entry's `device`, `asset`, `url` and `sha256` to
`POST /api/device/ota`. Top-level `device`, `asset`, `sha256` and `size`
fallbacks are intentionally not used.

The firmware version is injected through PlatformIO build flags from the Git tag.

Recommended firmware source release helper:

```bash
./release.sh 3.1.22
```

In the private `djconnect-app` repository, the firmware release script should
validate the semantic version, update firmware version metadata, run the
PlatformIO builds, rename firmware binaries to device-specific assets such as
`djconnect-lilygo-t-embed-s3-vX.Y.Z.bin`, calculate SHA256, update
`firmware_manifest.json`, commit, tag and push.

Preview the firmware release flow without changing files:

```bash
./release.sh 3.1.22 --dry-run
```

When publishing to the public firmware repository, use the firmware script's
public-repo option if available:

```bash
./release.sh 3.1.22 --publish-firmware-repo ../djconnect-firmware
```

The public `djconnect-firmware` repository should contain only the release
binary, `firmware_manifest.json`, release metadata and non-secret documentation.
Do not publish firmware source code, NVS secrets, device tokens, Spotify refresh
tokens or Home Assistant tokens.

## HACS Release Workflow

Use this checklist for every Home Assistant integration release.

Pre-release checklist:

- Confirm the working tree only contains intended changes.
- Update `custom_components/djconnect/manifest.json` to the target version.
- Update `custom_components/djconnect/const.py` to the same target version.
- Update `README.md` current version, examples, endpoints and HACS instructions.
- Update `CHANGELOG.md` as a single current-version changelog.
- Keep `AGENTS.md` aligned with the current version and release expectations.
- Verify `custom_components/djconnect/brand/` contains `icon.png`, `icon@2x.png` and `logo.png`.
- Verify `LICENSE` covers the Home Assistant integration and `FIRMWARE-LICENSE.md` covers firmware binaries.
- Run the lightweight tests:

```bash
python3 -m unittest discover -s tests
```

Tag and publish:

One-liner:

```bash
./release.sh 3.1.22
```

The script updates the integration version in `manifest.json`, `const.py`,
`README.md`, `CHANGELOG.md` and `AGENTS.md` before staging and committing.

Preview without executing git/gh commands:

```bash
./release.sh 3.1.22 --dry-run
```

Manual equivalent:

```bash
git add .
git commit -m "Release DJConnect v3.1.22"
git tag v3.1.22
git push origin main
git push origin v3.1.22
gh release create v3.1.22 --title "DJConnect v3.1.22" --notes-file CHANGELOG.md
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
2. Open DJConnect.
3. Choose **Redownload** or refresh HACS update information.
4. Select and install the new release from HACS.
5. Restart Home Assistant.
6. Go to **Settings -> Devices & services**.
7. Add DJConnect again, or remove and re-add the DJConnect integration if needed.
8. Complete pairing and Spotify OAuth in the DJConnect config flow.
9. Open DJConnect options and verify there is no internal server error.
10. Verify the integration icon/logo appears after browser/app cache refresh.
11. Run `djconnect.test_parse`, `djconnect.test_command` and `djconnect.test_tts`.
12. Verify device status, last command, last track and firmware update entities.

Firmware release cross-check, when publishing firmware as well:

- Build firmware from the private `djconnect-app` repository.
- Prefer the private firmware repo one-liner: `./release.sh X.Y.Z`.
- Use `./release.sh X.Y.Z --dry-run` before publishing when in doubt.
- Publish binaries to the public `djconnect-firmware` repository.
- Publish device-specific release assets such as `djconnect-lilygo-t-embed-s3-vX.Y.Z.bin` and `djconnect-esp32-s3-box-3-vX.Y.Z.bin`.
- Update `firmware_manifest.json` with manifest-level `version`, `version_tag`, `channel`, `min_ha_integration` and a `firmwares[]` entry per supported device.
- Confirm each `firmwares[]` entry includes `device`, `asset`, `url`, `sha256` and `size`.
- Confirm OTA discovers the new firmware through the Home Assistant update entity.

## Tests

Run the lightweight unit tests with:

```bash
python3 -m unittest discover -s tests
```

These tests use local stubs for Home Assistant imports and focus on pure DJConnect helpers, OAuth URL building, Assist response mapping, app/Raspberry Pi mDNS discovery, config-flow prefill/selection behavior and translation coverage.

## Troubleshooting

- If Spotify login does not return to Home Assistant, verify the Spotify redirect URI exactly matches the Nabu Casa or external Home Assistant URL.
- If the config flow does not load, restart Home Assistant and check that HACS installed `custom_components/djconnect`.
- If Home Assistant discovery still shows an old `spotify_dj` / `SpotifyDJ` card next to DJConnect, remove the old custom integration from Home Assistant: delete `/config/custom_components/spotify_dj`, remove any old HACS custom repository for SpotifyDJ, clear ignored/discovered SpotifyDJ entries from Settings -> Devices & services where needed, and restart Home Assistant. DJConnect itself only ships the `djconnect` integration domain; the old card means Home Assistant is still loading stale SpotifyDJ integration files or stale firmware/discovery from an ESP that has not been renamed yet.
- If the integration icon stays white or generic, update/re-download the HACS integration, restart Home Assistant, and refresh the browser/app cache. Home Assistant 2026.3+ reads custom integration brand images from `custom_components/djconnect/brand/`.
- If opening DJConnect options returns an internal server error, update to this release or newer; older builds assigned HA's read-only `config_entry` property.
- If OTA cannot start, make sure the device has reported `local_url` or can be reached as `http://[device_id].local`.
- If OTA is blocked, check battery level, USB power, and the OTA battery options.
- If the firmware update entity reports a GitHub rate limit, wait for GitHub's API limit to reset; DJConnect keeps the entity loaded and records the temporary error in its attributes. The firmware update entity is non-polling and checks GitHub on add/manual refresh/install plus an internal one-hour schedule, not every few seconds.
- If Spotify playback fails, reauthorize Spotify in Home Assistant and check that the selected backend has an active playback target.
- If Spotify fails only after about an hour of idle time, update to this release or newer; normal access-token expiry is handled by HA with a cached token and one refresh retry.
- If Spotify returns `invalid_grant` or `Refresh token revoked`, Spotify revoked the stored OAuth token. Open Home Assistant Repairs and choose `Fix` for the DJConnect authorization issue to run Spotify OAuth again.
- If an options-flow Spotify OAuth callback reports an empty failure after Spotify approved access, update to this release or newer; the callback now keeps the stored token even when the options dialog was already closed.
- If the ESP logs `HA playback HTTP 503` immediately after pairing, update to this release or newer; playback backend failures are now returned as JSON without invalidating HA pairing.
- If provisioning says `local_url is unknown`, make sure the device advertises `_djconnect._tcp` mDNS or enter the Client API URL, for example `http://djconnect-lilygo-t-embed-s3-90B70990A994.local`.
- If Home Assistant sees a Raspberry Pi/iOS/macOS client through mDNS but pairing shows a pairing-info reachability error, verify that the Client API URL shown in the pairing form opens `/api/device/pairing-info` from the Home Assistant network. Correct the Client API URL manually if Bonjour advertised a hostname or port that Home Assistant cannot reach.
- If Home Assistant added the integration but the ESP still shows a pairing code, check `sensor.djconnect_ha_pairingstatus`: `pending` means HA has a local token but the ESP has not confirmed `/api/device/pair` yet. Verify the device URL/mDNS reachability and wait for the next pairing retry or re-pair from the config flow.
- If the ESP briefly shows Home Assistant paired and then returns to a pairing code after the first command, update to this release or newer; DJConnect now accepts the real model-specific device ID after setup-code based direct pairing and logs token/device mismatch reasons without exposing token values.
- If the ESP logs `HA status response: 401` while HA can still reboot the device, update to this release or newer and re-pair if needed. Status/command/voice auth now accepts `djconnect-lilygo-t-embed-s3-XXXXXXXXXXXX` and `djconnect-esp32-s3-box-3-XXXXXXXXXXXX` with the stored token, learns the current id, and keeps `ha_pairing_status` stable.
- If ESP logs show repeated `Home Assistant direct pairing stored` during normal next/previous/volume/status commands, update to this release or newer; startup and playback paths no longer call `/api/device/pair` when HA already has a stored device token.
- If the pairing token is stale, open DJConnect options and choose `Retry pairing with current code`. If the device shows a new code, choose `Re-pair with new pairing code`.
- If brightness, speaker volume or timeout entities stay at defaults, make sure the ESP firmware sends these settings in its periodic Home Assistant status payload; DJConnect accepts common aliases such as `brightness`, `cue_volume`, `screen_dim_timeout` and `turn_off_after_ms`.
- If `/api/djconnect/voice` returns `No STT provider configured`, select an STT engine in DJConnect options, configure an Assist pipeline with STT such as Home Assistant Cloud STT, or clear the stale DJConnect pipeline option so the integration can use Home Assistant's preferred/default Assist pipeline.
- If `/api/djconnect/voice` returns `HA Assist STT did not return recognized text`, enable debug logging for `custom_components.djconnect`, trigger one ESP voice request, then open `/api/djconnect/debug/last_voice.wav` while logged in to Home Assistant. DJConnect only keeps this last raw ESP WAV in memory while debug logging is enabled; use it to check for clear speech, clipped audio, silence, wrong sample rate or noise.
- If WiFi/pairing works but Spotify does not, reauthorize Spotify in Home Assistant; pair/status payloads must not contain Spotify OAuth secrets.
- If Home Assistant cannot find a private `DJConnect Liked Proxy` playlist, reauthorize Spotify so the refresh token includes `playlist-read-private`.
- If a PTT command cannot start Spotify playback, the ESP should receive a friendly DJ announcement; check that Spotify is authorized in Home Assistant and that the backend has a reachable playback target.
- If `/api/djconnect/voice` returns `missing_text`, send raw WAV audio for PTT or a developer test text through `X-DJConnect-Text`.
- If `spoken=false`, HA did not provide a compatible WAV/MP3 URL or the ESP could not play it; the text response should still be displayed.
- If HA TTS returns MP3, DJConnect can send the MP3 `audio_url` to ESP firmware that supports MP3 DJ announcement playback.
- If Home Assistant reports `Invalid value for number.djconnect_volume: -1.0`, update to this release or newer; DJConnect treats unknown device volume as unavailable instead of publishing an out-of-range value.
- If the ESP reports `401` for `/api/device/dj_response`, pair the device again so the device token is refreshed.
- If `/api/djconnect/tts/{token}.wav` or `.mp3` returns `404` or `410`, the token is unknown or expired; trigger the DJ announcement again.
- If the ESP cannot download the temporary audio URL, make sure the Home Assistant internal URL is reachable from the DJConnect device network.
- Diagnostics are available from the Home Assistant integration page and redact token/password/secret fields.
