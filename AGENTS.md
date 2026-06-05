# SpotifyDJ context

Project: SpotifyDJ

Doel:
- SpotifyDJ device als Spotify/HA voice remote.
- HA custom integration heet `spotify_dj`.
- ESP firmware heet SpotifyDJ.
- ESP praat zelfstandig met Spotify API.
- HA doet pairing, Spotify OAuth provisioning, OTA, status, voice/AI integratie.

Belangrijke repos:
- HA integration: github.com/pcvantol/spotify-dj
- ESP firmware source: github.com/pcvantol/spotify-dj-app
- Public firmware releases: github.com/pcvantol/spotify-dj-firmware

Licentie/commercieel:
- HA integration blijft gratis en MIT-licensed via `LICENSE`.
- ESP firmware source blijft closed source tenzij expliciet anders afgesproken.
- Firmware binaries/release assets vallen onder `FIRMWARE-LICENSE.md`.
- Firmware/device copyright: `Copyright (c) 2026 Peter van Tol. All rights reserved.`
- Hardware mag white-label worden ingekocht en als SpotifyDJ device met firmware en gratis HA integration online worden verkocht.
- Wijzigingen aan docs/release-info moeten deze scheiding tussen open HA integration en closed firmware behouden.
- `THIRD_PARTY_NOTICES.md` moet blijven bestaan en Home Assistant APIs, manifest requirements/dependencies en Spotify API/trademark notice noemen.
- Spotify is een trademark van Spotify AB.
- SpotifyDJ mag nergens claimen verbonden te zijn aan, goedgekeurd te zijn door of gesponsord te zijn door Spotify AB.
- README legal sectie moet compact vermelden:
  - firmware proprietary software is;
  - HA integration separaat gratis gedistribueerd mag worden voor SpotifyDJ devices;
  - Spotify trademark/non-affiliation disclaimer;
  - third-party/open-source dependencies hun eigen licenties houden.

HA integration:
- domain: `spotify_dj`
- HACS custom integration.
- Actuele integratieversie: `2.3.0`.
- Config flow moet blijven laden.
- Spotify OAuth gebruikt een HA external step en opent de Spotify website.
- Spotify OAuth gebruikt bij voorkeur Nabu Casa HTTPS external URL.
- Spotify OAuth gebruikt standaard de ingebouwde Spotify Client ID; toon `spotify_client_id` alleen advanced en prefilled voor override.
- Redirect path: `/api/spotify_dj/spotify/callback`
- Geen handmatig `oauth_result` veld tonen.
- Config flow ondersteunt optionele BLE WiFi provisioning vóór normale pairing.
- BLE provisioning schrijft alleen WiFi SSID/password naar het SpotifyDJ device; geen Spotify credentials, MQTT credentials of device tokens via BLE.
- BLE service UUID: `7f705000-9f8f-4f1a-9b5f-570071fd0001`
- BLE WiFi write characteristic: `7f705001-9f8f-4f1a-9b5f-570071fd0001`
- BLE status characteristic: `7f705002-9f8f-4f1a-9b5f-570071fd0001`
- Voice velden moeten defaults hebben.
- Options-flow mag `config_entry` niet assignen; gebruik een eigen attribuut omdat recente Home Assistant versies `config_entry` read-only maken.
- Device UI language wordt tijdens pairing gekozen als `en`/`nl`, default op HA taal indien ondersteund, en meegestuurd als `device_language` en `language`; ESP slaat dit op als `provision.language`.
- Koppelcode uit de HA config-flow moet worden opgeslagen en ESP pairing moet een afwijkende koppelcode weigeren.
- `spotify_player` is verplicht in config-flow/options-flow.
- Gebruik waar veilig HA-populated combo boxes/dropdowns i.p.v. vrije tekst:
  - Assist pipeline uit HA Assist pipelines.
  - TTS engine uit HA `tts` entities.
  - Spotify player uit HA `media_player` entities.
  - Spotify market vaste keuzes.
  - DJ style vaste keuzes.
  - Firmware channel vaste keuzes.
