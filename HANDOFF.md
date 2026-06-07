# SpotifyDJ Handoff

## Current State

- Repository: `pcvantol/spotify-dj` Home Assistant custom integration.
- Integration domain: `spotify_dj`.
- Current released integration version: `2.9.14`.
- Latest release commit: `f54bfd5 Release SpotifyDJ v2.9.14`.
- Lightweight unit test suite is available under `tests/` and was last run successfully with `python3 -m unittest discover -s tests` before the `2.9.14` release.
- A static product/marketing onepager exists at `website/index.html`.
- The integration is intended for HACS distribution and local Home Assistant installation.
- ESP firmware source remains proprietary in `pcvantol/spotify-dj-app`; public firmware binaries/manifests are released from `pcvantol/spotify-dj-firmware`.
- The Home Assistant integration is MIT-licensed; firmware binaries/source are covered separately and remain proprietary unless explicitly changed.
- Firmware v2.9.12 and newer uses the local ESP API with the stored bearer token for device control.

## Architecture

### High-level Flow

```text
ESP SpotifyDJ device
  -> Home Assistant spotify_dj integration
  -> HA Assist/STT/TTS + Spotify OAuth/provisioning/orchestration
  -> ESP device runtime/audio/UI + Spotify API playback
```

### Responsibilities

- Home Assistant integration:
  - Config flow/options flow.
  - BLE WiFi provisioning.
  - Device pairing and device-token management.
  - Spotify OAuth PKCE via Home Assistant external step.
  - Spotify refresh-token rotation storage for HA backend playback.
  - OTA firmware discovery/update orchestration.
  - ESP status/event endpoints.
  - Raw WAV voice endpoint and HA-native STT/TTS orchestration.
  - Temporary WAV/MP3 TTS audio hosting for DJ responses.
  - Developer services/actions for parse, command, TTS and Spotify credential provisioning.
- ESP firmware:
  - Device runtime, UI and audio playback.
  - Microphone capture and raw WAV upload to HA.
  - Spotify API playback using provisioned OAuth credentials.
  - Status reporting to HA.
  - OTA endpoint execution.
  - DJ response display/audio playback from HA-provided text/audio URL.

### Important Endpoints

- `POST /api/spotify_dj/pair`
- `POST /api/spotify_dj/status`
- `POST /api/spotify_dj/event`
- `POST /api/spotify_dj/voice`
- `GET /api/spotify_dj/tts/{token}.{extension}`
- `GET /api/spotify_dj/spotify/callback`
- ESP endpoint used by HA: `POST /api/device/pair`
- ESP endpoint used by HA: `POST /api/device/ota`
- ESP endpoint used by HA: `POST /api/device/dj_response`
- ESP endpoint used by HA for device settings: `POST /api/device/command`
- HA endpoint used by ESP for backend playback: `POST /api/spotify_dj/command`
- ESP endpoint used by HA: `GET /api/device/info`
- ESP endpoint used by HA: `GET /api/device/pairing-info`
- ESP endpoint used by HA: `POST /api/device/reboot`
- ESP endpoint used by HA: `POST /api/device/forget`

### Voice/PTT Flow

```text
ESP physical PTT
  -> raw WAV upload to POST /api/spotify_dj/voice
  -> HA STT provider selection
  -> recognized text
  -> SpotifyDJ command processing
  -> Spotify playback command/result
  -> DJ text response
  -> HA TTS temporary WAV/MP3 URL where possible
  -> JSON response to ESP
  -> ESP displays text and plays audio URL
```

STT provider selection order:

1. `stt_engine` option from SpotifyDJ config/options.
2. Stored `assist_pipeline_id`.
3. Home Assistant preferred/default Assist pipeline.
4. First Assist pipeline with STT.
5. First HA `stt.*` entity.
6. HA `assist_pipeline.async_pipeline_from_audio_stream` fallback.

## Decisions Made

