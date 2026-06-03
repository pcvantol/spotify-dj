from __future__ import annotations

import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .tts import create_openai_tts_wav

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SpotifyDJTestVoiceButton(runtime, hass)])

class SpotifyDJTestVoiceButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Test DJ voice"
    _attr_unique_id = "spotifydj_test_dj_voice"

    def __init__(self, runtime, hass: HomeAssistant) -> None:
        self.runtime = runtime
        self.hass = hass

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self.runtime.entry.entry_id)}, name="SpotifyDJ", manufacturer="SpotifyDJ", model="LilyGO Voice Remote")

    async def async_press(self) -> None:
        text = "Daar gaan we hoor. SpotifyDJ is wakker en klaar voor je volgende plaat."
        wav = await create_openai_tts_wav(self.hass, text, self.runtime.config)
        self.runtime.update(last_dj_text=text, last_error=None)
        _LOGGER.warning("SpotifyDJ test button generated %d wav bytes", len(wav))
