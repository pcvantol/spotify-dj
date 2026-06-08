# Codex Prompt: Synchronize SpotifyDJ ESP Firmware With HA Integration

Werk in de bestaande proprietary ESP firmware repo `pcvantol/spotify-dj-app`.

## Doel

Synchroniseer de ESP firmware met de actuele Home Assistant `spotify_dj` integration architectuur.

De HA integration is de trusted backend voor:

- pairing;
- bearer-token lifecycle;
- backend playback;
- Spotify OAuth;
- Assist/STT/TTS;
- OTA offer handling;
- native HA entities.

De ESP blijft eigenaar van:

- device runtime;
- display/UI;
- buttons/rotary;
- LED-ring;
- local speaker cues;
- WiFi/setup;
- raw WAV capture/upload;
- local playback van HA DJ response audio.

## Belangrijke beslissingen

- Legacy broker-based control is verwijderd. Noem die oude route nergens meer in UI, docs, provisioning, status of logs.
- ESP is geen Spotify Connect speaker/player.
- ESP bewaart geen Spotify OAuth/client_id/refresh_token of andere playback-backend credentials.
- ESP stuurt generieke playback commands naar HA.
- HA vertaalt playback commands naar Spotify of toekomstige backends.
- ESP speaker is alleen voor local cues en DJ/voice response audio.
- `/api/device/provision_spotify` mag niet meer bestaan of gebruikt worden; als compat route nog aanwezig is, verwijder die of laat hem expliciet `410 Gone` geven zonder secrets.
- Pairing/status/voice/command auth gebruikt alleen het device bearer token.
- Device ID format voor actuele firmware is `spotifydj-lilygo-XXXXXXXXXXXX`.
- NVS taal key blijft `provision.language`.
- Secrets nooit loggen: geen device tokens, HA tokens, Spotify tokens, WiFi wachtwoorden of tijdelijke audio URL tokens.

## Endpoint contract

### ESP -> HA

Protected routes:

- `POST /api/spotify_dj/status`
- `POST /api/spotify_dj/command`
- `POST /api/spotify_dj/voice`
- `POST /api/spotify_dj/event` indien gebruikt

Headers:

```http
Authorization: Bearer <device_token>
X-SpotifyDJ-Device-ID: spotifydj-lilygo-XXXXXXXXXXXX
Content-Type: application/json
```

Voor PTT:

```http
Authorization: Bearer <device_token>
X-SpotifyDJ-Device-ID: spotifydj-lilygo-XXXXXXXXXXXX
Content-Type: audio/wav
```

### HA -> ESP

Protected local ESP routes:

- `GET /api/device/info`
- `GET /api/device/pairing-info`
- `POST /api/device/pair`
- `POST /api/device/command`
- `POST /api/device/ota`
- `POST /api/device/reboot`
- `POST /api/device/forget`
- `POST /api/device/dj_response`

Header:

```http
Authorization: Bearer <device_token>
```

## Taken

### 1. Pairing-token synchronisatie

Controleer en fix:

- ESP ontvangt `device_token` via `POST /api/device/pair`.
- ESP slaat exact die token persistent op.
- Eerste call naar HA `/api/spotify_dj/command` gebruikt exact die token.
- Eerste call naar HA `/api/spotify_dj/status` gebruikt exact die token.
- Eerste call naar HA `/api/spotify_dj/voice` gebruikt exact die token.
- ESP mag pending pairing niet wissen bij tijdelijke Spotify/backend fouten.
- ESP mag pending pairing alleen stale/invalid markeren bij echte HA auth/pairing errors:
  - 401;
  - 403;
  - 404 met duidelijke stale pairing betekenis.
- 200 JSON met `success:false` en `backend_unavailable` betekent niet pairing wissen.
- 503 backend unavailable mag bij voorkeur ook niet direct NVS pairing wissen; toon pairing degraded/backend unavailable.

Veilige logs:

- log `device_token=present/missing`, nooit de waarde;
- log HA response status en error key;
- log geen Authorization header.

### 2. Status payload uitbreiden

Zorg dat periodieke HA status payload actuele device settings bevat zodat HA native entities correct updaten.

Stuur minimaal:

