"""Home Assistant Assist STT for SpotifyDJ."""

from __future__ import annotations

import asyncio
import io
import wave
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent


def wav_to_pcm(wav_data: bytes) -> tuple[bytes, int]:
    """Extract PCM16 mono from WAV."""

    with wave.open(io.BytesIO(wav_data), "rb") as wav:
        rate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()

        if channels != 1:
            raise RuntimeError(
                f"Expected mono WAV, got {channels}"
            )

        if width != 2:
            raise RuntimeError(
                f"Expected PCM16 WAV, got width={width}"
            )

        pcm = wav.readframes(
            wav.getnframes()
        )

    return pcm, rate


async def transcribe_wav_with_ha(
    hass: HomeAssistant,
    wav_data: bytes,
    config: dict[str, Any],
) -> str:
    """Run WAV through HA Assist pipeline STT."""

    if not wav_data.startswith(b"RIFF"):
        raise RuntimeError("Geen geldige WAV")

    pcm, rate = wav_to_pcm(wav_data)

    from homeassistant.components.assist_pipeline import pipeline

    events = []
    result_text = None

    async def on_event(event):
        nonlocal result_text

        events.append(event)

        data = getattr(event, "data", {}) or {}

        # HA 2026 STT event
        if data.get("stt_output"):
            result_text = (
                data["stt_output"]
                .get("text")
            )

    class AudioStream:
        """Minimal async audio stream."""

        async def __aiter__(self):
            chunk = 4096

            for pos in range(
                0,
                len(pcm),
                chunk,
            ):
                yield pcm[pos:pos+chunk]
                await asyncio.sleep(0)


    await pipeline.async_pipeline_from_audio_stream(
        hass,
        context=None,
        pipeline_id=(
            config.get("assist_pipeline_id")
            or None
        ),
        audio_stream=AudioStream(),
        audio_sample_rate=rate,
        start_stage="stt",
        end_stage="stt",
        event_callback=on_event,
    )


    if not result_text:
        raise RuntimeError(
            f"Geen STT resultaat: {events}"
        )

    return result_text