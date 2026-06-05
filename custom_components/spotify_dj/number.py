from __future__ import annotations

from typing import Any

from aiohttp import ClientTimeout
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

MIN_VOLUME = 0.0
MAX_VOLUME = 60.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SpotifyDJVolumeNumber(runtime, hass)])


class SpotifyDJVolumeNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "volume"
    _attr_unique_id = "spotifydj_volume"
    _attr_native_min_value = MIN_VOLUME
    _attr_native_max_value = MAX_VOLUME
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, runtime: Any, hass: HomeAssistant) -> None:
        self.runtime = runtime
        self.hass = hass
        runtime.listeners.append(self._handle_runtime_update)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.runtime.entry.entry_id)},
            name="SpotifyDJ",
            manufacturer="SpotifyDJ",
            model="SpotifyDJ device",
        )

    @property
    def native_value(self) -> float | None:
        value = _volume_value(self.runtime.device_status)
        if value is None or value < MIN_VOLUME:
            return None
        return min(MAX_VOLUME, value)

    async def async_set_native_value(self, value: float) -> None:
        volume = max(MIN_VOLUME, min(MAX_VOLUME, float(value)))
        local_url = await self.runtime.async_device_local_url(self.hass)
        if not local_url:
            raise RuntimeError("SpotifyDJ device local_url is unknown")
        session = async_get_clientsession(self.hass)
        async with session.post(
            local_url.rstrip("/") + "/api/device/volume",
            json={"volume": volume},
            headers=self.runtime.device_headers(),
            timeout=ClientTimeout(total=15),
        ) as resp:
            text = await resp.text()
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(f"ESP volume request failed HTTP {resp.status}: {text}")
        self.runtime.device_status["volume"] = volume
        self.runtime.update()

    @callback
    def _handle_runtime_update(self) -> None:
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._handle_runtime_update in self.runtime.listeners:
            self.runtime.listeners.remove(self._handle_runtime_update)


def _volume_value(status: dict[str, Any]) -> float | None:
    for key in ("volume", "volume_percent", "volume_percent_local"):
        if key not in status:
            continue
        try:
            return float(status[key])
        except (TypeError, ValueError):
            return None
    return None
