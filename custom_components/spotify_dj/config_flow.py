"""Config flow for SpotifyDJ."""

from __future__ import annotations

import logging
import re
import secrets
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from custom_components.spotify_dj import register_http_views

from .const import (
    CONF_ALLOW_OTA_ON_BATTERY,
    CONF_ASSIST_PIPELINE_ID,
    CONF_BLE_ADDRESS,
    CONF_DEVICE_ID,
    CONF_DEVICE_LANGUAGE,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TOKEN,
    CONF_DJ_RESPONSE_ENABLED,
    CONF_DJ_RESPONSE_TTL_SECONDS,
    CONF_DJ_PROFILE,
    CONF_DJ_STYLE,
    CONF_FIRMWARE_ASSET_PREFIX,
    CONF_FIRMWARE_CHANNEL,
    CONF_FIRMWARE_DEVICE,
    CONF_FIRMWARE_REPO,
    CONF_HA_EXTERNAL_URL,
    CONF_LIKED_PROXY,
    CONF_LOCAL_URL,
    CONF_MAX_AUDIO_BYTES,
    CONF_MIN_BATTERY_FOR_OTA,
    CONF_MQTT_HOST,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    CONF_PAIR_CODE,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_MARKET,
    CONF_SPOTIFY_PLAYER,
    CONF_SPOTIFY_REFRESH_TOKEN,
    CONF_SPOTIFY_SCOPES,
    CONF_SPOTIFY_SOURCE,
    CONF_STT_ENGINE,
    CONF_TTS_ENGINE,
    CONF_TTS_LANGUAGE,
    CONF_TTS_VOICE,
    CONF_SETUP_METHOD,
    CONF_WIFI_PASSWORD,
    CONF_WIFI_SSID,
    DEFAULT_ASSIST_PIPELINE_ID,
    DEFAULT_DEVICE_NAME,
    DEFAULT_DEVICE_LANGUAGE,
    DEFAULT_DJ_RESPONSE_ENABLED,
    DEFAULT_DJ_RESPONSE_TTL_SECONDS,
    DEFAULT_DJ_STYLE,
    DEFAULT_FIRMWARE_ASSET_PREFIX,
    DEFAULT_FIRMWARE_CHANNEL,
    DEFAULT_FIRMWARE_DEVICE,
    DEFAULT_FIRMWARE_REPO,
    DEFAULT_MAX_AUDIO_BYTES,
    DEFAULT_MIN_BATTERY_FOR_OTA,
    DEFAULT_MQTT_HOST,
    DEFAULT_MQTT_PORT,
    DEFAULT_SETUP_METHOD,
    DEFAULT_SPOTIFY_CLIENT_ID,
    DEFAULT_SPOTIFY_MARKET,
    DEFAULT_SPOTIFY_SCOPES,
    DEFAULT_STT_ENGINE,
    DEFAULT_TTS_ENGINE,
    DEFAULT_TTS_LANGUAGE,
    DEFAULT_TTS_VOICE,
    DJ_STYLE_NAMES,
    DJ_STYLES,
    DOMAIN,
    SETUP_METHOD_BLE_WIFI,
    SETUP_METHOD_PAIR_EXISTING,
)
from .ble import async_discover_devices, async_provision_wifi
from .spotify_oauth import build_authorize_url, build_redirect_uri, create_code_verifier

_LOGGER = logging.getLogger(__name__)

FIRMWARE_CHANNEL_NAMES = {"stable": "Stable", "beta": "Beta"}
DEVICE_LANGUAGE_NAMES = {"en": "English", "nl": "Nederlands"}
PAIR_CODE_PATTERN = re.compile(r"^(?:\d{6}|[0-9A-Fa-f]{12})$")
ADVANCED_OPTIONS_FIELD = "show_advanced_options"
SPOTIFY_MARKET_NAMES = {
    "NL": "Netherlands",
    "BE": "Belgium",
    "DE": "Germany",
    "FR": "France",
    "GB": "United Kingdom",
    "US": "United States",
}
SETUP_METHOD_NAMES = {
    SETUP_METHOD_PAIR_EXISTING: "Pair existing WiFi device",
    SETUP_METHOD_BLE_WIFI: "Provision WiFi over Bluetooth",
}

