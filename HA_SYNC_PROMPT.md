# Codex Prompt: Synchronize Home Assistant Integration With DJConnect ESP Firmware

Werk in de bestaande Home Assistant custom integration repo `pcvantol/djconnect`.

## Doel

Synchroniseer de Home Assistant integration met de actuele DJConnect ESP firmware contracten voor release `v3.1.0`.

## 0. Repository / Release Hygiene

- HA integration repo: `pcvantol/djconnect`.
- ESP source repo: `pcvantol/djconnect-app`.
- Public OTA firmware repo: `pcvantol/djconnect-firmware`.
- Firmware binaries/manifests must be consumed from `djconnect-firmware`; the ESP source repo is not the OTA asset host.
- Current HA integration release/tag baseline is `v3.1.0`; do not reference old 2.x firmware assets or tags.
- Current firmware assets are device-specific, e.g. `djconnect-lilygo-t-embed-s3-vX.Y.Z.bin` and `djconnect-esp32-s3-box-3-vX.Y.Z.bin`.
- Current OTA manifest filename is `firmware_manifest.json`.
- Current OTA manifest uses `firmwares[]` entries; HA selects the matching entry and sends that entry's `device` target to ESP.

Belangrijke architectuur:

- ESP is geen Spotify Connect speaker/player.
- ESP bewaart geen backend OAuth/client_id/refresh_token of playback credentials.
- ESP doet geen directe Spotify Web API calls.
- ESP stuurt generieke playback commands naar Home Assistant.
- Home Assistant is trusted backend voor playback, credentials, Assist/STT/TTS, OTA, native entities en optionele `media_player`.
- ESP speaker is alleen voor local cues en DJ/voice response audio.
- Spotify OAuth credentials blijven HA-intern en worden nooit naar ESP gestuurd.

## 1. Pairing Contract

Controleer pairing flow:

- Integration domain: `djconnect`.
- ESP device ID format: `djconnect-lilygo-XXXXXXXXXXXX`.
- Accepteer geen legacy `djconnect-XXXXXXXXXXXX` device IDs.
- ESP mDNS service: `_djconnect._tcp`.
- ESP local pairing/info endpoints:
  - `GET /api/device/info`
  - `GET /api/device/pairing-info`
  - `POST /api/device/pair`

Belangrijk:

- HA mag een lokaal `device_token` voorbereiden, maar moet pairingstatus niet als `paired` rapporteren totdat de ESP tokenopslag bevestigt.
- Een aangemaakte HA config entry, device registry entry of set entities betekent nog niet dat de ESP gepaired is. Als het ESP display na de HA flow nog de pairing code toont, is HA pairing hooguit `pending`.
- Bij een 6-cijferige setupcode kent HA de echte ESP device-id nog niet. Resolve eerst de ESP URL via manual URL, `_djconnect._tcp` mDNS of single visible DJConnect mDNS service, roep daarna `GET /api/device/pairing-info` aan, verifieer dat `pair_code` overeenkomt en leer de echte `djconnect-lilygo-XXXXXXXXXXXX` `device_id`.
- Gebruik de echte `device_id` uit `/api/device/pairing-info` in de daaropvolgende `POST /api/device/pair`. Stuur nooit een tijdelijke `djconnect-<6-cijferige-code>` als `device_id` naar de ESP.
- Als `/api/device/pairing-info` niet bereikbaar is of de code niet matcht, rond de config flow niet af als succesvol gepaired; toon/retry als pending/recoverable pairing failure.
- `POST /api/device/pair` naar ESP moet `device_token` plus `ha_local_url` en/of `ha_remote_url` sturen.
- `ha_local_url` is de LAN URL die ESP eerst probeert, bijvoorbeeld `http://192.168.1.x:8123` of als laatste fallback `http://homeassistant.local:8123`.
- `ha_local_url` mag nooit een `*.ui.nabu.casa` cloud URL zijn.
- `ha_remote_url` is de optionele Nabu Casa/cloud URL die ESP gebruikt als local niet bereikbaar is.
- `ha_remote_url` mag wel een Nabu Casa/cloud URL zijn en mag niet als primair local pad gebruikt worden.
- Pairing zonder `ha_local_url` en zonder `ha_remote_url` moet als configuratiefout worden behandeld.
- Stuur geen legacy `ha_url` pairingveld.
- Treat ESP pairing as `pending` totdat een authenticated ESP status/command/voice post naar HA succesvol verwerkt is met dezelfde bearer token.
- Als HA 401/403/404 teruggeeft op ESP status/command/voice, pairing is stale/invalid.
- Als playback backend tijdelijk niet beschikbaar is, dat is geen pairing failure.