- Verberg firmware repo settings, firmware channel, max audio bytes, min battery for OTA en allow OTA on battery onder HA advanced options.
- Laat velden vrije tekst waar HA geen betrouwbare bron heeft, zoals TTS language/voice, playlist URI en firmware repo/asset/device strings.
- Spotify source/device naam is dynamisch; toon dit niet in de normale flow, alleen advanced als optionele override.
- MQTT broker settings (`mqtt_host`, `mqtt_port`, `mqtt_username`, `mqtt_password`) staan alleen advanced en worden mee geprovisioned naar ESP pair/provision/status payloads indien host is ingevuld.
- `mqtt_host` default is altijd `homeassistant.local`; lees hiervoor niet de HA MQTT/Mosquitto add-on/config uit.
- Bestaande SpotifyDJ MQTT waarden mogen niet overschreven worden door defaults.
- `mqtt_password` nooit loggen en altijd redacteren in diagnostics.
- Diagnostics moeten alle keys met `token`, `password` of `secret` redacteren; log geen volledige ESP event payloads.
- Diagnostics output moet legal metadata bevatten:
  - `copyright`: `Copyright (c) 2026 Peter van Tol. All rights reserved.`
  - `spotify_trademark`: `Spotify is a trademark of Spotify AB.`
  - `affiliation`: `SpotifyDJ is not affiliated with, endorsed by, or sponsored by Spotify AB.`
- Config-flow/options-flow UI moet subtiel en kort de Spotify trademark/non-affiliation notice tonen zonder UX te vervuilen.
- Verberg lokale/manual device URL in de normale flow; toon die alleen onder HA advanced options als mDNS/manual override nodig is.
- Alle SpotifyDJ entities moeten onder één HA device vallen met hetzelfde device identifier.
- Config-flow foutpaden moeten heldere NL/EN gebruikersmeldingen hebben, bijvoorbeeld bij lege of foutieve koppelcode, ontbrekende Spotify Client ID, foutieve external URL en OAuth fouten.
- Bestaande modules niet verwijderen, zoals `wav_util.py`, `pipeline.py`.
- Actieve routes gebruiken HA Assist/TTS en geen directe externe AI/STT/TTS API.
- DJ responses worden niet via Spotify Connect of HA media_player afgespeeld; HA genereert waar mogelijk een tijdelijke PCM WAV `audio_url` en POST `text` + optionele `audio_url` naar ESP endpoint `/api/device/dj_response`.
- ESP firmware doet microfoon-STT via de officiële HA Assist websocket API en stuurt herkende tekst naar `POST /api/spotify_dj/voice` met `X-SpotifyDJ-Text`.
- `POST /api/spotify_dj/voice` accepteert tekstcommands, geen WAV-transcriptie; legacy `audio/wav` uploads krijgen een gecontroleerde JSON foutmelding.

ESP firmware:
- Voeg pairing, mDNS, OTA en Spotify provisioning toe zonder bestaande Spotify/audio/UI code te herschrijven.
- mDNS service: `_spotifydj._tcp`
- Device ID: `spotifydj-XXXXXXXXXXXX`
- NVS namespace: `spotifydj`
- OTA endpoint: `POST /api/device/ota`
- Spotify provisioning endpoint: `POST /api/device/provision_spotify`
- Status endpoint naar HA: `POST /api/spotify_dj/status`
- Voice tekst endpoint naar HA: `POST /api/spotify_dj/voice`

Firmware releases:
- Build vanuit private repo `spotify-dj-app`.
- Publish binaries naar public repo `spotify-dj-firmware`.
- Private firmware repo moet bij voorkeur een eigen `release.sh` one-liner hebben:
  - `./release.sh X.Y.Z`
  - `./release.sh X.Y.Z --dry-run`
  - optioneel `./release.sh X.Y.Z --publish-firmware-repo ../spotify-dj-firmware`
- ESP firmware release-script moet semantic version valideren, firmware metadata bijwerken, PlatformIO build draaien, binary renamen, SHA256 berekenen, `firmware_manifest.json` bijwerken, committen, taggen en pushen.
- Release asset naam:
  `spotifydj-device-vX.Y.Z.bin`
