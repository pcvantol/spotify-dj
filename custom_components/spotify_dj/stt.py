from __future__ import annotations

from homeassistant.core import HomeAssistant


async def wav_to_text(hass: HomeAssistant, wav: bytes, conf: dict) -> str:
    raise RuntimeError("Direct STT is disabled in SpotifyDJ; use HA Assist pipeline audio handling instead")