ADVANCED_VOICE_FIELDS = (
    CONF_SPOTIFY_SOURCE,
    CONF_MQTT_HOST,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    CONF_MQTT_PASSWORD,
    CONF_FIRMWARE_REPO,
    CONF_FIRMWARE_ASSET_PREFIX,
    CONF_FIRMWARE_DEVICE,
    CONF_FIRMWARE_CHANNEL,
    CONF_MAX_AUDIO_BYTES,
    CONF_ALLOW_OTA_ON_BATTERY,
    CONF_MIN_BATTERY_FOR_OTA,
)


def _clean(value: Any, default: Any = "") -> Any:
    """Normalize empty form values."""
    if value is None:
        return default
    if isinstance(value, str) and value.strip() == "":
        return default
    return value


def _bool(value: Any, default: bool = False) -> bool:
    return default if value is None else bool(value)


def _int(value: Any, default: int) -> int:
    try:
        return int(_clean(value, default))
    except (TypeError, ValueError):
        return default


def _ha_device_language(hass: Any) -> str:
    """Return supported device UI language from the current HA language."""
    language = str(getattr(getattr(hass, "config", None), "language", "") or "").lower()
    return "nl" if language.startswith("nl") else DEFAULT_DEVICE_LANGUAGE


def _advanced_enabled(flow: Any) -> bool:
    """Return the flow-local advanced toggle without HA deprecated properties."""
    return bool(getattr(flow, "_show_advanced_options", False))


def _request_advanced(flow: Any, user_input: dict[str, Any]) -> bool:
    """Enable flow-local advanced fields when the user checks the inline toggle."""
    if user_input.get(ADVANCED_OPTIONS_FIELD) and not _advanced_enabled(flow):
        setattr(flow, "_show_advanced_options", True)
        return True
    return False


def _default_local_url(pair_code: str | None) -> str:
    """Return an mDNS URL only when the input is the device ID suffix."""
    normalized = str(pair_code or "").strip()
    if not re.fullmatch(r"[0-9A-Fa-f]{12}", normalized):
        return ""
    return f"http://spotifydj-{normalized}.local"


def _valid_pair_code(pair_code: str) -> bool:
    """Accept the displayed 6-digit code or 12-character device suffix."""
    return bool(PAIR_CODE_PATTERN.fullmatch(str(pair_code or "").strip()))


def _merged_mqtt_defaults(hass: Any, source: dict[str, Any]) -> dict[str, Any]:
    """Use static MQTT defaults when SpotifyDJ has no stored values."""
    merged = dict(source)
    if _clean(merged.get(CONF_MQTT_HOST), "") == "":
        merged[CONF_MQTT_HOST] = DEFAULT_MQTT_HOST
    if _clean(merged.get(CONF_MQTT_PORT), "") == "":
        merged[CONF_MQTT_PORT] = DEFAULT_MQTT_PORT
    return merged


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _options_with_current(options: dict[str, str], current: Any = "") -> dict[str, str]:
    """Keep stored free-text values selectable after switching to dropdowns."""
    value = _clean(current, "")
    merged = dict(options)
    if value and value not in merged:
        merged[value] = str(value)
    return merged


def _state_attributes(hass: Any, entity_id: str) -> dict[str, Any]:
    states = getattr(hass, "states", None)
    if not entity_id or not states or not hasattr(states, "get"):
        return {}
    state = states.get(entity_id)
    return getattr(state, "attributes", {}) or {}


def _entity_options(
    hass: Any,
    domain: str,
    current: Any = "",
    *,
    include_empty: bool = True,
) -> dict[str, str]:
    """Return HA entity IDs as dropdown options."""
    options: dict[str, str] = {"": "Default"} if include_empty else {}
    states = getattr(hass, "states", None)
    if states and hasattr(states, "async_entity_ids"):
        try:
            for entity_id in sorted(states.async_entity_ids(domain)):
                state = states.get(entity_id) if hasattr(states, "get") else None
                name = getattr(state, "name", None) or entity_id
                options[entity_id] = f"{name} ({entity_id})"
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Could not list %s entities for SpotifyDJ config flow",
                domain,
                exc_info=True,
            )
    return _options_with_current(options, current)


