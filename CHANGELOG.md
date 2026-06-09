# Changelog

## 3.0.9

- Fix Spotify setup external URL prefill for Home Assistant Cloud/Nabu Casa URLs by supporting current sync `network.get_url` and `cloud.async_remote_ui_url` helpers.
- Prefer the Nabu Casa Cloud URL when Home Assistant Network exposes both local and cloud URLs, while still requiring an HTTPS external URL for Spotify OAuth.
- Keep fallback support for configured `external_url`, `config.api.external_url` and integration data values across Home Assistant versions.
- Demote GitHub firmware release rate-limit messages from warning to debug so temporary API throttling no longer pollutes the Home Assistant logbook.
- Pair the ESP during the initial config flow before creating the Home Assistant config entry, so HA no longer reports a successful setup while the device is still waiting on the pairing screen.
- Learn the real `djconnect-lilygo-XXXXXXXXXXXX` device id and `local_url` from `/api/device/pairing-info` before storing the config entry.
- Extend tests for sync/async Home Assistant URL helpers, quiet GitHub rate-limit handling and initial pairing-before-entry behavior.
