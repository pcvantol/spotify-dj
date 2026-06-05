"""Send DJ responses to the SpotifyDJ device speaker/display."""

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
from .tts import UnsupportedTtsAudioError, create_tts_wav

_LOGGER = logging.getLogger(__name__)


@dataclass
class TtsAudioItem:
    """Temporary WAV audio item served to the paired SpotifyDJ device."""

    data: bytes
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


def get_tts_audio(hass: HomeAssistant, token: str) -> tuple[int, bytes | None]:
    """Return status code and audio bytes for a temporary TTS token."""
    store = _store(hass)
    item = store.get(token)
    if item is None:
        return 404, None
    if item.expires_at <= time.time():
        store.pop(token, None)
        return 410, None
    return 200, item.data


def store_tts_audio(
    hass: HomeAssistant,
    data: bytes,
    ttl_seconds: int = DEFAULT_DJ_RESPONSE_TTL_SECONDS,
) -> str:
    """Store WAV bytes temporarily and return a random download token."""
    cleanup_tts_audio(hass)
    token = secrets.token_urlsafe(24)
    _store(hass)[token] = TtsAudioItem(
        data=data,
        expires_at=time.time() + max(1, int(ttl_seconds)),
    )
    return token


async def async_create_dj_audio_url(
    hass: HomeAssistant,
    runtime: Any,
    text: str,
) -> str | None:
    """Create a temporary absolute WAV URL for the ESP, if HA TTS can produce WAV."""
    conf = runtime.config
    if not conf.get(CONF_DJ_RESPONSE_ENABLED, DEFAULT_DJ_RESPONSE_ENABLED):
        return None
    try:
        wav = await create_tts_wav(hass, text, conf)
    except UnsupportedTtsAudioError as exc:
        _LOGGER.debug(
            "SpotifyDJ DJ response audio skipped; HA TTS returned unsupported ESP audio: %s",
            exc,
        )
        return None
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("SpotifyDJ could not generate DJ response TTS: %s", exc)
        return None
    if not _looks_like_wav(wav):
        _LOGGER.warning("SpotifyDJ TTS provider did not return PCM WAV audio")
        return None
    ttl = int(conf.get(CONF_DJ_RESPONSE_TTL_SECONDS, DEFAULT_DJ_RESPONSE_TTL_SECONDS))
    token = store_tts_audio(hass, wav, ttl)
    base_url = await _async_ha_base_url(hass, conf)
    if not base_url:
        _LOGGER.warning("SpotifyDJ cannot build HA URL for DJ response audio")
        return None
    return f"{base_url.rstrip('/')}{API_TTS_BASE}/{token}.wav"


async def async_send_dj_response(
    hass: HomeAssistant,
    runtime: Any,
    text: str,
) -> dict[str, Any]:
    """Post DJ response text and optional WAV URL to the SpotifyDJ device."""
    payload = {"text": text}
    audio_url = await async_create_dj_audio_url(hass, runtime, text)
    if audio_url:
        payload["audio_url"] = audio_url

    local_url = await runtime.async_device_local_url(hass)
    if not local_url:
        raise RuntimeError("SpotifyDJ device local_url is unknown")
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
    }
    runtime.update(
        last_dj_text=text,
        last_dj_spoken=result["spoken"],
        last_dj_displayed=result["displayed"],
        last_dj_response_at=time.time(),
        last_error=None,
    )
    _LOGGER.debug("SpotifyDJ DJ response result: %s", result)
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
        _LOGGER.warning("SpotifyDJ DJ response delivery failed: %s", exc)
        return {
            "success": False,
            "spoken": False,
            "displayed": False,
            "message": str(exc),
        }


def _looks_like_wav(data: bytes) -> bool:
    return data.startswith(b"RIFF") and data[8:12] == b"WAVE"


async def _async_ha_base_url(hass: HomeAssistant, conf: dict[str, Any]) -> str:
    try:
        from homeassistant.helpers import network

        return await network.async_get_url(hass, prefer_external=False)
    except Exception:  # noqa: BLE001
        return str(conf.get(CONF_HA_EXTERNAL_URL) or "").strip()
