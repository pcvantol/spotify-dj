from __future__ import annotations

DOMAIN = "spotify_dj"
API_BASE = "/api/spotify_dj"
API_VOICE = f"{API_BASE}/voice"
API_PAIR = f"{API_BASE}/pair"
API_STATUS = f"{API_BASE}/status"
API_EVENT = f"{API_BASE}/event"
API_SPOTIFY_CALLBACK = f"{API_BASE}/spotify_callback"
PLATFORMS = ["sensor", "button", "update"]

CONF_SPOTIFY_PLAYER = "spotify_player"
CONF_SPOTIFY_SOURCE = "spotify_source"
CONF_OPENAI_API_KEY = "openai_api_key"
CONF_OPENAI_CHAT_MODEL = "openai_chat_model"
CONF_OPENAI_STT_MODEL = "openai_stt_model"
CONF_OPENAI_TTS_MODEL = "openai_tts_model"
CONF_OPENAI_TTS_VOICE = "openai_tts_voice"
CONF_DJ_STYLE = "dj_style"
CONF_LIKED_PROXY = "liked_songs_proxy_playlist"
CONF_MAX_AUDIO_BYTES = "max_audio_bytes"
CONF_FIRMWARE_REPO = "firmware_repo"
CONF_FIRMWARE_ASSET_PREFIX = "firmware_asset_prefix"
CONF_FIRMWARE_DEVICE = "firmware_device"
CONF_ALLOW_OTA_ON_BATTERY = "allow_ota_on_battery"
CONF_MIN_BATTERY_FOR_OTA = "min_battery_for_ota"
CONF_SPOTIFY_CLIENT_ID = "spotify_client_id"
CONF_SPOTIFY_REFRESH_TOKEN = "spotify_refresh_token"
CONF_SPOTIFY_MARKET = "spotify_market"
CONF_SPOTIFY_SCOPES = "spotify_scopes"

DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_STT_MODEL = "gpt-4o-mini-transcribe"
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_TTS_VOICE = "onyx"
DEFAULT_MAX_AUDIO_BYTES = 2_500_000
DEFAULT_FIRMWARE_REPO = "pcvantol/spotify-dj-app"
DEFAULT_FIRMWARE_ASSET_PREFIX = "spotifydj-lilygo-t-embed-s3"
DEFAULT_FIRMWARE_DEVICE = "lilygo-t-embed-s3"
DEFAULT_MIN_BATTERY_FOR_OTA = 40
DEFAULT_SPOTIFY_MARKET = "NL"
DEFAULT_SPOTIFY_SCOPES = "user-read-playback-state user-read-currently-playing user-modify-playback-state user-library-read playlist-read-private playlist-read-collaborative"
DEFAULT_DJ_STYLE = (
    "Nederlandse commerciële radio-dj uit de jaren 90/00: warm, zelfverzekerd, "
    "licht brutaal, droog komisch, energiek maar niet schreeuwerig. "
    "Gebruik korte zinnen, een glimlach in de stem en natuurlijke radiopauzes. "
    "Imiteer geen specifieke bestaande persoon."
)

ATTR_LAST_TEXT = "last_text"
ATTR_LAST_INTENT = "last_intent"
ATTR_LAST_DJ_TEXT = "last_dj_text"
ATTR_LAST_ERROR = "last_error"
ATTR_LAST_PLAYBACK = "last_playback"
