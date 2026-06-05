from __future__ import annotations

import logging
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .const import (
    API_SPOTIFY_CALLBACK,
    API_EVENT,
    API_PAIR,
    API_STATUS,
    API_TTS,
    API_VOICE,
    CONF_ASSIST_PIPELINE_ID,
    CONF_HA_EXTERNAL_URL,
    CONF_PAIR_CODE,
    DOMAIN,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_MARKET,
    CONF_SPOTIFY_REFRESH_TOKEN,
    CONF_SPOTIFY_SCOPES,
    DEFAULT_SPOTIFY_MARKET,
    DEFAULT_SPOTIFY_SCOPES,
)
from .dj_response import async_send_dj_response_best_effort, get_tts_audio
from .processor import process_text_command
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
                "Send recognized text using X-SpotifyDJ-Text. Audio STT must be "
                "handled by HA Assist pipeline."
            ),
        },
        status_code=400,
    )


def _text_from_payload(headers: Any, data: dict[str, Any] | None) -> str:
    header_text = headers.get("X-SpotifyDJ-Text")
    if header_text:
        return str(header_text).strip()
    if data and data.get("text"):
        return str(data["text"]).strip()
    return ""


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
        _LOGGER.info("SpotifyDJ paired device %s", device_id)
        response = {
            "success": True,
            "device_token": token,
            "assist_pipeline_id": conf.get(CONF_ASSIST_PIPELINE_ID, ""),
            "ha_url": conf.get(CONF_HA_EXTERNAL_URL, ""),
            "device_language": runtime.device_language(),
            "language": runtime.device_language(),
            "mqtt": runtime.mqtt_payload(),
            "api_base": "/api/spotify_dj",
            "voice_path": API_VOICE,
            "status_path": API_STATUS,
            "event_path": API_EVENT,
        }
        # If Spotify was already provisioned in HA, include credentials during pairing.
        spotify = runtime.spotify_payload()
        if spotify:
            response["spotify"] = spotify
            response.update(spotify)
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
            "mqtt": runtime.mqtt_payload(),
        }
        spotify = runtime.spotify_payload()
        if spotify:
            response["spotify"] = spotify
            response.update(spotify)
        return self.json(response)


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
        if not runtime.authorize_device_request(request.headers):
            return _json_error(self, "unauthorized", 401)

        try:
            content_type = request.headers.get("Content-Type", "")
            content_type = content_type.split(";", 1)[0].strip().lower()
            data = None

            if content_type == "audio/wav":
                await request.read()
                return _missing_text_response(self)

            if content_type == "application/json":
                try:
                    data = await request.json()
                except Exception:  # noqa: BLE001
                    return _json_error(self, "invalid_json", 400)
            elif not request.headers.get("X-SpotifyDJ-Text"):
                await request.read()

            user_text = _text_from_payload(request.headers, data)
            if not user_text:
                return _missing_text_response(self)

            _LOGGER.debug("SpotifyDJ command: %s", user_text)
            result = await process_text_command(hass, runtime, user_text, play=True)
            result["dj_response"] = await async_send_dj_response_best_effort(
                hass,
                runtime,
                result.get("dj_text") or "",
            )
            _LOGGER.debug("SpotifyDJ result: %s", result)
            return self.json({"success": True, **result})

        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("SpotifyDJ request failed: %s", exc)
            runtime.update(last_error=str(exc))
            return self.json(
                {
                    "success": False,
                    "error": "command_failed",
                    "message": str(exc),
                },
                status_code=500,
            )


class SpotifyDJTtsView(HomeAssistantView):
    url = API_TTS
    name = "api:spotify_dj:tts"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request, token: str):
        status, audio = get_tts_audio(request.app["hass"], token)
        if status == 404:
            return web.Response(status=404, text="SpotifyDJ TTS audio not found")
        if status == 410:
            return web.Response(status=410, text="SpotifyDJ TTS audio expired")
        return web.Response(
            body=audio,
            content_type="audio/wav",
            headers={"Content-Length": str(len(audio or b""))},
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
            await hass.config_entries.async_reload(entry.entry_id)
            return web.Response(
                text=(
                    "SpotifyDJ Spotify OAuth is gelukt. De refresh token is opgeslagen in Home Assistant. "
                    "Je kunt dit venster sluiten en daarna de service spotify_dj.provision_spotify_credentials uitvoeren."
                ),
                content_type="text/plain",
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("SpotifyDJ Spotify OAuth callback failed")
            return web.Response(text=f"SpotifyDJ Spotify OAuth failed: {exc}", status=500)