def _ble_wifi_schema(devices: dict[str, str]) -> dict[Any, Any]:
    """Build BLE WiFi provisioning fields with discovered devices when present."""
    device_validator = vol.In(devices) if devices else str
    return {
        vol.Required(CONF_BLE_ADDRESS): device_validator,
        vol.Required(CONF_WIFI_SSID): str,
        vol.Optional(CONF_WIFI_PASSWORD, default=""): str,
    }


def _spotify_schema(include_advanced: bool = False) -> dict[Any, Any]:
    """Build Spotify OAuth fields; Client ID is an advanced override."""
    schema: dict[Any, Any] = {
        vol.Required(CONF_HA_EXTERNAL_URL): str,
        vol.Optional(
            CONF_SPOTIFY_MARKET,
            default=DEFAULT_SPOTIFY_MARKET,
        ): vol.In(SPOTIFY_MARKET_NAMES),
    }
    if include_advanced:
        schema[
            vol.Optional(
                CONF_SPOTIFY_CLIENT_ID,
                default=DEFAULT_SPOTIFY_CLIENT_ID,
            )
        ] = str
    else:
        schema[vol.Optional(ADVANCED_OPTIONS_FIELD, default=False)] = bool
    return schema


def _voice_name(voice: Any) -> tuple[str, str] | None:
    """Normalize HA TTS voice objects into value/label pairs."""
    if isinstance(voice, str):
        return (voice, voice) if voice else None
    if isinstance(voice, dict):
        voice_id = voice.get("voice_id") or voice.get("id") or voice.get("name")
        voice_name = voice.get("name") or voice_id
    else:
        voice_id = (
            getattr(voice, "voice_id", None)
            or getattr(voice, "id", None)
            or getattr(voice, "name", None)
        )
        voice_name = getattr(voice, "name", None) or voice_id
    return (str(voice_id), str(voice_name)) if voice_id else None


def _tts_voice_options(hass: Any, tts_engine: str, current: Any = "") -> dict[str, str]:
    """Return voice options exposed by a TTS entity, when known."""
    options: dict[str, str] = {"": "Default"}
    voices = _state_attributes(hass, tts_engine).get("supported_voices") or []
    voices = voices or _state_attributes(hass, tts_engine).get("voices") or []
    for voice in voices:
        parsed = _voice_name(voice)
        if parsed:
            voice_id, voice_name = parsed
            options[voice_id] = voice_name
    return _options_with_current(options, current)


def _get_assist_pipelines(hass: Any) -> list[Any]:
    """Return Assist pipelines when HA exposes them."""
    try:
        from homeassistant.components.assist_pipeline.pipeline import async_get_pipelines

        return list(async_get_pipelines(hass))
    except Exception:  # noqa: BLE001
        _LOGGER.debug("SpotifyDJ could not list Assist pipelines", exc_info=True)
        return []


def _get_assist_pipeline(hass: Any, pipeline_id: str) -> Any | None:
    if not pipeline_id:
        return None
    return next(
        (
            pipeline
            for pipeline in _get_assist_pipelines(hass)
            if getattr(pipeline, "id", None) == pipeline_id
        ),
        None,
    )


async def _assist_pipeline_options(hass: Any, current: Any = "") -> dict[str, str]:
    """Return Assist pipeline IDs as dropdown options."""
    options = {"": "Default"}
    for pipeline in _get_assist_pipelines(hass):
        pipeline_id = getattr(pipeline, "id", "")
        if pipeline_id:
            options[pipeline_id] = getattr(pipeline, "name", "") or pipeline_id
    return _options_with_current(options, current)


