from __future__ import annotations

import time
import logging
from typing import Any

from aiohttp import ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_LIKED_PROXY,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_REFRESH_TOKEN,
    DEFAULT_SPOTIFY_MARKET,
)
from .spotify_oauth import refresh_access_token

SPOTIFY_API_BASE = "https://api.spotify.com/v1"
CACHE_TTL_SECONDS = 30
_LOGGER = logging.getLogger(__name__)


class SpotifyBackendError(RuntimeError):
    """Raised when the configured Spotify backend cannot serve a command."""


async def handle_spotify_command(
    hass: HomeAssistant,
    runtime: Any,
    command: str,
    value: Any = None,
    *,
    play: bool | None = None,
) -> dict[str, Any]:
    """Handle a generic SpotifyDJ playback command using HA-stored credentials."""
    backend = SpotifyBackend(hass, runtime)
    normalized = str(command or "").strip().lower()
    _LOGGER.debug("SpotifyDJ Spotify backend handling command: %s", normalized)
    if normalized == "status":
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "devices":
        return {"success": True, "devices": await backend.devices()}
    if normalized == "queue":
        return {"success": True, "queue": await backend.queue()}
    if normalized == "playlists":
        return {"success": True, "playlists": await backend.playlists()}
    if normalized == "pause":
        await backend.pause()
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "play":
        await backend.play(value)
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "next":
        await backend.next()
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "previous":
        await backend.previous()
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "start_liked_proxy":
        await backend.start_liked_proxy()
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "start_playlist":
        await backend.start_playlist(str(value or ""))
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "set_play_mode":
        await backend.set_play_mode(str(value or ""))
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "set_output":
        await backend.set_output(str(value or ""), play=bool(play))
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "set_volume":
        await backend.set_volume(value)
        return {"success": True, "playback": await backend.playback_state()}
    raise ValueError(f"Unsupported SpotifyDJ command: {command}")


class SpotifyBackend:
    """Small Spotify Web API backend using credentials stored in Home Assistant."""

    def __init__(self, hass: HomeAssistant, runtime: Any) -> None:
        self.hass = hass
        self.runtime = runtime
        self.session = async_get_clientsession(hass)

    @property
    def conf(self) -> dict[str, Any]:
        return self.runtime.config

    async def _access_token(self) -> str:
        client_id = str(self.conf.get(CONF_SPOTIFY_CLIENT_ID) or "").strip()
        refresh_token = str(
            getattr(self.runtime, "latest_spotify_refresh_token", None)
            or self.conf.get(CONF_SPOTIFY_REFRESH_TOKEN)
            or ""
        ).strip()
        if not client_id or not refresh_token:
            raise SpotifyBackendError("Spotify OAuth is not configured in Home Assistant")
        token = await refresh_access_token(
            self.hass,
            client_id=client_id,
            refresh_token=refresh_token,
        )
        rotated = str(token.get("refresh_token") or "").strip()
        if rotated:
            updater = getattr(self.runtime, "update_spotify_refresh_token", None)
            if callable(updater) and updater(rotated):
                entry = getattr(self.runtime, "entry", None)
                if entry is not None:
                    new_data = dict(entry.data)
                    new_data[CONF_SPOTIFY_REFRESH_TOKEN] = rotated
                    self.hass.config_entries.async_update_entry(entry, data=new_data)
                _LOGGER.debug("SpotifyDJ Spotify refresh_token=rotated/present")
        access_token = str(token.get("access_token") or "").strip()
        if not access_token:
            raise SpotifyBackendError("Spotify OAuth refresh did not return an access token")
        return access_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        expected_empty: bool = False,
    ) -> Any:
        token = await self._access_token()
        async with self.session.request(
            method,
            SPOTIFY_API_BASE + path,
            json=json,
            headers={"Authorization": f"Bearer {token}"},
            timeout=ClientTimeout(total=12),
        ) as resp:
            if resp.status == 204 or expected_empty:
                if resp.status < 200 or resp.status >= 300:
                    text = await resp.text()
                    raise SpotifyBackendError(
                        f"Spotify API failed HTTP {resp.status}: {_spotify_error_message(text)}"
                    )
                return {}
            try:
                body = await resp.json(content_type=None)
            except Exception:  # noqa: BLE001
                body = {"message": await resp.text()}
            if resp.status < 200 or resp.status >= 300:
                raise SpotifyBackendError(
                    f"Spotify API failed HTTP {resp.status}: {_spotify_error_message(body)}"
                )
            return body or {}

    async def _cached(self, key: str, loader) -> Any:
        cache = getattr(self.runtime, "backend_cache", None)
        if cache is None:
            self.runtime.backend_cache = {}
            cache = self.runtime.backend_cache
        now = time.monotonic()
        cached = cache.get(key)
        if cached and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
        value = await loader()
        cache[key] = (now, value)
        return value

    async def playback_state(self) -> dict[str, Any]:
        data = await self._request("GET", "/me/player")
        playback = _normalize_playback(data)
        self.runtime.device_status.update(
            {
                "spotify_status": "playing" if playback.get("is_playing") else "idle",
                "volume": playback.get("volume_percent"),
                "last_track": playback.get("track_name"),
                "sound_output": (playback.get("device") or {}).get("name"),
            }
        )
        self.runtime.update(last_playback=playback, last_error=None)
        return playback

    async def devices(self) -> list[dict[str, Any]]:
        async def load():
            data = await self._request("GET", "/me/player/devices")
            return [_normalize_device(device) for device in data.get("devices", [])]

        devices = await self._cached("devices", load)
        self.runtime.device_status["available_outputs"] = devices
        self.runtime.update()
        return devices

    async def queue(self) -> list[dict[str, str]]:
        data = await self._request("GET", "/me/player/queue")
        queue = data.get("queue") or []
        normalized = [_normalize_queue_item(item) for item in queue]
        self.runtime.device_status["queue"] = normalized
        self.runtime.update()
        return normalized

    async def playlists(self) -> list[dict[str, str]]:
        async def load():
            data = await self._request("GET", "/me/playlists?limit=50")
            return [_normalize_playlist(item) for item in data.get("items", [])]

        playlists = await self._cached("playlists", load)
        self.runtime.device_status["playlists"] = playlists
        self.runtime.update()
        return playlists

    async def pause(self) -> None:
        await self._request("PUT", "/me/player/pause", expected_empty=True)

    async def play(self, value: Any = None) -> None:
        body = None
        if value:
            body = {"uris": [str(value)]} if str(value).startswith("spotify:track:") else {"context_uri": str(value)}
        await self._request("PUT", "/me/player/play", json=body, expected_empty=True)

    async def next(self) -> None:
        await self._request("POST", "/me/player/next", expected_empty=True)

    async def previous(self) -> None:
        await self._request("POST", "/me/player/previous", expected_empty=True)

    async def start_liked_proxy(self) -> None:
        playlist = str(self.conf.get(CONF_LIKED_PROXY) or "").strip()
        if not playlist:
            raise SpotifyBackendError("SpotifyDJ Liked Proxy playlist URI is not configured")
        await self.start_playlist(playlist)

    async def start_playlist(self, playlist_uri: str) -> None:
        uri = playlist_uri.strip()
        if not uri:
            raise ValueError("Provide a playlist URI")
        await self._request(
            "PUT",
            "/me/player/play",
            json={"context_uri": uri},
            expected_empty=True,
        )

    async def set_play_mode(self, mode: str) -> None:
        normalized = mode.strip().lower()
        if normalized == "normal":
            await self._request("PUT", "/me/player/shuffle?state=false", expected_empty=True)
            await self._request("PUT", "/me/player/repeat?state=off", expected_empty=True)
            return
        if normalized == "shuffle":
            await self._request("PUT", "/me/player/shuffle?state=true", expected_empty=True)
            return
        repeat = {
            "repeat_once": "track",
            "repeat_infinite": "context",
        }.get(normalized)
        if not repeat:
            raise ValueError("set_play_mode must be normal, shuffle, repeat_once or repeat_infinite")
        await self._request("PUT", f"/me/player/repeat?state={repeat}", expected_empty=True)

    async def set_output(self, device_id: str, *, play: bool = False) -> None:
        if not device_id:
            raise ValueError("Provide an output device id")
        await self._request(
            "PUT",
            "/me/player",
            json={"device_ids": [device_id], "play": play},
            expected_empty=True,
        )

    async def set_volume(self, value: Any) -> None:
        try:
            volume = max(0, min(60, int(float(value))))
        except (TypeError, ValueError) as exc:
            raise ValueError("set_volume value must be 0-60") from exc
        await self._request(
            "PUT",
            f"/me/player/volume?volume_percent={volume}",
            expected_empty=True,
        )


