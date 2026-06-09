# DJConnect Home Assistant Integration Handoff

## Current State

- Repository: `pcvantol/djconnect`.
- Integration domain: `djconnect`.
- Current integration release: `3.0.21`.
- Release status: DJConnect `3.0.21` is the current release target.
- Home Assistant integration is HACS-distributed and MIT-licensed.
- ESP firmware source remains proprietary in `pcvantol/djconnect-app`.
- Public firmware release assets live in `pcvantol/djconnect-firmware`.
- Current firmware uses the local ESP API with bearer-token auth and generic playback commands.
- ESP no longer stores Spotify OAuth/client_id/refresh_token or other playback-backend credentials.
- HA integration is the trusted backend for pairing, Spotify OAuth/backend playback, Assist/STT/TTS, OTA and native entities.
- HA integration and ESP firmware must share the same `major.minor` protocol version; patch versions may differ.
- Lightweight tests live in `tests/` and currently pass with `python3 -m unittest discover -s tests`.

## Architecture

```text
DJConnect ESP device
  -> HA /api/djconnect/status, /command, /voice
  -> djconnect integration
  -> HA Assist/STT/TTS + Spotify backend playback
  -> optional /api/device/command or /api/device/dj_response back to ESP
```

### Home Assistant Responsibilities

- Config flow and options flow.
- Optional BLE WiFi provisioning before pairing.
- Device pairing and device-token lifecycle.
- Spotify OAuth PKCE through HA external step.
- Spotify refresh-token rotation and revoked-token repair.
- Backend playback proxy and native HA `media_player`.
- Device settings/entities through ESP `/api/device/command`.
- Raw WAV PTT processing via HA STT/Assist.
- DJ response TTS and temporary WAV/MP3 audio URLs.
- Firmware release discovery and OTA orchestration.
- Diagnostics, repairs and user-facing errors.

### ESP Responsibilities

- Device runtime, display, buttons, LED ring and local audio cues.
- Captive portal / BLE WiFi setup.
- Pairing-code display and local bearer-token storage.
- Status reports to HA.
- Generic playback commands to HA.
- Raw WAV upload to HA for PTT.
- Playback of HA-provided DJ response text/audio locally.
- OTA execution through `POST /api/device/ota`.

## Endpoint Contract

### ESP -> HA

- `POST /api/djconnect/pair`
- `POST /api/djconnect/status`
- `POST /api/djconnect/command`
- `POST /api/djconnect/voice`
- `POST /api/djconnect/event`

All protected ESP -> HA routes use:

- `Authorization: Bearer <device_token>`
- `X-DJConnect-Device-ID: djconnect-lilygo-XXXXXXXXXXXX`

Version contract:

- HA `3.0.z` accepts ESP `3.0.z`; HA `3.1.z` accepts ESP `3.1.z`.
- A different ESP `major.minor` returns HTTP `426` with `error: version_mismatch`.
- `version_mismatch` is a protocol/update requirement, not a stale pairing-token state; do not clear pairing because of it.

### HA -> ESP

- `GET /api/device/info`
- `GET /api/device/pairing-info`
- `POST /api/device/pair`
- `POST /api/device/command`
- `POST /api/device/ota`
- `POST /api/device/reboot`
- `POST /api/device/forget`
- `POST /api/device/dj_response`

All protected HA -> ESP routes use:

- `Authorization: Bearer <device_token>`

Do not use `/api/device/provision_spotify`; it is removed and should not be called.

## Decisions Made

