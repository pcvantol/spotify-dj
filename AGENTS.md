# DJConnect context

Project: DJConnect

Doel:
- DJConnect device als Spotify/HA voice remote.
- HA custom integration heet `djconnect`.
- ESP firmware heet DJConnect.
- ESP stuurt generieke playback commands naar Home Assistant en bewaart geen playback-backend credentials.
- HA doet pairing, Spotify OAuth/backend playback, OTA, status, voice/AI integratie.

Belangrijke repos:
- HA integration: github.com/pcvantol/djconnect
- ESP firmware source: github.com/pcvantol/djconnect-app
- Public firmware releases: github.com/pcvantol/djconnect-firmware

Architectuur beslissingen:
- HA integration orchestreert pairing, OAuth, backend playback, OTA, status en Assist/TTS; ESP firmware blijft eigenaar van device runtime/audio/UI.
- Huidige firmware gebruikt de lokale ESP API met bearer token voor device-acties.
- Pairing/status gebruikt canoniek `client_type` om client runtimes te onderscheiden; huidige waarden zijn `esp32`, `ios` en `macos`. ESP/LilyGO firmware moet verplicht `client_type: "esp32"` meesturen op JSON payloads.
- Backend playback loopt via de HA integration en wordt user-facing aangeboden als optionele/native `media_player` proxy; device-instellingen lopen via `POST /api/device/command`.
- ESP backend playback commands naar `POST /api/djconnect/command` gebruiken losse `set_shuffle` boolean en `set_repeat` met `off`/`track`/`context`; gebruik geen gecombineerde `set_play_mode` flow.
- HA integration en ESP firmware moeten dezelfde `major.minor` protocolversie hebben: HA `3.0.z` praat alleen met ESP `3.0.z`, HA `3.1.z` alleen met ESP `3.1.z`; patchversies mogen verschillen.
- Bij major/minor mismatch retourneert HA HTTP `426` met `error: version_mismatch` en HA/firmware metadata; dit is geen pairing-token failure en mag pairing/token niet wissen.
- ESP uploadt raw WAV audio naar `POST /api/djconnect/voice`; de HA integration doet Assist/STT intern via HA `stt.async_get_speech_to_text_engine(...).async_process_audio_stream` met eerst `stt_engine` uit options, daarna opgeslagen Assist pipeline, HA preferred/default pipeline, eerste pipeline met STT, eerste HA `stt.*` entity of als laatste HA `assist_pipeline.async_pipeline_from_audio_stream`, en geeft tekst plus optionele WAV/MP3 `audio_url` terug.
- Actieve HA routes gebruiken geen directe externe AI/STT/TTS APIs; gebruik HA Assist en HA TTS.
- DJ responses spelen op het DJConnect device af, niet via Spotify Connect of HA media_player; HA post `text` plus optionele tijdelijke WAV/MP3 `audio_url` naar `/api/device/dj_response`.
- Fallback DJ responses bij command/playback fouten moeten de gekozen `device_language` volgen (`en`/`nl`).
- Spotify OAuth loopt via HA external step met PKCE; geen handmatig `oauth_result` veld.
- Spotify OAuth refresh tokens kunnen roteren; bewaar nieuwe refresh tokens direct persistent en gebruik credentials alleen HA-intern voor backend playback.
- Spotify access tokens zijn kortlevend; cache ze HA-intern tot vlak voor expiry, refresh on demand en retry één keer bij Spotify API `401` voordat je een refresh-token repair overweegt.
- Als ESP `/api/djconnect/status` `spotify_configured=false` meldt, behandel dit alleen als compat/statushint voor backend playback; stuur geen Spotify OAuth credentials naar ESP.
- BLE provisioning doet alleen WiFi SSID/password; geen Spotify credentials, device tokens of andere secrets via BLE.
- Runtime discovery prefereert device-reported `local_url`, exacte `_djconnect._tcp` mDNS matches en daarna alleen een enkele zichtbare DJConnect mDNS service; genereer alleen `http://djconnect-lilygo-[device-suffix].local` voor echte device IDs met 12-hex suffix, inclusief `djconnect-lilygo-XXXXXXXXXXXX`, nooit voor 6-cijferige setupcodes.
- Normale config-flow blijft klein; operationele overrides zoals firmware repo/channel, Spotify source, max audio bytes en OTA battery settings blijven advanced.
- Alle entities horen onder één HA device met één stabiele device identifier.
- Firmware source blijft proprietary; HA integration blijft gratis MIT-licensed.
- Geen secrets in diagnostics/logs; redactie voor keys met `token`, `password` of `secret`.
- Spotify trademark/non-affiliation notice blijft zichtbaar in docs/UI/diagnostics.

