# SpotifyDJ context

Project: SpotifyDJ

Doel:
- LilyGO T-Embed S3 / CC1101 Plus als Spotify/HA voice remote.
- HA custom integration heet `spotify_dj`.
- ESP firmware heet SpotifyDJ.
- ESP praat zelfstandig met Spotify API.
- HA doet pairing, Spotify OAuth provisioning, OTA, status, voice/AI integratie.

Belangrijke repos:
- HA integration: github.com/pcvantol/spotify-dj
- ESP firmware source: github.com/pcvantol/spotify-dj-app
- Public firmware releases: github.com/pcvantol/spotify-dj-firmware

HA integration:
- domain: `spotify_dj`
- HACS custom integration.
- Config flow moet blijven laden.
- Spotify OAuth gebruikt Nabu Casa external URL.
- Redirect path: `/api/spotify_dj/spotify/callback`
- Geen handmatig `oauth_result` veld tonen.
- Voice velden moeten defaults hebben.
- Bestaande modules niet verwijderen, zoals `openai_client.py`, `wav_util.py`, `pipeline.py`.

ESP firmware:
- Voeg pairing, mDNS, OTA en Spotify provisioning toe zonder bestaande Spotify/audio/UI code te herschrijven.
- mDNS service: `_spotifydj._tcp`
- Device ID: `spotifydj-XXXXXXXXXXXX`
- NVS namespace: `spotifydj`
- OTA endpoint: `POST /api/device/ota`
- Spotify provisioning endpoint: `POST /api/device/provision_spotify`
- Status endpoint naar HA: `POST /api/spotify_dj/status`

Firmware releases:
- Build vanuit private repo `spotify-dj-app`.
- Publish binaries naar public repo `spotify-dj-firmware`.
- Release asset naam:
  `spotifydj-lilygo-t-embed-s3-vX.Y.Z.bin`
- Manifest:
  `firmware_manifest.json`
- Firmwareversie wordt via PlatformIO build flags uit Git tag geïnjecteerd.