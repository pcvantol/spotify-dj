from __future__ import annotations

import logging
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
    CONF_DEVICE_ID,
    CONF_DEVICE_TOKEN,
    CONF_HA_EXTERNAL_URL,
    CONF_LOCAL_URL,
    CONF_MAX_AUDIO_BYTES,
    CONF_PAIR_CODE,
    DOMAIN,
    DEFAULT_MAX_AUDIO_BYTES,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_MARKET,
    CONF_SPOTIFY_REFRESH_TOKEN,
    CONF_SPOTIFY_SCOPES,
    DEFAULT_SPOTIFY_MARKET,
    DEFAULT_SPOTIFY_SCOPES,
)
from .assist_stt import (
    SpotifyDJNoSttProviderError,
    STT_OPTION_KEYS,
    transcribe_wav_with_assist,
)
from .dj_response import async_send_dj_response_best_effort, get_tts_audio
from .processor import process_text_command
from .spotify_backend import SpotifyBackendError, handle_spotify_command
from .spotify_oauth import exchange_code_for_refresh_token

_LOGGER = logging.getLogger(__name__)


def _runtime(hass):
    return hass.data.get(DOMAIN, {}).get("runtime")


ERROR_MESSAGES = {
    "not_configured": "SpotifyDJ is not configured.",
    "invalid_json": "Send valid JSON.",
    "missing_pair_data": "Send both device_id and pair_code.",
    "invalid_pair_code": "The pairing code does not match this SpotifyDJ setup.",
    "unauthorized": "The SpotifyDJ device token is missing or invalid.",
    "missing_audio": "Send WAV audio bytes in the request body.",
    "audio_too_large": "The uploaded audio is too large.",
    "unsupported_media_type": "Send audio/wav, audio/x-wav, application/octet-stream or JSON text.",
    "invalid_command": "Send a valid SpotifyDJ command.",
    "backend_unavailable": "The configured playback backend is unavailable.",
    "stale_pairing": "SpotifyDJ pairing is stale. Pair the device again.",
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
            "Sorry, something went wrong while handling your SpotifyDJ command. "
            "Please try again."
        ),
        "nl": (
            "Sorry, er ging iets mis bij het verwerken van je SpotifyDJ opdracht. "
            "Probeer het opnieuw."
        ),
    },
}
DJ_TEST_TEXTS = {
    "en": "SpotifyDJ is ready for your next request.",
    "nl": "SpotifyDJ is klaar voor je volgende verzoek.",
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


def _missing_text_response(view: HomeAssistantView):
    return view.json(
        {
            "success": False,
            "error": "missing_text",
            "message": (
                "Send recognized text using X-SpotifyDJ-Text or upload WAV audio "
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
    header_text = headers.get("X-SpotifyDJ-Text")
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


def _set_device_state(runtime: Any, state: str) -> None:
    status = getattr(runtime, "device_status", None)
    if isinstance(status, dict):
        status["state"] = state


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
        _LOGGER.debug("SpotifyDJ Spotify refresh_token=rotated")
    return changed


def _persist_paired_device(
    hass: Any,
    runtime: Any,
    device_id: str,
    local_url: str | None,
    device_token: str,
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


class SpotifyDJPairView(HomeAssistantView):
    url = API_PAIR
    name = "api:spotify_dj:pair"
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
                "device_name": data.get("device_name") or "SpotifyDJ",
                "firmware": data.get("firmware"),
                "local_url": data.get("local_url"),
                "paired": True,
            }
        )
        runtime.update(last_error=None)
        _persist_paired_device(hass, runtime, device_id, data.get("local_url"), token)
        _LOGGER.info("SpotifyDJ paired device %s", device_id)
        response = {
            "success": True,
            "device_token": token,
            "assist_pipeline_id": conf.get(CONF_ASSIST_PIPELINE_ID, ""),
            "ha_url": conf.get(CONF_HA_EXTERNAL_URL, ""),
            "device_language": runtime.device_language(),
            "language": runtime.device_language(),
            "api_base": "/api/spotify_dj",
            "voice_path": API_VOICE,
            "status_path": API_STATUS,
            "event_path": API_EVENT,
        }
        return self.json(response)


class SpotifyDJStatusView(HomeAssistantView):
    url = API_STATUS
    name = "api:spotify_dj:status"
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
        runtime.device_status.update(data)
        if data.get("device_id") and runtime.device_token:
            _persist_paired_device(
                hass,
                runtime,
                data["device_id"],
                data.get("local_url") or data.get("ota_url"),
                runtime.device_token,
            )
        spotify_configured = data.get("spotify_configured")
        # OTA lifecycle hints from ESP.
        if data.get("ota_state") in {"idle", "success", "failed"}:
            runtime.ota_in_progress = False
        if data.get("ota_error"):
            runtime.ota_last_error = data.get("ota_error")
        runtime.update(last_error=None)
        conf = runtime.config
        response = {
            "success": True,
            "assist_pipeline_id": conf.get(CONF_ASSIST_PIPELINE_ID, ""),
            "ha_url": conf.get(CONF_HA_EXTERNAL_URL, ""),
            "device_token": runtime.device_token or "",
            "device_language": runtime.device_language(),
            "language": runtime.device_language(),
        }
        backend_available = bool(_current_spotify_credentials(runtime))
        _LOGGER.debug(
            "SpotifyDJ status from device %s: spotify_configured=%s backend_available=%s",
            data.get("device_id"),
            spotify_configured,
            backend_available,
        )
        response["backend_available"] = backend_available
        runtime.device_status["backend_available"] = backend_available
        return self.json(response)


class SpotifyDJCommandView(HomeAssistantView):
    url = API_COMMAND
    name = "api:spotify_dj:command"
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
        command = str(data.get("command") or "").strip()
        if not command:
            return _json_error(self, "invalid_command", 400)
        _LOGGER.debug(
            "SpotifyDJ backend command from %s: %s",
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
            return _json_error(self, "backend_unavailable", 503, str(exc))
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("SpotifyDJ backend command failed: %s", exc)
            runtime.update(last_error=str(exc))
            return _json_error(self, "backend_unavailable", 503, str(exc))


class SpotifyDJEventView(HomeAssistantView):
    url = API_EVENT
    name = "api:spotify_dj:event"
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
        event_type = data.get("type") or data.get("event")
        runtime.device_status["last_event"] = data
        runtime.update(last_error=None)
        _LOGGER.info("SpotifyDJ event received: %s", event_type)
        return self.json({"success": True})


class SpotifyDJVoiceView(HomeAssistantView):
    url = API_VOICE
    name = "api:spotify_dj:voice"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def post(self, request):
        hass = request.app["hass"]
        runtime = _runtime(hass)
        if runtime is None:
            return _json_error(self, "not_configured", 503)
        device_id = request.headers.get("X-SpotifyDJ-Device-ID")
        if not device_id:
            return _json_error(self, "unauthorized", 401)
        if not runtime.authorize_device_request(request.headers, device_id):
            return _json_error(self, "unauthorized", 401)

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
                entry = getattr(runtime, "entry", None)
                stt_key, stt_value = _first_config_value(runtime.config, STT_OPTION_KEYS)
                tts_key, tts_value = _first_config_value(runtime.config, ("tts_engine",))
                _LOGGER.info(
                    "SpotifyDJ WAV voice request: entry_id=%s options_keys=%s "
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
                except SpotifyDJNoSttProviderError as exc:
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
            elif request.headers.get("X-SpotifyDJ-Text"):
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
                _LOGGER.debug("SpotifyDJ DJ response text test: %s", user_text)
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

            _LOGGER.debug("SpotifyDJ command: %s", user_text)
            _set_device_state(runtime, "processing")
            runtime.update(last_text=user_text, last_error=None)
            try:
                result = await process_text_command(hass, runtime, user_text, play=True)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("SpotifyDJ command parser/playback failed: %s", exc)
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
                "SpotifyDJ result intent=%s playback=%s dj_text=%s audio_url=%s audio_type=%s",
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
            _LOGGER.exception("SpotifyDJ request failed: %s", exc)
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


class SpotifyDJTtsView(HomeAssistantView):
    url = API_TTS
    name = "api:spotify_dj:tts"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request, token: str, extension: str = "wav"):
        status, audio = get_tts_audio(request.app["hass"], token)
        if status == 404:
            return web.Response(status=404, text="SpotifyDJ TTS audio not found")
        if status == 410:
            return web.Response(status=410, text="SpotifyDJ TTS audio expired")
        if audio is None or extension.lower() != audio.extension:
            return web.Response(status=404, text="SpotifyDJ TTS audio type not found")
        return web.Response(
            body=audio.data,
            content_type=audio.content_type,
            headers={"Content-Length": str(len(audio.data))},
        )


class SpotifyDJSpotifyCallbackView(HomeAssistantView):
    url = API_SPOTIFY_CALLBACK
    name = "api:spotify_dj:spotify_callback"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request):
        hass = request.app["hass"]
        state = request.query.get("state")
        code = request.query.get("code")
        error = request.query.get("error")
        if error:
            return web.Response(text=f"SpotifyDJ Spotify OAuth failed: {error}", status=400)
        if not state or not code:
            return web.Response(text="SpotifyDJ Spotify OAuth failed: missing state/code", status=400)

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
                return web.Response(
                    text=(
                        "SpotifyDJ Spotify OAuth is gelukt. Je kunt dit venster sluiten en teruggaan naar Home Assistant."
                    ),
                    content_type="text/plain",
                )
            except Exception as exc:  # noqa: BLE001
                _LOGGER.exception("SpotifyDJ config-flow OAuth callback failed")
                return web.Response(text=f"SpotifyDJ Spotify OAuth failed: {exc}", status=500)

        pending = hass.data.setdefault(DOMAIN, {}).setdefault("spotify_oauth_pending", {})
        ctx = pending.pop(state, None)
        if not ctx:
            return web.Response(text="SpotifyDJ Spotify OAuth failed: unknown/expired state", status=400)

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
                raise RuntimeError("SpotifyDJ config entry no longer exists")
            new_data = dict(entry.data)
            new_data[CONF_SPOTIFY_CLIENT_ID] = ctx["client_id"]
            new_data[CONF_SPOTIFY_REFRESH_TOKEN] = token["refresh_token"]
            new_data[CONF_SPOTIFY_MARKET] = ctx.get("market", DEFAULT_SPOTIFY_MARKET)
            new_data[CONF_SPOTIFY_SCOPES] = ctx.get("scopes", DEFAULT_SPOTIFY_SCOPES)
            hass.config_entries.async_update_entry(entry, data=new_data)
            runtime = _runtime(hass)
            if runtime is not None:
                runtime.update_spotify_refresh_token(token.get("refresh_token"))
                _LOGGER.debug("SpotifyDJ Spotify refresh_token=rotated/present")
            await hass.config_entries.async_reload(entry.entry_id)
            return web.Response(
                text=(
                    "SpotifyDJ Spotify OAuth is gelukt. De refresh token is opgeslagen in Home Assistant. "
                    "Je kunt dit venster sluiten; Home Assistant beheert Spotify playback nu zelf."
                ),
                content_type="text/plain",
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("SpotifyDJ Spotify OAuth callback failed")
            return web.Response(text=f"SpotifyDJ Spotify OAuth failed: {exc}", status=500)
