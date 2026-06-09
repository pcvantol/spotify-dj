from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ALLOW_OTA_ON_BATTERY,
    CONF_MIN_BATTERY_FOR_OTA,
    DEFAULT_MIN_BATTERY_FOR_OTA,
    DOMAIN,
)
from .github import fetch_latest_firmware_release, is_newer

_LOGGER = logging.getLogger(__name__)
FIRMWARE_CHECK_INTERVAL_SECONDS = 60 * 60
FIRMWARE_EMPTY_BACKOFF_SECONDS = 6 * 60 * 60
FIRMWARE_ERROR_BACKOFF_SECONDS = 30 * 60

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DJConnectFirmwareUpdate(runtime, hass)])

class DJConnectFirmwareUpdate(UpdateEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "firmware"
    _attr_unique_id = "djconnect_firmware_update"
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL
        | UpdateEntityFeature.SPECIFIC_VERSION
        | UpdateEntityFeature.RELEASE_NOTES
    )

    def __init__(self, runtime, hass: HomeAssistant) -> None:
        self.runtime = runtime
        self.hass = hass
        self._latest = None
        self._installed = None
        self._update_error = None
        self._next_update_check = 0.0
        self._last_runtime_update_state: tuple[Any, ...] | None = None
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
    def installed_version(self) -> str | None:
        return self.runtime.device_status.get("firmware") or self._installed or "0.0.0"

    @property
    def latest_version(self) -> str | None:
        return self._latest.version if self._latest else self.installed_version

    @property
    def release_summary(self) -> str | None:
        return self._latest.release_notes if self._latest else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self._latest:
            return {
                "repo": self.runtime.config.get("firmware_repo"),
                "device_status": self.runtime.device_status,
                "firmware_update_error": self._update_error,
            }
        return {
            "repo": self.runtime.config.get("firmware_repo"),
            "firmware_asset": self._latest.firmware_asset,
            "manifest_url": self._latest.manifest_url,
            "sha256": self._latest.sha256,
            "target_device": self._latest.device,
            "device": self._latest.device,
            "size": self._latest.size,
            "min_ha_integration": self._latest.min_ha_integration,
            "device_status": self.runtime.device_status,
            "ota_in_progress": self.runtime.ota_in_progress,
            "ota_last_error": self.runtime.ota_last_error,
            "firmware_update_error": self._update_error,
        }

    async def async_added_to_hass(self) -> None:
        await self.async_update()

    async def async_will_remove_from_hass(self) -> None:
        if self._handle_runtime_update in self.runtime.listeners:
            self.runtime.listeners.remove(self._handle_runtime_update)

    def _handle_runtime_update(self) -> None:
        current = self._runtime_update_state()
        if current == self._last_runtime_update_state:
            return
        self._last_runtime_update_state = current
        self.async_write_ha_state()

    def _runtime_update_state(self) -> tuple[Any, ...]:
        status = self.runtime.device_status
        return (
            status.get("firmware"),
            status.get("ota_state"),
            status.get("update_state"),
            self.runtime.ota_in_progress,
            self.runtime.ota_last_error,
        )

    async def async_update(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and self._next_update_check > now:
            return
        try:
            self._latest = await fetch_latest_firmware_release(self.hass, self.runtime.config)
            self._update_error = None if self._latest else "No firmware release available"
            self._next_update_check = now + (
                FIRMWARE_CHECK_INTERVAL_SECONDS
                if self._latest
                else FIRMWARE_EMPTY_BACKOFF_SECONDS
            )
        except Exception as exc:  # noqa: BLE001
            self._latest = None
            self._update_error = str(exc)
            self._next_update_check = now + FIRMWARE_ERROR_BACKOFF_SECONDS
            _LOGGER.warning("DJConnect firmware update check failed: %s", exc)

    async def async_release_notes(self) -> str | None:
        return self.release_summary

    async def async_install(
        self,
        version: str | None = None,
        backup: bool = False,
        **kwargs: Any,
    ) -> None:
        await self.async_update(force=True)
        if not self._latest:
            raise RuntimeError("No DJConnect firmware release found")
        if version and version != self._latest.version:
            _LOGGER.info(
                "Requested version %s, latest available is %s; installing latest",
                version,
                self._latest.version,
            )
        if not is_newer(self._latest.version, self.installed_version) and not version:
            _LOGGER.info("DJConnect firmware is already current")
            return

        status = self.runtime.device_status
        battery = status.get("battery_percent")
        charging = bool(status.get("charging") or status.get("usb_powered"))
        allow_battery = bool(self.runtime.config.get(CONF_ALLOW_OTA_ON_BATTERY, False))
        min_battery = int(
            self.runtime.config.get(
                CONF_MIN_BATTERY_FOR_OTA,
                DEFAULT_MIN_BATTERY_FOR_OTA,
            )
        )
        if (
            not charging
            and not allow_battery
            and battery is not None
            and int(battery) < min_battery
        ):
            raise RuntimeError(f"Battery too low for OTA: {battery}% < {min_battery}%")

        await self.runtime.start_ota(self.hass, self._latest)
        await self._wait_for_reconnect()
        await self.async_update_ha_state(force_refresh=True)

    async def _wait_for_reconnect(self) -> None:
        """Wait briefly for ESP reboot/reconnect after OTA and refresh device info."""
        for attempt in range(8):
            await asyncio.sleep(5 if attempt else 2)
            try:
                await self.runtime.async_refresh_device_info(self.hass)
                self.runtime.ota_in_progress = False
                self.runtime.ota_last_error = None
                self._installed = self.runtime.device_status.get("firmware")
                self.runtime.update()
                return
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug(
                    "DJConnect waiting for device after OTA attempt %s: %s",
                    attempt + 1,
                    exc,
                )
        self.runtime.ota_in_progress = False
        self.runtime.ota_last_error = "Device did not reconnect after OTA in time"
        self.runtime.update()
