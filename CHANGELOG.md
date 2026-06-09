# Changelog

## 3.0.8

- Fix Spotify setup external URL prefill for Home Assistant Cloud/Nabu Casa URLs by supporting current sync `network.get_url` and `cloud.async_remote_ui_url` helpers.
- Prefer the Nabu Casa Cloud URL when Home Assistant Network exposes both local and cloud URLs, while still requiring an HTTPS external URL for Spotify OAuth.
- Keep fallback support for configured `external_url`, `config.api.external_url` and integration data values across Home Assistant versions.
- Demote GitHub firmware release rate-limit messages from warning to debug so temporary API throttling no longer pollutes the Home Assistant logbook.
- Extend tests for sync/async Home Assistant URL helpers and quiet GitHub rate-limit handling.
