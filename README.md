# SpotifyDJ

SpotifyDJ is a Home Assistant custom integration for a LilyGO T-Embed S3 / CC1101 Plus Spotify and voice remote.

The Home Assistant integration handles pairing, Spotify OAuth provisioning, OTA firmware updates, device status, and voice/AI integration. The ESP firmware can keep talking to the Spotify API independently after Home Assistant provisions the Spotify credentials.

## Current Version

- Home Assistant integration: `1.5.1`
- Domain: `spotify_dj`
- HACS category: `Integration`
- Device target: LilyGO T-Embed S3 / CC1101 Plus
- Firmware mDNS service: `_spotifydj._tcp`
- Device ID format: `spotifydj-XXXXXXXXXXXX`

## Features

- Pair a LilyGO SpotifyDJ device with a 6 digit code.
- Provision a per-device bearer token.
- Run Spotify OAuth with PKCE from the Home Assistant config flow.
- Open the Spotify authorization website instead of manually pasting an OAuth result.
- Support a Nabu Casa HTTPS callback at `/api/spotify_dj/spotify/callback`.
- Provision Spotify `client_id` and `refresh_token` to the ESP.
- Accept voice WAV requests from the ESP and return WAV responses.
- Use Home Assistant Assist/TTS settings with safe defaults.
- Process text commands through HA Assist before sending the resulting SpotifyDJ intent to Spotify.
- Use HA-native Assist/TTS routes in active services and entities, without a direct OpenAI API key requirement.
- Track device status, battery, Wi-Fi RSSI, firmware version, and last track.
- Manage firmware updates through a Home Assistant update entity.
- Provide diagnostics with sensitive values redacted.

## Repository Layout

- Home Assistant integration: `pcvantol/spotify-dj`
- ESP firmware source: `pcvantol/spotify-dj-app`
- Public firmware releases: `pcvantol/spotify-dj-firmware`

This repository contains the Home Assistant custom integration under `custom_components/spotify_dj`.

## Install Through HACS

1. Open HACS in Home Assistant.
2. Add `https://github.com/pcvantol/spotify-dj` as a custom repository.
3. Select category `Integration`.
4. Install SpotifyDJ.
5. Restart Home Assistant.
6. Go to **Settings -> Devices & services -> Add integration -> SpotifyDJ**.

## Spotify Developer App

Create a Spotify Developer App and copy its Client ID. PKCE is used, so no client secret is required.

Add this redirect URI to the Spotify app:

```text
https://<your-nabu-casa-id>.ui.nabu.casa/api/spotify_dj/spotify/callback
```

For local-only development you can use a reachable Home Assistant URL instead:

```text
http://homeassistant.local:8123/api/spotify_dj/spotify/callback
```

The redirect URI in Spotify must exactly match the Home Assistant external URL plus `/api/spotify_dj/spotify/callback`.

## Add SpotifyDJ In Home Assistant

1. Boot the LilyGO firmware in pairing mode.
2. Enter the 6 digit pair code shown on the LilyGO display.
3. Enter the Spotify Client ID.
4. Enter the HTTPS Home Assistant external URL, preferably the Nabu Casa URL.
5. Home Assistant opens the Spotify authorization website.
6. Approve access in Spotify.
7. Return to Home Assistant and complete the voice/DJ settings step.

The setup flow no longer shows a manual `oauth_result` field.

## Voice And DJ Settings

The config flow and options flow include safe defaults for optional voice fields:

- Assist pipeline ID
- TTS engine
- TTS language
- TTS voice
- DJ style
- Spotify player/source hints
- Liked proxy playlist URI
- Firmware repository/channel/options
- OTA battery safety options

Where Home Assistant exposes choices, SpotifyDJ shows populated dropdowns for Assist pipeline, TTS entity, known TTS voices, Spotify media player, Spotify market, DJ style, and firmware channel. Stored custom values remain selectable so existing setups keep working. Firmware repository settings, firmware channel, max audio bytes, and OTA battery settings are shown only when advanced options are enabled.

Supported DJ styles are:

- `classic_dutch_radio`
- `calm_evening`
- `festival`
- `minimal`

## Home Assistant Entities

SpotifyDJ creates:

