"""Config flow for DJConnect."""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from custom_components.djconnect import register_http_views

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
    CONF_PAIR_CODE,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_MARKET,
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
OPTIONS_ACTION_FIELD = "options_action"
OPTIONS_ACTION_SAVE = "save_options"
OPTIONS_ACTION_RETRY_PAIRING = "retry_device_pairing"
OPTIONS_ACTION_REPAIR = "repair_device_pairing"
OPTIONS_ACTION_SPOTIFY_REAUTH = "spotify_reauthorize"
BLE_ACTION_FIELD = "ble_action"
BLE_ACTION_PROVISION = "provision_wifi"
BLE_ACTION_RETRY_SCAN = "retry_ble_scan"
BLE_ACTION_CONTINUE_PAIRING = "continue_to_pairing"
BLE_DISCOVERY_TIMEOUT = 5
BLE_PROVISION_TIMEOUT = 25
SPOTIFY_MARKET_NAMES = {
    "NL": "Netherlands",
    "BE": "Belgium",
    "DE": "Germany",
    "FR": "France",
    "GB": "United Kingdom",
    "US": "United States",
}
SETUP_METHOD_NAMES_EN = {
    SETUP_METHOD_PAIR_EXISTING: "Pair existing WiFi device",
    SETUP_METHOD_BLE_WIFI: "Provision WiFi over Bluetooth",
}
SETUP_METHOD_NAMES_NL = {
    SETUP_METHOD_PAIR_EXISTING: "Bestaand WiFi device koppelen",
    SETUP_METHOD_BLE_WIFI: "WiFi via Bluetooth provisionen",
}
BLE_ACTION_NAMES_EN = {
    BLE_ACTION_PROVISION: "Write WiFi over Bluetooth",
    BLE_ACTION_RETRY_SCAN: "Rescan Bluetooth devices",
    BLE_ACTION_CONTINUE_PAIRING: "Continue to pairing",
}
BLE_ACTION_NAMES_NL = {
    BLE_ACTION_PROVISION: "WiFi via Bluetooth schrijven",
    BLE_ACTION_RETRY_SCAN: "Bluetooth devices opnieuw scannen",
    BLE_ACTION_CONTINUE_PAIRING: "Doorgaan naar koppelen",
}
OPTIONS_ACTION_NAMES_EN = {
    OPTIONS_ACTION_SAVE: "Save options",
    OPTIONS_ACTION_SPOTIFY_REAUTH: "Reauthorize Spotify",
    OPTIONS_ACTION_RETRY_PAIRING: "Retry pairing with current code",
    OPTIONS_ACTION_REPAIR: "Re-pair with new pairing code",
}
OPTIONS_ACTION_NAMES_NL = {
    OPTIONS_ACTION_SAVE: "Instellingen opslaan",
    OPTIONS_ACTION_SPOTIFY_REAUTH: "Spotify opnieuw autoriseren",
    OPTIONS_ACTION_RETRY_PAIRING: "Koppelen opnieuw proberen met huidige code",
    OPTIONS_ACTION_REPAIR: "Opnieuw koppelen met nieuwe koppelcode",
}

