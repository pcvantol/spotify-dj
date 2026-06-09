from __future__ import annotations

import base64
import html
import logging
from pathlib import Path
import re
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .const import (
    API_COMMAND,
    API_SPOTIFY_CALLBACK,
    API_EVENT,
    API_PAIR,
    API_STATUS,
    API_TTS,
    API_VOICE,
    CONF_ASSIST_PIPELINE_ID,
    CONF_CLIENT_TYPE,
    CONF_DEVICE_ID,
    CONF_DEVICE_TOKEN,
    CONF_HA_EXTERNAL_URL,
    CONF_LOCAL_URL,
    CONF_MAX_AUDIO_BYTES,
    CONF_PAIR_CODE,
    DOMAIN,
    CLIENT_TYPES,
    DEFAULT_CLIENT_TYPE,
    DEFAULT_MAX_AUDIO_BYTES,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_MARKET,
    CONF_SPOTIFY_REFRESH_TOKEN,
    CONF_SPOTIFY_SCOPES,
    DEFAULT_SPOTIFY_MARKET,
    DEFAULT_SPOTIFY_SCOPES,
    VERSION,
)
from .assist_stt import (
    DJConnectNoSttProviderError,
    STT_OPTION_KEYS,
    transcribe_wav_with_assist,
)
from .dj_response import async_send_dj_response_best_effort, get_tts_audio
from .ha_urls import async_ha_url_payload
from .processor import process_text_command
from .spotify_backend import SpotifyBackendError, handle_spotify_command
from .spotify_oauth import exchange_code_for_refresh_token

_LOGGER = logging.getLogger(__name__)
_LOGO_DATA_URI: str | None = None
VOICE_DEBUG_KEY = "last_voice_debug"
VOICE_DEBUG_URL = "/api/djconnect/debug/last_voice.wav"


def _djconnect_logo_data_uri() -> str:
    """Return the embedded DJConnect app icon for standalone OAuth callback pages."""
    global _LOGO_DATA_URI
    if _LOGO_DATA_URI is None:
        logo = Path(__file__).with_name("icon.png").read_bytes()
        _LOGO_DATA_URI = f"data:image/png;base64,{base64.b64encode(logo).decode()}"
    return _LOGO_DATA_URI


def _ha_integrations_url(base_url: str | None) -> str:
    """Build the Home Assistant integration deep link from the OAuth base URL."""
    base = str(base_url or "").rstrip("/")
    if not base:
        return "homeassistant://navigate/config/integrations/integration/djconnect"
    return f"{base}/config/integrations/integration/djconnect"


def _spotify_oauth_html_response(
    *,
    title: str,
    message: str,
    status: int = 200,
    base_url: str | None = None,
    success: bool = True,
) -> web.Response:
    """Render a friendly standalone Spotify OAuth result page."""
    accent = "#1db954" if success else "#ff8a00"
    icon = "✓" if success else "!"
    link = _ha_integrations_url(base_url)
    html_body = f"""<!doctype html>
<html lang="nl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #070b08;
      --card: rgba(18, 24, 20, .88);
      --text: #f4f7f5;
      --muted: #aeb8b2;
      --accent: {accent};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 28px;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(29, 185, 84, .24), transparent 34rem),
        radial-gradient(circle at bottom right, rgba(255, 138, 0, .16), transparent 28rem),
        var(--bg);
      color: var(--text);
    }}
    main {{
      width: min(680px, 100%);
      padding: 34px;
      border: 1px solid rgba(255,255,255,.10);
      border-radius: 28px;
      background: linear-gradient(145deg, rgba(28,36,31,.94), var(--card));
      box-shadow: 0 28px 90px rgba(0,0,0,.45);
      text-align: center;
    }}
    .logo-wrap {{
      position: relative;
      display: inline-block;
    }}
    img {{
      width: 112px;
      height: 112px;
      border-radius: 24px;
      object-fit: cover;
      box-shadow: 0 12px 38px rgba(0,0,0,.34);
    }}
    .badge {{
      position: absolute;
      right: -22px;
      bottom: -16px;
      display: grid;
      place-items: center;
      width: 44px;
      height: 44px;
      border-radius: 999px;
      background: var(--accent);
      color: #051008;
      font-size: 28px;
      font-weight: 800;
    }}
    h1 {{
      margin: 20px 0 12px;
      font-size: clamp(2rem, 6vw, 3.4rem);
      line-height: 1;
      letter-spacing: -.05em;
    }}
    p {{
      margin: 0 auto;
      max-width: 560px;
      color: var(--muted);
      font-size: 1.12rem;
      line-height: 1.65;
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 12px;
      margin-top: 28px;
    }}
    a, button {{
      border: 0;
      border-radius: 999px;
      padding: 14px 20px;
      background: var(--accent);
      color: #06100a;
      font: inherit;
      font-weight: 800;
      text-decoration: none;
      cursor: pointer;
    }}
    button.secondary {{
      background: rgba(255,255,255,.10);
      color: var(--text);
    }}
    small {{
      display: block;
      margin-top: 24px;
      color: rgba(244,247,245,.55);
    }}
  </style>
</head>
<body>
  <main>
    <div class="logo-wrap">
      <img src="{_djconnect_logo_data_uri()}" alt="DJConnect app icon">
      <div class="badge" aria-hidden="true">{icon}</div>
    </div>
    <h1>{html.escape(title)}</h1>
    <p>{html.escape(message)}</p>
    <div class="actions">
      <a href="{html.escape(link, quote=True)}">Open DJConnect in Home Assistant</a>
      <button class="secondary" onclick="window.close()">Sluit venster</button>
    </div>
    <small>DJConnect beheert playback via Home Assistant. Spotify is a trademark of Spotify AB.</small>
  </main>
</body>
</html>"""
    return web.Response(text=html_body, status=status, content_type="text/html")