```json
{
  "device_id": "spotifydj-lilygo-XXXXXXXXXXXX",
  "ha_pairing_status": "paired|pending|stale|unpaired",
  "local_url": "http://spotifydj-lilygo-XXXXXXXXXXXX.local",
  "firmware": "2.9.x",
  "battery_percent": 85,
  "wifi_rssi": -55,
  "uptime": 123456,
  "free_heap": 123456,
  "screen_brightness": 75,
  "brightness": 75,
  "speaker_volume": 50,
  "cue_volume": 50,
  "screen_dim_timeout_ms": 60000,
  "turn_off_after_ms": 300000,
  "language": "nl",
  "theme": "dark",
  "log_level": "info",
  "ota_state": "idle",
  "update_state": "idle"
}
```

Gebruik aliases waar makkelijk, want de HA integration accepteert meerdere namen:

- `screen_brightness` / `brightness`;
- `speaker_volume` / `cue_volume`;
- `screen_dim_timeout_ms`;
- `turn_off_after_ms`;
- `language`;
- `theme`;
- `log_level`.

### 3. Generic playback command API naar HA

ESP stuurt playback commands naar:

```http
POST /api/spotify_dj/command
```

Payload voorbeelden:

```json
{"device_id":"spotifydj-lilygo-XXXXXXXXXXXX","command":"status"}
{"device_id":"spotifydj-lilygo-XXXXXXXXXXXX","command":"devices"}
{"device_id":"spotifydj-lilygo-XXXXXXXXXXXX","command":"queue"}
{"device_id":"spotifydj-lilygo-XXXXXXXXXXXX","command":"playlists"}
{"device_id":"spotifydj-lilygo-XXXXXXXXXXXX","command":"pause"}
{"device_id":"spotifydj-lilygo-XXXXXXXXXXXX","command":"play"}
{"device_id":"spotifydj-lilygo-XXXXXXXXXXXX","command":"next"}
{"device_id":"spotifydj-lilygo-XXXXXXXXXXXX","command":"previous"}
{"device_id":"spotifydj-lilygo-XXXXXXXXXXXX","command":"set_output","value":"iPhone","play":true}
{"device_id":"spotifydj-lilygo-XXXXXXXXXXXX","command":"set_volume","value":35}
{"device_id":"spotifydj-lilygo-XXXXXXXXXXXX","command":"start_liked_proxy","play":true}
{"device_id":"spotifydj-lilygo-XXXXXXXXXXXX","command":"start_playlist","value":"spotify:playlist:...","play":true}
{"device_id":"spotifydj-lilygo-XXXXXXXXXXXX","command":"set_play_mode","value":"shuffle"}
```

Verwachte response shapes:

```json
{
  "success": true,
  "playback": {
    "has_playback": true,
    "is_playing": true,
    "track_name": "Song",
    "artist_name": "Artist",
    "album_image_url": "https://...",
    "progress_ms": 12345,
    "duration_ms": 180000,
    "volume_percent": 32,
    "shuffle": false,
    "repeat_state": "off",
    "device": {
      "id": "spotify-device-id",
      "name": "iPhone",
      "type": "Smartphone",
      "active": true,
      "supports_volume": true,
      "volume_percent": 32
    }
  }
}
```

Backend unavailable/auth failure:

```json
{
  "success": false,
  "error": "backend_unavailable",
  "message": "Spotify authorization has expired or was revoked. Reauthorize SpotifyDJ.",
  "backend_available": false,
  "playback": {}
}
```

Belangrijk:

- Dit is geen pairing failure.
- Toon een backend/playback fout in UI.
- Wis pairing niet.

### 4. Device command API vanaf HA

Controleer `POST /api/device/command` voor device-instellingen:

```json
{"command":"status"}
{"command":"screen_brightness","value":75}
{"command":"screen_dim_timeout","value":60000}
{"command":"turn_off_after","value":300000}
{"command":"speaker_volume","value":50}
{"command":"language","value":"nl"}
{"command":"theme","value":"dark"}
{"command":"log_level","value":"info"}
{"command":"dj_response","text":"Daar gaan we.","audio_url":"http://..."}
```

Responses altijd JSON:

```json
{"success":true}
```

of:

```json
{"success":false,"error":"invalid_command","message":"..."}
```

### 5. PTT / voice

Physical PTT:

```text
ESP records WAV
-> POST /api/spotify_dj/voice raw audio/wav
-> HA does STT/Assist/playback/TTS
-> HA returns DJ text plus optional WAV/MP3 audio_url
-> ESP displays text and plays local response audio
```