Licentie/commercieel:
- HA integration blijft gratis en MIT-licensed via `LICENSE`.
- ESP firmware source blijft closed source tenzij expliciet anders afgesproken.
- Firmware binaries/release assets vallen onder `FIRMWARE-LICENSE.md`.
- Firmware/device copyright: `Copyright (c) 2026 Peter van Tol. All rights reserved.`
- Hardware mag white-label worden ingekocht en als DJConnect device met firmware en gratis HA integration online worden verkocht.
- Wijzigingen aan docs/release-info moeten deze scheiding tussen open HA integration en closed firmware behouden.
- `THIRD_PARTY_NOTICES.md` moet blijven bestaan en Home Assistant APIs, manifest requirements/dependencies en Spotify API/trademark notice noemen.
- Spotify is een trademark van Spotify AB.
- DJConnect mag nergens claimen verbonden te zijn aan, goedgekeurd te zijn door of gesponsord te zijn door Spotify AB.
- README legal sectie moet compact vermelden:
  - firmware proprietary software is;
  - HA integration separaat gratis gedistribueerd mag worden voor DJConnect devices;
  - Spotify trademark/non-affiliation disclaimer;
  - third-party/open-source dependencies hun eigen licenties houden.

HA integration:
- domain: `djconnect`
- HACS custom integration.
- Actuele integratieversie: `3.0.25`.
- Config flow moet blijven laden.
- Spotify OAuth gebruikt een HA external step en opent de Spotify website.
- Spotify OAuth gebruikt bij voorkeur Nabu Casa HTTPS external URL.
- Spotify OAuth gebruikt standaard de ingebouwde Spotify Client ID; toon `spotify_client_id` alleen advanced en prefilled voor override.
- Spotify OAuth stap moet `ha_external_url` automatisch prefilling uit HA external URL/Nabu Casa waar beschikbaar, maar handmatige correctie toestaan.
- Spotify OAuth scopes moeten `playlist-read-private` bevatten zodat ESP private/eigen `DJConnect Liked Proxy` playlists via `/me/playlists` kan vinden.
- Oude config entries zonder `playlist-read-private` moeten via diagnostics/repairs duidelijke reauthorize instructies krijgen.
- Nieuwe Spotify refresh tokens uit OAuth callbacks moeten `CONF_SPOTIFY_REFRESH_TOKEN` persistent overschrijven en in runtime als latest token beschikbaar zijn.
- Pair/status responses mogen nooit Spotify OAuth secrets bevatten; gebruik latest refresh token alleen HA-intern.
- Spotify `invalid_grant` / revoked refresh tokens moeten als gebruikersvriendelijke reauthorize melding en native HA Repairs Fix-flow zichtbaar worden; de Fix-flow opent Spotify OAuth, slaat de nieuwe refresh token op en verwijdert de repair issue. Toon geen ruwe token-response en log nooit de refresh token.
- Options-flow moet ook een expliciete `Spotify opnieuw autoriseren` actie hebben die dezelfde OAuth callback gebruikt.
- Redirect path: `/api/djconnect/spotify/callback`
- Geen handmatig `oauth_result` veld tonen.
- Config flow ondersteunt optionele BLE WiFi provisioning vóór normale pairing.
- BLE config-flow gebruikt één exclusieve actie-keuze: WiFi via Bluetooth schrijven, Bluetooth devices opnieuw scannen of doorgaan naar koppelen als captive-portal WiFi al klaar is.
- BLE provisioning schrijft alleen WiFi SSID/password naar het DJConnect device; geen Spotify credentials, device tokens of andere secrets via BLE.
- BLE service UUID: `7f705000-9f8f-4f1a-9b5f-570071fd0001`
- BLE WiFi write characteristic: `7f705001-9f8f-4f1a-9b5f-570071fd0001`
- BLE status characteristic: `7f705002-9f8f-4f1a-9b5f-570071fd0001`
- Voice velden moeten defaults hebben.
- Options-flow mag `config_entry` niet assignen; gebruik een eigen attribuut omdat recente Home Assistant versies `config_entry` read-only maken.
- Options-flow bevat aparte acties voor instellingen opslaan, pairing opnieuw proberen met de huidige code, en volledig opnieuw koppelen met een nieuwe koppelcode; re-pair maakt een nieuw device token, bewaart dat persistent en probeert `/api/device/pair` opnieuw.
- `POST /api/device/pair` mag alleen bij initiële config-flow pairing, expliciete re-pair/token rotation of stale-pairing recovery worden aangeroepen; nooit bij normale status sync, playback commands, settings sync of HA startup als er al een device token is opgeslagen.
- Setup-code based pairing mag tijdelijk `djconnect-[6-cijferige-code]` gebruiken, maar HA moet na de eerste ESP status/command/voice call met dezelfde bearer token alleen de echte `djconnect-lilygo-XXXXXXXXXXXX` device-id accepteren, leren en persistent opslaan.
- Device UI language wordt tijdens pairing gekozen als `en`/`nl`, default op HA taal indien ondersteund, en meegestuurd als `device_language` en `language`; ESP slaat dit op als `provision.language`.
- HA stuurt tijdens pairing `client_type` mee en bewaart dit persistent; ESP firmware gebruikt `esp32`, toekomstige iOS/macOS app-clients gebruiken respectievelijk `ios` of `macos`.
- Koppelcode/device-suffix uit de HA config-flow moet worden opgeslagen en ESP pairing moet een afwijkende code weigeren.
- HA pairingstatus mag pas `paired` tonen nadat ESP `ha_pairing_status=paired` bevestigt; een lokaal HA `device_token` is hooguit `pending`.
- `spotify_player` is niet meer nodig; backend playback loopt via de HA playback proxy en ESP device-instellingen via de lokale ESP command API.
- Gebruik waar veilig HA-populated combo boxes/dropdowns i.p.v. vrije tekst:
  - Assist pipeline uit HA Assist pipelines.
  - TTS engine uit HA `tts` entities.
  - Spotify market vaste keuzes.
  - DJ style vaste keuzes.
  - Firmware channel vaste keuzes.
