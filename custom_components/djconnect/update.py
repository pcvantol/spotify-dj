from __future__ import annotations

import asyncio
from datetime import timedelta
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
    CONF_FIRMWARE_CHANNEL,
    CONF_FIRMWARE_DEVICE,
    CONF_FIRMWARE_REPO,
    CONF_MIN_BATTERY_FOR_OTA,
    CLIENT_TYPE_ESP32,
    DEFAULT_FIRMWARE_CHANNEL,
    DEFAULT_FIRMWARE_DEVICE,
    DEFAULT_FIRMWARE_REPO,
    DEFAULT_MIN_BATTERY_FOR_OTA,
    DOMAIN,
)
from .entity_ids import entry_unique_id
from .github import fetch_latest_firmware_release, is_newer

try:
    from homeassistant.helpers.event import async_track_time_interval
except Exception:  # pragma: no cover - Home Assistant/stub compatibility
    async_track_time_interval = None

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
    client_type = _runtime_client_type(runtime)
    if client_type != CLIENT_TYPE_ESP32:
        _LOGGER.debug(
            "Skipping DJConnect firmware update entity for client_type=%s",
            client_type,
        )
        return
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
    _attr_should_poll = False

    def __init__(self, runtime, hass: HomeAssistant) -> None:
        self.runtime = runtime
        self.hass = hass
        self._attr_unique_id = entry_unique_id(runtime, "firmware_update")
        self._latest = None
        self._installed = None
        self._update_error = None
        self._next_update_check = 0.0
        self._last_runtime_update_state: tuple[Any, ...] | None = None
        runtime.listeners.append(self._handle_runtime_update)

    @property
    def available(self) -> bool:
        return _runtime_client_type(self.runtime) == CLIENT_TYPE_ESP32

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
                "repo": DEFAULT_FIRMWARE_REPO,
                "channel": _firmware_channel_from_config(self.runtime),
                "target_device": _firmware_device_from_status(self.runtime),
                "device_status": self.runtime.device_status,
                "firmware_update_error": self._update_error,
            }
        return {
            "repo": DEFAULT_FIRMWARE_REPO,
            "channel": _firmware_channel_from_config(self.runtime),
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
        if not self.available:
            self._latest = None
            self._update_error = "Firmware OTA is only available for ESP32 clients"
            return
        await self.async_update()
        if async_track_time_interval is not None:
            remove_listener = async_track_time_interval(
                self.hass,
                self._async_scheduled_update,
                timedelta(seconds=FIRMWARE_CHECK_INTERVAL_SECONDS),
            )
            if hasattr(self, "async_on_remove"):
                self.async_on_remove(remove_listener)

    async def _async_scheduled_update(self, now: Any) -> None:
        if not self.available:
            self._latest = None
            self._update_error = "Firmware OTA is only available for ESP32 clients"
            self.async_write_ha_state()
            return
        await self.async_update()
        self.async_write_ha_state()

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
            _runtime_client_type(self.runtime),
            status.get("firmware"),
            status.get("ota_state"),
            status.get("update_state"),
            self.runtime.ota_in_progress,
            self.runtime.ota_last_error,
        )

    async def async_update(self, *, force: bool = False) -> None:
        await self._async_refresh_latest_release(bypass_throttle=False)

    async def _async_refresh_latest_release(self, *, bypass_throttle: bool = False) -> None:
        """Refresh GitHub firmware metadata while protecting against HA refresh storms."""
        if not self.available:
            self._latest = None
            self._update_error = "Firmware OTA is only available for ESP32 clients"
            return
        now = time.monotonic()
        if not bypass_throttle and self._next_update_check > now:
            return
        try:
            self._latest = await fetch_latest_firmware_release(
                self.hass,
                _firmware_release_config(self.runtime),
            )
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
        if not self.available:
            return None
        return self.release_summary

    async def async_install(
        self,
        version: str | None = None,
        backup: bool = False,
        **kwargs: Any,
    ) -> None:
        if not self.available:
            raise RuntimeError("Firmware OTA is only available for ESP32 clients")
        await self._async_refresh_latest_release(bypass_throttle=True)
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


def _firmware_release_config(runtime: Any) -> dict[str, Any]:
    """Build firmware release config from runtime status, not user flow fields."""
    return {
        CONF_FIRMWARE_REPO: DEFAULT_FIRMWARE_REPO,
        CONF_FIRMWARE_CHANNEL: _firmware_channel_from_config(runtime),
        CONF_FIRMWARE_DEVICE: _firmware_device_from_status(runtime),
    }


def _runtime_client_type(runtime: Any) -> str:
    getter = getattr(runtime, "client_type", None)
    if callable(getter):
        return str(getter() or CLIENT_TYPE_ESP32)
    status = getattr(runtime, "device_status", {}) or {}
    config = getattr(runtime, "config", {}) or {}
    return str(status.get("client_type") or config.get("client_type") or CLIENT_TYPE_ESP32)


def _firmware_channel_from_config(runtime: Any) -> str:
    value = str(
        getattr(runtime, "config", {}).get(
            CONF_FIRMWARE_CHANNEL,
            DEFAULT_FIRMWARE_CHANNEL,
        )
        or DEFAULT_FIRMWARE_CHANNEL
    ).strip().lower()
    return "beta" if value == "beta" else DEFAULT_FIRMWARE_CHANNEL


def _firmware_device_from_status(runtime: Any) -> str:
    status = getattr(runtime, "device_status", {}) or {}
    for key in (
        "firmware_device",
        "device",
        "device_model",
        "model",
        "ota_device",
        "board",
    ):
        value = str(status.get(key) or "").strip()
        if value:
            return _normalize_firmware_device(value)
    return DEFAULT_FIRMWARE_DEVICE


def _normalize_firmware_device(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-")
    aliases = {
        "t-embed-cc1101": "lilygo-t-embed-s3",
        "t-embed": "lilygo-t-embed-s3",
        "lilygo": "lilygo-t-embed-s3",
        "t-embed-s3": "lilygo-t-embed-s3",
        "esp32-s3-box3": "esp32-s3-box-3",
        "esp32-s3-box-3": "esp32-s3-box-3",
        "box3": "esp32-s3-box-3",
    }
    return aliases.get(normalized, normalized)
