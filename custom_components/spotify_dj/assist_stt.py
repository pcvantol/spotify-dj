from __future__ import annotations

import asyncio
import inspect
import io
import logging
import wave
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_ASSIST_PIPELINE_ID, CONF_TTS_LANGUAGE, DEFAULT_TTS_LANGUAGE, DOMAIN

_LOGGER = logging.getLogger(__name__)

NO_STT_PROVIDER = "No Home Assistant STT provider configured"


class SpotifyDJSttError(RuntimeError):
    """Base error for SpotifyDJ STT handling."""


class SpotifyDJNoSttProviderError(SpotifyDJSttError):
    """Raised when Home Assistant has no usable STT provider."""


@dataclass(frozen=True)
class SttInfo:
    """Resolved Home Assistant STT settings for one voice upload."""

    ha_version: str
    pipeline_id: str | None
    engine: str | None
    language: str
    audio_format: str
    sample_rate: int
    channels: int


async def transcribe_wav_with_assist(
    hass: HomeAssistant,
    wav: bytes,
    conf: dict[str, Any],
) -> str:
    """Transcribe WAV audio through Home Assistant's supported STT helper."""
    test_handler = hass.data.get(DOMAIN, {}).get("stt_handler")
    if callable(test_handler):
        result = test_handler(hass, wav, conf)
        if hasattr(result, "__await__"):
            result = await result
        return _require_text(result)

    info = _resolve_stt_info(hass, wav, conf)
    _LOGGER.debug(
        "SpotifyDJ STT request: ha_version=%s pipeline_id=%s stt_engine=%s "
        "audio_format=%s sample_rate=%s channels=%s",
        info.ha_version,
        info.pipeline_id,
        info.engine,
        info.audio_format,
        info.sample_rate,
        info.channels,
    )
    if not info.engine:
        raise SpotifyDJNoSttProviderError(NO_STT_PROVIDER)

    try:
        from homeassistant.components import stt
    except Exception as exc:  # noqa: BLE001
        raise SpotifyDJNoSttProviderError(NO_STT_PROVIDER) from exc

    processor = getattr(stt, "async_process_audio_stream", None)
    if processor is None:
        raise SpotifyDJNoSttProviderError(NO_STT_PROVIDER)

    metadata = _speech_metadata(stt, info)
    result = await _call_stt_processor(
        processor,
        hass,
        metadata,
        _audio_chunks(wav),
        info.engine,
    )
    return _require_text(_text_from_stt_result(result))


def detect_stt_support(hass: HomeAssistant, conf: dict[str, Any]) -> dict[str, Any]:
    """Return startup diagnostics for the configured HA STT route."""
    info = _resolve_stt_info(hass, b"", conf)
    try:
        from homeassistant.components import stt

        helper_available = callable(getattr(stt, "async_process_audio_stream", None))
    except Exception:  # noqa: BLE001
        helper_available = False
    return {
        "ha_version": info.ha_version,
        "pipeline_id": info.pipeline_id,
        "stt_engine": info.engine,
        "language": info.language,
        "audio_format": info.audio_format,
        "stt_helper_available": helper_available,
        "configured": bool(info.engine and helper_available),
    }


def _resolve_stt_info(
    hass: HomeAssistant,
    wav: bytes,
    conf: dict[str, Any],
) -> SttInfo:
    sample_rate, channels, _sample_width = _wav_parameters(wav)
    pipeline_id = str(conf.get(CONF_ASSIST_PIPELINE_ID) or "").strip() or None
    language = str(conf.get(CONF_TTS_LANGUAGE) or DEFAULT_TTS_LANGUAGE)
    engine = None
    pipeline = _get_assist_pipeline(hass, pipeline_id)
    if pipeline is not None:
        pipeline_id = str(
            getattr(pipeline, "id", None)
            or getattr(pipeline, "conversation_id", None)
            or pipeline_id
            or ""
        ) or None
        engine = _first_attr(pipeline, "stt_engine", "stt_engine_id", "stt_provider")
        language = (
            _first_attr(pipeline, "stt_language", "language")
            or language
        )
    return SttInfo(
        ha_version=_ha_version(),
        pipeline_id=pipeline_id,
        engine=str(engine).strip() if engine else None,
        language=str(language),
        audio_format="wav",
        sample_rate=sample_rate,
        channels=channels,
    )