ADVANCED_VOICE_FIELDS = (
    CONF_SPOTIFY_SOURCE,
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


def _defaultable_value(
    source: dict[str, Any],
    key: str,
    default: Any,
    *,
    preserve_empty: bool,
) -> Any:
    """Return an option value while preserving explicit empty `Default` choices."""
    if preserve_empty and key in source and source.get(key) in (None, ""):
        return ""
    return _clean(source.get(key), default)


def _ha_device_language(hass: Any) -> str:
    """Return supported device UI language from the current HA language."""
    language = str(getattr(getattr(hass, "config", None), "language", "") or "").lower()
    return "nl" if language.startswith("nl") else DEFAULT_DEVICE_LANGUAGE


def _setup_method_names(hass: Any) -> dict[str, str]:
    """Return setup method labels in the current Home Assistant language."""
    language = str(getattr(getattr(hass, "config", None), "language", "") or "").lower()
    return SETUP_METHOD_NAMES_NL if language.startswith("nl") else SETUP_METHOD_NAMES_EN


def _ble_action_names(hass: Any) -> dict[str, str]:
    """Return mutually exclusive BLE setup actions in the current HA language."""
    language = str(getattr(getattr(hass, "config", None), "language", "") or "").lower()
    return BLE_ACTION_NAMES_NL if language.startswith("nl") else BLE_ACTION_NAMES_EN


def _options_action_names(hass: Any) -> dict[str, str]:
    """Return options flow actions in the current HA language."""
    language = str(getattr(getattr(hass, "config", None), "language", "") or "").lower()
    return OPTIONS_ACTION_NAMES_NL if language.startswith("nl") else OPTIONS_ACTION_NAMES_EN


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
    return f"http://djconnect-lilygo-{normalized}.local"


def _valid_pair_code(pair_code: str) -> bool:
    """Accept the displayed 6-digit code or 12-character device suffix."""
    return bool(PAIR_CODE_PATTERN.fullmatch(str(pair_code or "").strip()))


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
                "Could not list %s entities for DJConnect config flow",
                domain,
                exc_info=True,
            )
    return _options_with_current(options, current)


def _ble_wifi_schema(devices: dict[str, str], hass: Any = None) -> dict[Any, Any]:
    """Build BLE WiFi provisioning fields with discovered devices when present."""
    device_validator = vol.In({"": "Select device", **devices}) if devices else str
    default_device = next(iter(devices), "") if len(devices) == 1 else ""
    return {
        vol.Required(BLE_ACTION_FIELD, default=BLE_ACTION_PROVISION): vol.In(
            _ble_action_names(hass)
        ),
        vol.Optional(CONF_BLE_ADDRESS, default=default_device): device_validator,
        vol.Optional(CONF_WIFI_SSID, default=""): str,
        vol.Optional(CONF_WIFI_PASSWORD, default=""): str,
    }


async def _discover_ble_devices_safe(hass: Any) -> dict[str, str]:
    """Discover setup devices without letting Bluetooth stall the config flow."""
    try:
        return await asyncio.wait_for(
            async_discover_devices(hass),
            timeout=BLE_DISCOVERY_TIMEOUT,
        )
    except TimeoutError:
        _LOGGER.warning("DJConnect BLE discovery timed out; allowing manual address entry")
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("DJConnect BLE discovery failed: %s", exc)
    return {}


async def _provision_ble_wifi_safe(
    hass: Any,
    address: str,
    ssid: str,
    password: str,
) -> dict[str, Any]:
    """Write WiFi credentials with a hard timeout so setup can continue."""
    try:
        return await asyncio.wait_for(
            async_provision_wifi(hass, address, ssid, password),
            timeout=BLE_PROVISION_TIMEOUT,
        )
    except TimeoutError as exc:
        raise RuntimeError(
            "Bluetooth WiFi provisioning timed out. Put the device back in setup "
            "mode or use normal WiFi pairing."
        ) from exc


def _spotify_schema(include_advanced: bool = False) -> dict[Any, Any]:
    """Build Spotify OAuth fields; Client ID is an advanced override."""
    return _spotify_schema_with_defaults(include_advanced)