- Verberg firmware repo settings, firmware channel, max audio bytes, min battery for OTA en allow OTA on battery achter een integration-local advanced checkbox; gebruik niet HA's deprecated `show_advanced_options` property.
- Laat velden vrije tekst waar HA geen betrouwbare bron heeft, zoals TTS language/voice, playlist URI en firmware repo/asset/device strings.
- Als TTS engine wijzigt en de opgeslagen TTS voice niet door de nieuwe engine wordt ondersteund, wis `tts_voice` naar `Default` zodat HA TTS geen provider-specifieke oude stem blijft gebruiken.
- Spotify source/device naam is dynamisch; toon dit niet in de normale flow, alleen advanced als optionele override.
- Huidige firmware gebruikt de lokale ESP API met bearer token voor device-acties.
- Diagnostics moeten alle keys met `token`, `password` of `secret` redacteren; log geen volledige ESP event payloads.
- Diagnostics output moet legal metadata bevatten:
  - `copyright`: `Copyright (c) 2026 Peter van Tol. All rights reserved.`
  - `spotify_trademark`: `Spotify is a trademark of Spotify AB.`
  - `affiliation`: `DJConnect is not affiliated with, endorsed by, or sponsored by Spotify AB.`
- Config-flow/options-flow UI moet subtiel en kort de Spotify trademark/non-affiliation notice tonen zonder UX te vervuilen.
- Verberg lokale/manual device URL in de normale flow; toon die alleen onder HA advanced options als mDNS/manual override nodig is.
- Als manual device URL leeg is tijdens setup, sla alleen automatisch `http://djconnect-lilygo-[device-suffix].local` op als de pairingwaarde een echte 12-hex device suffix is; runtime blijft device-reported `local_url` en `_djconnect._tcp` mDNS prefereren en negeert oude `djconnect-[6-digit-code].local` fallbacks.
- Alle DJConnect entities moeten onder één HA device vallen met hetzelfde device identifier.
- ESP status payloads naar HA moeten actuele device settings meesturen voor native entities, zoals screen_brightness_percent/screen_brightness, speaker_volume_percent/speaker_volume, screen_off_timeout_ms, turn_off_after/turn_off_after_ms, nested `settings`, `screen` en `led`; HA accepteert aliases en converteert milliseconden naar seconden/minuten.
- `number.djconnect_volume` mag onbekende devicewaarden zoals `-1` nooit publiceren; geef dan `None/unavailable` terug binnen HA range 0–60.
- Config-flow foutpaden moeten heldere NL/EN gebruikersmeldingen hebben, bijvoorbeeld bij lege of foutieve koppelcode/device-suffix, ontbrekende Spotify Client ID, foutieve external URL en OAuth fouten.
- Bestaande modules niet verwijderen, zoals `wav_util.py`, `pipeline.py`.
- Actieve routes gebruiken HA Assist/TTS en geen directe externe AI/STT/TTS API.
- Voice STT mag niet afhankelijk zijn van niet-beschikbare/private Assist audio pipeline helpers; gebruik HA's ondersteunde STT helper en geef `No STT provider configured. Checked options keys: ...` terug als er geen STT provider is.
- `stt_engine` is de officiële DJConnect options-flow key voor fysieke PTT STT provider selectie; gebruik deze vóór Assist pipeline lookup. Log alleen keys/provider-id metadata, nooit API keys/tokens/audio URL tokens.
- `stt_engine` moet zichtbaar blijven in normale config/options-flow; gebruik HA-populated dropdown als `stt.*` entities beschikbaar zijn en anders vrije tekst zodat `stt.openai_stt` handmatig ingevuld kan worden.
- Als `assist_pipeline_id` leeg is, gebruik HA preferred/default Assist pipeline; als opgeslagen pipeline ontbreekt, fallback naar preferred/default of eerste pipeline met STT. Geef alleen no-provider terug als de geselecteerde pipeline echt geen STT engine/provider heeft.
- DJ responses worden niet via Spotify Connect of HA media_player afgespeeld; HA genereert waar mogelijk een tijdelijke WAV/MP3 `audio_url` en POST `text` + optionele `audio_url` naar ESP endpoint `/api/device/dj_response`.
- Als HA TTS WAV of MP3 audio teruggeeft, mag HA een tijdelijke `audio_url` meesturen; ESP bepaalt wav/mp3/unknown. Alleen onbekende audio wordt text-only zonder warning.
- ESP firmware stuurt microfoon-WAV naar `POST /api/djconnect/voice` met `Authorization: Bearer <device_token>` en `X-DJConnect-Device-ID`.
- `POST /api/djconnect/voice` accepteert raw WAV uploads voor backend HA Assist/STT en blijft tekstcommands ondersteunen voor developer tests.
- Text-only/JSON requests naar `/api/djconnect/voice` zijn DJ-response tests en mogen geen Spotify command parsing/playback uitvoeren; raw WAV PTT requests blijven wel STT + command parser + Spotify playback gebruiken.
- De HA Assist tekstprompt voor DJConnect moet vragen om, waar mogelijk, één kort leuk feitje over de artiest en/of het nummer in de DJ announcement.

