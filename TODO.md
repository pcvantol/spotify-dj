# DJConnect TODO Backlog

## Immediate Validation

- Install the latest HACS release in Home Assistant.
- Restart Home Assistant after installation.
- Open DJConnect options flow and confirm there is no internal server error.
- Confirm existing paired device remains paired after HA restart when ESP reports `ha_pairing_status=paired`.
- Confirm iOS/macOS paired clients do not show active/available firmware OTA or reboot entities.
- Confirm iOS/macOS PTT requests do not create a false Spotify refresh-token repair after the first DJ announcement.
- Confirm HA shows pairing `pending` and retries `/api/device/pair` when a local token exists but ESP has not confirmed pairing.
- Confirm ESP `/status` updates persist the real `djconnect-XXXXXXXXXXXX` device id.
- Confirm ESP `/status` updates persist the real `local_url` when provided.
- Confirm old setup-code entries stop using `djconnect-[6-digit-code].local` after status repair.

## PTT / Voice

- Test physical PTT end-to-end on the ESP device.
- Confirm ESP uploads raw WAV to `POST /api/djconnect/voice`.
- Confirm HA logs selected `stt_engine` without secrets.
- Confirm HA logs WAV metadata: sample rate, channel count, sample width and byte length.
- Confirm selected HA STT provider accepts the WAV metadata.
- Confirm recognized text reaches DJConnect command processing.
- Confirm Spotify playback action runs when Spotify is idle.
- Confirm repeated iOS/macOS PTT requests reuse or serialize Spotify token refresh without false `invalid_grant` repairs.
- Confirm artist queue/up-next selection does not send invalid Spotify artist offset payloads.
- Confirm friendly DJ fallback response is returned when Spotify playback fails.
- Confirm DJ fallback response follows `device_language` (`nl` or `en`).
- Confirm ESP receives and plays WAV/MP3 `audio_url` when HA TTS generates supported audio.
- Confirm ESP handles text-only DJ aankondiging if HA TTS output is unsupported.

## Spotify Provisioning

- Verify Spotify OAuth still completes through HA external step.
- Verify OAuth scopes include `playlist-read-private`.
- Verify OAuth callback stores latest `spotify_refresh_token` persistently.
- Verify concurrent Spotify API calls after HA restart do not refresh the same old token in parallel.
- Verify status payload with `spotify_configured=false` does not return Spotify credentials.
- Verify Spotify OAuth credentials stay in Home Assistant and are not sent to ESP.
- Verify no Spotify refresh token value appears in logs or diagnostics.

## Pairing / Discovery

- Test pairing with a fresh ESP in setup mode.
- Test captive-portal WiFi setup followed by BLE screen action `Continue to pairing`.
- Test BLE screen action `Rescan Bluetooth devices`.
- Test BLE screen action `Write WiFi over Bluetooth`.
- Test pairing with Client API URL left empty for ESP devices.
- Test pairing with iOS/macOS Client API URL copied from app Settings.
- Test mDNS discovery through `_djconnect._tcp`.
- Test mDNS single-device fallback when only one DJConnect device is visible.
- Test Client API URL fallback on a network where mDNS fails.
- Confirm invalid pairing code is rejected with a clear user message.
- Confirm real device id and local URL are persisted after `/pair`.
- Confirm real device id and local URL are persisted after `/status`.

## Config Flow / Options Flow

- Confirm normal config flow stays small and user-focused.
- Confirm `client_type` and Client API URL are visible in normal pairing.
- Confirm `stt_engine` remains visible in normal flow/options.
- Confirm `stt_engine` dropdown is populated from HA `stt.*` entities when available.
- Confirm `stt_engine` remains free-text capable when no HA `stt.*` entities are discoverable.
- Confirm advanced-only options remain hidden behind the integration-local advanced checkbox.
- Confirm HA deprecated `show_advanced_options` is not used.
- Confirm no `spotify_player` field is required in config/options flow.
- Confirm all titles, labels and error messages are available in Dutch and English.

## OTA / Firmware Updates

- Verify firmware release discovery from `pcvantol/djconnect-firmware`.
- Verify `firmware_manifest.json` is parsed even if GitHub serves it as `application/octet-stream`.
- Verify update entity displays firmware asset, manifest URL, target device, sha256 and min HA integration.
- Verify OTA payload sends manifest `device`, currently `lilygo-t-embed-s3`.
- Verify ESP no longer rejects OTA with `Wrong device target`.
- Verify OTA errors are shown clearly in HA.
- Verify firmware OTA update entity is not added and remains unavailable for `client_type=ios` and `client_type=macos`.
- Verify reboot entity is not added for `client_type=ios` and `client_type=macos`.

## Developer Services

- Test `djconnect.test_parse`.
- Test `djconnect.test_command` with `play: false`.
- Test `djconnect.test_command` with `play: true`.
- Test `djconnect.test_tts` and confirm response is sent to ESP, not HA media player.
- Test Spotify backend playback after OAuth refresh-token rotation.
- Test Spotify backend playback with simultaneous status/play/queue calls after OAuth refresh-token rotation.
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
- Keep `CHANGELOG.md` consolidated to the current release only.
- Keep `HANDOFF.md` current after major debugging sessions.
- Keep `TODO.md` and `ISSUES.md` current after field testing.
- Document known HA restart requirement after HACS custom integration updates.

## Website / Marketing

- Keep product/marketing website work in the external website location, not this HA integration repo.
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
