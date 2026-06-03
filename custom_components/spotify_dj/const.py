"""Constants for SpotifyDJ."""

DOMAIN = "spotify_dj"

NAME = "SpotifyDJ"
VERSION = "1.1.1"

MANUFACTURER = "SpotifyDJ"
MODEL = "LILYGO T-Embed S3"

# Core config
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_PAIR_CODE = "pair_code"
CONF_LOCAL_URL = "local_url"

DEFAULT_DEVICE_NAME = "SpotifyDJ"

# Home Assistant / device API
CONF_HA_URL = "ha_url"
CONF_DEVICE_TOKEN = "device_token"

# Spotify
CONF_SPOTIFY_CLIENT_ID = "spotify_client_id"
CONF_SPOTIFY_MARKET = "spotify_market"

DEFAULT_SPOTIFY_MARKET = "NL"

# Voice / Assist
CONF_ASSIST_PIPELINE_ID = "assist_pipeline_id"
CONF_TTS_ENGINE = "tts_engine"
CONF_TTS_LANGUAGE = "tts_language"
CONF_TTS_VOICE = "tts_voice"

DEFAULT_ASSIST_PIPELINE_ID = None
DEFAULT_TTS_ENGINE = "tts"
DEFAULT_TTS_LANGUAGE = "nl-NL"
DEFAULT_TTS_VOICE = None

# DJ style
CONF_DJ_STYLE = "dj_style"

DJ_STYLE_CLASSIC_DUTCH_RADIO = "classic_dutch_radio"
DJ_STYLE_CALM_EVENING = "calm_evening"
DJ_STYLE_FESTIVAL = "festival"
DJ_STYLE_MINIMAL = "minimal"

DEFAULT_DJ_STYLE = DJ_STYLE_CLASSIC_DUTCH_RADIO

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

# Firmware / OTA
CONF_FIRMWARE_REPO = "firmware_repo"
CONF_FIRMWARE_CHANNEL = "firmware_channel"

DEFAULT_FIRMWARE_REPO = "pcvantol/spotify-dj-firmware"
DEFAULT_FIRMWARE_CHANNEL = "stable"

FIRMWARE_CHANNEL_STABLE = "stable"
FIRMWARE_CHANNEL_BETA = "beta"

FIRMWARE_CHANNELS = [
    FIRMWARE_CHANNEL_STABLE,
    FIRMWARE_CHANNEL_BETA,
]

# Endpoints
API_BASE = "/api/spotify_dj"
API_PAIR = f"{API_BASE}/pair"
API_VOICE = f"{API_BASE}/voice"
API_STATUS = f"{API_BASE}/status"
API_EVENT = f"{API_BASE}/event"
API_SPOTIFY_CALLBACK = f"{API_BASE}/spotify/callback"

DEVICE_API_BASE = "/api/device"
DEVICE_API_INFO = f"{DEVICE_API_BASE}/info"
DEVICE_API_PROVISION_SPOTIFY = f"{DEVICE_API_BASE}/provision_spotify"
DEVICE_API_OTA = f"{DEVICE_API_BASE}/ota"
DEVICE_API_REBOOT = f"{DEVICE_API_BASE}/reboot"