from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_SPOTIFY_PLAYER, CONF_SPOTIFY_SOURCE, CONF_LIKED_PROXY

_LOGGER = logging.getLogger(__name__)

MEDIA_CONTENT_TYPES = {
    "album": "album",
    "artist": "artist",
    "track": "track",
}


async def play_from_intent(
    hass: HomeAssistant,
    intent: dict[str, Any],
    conf: dict[str, Any],
) -> dict[str, Any]:
    player = conf.get(CONF_SPOTIFY_PLAYER)
    if not player:
        raise RuntimeError("Spotify playback player is not configured")

    source = (conf.get(CONF_SPOTIFY_SOURCE) or "").strip()
    if source:
        await _safe_select_source(hass, player, source)

    media_content_id, media_content_type = _media_from_intent(intent, conf)

    if not media_content_id:
        raise RuntimeError("Could not determine a Spotify search query")

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


def _media_from_intent(
    intent: dict[str, Any],
    conf: dict[str, Any],
) -> tuple[str, str]:
    media_type = (intent.get("type") or "search").lower()
    media_content_id = (
        intent.get("spotify_search_query") or intent.get("query") or ""
    ).strip()

    if media_type == "liked":
        return _liked_proxy_media(conf)
    if media_type == "playlist":
        return (intent.get("playlist") or media_content_id).strip(), "playlist"
    if media_type == "latest_album":
        return _latest_album_media(intent, media_content_id)
    return media_content_id, MEDIA_CONTENT_TYPES.get(media_type, "music")


def _liked_proxy_media(conf: dict[str, Any]) -> tuple[str, str]:
    proxy = (conf.get(CONF_LIKED_PROXY) or "").strip()
    if not proxy:
        raise RuntimeError("Liked songs require a proxy playlist URI")
    return proxy, "playlist"


def _latest_album_media(
    intent: dict[str, Any],
    fallback_query: str,
) -> tuple[str, str]:
    artist = (intent.get("artist") or "").strip()
    query = f"latest album {artist}" if artist else fallback_query
    return query, "album"


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
