from __future__ import annotations

from typing import Any
from homeassistant.core import HomeAssistant

from .pipeline import process_text_with_assist
from .spotify import play_from_intent


async def process_text_command(
    hass: HomeAssistant, runtime, user_text: str, play: bool = True
) -> dict[str, Any]:
    runtime.update(last_text=user_text, last_error=None)
    conf = runtime.config
    intent = await process_text_with_assist(hass, user_text, conf)
    playback = None
    if play:
        playback = await play_from_intent(hass, runtime, intent, conf)
    dj_text = intent.get("dj_announcement") or "Daar gaan we. Ik zet hem voor je klaar."
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
