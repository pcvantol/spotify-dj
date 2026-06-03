# SpotifyDJ

SpotifyDJ is a Home Assistant custom integration for a LilyGO T-Embed-S3 Spotify/voice remote.

It provides:

- LilyGO pairing with 6 digit code
- device token provisioning
- Spotify OAuth/PKCE provisioning concept
- HA-native voice/AI/TTS configuration surface
- device status endpoints
- GitHub Releases based firmware OTA management
- diagnostics and repair scaffolding

## Installation through HACS

1. Add this repository as a HACS custom repository.
2. Category: `Integration`.
3. Install SpotifyDJ.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration → SpotifyDJ**.

## Pairing flow

1. Boot the LilyGO firmware in pairing mode.
2. The display shows a 6 digit pair code.
3. Add the SpotifyDJ integration in Home Assistant.
4. Enter the pair code.
5. Configure Spotify Client ID and voice/DJ settings.

## Spotify OAuth / PKCE

For a private setup the user creates a Spotify Developer App and enters the Client ID during setup.
PKCE does not require a client secret.

Recommended redirect URI for development:

```text
http://homeassistant.local:8123/api/spotify_dj/spotify/callback
```

The integration is intended to broker the refresh token to the LilyGO so the ESP can keep its existing standalone Spotify API implementation.

## Firmware OTA distribution

Recommended hybrid layout:

- `pcvantol/spotify-dj-app` private firmware source repo
- `pcvantol/spotify-dj-firmware` public release repo with `.bin`, `.sha256` and `firmware_manifest.json`

Home Assistant checks the public firmware repo and instructs the LilyGO to install a concrete firmware URL through its `/api/device/ota` endpoint.

## Device endpoints expected on LilyGO

```text
POST /api/device/ota
POST /api/device/provision_spotify
GET  /api/device/info
```

## Integration endpoints exposed by HA

```text
POST /api/spotify_dj/pair
POST /api/spotify_dj/voice
POST /api/spotify_dj/status
POST /api/spotify_dj/event
GET  /api/spotify_dj/spotify/callback
```

## Release workflow

```bash
git add .
git commit -m "Release SpotifyDJ v1.1.1"
git tag v1.1.1
git push origin main
git push origin v1.1.1
```

Then create a GitHub Release for `v1.1.1`.
