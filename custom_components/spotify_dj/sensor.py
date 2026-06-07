from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT
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
            SpotifyDJStatusSensor(runtime),
            SpotifyDJLastTextSensor(runtime),
            SpotifyDJBatterySensor(runtime),
            SpotifyDJWifiSensor(runtime),
            SpotifyDJFirmwareSensor(runtime),
            SpotifyDJLastTrackSensor(runtime),
            SpotifyDJSpotifyStatusSensor(runtime),
            SpotifyDJPairingStatusSensor(runtime),
            SpotifyDJSoundOutputSensor(runtime),
        ]
    )

class SpotifyDJBaseSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, runtime) -> None:
        self.runtime = runtime
        runtime.listeners.append(self._handle_runtime_update)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.runtime.entry.entry_id)},
            name="SpotifyDJ",
            manufacturer="SpotifyDJ",
            model="SpotifyDJ device",
        )

    @callback
    def _handle_runtime_update(self) -> None:
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._handle_runtime_update in self.runtime.listeners:
            self.runtime.listeners.remove(self._handle_runtime_update)

class SpotifyDJStatusSensor(SpotifyDJBaseSensor):
    _attr_translation_key = "status"
    _attr_unique_id = "spotifydj_status"

    @property
    def native_value(self):
        if self.runtime.ota_in_progress:
            return "updating"
        return "error" if self.runtime.last_error else "ready"

    @property
    def extra_state_attributes(self):
        return {
            "last_error": self.runtime.last_error,
            "last_dj_text": self.runtime.last_dj_text,
            "last_dj_spoken": getattr(self.runtime, "last_dj_spoken", None),
            "last_dj_displayed": getattr(self.runtime, "last_dj_displayed", None),
            "last_dj_response_at": getattr(self.runtime, "last_dj_response_at", None),
            "last_playback": self.runtime.last_playback,
            "device_status": self.runtime.device_status,
            "ota_in_progress": self.runtime.ota_in_progress,
            "ota_last_error": self.runtime.ota_last_error,
        }

class SpotifyDJLastTextSensor(SpotifyDJBaseSensor):
    _attr_translation_key = "last_command"
    _attr_unique_id = "spotifydj_last_command"

    @property
    def native_value(self):
        return self.runtime.last_text

    @property
    def extra_state_attributes(self):
        return {"last_intent": self.runtime.last_intent}

class SpotifyDJBatterySensor(SpotifyDJBaseSensor):
    _attr_translation_key = "battery"
    _attr_unique_id = "spotifydj_battery"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return self.runtime.device_status.get("battery_percent")

class SpotifyDJWifiSensor(SpotifyDJBaseSensor):
    _attr_translation_key = "wifi_rssi"
    _attr_unique_id = "spotifydj_wifi_rssi"
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return self.runtime.device_status.get("wifi_rssi")

class SpotifyDJFirmwareSensor(SpotifyDJBaseSensor):
    _attr_translation_key = "firmware_version"
    _attr_unique_id = "spotifydj_firmware_version"

    @property
    def native_value(self):
        return self.runtime.device_status.get("firmware")

class SpotifyDJLastTrackSensor(SpotifyDJBaseSensor):
    _attr_translation_key = "last_track"
    _attr_unique_id = "spotifydj_last_track"

    @property
    def native_value(self):
        playback = self.runtime.last_playback or {}
        return playback.get("title") or self.runtime.device_status.get("last_track")

    @property
    def extra_state_attributes(self):
        return self.runtime.last_playback or {}


class SpotifyDJSpotifyStatusSensor(SpotifyDJBaseSensor):
    _attr_translation_key = "spotify_status"
    _attr_unique_id = "spotifydj_spotify_status"

    @property
    def native_value(self):
        return self.runtime.device_status.get("spotify_status")


class SpotifyDJPairingStatusSensor(SpotifyDJBaseSensor):
    _attr_translation_key = "ha_pairing_status"
    _attr_unique_id = "spotifydj_ha_pairing_status"

    @property
    def native_value(self):
        if self.runtime.device_token:
            return self.runtime.device_status.get("ha_pairing_status") or "paired"
        return "not_paired"


class SpotifyDJSoundOutputSensor(SpotifyDJBaseSensor):
    _attr_translation_key = "sound_output"
    _attr_unique_id = "spotifydj_sound_output"

    @property
    def native_value(self):
        return self.runtime.device_status.get("sound_output") or self.runtime.device_status.get(
            "output"
        )
