from __future__ import annotations

DOMAIN = "spotify_dj"
NAME = "SpotifyDJ"
VERSION = "1.0.0"

API_BASE = "/api/spotify_dj"
API_PAIR = f"{API_BASE}/pair"
API_VOICE = f"{API_BASE}/voice"
API_STATUS = f"{API_BASE}/status"
API_EVENT = f"{API_BASE}/event"

CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_TOKEN = "device_token"
CONF_LOCAL_URL = "local_url"
CONF_SPOTIFY_CLIENT_ID = "spotify_client_id"
CONF_SPOTIFY_MARKET = "spotify_market"
CONF_ASSIST_PIPELINE_ID = "assist_pipeline_id"
CONF_TTS_ENGINE = "tts_engine"
CONF_TTS_LANGUAGE = "tts_language"
CONF_TTS_VOICE = "tts_voice"
CONF_DJ_PROFILE = "dj_profile"
CONF_SPOTIFY_PLAYER = "spotify_player"
CONF_SPOTIFY_SOURCE = "spotify_source"
CONF_LIKED_PROXY = "liked_proxy_playlist_uri"
CONF_MAX_AUDIO_BYTES = "max_audio_bytes"

CONF_FIRMWARE_REPO = "firmware_repo"
CONF_FIRMWARE_ASSET_PREFIX = "firmware_asset_prefix"
CONF_FIRMWARE_DEVICE = "firmware_device"
CONF_FIRMWARE_CHANNEL = "firmware_channel"
CONF_ALLOW_OTA_ON_BATTERY = "allow_ota_on_battery"
CONF_MIN_BATTERY_FOR_OTA = "min_battery_for_ota"

DEFAULT_DEVICE_NAME = "SpotifyDJ"
DEFAULT_SPOTIFY_MARKET = "NL"
DEFAULT_MAX_AUDIO_BYTES = 2_000_000
DEFAULT_FIRMWARE_REPO = "pcvantol/spotify-dj-firmware"
DEFAULT_FIRMWARE_ASSET_PREFIX = "spotifydj-lilygo-t-embed-s3"
DEFAULT_FIRMWARE_DEVICE = "lilygo-t-embed-s3"
DEFAULT_FIRMWARE_CHANNEL = "stable"
DEFAULT_MIN_BATTERY_FOR_OTA = 40
DEFAULT_TTS_LANGUAGE = "nl-NL"
DEFAULT_DJ_PROFILE = "classic_dutch_radio"

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
# Backwards compatibility for earlier modules kept in this package.
API_SPOTIFY_CALLBACK = f"{API_BASE}/spotify/callback"
PLATFORMS = ["sensor", "button", "update"]
CONF_OPENAI_API_KEY = "openai_api_key"
CONF_OPENAI_CHAT_MODEL = "openai_chat_model"
CONF_OPENAI_STT_MODEL = "openai_stt_model"
CONF_OPENAI_TTS_MODEL = "openai_tts_model"
CONF_OPENAI_TTS_VOICE = "openai_tts_voice"
CONF_SPOTIFY_REFRESH_TOKEN = "spotify_refresh_token"
CONF_SPOTIFY_SCOPES = "spotify_scopes"
DEFAULT_CHAT_MODEL = "ha_conversation"
DEFAULT_STT_MODEL = "ha_stt"
DEFAULT_TTS_MODEL = "ha_tts"
DEFAULT_TTS_VOICE = ""
DEFAULT_SPOTIFY_SCOPES = " ".join(SPOTIFY_SCOPES)
