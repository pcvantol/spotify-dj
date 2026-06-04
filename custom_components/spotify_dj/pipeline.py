from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_ASSIST_PIPELINE_ID,
    CONF_TTS_LANGUAGE,
    DEFAULT_TTS_LANGUAGE,
)

_LOGGER = logging.getLogger(__name__)


async def process_text_with_assist(
    hass: HomeAssistant,
    user_text: str,
    conf: dict[str, Any],
) -> dict[str, Any]:
    """Run text through HA Assist and return a SpotifyDJ intent."""
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
    data = {
        "text": user_text,
        "language": assist_context.get("language") or DEFAULT_TTS_LANGUAGE,
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
        raise RuntimeError("HA Assist gaf geen response-data terug")
    result["pipeline_id"] = assist_context.get("pipeline_id")
    result["agent_id"] = assist_context.get("agent_id")
    return result


def _intent_from_assist_response(response: dict[str, Any], user_text: str) -> dict[str, Any]:
    conversation_response = response.get("response") or {}
    response_type = conversation_response.get("response_type")
    if response_type == "error":
        speech = _speech_from_response(conversation_response)
        raise RuntimeError(speech or "HA Assist kon de opdracht niet verwerken")

    data = _spotifydj_data(conversation_response)

    intent = {
        "intent": data.get("intent") or "play_music",
        "type": data.get("type") or data.get("media_type") or "search",
        "artist": data.get("artist"),
        "title": data.get("title"),
        "playlist": data.get("playlist"),
        "query": data.get("query") or user_text,
        "spotify_search_query": data.get("spotify_search_query") or data.get("query") or user_text,
        "dj_announcement": data.get("dj_announcement")
        or _speech_from_response(conversation_response),
    }
    if not intent["dj_announcement"]:
        intent["dj_announcement"] = "Daar gaan we. Ik zet hem voor je klaar."
    return intent


def _spotifydj_data(conversation_response: dict[str, Any]) -> dict[str, Any]:
    """Extract the structured intent payload returned by Assist, when available."""
    data = conversation_response.get("data") or {}
    if isinstance(data.get("spotify_dj"), dict):
        return data["spotify_dj"]
    return data


def _speech_from_response(conversation_response: dict[str, Any]) -> str:
    speech = conversation_response.get("speech") or {}
    plain = speech.get("plain") or {}
    ssml = speech.get("ssml") or {}
    return (plain.get("speech") or ssml.get("speech") or "").strip()