def _spotify_schema_with_defaults(
    include_advanced: bool = False,
    *,
    external_url: str = "",
) -> dict[Any, Any]:
    """Build Spotify OAuth fields; Client ID is an advanced override."""
    schema: dict[Any, Any] = {
        vol.Required(CONF_HA_EXTERNAL_URL, default=external_url): str,
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


async def _async_default_external_url(hass: Any) -> str:
    """Return HA's configured external URL when available."""
    try:
        from homeassistant.helpers import network

        url = await network.async_get_url(
            hass,
            prefer_external=True,
            allow_internal=False,
        )
    except Exception:  # noqa: BLE001
        url = ""
    if not url:
        url = await _async_cloud_external_url(hass)
    if not url:
        url = str(getattr(getattr(hass, "config", None), "external_url", "") or "")
    return url.strip().rstrip("/")


async def _async_cloud_external_url(hass: Any) -> str:
    """Return the Home Assistant Cloud remote UI URL when exposed by HA."""
    try:
        from homeassistant.components import cloud

        remote_url = getattr(cloud, "async_remote_ui_url", None)
        if remote_url is not None:
            return str(await remote_url(hass) or "")
    except Exception:  # noqa: BLE001
        _LOGGER.debug("DJConnect could not read Home Assistant Cloud URL", exc_info=True)
    cloud_data = getattr(hass, "data", {}).get("cloud") if hasattr(hass, "data") else None
    for attr in ("remote_ui_url", "remote_url", "url"):
        value = getattr(cloud_data, attr, "")
        if callable(value):
            try:
                value = value()
            except Exception:  # noqa: BLE001
                value = ""
        if value:
            return str(value)
    return ""


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


def _sync_tts_voice_with_engine(hass: Any, values: dict[str, Any]) -> dict[str, Any]:
    """Clear a stale TTS voice when the selected TTS engine cannot use it."""
    synced = dict(values)
    engine = str(synced.get(CONF_TTS_ENGINE) or "").strip()
    voice = str(synced.get(CONF_TTS_VOICE) or "").strip()
    if not voice:
        synced[CONF_TTS_VOICE] = ""
        return synced
    if not engine:
        synced[CONF_TTS_VOICE] = ""
        return synced
    supported = _tts_voice_options(hass, engine, "")
    if len(supported) > 1 and voice not in supported:
        synced[CONF_TTS_VOICE] = ""
    return synced


def _get_assist_pipelines(hass: Any) -> list[Any]:
    """Return Assist pipelines when HA exposes them."""
    try:
        from homeassistant.components.assist_pipeline.pipeline import async_get_pipelines

        return list(async_get_pipelines(hass))
    except Exception:  # noqa: BLE001
        _LOGGER.debug("DJConnect could not list Assist pipelines", exc_info=True)
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
    options_actions: dict[str, str] | None = None,
) -> dict[Any, Any]:
    """Build the non-advanced voice settings schema."""
    stt_validator = vol.In(stt_options) if len(stt_options) > 1 else str
    voice_validator = vol.In(tts_voice_options) if len(tts_voice_options) > 1 else str
    schema: dict[Any, Any] = {}
    if options_actions is not None:
        schema[
            vol.Required(
                OPTIONS_ACTION_FIELD,
                default=OPTIONS_ACTION_SAVE,
            )
        ] = vol.In(options_actions)
    schema.update({
        vol.Optional(
            CONF_ASSIST_PIPELINE_ID,
            default=defaults.get(CONF_ASSIST_PIPELINE_ID, ""),
        ): vol.In(assist_options),
        vol.Optional(CONF_STT_ENGINE, default=stt_engine): stt_validator,
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
        vol.Optional(CONF_LIKED_PROXY, default=defaults.get(CONF_LIKED_PROXY, "")): str,
    })
    return schema


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
    include_options_action: bool = False,
) -> vol.Schema:
    """Build a voice/options schema with dropdowns where HA can provide choices."""
    pipeline = _get_assist_pipeline(hass, defaults.get(CONF_ASSIST_PIPELINE_ID, ""))
    pipeline_stt_engine = getattr(pipeline, "stt_engine", None) if pipeline else None
    pipeline_tts_engine = getattr(pipeline, "tts_engine", None) if pipeline else None
    pipeline_tts_voice = getattr(pipeline, "tts_voice", None) if pipeline else None
    stt_engine = (
        defaults.get(CONF_STT_ENGINE)
        if CONF_STT_ENGINE in defaults
        else pipeline_stt_engine or DEFAULT_STT_ENGINE
    )
    tts_engine = (
        defaults.get(CONF_TTS_ENGINE)
        if CONF_TTS_ENGINE in defaults
        else pipeline_tts_engine or DEFAULT_TTS_ENGINE
    )
    tts_voice = (
        defaults.get(CONF_TTS_VOICE)
        if CONF_TTS_VOICE in defaults
        else pipeline_tts_voice or ""
    )

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
        options_actions=(
            _options_action_names(hass)
            if include_options_action
            else None
        ),
    )
    if include_advanced:
        schema.update(_advanced_voice_schema(defaults))
    else:
        schema[vol.Optional(ADVANCED_OPTIONS_FIELD, default=False)] = bool
    return vol.Schema(schema)