ESP firmware:
- Voeg pairing, mDNS, OTA en Spotify provisioning toe zonder bestaande Spotify/audio/UI code te herschrijven.
- mDNS service: `_djconnect._tcp`
- Device ID: `djconnect-lilygo-XXXXXXXXXXXX`; accepteer geen legacy `djconnect-XXXXXXXXXXXX` device IDs.
- NVS namespace: `djconnect`
- OTA endpoint: `POST /api/device/ota`
- ESP device command endpoint voor device-instellingen: `POST /api/device/command`
- ESP naar HA backend command endpoint: `POST /api/djconnect/command`
- Device info endpoint: `GET /api/device/info`
- Status endpoint naar HA: `POST /api/djconnect/status`
- Voice tekst endpoint naar HA: `POST /api/djconnect/voice`
- ESP moet `firmware` bij status meesturen en HTTP `426` `version_mismatch` van HA behandelen als update-required/protocolblokkade zonder NVS pairing/token te wissen.

Firmware releases:
- Build vanuit private repo `djconnect-app`.
- Publish binaries naar public repo `djconnect-firmware`.
- Private firmware repo moet bij voorkeur een eigen `release.sh` one-liner hebben:
  - `./release.sh X.Y.Z`
  - `./release.sh X.Y.Z --dry-run`
  - optioneel `./release.sh X.Y.Z --publish-firmware-repo ../djconnect-firmware`
- ESP firmware release-script moet semantic version valideren, firmware metadata bijwerken, PlatformIO build draaien, binary renamen, SHA256 berekenen, `firmware_manifest.json` bijwerken, committen, taggen en pushen.
- Release asset naam:
  `djconnect-device-vX.Y.Z.bin`
