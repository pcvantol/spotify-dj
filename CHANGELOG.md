# Changelog

## 1.4.3

- Replace the manual `oauth_result` setup field with a Home Assistant external OAuth step.
- Open the Spotify authorize website from the config flow and complete setup from the HTTPS callback.
- Keep the Nabu Casa callback path `/api/spotify_dj/spotify/callback` supported.

## 1.3.0

- Fix config flow loading regressions.
- Add safe defaults for empty voice settings.
- Keep `dj_style` and `dj_profile` aliases for backwards compatibility.
- Fix HTTP view constructors used by Home Assistant setup.

# Changelog

## 1.0.0

Production-polish release.

### Added
- Diagnostics download with secret redaction.
- Repair issue scaffolding for missing pairing/device token and Spotify Client ID.
- Dutch and English translations for config flow.
- HACS and hassfest GitHub Action validation.
- Stable/beta firmware channel option.
- v1.0 release checklist and GitHub/HACS guidance.

### Architecture
- Home Assistant remains the pairing, provisioning and OTA control plane.
- LilyGO can keep standalone Spotify API functionality after Spotify credential provisioning.
- OTA distribution is HA-managed through the public firmware release repository.

## 0.8.0

- HACS/brand assets.
- App icon and logo assets.
