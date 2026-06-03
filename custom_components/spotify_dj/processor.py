from __future__ import annotations

from typing import Any
from homeassistant.core import HomeAssistant

from .dj import parse_music_request
from .spotify import play_from_intent

async def process_text_command(hass: HomeAssistant, runtime, user_text: str, play: bool = True) -> dict[str, Any]:
    conf = runtime.config
    intent = await parse_music_request(hass, user_text, conf)
    playback = None
    if play:
        playback = await play_from_intent(hass, intent, conf)
    dj_text = intent.get("dj_announcement") or "Daar gaan we. Ik zet hem voor je klaar."
    runtime.update(last_text=user_text, last_intent=intent, last_dj_text=dj_text, last_playback=playback, last_error=None)
    return {"text": user_text, "intent": intent, "playback": playback, "dj_text": dj_text}
