from __future__ import annotations

import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

from . import DEFAULT_TEST_TTS_TEXT, async_speak_dj_test
from .const import DOMAIN
from .spotify_backend import SpotifyBackendError, handle_spotify_command

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SpotifyDJTestVoiceButton(runtime, hass),
            SpotifyDJCommandButton(runtime, hass, "next", "next_track"),
            SpotifyDJCommandButton(runtime, hass, "previous", "previous_track"),
            SpotifyDJCommandButton(runtime, hass, "play_pause", "play_pause"),
            SpotifyDJRefreshInfoButton(runtime, hass),
            SpotifyDJRebootButton(runtime, hass),
        ]
    )

class SpotifyDJTestVoiceButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "test_dj_response"
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
        await async_speak_dj_test(self.hass, self.runtime, DEFAULT_TEST_TTS_TEXT)
        _LOGGER.debug("SpotifyDJ test button sent DJ response to device")


class SpotifyDJBaseButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, runtime, hass: HomeAssistant, translation_key: str) -> None:
        self.runtime = runtime
        self.hass = hass
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"spotifydj_{translation_key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.runtime.entry.entry_id)},
            name="SpotifyDJ",
            manufacturer="SpotifyDJ",
            model="SpotifyDJ device",
        )


class SpotifyDJCommandButton(SpotifyDJBaseButton):
    def __init__(
        self,
        runtime,
        hass: HomeAssistant,
        command: str,
        translation_key: str,
    ) -> None:
        super().__init__(runtime, hass, translation_key)
        self.command = command

    async def async_press(self) -> None:
        try:
            if self.command in {"next", "previous", "play_pause"}:
                backend_command = self.command
                if self.command == "play_pause":
                    playback = self.runtime.last_playback or {}
                    backend_command = "pause" if playback.get("is_playing") else "play"
                await handle_spotify_command(self.hass, self.runtime, backend_command)
            else:
                await self.runtime.async_device_command(self.hass, self.command)
        except SpotifyBackendError as exc:
            self.runtime.update(last_error=str(exc))
            _LOGGER.warning("SpotifyDJ button command unavailable: %s", exc)
            return
        _LOGGER.debug("SpotifyDJ button sent command %s", self.command)


class SpotifyDJRefreshInfoButton(SpotifyDJBaseButton):
    def __init__(self, runtime, hass: HomeAssistant) -> None:
        super().__init__(runtime, hass, "refresh_device_info")

    async def async_press(self) -> None:
        await self.runtime.async_refresh_device_info(self.hass)


class SpotifyDJRebootButton(SpotifyDJBaseButton):
    def __init__(self, runtime, hass: HomeAssistant) -> None:
        super().__init__(runtime, hass, "reboot_device")

    async def async_press(self) -> None:
        await self.runtime.async_device_post(self.hass, "/api/device/reboot")
