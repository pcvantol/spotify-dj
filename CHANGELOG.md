# Changelog

## 1.5.1

- Replace the manual `oauth_result` setup field with a Home Assistant external OAuth step.
- Open the Spotify authorize website from the config flow and complete setup from the HTTPS callback.
- Keep the Nabu Casa callback path `/api/spotify_dj/spotify/callback` supported.
- Keep voice and AI settings in the config flow and options flow with safe defaults.
- Route test parse/command services through HA Assist instead of the legacy direct OpenAI parser.
- Route the test DJ voice button through HA TTS instead of direct OpenAI TTS.
- Remove direct OpenAI STT/TTS calls from active HTTP voice handling.
- Add Home Assistant populated dropdowns for supported config-flow fields.
- Add clearer config-flow error messages in Dutch and English.
- Add lightweight unit tests for OAuth helpers, config-flow helpers and translation coverage.
- Refresh README and AGENTS instructions for the current HACS release workflow.