Expected HA -> ESP pair payload:

Expected ESP pairing-info response before direct pairing:

```json
{
  "device_id": "djconnect-lilygo-XXXXXXXXXXXX",
  "device_name": "DJConnect",
  "pair_code": "123456",
  "firmware": "3.0.27",
  "local_url": "http://djconnect-lilygo-XXXXXXXXXXXX.local"
}
```

```json
{
  "pair_code": "123456",
  "device_id": "djconnect-lilygo-XXXXXXXXXXXX",
  "device_name": "DJConnect",
  "device_language": "nl",
  "language": "nl",
  "device_token": "<device-token>",
  "ha_local_url": "http://homeassistant.local:8123",
  "ha_remote_url": "https://example.ui.nabu.casa",
  "assist_pipeline_id": "..."
}
```

## 2. HA Status Endpoint

ESP post periodiek en bij boot:

```http
POST /api/djconnect/status
Authorization: Bearer <device_token>
X-DJConnect-Device-ID: djconnect-lilygo-XXXXXXXXXXXX
Content-Type: application/json
```

Payload bevat onder andere:

- `device_id`
- `client_type` met waarde `esp32` voor ESP/LilyGO clients
- `firmware`
- `ha_pairing_status`
- `playback_configured`
- `battery` / `battery_percent`
- `wifi_rssi`
- `language`
- `theme`
- `log_level`
- brightness/timeouts/speaker volume
- nested `settings`, `screen` en `led`
- `ota_state` / `update_state`

Taken:

- Parse both top-level fields and nested `settings`, `screen`, `led`.
- Update native HA entities from these status fields.
- Convert millisecond timeout fields naar HA seconden/minuten waar nodig.
- Publish invalid unknown device values zoals volume `-1` als unavailable/`None`, niet als out-of-range HA state.
- OTA/update entity moet `ota_state/update_state=idle` plus firmware version verwerken om `updating` te clearen na reboot.
- Status payloads mogen nooit secrets loggen of in diagnostics tonen.
- ESP JSON routes moeten `client_type` verplicht valideren; ontbrekend of onbekend `client_type` geeft een zichtbare contractfout, geen stille fallback.
- Huidige waarden zijn `esp32`, `ios` en `macos`; ESP/LilyGO firmware gebruikt verplicht `esp32`.
- HA en ESP firmware moeten dezelfde `major.minor` protocolversie gebruiken.
- Patchversies mogen verschillen: HA `3.0.x` accepteert ESP `3.0.y`, maar niet ESP `3.1.y` of `2.9.y`.
- Als de ESP `firmware` major/minor niet matcht met de HA integration versie, retourneer HTTP `426` met `error:"version_mismatch"` en velden `ha_version`, `ha_major_minor`, `firmware`, `firmware_major_minor`.
- `version_mismatch` is geen pairing-token failure; wis pairing/token niet.

## 3. Playback Command Proxy

ESP stuurt playback commands naar:

```http
POST /api/djconnect/command
Authorization: Bearer <device_token>
X-DJConnect-Device-ID: djconnect-lilygo-XXXXXXXXXXXX
Content-Type: application/json
```

Commands:

- `status`
- `devices`
- `queue`
- `playlists`
- `pause`
- `play`
- `next`
- `previous`
- `set_volume`
- `set_output`
- `start_liked_proxy`
- `start_playlist`
- `set_shuffle`
- `set_repeat`

Response contract:

- Auth/pairing failure: HTTP 401/403/404.
- Version/protocol mismatch: HTTP 426 met `success:false`, `error:"version_mismatch"` en HA/firmware major.minor metadata.
- Playback/backend unavailable: HTTP 200 met `success:false`, `backend_available:false`.
- Nooit HTTP 503 voor normale backend unavailable.
- `command=status` moet direct na ESP boot snel kunnen antwoorden.
- Gebruik geen gecombineerde `set_play_mode`; gebruik `set_shuffle` boolean en `set_repeat` met `off`/`track`/`context`.
- `/api/djconnect/command` is geen authoritative device-status bron en mag geen sensorwaarden resetten of vervangen door lege/unknown snapshots.

