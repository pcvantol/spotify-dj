from __future__ import annotations

import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    CONF_SPOTIFY_PLAYER,
    CONF_TTS_ENGINE,
    CONF_TTS_LANGUAGE,
    DEFAULT_TTS_ENGINE,
    DEFAULT_TTS_LANGUAGE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SpotifyDJTestVoiceButton(runtime, hass)])

class SpotifyDJTestVoiceButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Test DJ response TTS"
    _attr_unique_id = "spotifydj_test_dj_voice"

    def __init__(self, runtime, hass: HomeAssistant) -> None:
        self.runtime = runtime
        self.hass = hass

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.runtime.entry.entry_id)},
            name="SpotifyDJ",
            manufacturer="SpotifyDJ",
            model="SpotifyDJ device",
        )

    async def async_press(self) -> None:
        text = (
            "Daar gaan we. SpotifyDJ is gekoppeld, de stem werkt, "
            "en ik sta klaar voor je volgende plaat."
        )
        conf = self.runtime.config
        player = conf.get(CONF_SPOTIFY_PLAYER)
        if not player:
            raise RuntimeError(
                "Configureer eerst een Spotify/media_player in SpotifyDJ options"
            )
        await self.hass.services.async_call(
            "tts",
            "speak",
            {
                "entity_id": conf.get(CONF_TTS_ENGINE, DEFAULT_TTS_ENGINE),
                "media_player_entity_id": player,
                "message": text,
                "language": conf.get(CONF_TTS_LANGUAGE, DEFAULT_TTS_LANGUAGE),
            },
            blocking=True,
        )
        self.runtime.update(last_dj_text=text, last_error=None)
        _LOGGER.warning("SpotifyDJ test button sent text to HA TTS: %s", text)