def _base_voice_schema(
    defaults: dict[str, Any],
    *,
    assist_options: dict[str, str],
    stt_options: dict[str, str],
    tts_options: dict[str, str],
    tts_voice_options: dict[str, str],
    stt_engine: str,
    tts_engine: str,
    tts_voice: str,
    player_options: dict[str, str],
) -> dict[Any, Any]:
    """Build the non-advanced voice settings schema."""
    voice_validator = vol.In(tts_voice_options) if len(tts_voice_options) > 1 else str
    player_default = defaults.get(CONF_SPOTIFY_PLAYER, "")
    return {
        vol.Optional(
            CONF_ASSIST_PIPELINE_ID,
            default=defaults.get(CONF_ASSIST_PIPELINE_ID, ""),
        ): vol.In(assist_options),
        vol.Optional(CONF_STT_ENGINE, default=stt_engine): vol.In(stt_options),
        vol.Optional(CONF_TTS_ENGINE, default=tts_engine): vol.In(tts_options),
        vol.Optional(
            CONF_TTS_LANGUAGE,
            default=defaults.get(CONF_TTS_LANGUAGE, DEFAULT_TTS_LANGUAGE),
        ): str,
        vol.Optional(CONF_TTS_VOICE, default=tts_voice): voice_validator,
        vol.Optional(
            CONF_DJ_RESPONSE_ENABLED,
            default=defaults.get(
                CONF_DJ_RESPONSE_ENABLED,
                DEFAULT_DJ_RESPONSE_ENABLED,
            ),
        ): bool,
        vol.Optional(
            CONF_DJ_STYLE,
            default=defaults.get(CONF_DJ_STYLE, DEFAULT_DJ_STYLE),
        ): vol.In(DJ_STYLE_NAMES),
        vol.Required(
            CONF_SPOTIFY_PLAYER,
            default=player_default,
        ): vol.In(player_options),
        vol.Optional(CONF_LIKED_PROXY, default=defaults.get(CONF_LIKED_PROXY, "")): str,
    }


def _advanced_voice_schema(defaults: dict[str, Any]) -> dict[Any, Any]:
    """Build advanced firmware/OTA settings hidden behind HA advanced mode."""
    firmware_channel_options = _options_with_current(
        FIRMWARE_CHANNEL_NAMES,
        defaults.get(CONF_FIRMWARE_CHANNEL, DEFAULT_FIRMWARE_CHANNEL),
    )
    return {
        vol.Optional(
            CONF_SPOTIFY_SOURCE,
            default=defaults.get(CONF_SPOTIFY_SOURCE, ""),
        ): str,
        vol.Optional(
            CONF_MQTT_HOST,
            default=defaults.get(CONF_MQTT_HOST, ""),
        ): str,
        vol.Optional(
            CONF_MQTT_PORT,
            default=defaults.get(CONF_MQTT_PORT, DEFAULT_MQTT_PORT),
        ): int,
        vol.Optional(
            CONF_MQTT_USERNAME,
            default=defaults.get(CONF_MQTT_USERNAME, ""),
        ): str,
        vol.Optional(
            CONF_MQTT_PASSWORD,
            default=defaults.get(CONF_MQTT_PASSWORD, ""),
        ): str,
        vol.Optional(
            CONF_FIRMWARE_REPO,
            default=defaults.get(CONF_FIRMWARE_REPO, DEFAULT_FIRMWARE_REPO),
        ): str,
        vol.Optional(
            CONF_FIRMWARE_ASSET_PREFIX,
            default=defaults.get(
                CONF_FIRMWARE_ASSET_PREFIX,
                DEFAULT_FIRMWARE_ASSET_PREFIX,
            ),
        ): str,
        vol.Optional(
            CONF_FIRMWARE_DEVICE,
            default=defaults.get(CONF_FIRMWARE_DEVICE, DEFAULT_FIRMWARE_DEVICE),
        ): str,
        vol.Optional(
            CONF_FIRMWARE_CHANNEL,
            default=defaults.get(CONF_FIRMWARE_CHANNEL, DEFAULT_FIRMWARE_CHANNEL),
        ): vol.In(firmware_channel_options),
        vol.Optional(
            CONF_MAX_AUDIO_BYTES,
            default=defaults.get(CONF_MAX_AUDIO_BYTES, DEFAULT_MAX_AUDIO_BYTES),
        ): int,
        vol.Optional(
            CONF_ALLOW_OTA_ON_BATTERY,
            default=defaults.get(CONF_ALLOW_OTA_ON_BATTERY, True),
        ): bool,
        vol.Optional(
            CONF_MIN_BATTERY_FOR_OTA,
            default=defaults.get(CONF_MIN_BATTERY_FOR_OTA, DEFAULT_MIN_BATTERY_FOR_OTA),
        ): int,
        vol.Optional(
            CONF_DJ_RESPONSE_TTL_SECONDS,
            default=defaults.get(
                CONF_DJ_RESPONSE_TTL_SECONDS,
                DEFAULT_DJ_RESPONSE_TTL_SECONDS,
            ),
        ): int,
    }