## 4. Local ESP Device Command API

HA stuurt device settings naar:

```http
POST /api/device/command
Authorization: Bearer <device_token>
Content-Type: application/json
```

Canonical commands:

```json
{"command":"status"}
{"command":"screen_brightness","value":75}
{"command":"screen_dim_timeout","value":60000}
{"command":"turn_off_after","value":300000}
{"command":"speaker_volume","value":50}
{"command":"language","value":"nl"}
{"command":"theme","value":"dark"}
{"command":"log_level","value":"info"}
{"command":"dj_response","text":"Daar gaan we.","audio_url":"http://homeassistant.local:8123/api/djconnect/tts/example.mp3"}
```

Rules:

- Gebruik de lokale ESP API met bearer token.
- Roep `POST /api/device/pair` niet aan voor normale status sync, playback commands, settings sync of HA startup als er al een device token is opgeslagen.
- Re-pair/token rotation mag alleen via expliciete re-pair, initiële pairing of stale-pairing recovery.

## 5. PTT / DJ Response

Flow:

```text
ESP records WAV
-> POST /api/djconnect/voice raw audio/wav
-> HA does STT/backend command parsing/TTS
-> HA returns DJ text plus optional audio URL
-> ESP displays text and plays WAV/MP3 locally
```

Rules:

- Geen HA long-lived token op ESP.
- Geen directe ESP Assist WebSocket auth.
- `audio_url` mag WAV of MP3 zijn.
- ESP speaker is alleen voor cues en DJ response audio.
- Text-only/JSON requests naar `/api/djconnect/voice` zijn DJ-response developer tests en mogen geen Spotify command parsing/playback uitvoeren.
- Raw WAV PTT requests blijven wel STT + command parser + backend playback gebruiken.
- HA gebruikt `stt_engine` option eerst, daarna Assist pipeline fallback.
- De config/options flow gebruikt één vrije `dj_response_prompt` voor de gesproken response op het device.
- Verwijder oude vaste DJ style/profile opties volledig; geen backwards compatibility voor `dj_style` of `dj_profile`.
- Gebruik `dj_response_prompt` alleen voor de DJ response na Spotify-resolutie/playback, niet in de command-parser prompt.
- De command-parser prompt mag prompttekst zoals "Noem waar mogelijk..." nooit meegeven aan Spotify search of Assist device control.
- Free-text PTT/search requests zoeken standaard alleen Spotify-artiesten. Gebruik Spotify Search `type=artist` voor opdrachten zoals "ik wil Pearl Jam starten" of "Metallica"; broad track/album search alleen bij expliciete toekomstige contractuitbreiding.
- Na succesvolle Spotify resolve/playback genereert HA de DJ response op basis van resolved metadata (`artist`, context, playback/current item, artwork waar beschikbaar) plus `dj_response_prompt`.

## 6. Optional HA Media Player Entity

Als een `media_player` entity bestaat:

- Represents backend playback state, niet de ESP speaker.
- Commands: play/pause, next/previous, volume, source/output, playlist/media start.
- Backend credentials blijven in Home Assistant.
- ESP device settings blijven via `POST /api/device/command` lopen.

## 7. OTA / Firmware Release Consumption

Controleer:

- HA leest firmware releases uit `pcvantol/djconnect-firmware`.
- Options-flow laat gebruikers wisselen tussen firmwarekanaal `stable` en `beta`.
- `stable` gebruikt GitHub `/releases/latest`; `beta` gebruikt de nieuwste prerelease uit `/releases?per_page=20`.
- Firmware repo en OTA target device blijven geen normale user-facing instellingen.
- Release assets are device-specific, such as `djconnect-lilygo-t-embed-s3-vX.Y.Z.bin` and `djconnect-esp32-s3-box-3-vX.Y.Z.bin`.
- Manifest is `firmware_manifest.json`.
- Manifest bevat manifest-level `version`, `version_tag`, `channel`, `min_ha_integration` en `firmwares[]`.
- Elke `firmwares[]` entry bevat minimaal `device`, `asset`, `url`, `sha256` en `size`.
- HA kiest de entry op basis van ESP status/info model/board/device en stuurt die entry's `device` ongewijzigd naar ESP `POST /api/device/ota`.
- LilyGO gebruikt manifest device `lilygo-t-embed-s3`; ESP32-S3-BOX-3 gebruikt manifest device `esp32-s3-box-3`.
- Gebruik geen generieke assetprefix als OTA target device.

