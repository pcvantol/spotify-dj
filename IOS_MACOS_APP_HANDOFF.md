# DJConnect iOS/macOS App Handoff

## Doel

Bereid een toekomstige DJConnect iOS/macOS app voor als extra client naast de ESP32/LilyGO firmware, zonder de Home Assistant architectuur te verbreden naar directe Spotify- of Assist-auth op clients.

De app is een DJConnect remote/client. Home Assistant blijft de trusted backend voor pairing, Spotify OAuth/backend playback, Assist/STT/TTS, OTA/status voor devices en alle secrets.

## Repositories

- HA integration: `pcvantol/djconnect`
- ESP firmware source: `pcvantol/djconnect-app`
- Public firmware releases: `pcvantol/djconnect-firmware`
- Toekomstige app repo: nog te bepalen

## Client Types

Gebruik canoniek `client_type` om runtimes te onderscheiden:

- `esp32`: fysiek DJConnect ESP device
- `ios`: toekomstige iOS app
- `macos`: toekomstige macOS app

Regels:

- `client_type` is verplicht op JSON pairing/status/command/voice routes.
- iOS device ID: `djconnect-ios-XXXXXXXXXXXX`, met `XXXXXXXXXXXX` als de eerste 12 alfanumerieke chars van de install ID.
- macOS device ID: `djconnect-macos-XXXXXXXXXXXX`, met `XXXXXXXXXXXX` als de eerste 12 alfanumerieke chars van de install ID.
- iOS/macOS app IDs zijn echte DJConnect client IDs, maar geen ESP mDNS hostnames; HA mag hiervoor geen `http://<device_id>.local` device-command fallback genereren.
- `client_type:"ios"` mag alleen met `djconnect-ios-XXXXXXXXXXXX`.
- `client_type:"macos"` mag alleen met `djconnect-macos-XXXXXXXXXXXX`.
- `client_type:"esp32"` blijft voor ESP model-specifieke IDs zoals `djconnect-lilygo-t-embed-s3-XXXXXXXXXXXX` en `djconnect-esp32-s3-box-3-XXXXXXXXXXXX`.
- Geen fallback naar oude `device_type`.
- `device_type` niet opnieuw introduceren.
- ESP firmware mag alleen `esp32` gebruiken.
- iOS app gebruikt `ios`; macOS app gebruikt `macos`.

## Architectuurregels

- Clients bewaren geen Spotify refresh tokens, Spotify client secrets, HA long-lived tokens of backend playback credentials.
- Spotify OAuth en token refresh blijven in Home Assistant.
- Playback commands lopen via Home Assistant.
- Voice/STT/TTS loopt via Home Assistant Assist/TTS.
- DJ responses worden door HA gegenereerd met de configureerbare `dj_response_prompt`.
- De app mag lokale UI/audio hebben, maar backend playback blijft HA-owned.

## Pairing

De app moet een eigen pairing-flow krijgen die aansluit op hetzelfde HA securitymodel:

- HA maakt of registreert een client token.
- App gebruikt bearer-token auth naar HA routes.
- Pairingstatus is pas `paired` nadat HA de client succesvol geauthenticeerd heeft.
- `client_type` wordt persistent opgeslagen in de HA config entry of client registry metadata.
- App pairing mag ESP device pairing niet overschrijven.

Aanbevolen app identity:

```json
{
  "client_id": "djconnect-ios-<stable-id>",
  "client_type": "ios",
  "client_name": "DJConnect iPhone"
}
```

Voor macOS:

```json
{
  "client_id": "djconnect-macos-<stable-id>",
  "client_type": "macos",
  "client_name": "DJConnect Mac"
}
```

Gebruik voor apps liever `client_id` dan ESP-specifieke `device_id`. Als bestaande HA routes voorlopig `device_id` vereisen, map app clients expliciet en documenteer dat als tijdelijke routecompatibiliteit.

## HA Routegebruik

App clients mogen dezelfde backend-command semantiek gebruiken als ESP, maar niet dezelfde ESP-local routes.

App -> HA:

- `POST /api/djconnect/command`
- `POST /api/djconnect/voice`
- eventueel toekomstige `POST /api/djconnect/client/status`

Niet gebruiken voor app clients:

- `POST /api/device/pair`
- `POST /api/device/command`
- `POST /api/device/ota`
- `POST /api/device/dj_response`

Die `/api/device/*` routes zijn voor lokale ESP hardware.

## Playback Commands

App commands blijven generiek:

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
- `play_context_at`
- `set_shuffle`
- `set_repeat`

Responsecontract blijft gelijk:

- Auth/pairing failure: HTTP `401`/`403`/`404`
- Version/protocol mismatch: HTTP `426`
- Backend unavailable: HTTP `200` met `success:false`, `backend_available:false`
- Geen HTTP `503` voor normale Spotify/backend unavailable

## Voice / DJ Response

iOS/macOS kan twee routes ondersteunen:

- Raw audio upload naar `POST /api/djconnect/voice`
- Text command naar een toekomstige app-safe text endpoint of bestaande voice text-mode als developer/test route

Belangrijk:

- Geen directe Spotify parsing in de app.
- Geen directe Spotify Web API calls in de app.
- HA doet STT, artist-only Spotify resolve/playback en DJ response generatie.
- HA response bevat `text`/`dj_text` en optioneel `audio_url`.
- De app kan audio lokaal afspelen als dat UX-technisch gewenst is.

## Debug / Diagnostics

Voor app support zijn deze HA attributes nuttig:

- laatste STT tekst
- laatste Spotify search samenvatting
- resolved artist/context/media metadata
- laatste command
- laatste playback/backend error

Geen secrets in diagnostics/logs:

- redact keys met `token`, `password`, `secret`
- log geen Authorization headers
- log geen tijdelijke audio URL tokens

## Config / Options Flow

Huidige HA settings blijven leidend:

- `stt_engine`
- Assist pipeline
- TTS engine/language/voice
- Spotify source/output override
- `dj_response_prompt`

Niet terugbrengen:

- vaste DJ style/profile opties
- `dj_style`
- `dj_profile`
- `device_type`
- Spotify credentials op clients

## Open Ontwerpkeuzes

- Aparte app-client registry binnen de integration of HA config entry options.
- QR-code/deep-link pairing voor app clients.
- Of iOS/macOS app een eigen HA Repairs/reauthorize UX moet kunnen openen.
- Of app status onder hetzelfde HA device valt of als aparte client/device zichtbaar wordt.
- Welke route app text commands krijgt, zodat text-only ESP developer tests niet per ongeluk playback starten.

## Acceptatiecriteria

- ESP pairing blijft ongewijzigd en strikt `client_type:"esp32"`.
- iOS/macOS app kan als aparte client worden herkend zonder `device_type`.
- HA secrets blijven alleen in Home Assistant.
- App playback loopt via HA command proxy.
- App voice loopt via HA STT/Assist/TTS.
- DJ response gebruikt resolved Spotify metadata plus `dj_response_prompt`.
- Geen oude SpotifyDJ/spotify_dj naming of fixed DJ style compatibility komt terug.
