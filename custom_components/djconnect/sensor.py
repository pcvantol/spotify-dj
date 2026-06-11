from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CLIENT_TYPE_ESP32, DOMAIN
from .entity_ids import entry_unique_id

MAX_SENSOR_STATE_TEXT_LENGTH = 255

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    entities = [
        DJConnectStatusSensor(runtime),
        DJConnectLastTextSensor(runtime),
        DJConnectFirmwareSensor(runtime),
        DJConnectLastTrackSensor(runtime),
        DJConnectSpotifyStatusSensor(runtime),
        DJConnectPairingStatusSensor(runtime),
        DJConnectSoundOutputSensor(runtime),
        DJConnectPlaybackAvailableSensor(runtime),
        DJConnectQueueSensor(runtime),
        DJConnectPlaylistsSensor(runtime),
        DJConnectOutputsSensor(runtime),
    ]
    if _runtime_client_type(runtime) == CLIENT_TYPE_ESP32:
        entities.extend(
            [
                DJConnectBatterySensor(runtime),
                DJConnectWifiSensor(runtime),
                DJConnectScreenStateSensor(runtime),
                DJConnectLedStateSensor(runtime),
            ]
        )
    async_add_entities(entities)

class DJConnectBaseSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime) -> None:
        self.runtime = runtime
        self._attr_unique_id = entry_unique_id(
            runtime,
            getattr(self, "_attr_unique_id", "") or getattr(self, "_attr_translation_key", ""),
        )
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
            "last_stt_text": getattr(self.runtime, "last_stt_text", None),
            "last_spotify_search": getattr(self.runtime, "last_spotify_search", None),
            "last_resolved_media": getattr(self.runtime, "last_resolved_media", None),
            "last_dj_text": self.runtime.last_dj_text,
            "last_dj_response_debug": getattr(self.runtime, "last_dj_response_debug", None),
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

    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self._last_value = _last_command_value(runtime)
        self._last_runtime_update_state: tuple | None = None

    @callback
    def _handle_runtime_update(self) -> None:
        current = self._runtime_update_state()
        if current == self._last_runtime_update_state:
            return
        self._last_runtime_update_state = current
        self.async_write_ha_state()

    def _runtime_update_state(self) -> tuple:
        return (
            self.native_value,
            _last_command_first_raw_value(self.runtime),
            getattr(self.runtime, "last_text", None),
            getattr(self.runtime, "last_stt_text", None),
            getattr(self.runtime, "last_dj_text", None),
            _stable_repr(getattr(self.runtime, "last_intent", None)),
            _stable_repr(getattr(self.runtime, "last_spotify_search", None)),
            _stable_repr(getattr(self.runtime, "last_resolved_media", None)),
        )

    @property
    def native_value(self):
        value = _last_command_value(self.runtime)
        if value not in (None, ""):
            self._last_value = value
        return self._last_value

    @property
    def available(self) -> bool:
        return True

    @property
    def extra_state_attributes(self):
        full_value = _last_command_first_raw_value(self.runtime) or self._last_value
        return {
            "full_value": full_value,
            "state_truncated": _is_long_text_state(full_value),
            "state_prompt_leak_ignored": _looks_like_assist_prompt_leak(full_value or ""),
            "last_stt_text": getattr(self.runtime, "last_stt_text", None) or self._last_value,
            "last_text": getattr(self.runtime, "last_text", None),
            "last_dj_text": getattr(self.runtime, "last_dj_text", None) or self._last_value,
            "last_intent": getattr(self.runtime, "last_intent", None),
            "last_spotify_search": getattr(self.runtime, "last_spotify_search", None),
            "last_resolved_media": getattr(self.runtime, "last_resolved_media", None),
        }

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

    def __init__(self, runtime) -> None:
        super().__init__(runtime)
        self._last_value = _last_track_value(runtime)
        self._last_runtime_update_state: tuple | None = None

    @callback
    def _handle_runtime_update(self) -> None:
        current = self._runtime_update_state()
        if current == self._last_runtime_update_state:
            return
        self._last_runtime_update_state = current
        self.async_write_ha_state()

    def _runtime_update_state(self) -> tuple:
        return (
            self.native_value,
            _stable_repr(getattr(self.runtime, "last_playback", None)),
            _stable_repr(getattr(self.runtime, "last_resolved_media", None)),
            _stable_repr(_last_track_status_values(self.runtime)),
        )

    @property
    def native_value(self):
        value = _last_track_value(self.runtime)
        if value not in (None, ""):
            self._last_value = value
        return self._last_value

    @property
    def available(self) -> bool:
        return True

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


