# SpotifyDJ Home Assistant custom integration v0.7.0

SpotifyDJ turns a LilyGO T-Embed S3 into a push-to-talk Spotify/AI DJ remote for Home Assistant.

## What v0.7.0 adds

- Spotify OAuth/PKCE provisioning to LilyGO ESP standalone Spotify API client
- HA receives Spotify refresh token and pushes it once to ESP `/api/device/provision_spotify`
- Home Assistant-managed firmware OTA via GitHub Releases
- `update.spotifydj_firmware` entity
- `/api/spotify_dj/pair` device-token pairing endpoint
- `/api/spotify_dj/status` status endpoint
- `/api/spotify_dj/event` event endpoint
- `/api/spotify_dj/voice` WAV in -> WAV out endpoint
- Device sensors: battery, Wi-Fi RSSI, firmware, last track/status
- OpenAI STT/intent/TTS pipeline from earlier versions

## Recommended repository split

Use two repos:

```text
pcvantol/spotify-dj      # Home Assistant custom integration / HACS repo
pcvantol/spotify-dj-app  # LilyGO firmware releases, .bin assets
```

The HA integration checks GitHub Releases from `spotify-dj-app` and sends a concrete OTA command to the ESP. The ESP does not need to poll GitHub.

## HACS installation

1. Push this repository layout to `https://github.com/pcvantol/spotify-dj`.
2. In Home Assistant: HACS -> three dots -> Custom repositories.
3. Add `https://github.com/pcvantol/spotify-dj` as type `Integration`.
4. Install SpotifyDJ and restart Home Assistant.
5. Add the integration via Settings -> Devices & services -> Add integration -> SpotifyDJ.

## Manual installation

Copy:

```text
custom_components/spotify_dj
```

to:

```text
/config/custom_components/spotify_dj
```

Restart Home Assistant and add SpotifyDJ from Devices & services.

## Configuration

Important options:

| Option | Example | Purpose |
|---|---|---|
| OpenAI API key | `sk-...` | STT, intent parser, DJ TTS |
| Spotify player | `media_player.spotify_peter` | HA Spotify media player entity |
| Spotify source | `Woonkamer` | Optional Spotify Connect target |
| Firmware repo | `pcvantol/spotify-dj-app` | GitHub repo containing ESP firmware releases |
| Firmware asset prefix | `spotifydj-lilygo-t-embed-s3` | `.bin` filename prefix |
| Firmware device | `lilygo-t-embed-s3` | Device type check |
| Minimum OTA battery | `40` | Blocks OTA below this percentage unless charging |

## Device pairing

The LilyGO calls:

```http
POST /api/spotify_dj/pair
Content-Type: application/json
```

Body:

```json
{
  "device_id": "spotifydj-aabbccddeeff",
  "device_name": "SpotifyDJ Living",
  "pair_code": "482931",
  "firmware": "1.0.0",
  "local_url": "http://spotifydj-aabbccddeeff.local"
}
```

Response:

```json
{
  "success": true,
  "device_token": "...",
  "api_base": "/api/spotify_dj",
  "voice_path": "/api/spotify_dj/voice",
  "status_path": "/api/spotify_dj/status",
  "event_path": "/api/spotify_dj/event"
}
```

Store `device_token` in ESP NVS. Future calls use:

```http
Authorization: Bearer <device_token>
X-SpotifyDJ-Device-ID: spotifydj-aabbccddeeff
```

## Status endpoint

The ESP should periodically POST:

```http
POST /api/spotify_dj/status
Authorization: Bearer <device_token>
X-SpotifyDJ-Device-ID: spotifydj-aabbccddeeff
Content-Type: application/json
```

```json
{
  "device_id": "spotifydj-aabbccddeeff",
  "battery_percent": 93,
  "battery_mv": 4145,
  "charging": true,
  "usb_powered": true,
  "wifi_rssi": -53,
  "firmware": "1.0.0",
  "local_url": "http://spotifydj-aabbccddeeff.local",
  "paired": true
}
```

## Firmware releases for OTA

Create a GitHub Release in `pcvantol/spotify-dj-app` with assets:

```text
spotifydj-lilygo-t-embed-s3-v1.1.0.bin
spotifydj-firmware-manifest.json
spotifydj-lilygo-t-embed-s3-v1.1.0.sha256
```

`spotifydj-firmware-manifest.json`:

```json
{
  "version": "1.1.0",
  "device": "lilygo-t-embed-s3",
  "asset": "spotifydj-lilygo-t-embed-s3-v1.1.0.bin",
  "sha256": "<64 hex chars>",
  "min_ha_integration": "0.6.0",
  "notes": "Adds HA-managed OTA."
}
```

When HA sees the device runs `1.0.0` and GitHub latest is `1.1.0`, it shows an update entity.

## ESP OTA endpoint contract

When the user clicks install in HA, HA calls the ESP:

```http
POST http://spotifydj-aabbccddeeff.local/api/device/ota
Authorization: Bearer <device_token>
X-SpotifyDJ-Device-ID: spotifydj-aabbccddeeff
Content-Type: application/json
```

