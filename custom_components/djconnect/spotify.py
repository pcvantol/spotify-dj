from __future__ import annotations

import re
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_LIKED_PROXY, CONF_SPOTIFY_SOURCE
from .spotify_backend import handle_spotify_command

MEDIA_CONTENT_TYPES = {
    "artist": "artist",
    "album": "album",
    "track": "track",
    "search": "artist",
    "music": "artist",
    "playlist": "playlist",
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
    if media_type == "track":
        return _track_media(intent, media_content_id)
    if media_type == "album":
        return _album_media(intent, media_content_id)
    if media_type == "latest_album":
        return _artist_media(intent, media_content_id)
    if media_type in {"search", "music"}:
        if intent.get("artist"):
            return _artist_media(intent, media_content_id)
        if intent.get("playlist"):
            return str(intent.get("playlist") or "").strip(), "playlist"
        if intent.get("title") or intent.get("track"):
            return _track_media(intent, media_content_id)
        if intent.get("album"):
            return _album_media(intent, media_content_id)
        parsed = parse_spoken_music_request(media_content_id)
        parsed_type = str(parsed.get("type") or "artist")
        if parsed_type == "liked":
            return _liked_proxy_media(conf)
        if parsed_type == "playlist":
            return str(parsed.get("query") or "").strip(), "playlist"
        if parsed_type == "track":
            return str(parsed.get("query") or "").strip(), "track"
        if parsed_type == "album":
            return str(parsed.get("query") or "").strip(), "album"
        return str(parsed.get("query") or "").strip(), "artist"
    if media_type == "artist":
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


def _track_media(
    intent: dict[str, Any],
    fallback_query: str,
) -> tuple[str, str]:
    title = _clean_artist_query(intent.get("title") or intent.get("track") or "")
    artist = _clean_artist_query(intent.get("artist") or "")
    query = _query_with_artist(title, artist) if title else _clean_artist_query(fallback_query)
    return query, "track"


def _album_media(
    intent: dict[str, Any],
    fallback_query: str,
) -> tuple[str, str]:
    album = _clean_artist_query(intent.get("album") or intent.get("title") or "")
    artist = _clean_artist_query(intent.get("artist") or "")
    query = _query_with_artist(album, artist) if album else _clean_artist_query(fallback_query)
    return query, "album"


def _query_with_artist(title: str, artist: str) -> str:
    return f"{title} {artist}".strip() if artist else title


_ARTIST_QUERY_PATTERNS = (
    r"^\s*(?:artiest|band|artist)\s+(.+?)\s*$",
    r"^\s*ik\s+heb\s+(?:wel\s+)?(?:zin|trek)\s+in\s+(.+?)\s*$",
    r"^\s*ik\s+wil\s+(?:wel\s+|graag\s+)?(.+?)\s+(?:horen|luisteren|starten|opzetten|spelen)\s*$",
    r"^\s*(.+?)\s+wil\s+ik\s+(?:wel\s+|graag\s+)?(?:horen|luisteren|starten|opzetten|spelen)\s*$",
    r"^\s*(?:zet|speel|start|draai)\s+(?:eens\s+|even\s+|maar\s+|graag\s+)?(?:af\s+|op\s+|aan\s+)?(.+?)\s*(?:op|af|aan)?\s*$",
    r"^\s*(?:play|start|put\s+on)\s+(.+?)\s*$",
    r"^\s*i\s+(?:feel\s+like|want\s+to\s+hear|want)\s+(.+?)\s*$",
)

_LIKED_QUERY_PATTERNS = (
    r"^\s*(?:speel|start|zet|draai)\s+(?:mijn\s+)?(?:standaard\s+playlist|favorieten|liked\s+songs)\s*(?:op|af|aan)?\s*$",
    r"^\s*(?:play|start)\s+(?:my\s+)?(?:default\s+playlist|liked\s+songs|favorites)\s*$",
)

_PLAYLIST_QUERY_PATTERNS = (
    r"^\s*(?:speel|start|zet|draai)\s+(?:mijn\s+)?(?:playlist|afspeellijst)\s+(.+?)\s*(?:op|af|aan)?\s*$",
    r"^\s*(?:speel|start|zet|draai)\s+(.+?)\s+(?:playlist|afspeellijst)\s*(?:op|af|aan)?\s*$",
    r"^\s*(?:play|start|put\s+on)\s+(?:my\s+)?playlist\s+(.+?)\s*$",
    r"^\s*(?:play|start|put\s+on)\s+(.+?)\s+playlist\s*$",
)

_TRACK_QUERY_PATTERNS = (
    r"^\s*(?:speel|start|zet|draai)\s+(?:het\s+)?(?:nummer|liedje|track)\s+(.+?)\s+van\s+(?:artiest|band)\s+(.+?)\s*(?:op|af|aan)?\s*$",
    r"^\s*(?:speel|start|zet|draai)\s+(?:het\s+)?(?:nummer|liedje|track)\s+(.+?)\s+van\s+(.+?)\s*(?:op|af|aan)?\s*$",
    r"^\s*(?:het\s+)?(?:nummer|liedje|track)\s+(.+?)\s+van\s+(?:artiest|band)\s+(.+?)\s*$",
    r"^\s*(?:speel|start|zet|draai)\s+(?:het\s+)?(?:nummer|liedje|track)\s+(.+?)\s*(?:op|af|aan)?\s*$",
    r"^\s*(?:het\s+)?(?:nummer|liedje|track)\s+(.+?)\s+van\s+(.+?)\s*$",
    r"^\s*(?:het\s+)?(?:nummer|liedje|track)\s+(.+?)\s*$",
    r"^\s*(?:play|start|put\s+on)\s+(?:the\s+)?(?:song|track)\s+(.+?)\s+by\s+(.+?)\s*$",
    r"^\s*(?:play|start|put\s+on)\s+(?:the\s+)?(?:song|track)\s+(.+?)\s*$",
    r"^\s*(?:the\s+)?(?:song|track)\s+(.+?)\s+by\s+(.+?)\s*$",
    r"^\s*(?:the\s+)?(?:song|track)\s+(.+?)\s*$",
)

_ARTIST_WITH_TRACK_QUERY_PATTERNS = (
    r"^\s*(?:speel|start|zet|draai)\s+(?:artiest|band)\s+(.+?)\s+met\s+(?:het\s+)?(?:nummer|liedje|track)\s+(.+?)\s*(?:op|af|aan)?\s*$",
    r"^\s*(?:artiest|band)\s+(.+?)\s+met\s+(?:het\s+)?(?:nummer|liedje|track)\s+(.+?)\s*$",
    r"^\s*(?:play|start|put\s+on)\s+(?:artist|band)\s+(.+?)\s+with\s+(?:the\s+)?(?:song|track)\s+(.+?)\s*$",
    r"^\s*(?:artist|band)\s+(.+?)\s+with\s+(?:the\s+)?(?:song|track)\s+(.+?)\s*$",
)

_ALBUM_QUERY_PATTERNS = (
    r"^\s*(?:speel|start|zet|draai)\s+(?:het\s+)?(?:album|de\s+plaat)\s+(.+?)\s+van\s+(.+?)\s*(?:op|af|aan)?\s*$",
    r"^\s*(?:speel|start|zet|draai)\s+(?:het\s+)?(?:album|de\s+plaat)\s+(.+?)\s*(?:op|af|aan)?\s*$",
    r"^\s*(?:het\s+)?(?:album|de\s+plaat)\s+(.+?)\s+van\s+(.+?)\s*$",
    r"^\s*(?:play|start|put\s+on)\s+(?:the\s+)?album\s+(.+?)\s+by\s+(.+?)\s*$",
    r"^\s*(?:play|start|put\s+on)\s+(?:the\s+)?album\s+(.+?)\s*$",
    r"^\s*(?:the\s+)?album\s+(.+?)\s+by\s+(.+?)\s*$",
    r"^\s*(?:the\s+)?album\s+(.+?)\s*$",
    r"^\s*(?:het\s+)?(?:album|de\s+plaat)\s+(.+?)\s*$",
)


def parse_spoken_music_request(text: str) -> dict[str, str | None]:
    """Parse a spoken DJConnect music request into a Spotify search target."""
    query = _clean_artist_query(text)
    if not query:
        return _parsed_request("artist", "")
    for pattern in _LIKED_QUERY_PATTERNS:
        if re.match(pattern, query, flags=re.IGNORECASE):
            return _parsed_request("liked", query)
    playlist = _match_single_value(_PLAYLIST_QUERY_PATTERNS, query)
    if playlist:
        return _parsed_request("playlist", playlist, playlist=playlist)
    artist_track = _match_artist_title(_ARTIST_WITH_TRACK_QUERY_PATTERNS, query)
    if artist_track:
        artist, title = artist_track
        return _parsed_request(
            "track",
            _query_with_artist(title, artist),
            title=title,
            artist=artist,
        )
    track = _match_title_artist(_TRACK_QUERY_PATTERNS, query)
    if track:
        title, artist = track
        return _parsed_request(
            "track",
            _query_with_artist(title, artist),
            title=title,
            artist=artist,
        )
    album = _match_title_artist(_ALBUM_QUERY_PATTERNS, query)
    if album:
        title, artist = album
        return _parsed_request(
            "album",
            _query_with_artist(title, artist),
            title=title,
            artist=artist,
        )
    artist = _extract_artist_query(query)
    return _parsed_request("artist", artist, artist=artist)


def _parsed_request(
    media_type: str,
    query: str,
    *,
    artist: str | None = None,
    title: str | None = None,
    playlist: str | None = None,
) -> dict[str, str | None]:
    return {
        "type": media_type,
        "query": query,
        "artist": artist,
        "title": title,
        "playlist": playlist,
    }


def _match_single_value(patterns: tuple[str, ...], query: str) -> str:
    for pattern in patterns:
        match = re.match(pattern, query, flags=re.IGNORECASE)
        if match:
            candidate = _clean_artist_query(match.group(1))
            if candidate:
                return candidate
    return ""


def _match_title_artist(patterns: tuple[str, ...], query: str) -> tuple[str, str] | None:
    for pattern in patterns:
        match = re.match(pattern, query, flags=re.IGNORECASE)
        if not match:
            continue
        title = _clean_artist_query(match.group(1))
        artist = _clean_artist_query(match.group(2)) if len(match.groups()) > 1 else ""
        if title:
            return title, artist
    return None


def _match_artist_title(patterns: tuple[str, ...], query: str) -> tuple[str, str] | None:
    for pattern in patterns:
        match = re.match(pattern, query, flags=re.IGNORECASE)
        if not match:
            continue
        artist = _clean_artist_query(match.group(1))
        title = _clean_artist_query(match.group(2)) if len(match.groups()) > 1 else ""
        if artist and title:
            return artist, title
    return None


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