Expected HA response:

```json
{
  "success": true,
  "text": "Daar gaan we.",
  "dj_text": "Daar gaan we.",
  "audio_url": "http://homeassistant.local:8123/api/spotify_dj/tts/token.mp3",
  "audio_type": "mp3"
}
```

Fout:

```json
{
  "success": false,
  "error": "stt_failed",
  "message": "No STT provider configured..."
}
```

Acties:

- Directe HA Assist WebSocket auth vanaf ESP niet gebruiken.
- ESP uploadt alleen raw WAV.
- ESP speelt WAV of MP3 audio URL af indien ondersteund.
- Onbekend audioformaat: text-only tonen, niet crashen.
- Geen tijdelijke audio URL tokens loggen.

### 6. OAuth / Spotify secrets verwijderen

Controleer dat ESP:

- geen `spotify_client_id` opslaat;
- geen `client_id` opslaat;
- geen `spotify_refresh_token` opslaat;
- geen `refresh_token` opslaat;
- geen Spotify OAuth secrets verwacht in pair/status responses;
- `spotify_configured=false` hooguit als backend/statushint behandelt, niet als request om Spotify credentials te ontvangen.

Verwijder/neutraliseer oude codepaden die Spotify credentials naar ESP provisionen.

### 7. OTA

Controleer:

- OTA endpoint blijft `POST /api/device/ota`.
- Bearer token verplicht.
- Payload accepteert:

```json
{
  "version": "2.9.x",
  "url": "https://...",
  "sha256": "...",
  "device": "lilygo-t-embed-s3",
  "asset": "spotifydj-device-v2.9.x.bin"
}
```

- `device` moet matchen op `lilygo-t-embed-s3`.
- Assetnaam hoeft geen boardnaam te bevatten.
- Tijdens OTA:
  - duidelijke UI status;
  - paarse snelle LED-ring animatie;
  - status na reboot terug naar `idle`;
  - post-boot status naar HA met firmwareversie en idle state.

### 8. BLE WiFi provisioning

BLE provisioning doet alleen WiFi credentials.

Service/characteristics:

- Service UUID: `7f705000-9f8f-4f1a-9b5f-570071fd0001`
- WiFi write characteristic: `7f705001-9f8f-4f1a-9b5f-570071fd0001`
- Status read/notify characteristic: `7f705002-9f8f-4f1a-9b5f-570071fd0001`

Geen Spotify credentials, device tokens of andere secrets via BLE.

### 9. UI/UX

- Device blijft koppelcode tonen tot HA pairing echt bevestigd is.
- Na succesvolle HA direct pair en eerste geaccepteerde HA command/status mag UI naar paired/groen.
- Backend unavailable mag niet terug naar pairing-code scherm forceren.
- Pairing stale mag duidelijk tonen: reset/re-pair nodig.
- Soft reset/reboot moet local cue sound en felle witte LED-ring flash tonen vlak voor reboot.
- Bonus game Pong mag in UI blijven.
- Noem oude broker-gebaseerde routes nergens.

### 10. Tests

Voeg/update host tests waar mogelijk:

- Pairing token opgeslagen en hergebruikt voor `/status`, `/command`, `/voice`.
- Backend unavailable response wist pairing niet.
- 401/403/404 markeert pairing stale maar wist NVS niet automatisch.
- Status payload bevat settings aliases.
- Device command parsing voor brightness/speaker/language/theme/log_level.
- PTT upload bouwt correcte headers en content type.
- No Spotify OAuth secret keys in status/pair/provision payloads.
- OTA payload device target `lilygo-t-embed-s3`.

## Acceptatiecriteria

- ESP pairt met HA en blijft paired na de eerste `/api/spotify_dj/command`.
- ESP wist pairing niet door Spotify OAuth/backend failures.
- ESP status houdt HA native entities actueel.
- ESP gebruikt alleen de HA-native lokale API.
- ESP bewaart geen Spotify credentials.
- ESP stuurt generic playback commands naar HA.
- ESP PTT uploadt raw WAV naar HA en speelt HA DJ response lokaal af.
- OTA blijft werken met `spotifydj-device-vX.Y.Z.bin` en target `lilygo-t-embed-s3`.
- Logs bevatten geen secrets.