def _normalize_playback(data: dict[str, Any]) -> dict[str, Any]:
    item = data.get("item") or {}
    artists = item.get("artists") or []
    album = item.get("album") or {}
    images = album.get("images") or []
    return {
        "has_playback": bool(data),
        "is_playing": bool(data.get("is_playing")),
        "title": item.get("name") or "",
        "track_name": item.get("name") or "",
        "artist": ", ".join(artist.get("name", "") for artist in artists if artist.get("name")),
        "artist_name": ", ".join(artist.get("name", "") for artist in artists if artist.get("name")),
        "album_name": album.get("name") or "",
        "album_image_url": images[0].get("url") if images else "",
        "progress_ms": data.get("progress_ms"),
        "duration_ms": item.get("duration_ms"),
        "volume_percent": (data.get("device") or {}).get("volume_percent"),
        "shuffle": bool(data.get("shuffle_state")),
        "repeat_state": data.get("repeat_state") or "off",
        "device": _normalize_device(data.get("device") or {}),
    }


def _normalize_device(device: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": device.get("id") or "",
        "name": device.get("name") or "",
        "type": device.get("type") or "",
        "active": bool(device.get("is_active")),
        "supports_volume": not bool(device.get("is_restricted")),
        "volume_percent": device.get("volume_percent"),
    }


def _normalize_queue_item(item: dict[str, Any]) -> dict[str, str]:
    artists = item.get("artists") or []
    return {
        "title": item.get("name") or "",
        "subtitle": ", ".join(artist.get("name", "") for artist in artists if artist.get("name")),
        "uri": item.get("uri") or "",
    }


def _normalize_playlist(item: dict[str, Any]) -> dict[str, str]:
    owner = item.get("owner") or {}
    return {
        "name": item.get("name") or "",
        "owner": owner.get("display_name") or owner.get("id") or "",
        "uri": item.get("uri") or "",
    }


def _spotify_error_message(body: Any) -> str:
    """Return a concise Spotify error message without logging full payloads."""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("reason") or "Spotify API error")
        if isinstance(error, str):
            return error
        return str(body.get("message") or "Spotify API error")
    text = str(body or "").strip()
    return text[:240] if text else "Spotify API error"
