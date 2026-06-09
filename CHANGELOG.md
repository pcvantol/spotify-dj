# Changelog

## 3.0.13

- Add `button.djconnect_refresh_up_next` to refresh the backend queue/up-next list from Home Assistant.
- Refresh Spotify output devices from the sound-output select so HA shows available outputs without needing a manual `devices` command first.
- Accept output aliases from `available_outputs`, `outputs`, `devices` and nested `items` payloads.
- Keep queue context available from Spotify playback metadata and queue/status aliases.
- Improve playback proxy artwork fallback through `album_image_url`, `media_image_url`, `image_url` and `entity_picture`.
- Keep sparse ESP status heartbeats from clearing known sensor/entity values.
- Make Developer Actions UI fields explicit with `command_text` and `dj_response_text` while keeping legacy `text` YAML/scripts working.
- Fall back to a simple Spotify search intent when HA Assist treats the DJConnect parsing prompt as a normal smart-home device command.
- Document current HA button/entities and refresh flows.
- Extend tests for Up Next refresh, output refresh aliases, queue context, artwork fallback, developer action aliases and Assist fallback behavior.
