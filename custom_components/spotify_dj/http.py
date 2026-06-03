from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.http import HomeAssistantView

from .const import (
    API_SPOTIFY_CALLBACK,
    API_EVENT,
    API_PAIR,
    API_STATUS,
    API_VOICE,
    CONF_MAX_AUDIO_BYTES,
    DEFAULT_MAX_AUDIO_BYTES,
    DOMAIN,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_MARKET,
    CONF_SPOTIFY_REFRESH_TOKEN,
    CONF_SPOTIFY_SCOPES,
    DEFAULT_SPOTIFY_MARKET,
    DEFAULT_SPOTIFY_SCOPES,
)
from .processor import process_text_command
from .stt import wav_to_text
from .tts import create_error_wav, create_openai_tts_wav
from .spotify_oauth import exchange_code_for_refresh_token

_LOGGER = logging.getLogger(__name__)


def _runtime(hass):
    return hass.data.get(DOMAIN, {}).get("runtime")


class SpotifyDJPairView(HomeAssistantView):
    url = API_PAIR
    name = "api:spotify_dj:pair"
    requires_auth = False

    async def post(self, request):
        hass = request.app["hass"]
        runtime = _runtime(hass)
        if runtime is None:
            return self.json({"success": False, "error": "SpotifyDJ is not configured"}, status_code=503)
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            return self.json({"success": False, "error": "Invalid JSON"}, status_code=400)

        device_id = data.get("device_id")
        pair_code = str(data.get("pair_code") or "")
        if not device_id or not pair_code:
            return self.json({"success": False, "error": "Missing device_id or pair_code"}, status_code=400)

        # v0.6 pragmatic pairing: HA accepts the first device/code and returns a per-device token.
        # For stricter pairing, add config_flow step that pre-registers runtime.pairing_code.
        token = runtime.ensure_device_token()
        runtime.pairing_code = pair_code
        runtime.pairing_device_id = device_id
        runtime.device_status.update({
            "device_id": device_id,
            "device_name": data.get("device_name") or "SpotifyDJ",
            "firmware": data.get("firmware"),
            "local_url": data.get("local_url"),
            "paired": True,
        })
        runtime.update(last_error=None)
        _LOGGER.info("SpotifyDJ paired device %s", device_id)
        response = {
            "success": True,
            "device_token": token,
            "api_base": "/api/spotify_dj",
            "voice_path": API_VOICE,
            "status_path": API_STATUS,
            "event_path": API_EVENT,
        }
        # If Spotify was already provisioned in HA, include the credentials once during pairing.
        conf = runtime.config
        if conf.get(CONF_SPOTIFY_CLIENT_ID) and conf.get(CONF_SPOTIFY_REFRESH_TOKEN):
            response["spotify"] = {
                "client_id": conf.get(CONF_SPOTIFY_CLIENT_ID),
                "refresh_token": conf.get(CONF_SPOTIFY_REFRESH_TOKEN),
                "market": conf.get(CONF_SPOTIFY_MARKET, DEFAULT_SPOTIFY_MARKET),
                "scopes": conf.get(CONF_SPOTIFY_SCOPES, DEFAULT_SPOTIFY_SCOPES).split(),
            }
        return self.json(response)


class SpotifyDJStatusView(HomeAssistantView):
    url = API_STATUS
    name = "api:spotify_dj:status"
    requires_auth = False

    async def post(self, request):
        hass = request.app["hass"]
        runtime = _runtime(hass)
        if runtime is None:
            return self.json({"success": False, "error": "SpotifyDJ is not configured"}, status_code=503)
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            return self.json({"success": False, "error": "Invalid JSON"}, status_code=400)
        if not runtime.authorize_device_request(request.headers, data.get("device_id")):
            return self.json({"success": False, "error": "Unauthorized"}, status_code=401)
        runtime.device_status.update(data)
        # OTA lifecycle hints from ESP.
        if data.get("ota_state") in {"idle", "success", "failed"}:
            runtime.ota_in_progress = False
        if data.get("ota_error"):
            runtime.ota_last_error = data.get("ota_error")
        runtime.update(last_error=None)
        return self.json({"success": True})


