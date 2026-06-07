# SpotifyDJ TODO Backlog

## Immediate Validation

- Install HACS release `v2.9.10` in Home Assistant.
- Restart Home Assistant after installation.
- Open SpotifyDJ options flow and confirm there is no internal server error.
- Confirm existing paired device remains paired after HA restart.
- Confirm HA no longer attempts ESP re-pairing when `device_token` exists.
- Confirm ESP `/status` updates persist the real `spotifydj-XXXXXXXXXXXX` device id.
- Confirm ESP `/status` updates persist the real `local_url` when provided.
- Confirm old setup-code entries stop using `spotifydj-[6-digit-code].local` after status repair.

## PTT / Voice

- Test physical PTT end-to-end on the ESP device.
- Confirm ESP uploads raw WAV to `POST /api/spotify_dj/voice`.
- Confirm HA logs selected `stt_engine` without secrets.
- Confirm HA logs WAV metadata: sample rate, channel count, sample width and byte length.
- Confirm selected HA STT provider accepts the WAV metadata.
- Confirm recognized text reaches SpotifyDJ command processing.
- Confirm Spotify playback action runs when Spotify is idle.
- Confirm friendly DJ fallback response is returned when Spotify playback fails.
- Confirm DJ fallback response follows `device_language` (`nl` or `en`).
- Confirm ESP receives and plays WAV/MP3 `audio_url` when HA TTS generates supported audio.
- Confirm ESP handles text-only DJ response if HA TTS output is unsupported.

## Spotify Provisioning

- Verify Spotify OAuth still completes through HA external step.
- Verify OAuth scopes include `playlist-read-private`.
- Verify OAuth callback stores latest `spotify_refresh_token` persistently.
- Verify status payload with `spotify_configured=false` does not return Spotify credentials.
- Verify pair response uses latest refresh token, not stale entry data.
- Verify Spotify OAuth credentials stay in Home Assistant and are not sent to ESP.
- Verify no Spotify refresh token value appears in logs or diagnostics.

## Pairing / Discovery

- Test pairing with a fresh ESP in setup mode.
- Test pairing with manual device URL left empty.
- Test mDNS discovery through `_spotifydj._tcp`.
- Test mDNS single-device fallback when only one SpotifyDJ device is visible.
- Test manual advanced device URL override on a network where mDNS fails.
- Confirm invalid pairing code is rejected with a clear user message.
- Confirm real device id and local URL are persisted after `/pair`.
- Confirm real device id and local URL are persisted after `/status`.

## Config Flow / Options Flow

- Confirm normal config flow stays small and user-focused.
- Confirm `stt_engine` remains visible in normal flow/options.
- Confirm `stt_engine` dropdown is populated from HA `stt.*` entities when available.
- Confirm `stt_engine` remains free-text capable when no HA `stt.*` entities are discoverable.
- Confirm advanced-only options remain hidden behind the integration-local advanced checkbox.
- Confirm HA deprecated `show_advanced_options` is not used.
- Confirm no `spotify_player` field is required in config/options flow.
- Confirm all titles, labels and error messages are available in Dutch and English.

## OTA / Firmware Updates

- Verify firmware release discovery from `pcvantol/spotify-dj-firmware`.
- Verify binary asset prefix `spotifydj-device` is accepted.
- Verify `firmware_manifest.json` is parsed even if GitHub serves it as `application/octet-stream`.
- Verify update entity displays firmware asset, manifest URL, target device, sha256 and min HA integration.
- Verify OTA payload sends manifest `device`, currently `lilygo-t-embed-s3`.
- Verify ESP no longer rejects OTA with `Wrong device target`.
- Verify OTA errors are shown clearly in HA.

## Developer Services

- Test `spotify_dj.test_parse`.
- Test `spotify_dj.test_command` with `play: false`.
- Test `spotify_dj.test_command` with `play: true`.
- Test `spotify_dj.test_tts` and confirm response is sent to ESP, not HA media player.
- Test Spotify backend playback after OAuth refresh-token rotation.
- Update service documentation if any response payload changes.

## Security / Privacy

- Re-run diagnostics and confirm redaction for keys containing `token`, `password` or `secret`.
- Confirm no device token, HA token, Spotify refresh token or WiFi password appears in logs.
- Confirm BLE provisioning only sends WiFi SSID/password.
- Confirm no Spotify/device credentials are sent via BLE.
- Confirm `THIRD_PARTY_NOTICES.md` remains accurate after dependency changes.

## Documentation

- Update `README.md` after any architecture/API change.
- Update `AGENTS.md` after any durable project decision.
- Update `website/index.html` after any product positioning, quick-start,
  requirement, local API, OTA, Assist or legal/trademark wording change.
- Keep `CHANGELOG.md` consolidated to the current release only.
- Keep `HANDOFF.md` current after major debugging sessions.
- Keep `TODO.md` and `ISSUES.md` current after field testing.
- Document known HA restart requirement after HACS custom integration updates.

## Website / Marketing

- Review `website/index.html` on mobile and desktop before publishing.
- Decide whether to host the onepager from this repo, GitHub Pages or a separate product website repo.
- Add real product photos/screenshots when final hardware imagery is available.
- Keep requirements clear: Spotify Premium, Home Assistant, HACS, HA Assist pipeline, 2.4 GHz WiFi and mDNS/Nabu Casa recommendations.

## Release Workflow

- Run `python3 -m unittest discover -s tests` before release.
- Run `./release.sh X.Y.Z --dry-run` before publishing when changes are non-trivial.
- Run `./release.sh X.Y.Z` for release.
- Refresh HACS update info in Home Assistant.
- Install new release from HACS.
- Restart Home Assistant.
- Optionally run `./cleanup_old_releases.sh --keep 1 --execute` after successful release.