async def _voice_schema(
    hass: Any,
    defaults: dict[str, Any],
    *,
    include_advanced: bool = False,
) -> vol.Schema:
    """Build a voice/options schema with dropdowns where HA can provide choices."""
    pipeline = _get_assist_pipeline(hass, defaults.get(CONF_ASSIST_PIPELINE_ID, ""))
    pipeline_stt_engine = getattr(pipeline, "stt_engine", None) if pipeline else None
    pipeline_tts_engine = getattr(pipeline, "tts_engine", None) if pipeline else None
    pipeline_tts_voice = getattr(pipeline, "tts_voice", None) if pipeline else None
    stt_engine = defaults.get(CONF_STT_ENGINE) or pipeline_stt_engine or DEFAULT_STT_ENGINE
    tts_engine = defaults.get(CONF_TTS_ENGINE) or pipeline_tts_engine or DEFAULT_TTS_ENGINE
    tts_voice = defaults.get(CONF_TTS_VOICE) or pipeline_tts_voice or ""

    schema = _base_voice_schema(
        defaults,
        assist_options=await _assist_pipeline_options(
            hass,
            defaults.get(CONF_ASSIST_PIPELINE_ID, ""),
        ),
        stt_options=_entity_options(hass, "stt", stt_engine),
        tts_options=_entity_options(hass, "tts", tts_engine),
        tts_voice_options=_tts_voice_options(hass, tts_engine, tts_voice),
        stt_engine=stt_engine,
        tts_engine=tts_engine,
        tts_voice=tts_voice,
        player_options=_entity_options(
            hass,
            "media_player",
            defaults.get(CONF_SPOTIFY_PLAYER, ""),
            include_empty=False,
        ),
    )
    if include_advanced:
        schema.update(_advanced_voice_schema(defaults))
    else:
        schema[vol.Optional(ADVANCED_OPTIONS_FIELD, default=False)] = bool
    return vol.Schema(schema)