class SpotifyDJEventView(HomeAssistantView):
    url = API_EVENT
    name = "api:spotify_dj:event"
    requires_auth = False

    async def post(self, request):
        hass = request.app["hass"]
        runtime = _runtime(hass)
        if runtime is None:
            return self.json({"success": False, "error": "SpotifyDJ is not configured"}, status_code=503)
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            return self.json({"success": False, "error": "Invalid JSON"}, status_code=400)
        if not runtime.authorize_device_request(request.headers, data.get("device_id")):
            return self.json({"success": False, "error": "Unauthorized"}, status_code=401)
        event_type = data.get("type") or data.get("event")
        runtime.device_status["last_event"] = data
        runtime.update(last_error=None)
        _LOGGER.info("SpotifyDJ event %s: %s", event_type, data)
        return self.json({"success": True})


class SpotifyDJVoiceView(HomeAssistantView):
    url = API_VOICE
    name = "api:spotify_dj:voice"
    requires_auth = False

    async def post(self, request):
        hass = request.app["hass"]
        runtime = _runtime(hass)
        if runtime is None:
            return self.Response(status=503, text="SpotifyDJ is not configured")
        if not runtime.authorize_device_request(request.headers):
            return self.Response(status=401, text="Unauthorized")

        conf = runtime.config
        max_audio_bytes = int(conf.get(CONF_MAX_AUDIO_BYTES, DEFAULT_MAX_AUDIO_BYTES))
        wav = await request.read()
        if len(wav) > max_audio_bytes:
            msg = "De opname is te lang voor SpotifyDJ. Probeer het iets korter."
            runtime.update(last_error=msg)
            body = await create_error_wav(hass, msg, conf)
            return self.Response(body=body, content_type="audio/wav", status=413)

        try:
            user_text = request.headers.get("X-SpotifyDJ-Text")
            if user_text:
                _LOGGER.info("SpotifyDJ using text override: %s", user_text)
            else:
                if not wav:
                    raise RuntimeError("Geen audio ontvangen")
                user_text = await wav_to_text(hass, wav, conf)
                if not user_text:
                    raise RuntimeError("Ik verstond geen tekst")

            result = await process_text_command(hass, runtime, user_text, play=True)
            response_wav = await create_openai_tts_wav(hass, result["dj_text"], conf)
            _LOGGER.info("SpotifyDJ OK: %s", result)
            return self.Response(body=response_wav, content_type="audio/wav")

        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("SpotifyDJ request failed: %s", exc)
            msg = f"Sorry, SpotifyDJ liep vast: {exc}"
            runtime.update(last_error=str(exc))
            body = await create_error_wav(hass, msg, conf)
            return self.Response(body=body, content_type="audio/wav", status=200)


class SpotifyDJSpotifyCallbackView(HomeAssistantView):
    url = API_SPOTIFY_CALLBACK
    name = "api:spotify_dj:spotify_callback"
    requires_auth = False

    async def get(self, request):
        hass = request.app["hass"]
        state = request.query.get("state")
        code = request.query.get("code")
        error = request.query.get("error")
        if error:
            return self.Response(text=f"SpotifyDJ Spotify OAuth failed: {error}", status=400)
        if not state or not code:
            return self.Response(text="SpotifyDJ Spotify OAuth failed: missing state/code", status=400)

        pending = hass.data.setdefault(DOMAIN, {}).setdefault("spotify_oauth_pending", {})
        ctx = pending.pop(state, None)
        if not ctx:
            return self.Response(text="SpotifyDJ Spotify OAuth failed: unknown/expired state", status=400)

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
            return self.Response(
                text=(
                    "SpotifyDJ Spotify OAuth is gelukt. De refresh token is opgeslagen in Home Assistant. "
                    "Je kunt dit venster sluiten en daarna de service spotify_dj.provision_spotify_credentials uitvoeren."
                ),
                content_type="text/plain",
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("SpotifyDJ Spotify OAuth callback failed")
            return self.Response(text=f"SpotifyDJ Spotify OAuth failed: {exc}", status=500)