- Manifest:
  `firmware_manifest.json`
- Firmware assetnaam is de publieke distributienaam; manifest `device` is het OTA target-device dat HA ongewijzigd naar `POST /api/device/ota` stuurt.
- Voor de huidige firmware is manifest `device` `lilygo-t-embed-s3`; stuur niet de generieke assetprefix `djconnect-device` als OTA target.
- Firmwareversie wordt via PlatformIO build flags uit Git tag geïnjecteerd.
- Public firmware repo mag alleen release binary, `firmware_manifest.json`, release metadata en niet-geheime documentatie bevatten.
- Public firmware repo mag geen firmware source, NVS secrets, device tokens, Spotify refresh tokens of Home Assistant tokens bevatten.

README/release:
- README moet actueel blijven voor HACS installatie, Spotify OAuth, endpoints, OTA en release workflow.
- `website/index.html` is de statische product/marketing onepager voor pre-flashed DJConnect devices; houd quick start, randvoorwaarden, local-API verhaal en legal/trademark tekst actueel.
- Release checklist moet in README en AGENTS blijven staan en bij elke release worden gevolgd.
- Pre-release checklist:
  - Controleer dat de working tree alleen bedoelde wijzigingen bevat.
  - Update `custom_components/djconnect/manifest.json` naar de target versie.
  - Update `custom_components/djconnect/const.py` naar dezelfde target versie.
  - Update `README.md` current version, examples, endpoints en HACS instructies.
  - Update `website/index.html` als out-of-the-box setup, requirements, verkoopverhaal of legal wording wijzigt.
  - Update `CHANGELOG.md` als één actuele versie zonder oude versieblokken.
  - Houd `AGENTS.md` gelijk met actuele versie en release-eisen.
  - Controleer `custom_components/djconnect/brand/icon.png`, `icon@2x.png` en `logo.png`.
  - Controleer dat `LICENSE` de HA integration dekt en `FIRMWARE-LICENSE.md` firmware binaries dekt.
  - Controleer dat `THIRD_PARTY_NOTICES.md` actueel is voor manifest dependencies/requirements.
  - Controleer README/config-flow/options-flow/diagnostics legal notices.
  - Draai `python3 -m unittest discover -s tests`.
- HACS release workflow bevat minimaal:
  - One-liner mag via `./release.sh X.Y.Z`.
  - `./release.sh X.Y.Z` moet de versie automatisch bijwerken in `manifest.json`, `const.py`, `README.md`, `CHANGELOG.md` en `AGENTS.md` voordat commit/tag gebeurt.
  - Dry-run kan via `./release.sh X.Y.Z --dry-run`.
  - `git add .`
  - `git commit -m "Release DJConnect vX.Y.Z"`
  - `git tag vX.Y.Z`
  - `git push origin main`
  - `git push origin vX.Y.Z`
  - `gh release create vX.Y.Z --title "DJConnect vX.Y.Z" --notes-file CHANGELOG.md`
  - Optioneel oude semver releases/tags opruimen met `./cleanup_old_releases.sh --keep 1 --execute`.
  - HACS update-info refresh/redownload.
  - Nieuwe release installeren vanuit HACS.
  - Home Assistant restart.
  - DJConnect integration opnieuw toevoegen indien nodig.
  - Options-flow openen en controleren dat er geen internal server error is.
  - Browser/app cache refreshen en controleren dat integration icon/logo verschijnt.
  - `djconnect.test_parse`, `djconnect.test_command` en `djconnect.test_tts` testen.
  - Status, last command, last track en firmware update entities controleren.
- Firmware release cross-check:
  - Build firmware vanuit private repo `djconnect-app`.
  - Gebruik bij voorkeur `./release.sh X.Y.Z` in de private firmware repo.
  - Gebruik `./release.sh X.Y.Z --dry-run` bij twijfel voordat gepubliceerd wordt.
  - Publish binaries naar public repo `djconnect-firmware`.
  - Release asset naam is `djconnect-device-vX.Y.Z.bin`.
  - Update `firmware_manifest.json` met `version`, `device`, `asset`, `sha256`, `size` en `min_ha_integration`.
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
  - HA/ESP `major.minor` version mismatch geeft HTTP 426 `version_mismatch` en houdt pairing intact.