def _request_token(headers: Any) -> str:
    auth = str(headers.get("Authorization", "") or "").strip()
    return auth.removeprefix("Bearer ").strip()


def _runtime_matches_device(runtime: Any, device_id: str) -> bool:
    known = str(
        getattr(runtime, "device_status", {}).get("device_id")
        or getattr(runtime, "pairing_device_id", "")
        or getattr(runtime, "config", {}).get(CONF_DEVICE_ID, "")
        or ""
    ).strip()
    if not known or not device_id:
        return False
    if known == device_id:
        return True
    return bool(
        re.fullmatch(r"djconnect-\d{6}", known)
        and _is_real_device_id(device_id)
    )


def _is_real_device_id(device_id: str) -> bool:
    return bool(
        re.fullmatch(r"djconnect-(?:lilygo-)?[0-9A-Fa-f]{12}", str(device_id or ""))
    )


def _runtime(hass, device_id: str | None = None, headers: Any | None = None):
    data = hass.data.get(DOMAIN, {})
    runtimes = [
        runtime
        for key, runtime in data.items()
        if key != "runtime" and hasattr(runtime, "authorize_device_request")
    ]
    device_id = str(device_id or "").strip()
    if device_id:
        matches = [runtime for runtime in runtimes if _runtime_matches_device(runtime, device_id)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            _LOGGER.warning(
                "DJConnect found multiple runtimes for device_id=%s; using active runtime",
                device_id,
            )
    token = _request_token(headers or {})
    if token:
        token_matches = [
            runtime
            for runtime in runtimes
            if getattr(runtime, "device_token", None) == token
        ]
        if len(token_matches) == 1:
            return token_matches[0]
        if len(token_matches) > 1:
            _LOGGER.warning(
                "DJConnect found multiple runtimes with matching device token; using active runtime"
            )
    return data.get("runtime")


ERROR_MESSAGES = {
    "not_configured": "DJConnect is not configured.",
    "invalid_json": "Send valid JSON.",
    "missing_pair_data": "Send both device_id and pair_code.",
    "invalid_pair_code": "The pairing code does not match this DJConnect setup.",
    "unauthorized": "The DJConnect device token is missing or invalid.",
    "missing_audio": "Send WAV audio bytes in the request body.",
    "audio_too_large": "The uploaded audio is too large.",
    "unsupported_media_type": "Send audio/wav, audio/x-wav, application/octet-stream or JSON text.",
    "invalid_command": "Send a valid DJConnect command.",
    "invalid_client_type": "Send a valid DJConnect client_type.",
    "backend_unavailable": "The configured playback backend is unavailable.",
    "stale_pairing": "DJConnect pairing is stale. Pair the device again.",
    "version_mismatch": "DJConnect Home Assistant integration and device firmware major.minor versions must match.",
}
DJ_FAILURE_TEXTS = {
    "assist": {
        "en": (
            "Sorry, I could not process your voice command with Home Assistant Assist. "
            "Check the selected Assist pipeline and try again."
        ),
        "nl": (
            "Sorry, ik kon je spraakopdracht niet verwerken met Home Assistant Assist. "
            "Controleer de gekozen Assist pipeline en probeer het opnieuw."
        ),
    },
    "spotify": {
        "en": (
            "Sorry, I understood your request, but I could not start Spotify playback. "
            "Check whether a Spotify playback device is available and try again."
        ),
        "nl": (
            "Sorry, ik heb je verzoek begrepen, maar ik kon Spotify niet starten. "
            "Controleer of er een Spotify afspeelapparaat beschikbaar is en probeer het opnieuw."
        ),
    },
    "generic": {
        "en": (
            "Sorry, something went wrong while handling your DJConnect command. "
            "Please try again."
        ),
        "nl": (
            "Sorry, er ging iets mis bij het verwerken van je DJConnect opdracht. "
            "Probeer het opnieuw."
        ),
    },
}
DJ_TEST_TEXTS = {
    "en": "DJConnect is ready for your next request.",
    "nl": "DJConnect is klaar voor je volgende verzoek.",
}


def _json_error(
    view: HomeAssistantView,
    error: str,
    status_code: int,
    message: str | None = None,
):
    return view.json(
        {
            "success": False,
            "error": error,
            "message": message or ERROR_MESSAGES.get(error, error),
        },
        status_code=status_code,
    )


def _major_minor(version: Any) -> str | None:
    match = re.search(r"(\d+)\.(\d+)(?:\.\d+)?", str(version or ""))
    if not match:
        return None
    return f"{match.group(1)}.{match.group(2)}"


def _versions_compatible(ha_version: Any, firmware_version: Any) -> bool:
    if str(firmware_version or "").strip() == "0.0.0":
        return True

    ha_major_minor = _major_minor(ha_version)
    firmware_major_minor = _major_minor(firmware_version)
    return bool(
        ha_major_minor
        and firmware_major_minor
        and ha_major_minor == firmware_major_minor
    )


def _version_mismatch_response(view: HomeAssistantView, firmware_version: Any):
    ha_major_minor = _major_minor(VERSION)
    firmware_major_minor = _major_minor(firmware_version)
    return view.json(
        {
            "success": False,
            "error": "version_mismatch",
            "message": (
                "DJConnect Home Assistant integration and device firmware "
                "major.minor versions must match."
            ),
            "ha_version": VERSION,
            "ha_major_minor": ha_major_minor,
            "firmware": firmware_version,
            "firmware_major_minor": firmware_major_minor,
        },
        status_code=426,
    )


def _runtime_firmware_version(runtime: Any) -> Any:
    status = getattr(runtime, "device_status", {}) or {}
    return status.get("firmware") or status.get("firmware_version")


def _runtime_versions_compatible(runtime: Any) -> bool:
    firmware_version = _runtime_firmware_version(runtime)
    if not firmware_version:
        return True
    return _versions_compatible(VERSION, firmware_version)


def _runtime_version_mismatch_response(view: HomeAssistantView, runtime: Any):
    return _version_mismatch_response(view, _runtime_firmware_version(runtime))


def _missing_text_response(view: HomeAssistantView):
    return view.json(
        {
            "success": False,
            "error": "missing_text",
            "message": (
                "Send recognized text using X-DJConnect-Text or upload WAV audio "
                "for Home Assistant Assist STT."
            ),
        },
        status_code=400,
    )


def _stt_error_response(
    view: HomeAssistantView,
    message: str,
    status_code: int = 500,
):
    return view.json(
        {
            "success": False,
            "error": "stt_failed",
            "message": message,
        },
        status_code=status_code,
    )


def _text_from_payload(headers: Any, data: dict[str, Any] | None) -> str:
    header_text = headers.get("X-DJConnect-Text")
    if header_text:
        return str(header_text).strip()
    if data and data.get("text"):
        return str(data["text"]).strip()
    return ""


def _is_audio_upload(content_type: str) -> bool:
    return content_type in {"audio/wav", "audio/x-wav", "application/octet-stream"}


def _audio_type_from_url(audio_url: str | None) -> str | None:
    if not audio_url:
        return None
    lowered = audio_url.lower().split("?", 1)[0]
    if lowered.endswith(".mp3"):
        return "mp3"
    if lowered.endswith(".wav"):
        return "wav"
    return None


def _store_debug_voice_wav(
    hass: Any,
    device_id: str | None,
    content_type: str,
    wav: bytes,
) -> None:
    if not _LOGGER.isEnabledFor(logging.DEBUG):
        return
    hass.data.setdefault(DOMAIN, {})[VOICE_DEBUG_KEY] = {
        "wav": wav,
        "device_id": device_id,
        "content_type": content_type,
        "bytes": len(wav),
    }
    _LOGGER.debug(
        "DJConnect voice debug WAV captured: url=%s device_id=%s content_type=%s bytes=%s",
        VOICE_DEBUG_URL,
        device_id,
        content_type,
        len(wav),
    )


def _is_voice_only_payload(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    voice_keys = {"recording", "state", "last_error", "error", "message", "recognized_text"}
    identity_keys = {"device_id", CONF_CLIENT_TYPE, "payload_type"}
    keys = set(data)
    return bool(keys & voice_keys) and keys <= voice_keys | identity_keys


def _is_command_payload(data: Any) -> bool:
    return isinstance(data, dict) and (
        data.get("payload_type") == "command" or bool(data.get("command"))
    )


def _set_device_state(runtime: Any, state: str) -> None:
    status = getattr(runtime, "device_status", None)
    if isinstance(status, dict):
        status["state"] = state


def _normalized_status_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Flatten firmware status compatibility fields into HA entity keys."""
    normalized = dict(data)
    settings = data.get("settings")
    if isinstance(settings, dict):
        for key, value in settings.items():
            normalized.setdefault(key, value)
    screen = data.get("screen")
    if isinstance(screen, dict):
        if screen.get("state") is not None:
            normalized.setdefault("screen_state", screen.get("state"))
        if screen.get("brightness_level") is not None:
            normalized.setdefault("screen_brightness_level", screen.get("brightness_level"))
            normalized.setdefault("screen_brightness", screen.get("brightness_level"))
    led = data.get("led")
    if isinstance(led, dict) and led.get("state") is not None:
        normalized.setdefault("led_state", led.get("state"))
    aliases = {
        "screen_brightness_percent": "screen_brightness",
        "speaker_volume_percent": "speaker_volume",
        "screen_off_timeout_ms": "screen_timeout_ms",
    }
    for source, target in aliases.items():
        if normalized.get(source) is not None:
            normalized[target] = normalized[source]
    return normalized


def _payload_client_type(data: dict[str, Any]) -> str:
    return str(data.get(CONF_CLIENT_TYPE) or "").strip().lower()


def _validate_required_client_type(data: dict[str, Any]) -> str | None:
    client_type = _payload_client_type(data)
    if not client_type or client_type not in CLIENT_TYPES:
        return None
    return client_type


def _merge_status_update(status: dict[str, Any], update: dict[str, Any]) -> None:
    """Merge ESP status without letting sparse heartbeats erase known values."""
    if not update:
        _LOGGER.debug("Ignoring empty ESP status payload for device sensor update")
        return
    _LOGGER.debug("Merging ESP status payload without resetting missing fields")
    for key, value in update.items():
        if _is_empty_status_value(value) and key in status:
            continue
        status[key] = value


def _is_empty_status_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _runtime_client_type(runtime: Any) -> str:
    getter = getattr(runtime, "client_type", None)
    if callable(getter):
        return str(getter() or DEFAULT_CLIENT_TYPE)
    status = getattr(runtime, "device_status", {}) or {}
    conf = getattr(runtime, "config", {}) or {}
    return str(
        status.get(CONF_CLIENT_TYPE)
        or conf.get(CONF_CLIENT_TYPE)
        or DEFAULT_CLIENT_TYPE
    )


def _current_spotify_credentials(runtime: Any) -> dict[str, Any]:
    getter = getattr(runtime, "get_current_spotify_credentials", None)
    if callable(getter):
        return getter()
    payload = getattr(runtime, "spotify_payload", None)
    return payload() if callable(payload) else {}


def _safe_config_keys(values: dict[str, Any] | None) -> list[str]:
    return sorted(str(key) for key in (values or {}).keys())


def _first_config_value(conf: dict[str, Any], keys: tuple[str, ...]) -> tuple[str | None, str | None]:
    for key in keys:
        value = str(conf.get(key) or "").strip()
        if value:
            return key, value
    return None, None


def _store_rotated_spotify_refresh_token(
    hass: Any,
    entry: Any,
    runtime: Any,
    refresh_token: str | None,
) -> bool:
    token = str(refresh_token or "").strip()
    if not token or entry is None:
        return False
    changed = False
    updater = getattr(runtime, "update_spotify_refresh_token", None)
    if callable(updater):
        changed = bool(updater(token))
    current = str((getattr(entry, "data", {}) or {}).get(CONF_SPOTIFY_REFRESH_TOKEN) or "")
    if token != current:
        new_data = dict(entry.data)
        new_data[CONF_SPOTIFY_REFRESH_TOKEN] = token
        hass.config_entries.async_update_entry(entry, data=new_data)
        changed = True
    if changed:
        _LOGGER.debug("DJConnect Spotify refresh_token=rotated")
    return changed


def _delete_spotify_reauth_issues(hass: Any, entry_id: str) -> None:
    try:
        from homeassistant.helpers import issue_registry as ir

        for suffix in (
            "missing_spotify_refresh_token",
            "missing_spotify_oauth_scopes",
            "spotify_refresh_token_revoked",
        ):
            ir.async_delete_issue(hass, DOMAIN, f"{entry_id}_{suffix}")
    except Exception:  # noqa: BLE001
        _LOGGER.debug("DJConnect could not delete Spotify reauth repair issues", exc_info=True)


def _persist_paired_device(
    hass: Any,
    runtime: Any,
    device_id: str,
    local_url: str | None,
    device_token: str,
    client_type: str | None = None,
) -> None:
    """Persist ESP pairing details so HA restarts keep the real device identity."""
    entry = getattr(runtime, "entry", None)
    config_entries = getattr(hass, "config_entries", None)
    updater = getattr(config_entries, "async_update_entry", None)
    if entry is None or not callable(updater):
        return
    new_data = dict(getattr(entry, "data", {}) or {})
    new_data[CONF_DEVICE_ID] = device_id
    new_data[CONF_DEVICE_TOKEN] = device_token
    new_data[CONF_CLIENT_TYPE] = str(client_type or _runtime_client_type(runtime))
    cleaned_url = str(local_url or "").strip()
    if cleaned_url:
        new_data[CONF_LOCAL_URL] = cleaned_url
    updater(entry, data=new_data)


def _device_language(runtime: Any) -> str:
    language_getter = getattr(runtime, "device_language", None)
    if callable(language_getter):
        language = str(language_getter() or "").lower()
    else:
        language = ""
    return "nl" if language.startswith("nl") else "en"


def _failure_kind(exc: Exception) -> str:
    text = str(exc).lower()
    if any(word in text for word in ("assist", "conversation", "pipeline")):
        return "assist"
    if any(
        word in text
        for word in ("spotify", "playback", "media_player", "play_media", "player")
    ):
        return "spotify"
    if "apparaat" in text:
        return "spotify"
    return "generic"


def _command_failed_text(runtime: Any, exc: Exception | None = None) -> str:
    kind = _failure_kind(exc) if exc else "generic"
    return DJ_FAILURE_TEXTS[kind][_device_language(runtime)]


def _test_dj_text(runtime: Any) -> str:
    return DJ_TEST_TEXTS[_device_language(runtime)]


async def _send_failure_dj_response(
    hass: Any,
    runtime: Any,
    exc: Exception | None = None,
) -> dict[str, Any]:
    return await async_send_dj_response_best_effort(
        hass,
        runtime,
        _command_failed_text(runtime, exc),
    )


class DJConnectPairView(HomeAssistantView):
    url = API_PAIR
    name = "api:djconnect:pair"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def post(self, request):
        hass = request.app["hass"]
        runtime = _runtime(hass)
        if runtime is None:
            return _json_error(self, "not_configured", 503)
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            return _json_error(self, "invalid_json", 400)

        device_id = data.get("device_id")
        pair_code = str(data.get("pair_code") or "")
        if not device_id or not pair_code:
            return _json_error(self, "missing_pair_data", 400)
        client_type = _validate_required_client_type(data)
        if client_type is None:
            return _json_error(self, "invalid_client_type", 400)
        conf = runtime.config
        expected_pair_code = str(conf.get(CONF_PAIR_CODE) or "").strip()
        if expected_pair_code and pair_code != expected_pair_code:
            runtime.update(last_error=ERROR_MESSAGES["invalid_pair_code"])
            return _json_error(self, "invalid_pair_code", 401)

        # Pairing accepts the first device/code and returns a per-device token.
        token = runtime.ensure_device_token()
        runtime.pairing_code = pair_code
        runtime.pairing_device_id = device_id
        runtime.device_status.update(
            {
                "device_id": device_id,
                "device_name": data.get("device_name") or "DJConnect",
                CONF_CLIENT_TYPE: client_type,
                "firmware": data.get("firmware"),
                "local_url": data.get("local_url"),
                "ha_pairing_status": "pending",
            }
        )
        runtime.update(last_error=None)
        _persist_paired_device(
            hass,
            runtime,
            device_id,
            data.get("local_url"),
            token,
            runtime.device_status.get(CONF_CLIENT_TYPE),
        )
        _LOGGER.info("DJConnect paired device %s", device_id)
        response = {
            "success": True,
            "client_type": _runtime_client_type(runtime),
            "device_token": token,
            "assist_pipeline_id": conf.get(CONF_ASSIST_PIPELINE_ID, ""),
            "device_language": runtime.device_language(),
            "language": runtime.device_language(),
            "api_base": "/api/djconnect",
            "voice_path": API_VOICE,
            "status_path": API_STATUS,
            "event_path": API_EVENT,
        }
        response.update(await async_ha_url_payload(hass, conf))
        return self.json(response)


class DJConnectStatusView(HomeAssistantView):
    url = API_STATUS
    name = "api:djconnect:status"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def post(self, request):
        hass = request.app["hass"]
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            return _json_error(self, "invalid_json", 400)
        runtime = _runtime(
            hass,
            data.get("device_id") or request.headers.get("X-DJConnect-Device-ID"),
            request.headers,
        )
        if runtime is None:
            return _json_error(self, "not_configured", 503)
        if not runtime.authorize_device_request(request.headers, data.get("device_id")):
            return _json_error(self, "unauthorized", 401)
        status_update = _normalized_status_payload(data)
        client_type = _validate_required_client_type(status_update)
        if client_type is None:
            runtime.update(
                last_error=(
                    "DJConnect ESP status payload is missing required "
                    "client_type=esp32"
                )
            )
            return _json_error(self, "invalid_client_type", 400)
        status_update[CONF_CLIENT_TYPE] = client_type
        if _is_command_payload(status_update):
            _LOGGER.debug("Ignoring command payload for device sensor update")
        elif _is_voice_only_payload(status_update):
            _LOGGER.debug("Ignoring voice-only payload for device sensor update")
        else:
            _merge_status_update(runtime.device_status, status_update)
        if not _runtime_versions_compatible(runtime):
            runtime.update(
                last_error=(
                    "DJConnect version mismatch: HA "
                    f"{VERSION}, firmware {_runtime_firmware_version(runtime)}"
                )
            )
            return _runtime_version_mismatch_response(self, runtime)
        if data.get("device_id") and runtime.device_token:
            _persist_paired_device(
                hass,
                runtime,
                data["device_id"],
                data.get("local_url") or data.get("ota_url"),
                runtime.device_token,
                runtime.device_status.get(CONF_CLIENT_TYPE),
            )
        spotify_configured = data.get("spotify_configured")
        # OTA lifecycle hints from ESP.
        ota_state = data.get("ota_state") or data.get("update_state")
        if ota_state in {"idle", "success", "failed"}:
            runtime.ota_in_progress = False
        if data.get("ota_error"):
            runtime.ota_last_error = data.get("ota_error")
        runtime.update(last_error=None)
        conf = runtime.config
        response = {
            "success": True,
            "client_type": _runtime_client_type(runtime),
            "assist_pipeline_id": conf.get(CONF_ASSIST_PIPELINE_ID, ""),
            "device_language": runtime.device_language(),
            "language": runtime.device_language(),
            "playback": getattr(runtime, "last_playback", None) or {},
        }
        response.update(await async_ha_url_payload(hass, conf))
        backend_available = bool(_current_spotify_credentials(runtime))
        _LOGGER.debug(
            "DJConnect status from device %s: spotify_configured=%s backend_available=%s",
            data.get("device_id"),
            spotify_configured,
            backend_available,
        )
        response["backend_available"] = backend_available
        runtime.device_status["backend_available"] = backend_available
        return self.json(response)


class DJConnectCommandView(HomeAssistantView):
    url = API_COMMAND
    name = "api:djconnect:command"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def post(self, request):
        hass = request.app["hass"]
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            return _json_error(self, "invalid_json", 400)
        runtime = _runtime(
            hass,
            data.get("device_id") or request.headers.get("X-DJConnect-Device-ID"),
            request.headers,
        )
        if runtime is None:
            return _json_error(self, "not_configured", 503)
        if not runtime.authorize_device_request(request.headers, data.get("device_id")):
            return _json_error(self, "unauthorized", 401)
        client_type = _validate_required_client_type(data)
        if client_type is None:
            return _json_error(self, "invalid_client_type", 400)
        if _is_command_payload(data):
            _LOGGER.debug("Ignoring command payload for device sensor update")
        runtime.device_status[CONF_CLIENT_TYPE] = client_type
        if not _runtime_versions_compatible(runtime):
            return _runtime_version_mismatch_response(self, runtime)
        header_device = request.headers.get("X-DJConnect-Device-ID")
        real_device_id = data.get("device_id") or header_device
        if real_device_id and getattr(runtime, "device_token", None):
            _persist_paired_device(
                hass,
                runtime,
                real_device_id,
                getattr(runtime, "device_status", {}).get("local_url"),
                runtime.device_token,
                getattr(runtime, "device_status", {}).get(CONF_CLIENT_TYPE),
            )
        command = str(data.get("command") or "").strip()
        if not command:
            return _json_error(self, "invalid_command", 400)
        _LOGGER.debug(
            "DJConnect backend command from %s: %s",
            data.get("device_id"),
            command,
        )
        try:
            result = await handle_spotify_command(
                hass,
                runtime,
                command,
                data.get("value"),
                play=bool(data.get("play", False)),
            )
            runtime.update(last_error=None)
            return self.json(result)
        except ValueError as exc:
            return _json_error(self, "invalid_command", 400, str(exc))
        except SpotifyBackendError as exc:
            runtime.update(last_error=str(exc))
            runtime.device_status["backend_available"] = False
            return self.json(
                {
                    "success": False,
                    "error": "backend_unavailable",
                    "message": str(exc) or ERROR_MESSAGES["backend_unavailable"],
                    "backend_available": False,
                    "playback": getattr(runtime, "last_playback", None) or {},
                }
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("DJConnect backend command failed: %s", exc)
            runtime.update(last_error=str(exc))
            runtime.device_status["backend_available"] = False
            return self.json(
                {
                    "success": False,
                    "error": "backend_unavailable",
                    "message": str(exc) or ERROR_MESSAGES["backend_unavailable"],
                    "backend_available": False,
                    "playback": getattr(runtime, "last_playback", None) or {},
                }
            )


class DJConnectEventView(HomeAssistantView):
    url = API_EVENT
    name = "api:djconnect:event"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def post(self, request):
        hass = request.app["hass"]
        runtime = _runtime(hass)
        if runtime is None:
            return _json_error(self, "not_configured", 503)
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            return _json_error(self, "invalid_json", 400)
        if not runtime.authorize_device_request(request.headers, data.get("device_id")):
            return _json_error(self, "unauthorized", 401)
        client_type = _validate_required_client_type(data)
        if client_type is None:
            return _json_error(self, "invalid_client_type", 400)
        runtime.device_status[CONF_CLIENT_TYPE] = client_type
        if not _runtime_versions_compatible(runtime):
            return _runtime_version_mismatch_response(self, runtime)
        event_type = data.get("type") or data.get("event")
        runtime.device_status["last_event"] = data
        runtime.update(last_error=None)
        _LOGGER.info("DJConnect event received: %s", event_type)
        return self.json({"success": True})


class DJConnectVoiceView(HomeAssistantView):
    url = API_VOICE
    name = "api:djconnect:voice"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def post(self, request):
        hass = request.app["hass"]
        device_id = request.headers.get("X-DJConnect-Device-ID")
        if not device_id:
            return _json_error(self, "unauthorized", 401)
        runtime = _runtime(hass, device_id, request.headers)
        if runtime is None:
            return _json_error(self, "not_configured", 503)
        if not runtime.authorize_device_request(request.headers, device_id):
            return _json_error(self, "unauthorized", 401)
        if not _runtime_versions_compatible(runtime):
            return _runtime_version_mismatch_response(self, runtime)
        if getattr(runtime, "device_token", None):
            _persist_paired_device(
                hass,
                runtime,
                device_id,
                getattr(runtime, "device_status", {}).get("local_url"),
                runtime.device_token,
                getattr(runtime, "device_status", {}).get(CONF_CLIENT_TYPE),
            )

        try:
            content_type = request.headers.get("Content-Type", "")
            content_type = content_type.split(";", 1)[0].strip().lower()
            data = None
            user_text = ""
            is_audio_request = _is_audio_upload(content_type)

            if is_audio_request:
                limit = int(runtime.config.get(CONF_MAX_AUDIO_BYTES, DEFAULT_MAX_AUDIO_BYTES))
                wav = await request.read()
                if not wav:
                    return _json_error(self, "missing_audio", 400)
                if len(wav) > limit:
                    return _json_error(self, "audio_too_large", 413)
                _store_debug_voice_wav(hass, device_id, content_type, wav)
                entry = getattr(runtime, "entry", None)
                stt_key, stt_value = _first_config_value(runtime.config, STT_OPTION_KEYS)
                tts_key, tts_value = _first_config_value(runtime.config, ("tts_engine",))
                _LOGGER.info(
                    "DJConnect WAV voice request: entry_id=%s options_keys=%s "
                    "data_keys=%s stt_provider=%s:%s tts_provider=%s:%s "
                    "content_type=%s body_bytes=%s",
                    getattr(entry, "entry_id", None),
                    _safe_config_keys(getattr(entry, "options", None)),
                    _safe_config_keys(getattr(entry, "data", None)),
                    stt_key,
                    stt_value,
                    tts_key,
                    tts_value,
                    content_type,
                    len(wav),
                )
                _set_device_state(runtime, "processing")
                runtime.update(last_error=None)
                try:
                    user_text = await transcribe_wav_with_assist(hass, wav, runtime.config)
                except DJConnectNoSttProviderError as exc:
                    _set_device_state(runtime, "error")
                    runtime.update(last_error=str(exc))
                    return _stt_error_response(self, str(exc), 503)
                except Exception as exc:  # noqa: BLE001
                    _set_device_state(runtime, "error")
                    runtime.update(last_error=str(exc))
                    return _stt_error_response(self, str(exc))
            elif content_type == "application/json":
                try:
                    data = await request.json()
                except Exception:  # noqa: BLE001
                    return _json_error(self, "invalid_json", 400)
                if _is_voice_only_payload(data):
                    _LOGGER.debug("Ignoring voice-only payload for device sensor update")
            elif request.headers.get("X-DJConnect-Text"):
                pass
            elif content_type:
                await request.read()
                return _json_error(self, "unsupported_media_type", 415)
            else:
                await request.read()

            user_text = user_text or _text_from_payload(request.headers, data)
            if not user_text:
                return _missing_text_response(self)

            if not is_audio_request:
                dj_text = _test_dj_text(runtime)
                _LOGGER.debug("DJConnect DJ response text test: %s", user_text)
                _set_device_state(runtime, "responding")
                runtime.update(last_text=user_text, last_dj_text=dj_text, last_error=None)
                dj_response = await async_send_dj_response_best_effort(
                    hass,
                    runtime,
                    dj_text,
                )
                audio_url = dj_response.get("audio_url_value")
                _set_device_state(runtime, "idle")
                return self.json(
                    {
                        "success": True,
                        "text": dj_text,
                        "dj_text": dj_text,
                        "recognized_text": user_text,
                        "dj_response": dj_response,
                        "audio_url": audio_url,
                        "audio_type": _audio_type_from_url(audio_url),
                    }
                )

            _LOGGER.debug("DJConnect command: %s", user_text)
            _set_device_state(runtime, "processing")
            runtime.update(last_text=user_text, last_error=None)
            try:
                result = await process_text_command(hass, runtime, user_text, play=True)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("DJConnect command parser/playback failed: %s", exc)
                _set_device_state(runtime, "responding")
                dj_text = _command_failed_text(runtime, exc)
                runtime.update(last_error=str(exc), last_dj_text=dj_text)
                dj_response = await async_send_dj_response_best_effort(
                    hass,
                    runtime,
                    dj_text,
                )
                audio_url = dj_response.get("audio_url_value")
                _set_device_state(runtime, "idle")
                return self.json(
                    {
                        "success": True,
                        "error": "command_failed",
                        "message": str(exc),
                        "text": dj_text,
                        "dj_text": dj_text,
                        "recognized_text": user_text,
                        "intent": getattr(runtime, "last_intent", None),
                        "dj_response": dj_response,
                        "audio_url": audio_url,
                        "audio_type": _audio_type_from_url(audio_url),
                    }
                )
            _set_device_state(runtime, "responding")
            result["dj_response"] = await async_send_dj_response_best_effort(
                hass,
                runtime,
                result.get("dj_text") or "",
            )
            audio_url = result.get("dj_response", {}).get("audio_url_value")
            _set_device_state(runtime, "idle")
            _LOGGER.debug(
                "DJConnect result intent=%s playback=%s dj_text=%s audio_url=%s audio_type=%s",
                result.get("intent"),
                bool(result.get("playback")),
                bool(result.get("dj_text")),
                bool(audio_url),
                _audio_type_from_url(audio_url),
            )
            return self.json(
                {
                    "success": True,
                    **result,
                    "text": result.get("dj_text") or result.get("text"),
                    "recognized_text": user_text,
                    "audio_url": audio_url,
                    "audio_type": _audio_type_from_url(audio_url),
                }
            )

        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("DJConnect request failed: %s", exc)
            _set_device_state(runtime, "error")
            runtime.update(last_error=str(exc))
            dj_response = await _send_failure_dj_response(hass, runtime, exc)
            dj_text = _command_failed_text(runtime, exc)
            runtime.update(last_error=str(exc))
            return self.json(
                {
                    "success": False,
                    "error": "command_failed",
                    "message": str(exc),
                    "dj_text": dj_text,
                    "dj_response": dj_response,
                },
                status_code=500,
            )


class DJConnectTtsView(HomeAssistantView):
    url = API_TTS
    name = "api:djconnect:tts"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request, token: str, extension: str = "wav"):
        status, audio = get_tts_audio(request.app["hass"], token)
        if status == 404:
            return web.Response(status=404, text="DJConnect TTS audio not found")
        if status == 410:
            return web.Response(status=410, text="DJConnect TTS audio expired")
        if audio is None or extension.lower() != audio.extension:
            return web.Response(status=404, text="DJConnect TTS audio type not found")
        return web.Response(
            body=audio.data,
            content_type=audio.content_type,
            headers={"Content-Length": str(len(audio.data))},
        )


class DJConnectVoiceDebugView(HomeAssistantView):
    url = VOICE_DEBUG_URL
    name = "api:djconnect:voice_debug"
    requires_auth = True

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request):
        debug = request.app["hass"].data.get(DOMAIN, {}).get(VOICE_DEBUG_KEY)
        if not debug:
            return web.Response(status=404, text="DJConnect voice debug WAV not available")
        wav = debug.get("wav")
        if not wav:
            return web.Response(status=404, text="DJConnect voice debug WAV is empty")
        filename = f"djconnect-last-voice-{debug.get('device_id') or 'device'}.wav"
        return web.Response(
            body=wav,
            content_type="audio/wav",
            headers={
                "Content-Length": str(len(wav)),
                "Content-Disposition": f'inline; filename="{filename}"',
                "X-DJConnect-Device-ID": str(debug.get("device_id") or ""),
            },
        )


class DJConnectSpotifyCallbackView(HomeAssistantView):
    url = API_SPOTIFY_CALLBACK
    name = "api:djconnect:spotify_callback"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request):
        hass = request.app["hass"]
        state = request.query.get("state")
        code = request.query.get("code")
        error = request.query.get("error")
        if error:
            return _spotify_oauth_html_response(
                title="Spotify OAuth niet gelukt",
                message=f"Spotify gaf deze fout terug: {error}. Start de Spotify autorisatie opnieuw vanuit Home Assistant.",
                status=400,
                success=False,
            )
        if not state or not code:
            return _spotify_oauth_html_response(
                title="Spotify OAuth niet compleet",
                message="De callback mist een state of code. Start de Spotify autorisatie opnieuw vanuit Home Assistant.",
                status=400,
                success=False,
            )

        # Config-flow OAuth path: during initial setup there is no config entry yet.
        # config_flow.py stores pending context under config_flow_oauth_pending.
        config_pending = hass.data.setdefault(DOMAIN, {}).setdefault("config_flow_oauth_pending", {})
        ctx = config_pending.pop(state, None)
        if ctx:
            try:
                token = await exchange_code_for_refresh_token(
                    hass,
                    client_id=ctx["client_id"],
                    code=code,
                    code_verifier=ctx["code_verifier"],
                    redirect_uri=ctx["redirect_uri"],
                )
                runtime = _runtime(hass)
                entry = getattr(runtime, "entry", None)
                if entry is not None:
                    _store_rotated_spotify_refresh_token(
                        hass,
                        entry,
                        runtime,
                        token.get("refresh_token"),
                    )
                results = hass.data.setdefault(DOMAIN, {}).setdefault("config_flow_oauth_results", {})
                results[state] = {
                    CONF_SPOTIFY_CLIENT_ID: ctx["client_id"],
                    CONF_SPOTIFY_REFRESH_TOKEN: token["refresh_token"],
                    CONF_SPOTIFY_MARKET: ctx.get("market", DEFAULT_SPOTIFY_MARKET),
                    CONF_SPOTIFY_SCOPES: ctx.get("scopes", DEFAULT_SPOTIFY_SCOPES),
                }
                flow_id = ctx.get("flow_id")
                if flow_id:
                    await hass.config_entries.flow.async_configure(flow_id, {"state": state})
                return _spotify_oauth_html_response(
                    title="DJConnect is gekoppeld",
                    message=(
                        "Spotify is gekoppeld met DJConnect. Je kunt dit venster sluiten en teruggaan naar "
                        "Home Assistant om je DJConnect setup af te maken."
                    ),
                    base_url=ctx.get("ha_external_url") or ctx.get("redirect_uri", "").split(API_SPOTIFY_CALLBACK)[0],
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.exception("DJConnect config-flow OAuth callback failed")
                return _spotify_oauth_html_response(
                    title="Spotify OAuth fout",
                    message=f"Home Assistant kon de Spotify autorisatie niet afronden: {exc}",
                    status=500,
                    success=False,
                )

        pending = hass.data.setdefault(DOMAIN, {}).setdefault("spotify_oauth_pending", {})
        ctx = pending.pop(state, None)
        if not ctx:
            return _spotify_oauth_html_response(
                title="Spotify OAuth verlopen",
                message="Deze OAuth sessie is onbekend of verlopen. Start Spotify opnieuw autoriseren vanuit Home Assistant.",
                status=400,
                success=False,
            )

        try:
            token = await exchange_code_for_refresh_token(
                hass,
                client_id=ctx["client_id"],
                code=code,
                code_verifier=ctx["code_verifier"],
                redirect_uri=ctx["redirect_uri"],
            )
            entry = hass.config_entries.async_get_entry(ctx["entry_id"])
            if entry is None:
                raise RuntimeError("DJConnect config entry no longer exists")
            new_data = dict(entry.data)
            new_data[CONF_SPOTIFY_CLIENT_ID] = ctx["client_id"]
            new_data[CONF_SPOTIFY_REFRESH_TOKEN] = token["refresh_token"]
            new_data[CONF_SPOTIFY_MARKET] = ctx.get("market", DEFAULT_SPOTIFY_MARKET)
            new_data[CONF_SPOTIFY_SCOPES] = ctx.get("scopes", DEFAULT_SPOTIFY_SCOPES)
            hass.config_entries.async_update_entry(entry, data=new_data)
            runtime = _runtime(hass)
            if runtime is not None:
                runtime.update_spotify_refresh_token(token.get("refresh_token"))
                _LOGGER.debug("DJConnect Spotify refresh_token=rotated/present")
            _delete_spotify_reauth_issues(hass, entry.entry_id)
            await hass.config_entries.async_reload(entry.entry_id)
            flow_id = ctx.get("flow_id")
            if flow_id:
                try:
                    await hass.config_entries.flow.async_configure(
                        flow_id,
                        {"state": state},
                    )
                except Exception:  # noqa: BLE001
                    _LOGGER.debug(
                        "DJConnect OAuth options flow was already closed before callback completion",
                        exc_info=True,
                    )
            return _spotify_oauth_html_response(
                title="DJConnect is opnieuw geautoriseerd",
                message=(
                    "Spotify is opnieuw gekoppeld met DJConnect. Je kunt dit venster sluiten en teruggaan naar "
                    "Home Assistant."
                ),
                base_url=ctx.get("ha_external_url") or ctx.get("redirect_uri", "").split(API_SPOTIFY_CALLBACK)[0],
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("DJConnect Spotify OAuth callback failed")
            return _spotify_oauth_html_response(
                title="Spotify OAuth fout",
                message=f"Home Assistant kon de Spotify autorisatie niet afronden: {exc}",
                status=500,
                success=False,
            )