OTA payload naar ESP:

```json
{
  "version": "3.1.0",
  "url": "https://github.com/pcvantol/djconnect-firmware/releases/download/v3.1.0/djconnect-lilygo-t-embed-s3-v3.1.0.bin",
  "sha256": "...",
  "device": "lilygo-t-embed-s3",
  "asset": "djconnect-lilygo-t-embed-s3-v3.1.0.bin"
}
```

## 8. Tests To Add / Update

- Pairing pending until ESP confirms token storage through authenticated status/command/voice.
- Six-digit setup-code pairing fetches ESP `/api/device/pairing-info`, verifies the displayed code, learns the real `djconnect-lilygo-XXXXXXXXXXXX` device id and uses that real id in `POST /api/device/pair`.
- HA config flow/entities may exist while pairing is still `pending`; tests must fail if HA reports `paired` before ESP confirmation.
- If `/api/device/pair` is never observed by the ESP and the ESP display stays on the pairing screen, HA must keep/recover `pending` state and retry explicit pairing instead of claiming success.
- 401/403/404 marks pairing stale.
- HTTP 200 with `backend_available:false` does not mark pairing stale.
- Status payload updates native entities from top-level and nested `settings`/`screen`/`led`.
- OTA status clears after ESP posts idle + firmware version.
- No backend playback credentials are sent to/stored on ESP.
- DJ response WAV/MP3 works and unknown audio remains text-only.
- Empty queue/devices/playlists responses do not become HTTP 503.
- `set_shuffle` and `set_repeat` remain canonical.
- Legacy `djconnect-XXXXXXXXXXXX` device IDs are rejected.
- HA/ESP major.minor mismatch returns HTTP 426 `version_mismatch` and keeps pairing intact.
- Pair payload contains `ha_local_url` and/or `ha_remote_url`, and never `ha_url`.
- Diagnostics redact keys containing `token`, `password` or `secret` and include legal metadata.
- Full status payload vult sensoren.
- Status updates zijn merge-only: ontbrekende velden behouden bestaande waarden.
- Command/voice/backend/playback payloads en coordinator refreshes mogen de cached ESP device-status niet vervangen door lege dicts, `None`, `unknown` of `pending`.
- Persist/restore last-known ESP status in config entry data as `last_device_status`; never store secrets there.
- `sensor.djconnect_last_track` and `sensor.djconnect_last_command` keep their last non-empty native value when sparse runtime snapshots omit them.
- Expose PTT debug attributes on status/last-command sensors: last STT text, Spotify search summary and resolved media metadata.
- Spotify artist-only search is covered by tests: `"Metallica"` / `"ik wil Pearl Jam starten"` must query artists, not leak DJ response prompt text into the query.
- `dj_response_prompt` replaces old fixed style/profile options; tests must fail if `dj_style` or `dj_profile` return.

Run:

```bash
python3 -m unittest discover -s tests
```

## 9. Acceptance Criteria

- ESP `v3.1.x` pairs without stale-pairing loops.
- After a 6-digit setup-code flow, ESP logs `Home Assistant direct pairing stored: device_token=present`, exits the pairing screen and after reboot logs `Home Assistant pairing: paired`.
- ESP S indicator updates green/grey/red after reboot without user action.
- HA entities reflect ESP state after reboot/status post.
- Backend unavailable keeps HA pairing intact.
- HA `3.0.z` only talks to ESP `3.0.z`; HA `3.1.z` only talks to ESP `3.1.z`; mismatch returns HTTP 426 without clearing pairing.
- Backend credentials remain only in Home Assistant.
- OTA discovers firmware from `pcvantol/djconnect-firmware`.
- OTA sends target `lilygo-t-embed-s3`, not `djconnect-device`.
- Raw WAV PTT returns DJ response text and optional WAV/MP3 audio URL.
- Raw WAV PTT resolves artist requests through Spotify artist search, starts playback, then generates a user-facing DJ response from resolved metadata and `dj_response_prompt`.
- Sensor values, especially last command and last track, remain stable after sparse command/status/playback refreshes.
- No old SpotifyDJ/spotifydj/spotify_dj naming remains in HA user-facing UI, docs or tests except explicit negative migration notes.
