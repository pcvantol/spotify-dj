from __future__ import annotations

import asyncio
import io
import logging
import wave
from collections.abc import AsyncIterator
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_ASSIST_PIPELINE_ID, CONF_TTS_LANGUAGE, DEFAULT_TTS_LANGUAGE, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def transcribe_wav_with_assist(
    hass: HomeAssistant,
    wav: bytes,
    conf: dict[str, Any],
) -> str:
    """Transcribe WAV audio through Home Assistant Assist/STT backend."""
    test_handler = hass.data.get(DOMAIN, {}).get("stt_handler")
    if callable(test_handler):
        result = test_handler(hass, wav, conf)
        if hasattr(result, "__await__"):
            result = await result
        return _require_text(result)

    metadata = _wav_metadata(wav, conf)
    events: list[dict[str, Any]] = []

    async def event_callback(event: dict[str, Any]) -> None:
        events.append(event)

    try:
        from homeassistant.components.assist_pipeline import pipeline

        runner = getattr(pipeline, "async_pipeline_from_audio_stream", None)
        if runner is None:
            raise RuntimeError("Home Assistant Assist audio pipeline helper is unavailable")

        kwargs = {
            "hass": hass,
            "context": None,
            "event_callback": event_callback,
            "stt_metadata": metadata,
            "stt_stream": _audio_chunks(wav),
            "pipeline_id": conf.get(CONF_ASSIST_PIPELINE_ID) or None,
        }
        try:
            await runner(**kwargs)
        except TypeError:
            await runner(
                hass,
                None,
                event_callback,
                metadata,
                _audio_chunks(wav),
                pipeline_id=conf.get(CONF_ASSIST_PIPELINE_ID) or None,
            )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"HA Assist STT failed: {exc}") from exc

    return _require_text(_text_from_events(events))


def _wav_metadata(wav: bytes, conf: dict[str, Any]) -> Any:
    """Build HA STT metadata from a WAV header, with a dict fallback for tests."""
    sample_rate = 16000
    channels = 1
    sample_width = 2
    try:
        with wave.open(io.BytesIO(wav), "rb") as wav_file:
            sample_rate = int(wav_file.getframerate())
            channels = int(wav_file.getnchannels())
            sample_width = int(wav_file.getsampwidth())
    except Exception:  # noqa: BLE001
        _LOGGER.debug("SpotifyDJ could not parse WAV header; using default STT metadata")

    try:
        from homeassistant.components import stt

        return stt.SpeechMetadata(
            language=conf.get(CONF_TTS_LANGUAGE) or DEFAULT_TTS_LANGUAGE,
            format=stt.AudioFormats.WAV,
            codec=stt.AudioCodecs.PCM,
            bit_rate=sample_rate * sample_width * channels * 8,
            sample_rate=sample_rate,
            channel=channels,
        )
    except Exception:  # noqa: BLE001
        return {
            "language": conf.get(CONF_TTS_LANGUAGE) or DEFAULT_TTS_LANGUAGE,
            "format": "wav",
            "codec": "pcm",
            "sample_rate": sample_rate,
            "channel": channels,
        }


async def _audio_chunks(wav: bytes, chunk_size: int = 4096) -> AsyncIterator[bytes]:
    for offset in range(0, len(wav), chunk_size):
        yield wav[offset : offset + chunk_size]
        await asyncio.sleep(0)


def _text_from_events(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        data = event.get("data") if isinstance(event, dict) else None
        if not isinstance(data, dict):
            data = event
        for key in ("text", "stt_text"):
            if isinstance(data, dict) and data.get(key):
                return str(data[key]).strip()
        stt_output = data.get("stt_output") if isinstance(data, dict) else None
        if isinstance(stt_output, dict) and stt_output.get("text"):
            return str(stt_output["text"]).strip()
    return ""


def _require_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise RuntimeError("HA Assist STT did not return recognized text")
    return text
