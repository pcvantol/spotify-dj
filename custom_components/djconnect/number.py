from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CLIENT_TYPE_ESP32, DOMAIN
from .entity_ids import entry_unique_id
from .spotify_backend import handle_spotify_command

MIN_VOLUME = 0.0
MAX_VOLUME = 60.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    entities: list[NumberEntity] = [DJConnectVolumeNumber(runtime, hass)]
    if _runtime_client_type(runtime) == CLIENT_TYPE_ESP32:
        entities.extend(
            [
                DJConnectCommandNumber(
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
                DJConnectCommandNumber(
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
                DJConnectCommandNumber(
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
    async_add_entities(entities)


class DJConnectVolumeNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "volume"
    _attr_unique_id = "djconnect_volume"
    _attr_native_min_value = MIN_VOLUME
    _attr_native_max_value = MAX_VOLUME
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, runtime: Any, hass: HomeAssistant) -> None:
        self.runtime = runtime
        self.hass = hass
        self._attr_unique_id = entry_unique_id(runtime, "volume")
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


class DJConnectCommandNumber(NumberEntity):
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
        self._attr_unique_id = entry_unique_id(runtime, translation_key)
        self._attr_native_min_value = min_value
        self._attr_native_max_value = max_value
        self._attr_native_unit_of_measurement = unit
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
    def native_value(self) -> float | None:
        number = _device_setting_number(
            self.runtime.device_status,
            self.status_key,
            self.value_multiplier,
        )
        if number is None:
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


def _device_setting_number(
    status: dict[str, Any],
    status_key: str,
    value_multiplier: int,
) -> float | None:
    for key, divisor in _status_key_aliases(status_key, value_multiplier):
        if key not in status:
            continue
        try:
            value = float(status[key])
        except (TypeError, ValueError):
            continue
        if divisor > 1:
            value /= divisor
        return value
    return None


def _status_key_aliases(status_key: str, value_multiplier: int) -> list[tuple[str, int]]:
    if status_key == "screen_brightness":
        return [
            ("screen_brightness", 1),
            ("screen_brightness_percent", 1),
            ("screen_brightness_level", 1),
            ("brightness", 1),
            ("display_brightness", 1),
        ]
    if status_key == "speaker_volume":
        return [
            ("speaker_volume", 1),
            ("speaker_volume_percent", 1),
            ("cue_volume", 1),
            ("sound_volume", 1),
            ("volume_percent_local", 1),
            ("local_volume", 1),
            ("volume", 1),
        ]
    if status_key == "screen_timeout":
        return [
            ("screen_timeout", 1),
            ("screen_timeout_seconds", 1),
            ("screen_timeout_ms", value_multiplier),
            ("screen_off_timeout_ms", value_multiplier),
            ("screen_dim_timeout", value_multiplier),
            ("screen_dim_timeout_ms", value_multiplier),
        ]
    if status_key == "turn_off_after":
        return [
            ("turn_off_after_minutes", 1),
            ("turn_off_after", value_multiplier),
            ("turn_off_after_ms", value_multiplier),
            ("auto_off_timeout", value_multiplier),
        ]
    return [(status_key, 1)]


def _runtime_client_type(runtime: Any) -> str:
    getter = getattr(runtime, "client_type", None)
    if callable(getter):
        return str(getter() or CLIENT_TYPE_ESP32)
    status = getattr(runtime, "device_status", {}) or {}
    config = getattr(runtime, "config", {}) or {}
    return str(status.get("client_type") or config.get("client_type") or CLIENT_TYPE_ESP32)
