# Changelog

## 1.1.0
Fix config flow constants


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