- Manifest:
  `firmware_manifest.json`
- Firmwareversie wordt via PlatformIO build flags uit Git tag geïnjecteerd.
- Public firmware repo mag alleen release binary, `firmware_manifest.json`, release metadata en niet-geheime documentatie bevatten.
- Public firmware repo mag geen firmware source, NVS secrets, device tokens, Spotify refresh tokens of Home Assistant tokens bevatten.

README/release:
- README moet actueel blijven voor HACS installatie, Spotify OAuth, endpoints, OTA en release workflow.
- Release checklist moet in README en AGENTS blijven staan en bij elke release worden gevolgd.
- Pre-release checklist:
  - Controleer dat de working tree alleen bedoelde wijzigingen bevat.
  - Update `custom_components/spotify_dj/manifest.json` naar de target versie.
  - Update `custom_components/spotify_dj/const.py` naar dezelfde target versie.
  - Update `README.md` current version, examples, endpoints en HACS instructies.
  - Update `CHANGELOG.md` als één actuele versie zonder oude versieblokken.
  - Houd `AGENTS.md` gelijk met actuele versie en release-eisen.
  - Controleer `custom_components/spotify_dj/brand/icon.png`, `icon@2x.png` en `logo.png`.
  - Controleer dat `LICENSE` de HA integration dekt en `FIRMWARE-LICENSE.md` firmware binaries dekt.
  - Controleer dat `THIRD_PARTY_NOTICES.md` actueel is voor manifest dependencies/requirements.
  - Controleer README/config-flow/options-flow/diagnostics legal notices.
  - Draai `python3 -m unittest discover -s tests`.
- HACS release workflow bevat minimaal:
  - One-liner mag via `./release.sh X.Y.Z`.
  - `./release.sh X.Y.Z` moet de versie automatisch bijwerken in `manifest.json`, `const.py`, `README.md`, `CHANGELOG.md` en `AGENTS.md` voordat commit/tag gebeurt.
  - Dry-run kan via `./release.sh X.Y.Z --dry-run`.
  - `git add .`
  - `git commit -m "Release SpotifyDJ vX.Y.Z"`
  - `git tag vX.Y.Z`
  - `git push origin main`
  - `git push origin vX.Y.Z`
  - `gh release create vX.Y.Z --title "SpotifyDJ vX.Y.Z" --notes-file CHANGELOG.md`
  - HACS update-info refresh/redownload.
  - Nieuwe release installeren vanuit HACS.
  - Home Assistant restart.
  - SpotifyDJ integration opnieuw toevoegen indien nodig.
  - Options-flow openen en controleren dat er geen internal server error is.
  - Browser/app cache refreshen en controleren dat integration icon/logo verschijnt.
  - `spotify_dj.test_parse`, `spotify_dj.test_command` en `spotify_dj.test_tts` testen.
  - Status, last command, last track en firmware update entities controleren.
- Firmware release cross-check:
  - Build firmware vanuit private repo `spotify-dj-app`.
  - Gebruik bij voorkeur `./release.sh X.Y.Z` in de private firmware repo.
  - Gebruik `./release.sh X.Y.Z --dry-run` bij twijfel voordat gepubliceerd wordt.
  - Publish binaries naar public repo `spotify-dj-firmware`.
  - Release asset naam is `spotifydj-device-vX.Y.Z.bin`.
  - Update `firmware_manifest.json` met `version`, `asset`, `sha256` en `min_ha_integration`.
  - Controleer dat OTA de nieuwe firmware via de HA update entity ontdekt.

Tests:
- Testcode staat onder `tests/`.
- Lichtgewicht tests draaien zonder volledige Home Assistant installatie met:
  `python3 -m unittest discover -s tests`
- Houd tests voor:
  - Spotify OAuth redirect/PKCE URL helpers.
  - Config-flow helper/default gedrag.
  - Vertaalcoverage voor config-flow error keys.
  - Diagnostics redaction en legal metadata.
