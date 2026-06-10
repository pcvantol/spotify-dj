from __future__ import annotations

import logging
from dataclasses import dataclass
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


@dataclass(slots=True)
class TtsAudio:
    """Playable HA TTS audio for DJConnect devices."""

    data: bytes
    extension: str
    content_type: str


class UnsupportedTtsAudioError(RuntimeError):
    """Raised when HA TTS works but returns audio the ESP cannot play."""


async def create_tts_audio(hass: HomeAssistant, text: str, conf: dict) -> TtsAudio:
    """Generate backend TTS audio and return WAV or MP3 bytes for the ESP."""
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
    audio_type = _audio_type(mime_type, audio)
    if audio_type == "wav":
        return TtsAudio(audio, "wav", "audio/wav")
    if audio_type == "mp3":
        return TtsAudio(audio, "mp3", "audio/mpeg")
    raise UnsupportedTtsAudioError(
        f"Home Assistant TTS returned unsupported audio type {mime_type}"
    )


async def create_tts_wav(hass: HomeAssistant, text: str, conf: dict) -> bytes:
    """Generate backend TTS audio and return it only when HA provides WAV bytes."""
    audio = await create_tts_audio(hass, text, conf)
    if audio.extension != "wav":
        raise UnsupportedTtsAudioError(
            f"Home Assistant TTS returned unsupported audio type {audio.content_type}"
        )
    return audio.data


async def create_error_wav(hass: HomeAssistant, message: str, conf: dict) -> bytes:
    return simple_tone_wav()


def _audio_type(mime_type: Any, audio: bytes) -> str | None:
    normalized = str(mime_type or "").lower()
    if "wav" in normalized or (audio.startswith(b"RIFF") and audio[8:12] == b"WAVE"):
        return "wav"
    if (
        "mpeg" in normalized
        or "mp3" in normalized
        or audio.startswith(b"ID3")
        or (len(audio) >= 2 and audio[0] == 0xFF and (audio[1] & 0xE0) == 0xE0)
    ):
        return "mp3"
    return None


async def _async_generate_tts_media_source_id(
    tts_module: Any,
    hass: HomeAssistant,
    text: str,
    conf: dict,
) -> str | None:
    """Call the HA TTS media-source generator across supported HA versions."""
    configured_engine = str(conf.get(CONF_TTS_ENGINE) or "").strip()
    engine = configured_engine or DEFAULT_TTS_ENGINE
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
        for kwargs in _tts_media_source_kwargs(
            text=text,
            engine=engine,
            language=language,
            options=options,
        ):
            try:
                value = generator(hass, **kwargs)
                if hasattr(value, "__await__"):
                    value = await value
                if value:
                    return str(value)
            except TypeError:
                continue
            except Exception as exc:  # noqa: BLE001
                if _is_invalid_tts_provider_error(exc):
                    attempted_engine = kwargs.get("engine") or "Home Assistant default"
                    _LOGGER.debug(
                        "DJConnect TTS provider %s is invalid; trying next TTS fallback",
                        attempted_engine,
                    )
                    continue
                _LOGGER.debug("DJConnect TTS media-source generation failed", exc_info=True)
                continue
    return None


def _tts_media_source_kwargs(
    *,
    text: str,
    engine: str,
    language: str,
    options: dict[str, Any] | None,
) -> tuple[dict[str, Any], ...]:
    values: list[dict[str, Any]] = []
    if engine and options is not None:
        values.append(
            {
                "message": text,
                "engine": engine,
                "language": language,
                "options": options,
            }
        )
    if engine:
        values.append(
            {
                "message": text,
                "engine": engine,
                "language": language,
            }
        )
    values.append(
        {
            "message": text,
            "language": language,
        }
    )
    return tuple(values)


def _is_invalid_tts_provider_error(exc: Exception) -> bool:
    return "invalid tts provider selected" in str(exc).lower()
