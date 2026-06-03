from __future__ import annotations

import logging
from homeassistant.core import HomeAssistant
from .const import CONF_OPENAI_API_KEY, CONF_OPENAI_STT_MODEL, DEFAULT_STT_MODEL
from .openai_client import transcribe_wav

_LOGGER = logging.getLogger(__name__)

async def wav_to_text(hass: HomeAssistant, wav: bytes, conf: dict) -> str:
    api_key = conf[CONF_OPENAI_API_KEY]
    model = conf.get(CONF_OPENAI_STT_MODEL, DEFAULT_STT_MODEL)
    text = await transcribe_wav(hass, api_key, model, wav, language="nl")
    _LOGGER.info("SpotifyDJ STT: %s", text)
    return text
