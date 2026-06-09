# Codex Prompt: Synchronize Home Assistant Integration With DJConnect ESP Firmware

Werk in de bestaande Home Assistant custom integration repo `pcvantol/djconnect`.

## Doel

Synchroniseer de Home Assistant integration met de actuele DJConnect ESP firmware contracten voor release `v3.0.6`.

## 0. Repository / Release Hygiene

- HA integration repo: `pcvantol/djconnect`.
- ESP source repo: `pcvantol/djconnect-app`.
- Public OTA firmware repo: `pcvantol/djconnect-firmware`.
- Firmware binaries/manifests must be consumed from `djconnect-firmware`; the ESP source repo is not the OTA asset host.
- Current HA integration release/tag baseline is `v3.0.6`; do not reference old 2.x firmware assets or tags.
- Current firmware asset naming convention is `djconnect-device-vX.Y.Z.bin`.
- Current OTA manifest filename is `firmware_manifest.json`.
- Current OTA manifest `device` target is `lilygo-t-embed-s3`.

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
- `POST /api/device/pair` naar ESP moet `device_token` plus `ha_local_url` en/of `ha_remote_url` sturen.
- `ha_local_url` is de LAN URL die ESP eerst probeert, bijvoorbeeld `http://homeassistant.local:8123`.
- `ha_remote_url` is de optionele Nabu Casa/cloud URL die ESP gebruikt als local niet bereikbaar is.
- Pairing zonder `ha_local_url` en zonder `ha_remote_url` moet als configuratiefout worden behandeld.
- Stuur geen legacy `ha_url` pairingveld.
- Treat ESP pairing as `pending` totdat een authenticated ESP status/command/voice post naar HA succesvol verwerkt is met dezelfde bearer token.
- Als HA 401/403/404 teruggeeft op ESP status/command/voice, pairing is stale/invalid.
- Als playback backend tijdelijk niet beschikbaar is, dat is geen pairing failure.

Expected HA -> ESP pair payload:

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
- HA DJ response prompt vraagt waar mogelijk om een kort leuk feitje over artiest en/of nummer.

## 6. Optional HA Media Player Entity

Als een `media_player` entity bestaat:

- Represents backend playback state, niet de ESP speaker.
- Commands: play/pause, next/previous, volume, source/output, playlist/media start.
- Backend credentials blijven in Home Assistant.
- ESP device settings blijven via `POST /api/device/command` lopen.

## 7. OTA / Firmware Release Consumption

Controleer:

- HA leest firmware releases uit `pcvantol/djconnect-firmware`.
- Release asset is `djconnect-device-vX.Y.Z.bin`.
- Manifest is `firmware_manifest.json`.
- Manifest bevat `version`, `device`, `asset`, `sha256`, `size`, `min_ha_integration`.
- HA stuurt manifest `device` ongewijzigd naar ESP `POST /api/device/ota`.
- Voor huidige firmware is manifest `device` `lilygo-t-embed-s3`.
- Gebruik niet de generieke assetprefix `djconnect-device` als OTA target device.

OTA payload naar ESP:

```json
{
  "version": "3.0.6",
  "url": "https://github.com/pcvantol/djconnect-firmware/releases/download/v3.0.6/djconnect-device-v3.0.6.bin",
  "sha256": "...",
  "device": "lilygo-t-embed-s3",
  "asset": "djconnect-device-v3.0.6.bin"
}
```

## 8. Tests To Add / Update

- Pairing pending until ESP confirms token storage through authenticated status/command/voice.
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

Run:

```bash
python3 -m unittest discover -s tests
```

## 9. Acceptance Criteria

- ESP `v3.0.6` pairs without stale-pairing loops.
- ESP S indicator updates green/grey/red after reboot without user action.
- HA entities reflect ESP state after reboot/status post.
- Backend unavailable keeps HA pairing intact.
- HA `3.0.z` only talks to ESP `3.0.z`; HA `3.1.z` only talks to ESP `3.1.z`; mismatch returns HTTP 426 without clearing pairing.
- Backend credentials remain only in Home Assistant.
- OTA discovers firmware from `pcvantol/djconnect-firmware`.
- OTA sends target `lilygo-t-embed-s3`, not `djconnect-device`.
- Raw WAV PTT returns DJ response text and optional WAV/MP3 audio URL.
- No old SpotifyDJ/spotifydj/spotify_dj naming remains in HA user-facing UI, docs or tests except explicit negative migration notes.
