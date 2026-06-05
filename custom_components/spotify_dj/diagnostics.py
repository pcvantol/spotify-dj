from __future__ import annotations

from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import CONF_SPOTIFY_SCOPES, DOMAIN, SPOTIFY_SCOPES
from .spotify_oauth import missing_spotify_scopes, normalize_spotify_scopes

_REDACT_KEY_PARTS = ("token", "password", "secret")
LEGAL_DIAGNOSTICS = {
    "copyright": "Copyright (c) 2026 Peter van Tol. All rights reserved.",
    "spotify_trademark": "Spotify is a trademark of Spotify AB.",
    "affiliation": (
        "SpotifyDJ is not affiliated with, endorsed by, or sponsored by Spotify AB."
    ),
}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("REDACTED" if _is_sensitive_key(key) else _redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).lower()
    return any(part in normalized for part in _REDACT_KEY_PARTS)


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    configured_scopes = entry.data.get(CONF_SPOTIFY_SCOPES)
    missing_scopes = missing_spotify_scopes(configured_scopes)
    return {
        "legal": LEGAL_DIAGNOSTICS,
        "spotify_oauth": {
            "configured_scopes": normalize_spotify_scopes(configured_scopes),
            "required_scopes": SPOTIFY_SCOPES,
            "missing_scopes": missing_scopes,
            "reauthorization_required": bool(missing_scopes),
        },
        "entry": {
            "title": entry.title,
            "data": _redact(dict(entry.data)),
            "options": _redact(dict(entry.options)),
        },
        "runtime": _redact({
            "last_text": getattr(runtime, "last_text", None),
            "last_intent": getattr(runtime, "last_intent", None),
            "last_dj_text": getattr(runtime, "last_dj_text", None),
            "last_dj_spoken": getattr(runtime, "last_dj_spoken", None),
            "last_dj_displayed": getattr(runtime, "last_dj_displayed", None),
            "last_dj_response_at": getattr(runtime, "last_dj_response_at", None),
            "last_error": getattr(runtime, "last_error", None),
            "device_status": getattr(runtime, "device_status", {}),
            "ota_in_progress": getattr(runtime, "ota_in_progress", False),
            "ota_last_error": getattr(runtime, "ota_last_error", None),
        }) if runtime else {},
    }