```json
{
  "version": "1.1.0",
  "url": "https://github.com/pcvantol/spotify-dj-app/releases/download/v1.1.0/spotifydj-lilygo-t-embed-s3-v1.1.0.bin",
  "sha256": "<64 hex chars>",
  "device": "lilygo-t-embed-s3",
  "asset": "spotifydj-lilygo-t-embed-s3-v1.1.0.bin"
}
```

ESP should:

1. Validate token and device id.
2. Check battery/USB.
3. Download the `.bin`.
4. Verify SHA-256.
5. Write OTA partition.
6. Reboot.
7. On successful boot, POST `/api/spotify_dj/status` with `firmware: "1.1.0"` and `ota_state: "success"`.

## mDNS

ESP should advertise:

```text
hostname: spotifydj-<chipid>.local
service:  _spotifydj._tcp.local
port:     80
TXT:
  name=SpotifyDJ
  version=1.0.0
  device_id=spotifydj-aabbccddeeff
  paired=true
```

## Voice endpoint

```http
POST /api/spotify_dj/voice
Authorization: Bearer <device_token>
X-SpotifyDJ-Device-ID: spotifydj-aabbccddeeff
Content-Type: audio/wav
```

Response is `audio/wav` containing the DJ announcement.


## v0.7.0 Spotify OAuth provisioning

This version supports the architecture where the ESP talks to Spotify directly.
Home Assistant acts as a temporary provisioning broker:

```text
LilyGO pairing code
  -> HA SpotifyDJ integration
  -> Spotify OAuth/PKCE in browser
  -> HA stores refresh_token
  -> HA POSTs credentials once to LilyGO
  -> ESP stores refresh_token in NVS
  -> ESP calls Spotify API standalone
```

### 1. Spotify Developer app

Create a Spotify Developer app and add this Redirect URI:

```text
http://homeassistant.local:8123/api/spotify_dj/spotify_callback
```

If you use an external HA URL, also add:

```text
https://your-ha.example.com/api/spotify_dj/spotify_callback
```

No client secret is needed; SpotifyDJ uses Authorization Code with PKCE.

Required scopes for the standalone ESP Spotify client:

```text
user-read-playback-state
user-read-currently-playing
user-modify-playback-state
user-library-read
playlist-read-private
playlist-read-collaborative
```

### 2. Start OAuth from HA

Call service:

```yaml
service: spotify_dj.start_spotify_oauth
data:
  client_id: "YOUR_SPOTIFY_CLIENT_ID"
  ha_base_url: "http://homeassistant.local:8123"
  market: "NL"
```

The service returns `auth_url`. Open it in your browser, log in to Spotify, and approve.
The callback stores the refresh token in the SpotifyDJ config entry.

### 3. Provision to LilyGO

After the device is paired and has sent status with `local_url`, call:

```yaml
service: spotify_dj.provision_spotify_credentials
```

HA sends:

```http
POST http://spotifydj-xxxx.local/api/device/provision_spotify
Authorization: Bearer <spotifydj_device_token>
X-SpotifyDJ-Device-ID: spotifydj-xxxx
Content-Type: application/json
```

Payload:

```json
{
  "spotify_client_id": "...",
  "spotify_refresh_token": "...",
  "spotify_market": "NL",
  "spotify_scopes": [
    "user-read-playback-state",
    "user-read-currently-playing",
    "user-modify-playback-state",
    "user-library-read",
    "playlist-read-private",
    "playlist-read-collaborative"
  ]
}
```

The ESP stores these in NVS, for example:

```cpp
prefs.putString("sp_client_id", clientId);
prefs.putString("sp_refresh", refreshToken);
prefs.putString("sp_market", market);
```

Security note: the Spotify refresh token is sensitive. This design is meant for your own trusted device. The HA-only Spotify brain remains safer, but this v0.7 flow fits the standalone ESP Spotify API architecture.

## v0.8.0 - HACS / branding polish

This release adds branding assets so HACS and Home Assistant can show a SpotifyDJ icon when the repository is installed as a custom integration.

### Included branding assets

```text
brands/
├── spotify_dj/
│   ├── icon.png
│   ├── icon@2x.png
│   └── logo.png
└── custom_integrations/
    └── spotify_dj/
        ├── icon.png
        ├── icon@2x.png
        └── logo.png
```

Also included:

```text
custom_components/spotify_dj/icon.png
custom_components/spotify_dj/icon@2x.png
custom_components/spotify_dj/logo.png
screenshots/spotifydj_icon_1024.png
info.md
CHANGELOG.md
```

### After updating in HACS

1. Update SpotifyDJ in HACS.
2. Restart Home Assistant.
3. Hard-refresh your browser/app cache if the icon does not appear immediately.
4. HACS and Home Assistant may cache brand images aggressively.

For long-term public distribution, consider submitting the icon/logo to the official Home Assistant brands repository under `custom_integrations/spotify_dj`.