def _voice_defaults(
    data: dict[str, Any] | None = None,
    *,
    preserve_empty: bool = False,
) -> dict[str, Any]:
    """Return voice/options config with safe defaults."""
    source = data or {}
    dj_style = _clean(
        source.get(CONF_DJ_STYLE) or source.get(CONF_DJ_PROFILE),
        DEFAULT_DJ_STYLE,
    )
    if dj_style not in DJ_STYLES:
        dj_style = DEFAULT_DJ_STYLE
    return {
        CONF_ASSIST_PIPELINE_ID: _defaultable_value(
            source,
            CONF_ASSIST_PIPELINE_ID,
            DEFAULT_ASSIST_PIPELINE_ID,
            preserve_empty=preserve_empty,
        ),
        CONF_STT_ENGINE: _defaultable_value(
            source,
            CONF_STT_ENGINE,
            DEFAULT_STT_ENGINE,
            preserve_empty=preserve_empty,
        ),
        CONF_TTS_ENGINE: _defaultable_value(
            source,
            CONF_TTS_ENGINE,
            DEFAULT_TTS_ENGINE,
            preserve_empty=preserve_empty,
        ),
        CONF_TTS_LANGUAGE: _clean(source.get(CONF_TTS_LANGUAGE), DEFAULT_TTS_LANGUAGE),
        CONF_TTS_VOICE: _defaultable_value(
            source,
            CONF_TTS_VOICE,
            DEFAULT_TTS_VOICE,
            preserve_empty=preserve_empty,
        ),
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
        CONF_SPOTIFY_SOURCE: _clean(source.get(CONF_SPOTIFY_SOURCE), ""),
        CONF_LIKED_PROXY: _clean(source.get(CONF_LIKED_PROXY), ""),
    }


