# Changelog

## 3.0.18

- Add explicit Spotify repair-flow popup text for the initial repair action, so the Home Assistant repair dialog no longer opens as a blank external-website step.
- Harden device sensor caching: local ESP command responses, device-info refreshes, empty Spotify playback snapshots and accidental command/voice payloads can no longer replace the cached ESP status with empty/unknown values.
- Keep `ha_pairing_status`, firmware, battery, Wi-Fi RSSI, screen/LED state, sound output, volume and last track stable until a real `/api/djconnect/status` update or explicit user action changes them.
- Guard device sensors against command/voice payloads: `/api/djconnect/command` and voice-only payloads now explicitly avoid device sensor merges, so sparse command/status polls cannot reset battery, firmware, RSSI, pairing, output or screen/LED state to unknown/pending.
- Add an authenticated voice debug endpoint at `/api/djconnect/debug/last_voice.wav`; when DJConnect debug logging is enabled, HA keeps the last raw ESP WAV in memory so you can listen to exactly what STT received.
- Add `button.djconnect_refresh_up_next` to refresh the backend queue/up-next list from Home Assistant.
- Refresh Spotify output devices from the sound-output select so HA shows available outputs without needing a manual `devices` command first.
- Accept output aliases from `available_outputs`, `outputs`, `devices` and nested `items` payloads.
- Return queue `context_uri` / `contextUri` and queue item album-art aliases for ESP/web Up Next support.
- Keep queue context available from Spotify playback metadata and queue/status aliases.
- Improve playback proxy artwork fallback through `album_image_url`, `media_image_url`, `image_url` and `entity_picture`.
- Keep sparse ESP status heartbeats from clearing known sensor/entity values.
- Make Developer Actions UI fields explicit with `command_text` and `dj_response_text` while keeping legacy `text` YAML/scripts working.
- Fall back to a simple Spotify search intent when HA Assist treats the DJConnect parsing prompt as a normal smart-home device command.
- Document current HA button/entities, website HA-control copy, refresh flows and ESP sync contract.
- Extend tests for Up Next refresh, output refresh aliases, queue context, artwork fallback, developer action aliases and Assist fallback behavior.