- Active integration routes use Home Assistant Assist/STT/TTS only; no direct external AI/STT/TTS API calls should remain in active paths.
- `stt_engine` is the official SpotifyDJ option key for physical PTT STT provider selection.
- Text-only/JSON requests to `/api/spotify_dj/voice` are developer/DJ-response tests and must not trigger Spotify playback command parsing.
- Raw WAV requests to `/api/spotify_dj/voice` remain the real PTT path and do trigger STT, command parsing and Spotify playback.
- Backend playback is controlled by the Home Assistant integration and exposed through a native playback-proxy `media_player`; ESP device settings use `/api/device/command`.
- DJ responses play on the SpotifyDJ ESP device, not through Spotify Connect and not through a Home Assistant media player.
- HA may send temporary WAV or MP3 `audio_url` values to the ESP; ESP decides how to play supported formats.
- Spotify OAuth uses PKCE and Home Assistant external step. The config flow must not expose a manual `oauth_result` field.
- Spotify OAuth scopes must include `playlist-read-private` so private `SpotifyDJ Liked Proxy` playlists can be found by firmware.
- Spotify refresh tokens may rotate. New tokens must be saved persistently immediately and all pair/status/provision responses must use canonical/latest credentials.
- ESP `/status` with `spotify_configured=false` is treated as a compatibility/status hint for HA backend playback, not as a request to send OAuth credentials to ESP.
- BLE provisioning writes WiFi SSID/password only. No Spotify credentials, device tokens or other secrets over BLE.
- Runtime discovery prefers device-reported `local_url`, exact `_spotifydj._tcp` mDNS matches, then a single visible SpotifyDJ mDNS device.
- Never generate or store `spotifydj-[6-digit-code].local` as a valid device URL. Only 12-hex device suffixes may become `http://spotifydj-[suffix].local` fallbacks.
- Pair/status handlers persist the real `spotifydj-XXXXXXXXXXXX` identity and reported `local_url` so HA restarts do not fall back to setup-code identities.
- HA startup skips ESP re-pairing if a device token already exists; Spotify credential provisioning is opportunistic and may defer until the device is reachable.
- Firmware asset name is distributive, e.g. `spotifydj-device-vX.Y.Z.bin`; OTA target device comes from `firmware_manifest.json` field `device`, currently `lilygo-t-embed-s3`.
- All HA entities should belong to one stable Home Assistant device identifier.
- Secrets must not be logged or exposed in diagnostics; redact keys containing `token`, `password` or `secret`.
- Spotify trademark/non-affiliation notice must remain in docs/UI/diagnostics.

## Known Issues

- Real-world PTT/STT behavior still needs validation on the target Home Assistant instance with the selected `stt_engine`, especially providers that are strict about WAV metadata.
- HA STT provider compatibility depends on Home Assistant core APIs and installed STT integrations. The fallback chain is defensive but should be tested after Home Assistant upgrades.
- Already-installed entries created before the real device id/local URL persistence fix may self-repair only after the ESP successfully posts `/api/spotify_dj/status` with real `device_id` and `local_url`.
- mDNS can still fail on networks where `.local` resolution or HA zeroconf browsing is unreliable. Manual device URL remains available under advanced options.
- HACS/Home Assistant custom integration updates still normally require a Home Assistant restart to load changed Python code.
- Brand icons in Home Assistant frontend may require cache refresh and may still depend on Home Assistant/HACS frontend behavior.

## Next Tasks

- Install `v2.9.10` through HACS, restart Home Assistant and verify:
  - Options flow opens without internal server error.
  - Existing paired device remains paired.
  - No startup re-pair attempt is logged when `device_token` exists.
  - ESP `/status` persists real `spotifydj-XXXXXXXXXXXX` and `local_url`.
  - Spotify provisioning no longer fails because HA only knows a 6-digit setup-code URL.
- Test physical PTT end-to-end:
  - ESP uploads raw WAV.
  - HA selects/logs the intended STT provider.
  - STT returns recognized text.
  - Spotify command processing runs.
  - DJ text and optional WAV/MP3 `audio_url` return to ESP.
- If STT still fails, capture sanitized logs around:
  - selected `stt_engine`,
  - WAV sample rate/channels/sample width,
  - provider result type/state,
  - Assist event types.
- Verify developer services/actions:
  - `spotify_dj.test_parse`
  - `spotify_dj.test_command`
  - `spotify_dj.test_tts`
- Verify Spotify token rotation/backend playback:
  - OAuth callback stores latest refresh token.
  - ESP status with `spotify_configured=false` receives current credentials.
  - Logs do not expose refresh tokens.
- Verify OTA with public firmware repo:
  - Latest GitHub release is discovered.
  - `firmware_manifest.json` parses even as `application/octet-stream`.
  - OTA payload sends `device: "lilygo-t-embed-s3"` from manifest.
- Keep documentation current after each release:
  - `README.md`
  - `CHANGELOG.md`
  - `AGENTS.md`
  - `website/index.html`
  - `THIRD_PARTY_NOTICES.md`
- Review `website/index.html` whenever the out-of-the-box setup,
  requirements, local API architecture or legal/trademark wording
  changes.
- Before future releases, run:
  - `python3 -m unittest discover -s tests`
  - `./release.sh X.Y.Z --dry-run`
  - `./release.sh X.Y.Z`
- Optional cleanup after successful releases:
  - `./cleanup_old_releases.sh --keep 1 --execute`
