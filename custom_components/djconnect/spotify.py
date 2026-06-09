from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_LIKED_PROXY, CONF_SPOTIFY_SOURCE
from .spotify_backend import handle_spotify_command

MEDIA_CONTENT_TYPES = {
    "album": "album",
    "artist": "artist",
    "track": "track",
}


async def play_from_intent(
    hass: HomeAssistant,
    runtime: Any,
    intent: dict[str, Any],
    conf: dict[str, Any],
) -> dict[str, Any]:
    source = (conf.get(CONF_SPOTIFY_SOURCE) or "").strip()
    if source:
        await handle_spotify_command(hass, runtime, "set_output", source, play=False)

    media_content_id, media_content_type = _media_from_intent(intent, conf)

    if not media_content_id:
        raise RuntimeError("Could not determine a Spotify search query")

    command = "start_playlist" if media_content_type == "playlist" else "play"
    value: Any = media_content_id
    if command == "play" and not media_content_id.startswith("spotify:"):
        value = {"query": media_content_id, "type": media_content_type}
    response = await handle_spotify_command(
        hass,
        runtime,
        command,
        value,
    )

    return {
        "played": True,
        "source": source,
        "media_content_id": media_content_id,
        "media_content_type": media_content_type,
        "resolved_media": getattr(runtime, "last_resolved_media", None),
        "device_response": response,
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
