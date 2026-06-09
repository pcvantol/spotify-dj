from __future__ import annotations

from typing import Any
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DJ_RESPONSE_PROMPT,
    CONF_TTS_LANGUAGE,
    DEFAULT_DJ_RESPONSE_PROMPT,
    DEFAULT_TTS_LANGUAGE,
)
from .pipeline import generate_dj_response_with_assist, process_text_with_assist
from .spotify import play_from_intent


async def process_text_command(
    hass: HomeAssistant, runtime, user_text: str, play: bool = True
) -> dict[str, Any]:
    runtime.update(last_text=user_text, last_stt_text=user_text, last_error=None)
    conf = runtime.config
    intent = await process_text_with_assist(hass, user_text, conf)
    runtime.update(last_intent=intent)
    playback = None
    if play:
        playback = await play_from_intent(hass, runtime, intent, conf)
    fallback_dj_text = _dj_response_text(intent, playback, conf)
    dj_text = await generate_dj_response_with_assist(
        hass,
        media=_resolved_media(playback) or intent,
        fallback_text=fallback_dj_text,
        conf=conf,
    )
    result = {
        "text": user_text,
        "intent": intent,
        "playback": playback,
        "dj_text": dj_text,
    }
    runtime.update(
        last_intent=intent,
        last_dj_text=dj_text,
        last_playback=playback,
        last_error=None,
    )
    return result


def _dj_response_text(
    intent: dict[str, Any],
    playback: dict[str, Any] | None,
    conf: dict[str, Any],
) -> str:
    """Create a concrete device DJ response from the resolved playback result."""
    media = _resolved_media(playback) or intent
    title = _first_text(media, "track_name", "title", "name")
    artist = _first_text(media, "artist", "artist_name")
    album = _first_text(media, "album_name", "album")
    playlist = _first_text(media, "playlist", "name")
    prompt = str(conf.get(CONF_DJ_RESPONSE_PROMPT) or DEFAULT_DJ_RESPONSE_PROMPT)
    language = str(conf.get(CONF_TTS_LANGUAGE) or DEFAULT_TTS_LANGUAGE)
    is_nl = language.lower().startswith("nl")

    if title or artist:
        return _track_response(
            title=title,
            artist=artist,
            album=album,
            prompt=prompt,
            is_nl=is_nl,
        )
    if playlist:
        return _playlist_response(playlist, prompt=prompt, is_nl=is_nl)

    announcement = str(intent.get("dj_announcement") or "").strip()
    if announcement and not _is_generic_announcement(announcement):
        return announcement
    return "Daar gaan we. Ik zet hem voor je klaar." if is_nl else "Here we go. I'll start it for you."


def _resolved_media(playback: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(playback, dict):
        return {}
    resolved = playback.get("resolved_media")
    if isinstance(resolved, dict) and any(resolved.get(key) for key in ("title", "track_name", "artist")):
        return resolved
    response = playback.get("device_response") or {}
    if isinstance(response, dict):
        current = response.get("playback") or response
        if isinstance(current, dict):
            return current
    return {}


def _track_response(
    *,
    title: str,
    artist: str,
    album: str,
    prompt: str,
    is_nl: bool,
) -> str:
    subject = _track_subject(title, artist, is_nl=is_nl)
    prompt_words = prompt.lower()
    if "minimaal" in prompt_words or "minimal" in prompt_words:
        return subject
    if "rustig" in prompt_words or "calm" in prompt_words:
        if is_nl:
            return f"Rustig erin: {subject}. Even laten landen."
        return f"Ease into this one: {subject}. Let it breathe."
    if "festival" in prompt_words or "energiek" in prompt_words:
        if is_nl:
            return f"Handen omhoog: {subject}. Dit is er eentje om wakker van te worden."
        return f"Hands up: {subject}. This one should wake the room."
    if album and artist:
        return f"Daar is {artist}, met {title}. Van {album}; zet 'm maar lekker open."
    return f"Daar is {subject}. Zet 'm maar lekker open." if is_nl else f"Here is {subject}. Turn it up."


def _playlist_response(playlist: str, *, prompt: str, is_nl: bool) -> str:
    prompt_words = prompt.lower()
    if "minimaal" in prompt_words or "minimal" in prompt_words:
        return playlist
    if "festival" in prompt_words or "energiek" in prompt_words:
        return f"Daar gaan we: {playlist}. Tijd om los te komen." if is_nl else f"Here we go: {playlist}. Time to move."
    if "rustig" in prompt_words or "calm" in prompt_words:
        return f"Ik zet {playlist} rustig voor je op." if is_nl else f"I'll ease into {playlist} for you."
    return f"Ik zet {playlist} voor je klaar." if is_nl else f"I'll start {playlist} for you."


def _track_subject(title: str, artist: str, *, is_nl: bool) -> str:
    if title and artist:
        return f"{title} van {artist}" if is_nl else f"{title} by {artist}"
    return title or artist


def _first_text(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(source.get(key) or "").strip()
        if value:
            return value
    return ""


def _is_generic_announcement(value: str) -> bool:
    normalized = " ".join(value.lower().split())
    return normalized in {
        "daar gaan we.",
        "daar gaan we",
        "daar gaan we. ik zet hem voor je klaar.",
        "ik zet hem voor je klaar.",
        "here we go.",
        "here we go",
        "here we go. i'll start it for you.",
    }
