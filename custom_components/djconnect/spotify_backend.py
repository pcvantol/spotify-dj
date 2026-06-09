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
    DOMAIN,
    DEFAULT_SPOTIFY_MARKET,
)
from .spotify_oauth import SpotifyTokenRefreshError, refresh_access_token

SPOTIFY_API_BASE = "https://api.spotify.com/v1"
CACHE_TTL_SECONDS = 30
ACCESS_TOKEN_EXPIRY_SAFETY_SECONDS = 60
_LOGGER = logging.getLogger(__name__)


class SpotifyBackendError(RuntimeError):
    """Raised when the configured Spotify backend cannot serve a command."""


class SpotifyReauthRequiredError(SpotifyBackendError):
    """Raised when Spotify revoked the stored OAuth refresh token."""


async def handle_spotify_command(
    hass: HomeAssistant,
    runtime: Any,
    command: str,
    value: Any = None,
    *,
    play: bool | None = None,
) -> dict[str, Any]:
    """Handle a generic DJConnect playback command using HA-stored credentials."""
    backend = SpotifyBackend(hass, runtime)
    normalized = str(command or "").strip().lower()
    _LOGGER.debug("DJConnect Spotify backend handling command: %s", normalized)
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
    if normalized == "set_shuffle":
        await backend.set_shuffle(value)
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "set_repeat":
        await backend.set_repeat(str(value or ""))
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "set_output":
        await backend.set_output(str(value or ""), play=bool(play))
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "set_volume":
        await backend.set_volume(value)
        return {"success": True, "playback": await backend.playback_state()}
    raise ValueError(f"Unsupported DJConnect command: {command}")


class SpotifyBackend:
    """Small Spotify Web API backend using credentials stored in Home Assistant."""

    def __init__(self, hass: HomeAssistant, runtime: Any) -> None:
        self.hass = hass
        self.runtime = runtime
        self.session = async_get_clientsession(hass)

    @property
    def conf(self) -> dict[str, Any]:
        return self.runtime.config

    async def _access_token(self, *, force_refresh: bool = False) -> str:
        client_id = str(self.conf.get(CONF_SPOTIFY_CLIENT_ID) or "").strip()
        refresh_token = str(
            getattr(self.runtime, "latest_spotify_refresh_token", None)
            or self.conf.get(CONF_SPOTIFY_REFRESH_TOKEN)
            or ""
        ).strip()
        if not client_id or not refresh_token:
            raise SpotifyBackendError("Spotify OAuth is not configured in Home Assistant")
        cached_token = getattr(self.runtime, "spotify_access_token", None)
        cached_expires_at = float(getattr(self.runtime, "spotify_access_token_expires_at", 0) or 0)
        if (
            not force_refresh
            and cached_token
            and cached_expires_at - ACCESS_TOKEN_EXPIRY_SAFETY_SECONDS > time.time()
        ):
            return str(cached_token)
        try:
            token = await refresh_access_token(
                self.hass,
                client_id=client_id,
                refresh_token=refresh_token,
            )
        except SpotifyTokenRefreshError as exc:
            if exc.error == "invalid_grant":
                _create_spotify_reauth_issue(
                    self.hass,
                    getattr(self.runtime, "entry", None),
                )
                message = (
                    "Spotify authorization has expired or was revoked. "
                    "Reauthorize DJConnect from the integration options or run "
                    "djconnect.start_spotify_oauth, then try again."
                )
                self.runtime.update(last_error=message)
                raise SpotifyReauthRequiredError(message) from exc
            raise SpotifyBackendError(
                f"Spotify OAuth refresh failed HTTP {exc.status}: {exc.error or 'unknown'}"
            ) from exc
        rotated = str(token.get("refresh_token") or "").strip()
        if rotated:
            updater = getattr(self.runtime, "update_spotify_refresh_token", None)
            if callable(updater) and updater(rotated):
                entry = getattr(self.runtime, "entry", None)
                if entry is not None:
                    new_data = dict(entry.data)
                    new_data[CONF_SPOTIFY_REFRESH_TOKEN] = rotated
                    self.hass.config_entries.async_update_entry(entry, data=new_data)
                _LOGGER.debug("DJConnect Spotify refresh_token=rotated/present")
        access_token = str(token.get("access_token") or "").strip()
        if not access_token:
            raise SpotifyBackendError("Spotify OAuth refresh did not return an access token")
        expires_in = int(token.get("expires_in") or 3600)
        self.runtime.spotify_access_token = access_token
        self.runtime.spotify_access_token_expires_at = time.time() + max(60, expires_in)
        return access_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        expected_empty: bool = False,
    ) -> Any:
        return await self._request_with_token(
            method,
            path,
            json=json,
            expected_empty=expected_empty,
            force_refresh=False,
            retry_on_unauthorized=True,
        )

    async def _request_with_token(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None,
        expected_empty: bool,
        force_refresh: bool,
        retry_on_unauthorized: bool,
    ) -> Any:
        token = await self._access_token(force_refresh=force_refresh)
        async with self.session.request(
            method,
            SPOTIFY_API_BASE + path,
            json=json,
            headers={"Authorization": f"Bearer {token}"},
            timeout=ClientTimeout(total=12),
        ) as resp:
            if resp.status == 401 and retry_on_unauthorized:
                await _consume_spotify_response(resp)
                self.runtime.spotify_access_token = None
                self.runtime.spotify_access_token_expires_at = 0
                _LOGGER.debug("DJConnect Spotify access token expired; refreshing once")
                return await self._request_with_token(
                    method,
                    path,
                    json=json,
                    expected_empty=expected_empty,
                    force_refresh=True,
                    retry_on_unauthorized=False,
                )
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
                "shuffle": playback.get("shuffle"),
                "repeat_state": playback.get("repeat_state"),
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
            raise SpotifyBackendError("DJConnect Liked Proxy playlist URI is not configured")
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

    async def set_shuffle(self, value: Any) -> None:
        """Set Spotify shuffle state from the canonical DJConnect command."""
        enabled = _bool_value(value)
        await self._request(
            "PUT",
            f"/me/player/shuffle?state={str(enabled).lower()}",
            expected_empty=True,
        )

    async def set_repeat(self, value: str) -> None:
        """Set Spotify repeat state from the canonical DJConnect command."""
        repeat = value.strip().lower()
        if repeat not in {"off", "track", "context"}:
            raise ValueError("set_repeat value must be off, track or context")
        await self._request(
            "PUT",
            f"/me/player/repeat?state={repeat}",
            expected_empty=True,
        )

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


def _bool_value(value: Any) -> bool:
    """Parse a canonical boolean command value."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("set_shuffle value must be true or false")


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


async def _consume_spotify_response(resp: Any) -> None:
    """Read an error response before retrying so aiohttp can reuse the connection."""
    try:
        await resp.text()
    except Exception:  # noqa: BLE001
        pass


def _create_spotify_reauth_issue(hass: HomeAssistant, entry: Any) -> None:
    """Create a repair hint when Spotify revoked the stored refresh token."""
    if entry is None:
        return
    try:
        from homeassistant.helpers import issue_registry as ir

        ir.async_create_issue(
            hass,
            DOMAIN,
            f"{entry.entry_id}_spotify_refresh_token_revoked",
            data={"entry_id": entry.entry_id},
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="spotify_refresh_token_revoked",
        )
    except Exception:  # noqa: BLE001
        _LOGGER.debug(
            "DJConnect could not create Spotify reauthorization repair issue",
            exc_info=True,
        )
