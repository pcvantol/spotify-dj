# Changelog

## 3.0.0

- Rename the integration, repository references, brands, examples, website assets and user-facing documentation from SpotifyDJ to DJConnect.
- Publish DJConnect as the clean `v3.0.0` release line after removing old SpotifyDJ GitHub releases and tags from the renamed repository.
- Keep the Home Assistant integration domain on `djconnect` and align HACS metadata, README, AGENTS instructions, ESP sync prompt and handoff notes with the new release.
- Preserve the split licensing model: MIT-licensed Home Assistant integration, proprietary ESP firmware source, public firmware binaries covered by `FIRMWARE-LICENSE.md`, and visible Spotify trademark/non-affiliation notices.
- Harden pairing so Home Assistant only calls `/api/device/pair` during initial pairing, explicit re-pair/token rotation or stale-pairing recovery, and never during normal startup, status sync, settings sync or playback commands.
- Keep Home Assistant pairing status pending until the ESP confirms `ha_pairing_status=paired`, while accepting the real `djconnect-lilygo-XXXXXXXXXXXX` device ID after setup-code based pairing.
- Replace the legacy ESP pairing `ha_url` field with `ha_local_url` and `ha_remote_url` so firmware can use LAN-first routing with cloud fallback.
- Move backend playback fully behind the Home Assistant integration and expose it through the optional DJConnect playback proxy `media_player`.
- Replace the old combined `set_play_mode` flow with canonical `set_shuffle` and `set_repeat` backend commands plus native Home Assistant switch/select entities.
- Cache Spotify access tokens in Home Assistant, refresh them on demand, retry once after Spotify API `401`, and show revoked refresh tokens through user-friendly reauthorization/Repair flows.
- Keep Spotify OAuth credentials HA-internal; pair/status responses and BLE provisioning never send Spotify client IDs, access tokens or refresh tokens to the ESP.
- Use Home Assistant external OAuth with PKCE and the `/api/djconnect/spotify/callback` redirect path, preferring Nabu Casa HTTPS URLs when available.
- Route physical PTT through authenticated raw WAV uploads to `/api/djconnect/voice`, process STT through Home Assistant providers/pipelines, and keep text-only voice requests as developer DJ-response tests.
- Deliver DJ responses to the DJConnect device via `/api/device/dj_response` with response text and optional temporary WAV/MP3 `audio_url`; never route DJ responses through Spotify Connect.
- Add DJConnect device language selection, HA-populated dropdowns where reliable, safer options-flow defaults, and explicit re-pair/retry/Spotify reauthorize actions.
- Expose native device entities for playback controls, firmware update, screen/LED state, brightness, volume, timeouts, language, theme, log level and status diagnostics under one stable Home Assistant device.
- Treat unknown or invalid device values such as volume `-1` as unavailable instead of publishing out-of-range Home Assistant states.
- Prefer device-reported `local_url`, exact `_djconnect._tcp` mDNS matches and then a single visible DJConnect mDNS service; avoid old `djconnect-[6-digit-code].local` fallbacks.
- Align OTA discovery with public firmware assets named `djconnect-device-vX.Y.Z.bin`, manifests named `firmware_manifest.json`, and manifest `device` targets such as `lilygo-t-embed-s3`.
- Add and document the release helper/cleanup flow for dry-run-first version bumps, GitHub release creation and old release/tag cleanup.
- Refresh README, website, examples, diagnostics metadata, handoff notes and ESP synchronization prompt for the DJConnect architecture.
- Expand lightweight tests for OAuth helpers, config-flow defaults, diagnostics redaction/legal metadata, translations, playback backend behavior, voice helpers, native entities and update handling.