- The previous external message-bus control route is removed and must not be reintroduced.
- ESP is not a Spotify Connect speaker/player.
- HA `media_player.djconnect_playback_proxy` represents backend playback, not ESP speaker audio.
- ESP speaker is only for local cues and DJ/voice response audio.
- ESP stores no Spotify/Sonos/backend credentials.
- Pairing/status responses must never include `spotify_client_id`, `client_id`, `spotify_refresh_token`, `refresh_token` or nested Spotify OAuth secrets.
- Spotify OAuth credentials stay HA-internal.
- Spotify access tokens are cached in Home Assistant until shortly before expiry. Normal access-token expiry must refresh on demand and retry once after Spotify API `401`; only refresh-token rejection should create a Repair issue.
- Spotify `invalid_grant` / revoked refresh tokens produce a user-friendly reauthorize/Repair flow.
- Repair flow must open Spotify OAuth and may only close as fixed after a new/missing refresh token is stored, not merely because an old token exists.
- Options flow also has a “Spotify opnieuw autoriseren” action using the same callback storage path.
- Token sent by HA to ESP in `POST /api/device/pair` must be exactly the token accepted by HA `/status`, `/command` and `/voice`.
- HA -> ESP pairing payload uses `ha_local_url` and `ha_remote_url`; legacy `ha_url` must not be sent or expected.
- At least one of `ha_local_url` or `ha_remote_url` must be present. ESP should try `ha_local_url` first and use `ha_remote_url` as cloud fallback.
- `ha_local_url` must never be a `*.ui.nabu.casa` cloud URL; resolve HA Network/internal/source-IP local URL first, then use `http://homeassistant.local:8123` as final local fallback and send cloud only as `ha_remote_url`.
- HA may call `POST /api/device/pair` only for initial pairing, explicit re-pair/token rotation or stale-pairing recovery. Startup with a stored token, normal status sync, playback commands and settings sync must not call it.
- Setup-code pairing can start with a temporary six-digit identity, but HA must learn and persist only the real `djconnect-lilygo-XXXXXXXXXXXX` ID from the first authenticated ESP call. Legacy `djconnect-XXXXXXXXXXXX` IDs are not accepted.
- HA and ESP firmware compatibility is strict on `major.minor`: patch versions may differ, but `3.0.z` must not talk to `3.1.z`. HA returns HTTP `426` `version_mismatch` with HA/firmware metadata and keeps pairing intact.
- ESP status payloads can report device settings as top-level fields or nested `settings`, `screen` and `led` objects; HA flattens those aliases for native entities.
- HA pairing status is `pending` until ESP confirms `ha_pairing_status=paired`; a locally stored token alone is not enough.
- `POST /api/djconnect/command` should return JSON and avoid 503 loops for Spotify auth failures; report backend unavailable without causing ESP to clear pairing.
- Physical PTT uses raw WAV upload to HA; ESP must not authenticate directly to HA Assist WebSocket.
- HA STT provider selection uses `stt_engine` first, then Assist pipeline/default/fallbacks.
- DJConnect prompts HA Assist to include one short fun fact about the artist and/or song when it creates a DJ announcement.
- Options flow clears a stale provider-specific `tts_voice` when the selected TTS engine changes and no longer supports that voice.
- Text-only `/api/djconnect/voice` is a DJ response test and must not trigger Spotify playback parsing.
- Raw WAV `/api/djconnect/voice` is the real STT + command + playback path.
- DJ response TTS is returned to ESP as text and optional temporary WAV/MP3 `audio_url`.
- Device setting entities accept firmware aliases such as `brightness`, `screen_brightness`, `cue_volume`, `speaker_volume`, `screen_dim_timeout_ms` and `turn_off_after_ms`.
- `number.djconnect_volume` and other numbers must publish `None/unavailable`, not invalid values outside HA ranges.
- Firmware asset name is distributive, e.g. `djconnect-device-vX.Y.Z.bin`; OTA target device comes from `firmware_manifest.json` field `device`, currently `lilygo-t-embed-s3`.
- Secrets must not appear in logs, diagnostics or state attributes.
- Spotify trademark/non-affiliation notice remains in docs/UI/diagnostics.

## Current Release Notes

