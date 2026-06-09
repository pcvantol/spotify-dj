from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .spotify_backend import handle_spotify_command

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DJConnectShuffleSwitch(runtime, hass)])


class DJConnectShuffleSwitch(SwitchEntity):
    """Home Assistant switch for backend playback shuffle."""

    _attr_has_entity_name = True
    _attr_translation_key = "shuffle"
    _attr_unique_id = "djconnect_shuffle"

    def __init__(self, runtime: Any, hass: HomeAssistant) -> None:
        self.runtime = runtime
        self.hass = hass
        runtime.listeners.append(self._handle_runtime_update)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.runtime.entry.entry_id)},
            name="DJConnect",
            manufacturer="DJConnect",
            model="DJConnect device",
        )

    @property
    def is_on(self) -> bool | None:
        playback = self.runtime.last_playback or {}
        if "shuffle" in playback:
            return bool(playback.get("shuffle"))
        if "shuffle" in self.runtime.device_status:
            return bool(self.runtime.device_status.get("shuffle"))
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set_shuffle(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_shuffle(False)

    async def _set_shuffle(self, enabled: bool) -> None:
        await handle_spotify_command(self.hass, self.runtime, "set_shuffle", enabled)
        self.runtime.device_status["shuffle"] = enabled
        self.runtime.update()
        await self._refresh_device_display()

    async def _refresh_device_display(self) -> None:
        try:
            await self.runtime.async_device_command(self.hass, "status")
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("DJConnect device display refresh failed: %s", exc)

    @callback
    def _handle_runtime_update(self) -> None:
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._handle_runtime_update in self.runtime.listeners:
            self.runtime.listeners.remove(self._handle_runtime_update)