def _get_assist_pipeline(hass: HomeAssistant, pipeline_id: str | None) -> Any | None:
    try:
        from homeassistant.components.assist_pipeline.pipeline import async_get_pipelines

        pipelines = async_get_pipelines(hass)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("SpotifyDJ Assist pipeline registry unavailable: %s", exc)
        return None

    if pipeline_id:
        getter = getattr(pipelines, "async_get_pipeline", None)
        if callable(getter):
            try:
                return getter(pipeline_id)
            except Exception:  # noqa: BLE001
                return None
        mapping = getattr(pipelines, "pipelines", None)
        if isinstance(mapping, dict):
            return mapping.get(pipeline_id)

    current_getter = getattr(pipelines, "async_get_preferred_pipeline", None)
    if callable(current_getter):
        try:
            return current_getter()
        except Exception:  # noqa: BLE001
            return None
    current = getattr(pipelines, "preferred_pipeline", None) or getattr(
        pipelines,
        "current_pipeline",
        None,
    )
    if current is not None:
        return current
    mapping = getattr(pipelines, "pipelines", None)
    if isinstance(mapping, dict) and mapping:
        return next(iter(mapping.values()))
    return None


def _speech_metadata(stt: Any, info: SttInfo) -> Any:
    try:
        return stt.SpeechMetadata(
            language=info.language,
            format=stt.AudioFormats.WAV,
            codec=stt.AudioCodecs.PCM,
            bit_rate=info.sample_rate * info.channels * 16,
            sample_rate=info.sample_rate,
            channel=info.channels,
        )
    except Exception:  # noqa: BLE001
        return {
            "language": info.language,
            "format": "wav",
            "codec": "pcm",
            "sample_rate": info.sample_rate,
            "channel": info.channels,
        }


async def _call_stt_processor(
    processor: Any,
    hass: HomeAssistant,
    metadata: Any,
    stream: AsyncIterator[bytes],
    engine: str,
) -> Any:
    try:
        signature = inspect.signature(processor)
    except (TypeError, ValueError):
        signature = None
    if signature is not None and "engine" in signature.parameters:
        return await processor(hass, metadata, stream, engine=engine)
    if signature is not None and "provider" in signature.parameters:
        return await processor(hass, metadata, stream, provider=engine)
    try:
        return await processor(hass, metadata, stream, engine)
    except TypeError:
        return await processor(hass, metadata, stream)


def _wav_parameters(wav: bytes) -> tuple[int, int, int]:
    if not wav:
        return 16000, 1, 2
    try:
        with wave.open(io.BytesIO(wav), "rb") as wav_file:
            return (
                int(wav_file.getframerate()),
                int(wav_file.getnchannels()),
                int(wav_file.getsampwidth()),
            )
    except Exception:  # noqa: BLE001
        _LOGGER.debug("SpotifyDJ could not parse WAV header; using default STT metadata")
        return 16000, 1, 2


async def _audio_chunks(wav: bytes, chunk_size: int = 4096) -> AsyncIterator[bytes]:
    for offset in range(0, len(wav), chunk_size):
        yield wav[offset : offset + chunk_size]
        await asyncio.sleep(0)


def _text_from_stt_result(result: Any) -> str:
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, dict):
        return str(result.get("text") or result.get("stt_text") or "").strip()
    text = getattr(result, "text", None)
    if text:
        return str(text).strip()
    return ""


def _require_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise SpotifyDJSttError("HA Assist STT did not return recognized text")
    return text


def _first_attr(obj: Any, *names: str) -> Any:
    for name in names:
        value = getattr(obj, name, None)
        if value:
            return value
    return None


def _ha_version() -> str:
    try:
        from homeassistant.const import __version__

        return str(__version__)
    except Exception:  # noqa: BLE001
        return "unknown"
