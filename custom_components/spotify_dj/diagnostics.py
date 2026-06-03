from __future__ import annotations

from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN

_REDACT_KEYS = {"device_token", "spotify_refresh_token", "openai_api_key"}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("REDACTED" if k in _REDACT_KEYS else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    return {
        "entry": {
            "title": entry.title,
            "data": _redact(dict(entry.data)),
            "options": _redact(dict(entry.options)),
        },
        "runtime": _redact({
            "last_text": getattr(runtime, "last_text", None),
            "last_intent": getattr(runtime, "last_intent", None),
            "last_dj_text": getattr(runtime, "last_dj_text", None),
            "last_error": getattr(runtime, "last_error", None),
            "device_status": getattr(runtime, "device_status", {}),
            "ota_in_progress": getattr(runtime, "ota_in_progress", False),
            "ota_last_error": getattr(runtime, "ota_last_error", None),
        }) if runtime else {},
    }
