from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_ASSIST_PIPELINE_ID,
    CONF_DJ_STYLE,
    CONF_TTS_LANGUAGE,
    DEFAULT_DJ_STYLE,
    DEFAULT_TTS_LANGUAGE,
    DJ_STYLE_CALM_EVENING,
    DJ_STYLE_CLASSIC_DUTCH_RADIO,
    DJ_STYLE_FESTIVAL,
    DJ_STYLE_MINIMAL,
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
        "dj_style": conf.get(CONF_DJ_STYLE) or DEFAULT_DJ_STYLE,
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
    dj_style = assist_context.get("dj_style") or DEFAULT_DJ_STYLE
    data = {
        "text": _djconnect_assist_prompt(user_text, str(language), str(dj_style)),
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
    dj_style: str = DEFAULT_DJ_STYLE,
) -> str:
    """Add DJConnect-specific DJ response guidance to the Assist text request."""
    style_instruction = _dj_style_instruction(dj_style, language)
    if str(language or "").lower().startswith("nl"):
        return (
            "Verwerk deze DJConnect muziekopdracht en maak waar mogelijk "
            "djconnect intentdata. Als je een dj_announcement geeft, vertel "
            "ook één kort leuk feitje over de artiest en/of het nummer. "
            f"DJ stijl: {style_instruction}. "
            f"Opdracht: {user_text}"
        )
    return (
        "Handle this DJConnect music request and return djconnect intent data "
        "when possible. If you provide a dj_announcement, also include one short "
        f"fun fact about the artist and/or song. DJ style: {style_instruction}. "
        f"Request: {user_text}"
    )


def _dj_style_instruction(dj_style: str, language: str) -> str:
    """Translate DJ style settings into concrete prompt guidance."""
    is_nl = str(language or "").lower().startswith("nl")
    if dj_style == DJ_STYLE_CALM_EVENING:
        return (
            "warm, rustig en ontspannen; maximaal één korte zin, geen hype"
            if is_nl
            else "warm, calm and relaxed; one short sentence at most, no hype"
        )
    if dj_style == DJ_STYLE_FESTIVAL:
        return (
            "energiek en enthousiast alsof je een festivalstage opent; kort houden"
            if is_nl
            else "energetic and excited like opening a festival stage; keep it short"
        )
    if dj_style == DJ_STYLE_MINIMAL:
        return (
            "zeer kort en functioneel; geen extra grapjes, maximaal enkele woorden"
            if is_nl
            else "very short and functional; no extra jokes, only a few words"
        )
    if dj_style == DJ_STYLE_CLASSIC_DUTCH_RADIO:
        return (
            "klassieke Nederlandse radio-DJ; vriendelijk, herkenbaar en licht enthousiast"
            if is_nl
            else "classic Dutch radio DJ; friendly, familiar and lightly upbeat"
        )
    return (
        "vriendelijk en kort"
        if is_nl
        else "friendly and brief"
    )


def _intent_from_assist_response(response: dict[str, Any], user_text: str) -> dict[str, Any]:
    conversation_response = response.get("response") or {}
    response_type = conversation_response.get("response_type")
    if response_type == "error":
        speech = _speech_from_response(conversation_response)
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
