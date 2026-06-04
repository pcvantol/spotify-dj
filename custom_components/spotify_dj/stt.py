"""Speech-to-text helpers for SpotifyDJ."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant


async def transcribe_wav_with_ha(
    hass: HomeAssistant,
    wav_data: bytes,
    config: dict[str, Any],
) -> str:
    """Transcribe WAV audio through Home Assistant STT.

    Uses HA's stt.transcribe service. The uploaded WAV is written to a temp file
    because HA STT providers generally expect a file/media source.
    """
    if not wav_data:
        raise RuntimeError("Geen audio ontvangen")

    # Basic sanity check: RIFF/WAV
    if not wav_data.startswith(b"RIFF"):
        raise RuntimeError("Audio is geen WAV/RIFF bestand")

    language = config.get("tts_language") or "nl-NL"

    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        ) as tmp:
            tmp.write(wav_data)
            tmp_path = Path(tmp.name)

        response = await hass.services.async_call(
            "stt",
            "transcribe",
            {
                "entity_id": config.get("stt_entity_id") or None,
                "media_content_id": str(tmp_path),
                "language": language,
            },
            blocking=True,
            return_response=True,
        )

        # HA service response shapes differ slightly by STT provider/version.
        speech = (
            response.get("text")
            or response.get("speech")
            or response.get("result")
            or response.get("response", {}).get("text")
            or response.get("response", {}).get("speech")
        )

        if not speech:
            raise RuntimeError(f"STT gaf geen tekst terug: {response}")

        return str(speech).strip()

    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)