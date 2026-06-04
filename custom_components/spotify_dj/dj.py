from __future__ import annotations

from homeassistant.core import HomeAssistant


async def parse_music_request(hass: HomeAssistant, user_text: str, conf: dict) -> dict:
    raise RuntimeError("Direct AI parsing is disabled in SpotifyDJ; use HA Assist via pipeline.py instead")