def _voice_errors(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate required voice/options fields."""
    return {}


class DJConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the DJConnect config flow."""

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
                    ): vol.In(_setup_method_names(getattr(self, "hass", None))),
                }
            ),
        )

    async def async_step_ble_wifi(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Provision WiFi credentials to a DJConnect setup device over BLE."""
        errors: dict[str, str] = {}
        devices = await _discover_ble_devices_safe(self.hass)

        if user_input is not None:
            action = user_input.get(BLE_ACTION_FIELD, BLE_ACTION_PROVISION)
            if action == BLE_ACTION_CONTINUE_PAIRING:
                return await self.async_step_pair()
            if action == BLE_ACTION_RETRY_SCAN:
                return await self.async_step_ble_wifi()
            address = str(user_input.get(CONF_BLE_ADDRESS, "")).strip()
            ssid = str(user_input.get(CONF_WIFI_SSID, "")).strip()
            password = str(user_input.get(CONF_WIFI_PASSWORD, ""))
            if not address:
                errors[CONF_BLE_ADDRESS] = "ble_device_required"
            elif not ssid:
                errors[CONF_WIFI_SSID] = "wifi_ssid_required"
            else:
                try:
                    status = await _provision_ble_wifi_safe(
                        self.hass,
                        address,
                        ssid,
                        password,
                    )
                    _LOGGER.debug(
                        "DJConnect BLE WiFi provisioning completed: %s",
                        status.get("state"),
                    )
                    return await self.async_step_pair()
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.warning("DJConnect BLE WiFi provisioning failed: %s", exc)
                    errors["base"] = "ble_wifi_failed"

        return self.async_show_form(
            step_id="ble_wifi",
            data_schema=vol.Schema(_ble_wifi_schema(devices, getattr(self, "hass", None))),
            errors=errors,
        )

    async def async_step_pair(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Pair the DJConnect device using the displayed pair code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if _request_advanced(self, user_input):
                return await self.async_step_pair()
            method = user_input.get(CONF_SETUP_METHOD, SETUP_METHOD_PAIR_EXISTING)
            if method == SETUP_METHOD_BLE_WIFI:
                return await self.async_step_ble_wifi()
            pair_code = str(user_input.get(CONF_PAIR_CODE, "")).strip()
            self._last_pair_code = pair_code
            if not pair_code:
                errors[CONF_PAIR_CODE] = "missing_pair_code"
            elif not _valid_pair_code(pair_code):
                errors[CONF_PAIR_CODE] = "invalid_pair_code"
            else:
                device_id = f"djconnect-{pair_code}"
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
            vol.Optional(
                CONF_SETUP_METHOD,
                default=SETUP_METHOD_PAIR_EXISTING,
            ): vol.In(_setup_method_names(getattr(self, "hass", None))),
            vol.Optional(CONF_PAIR_CODE): str,
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
                _spotify_schema_with_defaults(
                    _advanced_enabled(self),
                    external_url=await _async_default_external_url(self.hass),
                )
            ),
            errors=errors,
            description_placeholders={
                "callback_path": "/api/djconnect/spotify/callback",
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
                data.update(
                    _sync_tts_voice_with_engine(
                        self.hass,
                        _voice_defaults(user_input),
                    )
                )
                return self.async_create_entry(
                    title=data.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME),
                    data=data,
                )

        return self.async_show_form(
            step_id="voice",
            data_schema=await _voice_schema(
                self.hass,
                _voice_defaults({}),
                include_advanced=_advanced_enabled(self),
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "DJConnectOptionsFlow":
        """Create options flow."""
        return DJConnectOptionsFlow(config_entry)


class DJConnectOptionsFlow(config_entries.OptionsFlow):
    """Handle DJConnect options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._show_advanced_options = False
        self._oauth: dict[str, str] = {}

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Manage DJConnect options."""
        current = {**self._config_entry.data, **self._config_entry.options}
        defaults = _voice_defaults(current, preserve_empty=True)
        errors: dict[str, str] = {}
        if user_input is not None:
            if _request_advanced(self, user_input):
                return await self.async_step_init()
            action = user_input.get(OPTIONS_ACTION_FIELD)
            if action == OPTIONS_ACTION_SPOTIFY_REAUTH:
                return await self.async_step_spotify_reauth()
            if action == OPTIONS_ACTION_RETRY_PAIRING:
                return await self._async_retry_pairing()
            if action == OPTIONS_ACTION_REPAIR:
                return await self.async_step_repair_pairing()
            errors = _voice_errors(user_input)
            if not errors:
                merged = dict(current)
                merged.update(
                    {
                        key: value
                        for key, value in user_input.items()
                        if key != OPTIONS_ACTION_FIELD
                    }
                )
                merged = _sync_tts_voice_with_engine(self.hass, merged)
                return self.async_create_entry(
                    title="",
                    data=_voice_defaults(merged, preserve_empty=True),
                )

        return self.async_show_form(
            step_id="init",
            data_schema=await _voice_schema(
                self.hass,
                defaults,
                include_advanced=_advanced_enabled(self),
                include_options_action=True,
            ),
            errors=errors,
        )

    async def async_step_spotify_reauth(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Reauthorize Spotify from the options flow."""
        if user_input is not None:
            return self.async_external_step_done(next_step_id="spotify_reauth_done")
        current = {**self._config_entry.data, **self._config_entry.options}
        client_id = str(
            current.get(CONF_SPOTIFY_CLIENT_ID) or DEFAULT_SPOTIFY_CLIENT_ID
        ).strip()
        external_url = str(
            current.get(CONF_HA_EXTERNAL_URL)
            or await _async_default_external_url(self.hass)
            or ""
        ).strip().rstrip("/")
        if not client_id or not external_url:
            return self.async_show_form(
                step_id="init",
                data_schema=await _voice_schema(
                    self.hass,
                    _voice_defaults(current),
                    include_advanced=_advanced_enabled(self),
                    include_options_action=True,
                ),
                errors={"base": "oauth_setup_failed"},
            )
        redirect_uri = build_redirect_uri(external_url)
        state = secrets.token_urlsafe(24)
        code_verifier = create_code_verifier()
        self._oauth = {
            "state": state,
            "redirect_uri": redirect_uri,
            "authorize_url": build_authorize_url(
                client_id,
                redirect_uri,
                DEFAULT_SPOTIFY_SCOPES,
                state,
                code_verifier,
            ),
        }
        pending = self.hass.data.setdefault(DOMAIN, {}).setdefault(
            "spotify_oauth_pending",
            {},
        )
        pending[state] = {
            "flow_id": self.flow_id,
            "entry_id": self._config_entry.entry_id,
            "client_id": client_id,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "market": current.get(CONF_SPOTIFY_MARKET, DEFAULT_SPOTIFY_MARKET),
            "scopes": DEFAULT_SPOTIFY_SCOPES,
        }
        return self.async_external_step(
            step_id="spotify_reauth",
            url=self._oauth["authorize_url"],
            description_placeholders={"redirect_uri": redirect_uri},
        )

    async def async_step_spotify_reauth_done(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Show a translated completion step after Spotify OAuth reauthorization."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=dict(self._config_entry.options),
            )
        return self.async_show_form(
            step_id="spotify_reauth_done",
            data_schema=vol.Schema({}),
        )

    async def async_step_repair_pairing(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Collect a fresh pairing code before fully re-pairing the ESP."""
        errors: dict[str, str] = {}
        if user_input is not None:
            pair_code = str(user_input.get(CONF_PAIR_CODE, "")).strip()
            if not pair_code:
                errors[CONF_PAIR_CODE] = "missing_pair_code"
            elif not _valid_pair_code(pair_code):
                errors[CONF_PAIR_CODE] = "invalid_pair_code"
            else:
                return await self._async_retry_pairing(pair_code=pair_code)

        return self.async_show_form(
            step_id="repair_pairing",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PAIR_CODE,
                        default=str(self._config_entry.data.get(CONF_PAIR_CODE, "")),
                    ): str,
                }
            ),
            errors=errors,
        )

    async def _async_retry_pairing(self, pair_code: str | None = None) -> FlowResult:
        """Generate a fresh device token and retry pairing with the ESP."""
        errors: dict[str, str] = {}
        try:
            runtime = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id)
            if runtime is None:
                errors["base"] = "repair_pairing_failed"
            else:
                token = secrets.token_urlsafe(32)
                data = dict(self._config_entry.data)
                if pair_code is not None:
                    device_id = f"djconnect-{pair_code}"
                    data[CONF_PAIR_CODE] = pair_code
                    data[CONF_DEVICE_ID] = device_id
                    data[CONF_LOCAL_URL] = _clean(
                        data.get(CONF_LOCAL_URL),
                        _default_local_url(pair_code),
                    )
                    runtime.pairing_code = pair_code
                    runtime.pairing_device_id = device_id
                    runtime.device_status["device_id"] = device_id
                    runtime.device_status.pop("paired", None)
                runtime.device_token = token
                runtime.device_status["ha_pairing_status"] = "pending"
                runtime.update(last_error=None)
                data[CONF_DEVICE_TOKEN] = token
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data=data,
                )
                await runtime.pair_device(self.hass)
                runtime.device_status["ha_pairing_status"] = "pending"
                runtime.update(last_error=None)
                return self.async_create_entry(
                    title="",
                    data=dict(self._config_entry.options),
                )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("DJConnect re-pair failed: %s", exc)
            errors["base"] = "repair_pairing_failed"

        current = {**self._config_entry.data, **self._config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=await _voice_schema(
                self.hass,
                _voice_defaults(current),
                include_advanced=_advanced_enabled(self),
                include_options_action=True,
            ),
            errors=errors,
        )
