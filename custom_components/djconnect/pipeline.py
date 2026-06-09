from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_ASSIST_PIPELINE_ID,
    CONF_DJ_RESPONSE_PROMPT,
    CONF_TTS_LANGUAGE,
    DEFAULT_DJ_RESPONSE_PROMPT,
    DEFAULT_TTS_LANGUAGE,
)

_LOGGER = logging.getLogger(__name__)


async def process_text_with_assist(
    hass: HomeAssistant,
    user_text: str,
    conf: dict[str, Any],
) -> dict[str, Any]:
    """Run text through HA Assist and return a DJConnect intent."""
    assist_context = _assist_context(hass, conf)
    response = await _conversation_process(hass, user_text, assist_context)
    intent = _intent_from_assist_response(response, user_text)
    intent["assist"] = response
    return intent


def _assist_context(hass: HomeAssistant, conf: dict[str, Any]) -> dict[str, Any]:
    """Resolve the configured pipeline into conversation service arguments."""
    pipeline_id = (conf.get(CONF_ASSIST_PIPELINE_ID) or "").strip()
    context: dict[str, Any] = {
        "language": conf.get(CONF_TTS_LANGUAGE) or DEFAULT_TTS_LANGUAGE,
    }
    if not pipeline_id:
        return context

    pipeline = _get_assist_pipeline(hass, pipeline_id)
    if pipeline is None:
        context["agent_id"] = pipeline_id
        return context

    conversation_engine = getattr(pipeline, "conversation_engine", None)
    conversation_language = getattr(pipeline, "conversation_language", None)
    language = conversation_language or getattr(pipeline, "language", None)
    if conversation_engine:
        context["agent_id"] = conversation_engine
    if language:
        context["language"] = language
    context["pipeline_id"] = pipeline_id
    return context


def _get_assist_pipeline(hass: HomeAssistant, pipeline_id: str) -> Any | None:
    try:
        from homeassistant.components.assist_pipeline.pipeline import async_get_pipelines

        for pipeline in async_get_pipelines(hass):
            if getattr(pipeline, "id", None) == pipeline_id:
                return pipeline
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Could not resolve Assist pipeline %s", pipeline_id, exc_info=True)
    return None


async def _conversation_process(
    hass: HomeAssistant,
    user_text: str,
    assist_context: dict[str, Any],
) -> dict[str, Any]:
    language = assist_context.get("language") or DEFAULT_TTS_LANGUAGE
    data = {
        "text": _djconnect_assist_prompt(user_text, str(language)),
        "language": language,
    }
    if assist_context.get("agent_id"):
        data["agent_id"] = assist_context["agent_id"]

    result = await hass.services.async_call(
        "conversation",
        "process",
        data,
        blocking=True,
        return_response=True,
    )
    if not isinstance(result, dict):
        raise RuntimeError("HA Assist did not return response data")
    result["pipeline_id"] = assist_context.get("pipeline_id")
    result["agent_id"] = assist_context.get("agent_id")
    return result


def _djconnect_assist_prompt(
    user_text: str,
    language: str,
) -> str:
    """Add DJConnect-specific DJ response guidance to the Assist text request."""
    if str(language or "").lower().startswith("nl"):
        return (
            "Analyseer alleen deze DJConnect muziekopdracht. Bepaal de artiest "
            "of playlist voor Spotify. Geef waar mogelijk djconnect intentdata terug. "
            "Gebruik geen apparaatbediening en interpreteer de instructietekst niet "
            "als apparaatnaam. "
            f"Opdracht: {user_text}"
        )
    return (
        "Analyze only this DJConnect music request. Determine the artist or playlist "
        "for Spotify. Return djconnect intent data when possible. Do not control "
        "Home Assistant devices and do not treat the instruction text as a device name. "
        f"Request: {user_text}"
    )


async def generate_dj_response_with_assist(
    hass: HomeAssistant,
    *,
    media: dict[str, Any],
    fallback_text: str,
    conf: dict[str, Any],
) -> str:
    """Ask HA Assist for a short DJ response using resolved playback metadata."""
    prompt = str(conf.get(CONF_DJ_RESPONSE_PROMPT) or DEFAULT_DJ_RESPONSE_PROMPT).strip()
    language = conf.get(CONF_TTS_LANGUAGE) or DEFAULT_TTS_LANGUAGE
    media_context = _dj_response_media_context(media)
    if not media_context:
        return fallback_text
    media_lines = _dj_response_media_lines(media_context)
    text = (
        "Je schrijft alleen een korte gesproken DJ response voor het DJConnect device. "
        "Dit is geen Home Assistant apparaatopdracht. Bedien geen apparaten. "
        "Gebruik deze DJ response prompt als stijl-/inhoudsinstructie: "
        f"{prompt}\n\nMedia:\n{media_lines}\n\n"
        "Antwoord alleen met de tekst die uitgesproken moet worden. Geen JSON, geen uitleg, geen URI."
        if str(language).lower().startswith("nl")
        else "Write only a short spoken DJ response for the DJConnect device. "
        "This is not a Home Assistant device command. Do not control devices. "
        f"Use this DJ response prompt as style/content guidance: {prompt}\n\n"
        f"Media:\n{media_lines}\n\n"
        "Return only the text that should be spoken. No JSON, no explanation, no URI."
    )
    try:
        result = await hass.services.async_call(
            "conversation",
            "process",
            {"text": text, "language": language},
            blocking=True,
            return_response=True,
        )
        response = (result or {}).get("response") or {}
        generated = _speech_from_response(response)
        blocked_reason = _dj_response_block_reason(generated)
        if blocked_reason is None:
            return generated
        _LOGGER.debug(
            "Ignoring unusable Assist DJ response (%s): %s",
            blocked_reason,
            generated,
        )
        return fallback_text
    except Exception:  # noqa: BLE001
        _LOGGER.debug("DJConnect DJ response generation through Assist failed", exc_info=True)
        return fallback_text


