from __future__ import annotations

import logging
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_SPOTIFY_PLAYER, CONF_SPOTIFY_SOURCE, CONF_LIKED_PROXY

_LOGGER = logging.getLogger(__name__)

async def play_from_intent(hass: HomeAssistant, intent: dict[str, Any], conf: dict[str, Any]) -> dict[str, Any]:
    player = conf.get(CONF_SPOTIFY_PLAYER)
    if not player:
        raise RuntimeError("Spotify player is niet ingesteld")

    source = (conf.get(CONF_SPOTIFY_SOURCE) or "").strip()
    if source:
        await _safe_select_source(hass, player, source)

    media_type = (intent.get("type") or "search").lower()
    media_content_id = (intent.get("spotify_search_query") or intent.get("query") or "").strip()
    media_content_type = "music"

    if media_type == "liked":
        proxy = (conf.get(CONF_LIKED_PROXY) or "").strip()
        if not proxy:
            raise RuntimeError("Voor favoriete nummers is een liked-songs proxy playlist URI nodig")
        media_content_id = proxy
        media_content_type = "playlist"
    elif media_type == "playlist":
        media_content_id = (intent.get("playlist") or media_content_id).strip()
        media_content_type = "playlist"
    elif media_type == "track":
        media_content_type = "track"
    elif media_type == "artist":
        media_content_type = "artist"
    elif media_type == "album":
        media_content_type = "album"
    elif media_type == "latest_album":
        # HA Spotify service can search by text, but cannot reliably sort by latest album.
        # We send a richer music query for now; a future version can use the Spotify Web API token directly.
        artist = (intent.get("artist") or "").strip()
        media_content_id = f"latest album {artist}" if artist else media_content_id
        media_content_type = "album"
    else:
        media_content_type = "music"

    if not media_content_id:
        raise RuntimeError("Ik kon geen Spotify zoekopdracht bepalen")

    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": player,
            "media_content_id": media_content_id,
            "media_content_type": media_content_type,
        },
        blocking=True,
    )

    return {
        "played": True,
        "player": player,
        "source": source,
        "media_content_id": media_content_id,
        "media_content_type": media_content_type,
    }

async def _safe_select_source(hass: HomeAssistant, player: str, source: str) -> None:
    try:
        await hass.services.async_call(
            "media_player",
            "select_source",
            {"entity_id": player, "source": source},
            blocking=True,
        )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("SpotifyDJ select_source failed: %s", exc)