- Current release line is `3.0.x`; only the latest GitHub release/tag should be kept after release cleanup.
- Voice/Assist search text such as "ik wil Pearl Jam starten" must be resolved through Spotify Search before `/me/player/play`; do not send arbitrary text as `context_uri`.
- Device DJ responses after successful PTT playback should be generated from resolved Spotify/playback metadata and the configured `dj_style`, not from the generic Assist fallback announcement.
- If Spotify playback fails because there is no active device, refresh `/me/player/devices`, prefer configured `spotify_source` by id or visible name, transfer playback and retry once.
- `spotify_source` is a normal options-flow field again because it is needed for reliable voice playback routing; firmware/OTA overrides remain hidden behind the local advanced checkbox.
- `3.0.21` prevents Nabu Casa/cloud URLs from being sent as `ha_local_url` during pairing and falls back to HA network/source-IP local URL discovery, then `http://homeassistant.local:8123`.
- `3.0.20` keeps the options-flow “re-pair with new pairing code” field empty instead of pre-filling the old stored pairing code.
- `3.0.19` sets the Spotify repair OAuth popup title and description directly on the Repairs external-step result, so Home Assistant no longer shows a blank dialog when translation lookup misses a dynamic repair issue id.
- `3.0.18` adds explicit Spotify repair-flow popup text for the initial external-website repair step, so the repair dialog does not open blank.
- Strict current ESP device identity is `djconnect-lilygo-XXXXXXXXXXXX`; legacy `djconnect-XXXXXXXXXXXX` IDs are not accepted.
- HA blocks ESP calls with HTTP `426` `version_mismatch` when HA and ESP firmware `major.minor` differ, while preserving pairing/token state.
- ESP status payloads are merged as partial updates, so sparse heartbeat/status posts do not clear known HA sensor values.
- `/api/djconnect/status` is the only authoritative ESP device-status source. Command, voice, backend playback and local ESP info/command refreshes must never replace the full cached sensor snapshot with empty/unknown values.
- Local ESP `/api/device/command` responses and `/api/device/info` refreshes are merge-only and preserve cached firmware, battery, RSSI, screen/LED, sound output, volume, last track and `ha_pairing_status` when fields are missing or empty.
- Empty Spotify playback snapshots may update backend/playback state, but must not clear cached device sensor fields such as `sound_output`, `volume`, `last_track` or pairing status.
- Command and voice payloads are never authoritative device-status sources; they must not clear sensor values or move `ha_pairing_status` back to `pending` when fields are absent.
- ESP status must include `client_type=esp32`; missing client type is surfaced as a visible HA status error.
- Native HA entities include backend playback proxy, queue/up-next, output list, output select, firmware OTA, device settings and test/refresh buttons under one HA device.
- `button.djconnect_refresh_up_next` refreshes Spotify/Home Assistant backend queue data through the `queue` command.
- `command=queue` returns top-level `context_uri` / `contextUri` and queue item artwork aliases so ESP/web Up Next can use `play_context_at` and show thumbnails.
- `select.djconnect_sound_output` refreshes Spotify output devices itself and accepts `available_outputs`, `outputs`, `devices` and nested `items` aliases.
- Playback proxy exposes album art through `album_image_url`, `media_image_url`, `image_url` and `entity_picture` aliases.
- Voice debug is opt-in via debug logging: when `custom_components.djconnect` debug logging is enabled, HA stores the last raw ESP WAV in memory and exposes it at authenticated URL `/api/djconnect/debug/last_voice.wav`.
- Developer Actions use explicit UI field names `command_text` and `dj_response_text`; legacy `text` remains accepted for existing YAML/scripts.
- If HA Assist treats the DJConnect parsing prompt as a smart-home device command, DJConnect falls back to a simple Spotify search intent instead of raising a websocket script exception.
- ESP sync prompt now requires menu-open LED ring off/volume-clear behavior and a blue LED ring/accent for Asteroids.
- Spotify OAuth callback stores tokens even if an options flow is already closed and `UnknownFlow` occurs.
- Spotify OAuth Repair flow starts an external Spotify OAuth step and does not mark the issue fixed until a new token is stored.
- Backend playback auth failures are returned as user-friendly JSON without forcing ESP pairing reset.
- Device number/select entities accept common firmware status aliases and unit conversions.

## Known Issues / Field Checks

- Validate the Repair “Fix” button in a real HA UI: it should open Spotify OAuth instead of instantly closing.
- Validate options-flow “Spotify opnieuw autoriseren” in a real HA UI.
- Confirm Nabu Casa/external URL is correctly detected or manually editable before OAuth.
- Confirm ESP remains paired after first `/api/djconnect/command` following direct pairing.
- Confirm ESP does not clear pairing when Spotify backend is temporarily unavailable.
- Confirm ESP shows update-required state and keeps pairing intact after HA returns `426 version_mismatch`.
- Confirm ESP status payload includes top-level or nested device settings so HA brightness/theme/log-level/speaker-volume entities do not remain unknown/minimum.
- Confirm physical PTT with selected HA STT provider returns recognized text.
- Confirm HA TTS returns WAV/MP3 or falls back to text-only without crashing.
- Confirm OTA clears updating state after post-boot status.

## Next Tasks

1. Install the latest `3.0.x` release via HACS and restart Home Assistant.
2. Verify the README/HACS banner and product website hero render as intended.
3. Verify `button.djconnect_refresh_up_next` updates `sensor.djconnect_queue` attributes.
4. Verify `select.djconnect_sound_output` populates Spotify outputs without manually calling `devices`.
5. Verify sensors keep last-known values after ESP status, playback command polling, voice tests and local device-info refreshes.
6. Test Repair flow for revoked Spotify token.
7. Test options-flow Spotify reauthorize action.
8. Pair a device from scratch and verify token synchronization with `ha_local_url` / `ha_remote_url`.
9. Verify ESP `/status` includes current settings aliases consumed by HA.
10. Run physical PTT end-to-end.
11. Verify native playback proxy media player controls Spotify backend playback and shows album art.
12. Verify no Spotify OAuth secrets are sent to ESP or logged.

## Validation Commands

```sh
python3 -m json.tool custom_components/djconnect/strings.json >/tmp/djconnect_strings.json
python3 -m json.tool custom_components/djconnect/translations/en.json >/tmp/djconnect_en.json
python3 -m json.tool custom_components/djconnect/translations/nl.json >/tmp/djconnect_nl.json
python3 -m py_compile custom_components/djconnect/*.py tests/*.py
python3 -m unittest discover -s tests
```
