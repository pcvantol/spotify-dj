from __future__ import annotations

import re
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_LIKED_PROXY, CONF_SPOTIFY_SOURCE
from .spotify_backend import handle_spotify_command

MEDIA_CONTENT_TYPES = {
    "artist": "artist",
    "album": "artist",
    "track": "artist",
    "search": "artist",
    "music": "artist",
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
    resolved_media = _fresh_resolved_media(runtime, media_content_id)

    return {
        "played": True,
        "source": source,
        "media_content_id": media_content_id,
        "media_content_type": media_content_type,
        "resolved_media": resolved_media,
        "device_response": response,
    }


def _fresh_resolved_media(
    runtime: Any,
    query: str,
) -> dict[str, Any] | None:
    """Return media resolved by the command that just ran, not stale playback."""
    search = getattr(runtime, "last_spotify_search", None)
    if isinstance(search, dict) and str(search.get("query") or "").strip() == str(query).strip():
        selected = search.get("selected")
        if isinstance(selected, dict) and selected:
            return selected
    return None


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
        return _artist_media(intent, media_content_id)
    if media_type in {"artist", "album", "track", "search", "music"}:
        return _artist_media(intent, media_content_id)
    return media_content_id, MEDIA_CONTENT_TYPES.get(media_type, "music")


def _liked_proxy_media(conf: dict[str, Any]) -> tuple[str, str]:
    proxy = (conf.get(CONF_LIKED_PROXY) or "").strip()
    if not proxy:
        raise RuntimeError("Liked songs require a default playlist URI")
    return proxy, "playlist"


def _artist_media(
    intent: dict[str, Any],
    fallback_query: str,
) -> tuple[str, str]:
    artist = (intent.get("artist") or "").strip()
    query = artist if artist else _extract_artist_query(fallback_query)
    return query, "artist"


_ARTIST_QUERY_PATTERNS = (
    r"^\s*ik\s+heb\s+(?:wel\s+)?(?:zin|trek)\s+in\s+(.+?)\s*$",
    r"^\s*ik\s+wil\s+(?:wel\s+|graag\s+)?(.+?)\s+(?:horen|luisteren|starten|opzetten|spelen)\s*$",
    r"^\s*(.+?)\s+wil\s+ik\s+(?:wel\s+|graag\s+)?(?:horen|luisteren|starten|opzetten|spelen)\s*$",
    r"^\s*(?:zet|speel|start|draai)\s+(?:eens\s+|even\s+|maar\s+|graag\s+)?(?:af\s+|op\s+|aan\s+)?(.+?)\s*(?:op|af|aan)?\s*$",
    r"^\s*(?:play|start|put\s+on)\s+(.+?)\s*$",
    r"^\s*i\s+(?:feel\s+like|want\s+to\s+hear|want)\s+(.+?)\s*$",
)


def _extract_artist_query(text: str) -> str:
    """Extract the likely artist from a spoken music request."""
    query = _clean_artist_query(text)
    for pattern in _ARTIST_QUERY_PATTERNS:
        match = re.match(pattern, query, flags=re.IGNORECASE)
        if match:
            candidate = _clean_artist_query(match.group(1))
            if candidate:
                return candidate
    return query


def _clean_artist_query(text: str) -> str:
    value = " ".join(str(text or "").strip().split())
    value = re.sub(r"[.!?]+$", "", value).strip()
    return value.strip(" \"'")
