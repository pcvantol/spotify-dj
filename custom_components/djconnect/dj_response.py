"""Send DJ responses to the DJConnect device speaker/display."""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_TTS_BASE,
    CONF_DJ_RESPONSE_ENABLED,
    CONF_DJ_RESPONSE_TTL_SECONDS,
    CONF_HA_EXTERNAL_URL,
    DEFAULT_DJ_RESPONSE_ENABLED,
    DEFAULT_DJ_RESPONSE_TTL_SECONDS,
    DOMAIN,
)
from .tts import UnsupportedTtsAudioError, TtsAudio, create_tts_audio

_LOGGER = logging.getLogger(__name__)


@dataclass
class TtsAudioItem:
    """Temporary audio item served to the paired DJConnect device."""

    data: bytes
    content_type: str
    extension: str
    expires_at: float


def _store(hass: HomeAssistant) -> dict[str, TtsAudioItem]:
    return hass.data.setdefault(DOMAIN, {}).setdefault("tts_audio", {})


def cleanup_tts_audio(hass: HomeAssistant, now: float | None = None) -> None:
    """Remove expired TTS audio items."""
    current_time = time.time() if now is None else now
    store = _store(hass)
    for token, item in list(store.items()):
        if item.expires_at <= current_time:
            store.pop(token, None)


def get_tts_audio(hass: HomeAssistant, token: str) -> tuple[int, TtsAudioItem | None]:
    """Return status code and audio bytes for a temporary TTS token."""
    store = _store(hass)
    item = store.get(token)
    if item is None:
        return 404, None
    if item.expires_at <= time.time():
        store.pop(token, None)
        return 410, None
    return 200, item


def store_tts_audio(
    hass: HomeAssistant,
    data: bytes,
    ttl_seconds: int = DEFAULT_DJ_RESPONSE_TTL_SECONDS,
    content_type: str = "audio/wav",
    extension: str = "wav",
) -> str:
    """Store playable audio bytes temporarily and return a random download token."""
    cleanup_tts_audio(hass)
    token = secrets.token_urlsafe(24)
    _store(hass)[token] = TtsAudioItem(
        data=data,
        content_type=content_type,
        extension=extension,
        expires_at=time.time() + max(1, int(ttl_seconds)),
    )
    return token


async def async_create_dj_audio_url(
    hass: HomeAssistant,
    runtime: Any,
    text: str,
) -> str | None:
    """Create a temporary absolute audio URL for the ESP, if HA TTS can produce it."""
    conf = runtime.config
    if not conf.get(CONF_DJ_RESPONSE_ENABLED, DEFAULT_DJ_RESPONSE_ENABLED):
        return None
    try:
        audio = await create_tts_audio(hass, text, conf)
    except UnsupportedTtsAudioError as exc:
        _LOGGER.debug(
            "DJConnect DJ response audio skipped; HA TTS returned unsupported ESP audio: %s",
            exc,
        )
        return None
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("DJConnect could not generate DJ response TTS: %s", exc)
        return None
    if not _is_supported_audio(audio):
        _LOGGER.warning("DJConnect TTS provider did not return supported WAV/MP3 audio")
        return None
    ttl = int(conf.get(CONF_DJ_RESPONSE_TTL_SECONDS, DEFAULT_DJ_RESPONSE_TTL_SECONDS))
    token = store_tts_audio(
        hass,
        audio.data,
        ttl,
        content_type=audio.content_type,
        extension=audio.extension,
    )
    base_url = await _async_ha_base_url(hass, conf)
    if not base_url:
        _LOGGER.warning("DJConnect cannot build HA URL for DJ response audio")
        return None
    return f"{base_url.rstrip('/')}{API_TTS_BASE}/{token}.{audio.extension}"


async def async_send_dj_response(
    hass: HomeAssistant,
    runtime: Any,
    text: str,
) -> dict[str, Any]:
    """Post DJ response text and optional WAV URL to the DJConnect device."""
    payload = {"text": text}
    audio_url = await async_create_dj_audio_url(hass, runtime, text)
    if audio_url:
        payload["audio_url"] = audio_url

    local_url = await runtime.async_device_local_url(hass)
    if not local_url:
        raise RuntimeError("DJConnect device local_url is unknown")
    url = local_url.rstrip("/") + "/api/device/dj_response"
    session = async_get_clientsession(hass)
    async with session.post(
        url,
        json=payload,
        headers=runtime.device_headers(),
        timeout=ClientTimeout(total=30),
    ) as resp:
        response_text = await resp.text()
        if resp.status < 200 or resp.status >= 300:
            raise RuntimeError(f"ESP DJ response failed HTTP {resp.status}: {response_text}")
        try:
            data = await resp.json()
        except Exception:  # noqa: BLE001
            data = {"success": True, "message": response_text}

    result = {
        "success": bool(data.get("success", True)),
        "spoken": bool(data.get("spoken", False)),
        "displayed": bool(data.get("displayed", False)),
        "message": data.get("message"),
        "audio_url": bool(audio_url),
        "audio_url_value": audio_url,
        "audio_type": audio_url.rsplit(".", 1)[-1].lower() if audio_url else None,
    }
    runtime.update(
        last_dj_text=text,
        last_dj_spoken=result["spoken"],
        last_dj_displayed=result["displayed"],
        last_dj_response_at=time.time(),
        last_error=None,
    )
    _LOGGER.debug(
        "DJConnect DJ response result success=%s spoken=%s displayed=%s audio_url=%s audio_type=%s",
        result["success"],
        result["spoken"],
        result["displayed"],
        result["audio_url"],
        result["audio_type"],
    )
    return result


async def async_send_dj_response_best_effort(
    hass: HomeAssistant,
    runtime: Any,
    text: str,
) -> dict[str, Any]:
    """Send DJ response without failing the voice command on TTS/device errors."""
    try:
        return await async_send_dj_response(hass, runtime, text)
    except Exception as exc:  # noqa: BLE001
        runtime.update(last_error=str(exc))
        _LOGGER.warning("DJConnect DJ response delivery failed: %s", exc)
        return {
            "success": False,
            "spoken": False,
            "displayed": False,
            "message": str(exc),
        }


def _is_supported_audio(audio: TtsAudio) -> bool:
    return audio.extension in {"wav", "mp3"} and bool(audio.data)


async def _async_ha_base_url(hass: HomeAssistant, conf: dict[str, Any]) -> str:
    try:
        from homeassistant.helpers import network

        return await network.async_get_url(hass, prefer_external=False)
    except Exception:  # noqa: BLE001
        return str(conf.get(CONF_HA_EXTERNAL_URL) or "").strip()
