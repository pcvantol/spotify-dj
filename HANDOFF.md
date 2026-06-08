# SpotifyDJ Home Assistant Integration Handoff

## Current State

- Repository: `pcvantol/spotify-dj`.
- Integration domain: `spotify_dj`.
- Current released integration version: `2.9.30`.
- Next expected release after current pending fixes: `2.9.32`.
- Home Assistant integration is HACS-distributed and MIT-licensed.
- ESP firmware source remains proprietary in `pcvantol/spotify-dj-app`.
- Public firmware release assets live in `pcvantol/spotify-dj-firmware`.
- Firmware v2.9.25+ uses the local ESP API with bearer-token auth and generic playback commands.
- ESP no longer stores Spotify OAuth/client_id/refresh_token or other playback-backend credentials.
- HA integration is the trusted backend for pairing, Spotify OAuth/backend playback, Assist/STT/TTS, OTA and native entities.
- Lightweight tests live in `tests/` and currently pass with `python3 -m unittest discover -s tests`.

## Architecture

```text
SpotifyDJ ESP device
  -> HA /api/spotify_dj/status, /command, /voice
  -> spotify_dj integration
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

- `POST /api/spotify_dj/pair`
- `POST /api/spotify_dj/status`
- `POST /api/spotify_dj/command`
- `POST /api/spotify_dj/voice`
- `POST /api/spotify_dj/event`

All protected ESP -> HA routes use:

- `Authorization: Bearer <device_token>`
- `X-SpotifyDJ-Device-ID: spotifydj-lilygo-XXXXXXXXXXXX`

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

Do not use `/api/device/provision_spotify`; it is removed/legacy and should not be called.

## Decisions Made

- Legacy external message-bus control is removed and must not be reintroduced.
- ESP is not a Spotify Connect speaker/player.
- HA `media_player.spotifydj_playback_proxy` represents backend playback, not ESP speaker audio.
- ESP speaker is only for local cues and DJ/voice response audio.
- ESP stores no Spotify/Sonos/backend credentials.
- Pairing/status responses must never include `spotify_client_id`, `client_id`, `spotify_refresh_token`, `refresh_token` or nested Spotify OAuth secrets.
- Spotify OAuth credentials stay HA-internal.
- Spotify `invalid_grant` / revoked refresh tokens produce a user-friendly reauthorize/Repair flow.
- Repair flow must open Spotify OAuth and may only close as fixed after a new/missing refresh token is stored, not merely because an old token exists.
- Options flow also has a “Spotify opnieuw autoriseren” action using the same callback storage path.
- Token sent by HA to ESP in `POST /api/device/pair` must be exactly the token accepted by HA `/status`, `/command` and `/voice`.
- Setup-code pairing can start with a temporary six-digit identity, but HA must learn and persist the real `spotifydj-lilygo-XXXXXXXXXXXX` ID from the first authenticated ESP call. Older `spotifydj-XXXXXXXXXXXX` IDs remain accepted for compatibility.
- ESP status payloads can report device settings as top-level fields or nested `settings`, `screen` and `led` objects; HA flattens those aliases for native entities.
- HA pairing status is `pending` until ESP confirms `ha_pairing_status=paired`; a locally stored token alone is not enough.
- `POST /api/spotify_dj/command` should return JSON and avoid 503 loops for Spotify auth failures; report backend unavailable without causing ESP to clear pairing.
- Physical PTT uses raw WAV upload to HA; ESP must not authenticate directly to HA Assist WebSocket.
- HA STT provider selection uses `stt_engine` first, then Assist pipeline/default/fallbacks.
- Text-only `/api/spotify_dj/voice` is a DJ response test and must not trigger Spotify playback parsing.
- Raw WAV `/api/spotify_dj/voice` is the real STT + command + playback path.
- DJ response TTS is returned to ESP as text and optional temporary WAV/MP3 `audio_url`.
- Device setting entities accept firmware aliases such as `brightness`, `screen_brightness`, `cue_volume`, `speaker_volume`, `screen_dim_timeout_ms` and `turn_off_after_ms`.
- `number.spotifydj_volume` and other numbers must publish `None/unavailable`, not invalid values outside HA ranges.
- Firmware asset name is distributive, e.g. `spotifydj-device-vX.Y.Z.bin`; OTA target device comes from `firmware_manifest.json` field `device`, currently `lilygo-t-embed-s3`.
- Secrets must not appear in logs, diagnostics or state attributes.
- Spotify trademark/non-affiliation notice remains in docs/UI/diagnostics.

## Current Pending HA Fixes

- Spotify OAuth callback now stores tokens even if an options flow is already closed and `UnknownFlow` occurs.
- Spotify OAuth Repair flow now starts an external Spotify OAuth step and does not mark the issue fixed until a new token is stored.
- Pairing/provisioning logs now include exception class/repr for empty-message failures.
- Status response includes cached playback where available.
- Backend playback auth failures are returned as user-friendly JSON without forcing ESP pairing reset.
- Device number entities accept common firmware status aliases and unit conversions.

## Known Issues / Field Checks

- Validate the Repair “Fix” button in a real HA UI: it should open Spotify OAuth instead of instantly closing.
- Validate options-flow “Spotify opnieuw autoriseren” in a real HA UI.
- Confirm Nabu Casa/external URL is correctly detected or manually editable before OAuth.
- Confirm ESP remains paired after first `/api/spotify_dj/command` following direct pairing.
- Confirm ESP does not clear pairing when Spotify backend is temporarily unavailable.
- Confirm ESP status payload includes top-level or nested device settings so HA brightness/theme/log-level/speaker-volume entities do not remain unknown/minimum.
- Confirm physical PTT with selected HA STT provider returns recognized text.
- Confirm HA TTS returns WAV/MP3 or falls back to text-only without crashing.
- Confirm OTA clears updating state after post-boot status.

## Next Tasks

1. Release the pending HA fixes as `2.9.30` when release execution is available.
2. Install via HACS and restart Home Assistant.
3. Test Repair flow for revoked Spotify token.
4. Test options-flow Spotify reauthorize action.
5. Pair a device from scratch and verify token synchronization.
6. Verify ESP `/status` includes current settings aliases consumed by HA.
7. Run physical PTT end-to-end.
8. Verify native playback proxy media player controls Spotify backend playback.
9. Verify no Spotify OAuth secrets are sent to ESP or logged.
10. Cleanup old releases after successful publication with `./cleanup_old_releases.sh --keep 1 --execute`.

## Validation Commands

```sh
python3 -m json.tool custom_components/spotify_dj/strings.json >/tmp/spotifydj_strings.json
python3 -m json.tool custom_components/spotify_dj/translations/en.json >/tmp/spotifydj_en.json
python3 -m json.tool custom_components/spotify_dj/translations/nl.json >/tmp/spotifydj_nl.json
python3 -m py_compile custom_components/spotify_dj/*.py tests/*.py
python3 -m unittest discover -s tests
```