def _runtime_client_type(runtime) -> str:
    getter = getattr(runtime, "client_type", None)
    if callable(getter):
        return str(getter() or CLIENT_TYPE_ESP32)
    return str(getattr(runtime, "device_status", {}).get("client_type") or CLIENT_TYPE_ESP32)


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


def _last_command_value(runtime):
    return _safe_text_state(_last_command_raw_value(runtime))


def _last_command_raw_value(runtime):
    for key in ("last_dj_text", "last_text", "last_stt_text"):
        value = getattr(runtime, key, None)
        if value not in (None, ""):
            safe = _safe_text_state(value)
            if safe not in (None, ""):
                return value
    status = getattr(runtime, "device_status", {}) or {}
    for key in ("last_dj_text", "last_command", "last_text", "last_stt_text"):
        value = status.get(key)
        if value not in (None, ""):
            safe = _safe_text_state(value)
            if safe not in (None, ""):
                return value
    return None


def _last_command_first_raw_value(runtime):
    for key in ("last_dj_text", "last_text", "last_stt_text"):
        value = getattr(runtime, key, None)
        if value not in (None, ""):
            return str(value)
    status = getattr(runtime, "device_status", {}) or {}
    for key in ("last_dj_text", "last_command", "last_text", "last_stt_text"):
        value = status.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _last_track_value(runtime):
    playback = getattr(runtime, "last_playback", None) or {}
    for key in ("track_name", "title", "name", "track"):
        value = playback.get(key)
        if value not in (None, ""):
            return _safe_text_state(value)
    resolved = getattr(runtime, "last_resolved_media", None) or {}
    for key in ("track_name", "title", "name", "artist", "artist_name"):
        value = resolved.get(key)
        if value not in (None, ""):
            return _safe_text_state(value)
    status = getattr(runtime, "device_status", {}) or {}
    for key in ("last_track", "track_name", "track", "title"):
        value = status.get(key)
        if value not in (None, ""):
            return _safe_text_state(value)
    return None


def _last_track_status_values(runtime):
    status = getattr(runtime, "device_status", {}) or {}
    return {
        key: status.get(key)
        for key in ("last_track", "track_name", "track", "title")
        if status.get(key) not in (None, "")
    }


def _stable_repr(value) -> str:
    return repr(value)


def _safe_text_state(value):
    """Return text that is safe for HA state storage."""
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text or _looks_like_assist_prompt_leak(text):
        return None
    if len(text) <= MAX_SENSOR_STATE_TEXT_LENGTH:
        return text
    return text[: MAX_SENSOR_STATE_TEXT_LENGTH - 1].rstrip() + "…"


def _is_long_text_state(value) -> bool:
    if value in (None, ""):
        return False
    return len(str(value).strip()) > MAX_SENSOR_STATE_TEXT_LENGTH


def _looks_like_assist_prompt_leak(value: str) -> bool:
    normalized = " ".join(str(value or "").lower().split())
    return (
        "gebruik deze dj response prompt" in normalized
        or "antwoord alleen met de tekst die uitgesproken moet worden" in normalized
    ) and (
        "niet vinden" in normalized
        or "geen apparaat vinden" in normalized
        or "can't find" in normalized
        or "cannot find" in normalized
    )
