# Changelog

## 3.0.10

- Add canonical `client_type` metadata for DJConnect clients, with `esp32` for LilyGO/ESP firmware and reserved `ios`/`macos` values for future app clients.
- Require ESP JSON pairing/status/command/event payloads to include a valid `client_type`; missing or unknown values now return `invalid_client_type`.
- Persist `client_type` in Home Assistant config entries and return it in pairing/status responses.
- Update the ESP sync prompt, README and handoff rules so ESP firmware sends `client_type: "esp32"` explicitly without a fallback field.
- Extend tests for required `client_type` handling, pairing payload metadata and future iOS/macOS client metadata.
