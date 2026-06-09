# Changelog

## 3.0.6

- Use the dark DJConnect SVG banner in the README so GitHub and HACS do not show the old white PNG canvas.
- Improve the product website hero so callout text no longer sits behind the LilyGO device illustration.
- Update the LilyGO-style device illustration with an embedded DJConnect icon on the screen.
- Add website copy for personal voice based DJ responses on the device.
- Expand the website bonus games copy to mention Pong, Asteroids and Fly.
- Rename the Home Assistant integration, HACS metadata, repository references, brand assets, examples, website and user-facing documentation to DJConnect.
- Keep the integration domain on `djconnect` and publish the clean `v3.0.5` release line after removing older release/tag history from the renamed repository.
- Enforce HA/ESP `major.minor` protocol compatibility: patch versions may differ, but mismatched major/minor firmware now receives HTTP `426` `version_mismatch` without clearing pairing.
- Require current ESP device identity format `djconnect-lilygo-XXXXXXXXXXXX`; setup-code pairing may start with a temporary `djconnect-[6-digit-code]` identity, but legacy `djconnect-XXXXXXXXXXXX` IDs are no longer accepted.
- Replace the ESP pairing `ha_url` field with `ha_local_url` and `ha_remote_url` so firmware can use LAN-first routing with cloud fallback.
- Harden pairing so `/api/device/pair` is only called during initial pairing, explicit re-pair/token rotation or stale-pairing recovery, and HA pairing remains pending until ESP confirms `ha_pairing_status=paired`.
- Keep Spotify OAuth credentials HA-internal; pair/status responses and BLE provisioning never send Spotify client IDs, access tokens or refresh tokens to the ESP.
- Move backend playback fully behind the Home Assistant integration and expose it through the optional DJConnect playback proxy `media_player`.
- Replace combined playback mode handling with canonical `set_shuffle` and `set_repeat` backend commands plus native Home Assistant switch/select entities.
- Cache Spotify access tokens in Home Assistant, refresh them on demand, retry once after Spotify API `401`, and surface revoked refresh tokens through user-friendly reauthorization/Repair flows.
- Use Home Assistant external OAuth with PKCE and the `/api/djconnect/spotify/callback` redirect path, preferring Nabu Casa HTTPS URLs when available.
- Route physical PTT through authenticated raw WAV uploads to `/api/djconnect/voice`, process STT through Home Assistant providers/pipelines, and keep text-only voice requests as developer DJ-response tests.
- Deliver DJ responses to the DJConnect device via `/api/device/dj_response` with response text and optional temporary WAV/MP3 `audio_url`; DJ responses are not routed through Spotify Connect.
- Add DJConnect device language selection, HA-populated dropdowns where reliable, safer options-flow defaults, and explicit re-pair/retry/Spotify reauthorize actions.
- Expose native device entities for playback controls, firmware update, screen/LED state, brightness, volume, timeouts, language, theme, log level and status diagnostics under one stable Home Assistant device.
- Treat unknown or invalid device values such as volume `-1` as unavailable instead of publishing out-of-range Home Assistant states.
- Prefer device-reported `local_url`, exact `_djconnect._tcp` mDNS matches and then a single visible DJConnect mDNS service; never create `djconnect-[6-digit-code].local` or legacy non-lilygo host fallbacks.
- Align OTA discovery with public firmware assets named `djconnect-device-vX.Y.Z.bin`, manifests named `firmware_manifest.json`, and manifest `device` targets such as `lilygo-t-embed-s3`.
- Preserve the split licensing model: MIT-licensed Home Assistant integration, proprietary ESP firmware source, public firmware binaries covered by `FIRMWARE-LICENSE.md`, and visible Spotify trademark/non-affiliation notices.
- Refresh README, website, examples, diagnostics metadata, handoff notes, ESP synchronization prompt and tests for the DJConnect 3.0.5 architecture.
