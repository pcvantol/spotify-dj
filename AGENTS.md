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
- Actuele integratieversie: `1.5.0`.
- Config flow moet blijven laden.
- Spotify OAuth gebruikt een HA external step en opent de Spotify website.
- Spotify OAuth gebruikt bij voorkeur Nabu Casa HTTPS external URL.
- Redirect path: `/api/spotify_dj/spotify/callback`
- Geen handmatig `oauth_result` veld tonen.
- Voice velden moeten defaults hebben.
- Gebruik waar veilig HA-populated combo boxes/dropdowns i.p.v. vrije tekst:
  - Assist pipeline uit HA Assist pipelines.
  - TTS engine uit HA `tts` entities.
  - Spotify player uit HA `media_player` entities.
  - Spotify market vaste keuzes.
  - DJ style vaste keuzes.
  - Firmware channel vaste keuzes.
- Verberg firmware repo settings, firmware channel, max audio bytes, min battery for OTA en allow OTA on battery onder HA advanced options.
- Laat velden vrije tekst waar HA geen betrouwbare bron heeft, zoals Spotify source/device naam, TTS language/voice, playlist URI en firmware repo/asset/device strings.
- Config-flow foutpaden moeten heldere NL/EN gebruikersmeldingen hebben, bijvoorbeeld bij lege of foutieve koppelcode, ontbrekende Spotify Client ID, foutieve external URL en OAuth fouten.
- Bestaande modules niet verwijderen, zoals `openai_client.py`, `wav_util.py`, `pipeline.py`.
- Houd `openai_client.py` en legacy voice modules aanwezig als compatibiliteitsstubs, maar actieve routes gebruiken HA Assist/TTS en geen directe OpenAI API.

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

README/release:
- README moet actueel blijven voor HACS installatie, Spotify OAuth, endpoints, OTA en release workflow.
- HACS release workflow bevat minimaal:
  - `git tag vX.Y.Z`
  - `git push origin main`
  - `git push origin vX.Y.Z`
  - `gh release create vX.Y.Z --title "SpotifyDJ vX.Y.Z" --notes-file CHANGELOG.md`
  - HACS update-info refresh/redownload
  - nieuwe release installeren vanuit HACS
  - Home Assistant restart
  - SpotifyDJ integration opnieuw toevoegen indien nodig.

Tests:
- Testcode staat onder `tests/`.
- Lichtgewicht tests draaien zonder volledige Home Assistant installatie met:
  `python3 -m unittest discover -s tests`
- Houd tests voor:
  - Spotify OAuth redirect/PKCE URL helpers.
  - Config-flow helper/default gedrag.
  - Vertaalcoverage voor config-flow error keys.
