from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SpotifyDJCommandSelect(
                runtime,
                hass,
                "sound_output",
                "sound_output",
                "set_output",
                _options_from_status(runtime.device_status, "available_outputs"),
            ),
            SpotifyDJCommandSelect(
                runtime,
                hass,
                "language",
                "language",
                "set_language",
                ["en", "nl"],
            ),
            SpotifyDJCommandSelect(
                runtime,
                hass,
                "theme",
                "theme",
                "set_theme",
                ["light", "dark", "auto"],
            ),
            SpotifyDJCommandSelect(
                runtime,
                hass,
                "log_level",
                "log_level",
                "set_log_level",
                ["debug", "info", "warning", "error"],
            ),
        ]
    )


class SpotifyDJCommandSelect(SelectEntity):
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
        self._attr_unique_id = f"spotifydj_{translation_key}"
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
    def options(self) -> list[str]:
        if self.status_key == "sound_output":
            return _options_from_status(
                self.runtime.device_status,
                "available_outputs",
                self._fallback_options,
            )
        current = self.current_option
        options = list(self._fallback_options)
        if current and current not in options:
            options.append(current)
        return options

    @property
    def current_option(self) -> str | None:
        value = self.runtime.device_status.get(self.status_key)
        return str(value) if value not in (None, "") else None

    async def async_select_option(self, option: str) -> None:
        await self.runtime.async_device_command(self.hass, self.command, value=option)
        self.runtime.device_status[self.status_key] = option
        self.runtime.update()

    @callback
    def _handle_runtime_update(self) -> None:
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._handle_runtime_update in self.runtime.listeners:
            self.runtime.listeners.remove(self._handle_runtime_update)


def _options_from_status(
    status: dict[str, Any],
    key: str,
    fallback: list[str] | None = None,
) -> list[str]:
    values = status.get(key) or fallback or []
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    return [str(value) for value in values if str(value or "").strip()]
