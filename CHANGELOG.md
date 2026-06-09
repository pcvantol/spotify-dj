# Changelog

## 3.0.24

- Persist the last known ESP device status in the Home Assistant config entry and restore it on integration reload/startup, so battery, firmware, sound output, screen/LED state and `ha_pairing_status=paired` do not fall back to unknown/pending while waiting for the next ESP status post.
- Expose PTT debugging as entity attributes on `sensor.djconnect_status` and `sensor.djconnect_last_command`, including `last_stt_text`, `last_spotify_search` and `last_resolved_media`.
- Generate the spoken PTT DJ response from resolved Spotify/playback metadata and the selected DJ style, so successful requests mention the actual track, artist, album or playlist instead of a generic “I’ll start it” fallback.
- Store resolved Spotify Search metadata with playback responses so device TTS can describe what actually started playing.
- Resolve plain Assist/voice search text through Spotify Search before starting playback, so commands like `ik wil Pearl Jam starten` are converted to a playable Spotify URI instead of being sent to `/me/player/play` as arbitrary text.
- Retry playback once when Spotify reports no active playback device: DJConnect now refreshes Spotify devices, selects the configured source by visible name or device ID when possible, transfers playback there and retries.
- Show Spotify source override in the normal config/options flow again, because it is needed for reliable voice playback routing.
- Preserve the parsed DJConnect intent when playback fails and include it in command-failed voice responses for easier Assist/Spotify debugging.
- Prevent Nabu Casa/cloud URLs from being sent as `ha_local_url`; pairing now uses Home Assistant's local/network URL, LAN source-IP fallback, or `http://homeassistant.local:8123` for `ha_local_url`, and sends cloud only as `ha_remote_url`.
- Keep the options-flow “re-pair with new pairing code” field empty instead of pre-filling the old stored pairing code.
- Set the Spotify repair OAuth popup title and description directly on the Repairs external-step result, so Home Assistant no longer shows a blank dialog when translation lookup misses the dynamic repair issue id.
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
