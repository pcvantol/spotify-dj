# Changelog

## 2.6.1

- Replace the manual `oauth_result` setup field with a Home Assistant external OAuth step.
- Open the Spotify authorize website from the config flow and complete setup from the HTTPS callback.
- Keep the Nabu Casa callback path `/api/spotify_dj/spotify/callback` supported.
- Keep voice and AI settings in the config flow and options flow with safe defaults.
- Route test parse/command services through HA Assist instead of the legacy direct AI parser.
- Ignore generic HA Assist smart-home refusal text as `dj_announcement` when no explicit SpotifyDJ intent data is returned.
- Route DJ responses to the SpotifyDJ device through HA-generated temporary PCM WAV URLs and `/api/device/dj_response`.
- Refactor the voice HTTP endpoint to accept text commands only after ESP-side HA Assist websocket STT.
- Return controlled JSON errors for legacy WAV uploads and missing text instead of running STT inside the integration.
- Include `assist_pipeline_id`, `ha_url`, and `device_token` in ESP provisioning/status payloads where applicable.
- Include Spotify OAuth credentials during pair/status responses with both nested and top-level `refresh_token`/`spotify_refresh_token` keys for firmware compatibility.
- Add SpotifyDJ device UI language selection during pairing and provision `device_language`/`language` to the ESP.
- Remove direct STT/TTS calls from active HTTP voice handling.
- Remove legacy direct external AI client code from the Home Assistant integration.
- Store the config-flow pair code and reject ESP pairing attempts with a different code.
- Require a Spotify media player in config-flow/options-flow.
- Keep manual SpotifyDJ device URL hidden unless Home Assistant advanced options are enabled.
- Default `allow_ota_on_battery` to enabled in advanced options.
- Use one stable HA device identifier for sensors, button, and update entities.
- Replace user-facing board/vendor wording with SpotifyDJ device wording.
- Add Home Assistant populated dropdowns for supported config-flow fields.
- Add complete readable config-flow/options-flow labels, descriptions, titles and error messages in Dutch and English.
- Improve developer test action docs, responses and safe debug logging.
- Harden diagnostics redaction for token/password/secret aliases and avoid logging full ESP event payloads.
- Refactor setup/service helpers to reduce handler complexity and improve testability.
- Add optional BLE WiFi provisioning in the config flow using the SpotifyDJ setup service UUID.
- Add Bluetooth manifest matcher and dependencies for HA Bluetooth adapters/proxies.
- Add bundled Spotify Client ID as default, with advanced override in the config flow.
- Fix opening the options flow on newer Home Assistant versions where `config_entry` is read-only.
- Add temporary `GET /api/spotify_dj/tts/{token}.wav` audio hosting with 404/410 handling.
- Add lightweight unit tests for OAuth helpers, config-flow helpers and translation coverage.
- Refresh README and AGENTS instructions for the current HACS release workflow.
