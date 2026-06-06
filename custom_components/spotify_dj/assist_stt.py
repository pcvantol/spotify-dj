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

from .const import (
    CONF_ASSIST_PIPELINE_ID,
    CONF_STT_ENGINE,
    CONF_TTS_LANGUAGE,
    DEFAULT_TTS_LANGUAGE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STT_OPTION_KEYS = (
    CONF_STT_ENGINE,
    "stt_provider",
    "stt_provider_id",
    "stt_engine_id",
    "stt_entity",
    "stt_entity_id",
    "openai_stt_engine",
    "openai_stt_provider",
    "openai_stt_model",
)
ASSIST_STT_VALUES = {"", "assist", "ha_assist", "home_assistant_assist", "pipeline"}
NO_STT_PROVIDER = "No STT provider configured. Checked options keys: "


class SpotifyDJSttError(RuntimeError):
    """Base error for SpotifyDJ STT handling."""


class SpotifyDJNoSttProviderError(SpotifyDJSttError):
    """Raised when Home Assistant has no usable STT provider."""


@dataclass(frozen=True)
class SttInfo:
    """Resolved Home Assistant STT settings for one voice upload."""

    ha_version: str
    pipeline_id: str | None
    pipeline_name: str | None
    engine: str | None
    language: str
    audio_format: str
    sample_rate: int
    channels: int
    sample_width: int
    byte_length: int


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
    _LOGGER.info(
        "SpotifyDJ STT request: ha_version=%s pipeline_id=%s pipeline_name=%s "
        "language=%s stt_engine=%s stt_available=%s audio_format=%s "
        "sample_rate=%s channels=%s sample_width=%s bytes=%s",
        info.ha_version,
        info.pipeline_id,
        info.pipeline_name,
        info.language,
        info.engine,
        bool(info.engine),
        info.audio_format,
        info.sample_rate,
        info.channels,
        info.sample_width,
        info.byte_length,
    )
    if not info.engine:
        return await _transcribe_with_assist_pipeline(hass, wav, info)

    try:
        from homeassistant.components import stt
    except Exception as exc:  # noqa: BLE001
        raise SpotifyDJNoSttProviderError(_no_stt_provider_message()) from exc

    metadata = _speech_metadata(stt, info)
    result = await _process_with_stt_engine(
        stt,
        hass,
        metadata,
        _audio_chunks(wav),
        info.engine,
    )
    text = _text_from_stt_result(result)
    _LOGGER.info(
        "SpotifyDJ STT provider result: type=%s state=%s has_text=%s",
        type(result).__name__,
        _result_state(result),
        bool(text),
    )
    return _require_text(text)


async def _transcribe_with_assist_pipeline(
    hass: HomeAssistant,
    wav: bytes,
    info: SttInfo,
) -> str:
    """Use HA's supported Assist audio pipeline helper as final STT fallback."""
    try:
        from homeassistant.components import stt
        from homeassistant.components.assist_pipeline import async_pipeline_from_audio_stream
        from homeassistant.components.assist_pipeline.pipeline import PipelineStage
        from homeassistant.core import Context
    except Exception as exc:  # noqa: BLE001
        raise SpotifyDJNoSttProviderError(_no_stt_provider_message()) from exc

    events: list[Any] = []

    async def event_callback(event: Any) -> None:
        events.append(event)

    _LOGGER.info(
        "SpotifyDJ STT fallback: using HA Assist audio pipeline helper "
        "pipeline_id=%s language=%s audio_format=%s",
        info.pipeline_id,
        info.language,
        info.audio_format,
    )
    try:
        await async_pipeline_from_audio_stream(
            hass,
            context=Context(),
            event_callback=event_callback,
            stt_metadata=_speech_metadata(stt, info),
            stt_stream=_audio_chunks(wav),
            pipeline_id=info.pipeline_id,
            start_stage=PipelineStage.STT,
            end_stage=PipelineStage.STT,
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("SpotifyDJ STT fallback pipeline run failed: %s", exc)
        message = str(exc)
        if "speech-to-text" in message or "does not support" in message:
            raise SpotifyDJNoSttProviderError(_no_stt_provider_message()) from exc
        raise SpotifyDJSttError(f"HA Assist STT failed: {message}") from exc

    text = _text_from_pipeline_events(events)
    _LOGGER.info(
        "SpotifyDJ Assist pipeline STT events: count=%s types=%s has_text=%s",
        len(events),
        _event_types(events),
        bool(text),
    )
    return _require_text(text)


def detect_stt_support(hass: HomeAssistant, conf: dict[str, Any]) -> dict[str, Any]:
    """Return startup diagnostics for the configured HA STT route."""
    info = _resolve_stt_info(hass, b"", conf)
    try:
        from homeassistant.components import stt

        helper_available = callable(getattr(stt, "async_get_speech_to_text_engine", None))
    except Exception:  # noqa: BLE001
        helper_available = False
    return {
        "ha_version": info.ha_version,
        "pipeline_id": info.pipeline_id,
        "pipeline_name": info.pipeline_name,
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
    sample_rate, channels, sample_width = _wav_parameters(wav)
    pipeline_id = str(conf.get(CONF_ASSIST_PIPELINE_ID) or "").strip() or None
    language = str(conf.get(CONF_TTS_LANGUAGE) or DEFAULT_TTS_LANGUAGE)
    engine = _selected_stt_engine(conf)
    pipeline_name = None
    pipeline = None if engine else _get_assist_pipeline(hass, pipeline_id)
    if engine:
        _LOGGER.info(
            "SpotifyDJ STT provider selected from integration options: %s",
            engine,
        )
    elif pipeline is not None:
        pipeline_id = str(
            _pipeline_attr(pipeline, "id")
            or _pipeline_attr(pipeline, "conversation_id")
            or pipeline_id
            or ""
        ) or None
        pipeline_name = _pipeline_attr(pipeline, "name")
        engine = _first_attr(
            pipeline,
            "stt_engine",
            "stt_engine_id",
            "stt_provider",
            "stt_provider_id",
        )
        language = (
            _first_attr(pipeline, "stt_language", "language")
            or language
        )
    if not engine:
        engine = _first_stt_entity(hass)
        if engine:
            pipeline_name = pipeline_name or "Home Assistant STT entity fallback"
            _LOGGER.info(
                "SpotifyDJ STT provider selected from HA stt entity fallback: %s",
                engine,
            )
    return SttInfo(
        ha_version=_ha_version(),
        pipeline_id=pipeline_id,
        pipeline_name=str(pipeline_name).strip() if pipeline_name else None,
        engine=str(engine).strip() if engine else None,
        language=str(language),
        audio_format="wav",
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
        byte_length=len(wav),
    )


def _selected_stt_engine(conf: dict[str, Any]) -> str | None:
    for key in STT_OPTION_KEYS:
        value = str(conf.get(key) or "").strip()
        if not value:
            continue
        if value.lower() in ASSIST_STT_VALUES:
            return None
        return value
    return None


def _no_stt_provider_message() -> str:
    return NO_STT_PROVIDER + ", ".join(STT_OPTION_KEYS)


def _get_assist_pipeline(hass: HomeAssistant, pipeline_id: str | None) -> Any | None:
    try:
        from homeassistant.components.assist_pipeline.pipeline import async_get_pipelines

        pipelines = async_get_pipelines(hass)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("SpotifyDJ Assist pipeline registry unavailable: %s", exc)
        return None

    available = _pipeline_list(pipelines)

    if pipeline_id:
        pipeline = _find_pipeline(pipelines, available, pipeline_id)
        if pipeline is not None:
            return pipeline
        _LOGGER.warning(
            "SpotifyDJ configured Assist pipeline %s was not found; falling back "
            "to Home Assistant preferred/default pipeline",
            pipeline_id,
        )

    current_getter = getattr(pipelines, "async_get_preferred_pipeline", None)
    if callable(current_getter):
        try:
            preferred = current_getter()
            if preferred is not None and _pipeline_has_stt(preferred):
                return preferred
        except Exception:  # noqa: BLE001
            _LOGGER.warning("SpotifyDJ preferred Assist pipeline lookup failed")
    current = getattr(pipelines, "preferred_pipeline", None) or getattr(
        pipelines,
        "current_pipeline",
        None,
    )
    if current is not None and _pipeline_has_stt(current):
        return current

    for pipeline in available:
        if _pipeline_has_stt(pipeline):
            return pipeline
    if available:
        return available[0]
    return None


def _first_stt_entity(hass: HomeAssistant) -> str | None:
    states = getattr(hass, "states", None)
    if not states or not hasattr(states, "async_entity_ids"):
        return None
    try:
        entity_ids = sorted(states.async_entity_ids("stt"))
    except Exception:  # noqa: BLE001
        return None
    return str(entity_ids[0]) if entity_ids else None


def _find_pipeline(
    pipelines: Any,
    available: list[Any],
    pipeline_id: str,
) -> Any | None:
    getter = getattr(pipelines, "async_get_pipeline", None)
    if callable(getter):
        try:
            pipeline = getter(pipeline_id)
            if pipeline is not None:
                return pipeline
        except Exception:  # noqa: BLE001
            return None
    for pipeline in available:
        if str(_pipeline_attr(pipeline, "id") or "") == pipeline_id:
            return pipeline
    return None


def _pipeline_list(pipelines: Any) -> list[Any]:
    if isinstance(pipelines, dict):
        return list(pipelines.values())
    mapping = getattr(pipelines, "pipelines", None)
    if isinstance(mapping, dict):
        return list(mapping.values())
    if isinstance(mapping, list | tuple):
        return list(mapping)
    try:
        return list(pipelines)
    except TypeError:
        return []


def _pipeline_has_stt(pipeline: Any) -> bool:
    return bool(
        _first_attr(
            pipeline,
            "stt_engine",
            "stt_engine_id",
            "stt_provider",
            "stt_provider_id",
        )
    )


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


async def _process_with_stt_engine(
    stt: Any,
    hass: HomeAssistant,
    metadata: Any,
    stream: AsyncIterator[bytes],
    engine: str,
) -> Any:
    getter = getattr(stt, "async_get_speech_to_text_engine", None)
    if callable(getter):
        provider = getter(hass, engine)
        if provider is None:
            raise SpotifyDJNoSttProviderError(f"STT provider not found: {engine}")
        checker = getattr(provider, "check_metadata", None)
        if callable(checker) and not checker(metadata):
            _LOGGER.warning(
                "SpotifyDJ STT provider %s does not support metadata %s",
                engine,
                metadata,
            )
        entity_processor = getattr(provider, "internal_async_process_audio_stream", None)
        if callable(entity_processor):
            return await entity_processor(metadata, stream)
        provider_processor = getattr(provider, "async_process_audio_stream", None)
        if callable(provider_processor):
            return await _call_stt_processor(provider_processor, metadata, stream)
        raise SpotifyDJNoSttProviderError(f"STT provider cannot process audio: {engine}")

    legacy_processor = getattr(stt, "async_process_audio_stream", None)
    if callable(legacy_processor):
        return await _call_legacy_stt_processor(
            legacy_processor,
            hass,
            metadata,
            stream,
            engine,
        )

    raise SpotifyDJNoSttProviderError(_no_stt_provider_message())


async def _call_stt_processor(
    processor: Any,
    metadata: Any,
    stream: AsyncIterator[bytes],
) -> Any:
    try:
        return await processor(metadata=metadata, stream=stream)
    except TypeError:
        return await processor(metadata, stream)


async def _call_legacy_stt_processor(
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


def _result_state(result: Any) -> str | None:
    if isinstance(result, dict):
        state = result.get("state")
    else:
        state = getattr(result, "state", None)
    return str(state) if state is not None else None


def _text_from_pipeline_events(events: list[Any]) -> str:
    for event in reversed(events):
        data = _event_data(event)
        for key in ("text", "stt_text"):
            value = data.get(key)
            if value:
                return str(value).strip()
        stt_output = data.get("stt_output")
        if isinstance(stt_output, dict) and stt_output.get("text"):
            return str(stt_output["text"]).strip()
        text = getattr(stt_output, "text", None)
        if text:
            return str(text).strip()
    return ""


def _event_types(events: list[Any]) -> list[str]:
    values: list[str] = []
    for event in events:
        if isinstance(event, dict):
            event_type = event.get("type")
        else:
            event_type = getattr(event, "type", None)
        values.append(str(event_type) if event_type is not None else type(event).__name__)
    return values


def _event_data(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        data = event.get("data", event)
    else:
        data = getattr(event, "data", None) or getattr(event, "as_dict", lambda: {})()
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
    return data if isinstance(data, dict) else {}


def _require_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise SpotifyDJSttError("HA Assist STT did not return recognized text")
    return text


def _first_attr(obj: Any, *names: str) -> Any:
    for name in names:
        value = _pipeline_attr(obj, name)
        if value:
            return value
    return None


def _pipeline_attr(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _ha_version() -> str:
    try:
        from homeassistant.const import __version__

        return str(__version__)
    except Exception:  # noqa: BLE001
        return "unknown"