def _dj_response_media_context(media: dict[str, Any]) -> dict[str, Any]:
    """Return safe user-facing media metadata for DJ response generation."""
    allowed_keys = (
        "type",
        "title",
        "track_name",
        "name",
        "artist",
        "artist_name",
        "album_name",
        "album",
        "playlist",
        "owner",
    )
    return {
        key: value
        for key in allowed_keys
        if (value := media.get(key)) not in (None, "", [], {})
    }


def _dj_response_media_lines(media_context: dict[str, Any]) -> str:
    labels = {
        "type": "type",
        "title": "titel",
        "track_name": "nummer",
        "name": "naam",
        "artist": "artiest",
        "artist_name": "artiest",
        "album_name": "album",
        "album": "album",
        "playlist": "playlist",
        "owner": "eigenaar",
    }
    lines = []
    for key, value in media_context.items():
        lines.append(f"{labels.get(key, key)}: {value}")
    return "\n".join(lines)


def _intent_from_assist_response(response: dict[str, Any], user_text: str) -> dict[str, Any]:
    conversation_response = response.get("response") or {}
    response_type = conversation_response.get("response_type")
    if response_type == "error":
        speech = _speech_from_response(conversation_response)
        if _assist_treated_prompt_as_ha_command(speech):
            return _fallback_search_intent(user_text)
        raise RuntimeError(speech or "HA Assist could not process the command")

    data = _djconnect_data(conversation_response)
    has_djconnect_data = _has_djconnect_data(conversation_response)

    intent = {
        "intent": data.get("intent") or "play_music",
        "type": data.get("type") or data.get("media_type") or "search",
        "artist": data.get("artist"),
        "title": data.get("title"),
        "playlist": data.get("playlist"),
        "query": data.get("query") or user_text,
        "spotify_search_query": data.get("spotify_search_query") or data.get("query") or user_text,
        "dj_announcement": data.get("dj_announcement")
        or (_speech_from_response(conversation_response) if has_djconnect_data else ""),
    }
    if not intent["dj_announcement"]:
        intent["dj_announcement"] = "Daar gaan we. Ik zet hem voor je klaar."
    return intent


def _fallback_search_intent(user_text: str) -> dict[str, Any]:
    return {
        "intent": "play_music",
        "type": "search",
        "artist": None,
        "title": None,
        "playlist": None,
        "query": user_text,
        "spotify_search_query": user_text,
        "dj_announcement": "Daar gaan we. Ik zet hem voor je klaar.",
    }


def _assist_treated_prompt_as_ha_command(speech: str) -> bool:
    normalized = " ".join(str(speech or "").lower().split())
    return (
        "djconnect muziekopdracht" in normalized
        or "djconnect music request" in normalized
        or "opdracht " in normalized
        or "request " in normalized
    ) and (
        "geen apparaat vinden" in normalized
        or "niet vinden" in normalized
        or "can't find" in normalized
        or "cannot find" in normalized
        or "no device" in normalized
    )


def _has_djconnect_data(conversation_response: dict[str, Any]) -> bool:
    data = conversation_response.get("data") or {}
    return isinstance(data.get("djconnect"), dict)


def _djconnect_data(conversation_response: dict[str, Any]) -> dict[str, Any]:
    """Extract the structured intent payload returned by Assist, when available."""
    data = conversation_response.get("data") or {}
    if isinstance(data.get("djconnect"), dict):
        return data["djconnect"]
    return data


def _speech_from_response(conversation_response: dict[str, Any]) -> str:
    speech = conversation_response.get("speech") or {}
    plain = speech.get("plain") or {}
    ssml = speech.get("ssml") or {}
    return (plain.get("speech") or ssml.get("speech") or "").strip()


def _is_usable_dj_response(value: str) -> bool:
    """Return whether Assist produced displayable DJ response text."""
    return _dj_response_block_reason(value) is None


def _dj_response_block_reason(value: str) -> str | None:
    """Return why generated DJ response text should not be displayed."""
    text = str(value or "").strip()
    if not text:
        return "empty"
    normalized = " ".join(text.lower().split())
    blocked_fragments = (
        "geen apparaat vinden",
        "kan geen apparaat",
        "can't find",
        "cannot find",
        "no device",
        "home assistant devices",
        "djconnect muziekopdracht",
        "djconnect music request",
        "spotify:artist:",
        "spotify:track:",
        "spotify:album:",
        "spotify:playlist:",
        "{'type'",
        '"type"',
        "'uri'",
        '"uri"',
    )
    for fragment in blocked_fragments:
        if fragment in normalized:
            return fragment
    return None
