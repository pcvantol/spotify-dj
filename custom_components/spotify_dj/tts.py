from __future__ import annotations

from homeassistant.core import HomeAssistant

from .wav_util import simple_tone_wav


async def create_openai_tts_wav(hass: HomeAssistant, text: str, conf: dict) -> bytes:
    raise RuntimeError("Direct TTS is disabled in SpotifyDJ; use HA TTS services instead")


async def create_error_wav(hass: HomeAssistant, message: str, conf: dict) -> bytes:
    return simple_tone_wav()
