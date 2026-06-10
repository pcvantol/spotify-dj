from __future__ import annotations

import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo

from . import DEFAULT_TEST_TTS_TEXT, async_speak_dj_test
from .const import DOMAIN
from .entity_ids import entry_unique_id
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
            DJConnectTestVoiceButton(runtime, hass),
            DJConnectCommandButton(runtime, hass, "next", "next_track"),
            DJConnectCommandButton(runtime, hass, "previous", "previous_track"),
            DJConnectCommandButton(runtime, hass, "play_pause", "play_pause"),
            DJConnectRefreshUpNextButton(runtime, hass),
            DJConnectRefreshInfoButton(runtime, hass),
            DJConnectRebootButton(runtime, hass),
        ]
    )

class DJConnectTestVoiceButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "test_dj_response"
    _attr_unique_id = "djconnect_test_dj_voice"

    def __init__(self, runtime, hass: HomeAssistant) -> None:
        self.runtime = runtime
        self.hass = hass
        self._attr_unique_id = entry_unique_id(runtime, "test_dj_voice")

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.runtime.entry.entry_id)},
            name="DJConnect",
            manufacturer="DJConnect",
            model="DJConnect device",
        )

    async def async_press(self) -> None:
        await async_speak_dj_test(self.hass, self.runtime, DEFAULT_TEST_TTS_TEXT)
        _LOGGER.debug("DJConnect test button sent DJ response to device")


class DJConnectBaseButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, runtime, hass: HomeAssistant, translation_key: str) -> None:
        self.runtime = runtime
        self.hass = hass
        self._attr_translation_key = translation_key
        self._attr_unique_id = entry_unique_id(runtime, translation_key)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.runtime.entry.entry_id)},
            name="DJConnect",
            manufacturer="DJConnect",
            model="DJConnect device",
        )


class DJConnectCommandButton(DJConnectBaseButton):
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
            if self.command in {"next", "previous"}:
                await self.runtime.async_device_command(self.hass, self.command)
            elif self.command == "play_pause":
                playback = await self._current_playback_for_toggle()
                backend_command = "pause" if playback.get("is_playing") else "play"
                await handle_spotify_command(self.hass, self.runtime, backend_command)
            else:
                await self.runtime.async_device_command(self.hass, self.command)
        except SpotifyBackendError as exc:
            self.runtime.update(last_error=str(exc))
            _LOGGER.warning("DJConnect button command unavailable: %s", exc)
            return
        _LOGGER.debug("DJConnect button sent command %s", self.command)

    async def _current_playback_for_toggle(self) -> dict[str, Any]:
        try:
            result = await handle_spotify_command(self.hass, self.runtime, "status")
            playback = result.get("playback") if isinstance(result, dict) else None
            if isinstance(playback, dict):
                return playback
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("DJConnect button playback status refresh failed: %s", exc)
        return self.runtime.last_playback or {}


class DJConnectRefreshInfoButton(DJConnectBaseButton):
    def __init__(self, runtime, hass: HomeAssistant) -> None:
        super().__init__(runtime, hass, "refresh_device_info")

    async def async_press(self) -> None:
        await self.runtime.async_refresh_device_info(self.hass)


class DJConnectRefreshUpNextButton(DJConnectBaseButton):
    def __init__(self, runtime, hass: HomeAssistant) -> None:
        super().__init__(runtime, hass, "refresh_up_next")

    async def async_press(self) -> None:
        try:
            await handle_spotify_command(self.hass, self.runtime, "queue")
        except SpotifyBackendError as exc:
            self.runtime.update(last_error=str(exc))
            _LOGGER.warning("DJConnect up next refresh unavailable: %s", exc)


class DJConnectRebootButton(DJConnectBaseButton):
    def __init__(self, runtime, hass: HomeAssistant) -> None:
        super().__init__(runtime, hass, "reboot_device")

    async def async_press(self) -> None:
        await self.runtime.async_device_post(self.hass, "/api/device/reboot")
