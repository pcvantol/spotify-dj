from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .spotify_backend import handle_spotify_command

MIN_VOLUME = 0.0
MAX_VOLUME = 60.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SpotifyDJVolumeNumber(runtime, hass),
            SpotifyDJCommandNumber(
                runtime,
                hass,
                "screen_brightness",
                "brightness",
                "screen_brightness",
                "value",
                0,
                100,
                "%",
            ),
            SpotifyDJCommandNumber(
                runtime,
                hass,
                "screen_timeout",
                "screen_timeout",
                "screen_dim_timeout",
                "value",
                0,
                600,
                "s",
                value_multiplier=1000,
            ),
            SpotifyDJCommandNumber(
                runtime,
                hass,
                "turn_off_after",
                "turn_off_after",
                "turn_off_after",
                "value",
                0,
                240,
                "min",
                value_multiplier=60000,
            ),
            SpotifyDJCommandNumber(
                runtime,
                hass,
                "speaker_volume",
                "speaker_volume",
                "speaker_volume",
                "value",
                0,
                100,
                "%",
            ),
        ]
    )


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
        await handle_spotify_command(
            self.hass,
            self.runtime,
            "set_volume",
            int(volume),
        )
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


class SpotifyDJCommandNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_native_step = 1.0

    def __init__(
        self,
        runtime: Any,
        hass: HomeAssistant,
        status_key: str,
        translation_key: str,
        command: str,
        payload_key: str,
        min_value: float,
        max_value: float,
        unit: str | None,
        *,
        value_multiplier: int = 1,
    ) -> None:
        self.runtime = runtime
        self.hass = hass
        self.status_key = status_key
        self.command = command
        self.payload_key = payload_key
        self.value_multiplier = value_multiplier
        self._attr_translation_key = translation_key
        self._attr_unique_id = f"spotifydj_{translation_key}"
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_unit_of_measurement = unit
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
        value = self.runtime.device_status.get(self.status_key)
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number < self._attr_native_min_value:
            return None
        return min(self._attr_native_max_value, number)

    async def async_set_native_value(self, value: float) -> None:
        number = max(
            self._attr_native_min_value,
            min(self._attr_native_max_value, float(value)),
        )
        await self.runtime.async_device_command(
            self.hass,
            self.command,
            **{self.payload_key: int(number * self.value_multiplier)},
        )
        self.runtime.device_status[self.status_key] = number
        self.runtime.update()

    @callback
    def _handle_runtime_update(self) -> None:
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._handle_runtime_update in self.runtime.listeners:
            self.runtime.listeners.remove(self._handle_runtime_update)
