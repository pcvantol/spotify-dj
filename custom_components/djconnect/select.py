from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CLIENT_TYPE_ESP32, DOMAIN
from .entity_ids import entry_unique_id
from .spotify_backend import handle_spotify_command

_LOGGER = logging.getLogger(__name__)

TURN_OFF_AFTER_OPTIONS = ["5", "15", "30", "60"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    entities: list[SelectEntity] = [
        DJConnectCommandSelect(
            runtime,
            hass,
            "sound_output",
            "sound_output",
            "set_output",
            _options_from_status(runtime.device_status),
        ),
        DJConnectCommandSelect(
            runtime,
            hass,
            "repeat_state",
            "repeat_state",
            "set_repeat",
            ["off", "track", "context"],
        ),
    ]
    if _runtime_client_type(runtime) == CLIENT_TYPE_ESP32:
        entities.extend(
            [
            DJConnectCommandSelect(
                runtime,
                hass,
                "language",
                "language",
                "language",
                ["en", "nl"],
            ),
            DJConnectCommandSelect(
                runtime,
                hass,
                "turn_off_after",
                "turn_off_after",
                "turn_off_after",
                TURN_OFF_AFTER_OPTIONS,
            ),
            DJConnectCommandSelect(
                runtime,
                hass,
                "theme",
                "theme",
                "theme",
                ["light", "dark", "auto"],
            ),
            DJConnectCommandSelect(
                runtime,
                hass,
                "log_level",
                "log_level",
                "log_level",
                ["debug", "info", "warning", "error"],
            ),
            ]
        )
    async_add_entities(entities)


class DJConnectCommandSelect(SelectEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        runtime: Any,
        hass: HomeAssistant,
        status_key: str,
        translation_key: str,
        command: str,
        options: list[str],
    ) -> None:
        self.runtime = runtime
        self.hass = hass
        self.status_key = status_key
        self.command = command
        self._fallback_options = list(options)
        self._attr_translation_key = translation_key
        self._attr_unique_id = entry_unique_id(runtime, translation_key)
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
    def options(self) -> list[str]:
        if self.status_key == "sound_output":
            options = _options_from_status(
                self.runtime.device_status,
                self._fallback_options,
            )
            current = self.current_option
            if current and current not in options:
                options.append(current)
            return options
        current = self.current_option
        options = list(self._fallback_options)
        if current and current not in options:
            options.append(current)
        return options

    @property
    def current_option(self) -> str | None:
        if self.status_key == "sound_output":
            return _current_sound_output(self.runtime)
        if self.status_key == "turn_off_after":
            return _current_turn_off_after(self.runtime.device_status)
        value = self.runtime.device_status.get(self.status_key)
        if value not in (None, ""):
            return str(value)
        defaults = {
            "theme": "auto",
            "log_level": "info",
            "language": self.runtime.config.get("device_language", "en"),
        }
        return defaults.get(self.status_key)

    async def async_select_option(self, option: str) -> None:
        if self.command == "set_output":
            await handle_spotify_command(
                self.hass,
                self.runtime,
                "set_output",
                _output_id_from_option(self.runtime.device_status, option),
                play=False,
            )
        elif self.command == "set_repeat":
            await handle_spotify_command(
                self.hass,
                self.runtime,
                "set_repeat",
                option,
            )
            await self._refresh_device_display()
        elif self.command == "turn_off_after":
            minutes = _closest_turn_off_after_minutes(option)
            await self.runtime.async_device_command(
                self.hass,
                self.command,
                value=minutes * 60000,
            )
            option = str(minutes)
        else:
            await self.runtime.async_device_command(self.hass, self.command, value=option)
        self.runtime.device_status[self.status_key] = option
        self.runtime.update()

    async def async_update(self) -> None:
        if self.status_key != "sound_output":
            return
        try:
            await handle_spotify_command(self.hass, self.runtime, "devices")
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("DJConnect sound output refresh failed: %s", exc)

    @callback
    def _handle_runtime_update(self) -> None:
        self.async_write_ha_state()

    async def _refresh_device_display(self) -> None:
        try:
            await self.runtime.async_device_command(self.hass, "status")
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("DJConnect device display refresh failed: %s", exc)

    async def async_will_remove_from_hass(self) -> None:
        if self._handle_runtime_update in self.runtime.listeners:
            self.runtime.listeners.remove(self._handle_runtime_update)


def _options_from_status(
    status: dict[str, Any],
    fallback: list[str] | None = None,
) -> list[str]:
    values = _output_values(status) or fallback or []
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    options: list[str] = []
    for value in values:
        if isinstance(value, dict):
            label = value.get("name") or value.get("id")
        else:
            label = value
        if str(label or "").strip():
            options.append(str(label))
    return options


def _output_id_from_option(status: dict[str, Any], option: str) -> str:
    values = _output_values(status)
    if not isinstance(values, list):
        return option
    for value in values:
        if not isinstance(value, dict):
            continue
        if value.get("name") == option or value.get("id") == option:
            return str(value.get("id") or option)
    return option


def _current_sound_output(runtime: Any) -> str | None:
    status = runtime.device_status
    playback = runtime.last_playback or {}
    device = playback.get("device") if isinstance(playback, dict) else None
    if isinstance(device, dict) and device.get("name"):
        return str(device["name"])
    for key in ("sound_output", "output"):
        value = status.get(key)
        if value not in (None, ""):
            return str(value)
    values = _output_values(status)
    if isinstance(values, list):
        for value in values:
            if isinstance(value, dict) and value.get("active"):
                label = value.get("name") or value.get("id")
                if label not in (None, ""):
                    return str(label)
    return None


def _output_values(status: dict[str, Any]) -> list[Any]:
    for key in ("available_outputs", "outputs", "devices"):
        values = status.get(key)
        if isinstance(values, dict):
            for nested_key in ("items", "outputs", "devices"):
                nested = values.get(nested_key)
                if isinstance(nested, list):
                    return nested
        if isinstance(values, list):
            return values
        if isinstance(values, str) and values.strip():
            return [item.strip() for item in values.split(",")]
    return []


def _current_turn_off_after(status: dict[str, Any]) -> str | None:
    minutes = _turn_off_after_minutes(status)
    if minutes is None:
        return None
    return str(_closest_turn_off_after_minutes(minutes))


def _turn_off_after_minutes(status: dict[str, Any]) -> int | None:
    aliases = (
        ("turn_off_after_minutes", 1),
        ("turn_off_after", 60000),
        ("turn_off_after_ms", 60000),
        ("auto_off_timeout", 60000),
    )
    for key, divisor in aliases:
        if key not in status:
            continue
        try:
            value = float(status[key])
        except (TypeError, ValueError):
            continue
        if divisor > 1:
            value /= divisor
        return int(round(value))
    return None


def _closest_turn_off_after_minutes(value: Any) -> int:
    try:
        minutes = int(float(value))
    except (TypeError, ValueError):
        return 15
    allowed = [int(option) for option in TURN_OFF_AFTER_OPTIONS]
    return min(allowed, key=lambda option: abs(option - minutes))


def _runtime_client_type(runtime: Any) -> str:
    getter = getattr(runtime, "client_type", None)
    if callable(getter):
        return str(getter() or CLIENT_TYPE_ESP32)
    status = getattr(runtime, "device_status", {}) or {}
    config = getattr(runtime, "config", {}) or {}
    return str(status.get("client_type") or config.get("client_type") or CLIENT_TYPE_ESP32)