def _voice_defaults(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return voice/options config with safe defaults."""
    source = data or {}
    dj_style = _clean(
        source.get(CONF_DJ_STYLE) or source.get(CONF_DJ_PROFILE),
        DEFAULT_DJ_STYLE,
    )
    if dj_style not in DJ_STYLES:
        dj_style = DEFAULT_DJ_STYLE
    return {
        CONF_ASSIST_PIPELINE_ID: _clean(
            source.get(CONF_ASSIST_PIPELINE_ID),
            DEFAULT_ASSIST_PIPELINE_ID,
        ),
        CONF_STT_ENGINE: _clean(source.get(CONF_STT_ENGINE), DEFAULT_STT_ENGINE),
        CONF_TTS_ENGINE: _clean(source.get(CONF_TTS_ENGINE), DEFAULT_TTS_ENGINE),
        CONF_TTS_LANGUAGE: _clean(source.get(CONF_TTS_LANGUAGE), DEFAULT_TTS_LANGUAGE),
        CONF_TTS_VOICE: _clean(source.get(CONF_TTS_VOICE), DEFAULT_TTS_VOICE),
        CONF_DJ_RESPONSE_ENABLED: _bool(
            source.get(CONF_DJ_RESPONSE_ENABLED),
            DEFAULT_DJ_RESPONSE_ENABLED,
        ),
        CONF_DJ_RESPONSE_TTL_SECONDS: _int(
            source.get(CONF_DJ_RESPONSE_TTL_SECONDS),
            DEFAULT_DJ_RESPONSE_TTL_SECONDS,
        ),
        CONF_DJ_STYLE: dj_style,
        CONF_DJ_PROFILE: dj_style,
        CONF_FIRMWARE_REPO: _clean(
            source.get(CONF_FIRMWARE_REPO),
            DEFAULT_FIRMWARE_REPO,
        ),
        CONF_FIRMWARE_ASSET_PREFIX: _clean(
            source.get(CONF_FIRMWARE_ASSET_PREFIX),
            DEFAULT_FIRMWARE_ASSET_PREFIX,
        ),
        CONF_FIRMWARE_DEVICE: _clean(
            source.get(CONF_FIRMWARE_DEVICE),
            DEFAULT_FIRMWARE_DEVICE,
        ),
        CONF_FIRMWARE_CHANNEL: _clean(
            source.get(CONF_FIRMWARE_CHANNEL),
            DEFAULT_FIRMWARE_CHANNEL,
        ),
        CONF_MAX_AUDIO_BYTES: _int(
            source.get(CONF_MAX_AUDIO_BYTES),
            DEFAULT_MAX_AUDIO_BYTES,
        ),
        CONF_ALLOW_OTA_ON_BATTERY: _bool(source.get(CONF_ALLOW_OTA_ON_BATTERY), True),
        CONF_MIN_BATTERY_FOR_OTA: _int(
            source.get(CONF_MIN_BATTERY_FOR_OTA),
            DEFAULT_MIN_BATTERY_FOR_OTA,
        ),
        CONF_SPOTIFY_PLAYER: _clean(source.get(CONF_SPOTIFY_PLAYER), ""),
        CONF_SPOTIFY_SOURCE: _clean(source.get(CONF_SPOTIFY_SOURCE), ""),
        CONF_MQTT_HOST: _clean(source.get(CONF_MQTT_HOST), ""),
        CONF_MQTT_PORT: _int(source.get(CONF_MQTT_PORT), DEFAULT_MQTT_PORT),
        CONF_MQTT_USERNAME: _clean(source.get(CONF_MQTT_USERNAME), ""),
        CONF_MQTT_PASSWORD: _clean(source.get(CONF_MQTT_PASSWORD), ""),
        CONF_LIKED_PROXY: _clean(source.get(CONF_LIKED_PROXY), ""),
    }


def _voice_errors(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate required voice/options fields."""
    if not _clean(user_input.get(CONF_SPOTIFY_PLAYER), ""):
        return {CONF_SPOTIFY_PLAYER: "spotify_player_required"}
    return {}


class SpotifyDJConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the SpotifyDJ config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._pairing: dict[str, Any] = {}
        self._spotify: dict[str, Any] = {}
        self._oauth: dict[str, str] = {}
        self._show_advanced_options = False

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Choose setup path."""
        if user_input is not None:
            method = user_input.get(CONF_SETUP_METHOD, DEFAULT_SETUP_METHOD)
            if method == SETUP_METHOD_BLE_WIFI:
                return await self.async_step_ble_wifi()
            return await self.async_step_pair()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SETUP_METHOD,
                        default=DEFAULT_SETUP_METHOD,
                    ): vol.In(SETUP_METHOD_NAMES),
                }
            ),
        )

    async def async_step_ble_wifi(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Provision WiFi credentials to a SpotifyDJ setup device over BLE."""
        errors: dict[str, str] = {}
        devices = await async_discover_devices(self.hass)

        if user_input is not None:
            address = str(user_input.get(CONF_BLE_ADDRESS, "")).strip()
            ssid = str(user_input.get(CONF_WIFI_SSID, "")).strip()
            password = str(user_input.get(CONF_WIFI_PASSWORD, ""))
            if not address:
                errors[CONF_BLE_ADDRESS] = "ble_device_required"
            elif not ssid:
                errors[CONF_WIFI_SSID] = "wifi_ssid_required"
            else:
                try:
                    status = await async_provision_wifi(
                        self.hass,
                        address,
                        ssid,
                        password,
                    )
                    _LOGGER.debug(
                        "SpotifyDJ BLE WiFi provisioning completed: %s",
                        status.get("state"),
                    )
                    return await self.async_step_pair()
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.warning("SpotifyDJ BLE WiFi provisioning failed: %s", exc)
                    errors["base"] = "ble_wifi_failed"

        return self.async_show_form(
            step_id="ble_wifi",
            data_schema=vol.Schema(_ble_wifi_schema(devices)),
            errors=errors,
        )

    async def async_step_pair(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Pair the SpotifyDJ device using the displayed pair code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if _request_advanced(self, user_input):
                return await self.async_step_pair()
            pair_code = str(user_input.get(CONF_PAIR_CODE, "")).strip()
            self._last_pair_code = pair_code
            if not pair_code:
                errors[CONF_PAIR_CODE] = "missing_pair_code"
            elif not _valid_pair_code(pair_code):
                errors[CONF_PAIR_CODE] = "invalid_pair_code"
            else:
                device_id = f"spotifydj-{pair_code}"
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()
                self._pairing = {
                    CONF_PAIR_CODE: pair_code,
                    CONF_DEVICE_ID: device_id,
                    CONF_DEVICE_NAME: _clean(
                        user_input.get(CONF_DEVICE_NAME),
                        DEFAULT_DEVICE_NAME,
                    ),
                    CONF_DEVICE_LANGUAGE: _clean(
                        user_input.get(CONF_DEVICE_LANGUAGE),
                        _ha_device_language(getattr(self, "hass", None)),
                    ),
                    CONF_DEVICE_TOKEN: secrets.token_urlsafe(32),
                    CONF_LOCAL_URL: _clean(
                        user_input.get(CONF_LOCAL_URL),
                        _default_local_url(pair_code),
                    ),
                }
                return await self.async_step_spotify()

        return self.async_show_form(
            step_id="pair",
            data_schema=vol.Schema(self._user_schema()),
            errors=errors,
        )

    def _user_schema(self) -> dict[Any, Any]:
        """Build pairing schema; manual device URL is advanced-only."""
        pair_code = getattr(self, "_last_pair_code", "")
        schema: dict[Any, Any] = {
            vol.Required(CONF_PAIR_CODE): str,
            vol.Optional(
                CONF_DEVICE_NAME,
                default=DEFAULT_DEVICE_NAME,
            ): str,
            vol.Optional(
                CONF_DEVICE_LANGUAGE,
                default=_ha_device_language(getattr(self, "hass", None)),
            ): vol.In(DEVICE_LANGUAGE_NAMES),
        }
        if not _advanced_enabled(self):
            schema[vol.Optional(ADVANCED_OPTIONS_FIELD, default=False)] = bool
        else:
            schema[vol.Optional(CONF_LOCAL_URL, default=_default_local_url(pair_code))] = str
        return schema

    async def async_step_spotify(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Collect Spotify Client ID and HTTPS HA external URL."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if _request_advanced(self, user_input):
                return await self.async_step_spotify()
            client_id = str(
                user_input.get(CONF_SPOTIFY_CLIENT_ID)
                or DEFAULT_SPOTIFY_CLIENT_ID
            ).strip()
            external_url = str(user_input.get(CONF_HA_EXTERNAL_URL, "")).strip().rstrip("/")
            if not client_id:
                errors[CONF_SPOTIFY_CLIENT_ID] = "spotify_client_id_required"
            elif not external_url:
                errors[CONF_HA_EXTERNAL_URL] = "external_url_required"
            elif not external_url.startswith("https://"):
                errors[CONF_HA_EXTERNAL_URL] = "external_url_https_required"
            elif not _is_https_url(external_url):
                errors[CONF_HA_EXTERNAL_URL] = "external_url_invalid"
            else:
                try:
                    self._prepare_spotify_oauth(client_id, external_url, user_input)
                    register_http_views(self.hass)
                    return await self.async_step_spotify_oauth()
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("Could not start Spotify OAuth")
                    errors["base"] = "oauth_setup_failed"

        return self.async_show_form(
            step_id="spotify",
            data_schema=vol.Schema(
                _spotify_schema(_advanced_enabled(self))
            ),
            errors=errors,
            description_placeholders={
                "callback_path": "/api/spotify_dj/spotify/callback",
            },
        )

    def _prepare_spotify_oauth(
        self,
        client_id: str,
        external_url: str,
        user_input: dict[str, Any],
    ) -> None:
        """Store pending Spotify OAuth context before opening the external step."""
        redirect_uri = build_redirect_uri(external_url)
        self._spotify = {
            CONF_SPOTIFY_CLIENT_ID: client_id,
            CONF_HA_EXTERNAL_URL: external_url,
            CONF_SPOTIFY_MARKET: _clean(
                user_input.get(CONF_SPOTIFY_MARKET),
                DEFAULT_SPOTIFY_MARKET,
            ),
            CONF_SPOTIFY_SCOPES: DEFAULT_SPOTIFY_SCOPES,
        }
        self._oauth = {
            "state": secrets.token_urlsafe(24),
            "code_verifier": create_code_verifier(),
            "redirect_uri": redirect_uri,
        }
        self._oauth["authorize_url"] = build_authorize_url(
            client_id,
            redirect_uri,
            DEFAULT_SPOTIFY_SCOPES,
            self._oauth["state"],
            self._oauth["code_verifier"],
        )
        pending = self.hass.data.setdefault(DOMAIN, {}).setdefault(
            "config_flow_oauth_pending",
            {},
        )
        pending[self._oauth["state"]] = {
            "flow_id": self.flow_id,
            "client_id": client_id,
            "code_verifier": self._oauth["code_verifier"],
            "redirect_uri": redirect_uri,
            "market": self._spotify[CONF_SPOTIFY_MARKET],
            "scopes": DEFAULT_SPOTIFY_SCOPES,
        }

    async def async_step_spotify_oauth(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Open Spotify OAuth as an external step and finish from the callback."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._handle_spotify_oauth_result(user_input)
            if not errors:
                return self.async_external_step_done(next_step_id="voice")

        if errors:
            return self.async_show_form(
                step_id="spotify_oauth",
                data_schema=vol.Schema({}),
                errors=errors,
            )

        if not self._oauth.get("authorize_url"):
            return self.async_show_form(
                step_id="spotify_oauth",
                data_schema=vol.Schema({}),
                errors={"base": "oauth_setup_failed"},
            )

        return self.async_external_step(
            step_id="spotify_oauth",
            url=self._oauth["authorize_url"],
            description_placeholders={
                "redirect_uri": self._oauth.get("redirect_uri", ""),
            },
        )

    def _handle_spotify_oauth_result(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Read the callback result stored by the HTTP OAuth callback."""
        state = str(user_input.get("state", "")).strip()
        if not state:
            return {"base": "oauth_failed"}
        try:
            result = (
                self.hass.data.get(DOMAIN, {})
                .get("config_flow_oauth_results", {})
                .pop(state, None)
            )
            if not result:
                return {"base": "oauth_not_completed"}
            self._spotify[CONF_SPOTIFY_REFRESH_TOKEN] = result[
                CONF_SPOTIFY_REFRESH_TOKEN
            ]
            self._spotify[CONF_SPOTIFY_MARKET] = result.get(
                CONF_SPOTIFY_MARKET,
                DEFAULT_SPOTIFY_MARKET,
            )
            self._spotify[CONF_SPOTIFY_SCOPES] = result.get(
                CONF_SPOTIFY_SCOPES,
                DEFAULT_SPOTIFY_SCOPES,
            )
            return {}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Spotify OAuth failed")
            return {"base": "oauth_failed"}

    async def async_step_voice(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Collect optional voice settings. Empty fields are allowed."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if _request_advanced(self, user_input):
                return await self.async_step_voice()
            errors = _voice_errors(user_input)
            if not errors:
                data: dict[str, Any] = {}
                data.update(self._pairing)
                data.update(self._spotify)
                data.update(_voice_defaults(user_input))
                return self.async_create_entry(
                    title=data.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME),
                    data=data,
                )

        return self.async_show_form(
            step_id="voice",
            data_schema=await _voice_schema(
                self.hass,
                _voice_defaults(_merged_mqtt_defaults(self.hass, {})),
                include_advanced=_advanced_enabled(self),
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "SpotifyDJOptionsFlow":
        """Create options flow."""
        return SpotifyDJOptionsFlow(config_entry)


class SpotifyDJOptionsFlow(config_entries.OptionsFlow):
    """Handle SpotifyDJ options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._show_advanced_options = False

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Manage SpotifyDJ options."""
        current = {**self._config_entry.data, **self._config_entry.options}
        defaults = _voice_defaults(_merged_mqtt_defaults(self.hass, current))
        errors: dict[str, str] = {}
        if user_input is not None:
            if _request_advanced(self, user_input):
                return await self.async_step_init()
            errors = _voice_errors(user_input)
            if not errors:
                merged = dict(current)
                merged.update(user_input)
                return self.async_create_entry(title="", data=_voice_defaults(merged))

        return self.async_show_form(
            step_id="init",
            data_schema=await _voice_schema(
                self.hass,
                defaults,
                include_advanced=_advanced_enabled(self),
            ),
            errors=errors,
        )
