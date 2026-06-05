from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_TTS_ENGINE,
    CONF_TTS_LANGUAGE,
    CONF_TTS_VOICE,
    DEFAULT_TTS_ENGINE,
    DEFAULT_TTS_LANGUAGE,
    DEFAULT_TTS_VOICE,
)
from .wav_util import simple_tone_wav

_LOGGER = logging.getLogger(__name__)


async def create_tts_wav(hass: HomeAssistant, text: str, conf: dict) -> bytes:
    """Generate backend TTS audio and return it only when HA provides WAV bytes."""
    try:
        from homeassistant.components import tts
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Home Assistant TTS is unavailable") from exc

    media_source_id = await _async_generate_tts_media_source_id(tts, hass, text, conf)
    if not media_source_id:
        raise RuntimeError("Home Assistant TTS did not return a media source")

    media_source_audio = getattr(tts, "async_get_media_source_audio", None)
    if media_source_audio is None:
        raise RuntimeError("Home Assistant TTS audio fetch helper is unavailable")

    mime_type, audio = await media_source_audio(hass, media_source_id)
    if "wav" not in str(mime_type).lower():
        raise RuntimeError(f"Home Assistant TTS returned unsupported audio type {mime_type}")
    if not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
        raise RuntimeError("Home Assistant TTS returned non-WAV audio")
    return audio


async def create_error_wav(hass: HomeAssistant, message: str, conf: dict) -> bytes:
    return simple_tone_wav()


async def _async_generate_tts_media_source_id(
    tts_module: Any,
    hass: HomeAssistant,
    text: str,
    conf: dict,
) -> str | None:
    """Call the HA TTS media-source generator across supported HA versions."""
    engine = conf.get(CONF_TTS_ENGINE) or DEFAULT_TTS_ENGINE
    language = conf.get(CONF_TTS_LANGUAGE) or DEFAULT_TTS_LANGUAGE
    voice = str(conf.get(CONF_TTS_VOICE) or DEFAULT_TTS_VOICE).strip()
    options = {"voice": voice} if voice else None

    generators = (
        getattr(tts_module, "async_generate_media_source_id", None),
        getattr(tts_module, "generate_media_source_id", None),
    )
    for generator in generators:
        if generator is None:
            continue
        for kwargs in (
            {
                "message": text,
                "engine": engine,
                "language": language,
                "options": options,
            },
            {
                "message": text,
                "engine": engine,
                "language": language,
            },
            {
                "message": text,
                "language": language,
            },
        ):
            try:
                value = generator(hass, **kwargs)
                if hasattr(value, "__await__"):
                    value = await value
                if value:
                    return str(value)
            except TypeError:
                continue
            except Exception:  # noqa: BLE001
                _LOGGER.debug("SpotifyDJ TTS media-source generation failed", exc_info=True)
                continue
    return None
