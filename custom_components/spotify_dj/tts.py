from __future__ import annotations

import logging
from homeassistant.core import HomeAssistant

from .const import (
    CONF_OPENAI_API_KEY, CONF_OPENAI_TTS_MODEL, CONF_OPENAI_TTS_VOICE, CONF_DJ_STYLE,
    DEFAULT_TTS_MODEL, DEFAULT_TTS_VOICE, DEFAULT_DJ_STYLE,
)
from .openai_client import speech_wav
from .wav_util import simple_tone_wav

_LOGGER = logging.getLogger(__name__)

async def create_openai_tts_wav(hass: HomeAssistant, text: str, conf: dict) -> bytes:
    api_key = conf[CONF_OPENAI_API_KEY]
    model = conf.get(CONF_OPENAI_TTS_MODEL, DEFAULT_TTS_MODEL)
    voice = conf.get(CONF_OPENAI_TTS_VOICE, DEFAULT_TTS_VOICE)
    style = conf.get(CONF_DJ_STYLE, DEFAULT_DJ_STYLE)
    instructions = (
        f"Spreek Nederlands als {style}. "
        "Korte radiopresentatie, glimlach in de stem, natuurlijke pauzes. "
        "Niet schreeuwerig. Imiteer geen specifieke bestaande persoon."
    )
    wav = await speech_wav(hass, api_key, model, voice, text, instructions=instructions)
    _LOGGER.info("SpotifyDJ TTS generated %d bytes", len(wav))
    return wav

async def create_error_wav(hass: HomeAssistant, message: str, conf: dict) -> bytes:
    try:
        return await create_openai_tts_wav(hass, message, conf)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Could not create spoken error WAV, returning tone")
        return simple_tone_wav()