- `sensor.spotifydj_status`
- `sensor.spotifydj_last_command`
- `sensor.spotifydj_battery`
- `sensor.spotifydj_wifi_rssi`
- `sensor.spotifydj_firmware_version`
- `sensor.spotifydj_last_track`
- `button.spotifydj_test_dj_voice`
- `update.spotifydj_firmware`

Entity IDs can differ if Home Assistant has renamed the device or entities.

## Services

SpotifyDJ registers these services:

- `spotify_dj.test_parse`
- `spotify_dj.test_tts`
- `spotify_dj.test_command`
- `spotify_dj.start_spotify_oauth`
- `spotify_dj.provision_spotify_credentials`

Use `spotify_dj.provision_spotify_credentials` after OAuth if you want Home Assistant to send the stored Spotify credentials to the paired LilyGO device again.

`spotify_dj.test_parse` and `spotify_dj.test_command` use this flow:

```text
text -> HA Assist conversation pipeline -> SpotifyDJ intent -> Spotify -> DJ response
```

## Home Assistant HTTP Endpoints

The integration exposes these endpoints:

```text
POST /api/spotify_dj/pair
POST /api/spotify_dj/voice
POST /api/spotify_dj/status
POST /api/spotify_dj/event
GET  /api/spotify_dj/spotify/callback
```

The ESP should send status updates to:

```text
POST /api/spotify_dj/status
```

Authenticated device requests use the provisioned bearer token and can include `X-SpotifyDJ-Device-ID`.

## ESP Device Endpoints

Home Assistant expects the firmware to expose:

```text
POST /api/device/ota
POST /api/device/provision_spotify
GET  /api/device/info
```

The integration also uses the device `local_url` from pairing/status, or falls back to `http://<device_id>.local`.

## Firmware OTA Releases

Firmware builds come from the private `spotify-dj-app` repo and are published to the public `spotify-dj-firmware` repo.

Expected release asset name:

```text
spotifydj-lilygo-t-embed-s3-vX.Y.Z.bin
```

Expected manifest:

```text
firmware_manifest.json
```

Example manifest:

```json
{
  "version": "1.5.1",
  "device": "lilygo-t-embed-s3",
  "asset": "spotifydj-lilygo-t-embed-s3-v1.5.1.bin",
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "min_ha_integration": "1.5.1"
}
```

The firmware version is injected through PlatformIO build flags from the Git tag.

## HACS Release Workflow

Update `custom_components/spotify_dj/manifest.json`, `custom_components/spotify_dj/const.py`, and `CHANGELOG.md` before tagging.

```bash
git add .
git commit -m "Release SpotifyDJ v1.5.1"
git tag v1.5.1
git push origin main
git push origin v1.5.1
gh release create v1.5.1 --title "SpotifyDJ v1.5.1" --notes-file CHANGELOG.md
```

Then update the installed integration through HACS/Home Assistant:

1. Open HACS in Home Assistant.
2. Open SpotifyDJ.
3. Choose **Redownload** or refresh HACS update information.
4. Select and install the new release from HACS.
5. Restart Home Assistant.
6. Go to **Settings -> Devices & services**.
7. Add SpotifyDJ again, or remove and re-add the SpotifyDJ integration if needed.
8. Complete pairing and Spotify OAuth in the SpotifyDJ config flow.

## Tests

Run the lightweight unit tests with:

```bash
python3 -m unittest discover -s tests
```

These tests use local stubs for Home Assistant imports and focus on pure SpotifyDJ helpers, OAuth URL building, Assist response mapping, and config-flow translation coverage.

## Troubleshooting

- If Spotify login does not return to Home Assistant, verify the Spotify redirect URI exactly matches the Nabu Casa or external Home Assistant URL.
- If the config flow does not load, restart Home Assistant and check that HACS installed `custom_components/spotify_dj`.
- If OTA cannot start, make sure the device has reported `local_url` or can be reached as `http://<device_id>.local`.
- If OTA is blocked, check battery level, USB power, and the OTA battery options.
- If provisioning fails, pair the LilyGO first and run `spotify_dj.provision_spotify_credentials` again.
- Diagnostics are available from the Home Assistant integration page and redact tokens.
