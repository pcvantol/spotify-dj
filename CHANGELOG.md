# Changelog

## 3.0.12

- Fix Home Assistant playback proxy play/pause toggle support.
- Fix sound output select state by reading playback device, `output` aliases and active output entries.
- Replace the `turn_off_after` slider with a fixed select for 5, 15, 30 or 60 minutes.
- Keep speaker volume from jumping back to unknown/zero by accepting local volume aliases from firmware status.
- Expose album art through `media_image_url` and choose the best Spotify image in playback metadata.
- Surface missing ESP `client_type=esp32` status payloads as a visible HA status error instead of leaving sensors silently unknown.
- Extend tests for media player controls, sound output, turn-off options, volume aliases, album art and strict client type errors.
