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
            DJConnectStatusSensor(runtime),
            DJConnectLastTextSensor(runtime),
            DJConnectBatterySensor(runtime),
            DJConnectWifiSensor(runtime),
            DJConnectFirmwareSensor(runtime),
            DJConnectLastTrackSensor(runtime),
            DJConnectSpotifyStatusSensor(runtime),
            DJConnectPairingStatusSensor(runtime),
            DJConnectSoundOutputSensor(runtime),
            DJConnectPlaybackAvailableSensor(runtime),
            DJConnectQueueSensor(runtime),
            DJConnectPlaylistsSensor(runtime),
            DJConnectOutputsSensor(runtime),
            DJConnectScreenStateSensor(runtime),
            DJConnectLedStateSensor(runtime),
        ]
    )

class DJConnectBaseSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, runtime) -> None:
        self.runtime = runtime
        runtime.listeners.append(self._handle_runtime_update)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.runtime.entry.entry_id)},
            name="DJConnect",
            manufacturer="DJConnect",
            model="DJConnect device",
        )

    @callback
    def _handle_runtime_update(self) -> None:
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._handle_runtime_update in self.runtime.listeners:
            self.runtime.listeners.remove(self._handle_runtime_update)

class DJConnectStatusSensor(DJConnectBaseSensor):
    _attr_translation_key = "status"
    _attr_unique_id = "djconnect_status"

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

class DJConnectLastTextSensor(DJConnectBaseSensor):
    _attr_translation_key = "last_command"
    _attr_unique_id = "djconnect_last_command"

    @property
    def native_value(self):
        return self.runtime.last_text

    @property
    def extra_state_attributes(self):
        return {"last_intent": self.runtime.last_intent}

class DJConnectBatterySensor(DJConnectBaseSensor):
    _attr_translation_key = "battery"
    _attr_unique_id = "djconnect_battery"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return self.runtime.device_status.get("battery_percent")

class DJConnectWifiSensor(DJConnectBaseSensor):
    _attr_translation_key = "wifi_rssi"
    _attr_unique_id = "djconnect_wifi_rssi"
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return self.runtime.device_status.get("wifi_rssi")

class DJConnectFirmwareSensor(DJConnectBaseSensor):
    _attr_translation_key = "firmware_version"
    _attr_unique_id = "djconnect_firmware_version"

    @property
    def native_value(self):
        return self.runtime.device_status.get("firmware")

class DJConnectLastTrackSensor(DJConnectBaseSensor):
    _attr_translation_key = "last_track"
    _attr_unique_id = "djconnect_last_track"

    @property
    def native_value(self):
        playback = self.runtime.last_playback or {}
        for key in ("track_name", "title", "name", "track"):
            value = playback.get(key)
            if value not in (None, ""):
                return value
        for key in ("last_track", "track_name", "track"):
            value = self.runtime.device_status.get(key)
            if value not in (None, ""):
                return value
        return None

    @property
    def extra_state_attributes(self):
        return self.runtime.last_playback or {}


class DJConnectSpotifyStatusSensor(DJConnectBaseSensor):
    _attr_translation_key = "spotify_status"
    _attr_unique_id = "djconnect_spotify_status"

    @property
    def native_value(self):
        return self.runtime.device_status.get("spotify_status")


class DJConnectPairingStatusSensor(DJConnectBaseSensor):
    _attr_translation_key = "ha_pairing_status"
    _attr_unique_id = "djconnect_ha_pairing_status"

    @property
    def native_value(self):
        status = self.runtime.device_status.get("ha_pairing_status")
        if status:
            return status
        if self.runtime.device_token:
            return "pending"
        return "not_paired"


class DJConnectSoundOutputSensor(DJConnectBaseSensor):
    _attr_translation_key = "sound_output"
    _attr_unique_id = "djconnect_sound_output"

    @property
    def native_value(self):
        return self.runtime.device_status.get("sound_output") or self.runtime.device_status.get(
            "output"
        )


class DJConnectPlaybackAvailableSensor(DJConnectBaseSensor):
    _attr_translation_key = "playback_available"
    _attr_unique_id = "djconnect_playback_available"

    @property
    def native_value(self):
        playback = self.runtime.last_playback or {}
        return bool(playback.get("has_playback")) or self.runtime.device_status.get(
            "backend_available"
        )


class DJConnectQueueSensor(DJConnectBaseSensor):
    _attr_translation_key = "queue"
    _attr_unique_id = "djconnect_queue"

    @property
    def native_value(self):
        return len(_collection_items(self.runtime.device_status.get("queue")))

    @property
    def extra_state_attributes(self):
        queue = self.runtime.device_status.get("queue")
        attrs = {
            "items": _collection_items(queue),
            "context": _queue_context(self.runtime, queue),
        }
        current = _queue_currently_playing(queue)
        if current:
            attrs["currently_playing"] = current
        return attrs


class DJConnectPlaylistsSensor(DJConnectBaseSensor):
    _attr_translation_key = "playlists"
    _attr_unique_id = "djconnect_playlists"

    @property
    def native_value(self):
        playlists = self.runtime.device_status.get("playlists") or []
        return len(playlists) if isinstance(playlists, list) else None

    @property
    def extra_state_attributes(self):
        return {"items": self.runtime.device_status.get("playlists") or []}


class DJConnectOutputsSensor(DJConnectBaseSensor):
    _attr_translation_key = "outputs"
    _attr_unique_id = "djconnect_outputs"

    @property
    def native_value(self):
        outputs = self.runtime.device_status.get("available_outputs") or []
        return len(outputs) if isinstance(outputs, list) else None

    @property
    def extra_state_attributes(self):
        return {"items": self.runtime.device_status.get("available_outputs") or []}


class DJConnectScreenStateSensor(DJConnectBaseSensor):
    _attr_translation_key = "screen_state"
    _attr_unique_id = "djconnect_screen_state"

    @property
    def native_value(self):
        return self.runtime.device_status.get("screen_state")


class DJConnectLedStateSensor(DJConnectBaseSensor):
    _attr_translation_key = "led_state"
    _attr_unique_id = "djconnect_led_state"

    @property
    def native_value(self):
        return self.runtime.device_status.get("led_state")


def _collection_items(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("items", "queue", "playlists", "outputs", "devices"):
            items = value.get(key)
            if isinstance(items, list):
                return items
    return []


def _queue_context(runtime, queue):
    if isinstance(queue, dict):
        for key in ("context", "queue_context", "context_uri"):
            value = queue.get(key)
            if value not in (None, "", {}, []):
                return value
    playback = runtime.last_playback or {}
    for key in ("context", "queue_context", "context_uri"):
        value = playback.get(key)
        if value not in (None, "", {}, []):
            return value
    for key in ("queue_context", "context_uri"):
        value = runtime.device_status.get(key)
        if value not in (None, "", {}, []):
            return value
    return None


def _queue_currently_playing(queue):
    if isinstance(queue, dict):
        value = queue.get("currently_playing") or queue.get("current")
        if isinstance(value, dict):
            return value
    return None
