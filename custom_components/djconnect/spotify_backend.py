from __future__ import annotations

import asyncio
import time
import logging
from urllib.parse import urlencode
from typing import Any

from aiohttp import ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_LIKED_PROXY,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_REFRESH_TOKEN,
    CONF_SPOTIFY_SOURCE,
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
        return {"success": True, **await backend.queue()}
    if normalized == "playlists":
        return {"success": True, "playlists": await backend.playlists()}
    if normalized == "pause":
        await backend.pause()
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "play":
        await backend.play(value)
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "play_context_at":
        await backend.play_context_at(value)
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "next":
        await backend.next()
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "previous":
        await backend.previous()
        return {"success": True, "playback": await backend.playback_state()}
    if normalized == "seek_relative":
        await backend.seek_relative(value)
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
        refresh_token = _current_refresh_token(self.runtime, self.conf)
        if not client_id or not refresh_token:
            raise SpotifyBackendError("Spotify OAuth is not configured in Home Assistant")
        cached_token = getattr(self.runtime, "spotify_access_token", None)
        cached_expires_at = float(getattr(self.runtime, "spotify_access_token_expires_at", 0) or 0)
        now = time.time()
        seconds_left = int(cached_expires_at - now)
        if (
            not force_refresh
            and cached_token
            and cached_expires_at - ACCESS_TOKEN_EXPIRY_SAFETY_SECONDS > now
        ):
            _LOGGER.debug(
                "DJConnect Spotify using cached access token seconds_left=%s",
                seconds_left,
            )
            return str(cached_token)
        _LOGGER.debug(
            "DJConnect Spotify access token refresh needed force_refresh=%s "
            "cached=%s seconds_left=%s refresh_sources=%s",
            force_refresh,
            bool(cached_token),
            seconds_left if cached_token else None,
            _refresh_token_source_names(self.runtime, self.conf),
        )
        lock = _token_refresh_lock(self.runtime)
        async with lock:
            cached_token = getattr(self.runtime, "spotify_access_token", None)
            cached_expires_at = float(
                getattr(self.runtime, "spotify_access_token_expires_at", 0) or 0
            )
            now = time.time()
            seconds_left = int(cached_expires_at - now)
            if (
                not force_refresh
                and cached_token
                and cached_expires_at - ACCESS_TOKEN_EXPIRY_SAFETY_SECONDS > now
            ):
                _LOGGER.debug(
                    "DJConnect Spotify reused access token after refresh lock seconds_left=%s",
                    seconds_left,
                )
                return str(cached_token)
            refresh_token = _current_refresh_token(self.runtime, self.conf)
            if not refresh_token:
                raise SpotifyBackendError("Spotify OAuth is not configured in Home Assistant")
            return await self._refresh_access_token_locked(
                client_id=client_id,
                refresh_token=refresh_token,
            )

    async def _refresh_access_token_locked(
        self,
        *,
        client_id: str,
        refresh_token: str,
        attempted_refresh_tokens: set[str] | None = None,
    ) -> str:
        attempted_refresh_tokens = set(attempted_refresh_tokens or set())
        attempted_refresh_tokens.add(refresh_token)
        _LOGGER.debug(
            "DJConnect Spotify refresh attempt source_count=%s attempted=%s",
            len(_refresh_token_candidates(self.runtime, self.conf)),
            len(attempted_refresh_tokens),
        )
        try:
            token = await refresh_access_token(
                self.hass,
                client_id=client_id,
                refresh_token=refresh_token,
            )
        except SpotifyTokenRefreshError as exc:
            if exc.error == "invalid_grant":
                for source, latest_refresh_token in _refresh_token_candidates(
                    self.runtime,
                    self.conf,
                ):
                    if latest_refresh_token in attempted_refresh_tokens:
                        continue
                    _LOGGER.debug(
                        "DJConnect Spotify refresh_token rejected; retrying alternate stored token source=%s",
                        source,
                    )
                    return await self._refresh_access_token_locked(
                        client_id=client_id,
                        refresh_token=latest_refresh_token,
                        attempted_refresh_tokens=attempted_refresh_tokens,
                    )
                _LOGGER.warning(
                    "DJConnect Spotify refresh token rejected by Spotify; user reauthorization required"
                )
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
                _LOGGER.debug(
                    "DJConnect Spotify refresh_token=rotated/persisted source=token_endpoint"
                )
        access_token = str(token.get("access_token") or "").strip()
        if not access_token:
            raise SpotifyBackendError("Spotify OAuth refresh did not return an access token")
        expires_in = int(token.get("expires_in") or 3600)
        self.runtime.spotify_access_token = access_token
        self.runtime.spotify_access_token_expires_at = time.time() + max(60, expires_in)
        _LOGGER.debug(
            "DJConnect Spotify access token refreshed expires_in=%s rotated_refresh_token=%s",
            expires_in,
            bool(rotated),
        )
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
        _merge_playback_status(
            self.runtime.device_status,
            {
                "spotify_status": "playing" if playback.get("is_playing") else "idle",
                "volume": playback.get("volume_percent"),
                "last_track": playback.get("track_name"),
                "sound_output": (playback.get("device") or {}).get("name"),
                "shuffle": playback.get("shuffle"),
                "repeat_state": playback.get("repeat_state"),
            },
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

    async def queue(self) -> dict[str, Any]:
        data = await self._request("GET", "/me/player/queue")
        queue = data.get("queue") or []
        normalized = [_normalize_queue_item(item) for item in queue]
        playback = self.runtime.last_playback or {}
        context_uri = str(playback.get("context_uri") or playback.get("queue_context") or "").strip()
        self.runtime.device_status["queue"] = {
            "items": normalized,
            "context_uri": context_uri,
            "contextUri": context_uri,
        }
        self.runtime.update()
        return {
            "queue": normalized,
            "context_uri": context_uri,
            "contextUri": context_uri,
        }

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
            value = await self._playable_value(value)
            body = {"uris": [str(value)]} if str(value).startswith("spotify:track:") else {"context_uri": str(value)}
        try:
            await self._request("PUT", "/me/player/play", json=body, expected_empty=True)
        except SpotifyBackendError as exc:
            if not _looks_like_no_active_device(exc):
                raise
            await self._ensure_playback_device(play=False)
            await self._request("PUT", "/me/player/play", json=body, expected_empty=True)

    async def play_context_at(self, value: Any) -> None:
        if not isinstance(value, dict):
            raise ValueError("Provide context_uri and offset_uri")
        context_uri = str(value.get("context_uri") or "").strip()
        offset_uri = str(value.get("offset_uri") or value.get("uri") or "").strip()
        if not offset_uri:
            raise ValueError("Provide offset_uri")
        if not context_uri:
            playback = self.runtime.last_playback or {}
            context_uri = str(playback.get("context_uri") or "").strip()
        if not context_uri:
            raise ValueError("Cannot start queue item without playback context")
        if context_uri.startswith("spotify:artist:") and offset_uri.startswith("spotify:track:"):
            await self._request(
                "PUT",
                "/me/player/play",
                json={"uris": [offset_uri]},
                expected_empty=True,
            )
            return
        await self._request(
            "PUT",
            "/me/player/play",
            json={"context_uri": context_uri, "offset": {"uri": offset_uri}},
            expected_empty=True,
        )

    async def next(self) -> None:
        await self._request("POST", "/me/player/next", expected_empty=True)

    async def previous(self) -> None:
        await self._request("POST", "/me/player/previous", expected_empty=True)

    async def seek_relative(self, value: Any) -> None:
        """Seek relative to the current Spotify playback position."""
        try:
            offset_ms = int(float(value))
        except (TypeError, ValueError) as exc:
            raise ValueError("seek_relative value must be an integer millisecond offset") from exc
        playback = await self.playback_state()
        if not playback.get("has_playback"):
            raise SpotifyBackendError("Cannot seek because Spotify playback is not active")
        current_ms = _int_or_none(playback.get("progress_ms")) or 0
        duration_ms = _int_or_none(playback.get("duration_ms"))
        position_ms = max(0, current_ms + offset_ms)
        if duration_ms is not None:
            position_ms = min(position_ms, max(0, duration_ms))
        await self._request(
            "PUT",
            f"/me/player/seek?position_ms={position_ms}",
            expected_empty=True,
        )

    async def start_liked_proxy(self) -> None:
        playlist = str(self.conf.get(CONF_LIKED_PROXY) or "").strip()
        if not playlist:
            raise SpotifyBackendError("DJConnect Liked Proxy playlist URI is not configured")
        await self.start_playlist(playlist)

    async def start_playlist(self, playlist_uri: str) -> None:
        uri = playlist_uri.strip()
        if not uri:
            raise ValueError("Provide a playlist URI")
        if not uri.startswith("spotify:playlist:"):
            uri = await self._search_uri(uri, "playlist")
        body = {"context_uri": uri}
        try:
            await self._request("PUT", "/me/player/play", json=body, expected_empty=True)
        except SpotifyBackendError as exc:
            if not _looks_like_no_active_device(exc):
                raise
            await self._ensure_playback_device(play=False)
            await self._request("PUT", "/me/player/play", json=body, expected_empty=True)

    async def _playable_value(self, value: Any) -> str:
        if isinstance(value, dict):
            query = str(value.get("query") or value.get("value") or "").strip()
            media_type = str(value.get("type") or "artist").strip().lower()
            if not query:
                raise ValueError("Provide a Spotify URI or search query")
            if query.startswith("spotify:"):
                return query
            return await self._search_uri(query, media_type)
        text = str(value or "").strip()
        if not text:
            raise ValueError("Provide a Spotify URI or search query")
        if text.startswith("spotify:"):
            return text
        return await self._search_uri(text, "artist")

    async def _search_uri(self, query: str, media_type: str) -> str:
        spotify_type = _spotify_search_type(media_type)
        market = str(self.conf.get("spotify_market") or DEFAULT_SPOTIFY_MARKET)
        params = urlencode({"q": query, "type": spotify_type, "limit": 1, "market": market})
        data = await self._request("GET", f"/search?{params}")
        item = _first_search_item(data, spotify_type)
        uri = str(item.get("uri") or "").strip()
        if not uri:
            self.runtime.last_spotify_search = _spotify_search_debug(
                query=query,
                spotify_type=spotify_type,
                data=data,
                selected={},
            )
            raise SpotifyBackendError(f"Spotify search found no {spotify_type} for: {query}")
        resolved = _normalize_search_item(item, spotify_type, query)
        self.runtime.last_resolved_media = resolved
        self.runtime.last_spotify_search = _spotify_search_debug(
            query=query,
            spotify_type=spotify_type,
            data=data,
            selected=resolved,
        )
        _LOGGER.debug(
            "DJConnect Spotify search resolved type=%s query=%s uri=%s",
            spotify_type,
            query,
            uri,
        )
        return uri

    async def _ensure_playback_device(self, *, play: bool) -> str:
        devices = await self.devices()
        configured = str(self.conf.get(CONF_SPOTIFY_SOURCE) or "").strip()
        selected = _select_spotify_device(devices, configured)
        device_id = str(selected.get("id") or "").strip()
        if not device_id:
            raise SpotifyBackendError(
                "No Spotify playback device is available. Open Spotify on a phone, "
                "desktop or speaker, or set Spotify source in DJConnect options."
            )
        await self._transfer_playback(device_id, play=play)
        return device_id

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
        devices = await self.devices()
        selected = _select_spotify_device(devices, device_id)
        device_id = str(selected.get("id") or device_id).strip()
        if not device_id:
            raise ValueError("Provide an output device id")
        await self._transfer_playback(device_id, play=play)

    async def _transfer_playback(self, device_id: str, *, play: bool = False) -> None:
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
    context = data.get("context") or {}
    context_uri = context.get("uri") or ""
    artists = item.get("artists") or []
    album = item.get("album") or {}
    images = album.get("images") or item.get("images") or []
    album_image_url = _best_image_url(images)
    return {
        "has_playback": bool(data),
        "is_playing": bool(data.get("is_playing")),
        "title": item.get("name") or "",
        "track_name": item.get("name") or "",
        "uri": item.get("uri") or "",
        "current_uri": item.get("uri") or "",
        "context": _normalize_context(context),
        "context_uri": context_uri,
        "queue_context": context_uri,
        "artist": ", ".join(artist.get("name", "") for artist in artists if artist.get("name")),
        "artist_name": ", ".join(artist.get("name", "") for artist in artists if artist.get("name")),
        "album_name": album.get("name") or "",
        "album_image_url": album_image_url,
        "media_image_url": album_image_url,
        "progress_ms": data.get("progress_ms"),
        "duration_ms": item.get("duration_ms"),
        "volume_percent": (data.get("device") or {}).get("volume_percent"),
        "shuffle": bool(data.get("shuffle_state")),
        "repeat_state": data.get("repeat_state") or "off",
        "device": _normalize_device(data.get("device") or {}),
    }


def _spotify_search_type(media_type: str) -> str:
    normalized = str(media_type or "").strip().lower()
    if normalized == "playlist":
        return "playlist"
    return "artist"


def _first_search_item(data: dict[str, Any], spotify_type: str) -> dict[str, Any]:
    section = data.get(f"{spotify_type}s") or {}
    items = section.get("items") or []
    if not isinstance(items, list):
        return {}
    for item in items:
        if isinstance(item, dict):
            return item
    return {}


def _normalize_search_item(item: dict[str, Any], spotify_type: str, query: str) -> dict[str, Any]:
    artists = item.get("artists") or []
    owner = item.get("owner") or {}
    album = item.get("album") or {}
    name = item.get("name") or ""
    artist_name = (
        name
        if spotify_type == "artist"
        else ", ".join(artist.get("name", "") for artist in artists if artist.get("name"))
    )
    return {
        "type": spotify_type,
        "query": query,
        "uri": item.get("uri") or "",
        "title": "" if spotify_type == "artist" else name,
        "track_name": "" if spotify_type == "artist" else name,
        "artist": artist_name,
        "artist_name": artist_name,
        "album_name": album.get("name") or "",
        "owner": owner.get("display_name") or owner.get("id") or "",
    }


def _spotify_search_debug(
    *,
    query: str,
    spotify_type: str,
    data: dict[str, Any],
    selected: dict[str, Any],
) -> dict[str, Any]:
    section = data.get(f"{spotify_type}s") or {}
    items = section.get("items") or []
    if not isinstance(items, list):
        items = []
    return {
        "query": query,
        "type": spotify_type,
        "total": section.get("total"),
        "returned": len(items),
        "selected": selected,
        "candidates": [
            _normalize_search_item(item, spotify_type, query)
            for item in items[:5]
            if isinstance(item, dict)
        ],
    }


def _select_spotify_device(devices: list[dict[str, Any]], configured: str) -> dict[str, Any]:
    configured = str(configured or "").strip()
    if configured:
        for device in devices:
            if str(device.get("id") or "").strip() == configured:
                return device
        for device in devices:
            if str(device.get("name") or "").strip().lower() == configured.lower():
                return device
    for device in devices:
        if device.get("active") and device.get("id"):
            return device
    for device in devices:
        if device.get("id"):
            return device
    return {}


def _looks_like_no_active_device(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "no active device" in message
        or "device not found" in message
        or "player command failed" in message
    )


def _merge_playback_status(device_status: dict[str, Any], update: dict[str, Any]) -> None:
    """Merge backend playback status without erasing cached device sensor values."""
    for key, value in update.items():
        if value in (None, "", [], {}) and key in device_status:
            continue
        device_status[key] = value


def _normalize_context(context: dict[str, Any]) -> dict[str, str]:
    return {
        "type": context.get("type") or "",
        "uri": context.get("uri") or "",
        "href": context.get("href") or "",
    }


def _best_image_url(images: Any) -> str:
    if not isinstance(images, list):
        return ""
    valid = [image for image in images if isinstance(image, dict) and image.get("url")]
    if not valid:
        return ""
    sorted_images = sorted(
        valid,
        key=lambda image: int(image.get("width") or 0) * int(image.get("height") or 0),
        reverse=True,
    )
    return str(sorted_images[0]["url"])


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
    images = (item.get("album") or {}).get("images") or item.get("images") or []
    album_image_url = _best_image_url(images)
    return {
        "title": item.get("name") or "",
        "subtitle": ", ".join(artist.get("name", "") for artist in artists if artist.get("name")),
        "uri": item.get("uri") or "",
        "album_image_url": album_image_url,
        "albumImageUrl": album_image_url,
        "image_url": album_image_url,
        "imageUrl": album_image_url,
        "thumbnail_url": album_image_url,
    }


def _normalize_playlist(item: dict[str, Any]) -> dict[str, str]:
    owner = item.get("owner") or {}
    image_url = _best_image_url(item.get("images") or [])
    return {
        "id": item.get("uri") or item.get("id") or "",
        "name": item.get("name") or "",
        "owner": owner.get("display_name") or owner.get("id") or "",
        "uri": item.get("uri") or "",
        "image_url": image_url,
        "imageUrl": image_url,
        "album_image_url": image_url,
        "albumImageUrl": image_url,
        "media_image_url": image_url,
        "thumbnail_url": image_url,
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


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _current_refresh_token(runtime: Any, conf: dict[str, Any]) -> str:
    candidates = _refresh_token_candidates(runtime, conf)
    return candidates[0][1] if candidates else ""


def _refresh_token_candidates(runtime: Any, conf: dict[str, Any]) -> list[tuple[str, str]]:
    """Return known Spotify refresh tokens without exposing token values in logs."""
    entry = getattr(runtime, "entry", None)
    entry_data = getattr(entry, "data", {}) if entry is not None else {}
    raw_candidates = (
        ("runtime", getattr(runtime, "latest_spotify_refresh_token", None)),
        ("entry", entry_data.get(CONF_SPOTIFY_REFRESH_TOKEN)),
        ("config", conf.get(CONF_SPOTIFY_REFRESH_TOKEN)),
    )
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for source, value in raw_candidates:
        token = str(value or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        result.append((source, token))
    return result


def _refresh_token_source_names(runtime: Any, conf: dict[str, Any]) -> list[str]:
    """Return source names only; never return token values."""
    return [source for source, _token in _refresh_token_candidates(runtime, conf)]


def _token_refresh_lock(runtime: Any) -> asyncio.Lock:
    lock = getattr(runtime, "spotify_token_refresh_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        runtime.spotify_token_refresh_lock = lock
    return lock


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
