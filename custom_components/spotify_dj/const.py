"""Constants for SpotifyDJ."""
from __future__ import annotations

DOMAIN = "spotify_dj"
NAME = "SpotifyDJ"
VERSION = "2.9.22"

API_BASE = "/api/spotify_dj"
API_PAIR = f"{API_BASE}/pair"
API_VOICE = f"{API_BASE}/voice"
API_COMMAND = f"{API_BASE}/command"
API_STATUS = f"{API_BASE}/status"
API_EVENT = f"{API_BASE}/event"
API_TTS_BASE = f"{API_BASE}/tts"
API_TTS = f"{API_TTS_BASE}/{{token}}.{{extension}}"
API_SPOTIFY_CALLBACK = f"{API_BASE}/spotify/callback"

CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_TOKEN = "device_token"
CONF_DEVICE_LANGUAGE = "device_language"
CONF_LOCAL_URL = "local_url"
CONF_HA_EXTERNAL_URL = "ha_external_url"
CONF_PAIR_CODE = "pair_code"
CONF_SETUP_METHOD = "setup_method"
CONF_BLE_ADDRESS = "ble_address"
CONF_WIFI_SSID = "wifi_ssid"
CONF_WIFI_PASSWORD = "wifi_password"

CONF_SPOTIFY_CLIENT_ID = "spotify_client_id"
CONF_SPOTIFY_REFRESH_TOKEN = "spotify_refresh_token"
CONF_SPOTIFY_MARKET = "spotify_market"
CONF_SPOTIFY_SCOPES = "spotify_scopes"
CONF_SPOTIFY_SOURCE = "spotify_source"
CONF_LIKED_PROXY = "liked_proxy_playlist_uri"

CONF_ASSIST_PIPELINE_ID = "assist_pipeline_id"
CONF_STT_ENGINE = "stt_engine"
CONF_TTS_ENGINE = "tts_engine"
CONF_TTS_LANGUAGE = "tts_language"
CONF_TTS_VOICE = "tts_voice"
CONF_DJ_RESPONSE_ENABLED = "dj_response_enabled"
CONF_DJ_RESPONSE_TTL_SECONDS = "dj_response_ttl_seconds"

# Both names are kept for backwards compatibility with older modules.
CONF_DJ_STYLE = "dj_style"
CONF_DJ_PROFILE = "dj_profile"

CONF_MAX_AUDIO_BYTES = "max_audio_bytes"

CONF_FIRMWARE_REPO = "firmware_repo"
CONF_FIRMWARE_ASSET_PREFIX = "firmware_asset_prefix"
CONF_FIRMWARE_DEVICE = "firmware_device"
CONF_FIRMWARE_CHANNEL = "firmware_channel"
CONF_ALLOW_OTA_ON_BATTERY = "allow_ota_on_battery"
CONF_MIN_BATTERY_FOR_OTA = "min_battery_for_ota"

DEFAULT_DEVICE_NAME = "SpotifyDJ"
DEFAULT_DEVICE_LANGUAGE = "en"
DEFAULT_SETUP_METHOD = "pair_existing"
SETUP_METHOD_PAIR_EXISTING = "pair_existing"
SETUP_METHOD_BLE_WIFI = "ble_wifi"
DEFAULT_SPOTIFY_CLIENT_ID = "5ea462242b3c447ab92fa54eb08c83be"
DEFAULT_SPOTIFY_MARKET = "NL"
DEFAULT_MAX_AUDIO_BYTES = 2_000_000
DEFAULT_FIRMWARE_REPO = "pcvantol/spotify-dj-firmware"
DEFAULT_FIRMWARE_ASSET_PREFIX = "spotifydj-device"
DEFAULT_FIRMWARE_DEVICE = "lilygo-t-embed-s3"
DEFAULT_FIRMWARE_CHANNEL = "stable"
DEFAULT_MIN_BATTERY_FOR_OTA = 40

DEFAULT_ASSIST_PIPELINE_ID = ""
DEFAULT_STT_ENGINE = ""
DEFAULT_TTS_ENGINE = "tts"
DEFAULT_TTS_LANGUAGE = "nl-NL"
DEFAULT_TTS_VOICE = ""
DEFAULT_DJ_RESPONSE_ENABLED = True
DEFAULT_DJ_RESPONSE_TTL_SECONDS = 120
DJ_STYLE_CLASSIC_DUTCH_RADIO = "classic_dutch_radio"
DJ_STYLE_CALM_EVENING = "calm_evening"
DJ_STYLE_FESTIVAL = "festival"
DJ_STYLE_MINIMAL = "minimal"

DEFAULT_DJ_STYLE = DJ_STYLE_CLASSIC_DUTCH_RADIO
DEFAULT_DJ_PROFILE = DEFAULT_DJ_STYLE

DJ_STYLES = [
    DJ_STYLE_CLASSIC_DUTCH_RADIO,
    DJ_STYLE_CALM_EVENING,
    DJ_STYLE_FESTIVAL,
    DJ_STYLE_MINIMAL,
]

DJ_STYLE_NAMES = {
    DJ_STYLE_CLASSIC_DUTCH_RADIO: "Classic Dutch radio",
    DJ_STYLE_CALM_EVENING: "Calm evening",
    DJ_STYLE_FESTIVAL: "Festival",
    DJ_STYLE_MINIMAL: "Minimal",
}

SPOTIFY_SCOPES = [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "user-library-read",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-read-recently-played",
    "user-top-read",
]
DEFAULT_SPOTIFY_SCOPES = " ".join(SPOTIFY_SCOPES)

PLATFORMS = ["sensor", "button", "number", "select", "update", "media_player"]

# Spotify OAuth/PKCE direct callback support
SPOTIFY_CALLBACK_PATH = API_SPOTIFY_CALLBACK
