from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import MediaPlayerEntity, MediaPlayerEntityFeature
try:
    from homeassistant.components.media_player.const import MediaPlayerState
except ImportError:  # Home Assistant versions before the enum export.
    class MediaPlayerState:
        PLAYING = "playing"
        PAUSED = "paused"
        IDLE = "idle"
        UNAVAILABLE = "unavailable"
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .spotify_backend import SpotifyBackendError, handle_spotify_command

_LOGGER = logging.getLogger(__name__)

SUPPORTED_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | getattr(MediaPlayerEntityFeature, "PLAY_PAUSE", 0)
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | getattr(MediaPlayerEntityFeature, "SHUFFLE_SET", 0)
    | getattr(MediaPlayerEntityFeature, "REPEAT_SET", 0)
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DJConnectPlaybackProxyMediaPlayer(runtime, hass)])


class DJConnectPlaybackProxyMediaPlayer(MediaPlayerEntity):
    """Backend playback session controlled through DJConnect's HA integration."""

    _attr_has_entity_name = True
    _attr_translation_key = "playback_proxy"
    _attr_unique_id = "djconnect_playback_proxy"
    _attr_supported_features = SUPPORTED_FEATURES

    def __init__(self, runtime: Any, hass: HomeAssistant) -> None:
        self.runtime = runtime
        self.hass = hass
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
    def available(self) -> bool:
        return (
            bool(self.runtime.device_token)
            and not _pairing_is_stale(self.runtime)
            and not _backend_auth_is_stale(self.runtime)
        )

    @property
    def state(self) -> MediaPlayerState:
        if not self.available:
            return MediaPlayerState.UNAVAILABLE
        playback = self.runtime.last_playback or {}
        if not playback.get("has_playback"):
            return MediaPlayerState.IDLE
        return MediaPlayerState.PLAYING if playback.get("is_playing") else MediaPlayerState.PAUSED

    @property
    def media_title(self) -> str | None:
        return _playback_value(self.runtime, "track_name", "title")

    @property
    def media_artist(self) -> str | None:
        return _playback_value(self.runtime, "artist_name", "artist")

    @property
    def media_album_name(self) -> str | None:
        return _playback_value(self.runtime, "album_name")

    @property
    def entity_picture(self) -> str | None:
        return _playback_value(self.runtime, "album_image_url", "entity_picture")

    @property
    def media_image_url(self) -> str | None:
        return _playback_value(
            self.runtime,
            "album_image_url",
            "media_image_url",
            "image_url",
            "entity_picture",
        )

    @property
    def volume_level(self) -> float | None:
        value = _playback_value(self.runtime, "volume_percent")
        try:
            volume = float(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, min(1.0, volume / 60.0))

    @property
    def source(self) -> str | None:
        device = (self.runtime.last_playback or {}).get("device") or {}
        return device.get("name") or self.runtime.device_status.get("sound_output")

    @property
    def source_list(self) -> list[str]:
        return [output["name"] for output in _outputs(self.runtime) if output.get("name")]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        playback = self.runtime.last_playback or {}
        return {
            "backend": "spotify",
            "represents": "backend_playback_session",
            "esp_speaker": "local_cues_and_dj_response_only",
            "device_id": self.runtime.device_status.get("device_id"),
            "firmware": self.runtime.device_status.get("firmware"),
            "ha_pairing_status": self.runtime.device_status.get("ha_pairing_status"),
            "shuffle": playback.get("shuffle"),
            "repeat_state": playback.get("repeat_state"),
            "backend_device": playback.get("device"),
        }

    async def async_update(self) -> None:
        try:
            await self._backend_command("status")
        except SpotifyBackendError:
            self.runtime.device_status["backend_available"] = False
        except Exception as exc:  # noqa: BLE001
            self.runtime.device_status["backend_available"] = False
            self.runtime.update(last_error=str(exc))

    async def async_media_play(self) -> None:
        await self._backend_command("play")

    async def async_media_pause(self) -> None:
        await self._backend_command("pause")

    async def async_media_play_pause(self) -> None:
        playback = self.runtime.last_playback or {}
        command = "pause" if playback.get("is_playing") else "play"
        await self._backend_command(command)

    async def async_media_next_track(self) -> None:
        await self._backend_command("next")
        await self._refresh_device_display()

    async def async_media_previous_track(self) -> None:
        await self._backend_command("previous")
        await self._refresh_device_display()

    async def async_set_volume_level(self, volume: float) -> None:
        await self._backend_command("set_volume", int(max(0.0, min(1.0, volume)) * 60))

    async def async_set_shuffle(self, shuffle: bool) -> None:
        await self._backend_command("set_shuffle", bool(shuffle))
        await self._refresh_device_display()

    async def async_set_repeat(self, repeat: str) -> None:
        await self._backend_command("set_repeat", repeat)
        await self._refresh_device_display()

    async def async_select_source(self, source: str) -> None:
        output = _output_by_name(self.runtime, source)
        await self._backend_command("set_output", (output or {}).get("id") or source, play=False)

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        command = "start_playlist" if str(media_type).lower() == "playlist" else "play"
        await self._backend_command(command, media_id)

    async def _backend_command(
        self,
        command: str,
        value: Any = None,
        *,
        play: bool | None = None,
    ) -> dict[str, Any]:
        try:
            result = await handle_spotify_command(
                self.hass,
                self.runtime,
                command,
                value,
                play=play,
            )
        except SpotifyBackendError as exc:
            self.runtime.update(last_error=str(exc))
            _LOGGER.warning("DJConnect playback backend unavailable: %s", exc)
            raise
        except Exception as exc:  # noqa: BLE001
            self.runtime.update(last_error=str(exc))
            _LOGGER.warning("DJConnect playback proxy command failed: %s", exc)
            raise
        self.runtime.update(last_error=None)
        return result

    async def _refresh_device_display(self) -> None:
        try:
            await self.runtime.async_device_command(self.hass, "status")
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("DJConnect device display refresh failed: %s", exc)

    @callback
    def _handle_runtime_update(self) -> None:
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._handle_runtime_update in self.runtime.listeners:
            self.runtime.listeners.remove(self._handle_runtime_update)


def _playback_value(runtime: Any, *keys: str) -> Any:
    playback = runtime.last_playback or {}
    for key in keys:
        value = playback.get(key)
        if value not in (None, ""):
            return value
    return None


def _outputs(runtime: Any) -> list[dict[str, Any]]:
    outputs = runtime.device_status.get("available_outputs") or []
    if not isinstance(outputs, list):
        return []
    normalized: list[dict[str, Any]] = []
    for output in outputs:
        if isinstance(output, dict):
            normalized.append(output)
        elif output:
            normalized.append({"id": str(output), "name": str(output)})
    return normalized


def _output_by_name(runtime: Any, name: str) -> dict[str, Any] | None:
    for output in _outputs(runtime):
        if output.get("name") == name or output.get("id") == name:
            return output
    return None


def _pairing_is_stale(runtime: Any) -> bool:
    status = str(runtime.device_status.get("ha_pairing_status") or "").lower()
    error = str(getattr(runtime, "last_error", None) or "").lower()
    return status in {"stale", "invalid", "unauthorized"} or "pairing is stale" in error


def _backend_auth_is_stale(runtime: Any) -> bool:
    error = str(getattr(runtime, "last_error", None) or "").lower()
    return "spotify authorization" in error and (
        "expired" in error or "revoked" in error or "reauthorize" in error
    )
